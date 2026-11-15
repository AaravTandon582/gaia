"""Log-space Bayesian online changepoint detection with a Gaussian NIG model."""

import numpy as np
from scipy.special import logsumexp
from scipy.stats import t as student_t


class BOCPD:
    """Adams-MacKay run-length filtering and candidate boundary extraction.

    ``hazard_lambda`` is the expected regime duration in observations (>1).
    Normal-Inverse-Gamma hyperparameters describe the prior mean/variance.
    Choose them in the units of the input (standardized data is often useful).

    ``detect`` returns ``(changepoints, posterior)``. Posterior shape is
    ``(T+1, T+1)``: row t follows t observations, column r is run length r,
    with posterior[0, 0] = 1. Changepoints are zero-based indices of the first
    observation of candidate new regimes, not the later detection time.

    With a constant hazard, P(r=0) equals that hazard. Boundaries are therefore
    extracted from drops in the positive MAP run length, requiring posterior
    mass >= ``threshold`` for shorter runs. ``min_run_length`` suppresses
    startup/closely spaced detections. These are tunable heuristic decisions,
    not significance tests. Batch detection uses O(T^2) time and memory.
    """

    def __init__(self, hazard_lambda=200, mu0=0., kappa0=1., alpha0=1., beta0=1.,
                 *, min_run_length=5, threshold=0.5):
        parameters = [hazard_lambda, mu0, kappa0, alpha0, beta0, threshold]
        if not all(np.isscalar(p) and np.isfinite(p) for p in parameters):
            raise ValueError("BOCPD parameters must be finite scalars")
        if hazard_lambda <= 1 or min(kappa0, alpha0, beta0) <= 0:
            raise ValueError("hazard_lambda must exceed 1; kappa0, alpha0, beta0 must be positive")
        if not 0 < threshold <= 1:
            raise ValueError("threshold must lie in (0, 1]")
        if isinstance(min_run_length, bool) or not isinstance(min_run_length, (int, np.integer)) or min_run_length < 1:
            raise ValueError("min_run_length must be a positive integer")
        self.lam = float(hazard_lambda)
        self.mu0, self.kappa0, self.alpha0, self.beta0 = map(float, (mu0, kappa0, alpha0, beta0))
        self.min_run_length, self.threshold = int(min_run_length), float(threshold)
        self.reset()

    def reset(self):
        """Reset filtering state; each call to detect starts independently."""
        self.log_R = np.array([0.])
        self.R = np.array([1.])
        self.mu, self.kappa = np.array([self.mu0]), np.array([self.kappa0])
        self.alpha, self.beta = np.array([self.alpha0]), np.array([self.beta0])
        self.t, self._previous_map = 0, 0
        self.changepoints, self.run_lengths = [], []

    def update(self, x):
        """Consume one finite real observation and return positive MAP run length."""
        if not np.isscalar(x) or np.iscomplexobj(x) or not np.isfinite(x):
            raise ValueError("x must be a finite real scalar")
        x = float(x)
        scale = np.sqrt(self.beta * (self.kappa + 1) / (self.alpha * self.kappa))
        log_predictive = student_t.logpdf(x, df=2 * self.alpha, loc=self.mu, scale=scale)
        log_joint = self.log_R + log_predictive
        hazard = 1 / self.lam
        new_log_R = np.concatenate((
            [logsumexp(log_joint) + np.log(hazard)],
            log_joint + np.log1p(-hazard),
        ))
        normalization = logsumexp(new_log_R)
        if not np.isfinite(normalization):
            raise ValueError("Predictive distribution overflowed; rescale the input")
        new_kappa = self.kappa + 1
        delta = x - self.mu
        new_mu = self.mu + delta / new_kappa
        new_beta = self.beta + 0.5 * (self.kappa / new_kappa) * delta**2
        if not np.isfinite(new_beta).all():
            raise ValueError("Variance update overflowed; rescale the input")
        self.log_R = new_log_R - normalization
        self.R = np.exp(self.log_R)
        self.mu = np.concatenate(([self.mu0], new_mu))
        self.kappa = np.concatenate(([self.kappa0], new_kappa))
        self.alpha = np.concatenate(([self.alpha0], self.alpha + 0.5))
        self.beta = np.concatenate(([self.beta0], new_beta))
        self.t += 1
        # r=0 is data-independent under this constant-hazard recursion.
        run_length = int(np.argmax(self.R[1:]) + 1)
        boundary = self.t - run_length
        last_boundary = self.changepoints[-1] if self.changepoints else 0
        shorter_mass = self.R[1:self._previous_map].sum() / (1 - self.R[0])
        if (run_length < self._previous_map
                and self._previous_map >= self.min_run_length
                and shorter_mass >= self.threshold
                and boundary - last_boundary >= self.min_run_length):
            self.changepoints.append(boundary)
        self._previous_map = run_length
        self.run_lengths.append(run_length)
        return run_length

    def detect(self, timeseries):
        """Return candidate changepoint indices and the complete posterior matrix."""
        if np.iscomplexobj(timeseries):
            raise ValueError("timeseries must be real-valued")
        values = np.asarray(timeseries, dtype=float)
        if values.ndim != 1 or not np.isfinite(values).all():
            raise ValueError("timeseries must be a finite one-dimensional array")
        self.reset()
        posterior = np.zeros((len(values) + 1, len(values) + 1))
        posterior[0, 0] = 1.
        for t, value in enumerate(values, start=1):
            self.update(value)
            posterior[t, :t + 1] = self.R
        return self.changepoints.copy(), posterior
