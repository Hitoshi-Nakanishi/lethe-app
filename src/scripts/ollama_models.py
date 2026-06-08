"""List and pre-download configured Ollama LLM models."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from recorder import settings as settings_store  # noqa: E402


def configured_llm_models() -> list[str]:
    """Return configured Ollama models in the order shown by the app."""
    return settings_store.llm_models()


def print_configured_models() -> None:
    models = configured_llm_models()
    if not models:
        print("No LLM models configured.")
        return
    print("Configured LLM models:")
    for model in models:
        print(f"  {model}")


def download_llm_model(model: str) -> int:
    """Run ``ollama pull`` for one model and return the process exit code."""
    try:
        result = subprocess.run(["ollama", "pull", model], check=False)
    except FileNotFoundError:
        print("`ollama` command not found. Install Ollama and ensure it is on PATH.", file=sys.stderr)
        return 127
    return result.returncode


def download_llm_models(models: list[str] | None = None) -> int:
    """Download explicit Ollama models, or every configured model when omitted."""
    selected = models if models is not None else configured_llm_models()
    if not selected:
        print("No LLM models configured.")
        return 0
    for model in selected:
        print(f"Downloading/checking Ollama LLM model: {model}")
        rc = download_llm_model(model)
        if rc != 0:
            return rc
    print("Ollama LLM model download complete.")
    return 0


def download_configured_llm_models(models: list[str] | None = None) -> int:
    """Backward-compatible wrapper for older task names."""
    return download_llm_models(models)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List or download Ollama LLM models configured for Lethe.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List LLM model names configured in default.toml.")
    subparsers.add_parser("pull-configured", help="Download every configured Ollama LLM model.")
    pull = subparsers.add_parser("pull", help="Download configured LLM models, or the model names passed after it.")
    pull.add_argument("models", nargs="*", help="Optional Ollama model names, for example llama3.1:8b qwen2.5:7b.")

    args = parser.parse_args(argv)
    if args.command == "list":
        print_configured_models()
        return 0
    if args.command == "pull-configured":
        return download_llm_models()
    if args.command == "pull":
        return download_llm_models(args.models or None)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
