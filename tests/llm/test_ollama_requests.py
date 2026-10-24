"""Tests for the Ollama request payloads sent by summarize and refine."""

from __future__ import annotations

from llm import ollama, refine, summarize


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


def test_context_window_fits_transcript_and_reply():
    assert ollama.context_window("") == ollama.MIN_CONTEXT
    assert ollama.context_window("あ" * 13_000) == 32768
    assert ollama.context_window("あ" * 1_000_000) == ollama.MAX_CONTEXT


def test_summarize_disables_thinking_and_sizes_context(monkeypatch):
    seen: list[tuple[str, dict]] = []
    monkeypatch.setattr(ollama.httpx, "Client", _fake_client(seen))

    assert summarize.summarize("本文", "qwen3.5:9b", "http://localhost:11434/") == "結果"
    url, payload = seen[0]
    assert url == "http://localhost:11434/api/generate"
    assert payload["model"] == "qwen3.5:9b"
    assert payload["think"] is False
    assert payload["options"] == {"num_ctx": ollama.context_window("本文")}


def test_refine_uses_same_context_as_summarize(monkeypatch):
    seen: list[tuple[str, dict]] = []
    monkeypatch.setattr(ollama.httpx, "Client", _fake_client(seen))

    transcript = "本文" * 5_000
    assert refine.refine_transcript(transcript, "メモ") == "結果"
    summarize.summarize(transcript, "qwen3.5:9b", "http://localhost:11434")
    (_, refine_payload), (_, minutes_payload) = seen
    assert refine_payload["think"] is False
    assert refine_payload["options"] == minutes_payload["options"]
