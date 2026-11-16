"""Read the curated, local Giovanni exports used by the GAIA demo."""

import csv
import os
from functools import lru_cache
from pathlib import Path
import re
import tempfile

import numpy as np
import pandas as pd

CACHE_DIR = Path(__file__).parent / "cache"
REGIONS = [
    dict(id="amazon", name="Amazon Basin", lat=-5, lon=-60,
         bounds=dict(west=-75, south=-15, east=-45, north=5)),
    dict(id="arctic", name="Arctic", lat=75, lon=0,
         bounds=dict(west=-180, south=65, east=180, north=85)),
    dict(id="mediterranean", name="Mediterranean", lat=38, lon=15,
         bounds=dict(west=-10, south=30, east=40, north=46)),
    dict(id="sahel", name="Sahel", lat=15, lon=5,
         bounds=dict(west=-20, south=10, east=40, north=20)),
    dict(id="california", name="California", lat=37, lon=-120,
         bounds=dict(west=-125, south=32, east=-114, north=42)),
]
VARIABLES = {
    "T2M": ("Temperature", "atmosphere", "K"),
    "SNOMAS": ("Snow mass", "cryo", "kg/m²"),
    "Rainf_f_tavg": ("Precipitation", "hydro", "kg/m²/s"),
    "Evap_tavg": ("Evapotranspiration", "hydro", "kg/m²/s"),
    "SoilMoi0_10cm_inst": ("Soil moisture", "hydro", "kg/m²"),
}

# Match the products used by the curated CSVs; do not silently substitute models.
DATASETS = {
    "T2M": ("M2T1NXSLV", "5.12.4"),
    "SNOMAS": ("M2TMNXLND", "5.12.4"),
    "Rainf_f_tavg": ("GLDAS_NOAH025_M", "2.1"),
    "Evap_tavg": ("GLDAS_NOAH025_3H", "2.1"),
    "SoilMoi0_10cm_inst": ("GLDAS_NOAH025_M", "2.1"),
}
REGIONAL_DATASETS = {
    ("sahel", "Evap_tavg"): ("FLDAS_NOAH01_C_GL_M", "001"),
    ("mediterranean", "T2M"): ("M2TMNXSLV", "5.12.4"),
}

# Water-balance term mapping: which cached variable serves as each budget
# component, or None when no compatible product is available for the region.
# ``Q`` is total runoff (surface + subsurface); only Amazon storm surface
# runoff (Qs_acc) is cached and it is not total runoff. ``dS`` is total
# storage change; shallow soil moisture (0-10 cm) does not qualify, and no
# region currently caches a compatible storage-change product. As a result
# every region reports ``inputs unavailable`` until compatible products exist.
WATER_BALANCE_TERMS = {
    "amazon": dict(P="Rainf_f_tavg", ET="Evap_tavg", Q=None, dS=None),
    "sahel": dict(P="Rainf_f_tavg", ET="Evap_tavg", Q=None, dS=None),
    "mediterranean": dict(P="Rainf_f_tavg", ET="Evap_tavg", Q=None, dS=None),
    "arctic": dict(P=None, ET=None, Q=None, dS=None),
    "california": dict(P=None, ET=None, Q=None, dS=None),
}


def available_series(region, domain=None):
    if region not in {item["id"] for item in REGIONS}:
        raise ValueError(f"Unsupported region: {region}")
    return [variable for variable, (_, kind, _) in VARIABLES.items()
            if (domain is None or kind == domain)
            and (CACHE_DIR / f"{region}_{variable}.csv").is_file()]


def region_catalog():
    return [{**region, "variables": available_series(region["id"])} for region in REGIONS]


