import numpy as np
import pytest
import pywt

from backend.analysis.wavelet import cwt_scalogram, dwt_decompose


@pytest.mark.parametrize("length", [255, 256])
def test_dwt_preserves_length_and_reconstructs_signal(length):
    t = np.arange(length)
    values = 0.01 * t + 2 * np.sin(2 * np.pi * t / 4)
    original = values.copy()
    trend, details = dwt_decompose(values)
    assert trend.shape == values.shape
    assert len(details) == 4
    approximation = pywt.wavedec(values, "db4", level=4)[0]
    np.testing.assert_allclose(pywt.waverec([approximation] + details, "db4")[:length], values, atol=1e-12)
    detail_signal = pywt.waverec([np.zeros_like(approximation)] + details, "db4")[:length]
    np.testing.assert_allclose(trend + detail_signal, values, atol=1e-12)
    assert np.std((trend - 0.01 * t)[32:-32]) < 0.02
    np.testing.assert_array_equal(values, original)


def test_constant_and_level_zero():
    trend, details = dwt_decompose(np.full(128, 7.))
    np.testing.assert_allclose(trend, 7, atol=1e-12)
    for detail in details: np.testing.assert_allclose(detail, 0, atol=1e-12)
    values = np.arange(5.)
    trend, details = dwt_decompose(values, level=0)
    np.testing.assert_array_equal(trend, values)
    assert details == []


def test_cwt_recovers_sinusoid_frequency_and_dt_units():
    dt, expected_frequency = 0.5, 0.125
    values = np.sin(2 * np.pi * expected_frequency * np.arange(512) * dt)
    scales = np.arange(2, 64)
    power, frequencies = cwt_scalogram(values, scales, dt)
    assert power.shape == (len(scales), len(values))
    assert np.isfinite(power).all() and (power >= 0).all()
    peak = frequencies[np.argmax(power[:, 128:-128].mean(axis=1))]
    assert peak == pytest.approx(expected_frequency, rel=0.09)
    power2, frequencies2 = cwt_scalogram(values, scales, 2 * dt)
    np.testing.assert_allclose(power2, power)
    np.testing.assert_allclose(frequencies2, frequencies / 2)


@pytest.mark.parametrize("values", [[], [1], [0, np.nan], [0, np.inf], [[1, 2]], [1j, 2j]])
def test_invalid_signal(values):
    with pytest.raises(ValueError): dwt_decompose(values)
    with pytest.raises(ValueError): cwt_scalogram(values, [1, 2], 1)


@pytest.mark.parametrize("level", [-1, 1.5, True, 12])
def test_invalid_dwt_level(level):
    with pytest.raises(ValueError): dwt_decompose(np.ones(128), level=level)


@pytest.mark.parametrize("scales", [[], [0, 1], [-1], [np.nan], [[1, 2]], [1j]])
def test_invalid_cwt_scales(scales):
    with pytest.raises(ValueError): cwt_scalogram(np.ones(128), scales, 1)


@pytest.mark.parametrize("dt", [0, -1, np.nan, np.inf, 1j])
def test_invalid_cwt_spacing(dt):
    with pytest.raises(ValueError): cwt_scalogram(np.ones(128), [1, 2], dt)
