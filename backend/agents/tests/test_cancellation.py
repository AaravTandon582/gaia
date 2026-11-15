import asyncio
import logging
from threading import Event
from unittest.mock import Mock

from fastapi.testclient import TestClient

from backend.agents.cancellation import scan_cancel_event
from backend.agents.scout import ScoutAgent
from backend.main import create_app


REQUEST = {"regions": ["amazon"], "date_range": ["2000-01-01", "2025-12-31"]}


def test_normal_scan_logs_result_and_releases_cancel_flag(caplog):
    flags = []

    class Scout:
        async def scan(self, *_):
            def worker():
                flags.append(scan_cancel_event.get())
                assert not flags[0].is_set()
                return []
            return await asyncio.to_thread(worker)

    caplog.set_level(logging.INFO, logger="backend.main")
    with TestClient(create_app([Scout()])) as client:
        with client.websocket_connect("/ws/scan") as ws:
            ws.send_json(REQUEST)
            while True:
                message = ws.receive_json()
                assert message["type"] != "error"
                if message["type"] == "complete":
                    assert message["links"] == []
                    break
            assert flags[0].wait(2)
    assert "scan start region=amazon" in caplog.text
    assert "scan done region=amazon links=0 in " in caplog.text
    assert "scan cancelled" not in caplog.text
    assert "connection closed" in caplog.text


def test_disconnect_stops_real_scout_worker_before_analysis(monkeypatch, caplog):
    """Cancelling the async wrapper must also stop its running worker thread."""
    started, stopped = Event(), Event()
    flags, variables = [], []
    analysis = Mock(side_effect=AssertionError("analysis continued after cancellation"))

    def blocking_load(region, variable, dates):
        variables.append(variable)
        flag = scan_cancel_event.get()
        flags.append(flag)
        started.set()
        assert flag.wait(3), "disconnect never signalled the worker"
        return None, {}  # The cancellation checkpoint must run before using these.

    class ObservedScout(ScoutAgent):
        def _scan(self, *args):
            try:
                return super()._scan(*args)
            finally:
                stopped.set()

    monkeypatch.setattr("backend.agents.scout.load_series", blocking_load)
    monkeypatch.setattr("backend.agents.scout.analyze_trend", analysis)
    caplog.set_level(logging.INFO, logger="backend.main")
    with TestClient(create_app([ObservedScout("hydro")])) as client:
        with client.websocket_connect("/ws/scan") as ws:
            ws.send_json(REQUEST)
            assert started.wait(2)
            # HTTP still responds while the worker waits: the event loop is free.
            assert client.get("/health").status_code == 200
            ws.close()
            assert flags[0].wait(2)
            assert stopped.wait(2)
    assert len(variables) == 1
    analysis.assert_not_called()
    assert "client disconnected" in caplog.text
    assert "scan cancelled region=amazon" in caplog.text
    assert "connection closed" in caplog.text
    assert "scan done" not in caplog.text


def test_cancellation_is_isolated_between_connections():
    flags = {}
    started = {name: Event() for name in ("amazon", "sahel")}
    stopped = {name: Event() for name in started}

    class Scout:
        async def scan(self, regions, _):
            region = regions[0]
            def worker():
                flag = scan_cancel_event.get()
                flags[region] = flag
                started[region].set()
                try:
                    assert flag.wait(3)
                    return []
                finally:
                    stopped[region].set()
            return await asyncio.to_thread(worker)

    with TestClient(create_app([Scout()])) as client:
        with client.websocket_connect("/ws/scan") as first:
            first.send_json(REQUEST)
            assert started["amazon"].wait(2)
            with client.websocket_connect("/ws/scan") as second:
                second.send_json({**REQUEST, "regions": ["sahel"]})
                assert started["sahel"].wait(2)
                first.close()
                assert stopped["amazon"].wait(2)
                assert not flags["sahel"].is_set()
                second.close()
                assert stopped["sahel"].wait(2)


def test_disconnect_during_alignment_skips_pcmci(monkeypatch):
    from backend.agents.orchestrator import OrchestratorAgent
    from backend.agents.tests.test_orchestrator import discovery

    started, stopped = Event(), Event()
    pcmci = Mock()
    original = OrchestratorAgent._monthly_series

    def blocked_alignment(self, item):
        flag = scan_cancel_event.get()
        started.set()
        assert flag.wait(3)
        try:
            return original(self, item)
        finally:
            stopped.set()

    class Scout:
        async def scan(self, *_):
            return [discovery()]

    monkeypatch.setattr(OrchestratorAgent, "_monthly_series", blocked_alignment)
    monkeypatch.setattr("backend.agents.orchestrator.PCMCI", pcmci)
    with TestClient(create_app([Scout()])) as client:
        with client.websocket_connect("/ws/scan") as ws:
            ws.send_json(REQUEST)
            assert started.wait(2)
            ws.close()
            assert stopped.wait(2)
    pcmci.return_value.run_pcmci.assert_not_called()


def test_disconnect_during_pcmci_discards_worker_result(monkeypatch, caplog):
    from backend.agents.orchestrator import PCMCI
    from backend.agents.tests.test_orchestrator import discovery

    started, stopped, release = Event(), Event(), Event()
    flags = []

    def blocked_pcmci(self, **kwargs):
        flags.append(scan_cancel_event.get())
        started.set()
        try:
            assert release.wait(3)
            return {}  # Cancellation must be checked before reading this result.
        finally:
            stopped.set()

    class Scout:
        async def scan(self, *_):
            return [discovery()]

    monkeypatch.setattr(PCMCI, "run_pcmci", blocked_pcmci)
    caplog.set_level(logging.INFO, logger="backend.main")
    with TestClient(create_app([Scout()])) as client:
        try:
            with client.websocket_connect("/ws/scan") as ws:
                ws.send_json(REQUEST)
                assert started.wait(2)
                assert client.get("/health").status_code == 200
                ws.close()
                assert flags[0].wait(2)
            # The connection can finish while an in-flight PCMCI call remains blocked.
            assert not stopped.is_set()
        finally:
            release.set()
            assert stopped.wait(2)
    assert "client disconnected" in caplog.text
    assert "scan cancelled region=amazon" in caplog.text
    assert "scan done" not in caplog.text
    assert "Scan failed" not in caplog.text
