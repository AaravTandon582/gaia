import { StrictMode } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

vi.mock("next/dynamic", () => ({ default: () => () => null }));
import { Dashboard } from "../components/Dashboard";

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
