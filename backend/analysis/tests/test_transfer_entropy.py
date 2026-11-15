import numpy as np
import pytest
from scipy.special import digamma

from backend.agents.preprocessing import preprocess_for_causal
from backend.analysis import transfer_entropy as module


def anomalies(coupled):
    rng = np.random.default_rng(0)
    data = np.zeros((700, 2))
    noise = rng.normal(size=data.shape)
    for t in range(2, len(data)):
        data[t] = 0.4 * data[t - 1] + noise[t]
        if coupled:
            data[t, 1] += 0.9 * data[t - 2, 0]
    data = data[100:]
    months = np.arange(len(data)) % 12 + 1
    return [preprocess_for_causal(column, months) for column in data.T]


def test_coupled_anomalies_exceed_surrogates():
    source, target = anomalies(coupled=True)
    result = module.transfer_entropy_significance(source, target, lag=2)
    assert result["te"] > 0
    assert result["te_p"] < 0.05


def test_independent_anomalies_are_not_significant():
    source, target = anomalies(coupled=False)
    result = module.transfer_entropy_significance(source, target, lag=2)
    assert result["te_p"] > 0.05


@pytest.mark.parametrize("lag,history_len,k", [(1, 2, 5), (3, 3, 2)])
def test_batched_estimator_matches_strict_brute_force(lag, history_len, k):
    source, target = np.random.default_rng(42).normal(size=(2, 40))
    # Independent, small O(N²) oracle checks embedding, max-norm, self removal,
    # and strict boundaries at the joint k-neighbor radius.
    rows = []
    for t in range(max(history_len, lag + history_len - 1), len(source)):
        rows.append([target[t]] + [target[t - j] for j in range(1, history_len + 1)]
                    + [source[t - lag - j] for j in range(history_len)])
    joint = np.array(rows)
    distances = np.max(np.abs(joint[:, None] - joint[None, :]), axis=2)
    np.fill_diagonal(distances, np.inf)
    eps = np.sort(distances, axis=1)[:, k - 1]

    def counts(points):
        distances = np.max(np.abs(points[:, None] - points[None, :]), axis=2)
        np.fill_diagonal(distances, np.inf)
        return (distances < eps[:, None]).sum(axis=1)

    n_yp = counts(joint[:, 1:1 + history_len])
    n_yfyp = counts(joint[:, :1 + history_len])
    n_xpyp = counts(joint[:, 1:])
    expected = digamma(k) + np.mean(digamma(n_yp + 1) - digamma(n_yfyp + 1) - digamma(n_xpyp + 1))
    assert module.compute_transfer_entropy(source, target, lag, history_len, k) == pytest.approx(expected)


def test_significance_uses_200_circular_shifts_and_counts_ties(monkeypatch):
    source, target = np.arange(40.), np.arange(40.) ** 2
    calls = []

    def estimate(x, y, lag, history_len, k):
        np.testing.assert_array_equal(y, target)
        assert (lag, history_len, k) == (3, 2, 5)
        calls.append(x.copy())
        return 1. if len(calls) <= 101 else 0.

    monkeypatch.setattr(module, "compute_transfer_entropy", estimate)
    result = module.transfer_entropy_significance(source, target, lag=3)
    assert len(calls) == 201
    np.testing.assert_array_equal(calls[0], source)
    offsets = np.random.default_rng(0).integers(1, len(source), size=200)
    for shifted, offset in zip(calls[1:], offsets):
        np.testing.assert_array_equal(shifted, np.roll(source, offset))
    assert result == {"te": 1., "te_p": 101 / 201}


def test_cancellation_stops_between_surrogates(monkeypatch):
    import asyncio
    from threading import Event
    from backend.agents.cancellation import check_cancelled, scan_cancel_event

    flag = Event()
    calls = []

    def estimate(*args):
        calls.append(1)
        if len(calls) == 2:  # Disconnect while the first surrogate is computing.
            flag.set()
        return 0.

    monkeypatch.setattr(module, "compute_transfer_entropy", estimate)
    token = scan_cancel_event.set(flag)
    try:
        with pytest.raises(asyncio.CancelledError):
            module.transfer_entropy_significance(np.arange(40.), np.arange(40.),
                                                  check_cancelled=check_cancelled)
    finally:
        scan_cancel_event.reset(token)
    assert len(calls) == 2


@pytest.mark.parametrize("kwargs", [{"lag": 0}, {"history_len": 0}, {"k": 0}, {"k": 1.5}, {"k": 40}])
def test_invalid_embedding_parameters(kwargs):
    with pytest.raises(ValueError):
        module.compute_transfer_entropy(np.arange(40.), np.arange(40.), **kwargs)


@pytest.mark.parametrize("source,target", [([1., np.nan], [1., 2.]),
    ([1., np.inf], [1., 2.]), ([1., 2.], [1.]), ([[1., 2.]], [[1., 2.]]),
    (np.ones(40), np.ones(40))])
def test_invalid_or_degenerate_series(source, target):
    with pytest.raises(ValueError):
        module.compute_transfer_entropy(source, target)
