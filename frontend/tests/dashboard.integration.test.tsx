/** DOM integration with real Leaflet/D3 and a live FastAPI WebSocket.
 * This is not a substitute for a visual browser test.
 * Run the backend on port 8000 before npm test.
 */
import { afterEach, beforeAll, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { Map } from "leaflet";

const state = vi.hoisted(() => ({ map: null as Map | null }));
vi.mock("next/dynamic", async () => {
  const { default: RegionMap } = await import("../components/RegionMap");
  const React = await import("react");
  return { default: () => function TestMap(props: React.ComponentProps<typeof RegionMap>) {
    const onMapReady = React.useCallback((map: Map) => { state.map = map; props.onMapReady?.(map); }, [props.onMapReady]);
    return <RegionMap {...props} onMapReady={onMapReady} />;
  } };
});
import { Dashboard } from "../components/Dashboard";

beforeAll(async () => {
  const response = await fetch("http://127.0.0.1:8000/health");
  expect((await response.json()).scouts).toBe(4);
  // JSDOM has no layout engine: supply a viewport for Leaflet's geometry.
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 900 });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 600 });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, get: () => 900 });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, get: () => 600 });
  HTMLElement.prototype.getBoundingClientRect = () => ({ x: 0, y: 0, left: 0, top: 0, right: 900, bottom: 600, width: 900, height: 600, toJSON: () => ({}) });
  // Leaflet detects SVG support via createSVGRect, absent in JSDOM.
  Object.defineProperty(SVGSVGElement.prototype, "createSVGRect", { configurable: true, value: () => ({}) });
});
afterEach(() => { cleanup(); state.map = null; });

async function clickMap(lat: number, lon: number) {
  await waitFor(() => expect(state.map).not.toBeNull());
  const point = state.map!.latLngToContainerPoint([lat, lon]);
  fireEvent.click(state.map!.getContainer(), { clientX: point.x, clientY: point.y });
}

test("map click → real scouts → PCMCI → clickable graph and raw chart", async () => {
  render(<Dashboard />);
  await screen.findByRole("button", { name: "Amazon Basin" });
  await clickMap(-5, -60);
  await screen.findByText("Scan complete · 12 causal links", {}, { timeout: 15_000 });
  expect(screen.getByRole("region", { name: "Causal graph results" })).toBeTruthy();
  expect(document.querySelectorAll(".causal-link").length).toBe(12);
  expect(document.querySelectorAll(".causal-node").length).toBe(3);
  expect(screen.getByRole("img", { name: /monthly time series/ })).toBeTruthy();
  const path = document.querySelector(".causal-link")!;
  fireEvent.click(path);
  expect(screen.getByRole("region", { name: "Selected causal link" }).textContent).toContain("p-value");
  fireEvent.change(screen.getByLabelText("Time series variable"), { target: { value: "amazon:Evap_tavg" } });
  expect(screen.getByRole("img", { name: "Evapotranspiration monthly time series" })).toBeTruthy();
});

test("bad date range reports API error and retry clears stale state", async () => {
  render(<Dashboard />);
  await screen.findByRole("button", { name: "Amazon Basin" });
  fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2025-01-01" } });
  fireEvent.click(screen.getByRole("button", { name: "Amazon Basin" }));
  expect((await screen.findByRole("alert", {}, { timeout: 10_000 })).textContent).toContain("24 cached months");
  expect(document.querySelectorAll(".causal-link").length).toBe(0);
  fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2000-01-01" } });
  fireEvent.click(screen.getByRole("button", { name: "Run scan" }));
  await screen.findByText("Scan complete · 12 causal links", {}, { timeout: 15_000 });
  expect(screen.queryByRole("alert")).toBeNull();
  // Selecting another region must replace the graph, not append to it.
  fireEvent.click(screen.getByRole("button", { name: "Sahel" }));
  await screen.findByText("Scan complete · 3 causal links", {}, { timeout: 15_000 });
  expect(document.querySelectorAll(".causal-link").length).toBe(3);
  expect(within(screen.getByRole("region", { name: "Causal graph results" })).queryByText(/Soil moisture/)).toBeNull();
});

test("unsupported location does not invent data, cancellation permits a new scan", async () => {
  render(<Dashboard />);
  await screen.findByRole("button", { name: "Amazon Basin" });
  await clickMap(-35, -30);
  expect(screen.getByText("No cached data at this location")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Run scan" }).hasAttribute("disabled")).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Amazon Basin" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel scan" }));
  expect(screen.getByText("Scan cancelled")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Run scan" }));
  await screen.findByText("Scan complete · 12 causal links", {}, { timeout: 15_000 });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
  expect(document.querySelectorAll(".causal-link").length).toBe(12);
});
