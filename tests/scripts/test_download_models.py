"""Tests for the model download task helper."""

from __future__ import annotations

from scripts import download_models


def test_configured_whisper_models_deduplicates_live_and_final_models():
    config = {
        "whisper_live_model": "medium",
        "whisper_final_model": "medium",
    }

    assert download_models.configured_whisper_models(config) == ["medium"]


def test_main_downloads_explicit_models(monkeypatch):
    seen: list[tuple[str, str, str]] = []

    def fake_download(model: str, *, device: str, compute_type: str) -> None:
        seen.append((model, device, compute_type))

    monkeypatch.setattr(download_models, "download_whisper_model", fake_download)

    rc = download_models.main(["--device", "cpu", "--compute-type", "int8", "base", "small"])

    assert rc == 0
    assert seen == [("base", "cpu", "int8"), ("small", "cpu", "int8")]
