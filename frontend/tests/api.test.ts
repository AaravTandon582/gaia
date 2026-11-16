import { expect, test } from "vitest";
import { parseScanEvent, scanUrl } from "../lib/api";
import { regionFromClick } from "../lib/region";

test("websocket URL follows API host and protocol", () => {
  expect(scanUrl()).toBe("ws://127.0.0.1:8000/ws/scan");
});
test("malformed causal payloads fail instead of rendering broken graphs", () => {
  expect(() => parseScanEvent('{"type":"complete","links":[{"lag":99}],"discoveries":[]}')).toThrow();
  expect(() => parseScanEvent("not json")).toThrow();
});
test("wrapped map longitudes select the same region", () => {
  expect(regionFromClick(-5, 300).lon).toBe(-60);
  expect(regionFromClick(90, -420).lat).toBe(85);
});
test("parseScanEvent accepts complete result with LSTM anomalies", () => {
  const payload = {
    type: "complete",
    links: [],
    discoveries: [],
    discovery_count: 0,
    method: "PCMCI",
    preprocessing: "Monthly climatology removed",
    anomalies: {
      status: "complete",
      scope: "all_model_features",
      retrospective: true,
      feature_names: ["T2M", "Rainf_f_tavg"],
      dates: ["2000-01-01", "2000-02-01"],
      reconstruction_error: [0.5, 1.2],
      is_anomaly: [false, true],
      window_count: [1, 1],
      threshold: 0.8,
      training_error_mean: 0.3,
      training_error_std: 0.1,
      sequence_length: 12,
      interpretation: "Reconstruction diagnostic",
    },
  };
  const event = parseScanEvent(JSON.stringify(payload));
  expect(event.type).toBe("complete");
  if (event.type === "complete" && event.anomalies?.status === "complete") {
    expect(event.anomalies.is_anomaly[1]).toBe(true);
    expect(event.anomalies.threshold).toBe(0.8);
  } else {
    throw new Error("Expected complete anomalies");
  }
});
test("parseScanEvent accepts complete result with unavailable anomalies", () => {
  const payload = {
    type: "complete",
    links: [],
    discoveries: [],
    discovery_count: 0,
    method: "PCMCI",
    preprocessing: "Monthly climatology removed",
    anomalies: { status: "unavailable", reason: "LSTM checkpoint missing" },
  };
  const event = parseScanEvent(JSON.stringify(payload));
  expect(event.type).toBe("complete");
  if (event.type === "complete" && event.anomalies?.status === "unavailable") {
    expect(event.anomalies.reason).toBe("LSTM checkpoint missing");
  } else {
    throw new Error("Expected unavailable anomalies");
  }
});
test("parseScanEvent accepts complete result without anomalies field", () => {
  const payload = {
    type: "complete",
    links: [],
    discoveries: [],
    discovery_count: 0,
    method: "PCMCI",
    preprocessing: "Monthly climatology removed",
  };
  const event = parseScanEvent(JSON.stringify(payload));
  expect(event.type).toBe("complete");
  if (event.type === "complete") {
    expect(event.anomalies).toBeUndefined();
  }
});
