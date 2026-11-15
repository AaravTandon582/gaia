"""KSG conditional mutual information and circular-shift significance."""

import numpy as np
from scipy.spatial import cKDTree
from scipy.special import digamma


def compute_transfer_entropy(source, target, lag=1, history_len=2, k=5):
    """Estimate I(y_t; (x_{t-lag}, ..., x_{t-lag-h+1}) | (y_{t-1}, ..., y_{t-h})).

    Histories contain ``history_len`` consecutive observations, newest first.
    Inputs are aligned, finite, preprocessed anomalies. Output is in nats;
    finite-sample estimates can be negative and are not clipped. Continuous
    data with positive k-neighbor distances are required (no tie jitter).
    """
    for name, value in (("lag", lag), ("history_len", history_len), ("k", k)):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if np.iscomplexobj(source) or np.iscomplexobj(target):
        raise ValueError("source and target must be real-valued")
    source, target = np.asarray(source, dtype=float), np.asarray(target, dtype=float)
    if source.ndim != 1 or target.shape != source.shape:
        raise ValueError("source and target must be one-dimensional with equal lengths")
    if not np.isfinite(source).all() or not np.isfinite(target).all():
        raise ValueError("source and target must contain finite observations")
    start = max(history_len, lag + history_len - 1)
    if len(source) - start <= k:
        raise ValueError("Not enough embedded observations for k neighbors")
    time = np.arange(start, len(source))
    offsets = np.arange(history_len)
    y_future = target[time, None]
    y_past = target[time[:, None] - 1 - offsets]
    x_past = source[time[:, None] - lag - offsets]
    joint = np.column_stack([y_future, y_past, x_past])
    # k+1 includes the point itself. The list form requests only that rank.
    eps = cKDTree(joint).query(joint, k=[k + 1], p=np.inf)[0][:, 0]
    if np.any(eps <= 0):
        raise ValueError("KSG requires positive neighbor distances; repeated embeddings found")
    # query_ball_point uses <= radius; nextafter enforces strict < eps.
    radius = np.nextafter(eps, -np.inf)

    def count(points):
        return cKDTree(points).query_ball_point(points, radius, p=np.inf, return_length=True) - 1

    n_yp = count(y_past)
    n_yfyp = count(np.column_stack([y_future, y_past]))
    n_xpyp = count(np.column_stack([x_past, y_past]))
    return float(digamma(k) + np.mean(
        digamma(n_yp + 1) - digamma(n_yfyp + 1) - digamma(n_xpyp + 1)
    ))


def transfer_entropy_significance(source, target, lag=1, history_len=2, k=5,
                                  *, seed=0, check_cancelled=None):
    """Return te and te_p using 200 nonzero source circular shifts.

    Draw offsets uniformly from 1..T-1 with replacement; preserve source
    ordering/autocorrelation on the circle and leave the target fixed. Seed 0
    makes API results reproducible. The plus-one test includes ties.
    """
    if check_cancelled is not None:
        check_cancelled()
    observed = compute_transfer_entropy(source, target, lag, history_len, k)
    offsets = np.random.default_rng(seed).integers(1, len(source), size=200)
    exceedances = 0
    for offset in offsets:
        if check_cancelled is not None:
            check_cancelled()
        surrogate = compute_transfer_entropy(np.roll(source, offset), target, lag, history_len, k)
        exceedances += surrogate >= observed
    if check_cancelled is not None:
        check_cancelled()
    return {"te": observed, "te_p": float((1 + exceedances) / 201)}
