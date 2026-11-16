# Orchestration

`OrchestratorAgent(scouts, status_callback=None, series_loader=None, pc_alpha=0.2)` accepts
objects implementing `async scan(regions, date_range) -> list[dict]`. The optional
status callback is async. `await run_scan(regions, date_range)` runs all scouts
with `asyncio.gather`, emits lifecycle events, and returns flattened discoveries.
A failed scout fails the scan and cancels unfinished scouts.

The default app configures four domain scouts and reads curated NASA Giovanni
exports from `backend/data/cache`. Scouts screen monthly data for a significant
Hamed–Rao modified Mann–Kendall trend on raw monthly values or a detrended monthly anomaly of at least 2.5
standard deviations. Only flagged variables enter PCMCI. Their raw series are
aligned, monthly climatology is subtracted, a linear trend is removed, and
each residual series is standardized. Scout screening inputs stay unchanged.
Domains without cached variables return an empty result.
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
`lag`, `strength`, raw `p_value`, `corrected_p`, `te`, and `te_p`. Node names are `region:variable`, lag is positive
months, and strength is the signed partial correlation. PCMCI uses analytic
ParCorr, `tau_min=1`, `tau_max=6`, and `pc_alpha=0.2` for PC1 parent selection.
Benjamini–Hochberg FDR is applied across all N × N × 6 lagged tests, including
self-links; only corrected p-values strictly below 0.05 are retained. Self-links
are suppressed after correction. Set `pc_alpha` on the orchestrator/create_app,
or `GAIA_PCMCI_PC_ALPHA` for the default app, to configure parent selection.
Only directed lagged edges between distinct `region:variable` nodes are returned.
Same-variable links across different regions are retained. Contemporaneous
associations are omitted. Tigramite indexes links as cause, effect, lag; see its
[PCMCI documentation](https://jakobrunge.github.io/tigramite/#tigramite.pcmci.PCMCI).

Only retained links run KSG transfer entropy on the same preprocessed anomalies,
with each link's lag, history length 2 and k=5. `te` is in nats; `te_p` uses 200
source circular shifts and the plus-one correction (seed 0). It is a bivariate
diagnostic conditioned on target history, not the multivariate conditioning used
by PCMCI; `te_p` is not FDR-adjusted and does not change the retained link set.
Cancellation is checked between links and surrogate evaluations.

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
The default app also runs `AnomalyAgent` in a worker thread and adds `anomalies`:
date-aligned reconstruction errors/flags, training threshold, and model feature
names. Its scope is all 12 model features across five regions, not attribution
to the selected region. Missing model dependencies/artifacts/features return an
explicit `unavailable` status without failing the causal scan. Cancellation is
checked between inference batches. See [the UI contract](../../docs/cursor-handoff.md).

The complete response also includes `n_samples` (aligned monthly rows before
lag trimming), `n_variables` (flagged unique nodes), `tau_max`, and `fdr_applied`.
For an empty variable set these counts are zero and `fdr_applied` is false.
Each connection runs one scan and closes. Disconnecting cancels async scouts.
PCMCI runs in a worker thread to keep the event loop responsive; a computation
already running in that thread finishes even if its client disconnects. Cached
CSV analysis also uses worker threads and has the same cancellation limitation.

`GET /regions` supplies coverage and variable availability; `GET /health` reports
API readiness. CORS and WebSocket origins default to localhost/127.0.0.1 port
3000. Override with comma-separated `GAIA_ALLOWED_ORIGINS` when needed.

Run focused checks with `python -m pytest backend/agents/tests -q` after installing
`backend/requirements-dev.txt`.

## Candidate regime dates

Each default discovery includes `changepoints`, a list of ISO calendar dates.
BOCPD processes standardized deseasonalized observations, with a cancellation
check at every streaming update. Missing months/values remain invalid rather
than being compressed. Boundaries are heuristic and do not alter the screening
flag or PCMCI graph. The dashboard displays them in a separate summary.
