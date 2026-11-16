"use client";
import { useState } from "react";
import { nodeId, type Anomalies, type Discovery } from "@/lib/api";
import { LSTMAnomalyBands } from "@/components/LSTMAnomalyBands";

export function TimeSeriesChart({
  discoveries,
  anomalies,
}: {
  discoveries: Discovery[];
  anomalies?: Anomalies;
}) {
  const [selected, setSelected] = useState("");
  const item = discoveries.find((entry) => nodeId(entry) === selected) ?? discoveries[0];
  if (!item) return <section className="rounded-lg border border-white/10 p-4 text-sm text-sky-100/60">Time series will appear after a scan.</section>;
  const min = Math.min(...item.values), max = Math.max(...item.values), span = max - min || 1;
  const points = item.values.map((value, index) => `${12 + index / Math.max(1, item.values.length - 1) * 276},${120 - (value - min) / span * 95}`).join(" ");
  return <section className="rounded-lg border border-white/10 p-3 relative">
    <h2 className="text-sm font-medium">Monthly observations</h2>
    <select aria-label="Time series variable" value={nodeId(item)} onChange={(event) => setSelected(event.target.value)} className="mt-3 w-full rounded bg-slate-800 p-2 text-xs">
      {discoveries.map((entry) => <option key={nodeId(entry)} value={nodeId(entry)}>{entry.label}</option>)}
    </select>
    <LSTMAnomalyBands chartDates={item.dates} anomalies={anomalies} ariaLabel={`${item.label} monthly time series`}>
      <text x="12" y="13" fill="#94a3b8" fontSize="10">{max.toPrecision(4)} {item.unit}</text>
      <polyline points={points} fill="none" stroke="#38bdf8" strokeWidth="1.5" />
      <text x="12" y="140" fill="#94a3b8" fontSize="10">{item.dates[0]?.slice(0, 7)}</text>
      <text x="288" y="140" textAnchor="end" fill="#94a3b8" fontSize="10">{item.dates.at(-1)?.slice(0, 7)}</text>
    </LSTMAnomalyBands>
    <p className="text-xs text-sky-100/65">{item.reason} · {item.values.length} months</p>
    <details className="mt-2 text-xs text-sky-100/45"><summary className="cursor-pointer">Data source</summary><p className="mt-2 break-all">{item.dataset}<br />{item.source_file}<br />Bounds (W, S, E, N): {item.source_bounds.join(", ")}</p></details>
  </section>;
}
