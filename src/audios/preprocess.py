"""Audio preprocessing pipeline for the mic recorder.

Two optional, composable stages applied to float32 mono audio in [-1, 1]:

1. ``_bandpass``: 4th-order Butterworth bandpass clamped to 80 Hz – 8 kHz.
   Removes low rumble (HVAC, mic stand vibration) and high hiss/whistle.
2. ``_denoise``: spectral gating via ``noisereduce`` in ``stationary=True``
   mode. Works well for constant background noise (fan, room tone, light
   street rumble). Less effective on non-stationary noise (chatter, music).

Sample rate is passed in; nothing here is global. All functions accept and
return the same numpy shape.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt


def preprocess_float32(
    audio_f32: np.ndarray,
    sr: int,
    *,
    bandpass: bool = True,
    denoise: bool = True,
) -> np.ndarray:
    """Apply the bandpass + (optional) noise-reduction pipeline."""
    if audio_f32.size == 0:
        return audio_f32
    out = audio_f32
    if bandpass:
        out = _bandpass(out, sr)
    if denoise:
        out = _denoise(out, sr)
    return out


def _bandpass(audio_f32: np.ndarray, sr: int, low_hz: float = 80.0, high_hz: float = 8000.0) -> np.ndarray:
    nyq = sr / 2.0
    low = max(low_hz / nyq, 1e-4)
    high = min(high_hz / nyq, 0.999)
    sos = butter(N=4, Wn=[low, high], btype="bandpass", output="sos")
    shape = audio_f32.shape
    filtered = sosfilt(sos, audio_f32.reshape(-1)).astype(np.float32)
    return filtered.reshape(shape)


def _denoise(audio_f32: np.ndarray, sr: int, *, stationary: bool = True) -> np.ndarray:
    import noisereduce as nr

    shape = audio_f32.shape
    flat = audio_f32.reshape(-1)
    reduced = nr.reduce_noise(y=flat, sr=sr, stationary=stationary).astype(np.float32)
    return reduced.reshape(shape)
