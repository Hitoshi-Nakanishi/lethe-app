"""Process-wide cache of loaded faster-whisper models.

Constructing a ``WhisperModel`` loads weights from disk (kotoba-whisper is
~1.5 GB) and takes several seconds. The recorder GUI transcribes
repeatedly, so each ``(model, device, compute_type)`` instance is kept
resident and the same object is handed back on later calls.

A ``WhisperModel`` is safe to reuse across sequential ``transcribe()``
calls. The GUI never runs two transcriptions at once -- the live preview
and the HQ pass are sequential -- so one cached instance per key is fine.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_cache: dict[tuple[str, str, str], object] = {}


def get_whisper_model(model_size: str, device: str = "auto", compute_type: str = "auto"):
    """Return a cached WhisperModel, constructing it on first request."""
    key = (model_size, device, compute_type)
    with _lock:
        model = _cache.get(key)
        if model is None:
            from faster_whisper import WhisperModel

            model = WhisperModel(model_size, device=device, compute_type=compute_type)
            _cache[key] = model
        return model
