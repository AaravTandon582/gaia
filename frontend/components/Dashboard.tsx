"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import type L from "leaflet";
import { AgentStatus } from "@/components/AgentStatus";
import CausalGraph from "@/components/CausalGraph";
import { TimeSeriesChart } from "@/components/TimeSeriesChart";
import { apiUrl, edgeId, nodeId, parseScanEvent, scanUrl, type CatalogRegion, type CausalLink, type ScanResult, type StatusEvent } from "@/lib/api";
import { type RegionSelection } from "@/lib/region";

const RegionMap = dynamic(() => import("@/components/RegionMap"), { ssr: false, loading: () => <div className="grid h-full place-items-center">Loading map…</div> });

export function Dashboard() {
  const [catalog, setCatalog] = useState<CatalogRegion[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const [retry, setRetry] = useState(0);
  const [region, setRegion] = useState<RegionSelection | null>(null);
  const [activeRegion, setActiveRegion] = useState<CatalogRegion | null>(null);
  const [leafletMap, setLeafletMap] = useState<L.Map | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<CausalLink | null>(null);
  const [events, setEvents] = useState<StatusEvent[]>([]);
  const [result, setResult] = useState<ScanResult | null>(null);
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
    setEvents([]);
    setError("");
    setRunning(false);
    const found = catalog.find((item) => selection.lat >= item.bounds.south && selection.lat <= item.bounds.north && selection.lon >= item.bounds.west && selection.lon <= item.bounds.east);
    setActiveRegion(found ?? null);
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
            if (event.status === "causal_started") setPhase("Discovering causal links…");
            else if (event.status === "scan_started") setPhase("Scouts are scanning…");
          } else if (event.type === "complete") {
            setResult(event);
            setPhase(`Scan complete · ${event.links.length} causal links`);
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
      <p className="text-right text-xs text-sky-100/60">Cached NASA observations · 2000–2025</p>
    </header>
    <div className="grid flex-1 lg:min-h-0 lg:grid-cols-[240px_minmax(0,1fr)_350px]">
      <AgentStatus events={events} phase={phase} />
      <main className="flex min-h-[500px] flex-col border-x border-white/10 lg:min-h-0">
        <div className="shrink-0 border-b border-white/10 bg-panel px-4 py-3">
          <h1 className="text-sm font-medium">Click a shaded region to start a scan</h1>
          <p className="mt-1 text-xs text-sky-100/55">Each scan uses the cached regional averages. Select a link to inspect its lag and strength.</p>
          {catalogError ? <div role="alert" className="mt-2 text-sm text-rose-300">{catalogError} <button className="underline" onClick={() => setRetry((value) => value + 1)}>Reconnect</button></div> : <div className="mt-3 flex flex-wrap gap-2" aria-label="Available regions">{catalog.map((item) => <button key={item.id} onClick={() => beginScan(item)} className={`rounded-full border px-3 py-1 text-xs ${activeRegion?.id === item.id ? "border-sky-400 bg-sky-400/20 text-sky-200" : "border-white/15 text-sky-100/70 hover:bg-white/10"}`}>{item.name}</button>)}</div>}
        </div>
        <div className="relative min-h-[380px] flex-1 lg:min-h-0">
          <RegionMap region={region} regions={catalog} onSelect={beginScan} onMapReady={setLeafletMap} />
          {result && <CausalGraph map={leafletMap} discoveries={result.discoveries} links={result.links} selectedEdge={selectedEdge} onEdgeSelect={setSelectedEdge} />}
        </div>
        <p className="shrink-0 border-t border-white/10 px-4 py-2 text-xs text-sky-100/60">Blue links: positive · Pink: negative · Arrows: cause → effect</p>
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
        {result && <section aria-label="Causal graph results" className="rounded-lg border border-white/10 p-3">
          <h2 className="font-medium">{result.links.length} statistical associations</h2>
          <p className="mt-1 text-xs text-sky-100/55">{result.method}<br />{result.preprocessing}</p>
          {result.links.length === 0 ? (
            <div className="mt-3 flex flex-col items-center gap-2 text-sky-100/70">
              <p className="text-sm">No significant lagged links in this scan.</p>
              <p className="text-[11px] leading-relaxed text-center max-w-xs">Try another region or date range to search for lagged statistical associations.</p>
            </div>
          ) : <ul className="mt-3 max-h-52 space-y-2 overflow-auto">{[...result.links].sort((a, b) => Number(a.cause === a.effect) - Number(b.cause === b.effect) || Math.abs(b.strength) - Math.abs(a.strength)).map((edge) => <li key={edgeId(edge)}><button onClick={() => setSelectedEdge(edge)} className={`w-full rounded border p-2 text-left text-xs ${selectedEdge && edgeId(selectedEdge) === edgeId(edge) ? "border-amber-400 bg-amber-400/10" : "border-white/10 hover:bg-white/5"}`}>{nameFor(edge.cause)} → {nameFor(edge.effect)}<span className="mt-1 block text-sky-100/50">{edge.lag} months · r {edge.strength.toFixed(3)} · p {edge.p_value.toPrecision(2)}</span></button></li>)}</ul>}
          <p className="mt-3 text-[11px] text-sky-100/45">Statistical candidate links under PCMCI assumptions; not proof of physical causation.</p>
        </section>}
        {selectedEdge && (
          <>
            <section aria-label="Selected statistical association" className="rounded-lg border border-amber-400/40 p-3 text-sm">
              <h2 className="text-amber-200">Selected statistical association</h2>
              <p className="mt-2">{nameFor(selectedEdge.cause)} → {nameFor(selectedEdge.effect)}</p>
              <p className="mt-2 text-xs text-sky-100/70">
                Lag: {selectedEdge.lag} months<br />
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
              </p>
              {causeTrend && (
                <>
                  <p className="mt-1 text-xs text-sky-100/70">
                    Mann-Kendall p ({nameFor(selectedEdge.cause)}): {causeTrend.trend_p.toPrecision(3)}
                  </p>
                  {causeTrend.sen_slope != null && (
                    <p className="mt-1 text-xs text-sky-100/70">
                      Sen's slope ({nameFor(selectedEdge.cause)}): {causeTrend.sen_slope.toFixed(4)} per month
                    </p>
                  )}
                </>
              )}
            </section>
            <p className="mt-3 text-[11px] text-sky-100/45">
              Association from lagged partial correlation after seasonal and trend removal; not proof of causation.
            </p>
          </>
        )}
        <TimeSeriesChart key={activeRegion?.id ?? "empty"} discoveries={result?.discoveries ?? []} />
      </aside>
    </div>
  </div>;
}
