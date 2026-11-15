"""Causal-only preprocessing; scout trend tests retain their original inputs."""

import numpy as np


def preprocess_for_causal(x, months):
    """Subtract monthly climatology, detrend, then standardize finite values.

    ``months`` contains calendar month numbers (1..12), one per consecutive
    monthly observation. NaNs stay at their original positions: callers must
    reject incomplete matrices, not drop rows and change the meaning of lags.
    """
    if np.iscomplexobj(x):
        raise ValueError("Causal series must be real-valued")
    values = np.asarray(x, dtype=float)
    months = np.asarray(months)
    if values.ndim != 1 or months.shape != values.shape or not np.isin(months, np.arange(1, 13)).all():
        raise ValueError("Expected one calendar month (1..12) per observation")
    valid = np.isfinite(values)
    if np.isinf(values).any() or valid.sum() < 3:
        raise ValueError("Causal series needs at least three finite observations and no infinities")
    adjusted = values.copy()
    for month in np.unique(months[valid]):
        selected = valid & (months == month)
        adjusted[selected] -= values[selected].mean()
    time = np.arange(len(values), dtype=float)[valid]
    design = np.column_stack([time - time.mean(), np.ones(len(time))])
    residual = adjusted[valid] - design @ np.linalg.lstsq(design, adjusted[valid], rcond=None)[0]
    scale = residual.std()
    tolerance = 32 * np.finfo(float).eps * max(1., np.max(np.abs(values[valid])))
    if scale <= tolerance:
        raise ValueError("Causal series is constant after preprocessing")
    adjusted[valid] = (residual - residual.mean()) / scale
    return adjusted
