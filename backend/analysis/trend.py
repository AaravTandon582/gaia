"""Seasonally adjusted trend statistics for regularly sampled monthly data."""

import numpy as np
import pandas as pd
import pymannkendall as mk
from scipy import stats
from statsmodels.tsa.seasonal import seasonal_decompose


def analyze_trend(timeseries, dates, alpha=0.05):
    """Return additive deseasonalization, OLS and original Mann-Kendall statistics.

    At least 24 finite observations and one date per consecutive calendar month
    are required. Missing values/months are rejected rather than interpolated.
    Both OLS and Sen slopes are in input units per month. ``is_significant``
    uses the two-sided Mann-Kendall test at ``alpha``; its original formulation
    assumes independent observations (seasonal adjustment does not remove all
    serial dependence). The 95% confidence interval is for the OLS slope.
    """
    if np.iscomplexobj(timeseries):
        raise ValueError("timeseries must be real-valued")
    values = np.asarray(timeseries, dtype=float)
    if values.ndim != 1 or len(values) < 24 or not np.isfinite(values).all():
        raise ValueError("timeseries must contain at least 24 finite monthly values")
    if not np.isscalar(alpha) or not np.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    date_values = np.asarray(dates)
    if date_values.ndim != 1 or len(date_values) != len(values):
        raise ValueError("dates must be one-dimensional and match timeseries length")
    if np.issubdtype(date_values.dtype, np.number):
        raise ValueError("dates must be calendar dates, not numeric offsets")
    try:
        index = pd.DatetimeIndex(pd.to_datetime(date_values, format="mixed", errors="raise"))
    except (ValueError, TypeError) as error:
        raise ValueError("dates must contain valid calendar dates") from error
    if index.hasnans:
        raise ValueError("dates must not contain missing dates")
    months = index.year.to_numpy() * 12 + index.month.to_numpy()
    if not np.all(np.diff(months) == 1):
        raise ValueError("dates must be ordered, unique, consecutive calendar months")

    decomposition = seasonal_decompose(
        values, model="additive", period=12, extrapolate_trend=12
    )
    deseasonalized = values - decomposition.seasonal
    # Avoid roundoff masquerading as a trend in exactly constant/seasonal data.
    tolerance = 32 * np.finfo(float).eps * max(1., np.max(np.abs(values)))
    if np.ptp(deseasonalized) <= tolerance:
        deseasonalized = np.full_like(values, deseasonalized.mean())
        slope, intercept, p_value, r_squared, stderr = 0., float(deseasonalized[0]), 1., 0., 0.
    else:
        regression = stats.linregress(np.arange(len(values), dtype=float), deseasonalized)
        slope, intercept = float(regression.slope), float(regression.intercept)
        p_value, r_squared, stderr = float(regression.pvalue), float(regression.rvalue**2), float(regression.stderr)
    mk_result = mk.original_test(deseasonalized, alpha=alpha)
    mann_kendall = {
        "trend": str(mk_result.trend), "h": bool(mk_result.h),
        "p": float(mk_result.p), "z": float(mk_result.z),
        "tau": float(mk_result.Tau), "s": float(mk_result.s),
        "var_s": float(mk_result.var_s), "slope": float(mk_result.slope),
        "intercept": float(mk_result.intercept),
    }
    margin = float(stats.t.ppf(0.975, len(values) - 2) * stderr)
    if mk_result.h:
        verdict = (
            f"A statistically significant {mk_result.trend} trend was detected "
            f"after seasonal adjustment (Mann-Kendall p={mk_result.p:.3g}, "
            f"alpha={alpha:g}); Sen's slope is {mk_result.slope:.6g} units per month."
        )
    else:
        verdict = (
            f"No statistically significant monotonic trend was detected after "
            f"seasonal adjustment (Mann-Kendall p={mk_result.p:.3g}, alpha={alpha:g})."
        )
    return {
        "deseasonalized": deseasonalized,
        "slope": slope, "intercept": intercept, "p_value": p_value,
        "r_squared": r_squared, "slope_stderr": stderr,
        "confidence_interval_95": (slope - margin, slope + margin),
        "slope_unit": "input units per month",
        "mann_kendall": mann_kendall, "mk_trend": mann_kendall["trend"],
        "mk_p": mann_kendall["p"], "sens_slope": mann_kendall["slope"],
        "is_significant": mann_kendall["h"], "verdict": verdict,
    }
