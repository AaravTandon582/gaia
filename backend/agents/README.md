# Orchestration

`OrchestratorAgent(scouts, status_callback=None, series_loader=None)` accepts
objects implementing `async scan(regions, date_range) -> list[dict]`. The optional
status callback is async. `await run_scan(regions, date_range)` runs all scouts
with `asyncio.gather`, emits lifecycle events, and returns flattened discoveries.
A failed scout fails the scan and cancels unfinished scouts.

The default app configures four domain scouts and reads curated NASA Giovanni
exports from `backend/data/cache`. Scouts screen monthly data for a significant
deseasonalized Mann–Kendall trend or a detrended monthly anomaly of at least 2.5
standard deviations. Only flagged variables enter PCMCI, after seasonal and
linear trend removal. Domains without cached variables return an empty result.
Custom scouts can still be injected through `create_app([scout, ...])`.

Each discovery represents one flagged variable:

```python
{
    "region": "arctic",
    "variable": "T2M",
    "dates": ["2000-01-01", "2000-02-01", ...],
    "values": [270.2, 271.1, ...],
    "flagged": True,  # optional; defaults to True
}
```

Alternatively, supply `timeseries` as a pandas Series with a DatetimeIndex, or
provide a synchronous `series_loader(discovery) -> pandas.Series`. Series are
averaged by calendar month and restricted to their common date range. Internal
gaps, nonfinite values, duplicate timestamps, constant columns, conflicting
duplicate discoveries, and fewer than 15 shared months raise ValueError. This
minimum is a computational guard, not a statistical sample-size recommendation.
No interpolation or missing-month compression is performed.

`run_causal_discovery(discoveries)` returns dictionaries with `cause`, `effect`,
`lag`, `strength`, and `p_value`. Node names are `region:variable`, lag is positive
months, and strength is the signed partial correlation. PCMCI uses analytic
ParCorr, `tau_max=6`, `pc_alpha=0.05`, and graph threshold `alpha_level=0.05`.
Only directed lagged edges are returned, including self-links. Contemporaneous
associations are omitted. Tigramite indexes links as cause, effect, lag; see its
[PCMCI documentation](https://jakobrunge.github.io/tigramite/#tigramite.pcmci.PCMCI).

Install `backend/requirements.txt` and run `uvicorn backend.main:app` from the
repository root. For a configured app, connect to `/ws/scan` and send one request:

```json
{"regions": ["arctic", "amazon"], "date_range": ["2000-01-01", "2025-12-31"]}
```

The socket streams `{type: "status", agent, status, ...}` events as scouts start
and finish, then a `causal_started` status. The final message is
`{type: "complete", discovery_count, links, discoveries, method, preprocessing}`;
failures emit `type: "error"`. Discoveries contain raw dates/values, signal
summaries, and source metadata; pandas series are excluded from JSON.
Each connection runs one scan and closes. Disconnecting cancels async scouts.
PCMCI runs in a worker thread to keep the event loop responsive; a computation
already running in that thread finishes even if its client disconnects. Cached
CSV analysis also uses worker threads and has the same cancellation limitation.

`GET /regions` supplies coverage and variable availability; `GET /health` reports
API readiness. CORS and WebSocket origins default to localhost/127.0.0.1 port
3000. Override with comma-separated `GAIA_ALLOWED_ORIGINS` when needed.

Run focused checks with `python -m pytest backend/agents/tests -q` after installing
`backend/requirements-dev.txt`.