@lru_cache(maxsize=32)
def _read_export(path_string, modified):
    # mtime is part of the cache key so replacing an export refreshes the data.
    dates, values, fills, metadata = [], [], [], {}
    path = Path(path_string)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 2:
                continue
            key = row[0].strip()
            if re.match(r"^\d{4}-\d{2}-\d{2}", key):
                dates.append(key)
                values.append(float(row[1]) if row[1].strip() else np.nan)
            elif key.startswith("Fill Value"):
                fills.append(float(row[1]))
            elif key == "time":
                metadata["dataset"] = row[1].strip().removeprefix("mean_")
            elif key == "Data Bounding Box:":
                metadata["source_bounds"] = [float(value) for value in row[1].split(",")]
    if not dates:
        raise ValueError(f"No observations in {path.name}")
    index = pd.to_datetime(dates, format="mixed", utc=True).tz_convert(None)
    series = pd.Series(values, index=index, dtype=float)
    series = series.mask(series.isin(fills) | ~np.isfinite(series))
    series = series.groupby(level=0).mean().sort_index().resample("MS").mean()
    return series, {**metadata, "source_file": path.name}


def load_series(region, variable, date_range):
    if variable not in available_series(region):
        raise ValueError(f"No cached data for {region}:{variable}")
    path = CACHE_DIR / f"{region}_{variable}.csv"
    series, metadata = _read_export(str(path), path.stat().st_mtime_ns)
    start, end = (pd.Timestamp(value).to_period("M").to_timestamp() for value in date_range)
    series = series.loc[start:end].copy()
    if len(series) < 24:
        raise ValueError(f"{region}:{variable} needs at least 24 cached months in the selected range")
    if not np.isfinite(series.to_numpy()).all():
        raise ValueError(f"Missing monthly observations for {region}:{variable}")
    return series, dict(metadata)


