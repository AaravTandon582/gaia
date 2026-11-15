from itertools import product

import numpy as np
import pytest
from scipy.stats import t as student_t

from backend.analysis.changepoint import BOCPD


def test_detects_known_mean_shifts_and_returns_normalized_posterior():
    rng = np.random.default_rng(3)
    signal = np.repeat([0., 5., -3.], 80) + rng.normal(0, 0.3, 240)
    original = signal.copy()
    changes, posterior = BOCPD(hazard_lambda=100).detect(signal)
    assert len(changes) == 2
    np.testing.assert_allclose(changes, [80, 160], atol=2)
    assert posterior.shape == (241, 241)
    np.testing.assert_allclose(posterior.sum(axis=1), 1, atol=1e-12)
    assert np.all(posterior >= 0)
    assert np.all(np.triu(posterior, 1) == 0)
    np.testing.assert_array_equal(signal, original)


def test_stationary_signal_does_not_invent_changes():
    changes, posterior = BOCPD().detect(np.zeros(200))
    assert changes == []
    assert posterior[-1].argmax() == 200


def test_posterior_matches_exhaustive_small_sequence():
    # Independent reference: enumerate every possible reset-after-observation
    # history, updating scalar sufficient statistics for each complete path.
    values = [0.2, -0.1, 2.3, 2.1]
    hazard = 0.1
    expected = np.zeros(len(values) + 1)
    for resets in product([False, True], repeat=len(values)):
        mu, kappa, alpha, beta, r, probability = 0., 1., 1., 1., 0, 1.
        for x, reset in zip(values, resets):
            probability *= student_t.pdf(x, 2 * alpha, loc=mu,
                                        scale=np.sqrt(beta * (kappa + 1) / (alpha * kappa)))
            probability *= hazard if reset else 1 - hazard
            if reset:
                mu, kappa, alpha, beta, r = 0., 1., 1., 1., 0
            else:
                beta += kappa * (x - mu)**2 / (2 * (kappa + 1))
                mu = (kappa * mu + x) / (kappa + 1)
                kappa += 1
                alpha += 0.5
                r += 1
        expected[r] += probability
    expected /= expected.sum()
    _, posterior = BOCPD(hazard_lambda=10).detect(values)
    np.testing.assert_allclose(posterior[-1], expected, rtol=1e-12)
    # Under constant hazard, r=0 is not a data-dependent alarm probability.
    np.testing.assert_allclose(posterior[1:, 0], hazard)


def test_repeated_batch_calls_reset_and_match_streaming():
    signal = np.r_[np.zeros(30), np.ones(30) * 5]
    model = BOCPD()
    first, posterior = model.detect(signal)
    second, again = model.detect(signal)
    assert first == second
    np.testing.assert_array_equal(posterior, again)
    streaming = BOCPD()
    for index, value in enumerate(signal, start=1):
        streaming.update(value)
        np.testing.assert_allclose(streaming.R, posterior[index, :index + 1])
    assert streaming.changepoints == first


def test_large_offsets_remain_finite_in_log_space():
    _, posterior = BOCPD().detect(1e6 + np.random.default_rng(1).normal(size=100))
    assert np.isfinite(posterior).all()
    np.testing.assert_allclose(posterior.sum(axis=1), 1)


def test_empty_input_is_prior_only():
    changes, posterior = BOCPD().detect([])
    assert changes == []
    np.testing.assert_array_equal(posterior, [[1.]])


@pytest.mark.parametrize("kwargs", [dict(hazard_lambda=1), dict(kappa0=0), dict(alpha0=-1),
                                    dict(beta0=0), dict(mu0=np.nan), dict(threshold=0),
                                    dict(min_run_length=0), dict(min_run_length=1.5)])
def test_invalid_parameters(kwargs):
    with pytest.raises(ValueError): BOCPD(**kwargs)


@pytest.mark.parametrize("signal", [[0, np.nan], [np.inf], [[1, 2]], [1j]])
def test_invalid_series(signal):
    with pytest.raises(ValueError): BOCPD().detect(signal)
