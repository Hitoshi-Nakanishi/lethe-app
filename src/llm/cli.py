import argparse
import sys
from pathlib import Path

from llm.summarize import summarize
from llm.transcribe import WhisperNotFoundError, transcribe


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m llm",
        description="Transcribe an audio file with Whisper and turn it into Markdown meeting minutes via a local Ollama model.",
    )
    p.add_argument("audio", type=Path, help="Path to the input audio file (mp3/wav/m4a/...).")
    p.add_argument("-o", "--output", type=Path, default=None, help="Output Markdown path. Defaults to <audio>.minutes.md.")
    p.add_argument("--whisper-model", default="base", help="Whisper model size (tiny/base/small/medium/large). Default: base.")
    p.add_argument("--language", default="ja", help="Spoken language. Default: ja.")
    p.add_argument("--model", default="llama3.1:8b", help="Ollama model tag to use for summarization. Default: llama3.1:8b.")
    p.add_argument(
        "--ollama-url", default="http://localhost:11434", help="Ollama HTTP base URL. Default: http://localhost:11434."
    )
    p.add_argument("--keep-transcript", action="store_true", help="Also save the raw transcript alongside the minutes.")
    p.add_argument("--transcript-only", action="store_true", help="Skip the Ollama step and only emit the raw transcript.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    audio: Path = args.audio
    output: Path = args.output or audio.with_suffix(".minutes.md")

    try:
        transcript = transcribe(audio, model=args.whisper_model, language=args.language)
    except WhisperNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.keep_transcript or args.transcript_only:
        transcript_path = audio.with_suffix(".transcript.txt")
        transcript_path.write_text(transcript, encoding="utf-8")
        print(f"wrote {transcript_path}", file=sys.stderr)

    if args.transcript_only:
        return 0

    minutes = summarize(
        transcript,
        model=args.model,
        ollama_url=args.ollama_url,
    )
    output.write_text(minutes + "\n", encoding="utf-8")
    print(f"wrote {output}", file=sys.stderr)
    return 0
