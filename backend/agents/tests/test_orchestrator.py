import asyncio
import json
from threading import Event

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.agents import orchestrator as module
from backend.agents.orchestrator import OrchestratorAgent
from backend.main import create_app


def discovery(variable="temperature", values=None, dates=None, region="arctic"):
    if values is None:
        values = np.random.default_rng(42).normal(size=60)
    if dates is None:
        dates = pd.date_range("2000", periods=len(values), freq="MS")
    return dict(region=region, variable=variable, timeseries=pd.Series(values, index=dates))


def test_scouts_run_concurrently_and_stream_completion():
    async def exercise():
        both_started = asyncio.Event()
        started = []
        events = []

        class Scout:
            async def scan(self, regions, date_range):
                assert regions == ["arctic"]
                assert date_range == ("2000", "2025")
                started.append(self)
                if len(started) == 2:
                    both_started.set()
                await both_started.wait()
                return [discovery()]

        async def status(event):
            events.append(event)

        agent = OrchestratorAgent([Scout(), Scout()], status_callback=status)
        results = await asyncio.wait_for(agent.run_scan(["arctic"], ("2000", "2025")), 2)
        assert len(results) == 2
        assert events[0]["status"] == "scan_started"
        assert events[-1]["status"] == "scan_completed"
        assert sum(event["status"] == "completed" for event in events) == 2

    asyncio.run(exercise())


def test_failure_cancels_remaining_scouts():
    async def exercise():
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class Slow:
            async def scan(self, *_):
                started.set()
                try:
                    await asyncio.Future()
                finally:
                    cancelled.set()

        class Broken:
            async def scan(self, *_):
                await started.wait()
                raise RuntimeError("broken scout")

        with pytest.raises(RuntimeError, match="broken scout"):
            await OrchestratorAgent([Slow(), Broken()]).run_scan([], ())
        assert cancelled.is_set()

    asyncio.run(exercise())


def test_alignment_deduplication_loader_and_link_direction(monkeypatch):
    captured = {}

    class PCMCI:
        def __init__(self, dataframe, cond_ind_test, verbosity):
            captured["data"] = dataframe.values[0]
            captured["test"] = cond_ind_test

        def run_pcmci(self, **kwargs):
            assert kwargs == dict(tau_max=6, pc_alpha=0.05, alpha_level=0.05)
            graph = np.full((2, 2, 7), "", dtype="<U3")
            graph[0, 1, 3] = "-->"
            graph[0, 1, 0] = "o-o"
            p = np.ones((2, 2, 7))
            val = np.zeros_like(p)
            p[0, 1, 3], val[0, 1, 3] = 0.01, -0.7
            return dict(graph=graph, p_matrix=p, val_matrix=val)

    monkeypatch.setattr(module, "PCMCI", PCMCI)
    first = discovery(values=np.arange(60))
    second = discovery("rain", np.arange(60) * 2,
                       pd.date_range("2000-03-31", periods=60, freq="ME"))
    loader_calls = []

    def loader(item):
        loader_calls.append(item)
        return second["timeseries"]

    links = OrchestratorAgent(series_loader=loader).run_causal_discovery([
        first, first, dict(region="arctic", variable="rain"), {"flagged": False},
    ])
    assert len(loader_calls) == 1
    np.testing.assert_array_equal(captured["data"], np.column_stack([np.arange(2, 60), np.arange(58) * 2]))
    assert isinstance(captured["test"], module.ParCorr)
    assert links == [dict(cause="arctic:temperature", effect="arctic:rain", lag=3,
                          strength=-0.7, p_value=0.01)]
    json.dumps(links, allow_nan=False)


def test_real_pcmci_recovers_known_lag():
    rng = np.random.default_rng(17)
    cause = rng.normal(size=600)
    effect = rng.normal(scale=0.2, size=600)
    effect[3:] += 0.9 * cause[:-3]
    links = OrchestratorAgent().run_causal_discovery([
        discovery("cause", cause), discovery("effect", effect),
    ])
    link = next(link for link in links if link["cause"] == "arctic:cause"
                and link["effect"] == "arctic:effect" and link["lag"] == 3)
    assert link["strength"] > 0.8
    assert link["p_value"] < 0.05


