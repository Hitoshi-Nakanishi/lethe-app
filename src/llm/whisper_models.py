"""Process-wide cache of loaded faster-whisper models.

Constructing a ``WhisperModel`` loads weights from disk (large-v3 is
~3 GB) and takes several seconds. The recorder GUI transcribes
repeatedly, so each ``(model, device, compute_type)`` instance is kept
resident and the same object is handed back on later calls.

A ``WhisperModel`` is safe to reuse across sequential ``transcribe()``
calls. The GUI never runs two transcriptions at once -- the live preview
and the HQ pass are sequential -- so one cached instance per key is fine.

The module also publishes a small catalog of selectable Whisper models
with their on-disk size, peak RAM and a relative quality/speed score, so
the UI can show what each option costs before the user commits to a
download.
"""

from __future__ import annotations

import threading
from pathlib import Path

_lock = threading.Lock()
_cache: dict[tuple[str, str, str], object] = {}

# Cancellation flags keyed by model id so a UI Cancel button can abort an
# in-flight first-time download. The flag is set by the GUI and observed by
# the tqdm subclass used during ``snapshot_download``.
_cancel_events: dict[str, threading.Event] = {}
_cancel_lock = threading.Lock()


class ModelDownloadCancelled(RuntimeError):
    """Raised inside the download thread when the user cancels."""


# (model size, approx. on-disk gigabytes, approx. peak RAM gigabytes, quality 1-5, speed 1-5, short note)
# Numbers are rounded estimates for the f32 CTranslate2 builds shipped by
# Systran on Hugging Face. RAM is the working-set the model reaches during a
# beam-search decode; multiply by ~1.5 for safety headroom.
MODEL_CATALOG: list[dict] = [
    {
        "id": "tiny",
        "label": "tiny",
        "disk_gb": 0.08,
        "ram_gb": 1.0,
        "quality": 1,
        "speed": 5,
        "note": "最速・最小。短いメモ用。",
        "note_en": "Fastest, smallest. Quick notes only.",
    },
    {
        "id": "base",
        "label": "base",
        "disk_gb": 0.15,
        "ram_gb": 1.2,
        "quality": 2,
        "speed": 5,
        "note": "軽量。雑音の少ない英語向け。",
        "note_en": "Light. Best for clean English audio.",
    },
    {
        "id": "small",
        "label": "small",
        "disk_gb": 0.5,
        "ram_gb": 2.0,
        "quality": 3,
        "speed": 4,
        "note": "バランス型。短い日本語にも実用的。",
        "note_en": "Balanced. Usable for short Japanese clips.",
    },
    {
        "id": "medium",
        "label": "medium",
        "disk_gb": 1.5,
        "ram_gb": 5.0,
        "quality": 4,
        "speed": 3,
        "note": "ライブ転写の既定。日本語の実用品質。",
        "note_en": "Default for live transcripts; usable Japanese quality.",
    },
    {
        "id": "large-v3",
        "label": "large-v3",
        "disk_gb": 3.0,
        "ram_gb": 10.0,
        "quality": 5,
        "speed": 1,
        "note": "高精度の既定。日本語の最高品質。",
        "note_en": "Default for HQ. Highest Japanese quality.",
    },
    {
        "id": "large-v3-turbo",
        "label": "large-v3-turbo",
        "disk_gb": 1.6,
        "ram_gb": 6.0,
        "quality": 4,
        "speed": 4,
        "note": "large-v3 並の精度を高速化。RAM が許せば最良の選択。",
        "note_en": "Near-large-v3 quality, much faster. Best when RAM allows.",
    },
]

_CATALOG_BY_ID: dict[str, dict] = {entry["id"]: entry for entry in MODEL_CATALOG}


def model_info(model_size: str) -> dict | None:
    """Return the catalog entry for ``model_size``, or ``None`` if unknown."""
    return _CATALOG_BY_ID.get(model_size)


def _hf_repo_id(model_size: str) -> str:
    """Map a faster-whisper model size to the Hugging Face repo it downloads."""
    try:
        from faster_whisper.utils import _MODELS  # type: ignore[attr-defined]
    except Exception:
        _MODELS = {}
    return _MODELS.get(model_size, f"Systran/faster-whisper-{model_size}")


def hf_cache_folder(model_size: str) -> Path:
    """Where huggingface_hub stores the snapshot for ``model_size``."""
    repo_id = _hf_repo_id(model_size)
    folder = "models--" + repo_id.replace("/", "--")
    return Path.home() / ".cache" / "huggingface" / "hub" / folder


def is_model_cached(model_size: str) -> bool:
    """True when the Whisper snapshot for ``model_size`` is already on disk.

    faster-whisper checks the same directory; we look here so the UI can warn
    *before* a transcription kicks off a multi-gigabyte download.
    """
    return hf_cache_folder(model_size).exists()


def cancel_download(model_size: str) -> None:
    """Signal an in-flight ``download_model`` call for ``model_size`` to abort."""
    with _cancel_lock:
        event = _cancel_events.get(model_size)
    if event is not None:
        event.set()


def _take_cancel_event(model_size: str) -> threading.Event:
    """Replace and return the cancel event for ``model_size``."""
    with _cancel_lock:
        event = threading.Event()
        _cancel_events[model_size] = event
        return event


def _clear_cancel_event(model_size: str, event: threading.Event) -> None:
    with _cancel_lock:
        if _cancel_events.get(model_size) is event:
            _cancel_events.pop(model_size, None)


def _make_cancellable_tqdm(event: threading.Event):
    """tqdm subclass that aborts download progress when ``event`` is set."""
    from tqdm import tqdm as _base_tqdm

    class _CancellableTqdm(_base_tqdm):
        def update(self, n: int = 1) -> bool | None:
            if event.is_set():
                raise ModelDownloadCancelled("download cancelled by user")
            return super().update(n)

        def refresh(self, *args, **kwargs):
            if event.is_set():
                raise ModelDownloadCancelled("download cancelled by user")
            return super().refresh(*args, **kwargs)

    return _CancellableTqdm


def download_model(model_size: str) -> None:
    """Pre-fetch the Whisper snapshot for ``model_size``.

    Cancellable by ``cancel_download(model_size)``. Raises
    ``ModelDownloadCancelled`` when the user aborts.
    """
    if is_model_cached(model_size):
        return
    from huggingface_hub import snapshot_download

    event = _take_cancel_event(model_size)
    try:
        snapshot_download(
            repo_id=_hf_repo_id(model_size),
            allow_patterns=["*.bin", "*.json", "*.txt", "*.model"],
            tqdm_class=_make_cancellable_tqdm(event),
        )
    finally:
        _clear_cancel_event(model_size, event)


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
