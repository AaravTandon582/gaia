# GAIA

Geospatial Autonomous Intelligence for Anomaly & Trend Discovery.

The local demo connects a Next.js/Leaflet dashboard to FastAPI scouts and
Tigramite PCMCI using the NASA Giovanni CSVs in `backend/data/cache`.

## Start the demo

Requirements: Python 3.11+ and Node 22.12+ (the launcher also tries an installed
Node 22 through nvm). From this directory:

```bash
./scripts/dev.sh
```

The launcher installs dependencies in `.venv` and `frontend/node_modules`, starts
both servers, and stops them on Ctrl-C. Open
**http://127.0.0.1:3000/dashboard**. Click the shaded **Amazon Basin** region
(or its region button). Scouts screen the cached series, then a graph of the
inferred links appears on the map. Click a graph edge or a link in the right
panel to inspect lag, signed strength and p-value. The time-series selector shows
raw monthly observations and source metadata.

## What the demo computes

- Five cached regions: Amazon, Arctic, Mediterranean, Sahel and California.
- Four domain scouts run concurrently. A domain without cached variables reports
  zero observations; there is currently no biosphere dataset.
- Scouts flag a significant deseasonalized Mann–Kendall trend (`p < 0.05`) or a
  monthly residual anomaly (`|z| >= 2.5`).
- PCMCI aligns flagged raw monthly series, subtracts each calendar month's
  climatology, removes a linear trend, and standardizes each variable.
  It uses analytic ParCorr, `tau_min=1`, `tau_max=6`, `pc_alpha=0.2`, and retains
  links with Benjamini–Hochberg corrected `q < 0.05`. Set `GAIA_PCMCI_PC_ALPHA`
  before starting the backend to configure the parent-selection threshold.
- Directed lagged links exclude same-node self-links but retain same-variable
  links across regions; contemporaneous associations are
  omitted. These are statistical candidates, not demonstrated physical causes.

The app uses actual cached regional averages, not a fresh spatial query at the
clicked point. Different source products can have slightly different coverage;
inspect each series' source bounds in the detail panel. Dates select whole
calendar months, with at least 24 available months required for screening.
Missing months fail clearly instead of being silently filled or removed.

## Configuration and API

- `GET http://127.0.0.1:8000/health`
- `GET http://127.0.0.1:8000/regions`
- `WS ws://127.0.0.1:8000/ws/scan`

Send `{"regions":["amazon"],"date_range":["2000-01-01","2025-12-31"]}` once per
WebSocket connection. Receive status events followed by either a complete
result with `links`/`discoveries`, or an error. Each connection then closes.

The frontend defaults to its page hostname on port 8000. To override, copy
`frontend/.env.example` to `frontend/.env.local` and set `NEXT_PUBLIC_API_URL`;
restart/rebuild the frontend. Set backend `GAIA_ALLOWED_ORIGINS` to a comma-separated
list when using origins other than localhost or 127.0.0.1 on port 3000.

## Checks

```bash
.venv/bin/python -m pytest backend/agents/tests -q
# With the backend running on 127.0.0.1:8000:
cd frontend
npm test
npm run build
```

Frontend integration tests use real Leaflet click handling, D3, and the live
backend in JSDOM. They cover graph rendering, edge selection, time series,
invalid dates, retry, cancellation, and stale-result replacement. JSDOM supplies
geometry because it has no layout engine; these tests do not verify visual
layout or external map-tile loading in a real browser.

The concrete scout/data contract is documented in `backend/agents/README.md`.
