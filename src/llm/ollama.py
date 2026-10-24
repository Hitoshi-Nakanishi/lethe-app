"""Shared Ollama request for the correction and minutes steps."""

import httpx

MIN_CONTEXT = 8192
MAX_CONTEXT = 131072


def context_window(transcript: str) -> int:
    """Return an Ollama ``num_ctx`` that fits the prompt and reply for ``transcript``.

    Without it Ollama picks a VRAM-dependent default: 4K on smaller GPUs, which
    silently truncates long meetings, or 256K on large ones, which slows every
    model load. Japanese text is at most about one token per character, and the
    correction step echoes the whole transcript back, hence twice its length.
    Correction and minutes get the same size for the same transcript, so
    running one after the other does not reload the model.
    """
    needed = 2 * len(transcript) + 4096
    size = MIN_CONTEXT
    while size < needed and size < MAX_CONTEXT:
        size *= 2
    return size


def generate(prompt: str, *, model: str, ollama_url: str, num_ctx: int, timeout: float) -> str:
    """Run one non-streaming generation with thinking disabled and return the text."""
    url = ollama_url.rstrip("/") + "/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False, "think": False, "options": {"num_ctx": num_ctx}}
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data.get("response", "").strip()
