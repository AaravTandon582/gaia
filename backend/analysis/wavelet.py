"""Discrete multiscale decomposition and Morlet continuous wavelet power."""

import numpy as np
import pywt


def _signal_array(signal):
    if np.iscomplexobj(signal):
        raise ValueError("signal must be real-valued")
    values = np.asarray(signal, dtype=float)
    if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("signal must contain at least two finite values in one dimension")
    return values


def dwt_decompose(signal, wavelet="db4", level=4):
    """Return (trend, details) using symmetric signal extension.

    Trend is the reconstruction from the level-L approximation alone, cropped
    to the input length. Details are *downsampled coefficient arrays* ordered
    [cD_L, ..., cD_1], coarsest to finest. Level zero returns the original
    signal and no details. Levels above dwt_max_level are rejected rather than
    returning a decomposition in which every coefficient has boundary effects.
    """
    values = _signal_array(signal)
    if isinstance(level, bool) or not isinstance(level, (int, np.integer)) or level < 0:
        raise ValueError("level must be a nonnegative integer")
    wavelet = pywt.Wavelet(wavelet)
    max_level = pywt.dwt_max_level(len(values), wavelet.dec_len)
    if level > max_level:
        raise ValueError(f"level {level} exceeds maximum {max_level} for this signal/wavelet")
    coefficients = pywt.wavedec(values, wavelet, mode="symmetric", level=level)
    trend = pywt.waverec(
        [coefficients[0]] + [np.zeros_like(c) for c in coefficients[1:]],
        wavelet, mode="symmetric",
    )[:len(values)]
    return trend, [c.copy() for c in coefficients[1:]]


def cwt_scalogram(signal, scales, dt):
    """Return (abs(CWT)**2, frequencies) using the real Morlet wavelet.

    Power has shape (len(scales), len(signal)). Scales are positive sample-scale
    factors; frequencies are cycles per unit of dt (cycles/month if dt=1 month).
    Power is unnormalized wavelet magnitude squared, not a calibrated PSD.
    Finite-record edge effects are present; no cone-of-influence mask is applied.
    """
    values = _signal_array(signal)
    if np.iscomplexobj(scales):
        raise ValueError("scales must be real-valued")
    scales = np.asarray(scales, dtype=float)
    if scales.ndim != 1 or len(scales) == 0 or not np.isfinite(scales).all() or (scales <= 0).any():
        raise ValueError("scales must be a nonempty one-dimensional array of positive finite values")
    if not np.isscalar(dt) or np.iscomplexobj(dt) or not np.isfinite(dt) or dt <= 0:
        raise ValueError("dt must be a positive finite scalar")
    coefficients, frequencies = pywt.cwt(values, scales, "morl", sampling_period=dt)
    return np.abs(coefficients)**2, frequencies
