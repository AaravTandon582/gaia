import { StrictMode } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

vi.mock("next/dynamic", () => ({ default: () => () => null }));
import { Dashboard } from "../components/Dashboard";
import { LSTMAnomalyBands } from "../components/LSTMAnomalyBands";
import { TimeSeriesChart } from "../components/TimeSeriesChart";
import { render as rtlRender } from "@testing-library/react";

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();
  send = vi.fn();
  constructor() { FakeSocket.instances.push(this); }
}

beforeEach(() => {
  FakeSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ regions: [
    { id: "amazon", name: "Amazon Basin", lat: -5, lon: -60, bounds: { south: -15, north: 5, west: -75, east: -45 }, variables: [] },
    { id: "sahel", name: "Sahel", lat: 15, lon: 5, bounds: { south: 10, north: 20, west: -20, east: 40 }, variables: [] },
  ] }) })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

test("second scan closes first socket and ignores its queued callbacks", async () => {
  render(<StrictMode><Dashboard /></StrictMode>);
  await screen.findByRole("button", { name: "Amazon Basin" });
  expect(FakeSocket.instances).toHaveLength(0); // Strict Mode effect replay opens none.
  fireEvent.click(screen.getByRole("button", { name: "Amazon Basin" }));
  const first = FakeSocket.instances[0];
  act(() => first.onopen?.());
  expect(JSON.parse(first.send.mock.calls[0][0]).regions).toEqual(["amazon"]);
  const staleMessage = first.onmessage!, staleClose = first.onclose!, staleError = first.onerror!;
  fireEvent.click(screen.getByRole("button", { name: "Sahel" }));
  const second = FakeSocket.instances[1];
  expect(first.close).toHaveBeenCalledTimes(1);
  expect(first.onmessage).toBeNull();
  act(() => {
    staleMessage({ data: JSON.stringify({ type: "complete", links: [], discoveries: [], discovery_count: 0 }) });
    staleClose();
    staleError();
    second.onopen?.();
  });
  expect(JSON.parse(second.send.mock.calls[0][0]).regions).toEqual(["sahel"]);
  expect(second.close).not.toHaveBeenCalled();
  expect(screen.queryByText(/Scan complete/)).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("unmount closes the active socket and detaches callbacks in Strict Mode", async () => {
  const { unmount } = render(<StrictMode><Dashboard /></StrictMode>);
  fireEvent.click(await screen.findByRole("button", { name: "Amazon Basin" }));
  const socket = FakeSocket.instances[0];
  const lateOpen = socket.onopen!;
  unmount();
  expect(socket.close).toHaveBeenCalledTimes(1);
  expect(socket.onopen).toBeNull();
  expect(socket.onmessage).toBeNull();
  act(() => lateOpen());
  expect(socket.send).not.toHaveBeenCalled();
});

test("pagehide closes the socket without unmounting and permits a scan after restore", async () => {
  const { unmount } = render(<StrictMode><Dashboard /></StrictMode>);
  fireEvent.click(await screen.findByRole("button", { name: "Amazon Basin" }));
  const first = FakeSocket.instances[0];
  act(() => first.onopen?.());
  const lateMessage = first.onmessage!;
  act(() => window.dispatchEvent(new Event("pagehide")));
  expect(first.close).toHaveBeenCalledTimes(1);
  expect(first.onmessage).toBeNull();
  expect(screen.getByText("Scan cancelled")).toBeTruthy();
  act(() => lateMessage({ data: JSON.stringify({ type: "complete", links: [], discoveries: [], discovery_count: 0 }) }));
  expect(screen.queryByText(/Scan complete/)).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Run scan" }));
  const second = FakeSocket.instances[1];
  expect(second.close).not.toHaveBeenCalled();
  unmount();
  act(() => window.dispatchEvent(new Event("pagehide")));
  expect(first.close).toHaveBeenCalledTimes(1);
  expect(second.close).toHaveBeenCalledTimes(1);
});

test("LSTMAnomalyBands shows unavailable state with reason", () => {
  const { container } = rtlRender(
    <LSTMAnomalyBands
      chartDates={["2000-01-01", "2000-02-01"]}
      anomalies={{ status: "unavailable", reason: "LSTM checkpoint missing" }}
    />,
  );
  expect(container.textContent).toContain("LSTM anomaly bands unavailable");
  expect(container.textContent).toContain("LSTM checkpoint missing");
});

test("LSTMAnomalyBands shows no bands when none detected", () => {
  const { container } = rtlRender(
    <LSTMAnomalyBands
      chartDates={["2000-01-01", "2000-02-01"]}
      anomalies={{
        status: "complete",
        scope: "all_model_features",
        retrospective: true as const,
        feature_names: ["T2M"],
        dates: ["2000-01-01", "2000-02-01"],
        reconstruction_error: [0.1, 0.2],
        is_anomaly: [false, false],
        window_count: [1, 1],
        threshold: 0.8,
        training_error_mean: 0.3,
        training_error_std: 0.1,
        sequence_length: 12,
        interpretation: "Reconstruction diagnostic",
      }}
    />,
  );
  expect(container.textContent).toContain("No combined-model anomaly bands detected this period.");
});

test("LSTMAnomalyBands aligns bands by calendar date not array position", () => {
  // Chart dates span a different range than anomaly dates; only the overlapping
  // calendar date should produce a band.
  const { container } = rtlRender(
    <LSTMAnomalyBands
      chartDates={["2000-01-01", "2000-02-01", "2000-03-01"]}
      anomalies={{
        status: "complete",
        scope: "all_model_features",
        retrospective: true as const,
        feature_names: ["T2M"],
        dates: ["2000-02-01"], // only Feb is anomalous
        reconstruction_error: [1.5],
        is_anomaly: [true],
        window_count: [1],
        threshold: 0.8,
        training_error_mean: 0.3,
        training_error_std: 0.1,
        sequence_length: 12,
        interpretation: "Reconstruction diagnostic",
      }}
    />,
  );
  const rects = container.querySelectorAll("rect");
  expect(rects).toHaveLength(1);
  expect(rects[0].getAttribute("data-anomaly-date")).toBe("2000-02-01");
  expect(Number(rects[0].getAttribute("x"))).toBe(81);
  expect(Number(rects[0].getAttribute("width"))).toBe(138);
  fireEvent.mouseEnter(rects[0]);
  expect(screen.getByRole("tooltip").textContent).toContain("2000-02 · MSE 1.50");
  expect(screen.getByRole("tooltip").textContent).toContain("retrospective");
});

test("TimeSeriesChart renders with anomalies prop", () => {
  const discoveries = [
    {
      region: "amazon",
      region_name: "Amazon Basin",
      variable: "T2M",
      label: "Temperature",
      domain: "atmosphere" as const,
      lat: -5,
      lon: -60,
      unit: "K",
      flagged: true,
      reason: "Significant trend",
      dates: ["2000-01-01", "2000-02-01"],
      values: [280, 281],
      source_file: "amazon_T2M.csv",
      dataset: "ERA5",
      source_bounds: [-75, -15, -45, 5],
      trend_p: 0.01,
      peak_anomaly_z: 2.5,
      sen_slope: 0.5,
    },
  ];
  const anomalies = {
    status: "complete" as const,
    scope: "all_model_features" as const,
    retrospective: true as const,
    feature_names: ["T2M"],
    dates: ["2000-01-01", "2000-02-01"],
    reconstruction_error: [0.5, 1.2],
    is_anomaly: [false, true],
    window_count: [1, 1],
    threshold: 0.8,
    training_error_mean: 0.3,
    training_error_std: 0.1,
    sequence_length: 12,
    interpretation: "Reconstruction diagnostic",
  };
  const { container } = rtlRender(
    <TimeSeriesChart discoveries={discoveries} anomalies={anomalies} />,
  );
  expect(container.textContent).toContain("Temperature");
  expect(container.textContent).toContain("K");
  const svg = screen.getByRole("img", { name: "Temperature monthly time series" });
  expect(svg.querySelector("polyline")).not.toBeNull();
  expect(svg.querySelectorAll("rect[data-anomaly-date]")).toHaveLength(1);
  expect(container.querySelectorAll("svg")).toHaveLength(1);
});

test("Dashboard renders discovery summary table", async () => {
  render(<Dashboard />);
  await screen.findByRole("button", { name: "Amazon Basin" });
  fireEvent.click(screen.getByRole("button", { name: "Amazon Basin" }));
  const first = FakeSocket.instances[0];
  act(() => first.onopen?.());
  act(() => {
    first.onmessage!({
      data: JSON.stringify({
        type: "complete",
        links: [],
        discoveries: [
          {
            region: "amazon",
            region_name: "Amazon Basin",
            variable: "T2M",
            label: "Temperature",
            domain: "atmosphere",
            lat: -5,
            lon: -60,
            unit: "K",
            flagged: true,
            reason: "Significant trend",
            dates: ["2000-01-01", "2000-02-01"],
            values: [280, 281],
            source_file: "amazon_T2M.csv",
            dataset: "ERA5",
            source_bounds: [-75, -15, -45, 5],
            trend_p: 0.01,
            peak_anomaly_z: 2.5,
            sen_slope: 0.5,
            changepoints: ["2000-02-01"],
          },
        ],
        discovery_count: 1,
        water_balance: { amazon: { status: "inputs unavailable", missing: ["Q", "dS"] } },
        method: "PCMCI",
        preprocessing: "Monthly climatology removed",
      }),
    });
  });
  expect(screen.getByText("Discovery summary")).toBeTruthy();
  expect(screen.getByRole("region", { name: "Water balance" }).textContent).toContain("total runoff, total storage change");
  expect(screen.getByText("Amazon Basin · Temperature")).toBeTruthy();
  expect(screen.getByText(/0\.010/)).toBeTruthy();
  expect(screen.getByRole("region", { name: "Candidate regime changes" }).textContent).toContain("2000-02");
});

test("new scans clear bands and ignore stale anomaly payloads", async () => {
  render(<Dashboard />);
  fireEvent.click(await screen.findByRole("button", { name: "Amazon Basin" }));
  const first = FakeSocket.instances[0];
  const lateResult = first.onmessage!;
  const payload = {
    type: "complete", links: [], discovery_count: 1,
    discoveries: [{ region: "amazon", region_name: "Amazon Basin", variable: "T2M",
      label: "Temperature", unit: "K", dates: ["2000-01-01", "2000-02-01"],
      values: [280, 281], source_bounds: [], trend_p: 0.01, peak_anomaly_z: 3 }],
    anomalies: { status: "complete", scope: "all_model_features", retrospective: true,
      dates: ["2000-01-01"], reconstruction_error: [1.5], is_anomaly: [true],
      window_count: [1], feature_names: ["amazon_T2M"], threshold: 0.8,
      training_error_mean: 0.3, training_error_std: 0.25, sequence_length: 12,
      interpretation: "Combined reconstruction diagnostic" },
  };
  act(() => first.onmessage?.({ data: JSON.stringify(payload) }));
  expect(document.querySelectorAll("rect[data-anomaly-date]")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Sahel" }));
  expect(document.querySelectorAll("rect[data-anomaly-date]")).toHaveLength(0);
  act(() => lateResult({ data: JSON.stringify(payload) }));
  expect(document.querySelectorAll("rect[data-anomaly-date]")).toHaveLength(0);
  act(() => FakeSocket.instances[1].onmessage?.({ data: JSON.stringify({ ...payload,
    anomalies: { status: "unavailable", reason: "Missing model inputs" },
  }) }));
  expect(screen.getByText("Missing model inputs")).toBeTruthy();
  expect(document.querySelectorAll("rect[data-anomaly-date]")).toHaveLength(0);
});
