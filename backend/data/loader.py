"""Read the curated, local Giovanni exports used by the GAIA demo."""

import csv
from functools import lru_cache
from pathlib import Path
import re

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
