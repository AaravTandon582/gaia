"use client";

import { useMemo } from "react";

type Props = {
  values: number[];
  dates: string[];
  width?: number;
  height?: number;
  title?: string;
};

// Morlet continuous wavelet scalogram rendered as an SVG heatmap.
// No external plotting library is used so the component stays dependency-free
// and consistent with the existing SVG time-series chart. Power is computed
// client-side from the raw monthly series (the same input wavelet.cwt_scalogram
// would receive on the backend).
export function WaveletScalogram({
  values,
  dates,
  width = 300,
  height = 150,
  title = "Wavelet scalogram",
}: Props) {
  if (!values || values.length < 16) {
    return (
      <section className="rounded-lg border border-white/10 p-3 text-xs text-sky-100/60">
        Wavelet scalogram needs more data.
      </section>
    );
  }

  const n = values.length;
  const omega0 = 6;
  const nScales = 20;
  // Fourier wavelength of Morlet ≈ 1.033 × scale for omega0 = 6.
  const scales = Array.from({ length: nScales }, (_, i) => {
    const period = 2 * Math.pow(32, i / Math.max(1, nScales - 1)); // ~2 … 64 months
    return period / 1.033;
  });

  // Subtract monthly climatology (same as preprocess_for_causal's first step),
  // then remove the linear trend, before the Morlet CWT.
  const months = dates.map((date) => parseInt(date.slice(5, 7), 10));
  const climSum = new Map<number, number>();
  const climCount = new Map<number, number>();
  for (let i = 0; i < n; i++) {
    const m = months[i];
    climSum.set(m, (climSum.get(m) ?? 0) + values[i]);
    climCount.set(m, (climCount.get(m) ?? 0) + 1);
  }
  const climMean = new Map<number, number>();
  for (const [m, sum] of climSum) {
    climMean.set(m, sum / climCount.get(m)!);
  }
  const deseasonalized = values.map((value, i) => value - climMean.get(months[i])!);

  // Remove the linear trend (least squares over the time index).
  const tMean = (n - 1) / 2;
  let num = 0;
  let den = 0;
  let yMean = 0;
  for (let i = 0; i < n; i++) {
    yMean += deseasonalized[i];
  }
  yMean /= n;
  for (let i = 0; i < n; i++) {
    const dt = i - tMean;
    num += dt * (deseasonalized[i] - yMean);
    den += dt * dt;
  }
  const slope = den === 0 ? 0 : num / den;
  const intercept = yMean - slope * tMean;
  const x = deseasonalized.map((value, i) => value - (slope * i + intercept));

  const c1 = Math.pow(Math.PI, -0.25);
  const power: number[][] = [];
  for (let si = 0; si < nScales; si++) {
    const a = scales[si];
    const invSqrtA = 1 / Math.sqrt(a);
    const row: number[] = [];
    const halfWidth = Math.ceil(4 * a);
    for (let b = 0; b < n; b++) {
      let re = 0;
      let im = 0;
      const t0 = Math.max(0, b - halfWidth);
      const t1 = Math.min(n - 1, b + halfWidth);
      for (let t = t0; t <= t1; t++) {
        const eta = (t - b) / a;
        const env = c1 * Math.exp(-0.5 * eta * eta);
        const phase = omega0 * eta;
        // CWT with the conjugate Morlet: psi* = c1 * exp(-i*omega0*eta) * exp(-eta^2/2)
        re += x[t] * env * Math.cos(phase) * invSqrtA;
        im -= x[t] * env * Math.sin(phase) * invSqrtA;
      }
      row.push(re * re + im * im);
    }
    power.push(row);
  }

  const maxPower = Math.max(...power.flat()) || 1;
  const logMax = Math.log(maxPower + 1);

  // NASA-blue sequential stops: deep panel → accent → bright sky.
  const stops = ["#071018", "#16324f", "#4da3ff", "#7dd3fc", "#e0f2fe"];
  const colorFor = (value: number) => {
    const t = Math.min(1, Math.log(value + 1) / logMax);
    const index = t * (stops.length - 1);
    const lo = Math.floor(index);
    const hi = Math.min(lo + 1, stops.length - 1);
    const f = index - lo;
    const interpolate = (a: number, b: number) => Math.round(a + f * (b - a));
    const [r1, g1, b1] = hexRgb(stops[lo]);
    const [r2, g2, b2] = hexRgb(stops[hi]);
    return `rgb(${interpolate(r1, r2)}, ${interpolate(g1, g2)}, ${interpolate(b1, b2)})`;
  };

  const cellW = width / n;
  const cellH = height / nScales;

  // Cone of influence: Morlet e-folding time = sqrt(2) × scale.
  // Times within that distance of either edge are edge-affected.
  const coiX = (scale: number) => (Math.SQRT2 * scale) * cellW;

  return (
    <section className="rounded-lg border border-white/10 p-3">
      <h2 className="text-xs font-medium mb-1 text-sky-100">{title}</h2>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${title} · power by period (rows) and time (columns)`}
        className="mt-1 w-full border border-white/10"
      >
        {/* Heatmap cells: rows are scales (coarse period at top), columns are time. */}
        {power.map((row, si) => {
          const scale = scales[scales.length - 1 - si]; // invert so long period is at top
          const exclude = coiX(scale);
          return row.map((value, b) => {
            const nearEdge = b * cellW < exclude || (n - 1 - b) * cellW < exclude;
            return (
              <rect
                key={`${si}-${b}`}
                x={b * cellW}
                y={si * cellH}
                width={cellW + 0.5}
                height={cellH + 0.5}
                fill={nearEdge ? "#071018" : colorFor(value)}
                fillOpacity={nearEdge ? 0.45 : 1}
                stroke="none"
              />
            );
          });
        })}
        {/* Cone-of-influence boundary: a translucent mask over edge-affected regions. */}
        <defs>
          <linearGradient id="coiFade" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#071018" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#071018" stopOpacity="0" />
          </linearGradient>
        </defs>
        {power.map((_row, si) => {
          const scale = scales[scales.length - 1 - si];
          const exclude = coiX(scale);
          const y = si * cellH;
          return (
            <g key={`coi-${si}`}>
              <rect
                x={0}
                y={y}
                width={Math.min(exclude, width)}
                height={cellH + 0.5}
                fill="url(#coiFade)"
              />
              <rect
                x={Math.max(width - exclude, 0)}
                y={y}
                width={Math.min(exclude, width)}
                height={cellH + 0.5}
                fill="url(#coiFade)"
              />
            </g>
          );
        })}
      </svg>
      <div className="flex justify-between mt-1 text-[10px] text-sky-100/50">
        <span>{dates[0]?.slice(0, 7)}</span>
        <span>periods ↑</span>
        <span>{dates.at(-1)?.slice(0, 7)}</span>
      </div>
      <p className="mt-1 text-[10px] text-sky-100/45">
        Shaded edge bands are the cone of influence (edge-affected, not interpreted).
      </p>
    </section>
  );
}

function hexRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const bigint = parseInt(h, 16);
  return [(bigint >> 16) & 255, (bigint >> 8) & 255, bigint & 255];
}
