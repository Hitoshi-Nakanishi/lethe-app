"""Tests for the Lethe audio preprocessing pipeline."""

from __future__ import annotations

import numpy as np

from audios.preprocess import preprocess_float32


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))


def test_empty_input_returned_unchanged():
    empty = np.zeros(0, dtype=np.float32)
    out = preprocess_float32(empty, 44100)
    assert out.size == 0


def test_shape_and_dtype_preserved():
    rng = np.random.default_rng(0)
    audio = (rng.standard_normal(44100) * 0.1).astype(np.float32)
    out = preprocess_float32(audio, 44100, bandpass=True, denoise=False)
    assert out.shape == audio.shape
    assert out.dtype == np.float32


def test_bandpass_attenuates_sub_80hz_rumble():
    sr = 44100
    t = np.arange(sr) / sr
    rumble = np.sin(2 * np.pi * 30.0 * t).astype(np.float32)  # 30 Hz, well below the cutoff
    out = preprocess_float32(rumble, sr, bandpass=True, denoise=False)
    assert _rms(out) < 0.3 * _rms(rumble)


def test_bandpass_keeps_speech_band_tone():
    sr = 44100
    t = np.arange(sr) / sr
    tone = (0.3 * np.sin(2 * np.pi * 1000.0 * t)).astype(np.float32)  # 1 kHz, inside the band
    out = preprocess_float32(tone, sr, bandpass=True, denoise=False)
    assert _rms(out) > 0.5 * _rms(tone)


def test_denoise_runs_and_preserves_shape():
    rng = np.random.default_rng(1)
    audio = (rng.standard_normal(16000) * 0.05).astype(np.float32)
    out = preprocess_float32(audio, 16000, bandpass=False, denoise=True)
    assert out.shape == audio.shape
    assert out.dtype == np.float32
