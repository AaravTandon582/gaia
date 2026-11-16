import json

import numpy as np
import pytest

from backend.analysis.physics import region_water_balances, validate_water_balance


def test_synthetic_balanced_case():
    result = validate_water_balance([10., 20., 5.], [4., 8., 2.], [3., 7., 4.], [3., 5., -1.])
    assert result["mean_residual"] == 0.
    assert result["mean_relative_error"] == 0.
    assert "averages to zero" in result["interpretation"]
    assert isinstance(result["mean_residual"], float)
    json.dumps(result, allow_nan=False)


def test_synthetic_unbalanced_case():
    result = validate_water_balance([10., 20.], [4., 8.], [2., 4.], [1., 2.])
    assert result["mean_residual"] == 4.5
    assert result["mean_relative_error"] == pytest.approx(0.3)
    assert "4.5" in result["interpretation"]
    assert "Precipitation exceeds" in result["interpretation"]
    assert "30.00%" in result["interpretation"]
    assert not {"passed", "valid", "threshold"}.intersection(result)


def test_negative_residual_and_scalar_inputs():
    result = validate_water_balance(10., 7., 4., 1.)
    assert result["mean_residual"] == -2.
    assert result["mean_relative_error"] == pytest.approx(0.2)
    assert "exceeds precipitation" in result["interpretation"]


def test_relative_error_does_not_cancel_opposite_residuals():
    result = validate_water_balance([10., 20.], [8., 22.], [0., 0.], [0., 0.])
    assert result["mean_residual"] == 0.
    assert result["mean_relative_error"] == pytest.approx(0.15)


@pytest.mark.parametrize("missing", range(4))
@pytest.mark.parametrize("value", [None, [], [np.nan], [np.inf]])
def test_missing_inputs_do_not_compute_a_balance(missing, value):
    inputs = [[10.], [4.], [3.], [3.]]
    inputs[missing] = value
    assert validate_water_balance(*inputs) == "inputs unavailable"


def test_dry_intervals_are_excluded_only_from_relative_error():
    result = validate_water_balance([0., 10.], [2., 5.], [0., 0.], [0., 0.])
    assert result["mean_residual"] == 1.5
    assert result["mean_relative_error"] == 0.5
    assert "excludes 1 zero-precipitation" in result["interpretation"]


