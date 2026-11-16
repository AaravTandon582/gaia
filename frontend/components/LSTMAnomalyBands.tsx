"use client";

import { useMemo, useState, type ReactNode } from "react";
import type { Anomalies } from "@/lib/api";

type Props = {
  chartDates: string[];
  anomalies: Anomalies | undefined;
  width?: number;
  height?: number;
  ariaLabel?: string;
  children?: ReactNode;
};

export function LSTMAnomalyBands({
  chartDates, anomalies, width = 300, height = 145,
  ariaLabel = "LSTM combined-model anomaly bands", children,
}: Props) {
  const [hoverDate, setHoverDate] = useState<string | null>(null);
  const complete = anomalies?.status === "complete" ? anomalies : undefined;
  const anomalyByDate = useMemo(() => new Map(
    complete?.dates.map((date, index) => [date.slice(0, 10), index]) ?? [],
  ), [complete]);
  const bands = chartDates.flatMap((date, chartIndex) => {
    const anomalyIndex = anomalyByDate.get(date.slice(0, 10));
    return anomalyIndex !== undefined && complete?.is_anomaly[anomalyIndex]
      ? [{ date, chartIndex, anomalyIndex }] : [];
  });
  const hovered = bands.find((band) => band.date === hoverDate);
  // Use the same margins and coordinates as the observation polyline.
  const left = 12, right = width - 12, top = 25, bottom = height - 25;
  const step = (right - left) / Math.max(1, chartDates.length - 1);
  if (!anomalies && !children) return null;

  return <section className="relative">
    {complete && <p className="mt-2 text-xs text-rose-200">Combined-model anomaly</p>}
    <svg viewBox={`0 0 ${width} ${height}`} className="mt-3 w-full" role="img" aria-label={ariaLabel}>
      {bands.map(({ date, chartIndex, anomalyIndex }) => {
        const center = left + chartIndex * step;
        const x = Math.max(left, center - step / 2);
        const end = Math.min(right, center + step / 2);
        const description = `${date.slice(0, 7)} · MSE ${complete!.reconstruction_error[anomalyIndex].toPrecision(3)} · threshold ${complete!.threshold.toPrecision(3)} · retrospective`;
        return <rect key={date} data-anomaly-date={date} x={x} y={top}
          width={end - x} height={bottom - top} fill="#fb7185"
          fillOpacity={hoverDate === date ? 0.35 : 0.15}
          stroke="#fb7185" strokeWidth={hoverDate === date ? 2 : 1}
          tabIndex={0} aria-label={description}
          onMouseEnter={() => setHoverDate(date)} onMouseLeave={() => setHoverDate(null)}
          onFocus={() => setHoverDate(date)} onBlur={() => setHoverDate(null)}>
          <title>{description}</title>
        </rect>;
      })}
      {children}
    </svg>
    {hovered && complete && <div role="tooltip" className="absolute left-0 top-0 z-10 rounded border border-white/10 bg-slate-900 px-2 py-1 text-xs text-sky-100 shadow-lg">
      {hovered.date.slice(0, 7)} · MSE {complete.reconstruction_error[hovered.anomalyIndex].toPrecision(3)} · threshold {complete.threshold.toPrecision(3)} · retrospective
    </div>}
    {anomalies?.status === "unavailable" && <div className="mt-1 text-xs text-sky-100/50">
      <p>LSTM anomaly bands unavailable</p><p>{anomalies.reason}</p>
    </div>}
    {complete && bands.length === 0 && <p className="mt-1 text-[10px] text-sky-100/50">No combined-model anomaly bands detected this period.</p>}
  </section>;
}
