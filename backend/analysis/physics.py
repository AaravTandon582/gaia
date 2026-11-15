"""Descriptive water-balance diagnostics for aligned physical observations."""

import numpy as np


def validate_water_balance(precip, et, runoff, delta_storage):
    """Return mean residual, mean absolute relative error, and interpretation.

    Supply equally shaped scalars or 1-D arrays covering the same region and
    intervals, in compatible units: all interval totals or all rates. Storage
    must be a change over the interval (positive for accumulation), not a stock.
    Use physical observations, not standardized/detrended causal anomalies.

    Relative error is mean(abs(P - ET - Q - dS) / abs(P)) for nonzero P,
    expressed as a fraction. It is None if every P is zero. Missing inputs
    (None, empty arrays, or nonfinite observations) return "inputs unavailable";
    no terms are inferred as zero and no incomplete intervals are dropped.
    """
    inputs = (precip, et, runoff, delta_storage)
    if any(value is None for value in inputs):
        return "inputs unavailable"
    if any(np.iscomplexobj(value) for value in inputs):
        raise ValueError("Water-balance inputs must be real-valued")
    arrays = [np.asarray(value, dtype=float) for value in inputs]
    if any(value.size == 0 for value in arrays):
        return "inputs unavailable"
    if any(value.ndim > 1 or value.shape != arrays[0].shape for value in arrays):
        raise ValueError("Water-balance inputs must have matching scalar or 1-D shapes")
    if any(not np.isfinite(value).all() for value in arrays):
        return "inputs unavailable"

    p, e, q, ds = arrays
    residual = p - e - q - ds
    mean_residual = float(np.mean(residual))
    nonzero = p != 0
    relative_error = float(np.mean(np.abs(residual[nonzero]) / np.abs(p[nonzero]))) if nonzero.any() else None
    direction = (
        "Precipitation exceeds ET plus runoff plus storage change on average."
        if mean_residual > 0 else
        "ET plus runoff plus storage change exceeds precipitation on average."
        if mean_residual < 0 else
        "The signed residual averages to zero; individual interval residuals may still differ."
    )
    interpretation = f"Mean P - ET - Q - dS is {mean_residual:.6g} in the input units. {direction}"
    if relative_error is None:
        interpretation += " Relative error is undefined because precipitation is zero in every interval."
    else:
        interpretation += f" Mean absolute relative error is {relative_error:.2%} of precipitation."
        excluded = int(np.count_nonzero(~nonzero))
        if excluded:
            interpretation += f" Relative error excludes {excluded} zero-precipitation interval(s); the mean residual includes them."
    interpretation += " This describes closure without a pass/fail threshold; differences in product, coverage, and timing can contribute to the residual."
    return {"mean_residual": mean_residual, "mean_relative_error": relative_error,
            "interpretation": interpretation}
