"""Descriptive water-balance diagnostics for aligned physical observations."""

import numpy as np
import pandas as pd

from ..data.loader import WATER_BALANCE_TERMS


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


def region_water_balances(discoveries):
    """Compute P - ET - Q - dS per region when all four terms are available.

    ``discoveries`` is the scout discovery list (each entry carries ``region``,
    ``variable``, ``dates`` and ``values``). Results are keyed by region id.
    A region returns ``status: "complete"`` with the numeric balance only when
    every term is present; otherwise it returns ``status: "inputs unavailable"``
    with the list of missing terms. No term is inferred as zero and no
    incomplete interval is dropped.
    """
    by_region = {}
    for discovery in discoveries:
        by_region.setdefault(discovery["region"], {})[discovery["variable"]] = discovery

    results = {}
    for region, terms in WATER_BALANCE_TERMS.items():
        variables = by_region.get(region, {})
        missing = [term for term, var in terms.items()
                   if var is None or var not in variables]
        if missing:
            results[region] = {"status": "inputs unavailable", "missing": missing}
            continue

        inputs = [variables[terms[term]] for term in ("P", "ET", "Q", "dS")]
        # Require explicitly normalized interval totals. Rates, accumulations,
        # and storage stocks cannot be mixed by merely aligning timestamps.
        if any(item.get("unit") != "mm/month" for item in inputs):
            results[region] = {"status": "inputs unavailable",
                               "missing": ["all terms normalized to mm/month"]}
            continue
        bounds = [item.get("source_bounds") for item in inputs]
        if any(bound is None or len(bound) != 4 for bound in bounds) or any(
                not np.array_equal(bound, bounds[0]) for bound in bounds[1:]):
            results[region] = {"status": "inputs unavailable",
                               "missing": ["matching spatial bounds"]}
            continue
        try:
            indices = [pd.DatetimeIndex(item["dates"]) for item in inputs]
            shared = indices[0].sort_values()
            months = shared.year.to_numpy() * 12 + shared.month.to_numpy()
            compatible = (len(shared) >= 2 and all(
                not index.hasnans and index.is_unique and index.sort_values().equals(shared)
                for index in indices) and np.all(np.diff(months) == 1))
            if not compatible:
                raise ValueError("Dates must cover the same consecutive months")
            arrays = [_align(item["dates"], item["values"], shared) for item in inputs]
            result = validate_water_balance(*arrays)
        except (ValueError, TypeError, IndexError):
            result = "inputs unavailable"
        if isinstance(result, str):
            results[region] = {"status": "inputs unavailable",
                               "missing": ["finite values on identical consecutive monthly intervals"]}
        else:
            results[region] = {"status": "complete", "n_months": int(len(shared)),
                               "unit": "mm/month", **result}

    return results


def _align(dates, values, shared):
    """Return values reordered to match ``shared`` dates."""
    date_index = pd.DatetimeIndex(dates)
    if len(values) != len(date_index):
        raise ValueError("Each date must have one value")
    positions = date_index.get_indexer(shared)
    if (positions < 0).any():
        raise ValueError("Some shared dates are missing from the series")
    return np.asarray(values, dtype=float)[positions]
