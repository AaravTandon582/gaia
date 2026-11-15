import WebSocket from "ws";

// Supply the SVG capability probe missing from the headless DOM.
Object.defineProperty(SVGSVGElement.prototype, "createSVGRect", { configurable: true, value: () => ({}) });
// Node's native WebSocket uses a different Event realm from JSDOM. Use the ws
// transport with the same Origin a real browser sends; all traffic stays live.
class BrowserSocket extends WebSocket {
  constructor(url: string) {
    super(url, { origin: "http://127.0.0.1:3000" });
    this.on("error", () => {}); // Closing while connecting is normal cancellation.
  }
}
Object.defineProperty(globalThis, "WebSocket", { configurable: true, value: BrowserSocket });
