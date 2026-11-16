"""Run the real API pipeline five times per demo; write observed results."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient

from backend.main import app


def run(repetitions=5):
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "transport": "FastAPI TestClient WebSocket (not browser visual QA)",
              "date_range": ["2000-01-01", "2025-12-31"], "scenarios": {}}
    with TestClient(app) as client:
        for region, expected in (("amazon", 2), ("sahel", 1)):
            trials, reference = [], None
            for _ in range(repetitions):
                started = perf_counter()
                with client.websocket_connect("/ws/scan") as ws:
                    ws.send_json({"regions": [region], "date_range": report["date_range"]})
                    while True:
                        result = ws.receive_json()
                        if result["type"] == "error":
                            raise RuntimeError(result["message"])
                        if result["type"] == "complete":
                            break
                assert len(result["links"]) == expected, result["links"]
                assert result["anomalies"]["status"] == "complete", result["anomalies"]
                if reference is None:
                    reference = result
                else:
                    assert result == reference, "Repeated scan changed scientific results"
                trials.append({"seconds": round(perf_counter() - started, 3),
                               "links": len(result["links"]),
                               "anomaly_months": sum(result["anomalies"]["is_anomaly"])})
            report["scenarios"][region] = dict(
                trials=trials, n_samples=reference["n_samples"],
                n_variables=reference["n_variables"], links=reference["links"],
                anomalies=reference["anomalies"],
            )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("reports/demo-rehearsal.json"))
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    for region, result in report["scenarios"].items():
        print(f"{region}: {len(result['trials'])} identical scans, {len(result['links'])} links; "
              f"{sum(result['anomalies']['is_anomaly'])} combined-model anomaly months")
