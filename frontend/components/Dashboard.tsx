"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import type L from "leaflet";
import { AgentStatus } from "@/components/AgentStatus";
import CausalGraph from "@/components/CausalGraph";
import { TimeSeriesChart } from "@/components/TimeSeriesChart";
import { apiUrl, edgeId, nodeId, parseScanEvent, scanUrl, type Anomalies, type CatalogRegion, type CausalLink, type ScanResult, type StatusEvent } from "@/lib/api";
import { type RegionSelection } from "@/lib/region";

const RegionMap = dynamic(() => import("@/components/RegionMap"), { ssr: false, loading: () => <div className="grid h-full place-items-center">Loading map…</div> });

const DEMO_SCENARIOS = [
  { label: "Amazon Water Cycle", regionId: "amazon", hasData: true },
  { label: "Sahel Water Cycle", regionId: "sahel", hasData: true },
  { label: "Arctic Temperature and Snow", regionId: "arctic", hasData: true },
  { label: "Mediterranean Water Cycle", regionId: "mediterranean", hasData: true },
  { label: "California Soil Moisture", regionId: "california", hasData: true },
] as const;

export function Dashboard() {
  const [catalog, setCatalog] = useState<CatalogRegion[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const [retry, setRetry] = useState(0);
  const [region, setRegion] = useState<RegionSelection | null>(null);
  const [activeRegion, setActiveRegion] = useState<CatalogRegion | null>(null);
  const [demoRegion, setDemoRegion] = useState<string | null>(null);
  const [leafletMap, setLeafletMap] = useState<L.Map | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<CausalLink | null>(null);
  const [events, setEvents] = useState<StatusEvent[]>([]);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [anomalies, setAnomalies] = useState<Anomalies | undefined>(undefined);
  const [running, setRunning] = useState(false);
  const [phase, setPhase] = useState("Select a shaded region to scan");
  const [error, setError] = useState("");
  const [startDate, setStartDate] = useState("2000-01-01");
  const [endDate, setEndDate] = useState("2025-12-31");
  const socket = useRef<WebSocket | null>(null);
  const timeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const disconnect = useCallback(() => {
    if (timeout.current) clearTimeout(timeout.current);
    timeout.current = null;
    const previous = socket.current;
    socket.current = null;
    if (previous) {
      previous.onopen = previous.onmessage = previous.onerror = previous.onclose = null;
      previous.close();
    }
  }, []);
  useEffect(() => {
    // A document refresh/navigation need not unmount the React tree.
    const onPageHide = () => {
      if (!socket.current) return;
      disconnect();
      setRunning(false);
      setEvents([]);
      setPhase("Scan cancelled");
    };
    window.addEventListener("pagehide", onPageHide);
    return () => {
      window.removeEventListener("pagehide", onPageHide);
      disconnect();
    };
  }, [disconnect]);
  useEffect(() => {
    const controller = new AbortController();
    fetch(apiUrl("/regions"), { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Region catalog is unavailable");
        const data = await response.json();
        if (!Array.isArray(data.regions)) throw new Error("Invalid region catalog");
        setCatalog(data.regions);
        setCatalogError("");
      })
      .catch((cause) => { if (cause.name !== "AbortError") setCatalogError("Cannot reach the backend. Start the GAIA API, then reconnect."); });
    return () => controller.abort();
  }, [retry]);

  const beginScan = useCallback((selection: RegionSelection) => {
    disconnect();
    setRegion(selection);
    setSelectedEdge(null);
    setResult(null);
    setAnomalies(undefined);
    setEvents([]);
    setError("");
    setRunning(false);
    const found = catalog.find((item) => selection.lat >= item.bounds.south && selection.lat <= item.bounds.north && selection.lon >= item.bounds.west && selection.lon <= item.bounds.east);
    setActiveRegion(found ?? null);
    setDemoRegion(found?.id ?? null);
    if (!found) { setPhase("No cached data at this location"); return; }
    setRegion({ lat: found.lat, lon: found.lon, bounds: found.bounds });
    if (!startDate || !endDate || startDate > endDate) { setError("Choose a valid start and end date."); setPhase("Invalid date range"); return; }
    setPhase("Connecting to scouts…");
    setRunning(true);
    const fail = (message: string) => { disconnect(); setRunning(false); setError(message); setPhase("Scan failed — ready to retry"); };
    try {
      const ws = new WebSocket(scanUrl());
      socket.current = ws;
      timeout.current = setTimeout(() => {
        if (socket.current === ws) fail("Scan timed out after 90 seconds. Please retry.");
      }, 90_000);
      ws.onopen = () => { if (socket.current === ws) ws.send(JSON.stringify({ regions: [found.id], date_range: [startDate, endDate] })); };
      ws.onmessage = (message) => {
        if (socket.current !== ws) return;
        try {
          const event = parseScanEvent(message.data);
          if (event.type === "status") {
            setEvents((current) => [...current.slice(-39), event]);
            if (event.agent === "lstm") {
              if (event.status === "started") setPhase("LSTM anomaly scan started…");
              else if (event.status === "anomaly_complete") setPhase("LSTM anomaly scan complete.");
              else if (event.status === "anomaly_unavailable") setPhase("LSTM anomaly data unavailable.");
            } else if (event.status === "causal_started") setPhase("Discovering statistical associations…");
            else if (event.status === "scan_started") setPhase("Scouts are scanning…");
          } else if (event.type === "complete") {
            setResult(event);
            setAnomalies(event.anomalies);
            setPhase(`Scan complete · ${event.links.length} statistical association${event.links.length === 1 ? "" : "s"}`);
            setRunning(false);
            disconnect();
          } else fail(event.message);
        } catch (cause) { fail(cause instanceof Error ? cause.message : "Invalid scan response"); }
      };
      ws.onerror = () => { if (socket.current === ws) fail("Cannot connect to the scan API. Check that the backend is running and retry."); };
      ws.onclose = () => { if (socket.current === ws) fail("The scan connection closed before results arrived. Please retry."); };
    } catch (cause) { fail(cause instanceof Error ? cause.message : "Could not start scan"); }
  }, [catalog, disconnect, startDate, endDate]);

  const nameFor = (id: string) => result?.discoveries.find((item) => nodeId(item) === id)?.label ?? id;
  const causeTrend = selectedEdge ? result?.discoveries.find((item) => nodeId(item) === selectedEdge.cause) : undefined;
  const fieldClass = "w-full rounded border border-white/15 bg-slate-900 px-2 py-1.5 text-xs text-sky-100";
  return <div className="flex min-h-dvh flex-col lg:h-dvh">
    <header className="flex min-h-14 shrink-0 items-center justify-between gap-4 border-b border-white/10 px-4 py-3">
      <Link href="/" className="text-sm font-semibold tracking-[0.22em]">GAIA</Link>
      <p className="text-right text-xs text-sky-100/60 flex flex-col items-end justify-end gap-1.5 sm:flex-row sm:items-center">
        {running ? (
          <>
            <span className="relative inline-block h-3 w-3">
              <span className="animate-spin absolute inset-0 block h-3 w-3 rounded-full border-2 border-sky-500/30 border-t-sky-400"></span>
            </span>
            {phase}
          </>
        ) : (
          "Cached NASA observations · 2000–2025"
        )}
      </p>
    </header>
    <div className="grid flex-1 lg:min-h-0 lg:grid-cols-[240px_minmax(0,1fr)_350px]">
      <AgentStatus events={events} phase={phase} />
      <main className="flex min-h-[500px] flex-col border-x border-white/10 lg:min-h-0">
        <div className="shrink-0 border-b border-white/10 bg-panel px-4 py-3">
          <h1 className="text-sm font-medium">Click a shaded region to start a scan</h1>
          <p className="mt-1 text-xs text-sky-100/55">Each scan uses the cached regional averages. Select a link to inspect its lag and strength.</p>
          {catalogError ? <div role="alert" className="mt-2 text-sm text-rose-300">{catalogError} <button className="underline" onClick={() => setRetry((value) => value + 1)}>Reconnect</button></div> : <div className="mt-3 flex flex-wrap gap-2" aria-label="Available regions">{catalog.map((item) => <button key={item.id} onClick={() => beginScan(item)} className={`rounded-full border px-3 py-1 text-xs ${activeRegion?.id === item.id ? "border-sky-400 bg-sky-400/20 text-sky-200" : "border-white/15 text-sky-100/70 hover:bg-white/10"}`}>{item.name}</button>)}</div>}
          <div className="mt-3">
            <p className="text-[11px] uppercase tracking-widest text-sky-200/60 mb-1">Demo scenarios</p>
            <select
              aria-label="Demo scenario"
              value={demoRegion ?? ""}
              onChange={(event) => {
                const id = event.target.value;
                if (!id) return;
                const item = catalog.find((region) => region.id === id);
                if (!item) return;
                const selection: RegionSelection = {
                  lat: (item.bounds.south + item.bounds.north) / 2,
                  lon: (item.bounds.west + item.bounds.east) / 2,
                  bounds: item.bounds,
                };
                beginScan(selection);
              }}
              className="w-full rounded border border-white/15 bg-slate-900 px-2 py-1.5 text-xs text-sky-100"
            >
              <option value="">Choose a demo scenario</option>
              {DEMO_SCENARIOS.map((scenario) => {
                const item = catalog.find((region) => region.id === scenario.regionId);
                if (!item) return null;
                return (
                  <option
                    key={scenario.regionId}
                    value={scenario.regionId}
                    disabled={item.variables.length === 0}
                  >
                    {scenario.label}{item.variables.length === 0 ? " — no cached variables" : ""}
                  </option>
                );
              })}
            </select>
          </div>
        </div>
        <div className="relative min-h-[380px] flex-1 lg:min-h-0">
          <RegionMap region={region} regions={catalog} onSelect={beginScan} onMapReady={setLeafletMap} />
          {result && <CausalGraph map={leafletMap} discoveries={result.discoveries} links={result.links} selectedEdge={selectedEdge} onEdgeSelect={setSelectedEdge} />}
        </div>
        <p className="shrink-0 border-t border-white/10 px-4 py-2 text-xs text-sky-100/60">Blue links: positive · Pink: negative · Arrows: lagged association direction (source → target)</p>
      </main>
      <aside className="flex flex-col gap-4 overflow-auto bg-panel p-4 lg:min-h-0">
        <section>
          <p className="text-[11px] uppercase tracking-widest text-sky-200/60">Detail view</p>
          <h2 className="mt-1 text-lg">{activeRegion?.name ?? "Select a region"}</h2>
          <p className="mt-1 text-xs text-sky-100/55">{activeRegion ? `${activeRegion.variables.length} cached variables available` : region ? "No cached observations here. Choose a shaded region or a region button." : "Amazon Basin is a good first demo."}</p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <label className="text-xs text-sky-100/60">Start<input aria-label="Start date" type="date" className={fieldClass} value={startDate} onChange={(event) => setStartDate(event.target.value)} disabled={running} /></label>
            <label className="text-xs text-sky-100/60">End<input aria-label="End date" type="date" className={fieldClass} value={endDate} onChange={(event) => setEndDate(event.target.value)} disabled={running} /></label>
          </div>
          {running ? <button className="mt-3 rounded border border-white/20 px-4 py-2 text-sm" onClick={() => { disconnect(); setRunning(false); setEvents([]); setPhase("Scan cancelled"); }}>Cancel scan</button> : <button disabled={!activeRegion} className="mt-3 rounded bg-accent px-4 py-2 text-sm font-medium text-slate-950 disabled:opacity-40" onClick={() => activeRegion && beginScan(activeRegion)}>Run scan</button>}
          {error && <p role="alert" className="mt-3 rounded border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</p>}
        </section>
        {running && !result && (
          <section aria-label="Causal graph results" className="rounded-lg border border-white/10 p-3">
            <h2 className="font-medium">Statistical associations</h2>
            <ul className="mt-3 max-h-52 space-y-2 overflow-auto">
              {[1, 2, 3].map((i) => (
                <li key={i} className="w-full rounded border p-2 text-left text-xs border-white/10 bg-white/5 animate-pulse">
                  <div className="h-3 bg-slate-800 rounded w-3/4 mb-1"></div>
                  <div className="h-2 bg-slate-800 rounded w-1/2"></div>
                </li>
              ))}
            </ul>
          </section>
        )}
        {!running && !result && !catalogError && (
          <div className="mt-3 flex flex-col items-center gap-2 text-sky-100/50">
            <p className="text-sm">No scan results yet.</p>
            <p className="text-[11px] text-center max-w-xs">Run a scan to see statistical associations here.</p>
          </div>
        )}
        {result && <section aria-label="Causal graph results" className="rounded-lg border border-white/10 p-3">
          <h2 className="font-medium">{result.links.length} statistical association{result.links.length === 1 ? "" : "s"}</h2>
          <p className="mt-1 text-xs text-sky-100/55">{result.method}<br />{result.preprocessing}</p>
          {result.links.length === 0 ? (
            <div className="mt-3 flex flex-col items-center gap-2 text-sky-100/70">
              <p className="text-sm">No significant lagged links in this scan.</p>
              <p className="text-[11px] leading-relaxed text-center max-w-xs">Try another region or date range to search for lagged statistical associations.</p>
            </div>
          ) : <ul className="mt-3 max-h-52 space-y-2 overflow-auto">{[...result.links].sort((a, b) => Number(a.cause === a.effect) - Number(b.cause === b.effect) || Math.abs(b.strength) - Math.abs(a.strength)).map((edge) => <li key={edgeId(edge)}><button onClick={() => setSelectedEdge(edge)} className={`w-full rounded border p-2 text-left text-xs ${selectedEdge && edgeId(selectedEdge) === edgeId(edge) ? "border-amber-400 bg-amber-400/10" : "border-white/10 hover:bg-white/5"}`}>{nameFor(edge.cause)} → {nameFor(edge.effect)}<span className="mt-1 block text-sky-100/50">{edge.lag} month{edge.lag === 1 ? "" : "s"} · r {edge.strength.toFixed(3)} · p {edge.p_value.toPrecision(2)}</span></button></li>)}</ul>}
          <p className="mt-3 text-[11px] text-sky-100/45">Statistical candidate links under PCMCI assumptions; not proof of physical causation.</p>
        </section>}
        {result && result.discoveries.length > 0 && (
          <section className="rounded-lg border border-white/10 p-3">
            <p className="text-[11px] uppercase tracking-widest text-sky-200/60 mb-2">Discovery summary</p>
            <div className="overflow-x-auto" role="region" aria-label="Discovery statistics" tabIndex={0}>
            <table className="w-full min-w-[560px] text-xs border-collapse [&_th]:pr-3 [&_td]:pr-3 [&_th]:whitespace-nowrap [&_td]:whitespace-nowrap">
              <thead>
                <tr className="text-sky-100/40 border-b border-white/10">
                  <th className="text-left pb-1">Region · variable</th>
                  <th className="text-left pb-1">Units</th>
                  <th className="text-left pb-1">Flagged</th>
                  <th className="text-left pb-1">Trend p</th>
                  <th className="text-left pb-1">Sen&apos;s slope</th>
                  <th className="text-left pb-1">Peak anomaly z</th>
                </tr>
              </thead>
              <tbody>
                {result.discoveries.map((item) => (
                  <tr key={nodeId(item)} className="border-b border-white/10 last:border-0">
                    <td className="py-1 text-sky-100/70">{item.region_name} · {item.label}</td>
                    <td className="py-1 text-sky-100/60">{item.unit}</td>
                    <td className="py-1">{item.flagged ? <span className="text-rose-300">Yes</span> : <span className="text-sky-100/50">No</span>}</td>
                    <td className="py-1 text-sky-100/60">{Number.isFinite(item.trend_p) ? item.trend_p.toPrecision(3) : "unavailable"}</td>
                    <td className="py-1 text-sky-100/60">{item.sen_slope != null ? item.sen_slope.toFixed(4) : "unavailable"}</td>
                    <td className="py-1 text-sky-100/60">{Number.isFinite(item.peak_anomaly_z) ? item.peak_anomaly_z.toPrecision(3) : "unavailable"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            <p className="mt-1 text-[10px] text-sky-100/45">Scroll the table horizontally for all metrics.</p>
            <p className="mt-2 text-[10px] text-sky-100/45 leading-relaxed">
              Raw p-value is the unadjusted ParCorr test p; FDR-adjusted p is the Benjamini-Hochberg corrected q. Strength is the signed
              partial-correlation coefficient; lag is in months. Transfer entropy (TE) is in nats — finite-sample estimates may be negative —
              and TE p-value is a separate circular-shift diagnostic, not FDR-corrected, and does not remove a PCMCI link. The LSTM score is a
              reconstruction diagnostic, not a p-value or a causal attribution. Mann–Kendall uses the Hamed–Rao modification on raw monthly
              data; its p-value is not OLS significance.
            </p>
          </section>
        )}
        {result && <section aria-label="Candidate regime changes" className="rounded-lg border border-white/10 p-3">
          <h2 className="text-sm font-medium">Candidate regime changes</h2>
          <p className="mt-1 text-xs text-sky-100/55">BOCPD screens standardized, seasonally adjusted observations. These dates are exploratory boundaries, not significance tests.</p>
          <ul className="mt-3 space-y-2 text-xs">
            {result.discoveries.map(item => <li key={nodeId(item)}>
              <span className="text-sky-100/80">{item.label}: </span>
              <span className="text-sky-100/55">{item.changepoints === undefined ? "Unavailable" : item.changepoints.length ? item.changepoints.map(date => date.slice(0, 7)).join(", ") : "No candidate boundaries"}</span>
            </li>)}
          </ul>
        </section>}
        {result && activeRegion && result.water_balance?.[activeRegion.id] && <section aria-label="Water balance" className="rounded-lg border border-white/10 p-3">
          <h2 className="text-sm font-medium">Water balance</h2>
          {(() => {
            const balance = result.water_balance[activeRegion.id];
            return balance.status === "inputs unavailable"
              ? <p className="mt-2 text-xs text-sky-100/55">Inputs unavailable. Missing: {balance.missing.map(term => ({ P: "precipitation", ET: "evapotranspiration", Q: "total runoff", dS: "total storage change" } as Record<string, string>)[term] ?? term).join(", ")}.</p>
              : <p className="mt-2 text-xs text-sky-100/55">Mean residual: {balance.mean_residual.toPrecision(3)} {balance.unit}. {balance.interpretation}</p>;
          })()}
        </section>}
        {selectedEdge && (
          <>
            <section aria-label="Selected statistical association" className="rounded-lg border border-amber-400/40 p-3 text-sm">
              <h2 className="text-amber-200">Selected statistical association</h2>
              <p className="mt-2">{nameFor(selectedEdge.cause)} → {nameFor(selectedEdge.effect)}</p>
              <p className="mt-2 text-xs text-sky-100/70">
                Lag: {selectedEdge.lag} month{selectedEdge.lag === 1 ? "" : "s"}<br />
                Strength: {selectedEdge.strength.toFixed(4)}<br />
                p-value: {selectedEdge.p_value.toPrecision(4)}
                {selectedEdge.corrected_p != null && (
                  <>
                    <br />
                    FDR-adjusted p: {selectedEdge.corrected_p.toPrecision(4)}
                  </>
                )}
                {result?.n_samples != null && (
                  <>
                    <br />
                    n samples: {result.n_samples}
                  </>
                )}
                {selectedEdge.te != null && (
                  <>
                    <br />
                    Transfer entropy: {selectedEdge.te.toPrecision(4)}
                  </>
                )}
                {selectedEdge.te_p != null && (
                  <>
                    <br />
                    TE p-value: {selectedEdge.te_p.toPrecision(4)}
                  </>
                )}
              </p>
              {causeTrend && (
                <>
                  <p className="mt-1 text-xs text-sky-100/70">
                    Mann-Kendall p ({nameFor(selectedEdge.cause)}): {causeTrend.trend_p.toPrecision(3)}
                  </p>
                  {causeTrend.sen_slope != null && (
                    <p className="mt-1 text-xs text-sky-100/70">
                      Sen&apos;s slope ({nameFor(selectedEdge.cause)}): {causeTrend.sen_slope.toFixed(4)} per month
                    </p>
                  )}
                </>
              )}
              {causeTrend && causeTrend.inputsAvailable === false && (
                <p className="mt-1 text-xs text-sky-100/40">
                  Data consistency check: inputs unavailable (runoff and storage not loaded)
                </p>
              )}
              {causeTrend && causeTrend.inputsAvailable !== false && causeTrend.meanResidualMmPerMonth != null && (
                <>
                  <p className="mt-1 text-xs text-sky-100/70">
                    Data consistency check: mean residual {causeTrend.meanResidualMmPerMonth.toFixed(2)} mm/month
                  </p>
                  <p className="mt-0 text-[10px] text-sky-100/45">
                    Compares P, ET, runoff and storage change. Tests whether datasets agree, not whether a link is a statistical association.
                  </p>
                </>
              )}
            </section>
            <p className="mt-3 text-[11px] text-sky-100/45">
              Association from lagged partial correlation after seasonal and trend removal; a statistical association only.
            </p>
          </>
        )}
        <TimeSeriesChart key={activeRegion?.id ?? "empty"} discoveries={result?.discoveries ?? []} anomalies={anomalies} />
      </aside>
    </div>
  </div>;
}