@pytest.mark.parametrize("kind, message", [
    ("constant", "constant"), ("short", "15 overlapping"),
    ("gap", "Missing observations"), ("nan", "finite"),
    ("duplicate", "unique"), ("disjoint", "15 overlapping"),
    ("conflict", "Conflicting"),
])
def test_invalid_series_fail_clearly(kind, message):
    item = discovery()
    series = item["timeseries"]
    items = [item]
    if kind == "constant":
        item["timeseries"] = series * 0
    elif kind == "short":
        item["timeseries"] = series.iloc[:14]
    elif kind == "gap":
        item["timeseries"] = series.drop(series.index[20])
    elif kind == "nan":
        series.iloc[20] = np.nan
    elif kind == "duplicate":
        item["timeseries"] = pd.concat([series, series.iloc[:1]])
    elif kind == "disjoint":
        items.append(discovery("rain", dates=pd.date_range("2010", periods=60, freq="MS")))
    elif kind == "conflict":
        items.append(discovery(values=np.arange(60)))
    with pytest.raises(ValueError, match=message):
        OrchestratorAgent().run_causal_discovery(items)


def test_empty_and_unflagged_discoveries():
    agent = OrchestratorAgent()
    assert agent.run_causal_discovery([]) == []
    assert agent.run_causal_discovery([{"flagged": False}]) == []


def test_dates_values_format_and_region_identity():
    item = discovery()
    dates = item.pop("timeseries").index.strftime("%Y-%m-%d").tolist()
    item.update(dates=dates, values=np.arange(60).tolist())
    agent = OrchestratorAgent()
    assert len(agent._monthly_series(item)) == 60
    # Same variable in different regions remains two distinct graph nodes.
    other = {**item, "region": "amazon", "values": np.sin(np.arange(60)).tolist()}
    links = agent.run_causal_discovery([item, other])
    assert all(link["cause"] in {"arctic:temperature", "amazon:temperature"} for link in links)


REQUEST = {"regions": ["arctic"], "date_range": ["2000-01-01", "2025-12-31"]}


def test_websocket_streams_before_scan_finishes():
    release = Event()

    class Scout:
        async def scan(self, *_):
            while not release.is_set():
                await asyncio.sleep(0.01)
            return []

    with TestClient(create_app([Scout()])) as client:
        with client.websocket_connect("/ws/scan") as ws:
            ws.send_json(REQUEST)
            assert ws.receive_json()["status"] == "scan_started"
            assert ws.receive_json()["status"] == "started"
            release.set()
            assert ws.receive_json()["status"] == "completed"
            assert ws.receive_json()["status"] == "scan_completed"
            assert ws.receive_json()["status"] == "causal_started"
            result = ws.receive_json()
            assert result["type"] == "complete"
            assert result["discovery_count"] == 0
            assert result["links"] == result["discoveries"] == []


@pytest.mark.parametrize("payload", [
    {"regions": [], "date_range": ["2000-01-01", "2025-12-31"]},
    {**REQUEST, "date_range": ["2025-12-31", "2000-01-01"]},
    {**REQUEST, "date_range": ["invalid", "2025-12-31"]},
    {**REQUEST, "regions": [" "]},
])
def test_websocket_rejects_invalid_requests(payload):
    with TestClient(create_app()) as client:
        with client.websocket_connect("/ws/scan") as ws:
            ws.send_json(payload)
            assert ws.receive_json()["type"] == "error"


def test_websocket_reports_missing_scouts():
    with TestClient(create_app()) as client:
        with client.websocket_connect("/ws/scan") as ws:
            ws.send_json(REQUEST)
            assert ws.receive_json() == {"type": "error", "message": "No ScoutAgents configured"}


@pytest.mark.parametrize("failure", [None, "scout", "causal"])
def test_websocket_pipeline_results_and_errors(failure):
    class Scout:
        async def scan(self, *_):
            if failure == "scout":
                raise RuntimeError("scout failure")
            if failure == "causal":
                return [discovery(values=np.zeros(60))]
            rng = np.random.default_rng(17)
            cause = rng.normal(size=300)
            effect = rng.normal(scale=0.2, size=300)
            effect[2:] += cause[:-2]
            return [discovery("cause", cause), discovery("effect", effect)]

    with TestClient(create_app([Scout()])) as client:
        with client.websocket_connect("/ws/scan") as ws:
            ws.send_json(REQUEST)
            events = []
            while True:
                event = ws.receive_json()
                events.append(event)
                if event["type"] in {"complete", "error"}:
                    break
            if failure:
                assert events[-1]["type"] == "error"
                assert not any(event["type"] == "complete" for event in events)
            else:
                assert events[-1]["discovery_count"] == 2
                assert any(link["cause"] == "arctic:cause" and
                           link["effect"] == "arctic:effect" and link["lag"] == 2
                           for link in events[-1]["links"])


def test_websocket_disconnect_cancels_scout():
    cancelled = Event()
    started = Event()

    class Scout:
        async def scan(self, *_):
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

    with TestClient(create_app([Scout()])) as client:
        with client.websocket_connect("/ws/scan") as ws:
            ws.send_json(REQUEST)
            assert started.wait(timeout=2)
            ws.close()
            assert cancelled.wait(timeout=2)
