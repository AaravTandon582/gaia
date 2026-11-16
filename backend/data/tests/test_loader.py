from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from backend.data.loader import DataLoader


def test_cached_fetch_needs_no_remote_dependencies(tmp_path, monkeypatch):
    path = tmp_path / "amazon_Rainf_f_tavg.csv"
    path.write_text("time,mean_test\n2020-01-01,1\n2020-02-01,2\n2020-03-01,3\n")
    loader = DataLoader(tmp_path, allow_download=False)
    values, dates = loader.fetch("Rainf_f_tavg", "amazon", ["2020-01-15", "2020-02-20"])
    np.testing.assert_array_equal(values, [1, 2])
    np.testing.assert_array_equal(dates, pd.date_range("2020", periods=2, freq="MS").to_numpy())
    with pytest.raises(ValueError, match="complete cached"):
        loader.fetch("Rainf_f_tavg", "amazon", ["2020-01-01", "2020-04-30"])
    path.write_text("time,mean_test\n2020-01-01,1\n2020-03-01,3\n")
    with pytest.raises(ValueError, match="complete cached"):
        loader.fetch("Rainf_f_tavg", "amazon", ["2020-01-01", "2020-03-31"])


@pytest.mark.parametrize("variable,region,dates", [
    ("missing", "amazon", ["2020", "2021"]),
    ("T2M", "missing", ["2020", "2021"]),
    ("T2M", "amazon", ["2021", "2020"]),
    ("T2M", "amazon", ["NaT", "2020"]),
])
def test_invalid_request(variable, region, dates, tmp_path):
    with pytest.raises(ValueError):
        DataLoader(tmp_path).fetch(variable, region, dates)


def grid_file(tmp_path, *, months=("2020-01-01", "2020-02-01"), engine="scipy"):
    xr = pytest.importorskip("xarray")
    # Descending latitude; 0..360 longitude. Only 300E lies in Amazon.
    data = np.array([[[99., 6.], [99., 2.]], [[99., 12.], [99., 4.]]])[:len(months)]
    ds = xr.Dataset({"Rainf_f_tavg": (("time", "latitude", "longitude"), data)},
                    coords={"time": pd.to_datetime(list(months)),
                            "latitude": [5., -15.], "longitude": [100., 300.]})
    path = tmp_path / "granule.nc"
    ds.to_netcdf(path, engine=engine)
    return path


@pytest.mark.parametrize("engine", ["scipy", "h5netcdf"])
def test_download_search_extraction_and_cache_roundtrip(tmp_path, monkeypatch, engine):
    earthaccess = pytest.importorskip("earthaccess")
    if engine == "h5netcdf":
        pytest.importorskip("h5py")
        pytest.importorskip("h5netcdf")
    path = grid_file(tmp_path, engine=engine)
    login = Mock(return_value=SimpleNamespace(authenticated=True))
    search = Mock(return_value=["granule"])
    download = Mock(return_value=[path])
    monkeypatch.setenv("EARTHDATA_TOKEN", "test-token")
    monkeypatch.setattr(earthaccess, "login", login)
    monkeypatch.setattr(earthaccess, "search_data", search)
    monkeypatch.setattr(earthaccess, "download", download)
    loader = DataLoader(tmp_path / "cache")
    values, dates = loader.fetch("Rainf_f_tavg", "amazon", ["2020-01-15", "2020-02-15"])
    weights = np.cos(np.deg2rad([5, -15]))
    expected = np.average([[6, 2], [12, 4]], weights=weights, axis=1)
    np.testing.assert_allclose(values, expected)
    login.assert_called_once_with(strategy="environment")
    search.assert_called_once_with(short_name="GLDAS_NOAH025_M", version="2.1",
        bounding_box=(-75, -15, -45, 5), temporal=("2020-01-01T00:00:00", "2020-02-29T23:59:59"))
    # The next fetch must read the CSV and never invoke Earthdata again.
    login.side_effect = AssertionError("cache miss")
    again, again_dates = loader.fetch("Rainf_f_tavg", "amazon", ["2020-01-01", "2020-02-29"])
    np.testing.assert_allclose(again, values)
    np.testing.assert_array_equal(again_dates, dates)
    assert not (loader.cache_dir / "amazon_Rainf_f_tavg.csv").exists()


