"""Tests for faster-whisper model fallback behavior."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

import llm.whisper_models as whisper_models
from llm.transcribe_final import transcribe_segments
from llm.transcribe_stream import StreamingTranscriber


@pytest.fixture(autouse=True)
def clear_model_cache():
    whisper_models._cache.clear()
    yield
    whisper_models._cache.clear()


def test_cuda_dependency_detection_matches_windows_cublas_error():
    exc = RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")

    assert whisper_models.is_cuda_dependency_error(exc)
    assert whisper_models.should_fallback_to_cpu("auto", exc)
    assert not whisper_models.should_fallback_to_cpu("cuda", exc)


def test_cuda_dependency_detection_ignores_unrelated_errors():
    assert not whisper_models.is_cuda_dependency_error(ValueError("bad audio"))


def test_auto_model_creation_falls_back_to_cpu(monkeypatch):
    calls: list[tuple[str, str, str]] = []

    class FakeWhisperModel:
        def __init__(self, model_size: str, *, device: str, compute_type: str) -> None:
            calls.append((model_size, device, compute_type))
            if device == "auto":
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
            self.device = device
            self.compute_type = compute_type

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeWhisperModel))

    model = whisper_models.get_whisper_model("base", "auto", "auto")

    assert model.device == "cpu"
    assert calls == [("base", "auto", "auto"), ("base", "cpu", "auto")]
    assert whisper_models._cache[("base", "auto", "auto")] is model


def test_streaming_transcriber_retries_chunk_on_cpu_fallback(monkeypatch):
    seen: list[tuple[str, int, str]] = []
    transcriber = StreamingTranscriber(seen.append, source_sr=16000, device="auto")

    class BrokenModel:
        def transcribe(self, _audio, **_kwargs):
            raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")

    class WorkingModel:
        def transcribe(self, _audio, **_kwargs):
            return [SimpleNamespace(text="fallback text")], None

    transcriber._model = BrokenModel()
    monkeypatch.setattr(transcriber, "_load_cpu_fallback_model", lambda: WorkingModel())

    transcriber._transcribe(np.zeros(16000, dtype=np.float32))

    assert seen == [("live", 0, "fallback text")]


def test_download_model_cancellation_raises(monkeypatch):
    from huggingface_hub import snapshot_download as _real_snapshot_download

    def fake_snapshot_download(*, tqdm_class, **_kwargs):
        # Simulate huggingface_hub's tqdm-driven loop: instantiate a progress
        # bar and tick it. cancel_download() flips the event, so the next
        # update() must raise ModelDownloadCancelled instead of running to
        # completion.
        bar = tqdm_class(total=10)
        whisper_models.cancel_download("fake-model")
        try:
            bar.update(1)
        finally:
            bar.close()

    import huggingface_hub

    monkeypatch.setattr(whisper_models, "is_model_cached", lambda _model_size: False)
    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_snapshot_download)

    with pytest.raises(whisper_models.ModelDownloadCancelled):
        whisper_models.download_model("fake-model")
    # Cancellation event should be cleared so a retry can begin fresh.
    assert "fake-model" not in whisper_models._cancel_events
    # Sanity that the real symbol was patched, not just a different attribute.
    assert _real_snapshot_download is not None


def test_final_transcribe_retries_on_cpu_fallback(monkeypatch):
    class BrokenModel:
        def transcribe(self, _audio, **_kwargs):
            raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")

    class WorkingModel:
        def transcribe(self, _audio, **_kwargs):
            segment = SimpleNamespace(start=0.0, end=1.2, text="fallback text")
            info = SimpleNamespace(duration=1.2)
            return [segment], info

    monkeypatch.setattr("llm.transcribe_final.get_whisper_model", lambda *_args: BrokenModel())
    monkeypatch.setattr("llm.transcribe_final.get_cpu_fallback_model", lambda *_args: WorkingModel())

    out = transcribe_segments(np.zeros(16000, dtype=np.float32), device="auto")

    assert out == [(0.0, 1.2, "fallback text")]
