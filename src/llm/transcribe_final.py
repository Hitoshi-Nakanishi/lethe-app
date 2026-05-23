"""One-shot high-accuracy transcription via faster-whisper.

Unlike ``transcribe_stream`` (a 5-second chunked live *preview*), this
transcribes the whole clip in a single pass: Whisper sees full 30s windows
with context instead of isolated 5s slices, so words are no longer clipped
at chunk boundaries. Slower, but much more accurate -- intended to run
once, on a worker thread.

``audio`` may be a file path (any ffmpeg-decodable format) or a 1-D float32
numpy array. For a path with no preprocessor, faster-whisper decodes the
file itself, which keeps memory flat for long recordings.

``transcribe_segments`` returns ``(start, end, text)`` tuples so callers
can show per-segment timestamps and offer click-to-seek playback;
``segments_to_text`` flattens them for export or LLM post-processing.

The default model is kotoba-whisper-v2.0, a Japanese-specialised distilled
Whisper. Because it is distilled, ``condition_on_previous_text`` is left
off: distilled decoders are prone to repetition loops when conditioned on
their own previous output.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

from llm.transcribe_stream import resample_to_16k
from llm.whisper_models import get_whisper_model

DEFAULT_MODEL = "kotoba-tech/kotoba-whisper-v2.0-faster"

Segment = tuple[float, float, str]


def transcribe_segments(
    audio: str | Path | np.ndarray,
    source_sr: int = 16000,
    *,
    model_size: str = DEFAULT_MODEL,
    language: str = "ja",
    beam_size: int = 10,
    compute_type: str = "float32",
    device: str = "auto",
    initial_prompt: str | None = None,
    preprocessor: Callable[[np.ndarray, int], np.ndarray] | None = None,
    progress_callback: Callable[[float], None] | None = None,
) -> list[Segment]:
    """Transcribe a whole clip in one pass and return timestamped segments.

    ``progress_callback`` receives a 0.0-1.0 fraction as segments complete.
    ``source_sr`` is only used when ``audio`` is a numpy array.
    """
    model = get_whisper_model(model_size, device, compute_type)
    audio_input = _resolve_audio(audio, source_sr, preprocessor)
    if audio_input is None:
        return []

    kwargs: dict = {
        "language": language,
        "beam_size": beam_size,
        "condition_on_previous_text": False,
        "vad_filter": True,
    }
    if initial_prompt and initial_prompt.strip():
        kwargs["initial_prompt"] = initial_prompt.strip()[-800:]

    segments, info = model.transcribe(audio_input, **kwargs)
    duration = float(getattr(info, "duration", 0.0) or 0.0)
    out: list[Segment] = []
    for seg in segments:
        piece = seg.text.strip()
        if piece:
            out.append((float(seg.start), float(seg.end), piece))
        if progress_callback is not None and duration > 0:
            progress_callback(min(seg.end / duration, 1.0))
    if progress_callback is not None:
        progress_callback(1.0)
    return out


def format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS, or H:MM:SS once past an hour."""
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def segments_to_text(segments: list[Segment], *, timestamps: bool = True) -> str:
    """Join segments into one transcript string, one segment per line."""
    if timestamps:
        return "\n".join(f"[{format_timestamp(start)}] {text}" for start, _end, text in segments).strip()
    return " ".join(text for _start, _end, text in segments).strip()


def _resolve_audio(
    audio: str | Path | np.ndarray,
    source_sr: int,
    preprocessor: Callable[[np.ndarray, int], np.ndarray] | None,
) -> str | np.ndarray | None:
    """Return what model.transcribe() should receive: a path str or a 16 kHz array."""
    if isinstance(audio, (str, Path)):
        if preprocessor is None:
            # Let faster-whisper decode the file itself (lowest memory).
            return str(audio)
        from faster_whisper.audio import decode_audio

        decoded = np.asarray(decode_audio(str(audio), sampling_rate=16000), dtype=np.float32).reshape(-1)
        return preprocessor(decoded, 16000).reshape(-1).astype(np.float32)

    arr = np.asarray(audio, dtype=np.float32).reshape(-1)
    if arr.size == 0:
        return None
    if preprocessor is not None:
        arr = preprocessor(arr, source_sr).reshape(-1).astype(np.float32)
    return resample_to_16k(arr, source_sr)
