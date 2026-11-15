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
