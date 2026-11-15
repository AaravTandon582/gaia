# Causal pipeline audit and validation

Date: 2026-11-14. Cached observations: 2000-01-01 through 2025-12-31.
Installed Tigramite: 5.2.10.1. No new dependencies.

## Audit before editing

- **Live computation:** `backend/main.py` (pre-edit lines 104–107) calls scouts and PCMCI for each WebSocket request. `backend/data/loader.py:45` caches CSV parsing, not causal results.
- **Old preprocessing:** `backend/analysis/trend.py:42–45` uses additive seasonal decomposition (period 12). `backend/agents/scout.py` (pre-edit lines 34–52) then linearly detrends and supplies residuals. There was no explicit calendar-month climatology subtraction or matrix-level standardization. Custom scout series bypassed preprocessing. Installed ParCorr standardizes its regression arrays internally (`tigramite/independence_tests/parcorr.py:61`).
- **Old significance:** `backend/agents/orchestrator.py` (pre-edit lines 162–178) used raw graph significance at alpha 0.05; no FDR correction.
- **Old settings:** `tau_min` omitted (installed default 0), `tau_max=6`, `pc_alpha=0.05`. Only lags 1–6 were returned. `pc_alpha` regularizes PC1 parent selection; it is not the final MCI or FDR cutoff. Installed implementation/docs: `tigramite/pcmci.py:1746` and `pcmci_base.py:262`.
- **Matrix dimensions:** Amazon 312 × 3, Sahel 312 × 2. These are aligned monthly rows before Tigramite lag trimming, not the effective regression sample count.

## Implemented changes

`backend/agents/preprocessing.py:6` subtracts each calendar month's finite-observation mean, removes an OLS linear trend, and standardizes residuals. NaNs retain their positions; insufficient/degenerate inputs and infinities fail explicitly. The production matrix rejects missing observations rather than interpolating or dropping calendar rows.

`backend/agents/orchestrator.py:160–200` applies preprocessing separately to each aligned raw series, runs `run_pcmci(tau_min=1, tau_max=6, pc_alpha=0.2, alpha_level=0.05)`, then calls `get_corrected_pvalues(p_matrix=..., fdr_method="fdr_bh", exclude_contemporaneous=True, tau_min=1, tau_max=6)`. Argument names were verified from the installed library. BH includes all N × N × 6 lagged tests, including self-links. Returned links require corrected p < 0.05 and distinct full region:variable node IDs.

Scout screening and Mann–Kendall inputs are unchanged; only their outgoing causal `timeseries` now carries raw observations. `pc_alpha` is configurable on OrchestratorAgent/create_app or through `GAIA_PCMCI_PC_ALPHA` for the default server.

The response adds `n_samples`, `n_variables`, `tau_max`, `fdr_applied`, and per-link `corrected_p`. The existing `p_value` remains raw. Empty-variable runs have zero samples/variables and `fdr_applied=false`. JSON fields are additive; the method/preprocessing descriptions now describe the new method.

## Regional link lists

**Before q values below are post-hoc BH corrections of the original full p-matrices, computed during the pre-edit capture. They were not used by the old selection rule.** The old and new parent-selection thresholds and preprocessing differ, so the after result is not just a filter of the before table. Strength is signed partial correlation. Self-links are excluded in both tables.

### Amazon — 312 samples, 3 variables

**Before: 7 links**

| Cause | Effect | Lag (months) | Strength | Corrected p (q) |
|---|---|---:|---:|---:|
| amazon:Rainf_f_tavg | amazon:Evap_tavg | 1 | 0.385666929 | 1.02795538e-10 |
| amazon:Rainf_f_tavg | amazon:Evap_tavg | 5 | 0.159558824 | 0.0534419322 |
| amazon:Rainf_f_tavg | amazon:SoilMoi0_10cm_inst | 6 | 0.114862386 | 0.214130333 |
| amazon:SoilMoi0_10cm_inst | amazon:Rainf_f_tavg | 1 | 0.121001582 | 0.210501816 |
| amazon:SoilMoi0_10cm_inst | amazon:Evap_tavg | 3 | -0.145367736 | 0.0948016475 |
| amazon:SoilMoi0_10cm_inst | amazon:Evap_tavg | 4 | -0.125949079 | 0.20251419 |
| amazon:SoilMoi0_10cm_inst | amazon:Evap_tavg | 5 | -0.190858803 | 0.0102292899 |