def test_all_zero_precipitation_still_returns_numeric_residual():
    result = validate_water_balance([0., 0.], [1., 3.], [0., 0.], [0., 0.])
    assert result["mean_residual"] == -2.
    assert result["mean_relative_error"] is None
    assert "undefined" in result["interpretation"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("precip", [[1., 2.], [[1.]], [1j]])
def test_invalid_shapes_or_complex_values_are_rejected(precip):
    with pytest.raises(ValueError):
        validate_water_balance(precip, [1.], [1.], [1.])


def discovery(region, variable, values, dates):
    return dict(region=region, variable=variable, dates=dates, values=values,
                unit="mm/month", source_bounds=[-75, -15, -45, 5])


def test_region_water_balances_all_unavailable_with_current_cache():
    from backend.data.loader import WATER_BALANCE_TERMS
    results = region_water_balances([])
    for region in WATER_BALANCE_TERMS:
        assert region in results
        assert results[region]["status"] == "inputs unavailable"
        assert "missing" in results[region]


def test_region_water_balances_reports_missing_terms():
    dates = [f"2000-{m:02d}-01" for m in range(1, 13)]
    inputs = [discovery("amazon", "Rainf_f_tavg", [1.0] * 12, dates),
              discovery("amazon", "Evap_tavg", [0.5] * 12, dates)]
    results = region_water_balances(inputs)
    assert results["amazon"]["status"] == "inputs unavailable"
    assert "Q" in results["amazon"]["missing"]
    assert "dS" in results["amazon"]["missing"]


def test_region_water_balances_computes_when_complete():
    dates = [f"2000-{m:02d}-01" for m in range(1, 13)]
    p = [10., 20., 30., 40., 50., 60., 70., 80., 90., 100., 110., 120.]
    e = [4., 8., 12., 16., 20., 24., 28., 32., 36., 40., 44., 48.]
    q = [3., 7., 11., 15., 19., 23., 27., 31., 35., 39., 43., 47.]
    ds = [3., 5., 7., 9., 11., 13., 15., 17., 19., 21., 23., 25.]
    inputs = [discovery("amazon", "Rainf_f_tavg", p, dates),
              discovery("amazon", "Evap_tavg", e, dates),
              discovery("amazon", "Qs_acc", q, dates),
              discovery("amazon", "dS_total", ds, dates)]
    # Temporarily point the term mapping at these variables.
    import backend.data.loader as loader_module
    original = loader_module.WATER_BALANCE_TERMS["amazon"]
    loader_module.WATER_BALANCE_TERMS["amazon"] = dict(P="Rainf_f_tavg", ET="Evap_tavg",
                                                       Q="Qs_acc", dS="dS_total")
    try:
        result = region_water_balances(inputs)
    finally:
        loader_module.WATER_BALANCE_TERMS["amazon"] = original
    assert result["amazon"]["status"] == "complete"
    assert result["amazon"]["n_months"] == 12
    np.testing.assert_allclose(result["amazon"]["mean_residual"], 0.0)
    assert result["amazon"]["mean_relative_error"] == 0.0


def test_region_water_balances_aligns_different_date_orders():
    dates = [f"2000-{m:02d}-01" for m in range(1, 7)]
    p = [10., 20., 30., 40., 50., 60.]
    e = [4., 8., 12., 16., 20., 24.]
    q = [3., 7., 11., 15., 19., 23.]
    ds = [3., 5., 7., 9., 11., 13.]
    # One series is in reverse order; alignment must still match by date.
    inputs = [discovery("amazon", "Rainf_f_tavg", p, dates),
              discovery("amazon", "Evap_tavg", e, dates),
              discovery("amazon", "Qs_acc", list(reversed(q)), list(reversed(dates))),
              discovery("amazon", "dS_total", ds, dates)]
    import backend.data.loader as loader_module
    original = loader_module.WATER_BALANCE_TERMS["amazon"]
    loader_module.WATER_BALANCE_TERMS["amazon"] = dict(P="Rainf_f_tavg", ET="Evap_tavg",
                                                       Q="Qs_acc", dS="dS_total")
    try:
        result = region_water_balances(inputs)
    finally:
        loader_module.WATER_BALANCE_TERMS["amazon"] = original
    assert result["amazon"]["status"] == "complete"
    assert result["amazon"]["n_months"] == 6
    np.testing.assert_allclose(result["amazon"]["mean_residual"], 0.0)


def test_region_water_balances_current_cache_state():
    """Amazon now has Q (Qs_acc), but dS is still missing for all regions."""
    from backend.data.loader import available_series, load_series
    results = {}
    for region in ["amazon", "sahel", "mediterranean", "arctic", "california"]:
        discoveries = []
        for variable in available_series(region):
            s, meta = load_series(region, variable, ("2000-01-01", "2025-12-31"))
            discoveries.append(dict(
                region=region, variable=variable,
                dates=s.index.strftime("%Y-%m-%d").tolist(),
                values=s.tolist(), label=variable))
        results[region] = region_water_balances(discoveries)[region]

    # Amazon has P, ET, Q (Qs_acc), but still missing dS.
    assert results["amazon"]["status"] == "inputs unavailable"
    assert results["amazon"]["missing"] == ["dS"], results["amazon"]
    # Sahel/Med: P and ET exist, Q and dS missing.
    for region in ["sahel", "mediterranean"]:
        assert results[region]["status"] == "inputs unavailable"
        assert "Q" in results[region]["missing"]
        assert "dS" in results[region]["missing"], results[region]
    # Arctic: only T2M and SNOMAS available.
    assert results["arctic"]["status"] == "inputs unavailable"
    assert set(results["arctic"]["missing"]) == {"P", "ET", "Q", "dS"}, results["arctic"]
    # California: only soil moisture.
    assert results["california"]["status"] == "inputs unavailable"
    assert set(results["california"]["missing"]) == {"P", "ET", "Q", "dS"}, results["california"]


def test_region_water_balances_qs_acc_treated_as_partial_runoff():
    """Qs_acc is storm surface runoff only; the balance reports it as partial."""
    dates = [f"2000-{m:02d}-01" for m in range(1, 13)]
    p = [10., 20., 30., 40., 50., 60., 70., 80., 90., 100., 110., 120.]
    e = [4., 8., 12., 16., 20., 24., 28., 32., 36., 40., 44., 48.]
    q = [0.08, 0.09, 0.11, 0.10, 0.08, 0.06, 0.04, 0.03, 0.02, 0.02, 0.03, 0.03]
    discoveries = [
        discovery("amazon", "Rainf_f_tavg", p, dates),
        discovery("amazon", "Evap_tavg", e, dates),
        discovery("amazon", "Qs_acc", q, dates),
    ]
    result = region_water_balances(discoveries)
    assert result["amazon"]["status"] == "inputs unavailable"
    assert "dS" in result["amazon"]["missing"]
    assert "Q" not in result["amazon"]["missing"], "Qs_acc should be recognized as Q"
    dates = [f"2000-{m:02d}-01" for m in range(1, 7)]
    p = [10., 20., 30., 40., 50., 60.]
    e = [4., 8., 12., 16., 20., 24.]
    q = [3., 7., 11., 15., 19., 23.]
    ds = [3., 5., 7., 9., 11., 13.]
    # One series is in reverse order; alignment must still match by date.
    inputs = [discovery("amazon", "Rainf_f_tavg", p, dates),
              discovery("amazon", "Evap_tavg", e, dates),
              discovery("amazon", "Qs_acc", list(reversed(q)), list(reversed(dates))),
              discovery("amazon", "dS_total", ds, dates)]
    import backend.data.loader as loader_module
    original = loader_module.WATER_BALANCE_TERMS["amazon"]
    loader_module.WATER_BALANCE_TERMS["amazon"] = dict(P="Rainf_f_tavg", ET="Evap_tavg",
                                                       Q="Qs_acc", dS="dS_total")
    try:
        result = region_water_balances(inputs)
    finally:
        loader_module.WATER_BALANCE_TERMS["amazon"] = original
    assert result["amazon"]["status"] == "complete"
    assert result["amazon"]["n_months"] == 6
    np.testing.assert_allclose(result["amazon"]["mean_residual"], 0.0)


@pytest.mark.parametrize("fault", ["nan", "gap", "short", "units", "bounds", "duplicates"])
def test_regional_balance_rejects_incompatible_inputs(monkeypatch, fault):
    from backend.analysis import physics
    monkeypatch.setitem(physics.WATER_BALANCE_TERMS, "test", dict(P="p", ET="e", Q="q", dS="s"))
    dates = ["2000-01-01", "2000-02-01", "2000-03-01"]
    inputs = [discovery("test", name, [value] * 3, dates.copy())
              for name, value in (("p", 10.), ("e", 4.), ("q", 3.), ("s", 3.))]
    if fault == "nan": inputs[-1]["values"][1] = np.nan
    if fault == "gap":
        inputs[-1]["dates"].pop(1)
        inputs[-1]["values"].pop(1)
    if fault == "short": inputs[-1]["values"].pop()
    if fault == "units": inputs[-1]["unit"] = "kg/m²/s"
    if fault == "bounds": inputs[-1]["source_bounds"] = [0, 0, 1, 1]
    if fault == "duplicates": inputs[-1]["dates"][1] = dates[0]
    result = region_water_balances(inputs)["test"]
    assert result["status"] == "inputs unavailable"
    assert "mean_residual" not in result
