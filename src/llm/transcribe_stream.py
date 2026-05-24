"""Realtime-style transcription via faster-whisper.

Not true streaming ASR. Audio is buffered and transcribed in fixed-length
windows, so the user-visible latency is roughly ``chunk_seconds`` plus the
model's inference time. ``vad_filter=True`` keeps silence from producing
hallucinated text.

Threading model:
- ``feed_int16`` is safe to call from any thread (e.g. the PortAudio
  callback). It only enqueues a copy of the audio chunk.
- A single worker thread loads the Whisper model and processes the queue.
- Transcribed text is emitted via the ``on_text`` callback. ``on_text``
  runs on the worker thread; the caller is responsible for marshaling to
  the UI thread if needed.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from math import gcd
from typing import Any

import numpy as np

TARGET_SR = 16000

# Permissive VAD: lower threshold + more padding so short utterances and
# soft speech aren't dropped. faster-whisper's defaults (threshold=0.5,
# silence=2000ms, pad=400ms) are tuned for noisy podcast audio and cut
# more aggressively than we want for meetings.
VAD_PARAMS = {
    "threshold": 0.35,
    "min_silence_duration_ms": 1000,
    "speech_pad_ms": 600,
}


def format_initial_prompt(notes: str) -> str | None:
    """Turn freeform notes into a directive ``initial_prompt`` for Whisper.

    Whisper caps the prompt at ~224 tokens, so we trim to the last 800
    characters and frame it as an authoritative-spelling instruction --
    that biases decoding more strongly than dumping raw notes verbatim.
    """
    if not notes:
        return None
    text = notes.strip()
    if not text:
        return None
    framed = f"以下の用語は正しい表記としてそのまま使ってください: {text}"
    return framed[-800:]


def resample_to_16k(audio_f32: np.ndarray, source_sr: int) -> np.ndarray:
    """Resample float32 audio to 16 kHz (Whisper's native input rate)."""
    if source_sr == TARGET_SR:
        return audio_f32
    from scipy.signal import resample_poly

    g = gcd(TARGET_SR, source_sr)
    return resample_poly(audio_f32, TARGET_SR // g, source_sr // g).astype(np.float32)


class StreamingTranscriber:
    def __init__(
        self,
        on_text: Callable[[str], None],
        *,
        model_size: str = "base",
        language: str = "ja",
        source_sr: int = 44100,
        chunk_seconds: float = 5.0,
        device: str = "auto",
        compute_type: str = "auto",
        prompt_provider: Callable[[], str] | None = None,
        preprocessor: Callable[[np.ndarray, int], np.ndarray] | None = None,
    ) -> None:
        self._on_text = on_text
        self._model_size = model_size
        self._language = language
        self._source_sr = source_sr
        self._chunk_seconds = chunk_seconds
        self._device = device
        self._compute_type = compute_type
        self._prompt_provider = prompt_provider
        self._preprocessor = preprocessor
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._model: Any | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def feed_int16(self, audio: np.ndarray) -> None:
        if self._thread is None:
            return
        self._queue.put(audio.copy())

    def stop(self, timeout: float = 30.0) -> None:
        if self._thread is None:
            return
        self._queue.put(None)
        self._thread.join(timeout=timeout)
        self._thread = None

    def _load_model(self):
        from llm.whisper_models import get_whisper_model

        return get_whisper_model(self._model_size, self._device, self._compute_type)

    def _load_cpu_fallback_model(self):
        from llm.whisper_models import get_cpu_fallback_model

        return get_cpu_fallback_model(self._model_size, self._device, self._compute_type)

    def _run(self) -> None:
        try:
            self._model = self._load_model()
        except Exception as exc:
            self._on_text(f"[error loading whisper model: {exc}]")
            return

        chunk_samples = int(self._chunk_seconds * self._source_sr)
        min_flush_samples = self._source_sr // 2
        buf = np.zeros(0, dtype=np.float32)
        stopping = False

        while True:
            item = self._queue.get()
            if item is None:
                stopping = True
            else:
                f32 = item.astype(np.float32).flatten() / 32768.0
                buf = np.concatenate([buf, f32])

            while len(buf) >= chunk_samples or (stopping and len(buf) >= min_flush_samples):
                take = min(chunk_samples, len(buf))
                chunk = buf[:take]
                buf = buf[take:]
                self._transcribe(chunk)

            if stopping:
                return

    def _current_prompt(self) -> str | None:
        if self._prompt_provider is None:
            return None
        try:
            notes = self._prompt_provider() or ""
        except Exception:
            return None
        return format_initial_prompt(notes)

    def _transcribe(self, audio_f32: np.ndarray) -> None:
        try:
            if self._preprocessor is not None:
                try:
                    audio_f32 = self._preprocessor(audio_f32, self._source_sr)
                except Exception as exc:
                    self._on_text(f"[preprocess error: {exc}]")
            resampled = resample_to_16k(audio_f32, self._source_sr)
            kwargs: dict = {
                "language": self._language,
                "vad_filter": True,
                "vad_parameters": VAD_PARAMS,
            }
            prompt = self._current_prompt()
            if prompt:
                kwargs["initial_prompt"] = prompt
            text = self._transcribe_with_loaded_model(resampled, kwargs)
            if text:
                self._on_text(text)
        except Exception as exc:
            from llm.whisper_models import should_fallback_to_cpu

            if should_fallback_to_cpu(self._device, exc):
                try:
                    self._model = self._load_cpu_fallback_model()
                    text = self._transcribe_with_loaded_model(resampled, kwargs)
                    if text:
                        self._on_text(text)
                    return
                except Exception as fallback_exc:
                    exc = fallback_exc
            self._on_text(f"[transcribe error: {exc}]")

    def _transcribe_with_loaded_model(self, audio: np.ndarray, kwargs: dict) -> str:
        model = self._model
        if model is None:
            raise RuntimeError("Whisper model is not loaded")
        segments, _ = model.transcribe(audio, **kwargs)
        return " ".join(s.text.strip() for s in segments).strip()
