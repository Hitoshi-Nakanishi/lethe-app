"""Process-wide cache of loaded faster-whisper models.

Constructing a ``WhisperModel`` loads weights from disk (large-v3 is
~3 GB) and takes several seconds. The recorder GUI transcribes
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

_CUDA_ERROR_MARKERS = (
    "cublas",
    "cudart",
    "cudnn",
    "cuda driver",
    "cuda runtime",
    "cuda failed",
    "cuda error",
)


def is_cuda_dependency_error(exc: BaseException) -> bool:
    """True when an exception looks like a missing or unusable CUDA runtime."""
    seen: set[int] = set()
    pending: list[BaseException | None] = [exc]
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        blob = f"{type(current).__name__} {current}".lower()
        if any(marker in blob for marker in _CUDA_ERROR_MARKERS):
            return True
        pending.extend((current.__cause__, current.__context__))
    return False


def should_fallback_to_cpu(device: str, exc: BaseException) -> bool:
    """Only auto device selection may silently fall back to CPU."""
    return device == "auto" and is_cuda_dependency_error(exc)


def _cpu_compute_type(compute_type: str) -> str:
    """Return a compute type that is valid when the fallback target is CPU."""
    if compute_type in {"float16", "bfloat16"}:
        return "float32"
    return compute_type


def _construct_model(model_size: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model_size, device=device, compute_type=compute_type)


def _get_or_create_unlocked(model_size: str, device: str, compute_type: str):
    key = (model_size, device, compute_type)
    model = _cache.get(key)
    if model is None:
        model = _construct_model(model_size, device, compute_type)
        _cache[key] = model
    return model


def get_cpu_fallback_model(model_size: str, requested_device: str, requested_compute_type: str):
    """Return a CPU model and alias the original auto key to it."""
    cpu_compute_type = _cpu_compute_type(requested_compute_type)
    with _lock:
        model = _get_or_create_unlocked(model_size, "cpu", cpu_compute_type)
        if requested_device == "auto":
            _cache[(model_size, requested_device, requested_compute_type)] = model
        return model


def get_whisper_model(model_size: str, device: str = "auto", compute_type: str = "auto"):
    """Return a cached WhisperModel, constructing it on first request."""
    key = (model_size, device, compute_type)
    with _lock:
        model = _cache.get(key)
        if model is None:
            try:
                model = _construct_model(model_size, device, compute_type)
            except Exception as exc:
                if should_fallback_to_cpu(device, exc):
                    model = _get_or_create_unlocked(model_size, "cpu", _cpu_compute_type(compute_type))
                else:
                    raise
            _cache[key] = model
        return model
