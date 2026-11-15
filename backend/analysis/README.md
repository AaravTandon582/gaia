# Time series analysis

Install `backend/requirements-dev.txt` and run from the repository root:

```bash
python -m pytest backend/analysis/tests -q
```

The local Anaconda interpreter (`/opt/anaconda3/bin/python`) has these dependencies.

## Interfaces

- `analyze_trend(timeseries, dates, alpha=0.05)` returns a dictionary containing
  `deseasonalized`, `slope`, `p_value`, `r_squared`, `confidence_interval_95`,
  `mann_kendall` (complete test statistics), `mk_trend`, `mk_p`, `sens_slope`,
  `is_significant`, and `verdict`. Input must contain at least 24 finite values
  at consecutive monthly dates. Seasonal adjustment subtracts the estimated
  additive seasonal component, retaining the trend and residual noise. OLS and
  Sen slopes are per month. Significance is based on original Mann-Kendall;
  autocorrelated residuals require a dependence-aware test before scientific
  claims. No automatic interpolation or date sorting is performed.
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
