"""Download configured faster-whisper models before first app use."""

from __future__ import annotations

import argparse
import gc
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from recorder import settings as settings_store  # noqa: E402


def configured_whisper_models(config: dict | None = None) -> list[str]:
    """Return unique configured Whisper models in live/final order."""
    models = config or settings_store.model_config()
    out: list[str] = []
    for key in ("whisper_live_model", "whisper_final_model"):
        model = str(models.get(key, "")).strip()
        if model and model not in out:
            out.append(model)
    return out


def download_whisper_model(model: str, *, device: str, compute_type: str) -> None:
    """Construct a WhisperModel once so faster-whisper downloads its files."""
    from faster_whisper import WhisperModel

    loaded = WhisperModel(model, device=device, compute_type=compute_type)
    del loaded
    gc.collect()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download the Whisper models configured for Lethe.")
    parser.add_argument(
        "--device",
        default="cpu",
        help="Device used only for the download/load check. Default: cpu.",
    )
    parser.add_argument(
        "--compute-type",
        default="int8",
        help="Compute type used only for the download/load check. Default: int8.",
    )
    parser.add_argument(
        "models",
        nargs="*",
        help="Optional explicit model names. Defaults to whisper_live_model and whisper_final_model from default.toml.",
    )
    args = parser.parse_args(argv)

    models = args.models or configured_whisper_models()
    if not models:
        print("No Whisper models configured.", file=sys.stderr)
        return 1

    for model in models:
        print(f"Downloading/checking Whisper model: {model}")
        download_whisper_model(model, device=args.device, compute_type=args.compute_type)
    print("Whisper model download complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