class DataLoader:
    """Cache-first monthly data retrieval, with optional authenticated downloads.

    Downloads are explicit calls to fetch, never triggered by a dashboard scan.
    Supported files are CF-compliant NetCDF/HDF5 on regular latitude/longitude
    grids. Monthly means retain source units (rates are not converted to totals).
    """

    def __init__(self, cache_dir=CACHE_DIR, *, allow_download=True):
        self.cache_dir = Path(cache_dir)
        self.allow_download = allow_download

    def list_variables(self):
        return {name: dict(description=label, domain=domain, units=units,
                           short_name=DATASETS[name][0], version=DATASETS[name][1],
                           regional_sources={region: dict(short_name=source[0], version=source[1])
                               for (region, variable), source in REGIONAL_DATASETS.items()
                               if variable == name})
                for name, (label, domain, units) in VARIABLES.items()}

    def fetch(self, variable, region, date_range):
        """Return (monthly numpy values, datetime64 dates), with no imputation."""
        if variable not in VARIABLES:
            raise ValueError(f"Unsupported variable: {variable}")
        location = next((item for item in REGIONS if item["id"] == region), None)
        if location is None:
            raise ValueError(f"Unsupported region: {region}")
        if len(date_range) != 2:
            raise ValueError("date_range needs a start and end")
        dates = pd.to_datetime(list(date_range), utc=True, errors="raise").tz_convert(None)
        if dates.hasnans or dates[0] > dates[1]:
            raise ValueError("date_range must contain ordered, valid dates")
        months = pd.date_range(dates[0].to_period("M").to_timestamp(),
                               dates[1].to_period("M").to_timestamp(), freq="MS")
        canonical = self.cache_dir / f"{region}_{variable}.csv"
        ranged = self.cache_dir / f"{region}_{variable}_{months[0]:%Y%m}_{months[-1]:%Y%m}.csv"
        for path in (canonical, ranged):
            if path.is_file():
                series, _ = _read_export(str(path), path.stat().st_mtime_ns)
                selected = series.reindex(months)
                if np.isfinite(selected.to_numpy()).all():
                    return selected.to_numpy(copy=True), months.to_numpy(copy=True)
        if not self.allow_download:
            raise ValueError(f"No complete cached data for {region}:{variable}")
        try:
            import earthaccess
        except ImportError as error:
            raise RuntimeError("Install backend/data/requirements.txt for Earthdata downloads") from error
        # Explicit strategies avoid a blocking interactive password prompt in a server.
        strategy = "environment" if any(os.getenv(key) for key in
            ("EARTHDATA_TOKEN", "EARTHDATA_USERNAME", "EARTHDATA_PASSWORD")) else "netrc"
        auth = earthaccess.login(strategy=strategy)
        if not auth.authenticated:
            raise RuntimeError("Earthdata authentication unavailable; configure environment credentials or .netrc")
        bounds = location["bounds"]
        bbox = tuple(bounds[key] for key in ("west", "south", "east", "north"))
        short_name, version = REGIONAL_DATASETS.get((region, variable), DATASETS[variable])
        # Search entire calendar months, even for partial-month date selections.
        end = months[-1] + pd.offsets.MonthBegin(1) - pd.Timedelta(seconds=1)
        granules = earthaccess.search_data(short_name=short_name, version=version,
            bounding_box=bbox, temporal=(months[0].isoformat(), end.isoformat()))
        if not granules:
            raise ValueError(f"No Earthdata granules for {region}:{variable}")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="gaia-download-", dir=self.cache_dir) as staging:
            paths = earthaccess.download(granules, local_path=staging)
            if not paths:
                raise ValueError("Earthdata returned no downloaded files")
            series = self._regional_monthly(paths, variable, bbox).reindex(months)
        if not np.isfinite(series.to_numpy()).all():
            raise ValueError("Downloaded data have missing monthly observations; cache not written")
        # Keep curated exports intact; cache this exact interval atomically.
        with tempfile.NamedTemporaryFile(mode="w", dir=self.cache_dir, suffix=".csv",
                                         delete=False, newline="") as handle:
            temporary = Path(handle.name)
            writer = csv.writer(handle)
            writer.writerow(["Data Bounding Box:", ",".join(map(str, bbox))])
            writer.writerow(["time", f"mean_{short_name}_{version}_{variable}"])
            writer.writerows(zip(months.strftime("%Y-%m-%d"), series.to_numpy()))
        try:
            temporary.replace(ranged)
        finally:
            temporary.unlink(missing_ok=True)
        return series.to_numpy(copy=True), months.to_numpy(copy=True)

    @staticmethod
    def _regional_monthly(paths, variable, bbox):
        import xarray as xr

        west, south, east, north = bbox
        pieces = []
        for path in paths:
            with xr.open_dataset(path, decode_cf=True) as dataset:
                if variable not in dataset:
                    raise ValueError(f"Downloaded file lacks {variable}")
                field = dataset[variable]
                rename = {name: target for name, target in
                          (("latitude", "lat"), ("longitude", "lon")) if name in field.dims}
                field = field.rename(rename)
                if set(field.dims) != {"time", "lat", "lon"}:
                    raise ValueError("Expected a time/latitude/longitude surface variable")
                if field.lat.ndim != 1 or field.lon.ndim != 1:
                    raise ValueError("Only rectilinear latitude/longitude grids are supported")
                # Normalize 0..360 longitudes; boolean indexing also handles descending latitude.
                field = field.assign_coords(lon=(field.lon + 180) % 360 - 180)
                for coordinate in (field.lat, field.lon.sortby(field.lon)):
                    steps = np.diff(coordinate.values)
                    tolerance = (8 * np.finfo(coordinate.dtype).eps *
                                 max(1., float(np.abs(coordinate).max()))
                                 if np.issubdtype(coordinate.dtype, np.floating) else 0.)
                    if len(steps) and (np.any(steps == 0) or
                                      not np.allclose(steps, steps[0], atol=tolerance)):
                        raise ValueError("Area weighting requires a regular grid")
                lon_mask = ((field.lon >= west) & (field.lon <= east) if west <= east else
                            (field.lon >= west) | (field.lon <= east))
                field = field.where((field.lat >= south) & (field.lat <= north) & lon_mask, drop=True)
                if not field.sizes["lat"] or not field.sizes["lon"]:
                    raise ValueError("No grid cells inside the requested region")
                weights = np.cos(np.deg2rad(field.lat))
                # CF decoding masks fill values; weights renormalize over valid cells.
                regional = field.weighted(weights).mean(("lat", "lon"), skipna=True)
                pieces.append(regional.to_series())
        series = pd.concat(pieces).sort_index()
        if not isinstance(series.index, pd.DatetimeIndex) or series.index.hasnans:
            raise ValueError("Downloaded times must use a valid Gregorian calendar")
        if series.index.has_duplicates:
            raise ValueError("Downloaded granules contain overlapping timestamps")
        return series.resample("MS").mean()
