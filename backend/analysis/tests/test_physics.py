import json

import numpy as np
import pytest

from backend.analysis.physics import validate_water_balance


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
