"""Combined model task helpers for Lethe."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from scripts import download_models, ollama_models  # noqa: E402


def print_model_list() -> None:
    """Print every model Lethe can pre-download from current configuration."""
    whisper = download_models.configured_whisper_models()
    llm = ollama_models.configured_llm_models()

    print("Whisper speech models:")
    if whisper:
        for model in whisper:
            print(f"  {model}")
    else:
        print("  (none configured)")

    print("Ollama LLM models:")
    if llm:
        for model in llm:
            print(f"  {model}")
    else:
        print("  (none configured)")


def download_all_models() -> int:
    """Download configured Whisper speech models and Ollama LLM models."""
    rc = download_models.main([])
    if rc != 0:
        return rc
    return ollama_models.download_configured_llm_models()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List or download all configured Lethe models.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List configured Whisper and Ollama models.")
    subparsers.add_parser("download", help="Download configured Whisper and Ollama models.")

    args = parser.parse_args(argv)
    if args.command == "list":
        print_model_list()
        return 0
    if args.command == "download":
        return download_all_models()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
