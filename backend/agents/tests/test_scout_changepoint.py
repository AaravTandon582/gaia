"""Regime dates survive scout serialization and respect the monthly grid."""
import asyncio
from threading import Event

import numpy as np
import pandas as pd
import pytest

from backend.agents import scout as scout_module
from backend.agents.cancellation import scan_cancel_event
from backend.agents.scout import ScoutAgent, changepoint_dates


def install_series(monkeypatch, values):
    series = pd.Series(values, index=pd.date_range("2000", periods=len(values), freq="MS"))
    monkeypatch.setattr(scout_module, "available_series", lambda *_: ["Rainf_f_tavg"])
    monkeypatch.setattr(scout_module, "load_series", lambda *_: (series, {}))
    return series


def test_scout_reports_real_shift_as_calendar_date(monkeypatch):
    rng = np.random.default_rng(12)
    series = install_series(monkeypatch, np.r_[rng.normal(0, .15, 80), rng.normal(5, .15, 80)])
    result = ScoutAgent("hydro")._scan(["amazon"], ("2000-01-01", "2025-12-31"))[0]
    assert result["changepoints"], "An empty result would hide a date-serialization failure"
    positions = [series.index.get_loc(pd.Timestamp(date)) for date in result["changepoints"]]
    assert any(abs(position - 80) <= 4 for position in positions)
    assert all(isinstance(date, str) and date in result["dates"] for date in result["changepoints"])


def test_scout_changepoints_empty_for_steady_series(monkeypatch):
    install_series(monkeypatch, np.ones(36))
    result = ScoutAgent("hydro")._scan(["amazon"], ("2000-01-01", "2002-12-01"))[0]
    assert result["values"] == [1.] * 36
    assert result["changepoints"] == []


def test_missing_values_do_not_compress_monthly_grid(monkeypatch):
    values = np.arange(48, dtype=float)
    values[10] = np.nan
    install_series(monkeypatch, values)
    with pytest.raises(ValueError, match="finite monthly"):
        ScoutAgent("hydro")._scan(["amazon"], ("2000-01-01", "2003-12-01"))


def test_boundaries_are_invariant_to_measurement_units():
    values = np.r_[np.zeros(40), np.ones(40)]
    dates = pd.date_range("2000", periods=80, freq="MS")
    first = changepoint_dates(values, dates)
    assert first
    assert first == changepoint_dates(values * 1e-5 + 273, dates)


def test_regime_detection_observes_cancellation():
    cancelled = Event()
    cancelled.set()
    token = scan_cancel_event.set(cancelled)
    try:
        with pytest.raises(asyncio.CancelledError):
            changepoint_dates(np.arange(48), pd.date_range("2000", periods=48, freq="MS"))
    finally:
        scan_cancel_event.reset(token)


def test_unknown_region_raises():
    with pytest.raises(ValueError, match="Unsupported region"):
        ScoutAgent("hydro")._scan(["atlantis"], ("2000-01-01", "2025-12-31"))