def test_partial_download_is_not_cached(tmp_path, monkeypatch):
    earthaccess = pytest.importorskip("earthaccess")
    path = grid_file(tmp_path, months=("2020-01-01",))
    monkeypatch.setattr(earthaccess, "login", Mock(return_value=SimpleNamespace(authenticated=True)))
    monkeypatch.setattr(earthaccess, "search_data", Mock(return_value=["granule"]))
    monkeypatch.setattr(earthaccess, "download", Mock(return_value=[path]))
    cache = tmp_path / "cache"
    with pytest.raises(ValueError, match="missing monthly"):
        DataLoader(cache).fetch("Rainf_f_tavg", "amazon", ["2020-01-01", "2020-02-29"])
    assert not list(cache.glob("*.csv"))


def test_missing_authentication_does_not_prompt_or_search(tmp_path, monkeypatch):
    earthaccess = pytest.importorskip("earthaccess")
    for key in ("EARTHDATA_TOKEN", "EARTHDATA_USERNAME", "EARTHDATA_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    login = Mock(return_value=SimpleNamespace(authenticated=False))
    search = Mock()
    monkeypatch.setattr(earthaccess, "login", login)
    monkeypatch.setattr(earthaccess, "search_data", search)
    with pytest.raises(RuntimeError, match="authentication"):
        DataLoader(tmp_path).fetch("T2M", "amazon", ["2020", "2021"])
    login.assert_called_once_with(strategy="netrc")
    search.assert_not_called()


def test_extraction_rejects_missing_variable_and_overlapping_times(tmp_path):
    path = grid_file(tmp_path)
    with pytest.raises(ValueError, match="lacks"):
        DataLoader._regional_monthly([path], "T2M", (-75, -15, -45, 5))
    with pytest.raises(ValueError, match="overlapping"):
        DataLoader._regional_monthly([path, path], "Rainf_f_tavg", (-75, -15, -45, 5))


def test_catalog_exposes_units_and_dataset():
    variables = DataLoader().list_variables()
    assert variables["Rainf_f_tavg"]["short_name"] == "GLDAS_NOAH025_M"
    assert variables["Rainf_f_tavg"]["units"] == "kg/m²/s"
    assert len(variables) == 5
    assert variables["Evap_tavg"]["regional_sources"]["sahel"]["short_name"] == "FLDAS_NOAH01_C_GL_M"


@pytest.mark.parametrize("region,variable,short_name,version", [
    ("sahel", "Evap_tavg", "FLDAS_NOAH01_C_GL_M", "001"),
    ("mediterranean", "T2M", "M2TMNXSLV", "5.12.4"),
])
def test_download_preserves_regional_product(region, variable, short_name, version,
                                            tmp_path, monkeypatch):
    earthaccess = pytest.importorskip("earthaccess")
    search = Mock(return_value=["granule"])
    monkeypatch.setattr(earthaccess, "login", Mock(return_value=SimpleNamespace(authenticated=True)))
    monkeypatch.setattr(earthaccess, "search_data", search)
    monkeypatch.setattr(earthaccess, "download", Mock(return_value=["granule.nc"]))
    loader = DataLoader(tmp_path)
    monkeypatch.setattr(loader, "_regional_monthly",
                        Mock(return_value=pd.Series([1.], index=pd.date_range("2020", periods=1))))
    loader.fetch(variable, region, ["2020-01-01", "2020-01-31"])
    assert search.call_args.kwargs["short_name"] == short_name
    assert search.call_args.kwargs["version"] == version
