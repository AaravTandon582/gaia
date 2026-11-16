# GAIA — project summary

## Problem

Climate and water-cycle measurements are distributed across products, variables,
and regions. Inspecting them individually makes lagged relationships and unusual
periods difficult to investigate, while shared seasonality can produce misleading
associations.

## Approach

GAIA offers a map-based workflow: select a region, run concurrent domain scouts,
inspect candidate lagged links, and examine the underlying observations and
statistics. Cached NASA Giovanni series make the demonstration reproducible.
Each scan runs analysis live; only data parsing and the loaded LSTM are reused.

## Five core statistical methods

1. **Trend/Mann–Kendall/Sen:** seasonal decomposition, regression, dependence-aware
   monotonic-trend screening, and robust slope summaries.
2. **Bayesian online change-point detection:** a Normal–Inverse–Gamma model tracks
   candidate regime boundaries in standardized deseasonalized observations.
   Default scouts expose calendar dates in the dashboard.
3. **Wavelet analysis:** discrete decomposition and continuous wavelet power expose
   variation across timescales.
4. **PCMCI:** lagged conditional-independence tests after climatology removal,
   detrending, and standardization, with BH false-discovery correction.
5. **Transfer entropy:** nearest-neighbor information transfer with circular-shift
   surrogates that retain within-series temporal structure apart from the wrap.

A **pretrained LSTM autoencoder** adds multivariate reconstruction anomalies.
The API uses saved training normalization and a fixed training mean + 2σ cutoff;
it reports combined-model scores rather than unsupported regional attribution.

## Observed demo results

Monthly observations cover January 2000–December 2025. Results below are measured
outputs, not claims of validated physical causation.

| Region | Cause → effect | Lag | ParCorr | BH q | TE (nats) | TE p |
|---|---|---:|---:|---:|---:|---:|
| Amazon | Precipitation → ET | 1 month | 0.387513 | 1.025e-10 | 0.077849 | 0.009950 |
| Amazon | Precipitation → ET | 5 months | 0.174813 | 0.028903 | -0.002705 | 0.626866 |
| Sahel | Precipitation → ET | 1 month | 0.274671 | 1.229e-5 | 0.061631 | 0.149254 |

Amazon uses 312 monthly samples and 3 variables; Sahel uses 312 and 2. Five full
API scans per region reproduced identical result payloads. TE supports the
Amazon one-month link at p < 0.05; it does not independently support the other
two links at that cutoff. Both diagnostics are shown rather than forcing agreement.

The 12-feature LSTM flags **19/312 months** using training mean 0.0901874,
training std 0.0829383, and threshold **0.256064**. This is one retrospective
multiregion diagnostic, shared across these scans. The period includes training
data; no independent detection-accuracy claim is made.

The earlier causal validation recovered both designed links in a synthetic VAR,
returned zero links for the preprocessed shared-trend/seasonal artifact case,
and found mean 0.30 / maximum 2 cross-links over 20 circular-shift null trials on
the real Amazon matrix. These are conditional on selected variables, not a
whole-pipeline false-discovery guarantee. [Audit](../reports/causal-audit.md).

## Engineering contribution

- Request-local cancellation and worker-thread analysis keep the API responsive
  and stop subsequent work after a client disconnects.
- Raw observations remain available alongside explicitly preprocessed causal inputs.
- Model calibration uses only training windows; missing model features produce
  an explicit unavailable result rather than fabricated scores.
- Cache-first retrieval can extract regional monthly series from supported NASA
  grids, with provenance-bearing interval caches separate from curated demos.

## Remaining work and roadmap

LSTM bands, the discovery summary, and metric explanations are implemented;
18 frontend tests and the production build pass after handoff review. Real Chrome
desktop/mobile and console checks also pass. Real water-balance closure
cannot be evaluated until total runoff and compatible storage change exist.
BOCPD candidate dates are integrated into the default scouts and dashboard.
A 30-second demo video and 12-slide HTML/PDF pitch with notes are ready. Public hosting was skipped
at the user's request; public-URL acceptance is therefore not applicable yet.

Beyond the hackathon: independent anomaly benchmarks, causal sensitivity and
confounding studies, spatial/product uncertainty, additional datasets, and
region-level model attribution. Full machine-readable demo evidence is in
[demo-rehearsal.json](../reports/demo-rehearsal.json).

## Final release verification

195 backend tests plus 9 subtests, 18 frontend tests, and the production build
pass. The final Chrome check shows candidate regime dates and explicit missing
water-balance terms, with no console errors or mobile page overflow.
Water-balance calculations require mm/month terms, identical spatial bounds,
and identical consecutive monthly intervals. No missing interval is dropped.
`./scripts/demo.sh` starts or reuses the local production services.
