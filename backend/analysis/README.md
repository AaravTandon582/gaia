# Time series analysis

Install `backend/requirements-dev.txt` and run from the repository root:

```bash
python -m pytest backend/analysis/tests -q
```

The local Anaconda interpreter (`/opt/anaconda3/bin/python`) has these dependencies.

## Interfaces

- `validate_water_balance(precip, et, runoff, delta_storage)` returns
  `mean_residual` (signed mean of P - ET - Q - dS), `mean_relative_error`
  (mean absolute residual divided by absolute precipitation, as a fraction),
  and a plain-English `interpretation`, without a pass/fail threshold.
  All four physical inputs must cover the same region/intervals and use matching
  units (all rates or all interval totals). `delta_storage` is a change, not a
  storage stock. Do not use standardized causal anomalies for this calculation.
  Zero-precipitation intervals remain in the mean residual but are excluded
  from relative error; when all precipitation is zero, relative error is None.
  None, empty arrays, or nonfinite observations return the literal string
  `"inputs unavailable"`. No missing term is replaced with zero.
  The current cache has P/ET for Amazon, Mediterranean, and Sahel, but no runoff
  or complete storage-change series. Shallow soil moisture (Amazon,
  Mediterranean, California) and Arctic snow mass are only partial storage
  components. Consequently no real cached water-balance residual is computed.
- `compute_transfer_entropy(source, target, lag=1, history_len=2, k=5)` estimates
  conditional mutual information in nats using the KSG neighbor-count formula
  and Chebyshev distance. For target time t, target history is t-1 through t-h,
  and source history is t-lag through t-lag-h+1. Radius queries are batched;
  marginal counts exclude self and use distances strictly below the joint
  k-neighbor radius. Finite-sample estimates can be negative and are not clipped.
  Inputs must be aligned finite anomalies; insufficient samples or zero joint
  k-neighbor distances (repeated embeddings) raise ValueError.
  `transfer_entropy_significance(...)` adds a one-sided `te_p` from exactly 200
  nonzero circular source shifts, with replacement, using seed 0 by default:
  `(1 + count(surrogate >= observed)) / 201`. The target stays fixed.
  The causal pipeline supplies its existing preprocessed matrix only for
  FDR-surviving links; TE is an additive diagnostic, not another link filter.
- `analyze_trend(timeseries, dates, alpha=0.05)` returns a dictionary containing
  `deseasonalized`, `slope`, `p_value`, `r_squared`, `confidence_interval_95`,
  `mann_kendall` (complete test statistics), `mk_trend`, `mk_p`, `sens_slope`,
  `is_significant`, and `verdict`. Input must contain at least 24 finite values
  at consecutive monthly dates. Seasonal adjustment subtracts the estimated
  additive seasonal component, retaining the trend and residual noise. OLS and
  Sen slopes are per month. OLS uses the deseasonalized series; significance
  currently uses Hamed–Rao modified Mann–Kendall on raw monthly values, with a
  constant/seasonal-only special case. No automatic interpolation or date
  sorting is performed.
- `BOCPD(...).detect(timeseries)` returns `(changepoints, posterior)`.
  `posterior[t, r]` is the probability of run length r after t observations,
  including the initial prior row. Shape is `(T+1, T+1)`. Indices mark the first
  observation of a candidate new regime. A Normal-Inverse-Gamma prior yields
  Student-t predictive densities; filtering uses log probabilities for numerical
  stability. A constant hazard makes P(r=0) constant, so supported drops in
  positive MAP run length identify candidate boundaries. The threshold and
  minimum run length are heuristic settings, not statistical significance.
  `update(x)` supports streaming; `detect` resets state each call. Seasonal
  signals should be adjusted before interpreting changes as regime shifts.
- `dwt_decompose(signal, wavelet='db4', level=4)` returns `(trend, details)`;
  trend has the original input length, and details contain downsampled
  `[cD_level, ..., cD_1]` coefficients. Symmetric extension is used. Excessive
  levels are rejected with the maximum supported level in the error message.
- `cwt_scalogram(signal, scales, dt)` returns `(power, frequencies)` for the
  real Morlet wavelet. Shape is `(n_scales, n_samples)`; frequencies are in
  cycles per unit of `dt`. Power is squared coefficient magnitude, not a
  normalized power spectral density. Edges have finite-record artifacts.

Arrays remain NumPy arrays; convert them to lists when serializing to JSON.

## References

- [statsmodels seasonal decomposition](https://www.statsmodels.org/stable/generated/statsmodels.tsa.seasonal.seasonal_decompose.html)
- [pyMannKendall source and test definitions](https://github.com/mmhs013/pyMannKendall)
- [Adams & MacKay, Bayesian Online Changepoint Detection](https://arxiv.org/abs/0710.3742)
- [PyWavelets multilevel DWT](https://pywavelets.readthedocs.io/en/latest/regression/multilevel.html)
- [PyWavelets continuous wavelet transform](https://pywavelets.readthedocs.io/en/latest/ref/cwt.html)

## Regional water balance

`region_water_balances(discoveries)` is included in the final scan response as
`water_balance`. Current cached regions report missing total runoff/storage
terms. Future complete inputs must explicitly use `mm/month`, share spatial
bounds, and cover identical consecutive months with finite values. Different
orders are aligned by date; gaps, duplicate months, incompatible units, and
nonfinite observations produce an unavailable result. Unit conversions and
confirmation of total runoff/storage semantics must happen before this function.
