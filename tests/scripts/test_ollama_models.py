"""Tests for Ollama model task helpers."""

from __future__ import annotations

import subprocess

from scripts import ollama_models


def test_configured_llm_models_uses_settings_order(monkeypatch):
    monkeypatch.setattr(ollama_models.settings_store, "llm_models", lambda: ["llama3.1:8b", "qwen2.5:7b"])

    assert ollama_models.configured_llm_models() == ["llama3.1:8b", "qwen2.5:7b"]


def test_download_llm_model_runs_ollama_pull(monkeypatch):
    seen: list[list[str]] = []

    def fake_run(cmd: list[str], *, check: bool) -> subprocess.CompletedProcess:
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(ollama_models.subprocess, "run", fake_run)

    assert ollama_models.download_llm_model("qwen2.5:7b") == 0
    assert seen == [["ollama", "pull", "qwen2.5:7b"]]


def test_download_llm_model_reports_missing_ollama(monkeypatch, capsys):
    def fake_run(cmd: list[str], *, check: bool) -> subprocess.CompletedProcess:
        raise FileNotFoundError

    monkeypatch.setattr(ollama_models.subprocess, "run", fake_run)

    assert ollama_models.download_llm_model("qwen2.5:7b") == 127
    assert "ollama" in capsys.readouterr().err


def test_download_configured_llm_models_stops_on_failure(monkeypatch):
    seen: list[str] = []

    def fake_download(model: str) -> int:
        seen.append(model)
        return 7 if model == "broken:latest" else 0

    monkeypatch.setattr(ollama_models, "download_llm_model", fake_download)

    assert ollama_models.download_configured_llm_models(["ok:latest", "broken:latest", "skipped:latest"]) == 7
    assert seen == ["ok:latest", "broken:latest"]


def test_pull_without_models_downloads_configured(monkeypatch):
    seen: list[list[str] | None] = []

    def fake_download(models: list[str] | None = None) -> int:
        seen.append(models)
        return 0

    monkeypatch.setattr(ollama_models, "download_llm_models", fake_download)

    assert ollama_models.main(["pull"]) == 0
    assert seen == [None]


def test_pull_accepts_multiple_models(monkeypatch):
    seen: list[list[str] | None] = []

    def fake_download(models: list[str] | None = None) -> int:
        seen.append(models)
        return 0

    monkeypatch.setattr(ollama_models, "download_llm_models", fake_download)

    assert ollama_models.main(["pull", "llama3.1:8b", "qwen2.5:7b"]) == 0
    assert seen == [["llama3.1:8b", "qwen2.5:7b"]]
