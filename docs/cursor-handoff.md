# Cursor tasks — finish the Hours 20–28 interface

**Status, 2026-11-15:** Cursor implemented the UI work below. Codex reviewed and
fixed date-mapped tooltip values, plot alignment, and pluralization, then verified
18 frontend tests and the production build. This document remains the contract;
browser visual/console QA, screenshots, and deployment checks remain open.
See [handoff verification](../reports/frontend-handoff-verification.md).

**Follow-up:** real production Chrome checks and screenshots are now complete,
including desktop/mobile, cancellation, refresh, and error recovery. Summary
table overflow was fixed. Public deployment was intentionally skipped.
See [browser acceptance](../reports/browser-acceptance.md).

Backend inference is connected to `/ws/scan`. Keep existing retry, error, cancel,
stale-socket, Strict Mode, and unmount/pagehide cleanup behavior. All old result
fields remain. Do not change the scientific thresholds or derive new anomaly
thresholds from the displayed region.

## 1. Display LSTM anomaly bands

Extend the scan result type with this discriminated union (backend sends lists
with one entry per date; this is a contract sketch, not a literal payload):

```typescript
type Anomalies = {
  status: "complete";
  scope: "all_model_features";
  retrospective: true;
  feature_names: string[];
  dates: string[];
  reconstruction_error: number[];
  is_anomaly: boolean[];
  window_count: number[];
  threshold: number;
  training_error_mean: number;
  training_error_std: number;
  sequence_length: number;
  interpretation: string;
} | {
  status: "unavailable";
  scope?: "all_model_features";
  reason: string;
};
```

Use `complete.anomalies`. Align bands by calendar date, not array position;
draw red bands only where `is_anomaly` is true. On unavailable/missing data,
show the reason or an unavailable state and clear previous bands. Label them
**Combined-model anomaly**: the checkpoint scores 12 features across five
regions, so a band must not claim the selected variable caused the anomaly.
Tooltip: date, reconstruction MSE, fixed training threshold, retrospective scope.

Status events include `{type:"status", agent:"lstm", status:"started"}`, then
`status:"anomaly_complete"` or `"anomaly_unavailable"`. These are optional
analysis stages; unavailable LSTM does not fail the causal scan.

## 2. Discovery summary table and help text

Use the existing `discoveries` list: region, variable/label, units, flagged,
trend_p, sen_slope, peak_anomaly_z, reason, and source metadata. Show missing
metrics as unavailable, not zero. Keep raw chart units visible.

For causal edges, distinguish raw p from BH corrected q, signed ParCorr
strength, and lag in months. TE is in nats (finite-sample estimates may be
negative), and `te_p` is a separate circular-shift diagnostic, not FDR-corrected.
It does not remove a PCMCI link. The LSTM score is a reconstruction diagnostic,
not a p-value or a causal attribution. Current Mann–Kendall uses the Hamed–Rao
modification on raw monthly data; do not label its p-value as OLS significance.

## 3. Final polish and demo capture

Finish responsive layout, loading/empty/error states, tooltips, and screenshot
placeholders in the README. Amazon and Sahel are the rehearsed demos. Zero links
is a valid scientific result. Preserve the user's current frontend edits.

Add frontend tests for date alignment, unavailable results clearing old bands,
stale scan results not replacing new anomalies, and summary rendering. Existing
9 tests and the production build must still pass. Perform actual browser console,
map-tile, refresh, and region-switch checks; JSDOM cannot certify these.

## Ownership

- Codex: backend algorithms, inference/API, data retrieval, regression tests,
  API demo rehearsals, README, project summary (implemented in this work).
- Cursor: frontend tasks above; deck/UI assets with the human.
- Human: choose/validate missing physical inputs, authenticated data access,
  deploy accounts/URLs, live acceptance, video/pitch rehearsal, final submission.

Live endpoint: `http://127.0.0.1:8000`, dashboard: `http://127.0.0.1:3000/dashboard`.
Complete API results and scientific numbers: `reports/demo-rehearsal.json`.
