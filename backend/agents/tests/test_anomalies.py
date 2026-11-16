import asyncio
import json
from threading import Event
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.agents.anomalies import AnomalyAgent
from backend.agents.cancellation import check_cancelled, scan_cancel_event
from backend.main import create_app


def test_real_model_scores_all_features_and_requested_months():
    pytest.importorskip("torch")
    agent = AnomalyAgent()
    result = agent.run(["2000-01-01", "2025-12-31"])
    assert result["status"] == "complete", result
    assert result["scope"] == "all_model_features"
    assert len(result["feature_names"]) == 12
    assert len(result["dates"]) == len(result["reconstruction_error"]) == 312
    assert len(result["is_anomaly"]) == len(result["window_count"]) == 312
    assert result["threshold"] == pytest.approx(
        result["training_error_mean"] + 2 * result["training_error_std"])
    np.testing.assert_array_equal(result["is_anomaly"],
                                  np.array(result["reconstruction_error"]) > result["threshold"])
    assert np.isfinite(result["reconstruction_error"]).all()
    pipeline = agent._pipeline
    short = agent.run(["2022-01-15", "2025-12-31"])
    assert agent._pipeline is pipeline
    assert short["dates"][0] == "2022-01-01"
    assert len(short["dates"]) == 48
    assert short["threshold"] == result["threshold"]
    json.dumps(result, allow_nan=False)


def test_missing_feature_does_not_fabricate_anomaly_scores():
    agent = AnomalyAgent(series_loader=Mock(side_effect=ValueError("missing feature")))
    agent._pipeline = Mock(feature_names=["amazon_Evap_tavg"])
    result = agent.run(["2000", "2025"])
    assert result["status"] == "unavailable"
    assert "missing feature" in result["reason"]
    assert "reconstruction_error" not in result
    agent._pipeline.predict.assert_not_called()


def test_unavailable_model_does_not_fail_scan(tmp_path):
    pytest.importorskip("torch")
    result = AnomalyAgent(tmp_path / "missing.pt").run(["2000", "2025"])
    assert result["status"] == "unavailable"


def test_missing_months_are_not_filled_or_silently_dropped():
    pytest.importorskip("torch")
    from backend.ml.inference import AutoencoderInference
    pipeline = AutoencoderInference()
    dates = pd.date_range("2020", periods=24, freq="MS").delete(4)
    agent = AnomalyAgent(series_loader=lambda *_: (pd.Series(1., index=dates), {}))
    agent._pipeline = pipeline
    result = agent.run(["2020-01-01", "2021-12-31"])
    assert result["status"] == "unavailable"
    assert "finite observations" in result["reason"]


def test_cancelled_request_does_not_enter_inference():
    agent = AnomalyAgent()
    flag = Event()
    token = scan_cancel_event.set(flag)
    try:
        flag.set()
        with pytest.raises(asyncio.CancelledError):
            agent.run(["2000", "2025"])
    finally:
        scan_cancel_event.reset(token)
    assert agent._pipeline is None


class EmptyScout:
    async def scan(self, *_):
        return []


def test_api_returns_anomalies_additively():
    payload = dict(status="complete", scope="all_model_features", dates=["2025-01-01"],
                   reconstruction_error=[3.], is_anomaly=[True], threshold=2.)
    agent = Mock(run=Mock(return_value=payload))
    with TestClient(create_app([EmptyScout()], anomaly_agent=agent)) as client:
        assert "T2M" in client.get("/variables").json()
        with client.websocket_connect("/ws/scan") as ws:
            ws.send_json({"regions": ["amazon"], "date_range": ["2025-01-01", "2025-12-31"]})
            while True:
                result = ws.receive_json()
                assert result["type"] != "error"
                if result["type"] == "complete":
                    break
    assert result["anomalies"] == payload
    assert result["links"] == result["discoveries"] == []
    agent.run.assert_called_once()


def test_disconnect_cancels_anomaly_worker():
    started, stopped = Event(), Event()

    class SlowAgent:
        def run(self, dates):
            flag = scan_cancel_event.get()
            started.set()
            try:
                assert flag.wait(3)
                check_cancelled()
                raise AssertionError("continued after disconnect")
            finally:
                stopped.set()

    with TestClient(create_app([EmptyScout()], anomaly_agent=SlowAgent())) as client:
        with client.websocket_connect("/ws/scan") as ws:
            ws.send_json({"regions": ["amazon"], "date_range": ["2000-01-01", "2025-12-31"]})
            assert started.wait(2)
            assert client.get("/health").status_code == 200
            ws.close()
            assert stopped.wait(2)


def test_forward_checks_cancellation_between_batches():
    torch = pytest.importorskip("torch")
    from backend.ml.train_autoencoder import score_all
    calls = []

    class Model:
        def eval(self):
            pass

        def anomaly_score(self, batch):
            calls.append(batch)
            return torch.zeros(batch.shape[:2])

    def cancel_after_one():
        if calls:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        score_all(Model(), np.zeros((4, 3, 2), dtype=np.float32),
                  batch_size=1, check_cancelled=cancel_after_one)
    assert len(calls) == 1