**After: 2 links**

| Cause | Effect | Lag (months) | Strength | Corrected p (q) |
|---|---|---:|---:|---:|
| amazon:Rainf_f_tavg | amazon:Evap_tavg | 1 | 0.387513093 | 1.02475112e-10 |
| amazon:Rainf_f_tavg | amazon:Evap_tavg | 5 | 0.174812556 | 0.0289029879 |

### Sahel — 312 samples, 2 variables

**Before: 1 links**

| Cause | Effect | Lag (months) | Strength | Corrected p (q) |
|---|---|---:|---:|---:|
| sahel:Rainf_f_tavg | sahel:Evap_tavg | 1 | 0.273665437 | 1.293541e-05 |

**After: 1 links**

| Cause | Effect | Lag (months) | Strength | Corrected p (q) |
|---|---|---:|---:|---:|
| sahel:Rainf_f_tavg | sahel:Evap_tavg | 1 | 0.274670682 | 1.22946059e-05 |

## Null checks and known-answer tests

- **Known VAR:** T=400 after 200 burn-in samples, seed 0, AR(1)=0.4 on each variable, a→b lag 2 coefficient 0.6, b→c lag 1 coefficient −0.5, independent unit Gaussian innovations. Exactly 2 cross-variable links recovered: a→b lag 2 (strength 0.569674233, q=1.0964337e-32), b→c lag 1 (strength −0.400778808, q=5.9098965e-15). Both requested links recovered; total ≤4 passes.
- **Synthetic shifted null:** the preprocessed VAR matrix is rolled independently by uniform integer offsets 50..350 inclusive, seeds 0..9; no second preprocessing pass. Counts: [0, 0, 0, 0, 0, 0, 4, 0, 0, 0]. Median **0**, satisfying ≤1; max 4 is reported, not hidden.
- **Trend/seasonal artifact:** two independent unit-noise series (seed 0, T=400) share only `0.03*t + 3*sin(2*pi*t/12)`. Same PCMCI/FDR settings in both arms: **6** cross-links without preprocessing; **0** with preprocessing.
- **Real Amazon shifted null:** the exact 312 × 3 preprocessed matrix supplied to PCMCI is captured, each column rolled independently by offsets 50..350 inclusive for seeds 0..19, then passed through production PCMCI/FDR without fitting a second climatology. Mean **0.30**, maximum **2** cross-links. Counts: [1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 2, 1, 0, 0, 1, 0, 0, 0, 0].

These shift checks keep the selected variables fixed. They are diagnostics conditional on scout selection, not a calibrated estimate of whole-pipeline FDR. Independent circular shifts can accidentally preserve a short relative lag (for example Amazon seed 11 shifts rainfall by 90 and evapotranspiration by 88); no seeds or offsets were excluded.

## Verification and reproducibility

- `.venv/bin/python -m pytest backend/agents/tests backend/analysis/tests -q`: **105 passed**. Two existing deprecation warnings.
- `cd frontend && npm test`: **9 passed**, using the restarted live backend.
- `npm run build`: **passed**. `npm run lint`: zero errors, one pre-existing hook-dependency warning.
- Live WebSocket checks returned Amazon n_samples=312, n_variables=3, tau_max=6, fdr_applied=true and 2 links; Sahel 312, 2, 6, true and 1 link.
- Initial legacy failures: Amazon expected 7 links; Arctic required a nonempty graph; two mocks assumed the old PCMCI signature/no correction. Updated exact regional expectations and mocks for the requested algorithm. No scientific assertion or significance threshold was relaxed. Frontend graph/node expectations now reflect the corrected result.
- Scope is the agent/API and analysis suites; the separate ML suite still requires torch, absent from this environment, as recorded in the earlier lifecycle task.

Reproduce the regional results and all 20 real null seeds:

```bash
.venv/bin/python -m scripts.audit_causal
```

Full precision data and every real-null offset: [before](causal-before.json), [after and null trials](causal-after.json), [synthetic checks](causal-synthetic.json).
