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
    monkeypatch.setattr(model_tasks.ollama_models, "download_llm_models", fake_llm)

    assert model_tasks.download_all_models() == 0
    assert calls == ["whisper:[]", "llm"]


def test_download_all_models_stops_when_whisper_fails(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(model_tasks.download_models, "main", lambda argv: 9)
    monkeypatch.setattr(model_tasks.ollama_models, "download_llm_models", lambda: calls.append("llm") or 0)

    assert model_tasks.download_all_models() == 9
    assert calls == []


def test_main_without_command_lists_models(monkeypatch, capsys):
    monkeypatch.setattr(model_tasks.download_models, "configured_whisper_models", lambda: ["medium"])
    monkeypatch.setattr(model_tasks.ollama_models, "configured_llm_models", lambda: ["llama3.1:8b"])

    assert model_tasks.main([]) == 0

    out = capsys.readouterr().out
    assert "medium" in out
    assert "llama3.1:8b" in out


def test_main_whisper_download_passes_models(monkeypatch):
    seen: list[list[str]] = []

    def fake_whisper(argv: list[str]) -> int:
        seen.append(argv)
        return 0

    monkeypatch.setattr(model_tasks.download_models, "main", fake_whisper)

    assert model_tasks.main(["whisper", "medium", "large-v3"]) == 0
    assert seen == [["medium", "large-v3"]]


def test_main_llm_download_passes_models(monkeypatch):
    seen: list[list[str] | None] = []

    def fake_llm(models: list[str] | None = None) -> int:
        seen.append(models)
        return 0

    monkeypatch.setattr(model_tasks.ollama_models, "download_llm_models", fake_llm)

    assert model_tasks.main(["llm", "llama3.1:8b", "qwen2.5:7b"]) == 0
    assert seen == [["llama3.1:8b", "qwen2.5:7b"]]
