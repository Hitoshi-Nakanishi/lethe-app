"""Tests for the Ollama request payloads sent by summarize and refine."""

from __future__ import annotations

from llm import refine, summarize


class _FakeResponse:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"response": " 結果 "}


def _fake_client(seen: list[tuple[str, dict]]):
    class _FakeClient:
        def __init__(self, timeout: float) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            pass

        def post(self, url: str, json: dict) -> _FakeResponse:
            seen.append((url, json))
            return _FakeResponse()

    return _FakeClient


def test_summarize_disables_thinking(monkeypatch):
    seen: list[tuple[str, dict]] = []
    monkeypatch.setattr(summarize.httpx, "Client", _fake_client(seen))

    assert summarize.summarize("本文", "qwen3.5:9b", "http://localhost:11434/") == "結果"
    url, payload = seen[0]
    assert url == "http://localhost:11434/api/generate"
    assert payload["model"] == "qwen3.5:9b"
    assert payload["think"] is False


def test_refine_disables_thinking(monkeypatch):
    seen: list[tuple[str, dict]] = []
    monkeypatch.setattr(refine.httpx, "Client", _fake_client(seen))

    assert refine.refine_transcript("本文", "メモ") == "結果"
    _, payload = seen[0]
    assert payload["model"] == "qwen3.5:9b"
    assert payload["think"] is False
