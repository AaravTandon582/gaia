import numpy as np
import pandas as pd
import pytest

from backend.analysis.trend import analyze_trend


@pytest.mark.parametrize("slope", [0.08, -0.08])
def test_known_trend_survives_seasonal_adjustment(slope):
    t = np.arange(120)
    seasonal = 5 * np.sin(2 * np.pi * t / 12)
    signal = 10 + slope * t + seasonal
    original = signal.copy()
    result = analyze_trend(signal, pd.date_range("2000-01-01", periods=120, freq="MS"))
    np.testing.assert_allclose(result["deseasonalized"], 10 + slope * t, atol=1e-10)
    assert result["slope"] == pytest.approx(slope)
    assert result["sens_slope"] == pytest.approx(slope)
    assert result["r_squared"] == pytest.approx(1)
    assert result["p_value"] < 0.001
    assert result["mk_p"] < 0.001
    assert result["is_significant"]
    assert result["mk_trend"] == ("increasing" if slope > 0 else "decreasing")
    assert "statistically significant" in result["verdict"]
    np.testing.assert_array_equal(signal, original)


@pytest.mark.parametrize("seasonal", [False, True])
def test_constant_or_only_seasonal_signal_has_no_trend(seasonal):
    values = np.full(120, 8.)
    if seasonal:
        values += 5 * np.sin(2 * np.pi * np.arange(120) / 12)
    result = analyze_trend(values, pd.date_range("2000", periods=120, freq="MS"))
    assert not result["is_significant"]
    assert result["mk_p"] == 1
    assert result["p_value"] == 1
    assert result["slope"] == 0
    assert result["sens_slope"] == 0
    assert result["confidence_interval_95"] == (0, 0)


def test_noise_is_retained_and_confidence_interval_is_nonzero():
    rng = np.random.default_rng(42)
    t = np.arange(240)
    values = 0.1 * t + np.sin(t * 2 * np.pi / 12) + rng.normal(0, 0.3, 240)
    result = analyze_trend(values, pd.date_range("2000", periods=240, freq="MS"))
    assert np.std(np.diff(result["deseasonalized"])) > 0.2
    lo, hi = result["confidence_interval_95"]
    assert lo < 0.1 < hi


@pytest.mark.parametrize("kind", ["short", "nan", "inf", "2d", "mismatch", "gap", "duplicate", "reverse", "numeric", "nat", "alpha"])
def test_invalid_input_rejected(kind):
    values = np.arange(36, dtype=float)
    dates = pd.date_range("2000", periods=36, freq="MS").to_numpy(copy=True)
    kwargs = {}
    if kind == "short": values, dates = values[:23], dates[:23]
    if kind == "nan": values[3] = np.nan
    if kind == "inf": values[3] = np.inf
    if kind == "2d": values = values[:, None]
    if kind == "mismatch": dates = dates[:-1]
    if kind == "gap": dates[10:] += np.timedelta64(62, "D")
    if kind == "duplicate": dates[3] = dates[2]
    if kind == "reverse": dates = dates[::-1]
    if kind == "numeric": dates = np.arange(36)
    if kind == "nat": dates[0] = np.datetime64("NaT")
    if kind == "alpha": kwargs["alpha"] = 1
    with pytest.raises(ValueError):
        analyze_trend(values, dates, **kwargs)


def test_mk_p_on_raw_series_is_not_fooled_by_white_noise():
    """White noise has no trend, so the scout-stage Mann-Kendall p-value should
    exceed 0.05 in most seeds. The test runs on the raw monthly series; a
    smoothed/deseasonalized input can manufacture spurious significance from
    serial dependence."""
    rng = np.random.default_rng(7)
    seeds = [int(value) for value in rng.integers(0, 10_000, 30)]
    p_values = []
    for seed in seeds:
        series = np.random.default_rng(seed).standard_normal(120)
        dates = pd.date_range("2000", periods=120, freq="MS")
        result = analyze_trend(series, dates)
        p_values.append(result["mk_p"])
    assert sum(p > 0.05 for p in p_values) >= 25
