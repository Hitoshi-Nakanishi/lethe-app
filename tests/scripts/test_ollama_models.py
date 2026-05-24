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
