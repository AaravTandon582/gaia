"""Fixed-seed scientific checks; thresholds are independent of regional results."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from backend.agents.orchestrator import OrchestratorAgent
from backend.agents.preprocessing import preprocess_for_causal


def var_data(seed=0):
    rng = np.random.default_rng(seed)
    data = np.zeros((600, 3))  # Discard 200 observations for burn-in.
    noise = rng.normal(size=data.shape)
    for t in range(2, len(data)):
        data[t] = 0.4 * data[t - 1] + noise[t]
        data[t, 1] += 0.6 * data[t - 2, 0]
        data[t, 2] -= 0.5 * data[t - 1, 1]
    return data[200:]


def run_matrix(matrix, *, preprocess=True):
    dates = pd.date_range("2000", periods=len(matrix), freq="MS")
    discoveries = [dict(region="test", variable=chr(97 + i),
                        timeseries=pd.Series(matrix[:, i], index=dates))
                   for i in range(matrix.shape[1])]
    agent = OrchestratorAgent()
    if preprocess:
        return agent.run_causal_discovery(discoveries)
    with patch("backend.agents.orchestrator.preprocess_for_causal", side_effect=lambda x, months: x):
        return agent.run_causal_discovery(discoveries)


def test_known_var_links():
    links = run_matrix(var_data())
    found = {(item["cause"], item["effect"], item["lag"]): item for item in links}
    assert found["test:a", "test:b", 2]["strength"] > 0
    assert found["test:b", "test:c", 1]["strength"] < 0
    assert len(links) <= 4
    assert all(item["corrected_p"] < 0.05 for item in links)


def test_pc_alpha_is_configurable(monkeypatch):
    from backend.agents.orchestrator import PCMCI
    original = PCMCI.run_pcmci
    observed = []

    def run(self, **kwargs):
        observed.append(kwargs["pc_alpha"])
        return original(self, **kwargs)

    monkeypatch.setattr(PCMCI, "run_pcmci", run)
    matrix = var_data()
    dates = pd.date_range("2000", periods=len(matrix), freq="MS")
    agent = OrchestratorAgent(pc_alpha=0.1)
    agent.run_causal_discovery([dict(region="test", variable="a",
                                     timeseries=pd.Series(matrix[:, 0], index=dates))])
    assert observed == [0.1]


def test_shifted_var_null():
    matrix = var_data()
    months = pd.date_range("2000", periods=len(matrix), freq="MS").month
    matrix = np.column_stack([preprocess_for_causal(x, months) for x in matrix.T])
    counts = []
    for seed in range(10):
        offsets = np.random.default_rng(seed).integers(50, 351, size=3)
        shifted = np.column_stack([np.roll(x, offset) for x, offset in zip(matrix.T, offsets)])
        counts.append(len(run_matrix(shifted, preprocess=False)))
    assert np.median(counts) <= 1, counts


def test_shared_trend_and_season_do_not_create_links():
    rng = np.random.default_rng(0)
    t = np.arange(400)
    common = 0.03 * t + 3 * np.sin(2 * np.pi * t / 12)
    matrix = common[:, None] + rng.normal(size=(400, 2))
    assert len(run_matrix(matrix, preprocess=False)) > 0
    assert len(run_matrix(matrix)) == 0


def test_preprocessing_standardizes_without_mutation_and_preserves_nan_positions():
    rng = np.random.default_rng(0)
    months = np.tile(np.arange(1, 13), 30)
    values = rng.normal(size=len(months)) + months + np.arange(len(months)) * 0.02
    values[17] = np.nan
    original = values.copy()
    result = preprocess_for_causal(values, months)
    np.testing.assert_array_equal(values, original)
    assert np.isnan(result[17])
    assert np.isfinite(result[np.arange(len(result)) != 17]).all()
    assert abs(np.nanmean(result)) < 1e-12
    assert np.nanstd(result) == pytest.approx(1.)
    valid = np.isfinite(result)
    assert abs(np.polyfit(np.arange(len(result))[valid], result[valid], 1)[0]) < 1e-12


@pytest.mark.parametrize("values", [np.ones(36), np.full(36, np.nan), np.full(36, np.inf)])
def test_degenerate_preprocessing_fails_clearly(values):
    with pytest.raises(ValueError):
        preprocess_for_causal(values, np.tile(np.arange(1, 13), 3))
