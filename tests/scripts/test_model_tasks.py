"""Tests for combined model task helpers."""

from __future__ import annotations

from scripts import model_tasks


def test_print_model_list_shows_whisper_and_llm_models(monkeypatch, capsys):
    monkeypatch.setattr(model_tasks.download_models, "configured_whisper_models", lambda: ["medium", "large-v3"])
    monkeypatch.setattr(model_tasks.ollama_models, "configured_llm_models", lambda: ["llama3.1:8b"])

    model_tasks.print_model_list()

    out = capsys.readouterr().out
    assert "Whisper speech models:" in out
    assert "medium" in out
    assert "large-v3" in out
    assert "Ollama LLM models:" in out
    assert "llama3.1:8b" in out


def test_download_all_models_runs_whisper_then_llm(monkeypatch):
    calls: list[str] = []

    def fake_whisper(argv: list[str]) -> int:
        calls.append(f"whisper:{argv}")
        return 0

    def fake_llm() -> int:
        calls.append("llm")
        return 0

    monkeypatch.setattr(model_tasks.download_models, "main", fake_whisper)
    monkeypatch.setattr(model_tasks.ollama_models, "download_configured_llm_models", fake_llm)

    assert model_tasks.download_all_models() == 0
    assert calls == ["whisper:[]", "llm"]


def test_download_all_models_stops_when_whisper_fails(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(model_tasks.download_models, "main", lambda argv: 9)
    monkeypatch.setattr(model_tasks.ollama_models, "download_configured_llm_models", lambda: calls.append("llm") or 0)

    assert model_tasks.download_all_models() == 9
    assert calls == []
