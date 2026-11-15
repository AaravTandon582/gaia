import type { RegionBounds } from "./region";

export type Domain = "atmosphere" | "hydro" | "cryo" | "bio";
export type CatalogRegion = { id: string; name: string; lat: number; lon: number; bounds: RegionBounds; variables: string[] };
export type CausalLink = { cause: string; effect: string; lag: number; strength: number; p_value: number; corrected_p?: number };
export type Discovery = {
  region: string; region_name: string; variable: string; label: string; domain: Domain;
  lat: number; lon: number; unit: string; flagged: boolean; reason: string;
  dates: string[]; values: number[]; source_file: string; dataset: string; source_bounds: number[];
  trend_p: number; peak_anomaly_z: number; sen_slope?: number;
};
export type StatusEvent = { type: "status"; agent: string; status: string; discovery_count?: number; message?: string };
export type ScanResult = { type: "complete"; links: CausalLink[]; discoveries: Discovery[]; discovery_count: number; method: string; preprocessing: string; n_samples?: number; n_variables?: number; tau_max?: number; fdr_applied?: boolean };
export type ScanEvent = StatusEvent | ScanResult | { type: "error"; message: string };

export function apiUrl(path: string) {
  const base = process.env.NEXT_PUBLIC_API_URL || `${window.location.protocol}//${window.location.hostname}:8000`;
  return new URL(path, base.endsWith("/") ? base : `${base}/`);
}
export function scanUrl() {
  const url = apiUrl("/ws/scan");
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}
export const nodeId = (item: Discovery) => `${item.region}:${item.variable}`;
export const edgeId = (edge: CausalLink) => `${edge.cause}>${edge.effect}:${edge.lag}`;

export function parseScanEvent(raw: string): ScanEvent {
  const event = JSON.parse(raw);
  if (event.type === "status" && typeof event.agent === "string" && typeof event.status === "string") return event;
  if (event.type === "error" && typeof event.message === "string") return event;
  if (event.type === "complete" && Array.isArray(event.links) && Array.isArray(event.discoveries)) {
    const validLinks = event.links.every((link: CausalLink) => typeof link.cause === "string" && typeof link.effect === "string" && Number.isInteger(link.lag) && link.lag >= 1 && link.lag <= 6 && Number.isFinite(link.strength) && Number.isFinite(link.p_value));
    const validSeries = event.discoveries.every((item: Discovery) => typeof item.region === "string" && typeof item.variable === "string" && Array.isArray(item.values) && Array.isArray(item.dates) && item.values.length === item.dates.length && item.values.every(Number.isFinite));
    if (validLinks && validSeries) return event;
  }
  throw new Error("The backend returned an unexpected scan response. Please retry.");
}
