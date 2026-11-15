"""Real cached-data scans through the same API used by the dashboard."""

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.agents.scout import default_scouts
from backend.data import loader
from backend.main import app, create_app


@pytest.mark.parametrize("region", ["amazon", "arctic", "mediterranean", "sahel", "california"])
def test_real_region_scan(region):
    with TestClient(app) as client:
        with client.websocket_connect("/ws/scan", headers={"origin": "http://127.0.0.1:3000"}) as ws:
            ws.send_json({"regions": [region], "date_range": ["2000-01-01", "2025-12-31"]})
            events = []
            while True:
                event = ws.receive_json()
                events.append(event)
                assert event["type"] != "error", event
                if event["type"] == "complete":
                    break
    result = events[-1]
    assert len([event for event in events if event.get("status") == "completed"]) == 4
    assert result["discoveries"]
    assert len(result["links"]) == {"amazon": 2, "arctic": 0, "mediterranean": 2,
                                    "sahel": 1, "california": 0}[region]
    assert result["n_samples"] == 312
    assert result["n_variables"] == {"amazon": 3, "arctic": 2, "mediterranean": 4,
                                    "sahel": 2, "california": 1}[region]
    assert result["tau_max"] == 6
    assert result["fdr_applied"] is True
    ids = {f"{item['region']}:{item['variable']}" for item in result["discoveries"]}
    for item in result["discoveries"]:
        assert item["region"] == region
        assert len(item["dates"]) == len(item["values"]) == 312
        assert item["source_file"]
        assert "timeseries" not in item
    for link in result["links"]:
        assert link["cause"] != link["effect"]
        assert link["cause"] in ids and link["effect"] in ids
        assert 1 <= link["lag"] <= 6
        assert link["p_value"] <= 0.05
        assert link["p_value"] <= link["corrected_p"] < 0.05
    json.dumps(result, allow_nan=False)


def test_http_cors_and_catalog():
    with TestClient(app) as client:
        response = client.get("/regions", headers={"origin": "http://localhost:3000"})
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert len(response.json()["regions"]) == 5
        assert client.get("/health").json() == {"status": "ok", "scouts": 4}
        assert "access-control-allow-origin" not in client.get(
            "/regions", headers={"origin": "https://untrusted.example"}).headers
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/scan", headers={"origin": "https://untrusted.example"}):
                pass


@pytest.mark.parametrize("region, dates, message", [
    ("unknown", ["2000-01-01", "2025-12-31"], "Unsupported region"),
    ("amazon", ["2025-01-01", "2025-12-31"], "24 cached months"),
])
def test_bad_selection_returns_error_then_retry_succeeds(region, dates, message):
    with TestClient(create_app(default_scouts())) as client:
        with client.websocket_connect("/ws/scan") as ws:
            ws.send_json({"regions": [region], "date_range": dates})
            while True:
                event = ws.receive_json()
                if event["type"] == "error":
                    assert message in event["message"]
                    break
        with client.websocket_connect("/ws/scan") as ws:
            ws.send_json({"regions": ["amazon"], "date_range": ["2010-01-01", "2020-12-31"]})
            while True:
                event = ws.receive_json()
                assert event["type"] != "error", event
                if event["type"] == "complete":
                    assert all(len(item["values"]) == 132 for item in event["discoveries"])
                    break


def test_loader_honors_fill_values_and_aggregates_submonthly(tmp_path):
    path = tmp_path / "example.csv"
    path.write_text("Fill Value:, -9999\nData Bounding Box:,\"-75,-15,-45,5\"\ntime, mean_test\n"
                    "2000-01-01,1\n2000-01-02,3\n2000-02-01,-9999\n2000-03-01,5\n")
    series, metadata = loader._read_export(str(path), path.stat().st_mtime_ns)
    assert series.iloc[0] == 2
    assert np.isnan(series.iloc[1])
    assert metadata["dataset"] == "test"
    assert metadata["source_bounds"] == [-75, -15, -45, 5]
