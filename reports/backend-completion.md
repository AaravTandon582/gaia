# Backend completion verification — 2026-11-15

## Completed in this work

- Connected saved LSTM inference to the default WebSocket scan, on a worker
  thread, with cancellation between batches. Results add `anomalies`; existing
  discovery/link fields and PCMCI thresholds are unchanged. Missing features or
  artifacts yield an explicit unavailable result, not invented scores.
- Added `DataLoader.fetch`, `list_variables`, and `GET /variables`. Cache-first
  retrieval supports authenticated Earthdata search/download and regional
  monthly averages from regular CF NetCDF/HDF5 grids. It preserves the Sahel
  FLDAS ET and Mediterranean monthly MERRA-2 temperature product choices.
- Added optional download requirements: earthaccess, xarray, h5netcdf, h5py.
  Installed these and the already-declared PyTorch ML requirements in `.venv`.
- Wrote the comprehensive README, project summary, current physical-input
  inventory, reproducible demo rehearsal script, and Cursor API/UI handoff.

## Automated verification

```text
.venv/bin/python -m pytest backend/analysis/tests backend/agents/tests backend/data/tests backend/ml -q
179 passed; 9 subtests passed; 2 pre-existing deprecation warnings

cd frontend && npm test   (Node 22.23.1, updated live backend on :8000)
9 passed

npm run build
Passed compilation, TypeScript, static page generation

git diff --check
Passed
```

The first combined run exposed a pytest package-name mismatch: ML tests were
loaded as `ml.*` while a training test patched `backend.ml.*`. Adding
`backend/__init__.py` made imports consistent. No scientific assertions or
thresholds were loosened. A live HDF5 read exposed missing h5py, which was added
explicitly and covered with an HDF5 fixture in addition to classic NetCDF.

## Real data and API checks

- Five TestClient WebSocket runs each for Amazon and Sahel produced identical
  full result payloads: 2 and 1 PCMCI links respectively. Timings and full
  precision results are in `reports/demo-rehearsal.json`.
- Independent network WebSocket requests to the running uvicorn server returned
  complete LSTM results for both regions, then closed with code 1000.
- Combined-model LSTM input is 312 months × 12 saved features. Threshold
  0.2560639903; 19 months flagged. Scores are retrospective and include training
  months. They are not per-region attribution or held-out accuracy results.
- An actual authenticated Earthdata download of Amazon precipitation for
  January 2000 succeeded, including regional extraction: monthly rate
  0.00010401132021797821 kg/m²/s. It used temporary storage and did not replace
  curated CSVs. Only this product/interval was live-download verified; other
  extraction cases and regional product routing have automated fixture tests.
- NASA/earthaccess search, download, and authentication APIs were checked against
  installed earthaccess 0.19.0 and its official documentation. Source links are
  in the README.

## Remaining ownership and limits

Cursor owns anomaly bands, summary table, metric help, UI polish, and actual
browser/console/refresh QA. Existing frontend changes were preserved. The human
owns deployment accounts/URLs, final demo recording, pitch, and submission.
The local development app was restarted with the new backend.

Real water-balance residuals remain `inputs unavailable`: the new Amazon export
is surface runoff only, and complete runoff/storage change are absent. BOCPD
is implemented/tested but not automatically integrated into default scouts.
The loader does not silently promote downloaded interval data into curated demo
features; that requires checking source bounds, units, and training compatibility.
