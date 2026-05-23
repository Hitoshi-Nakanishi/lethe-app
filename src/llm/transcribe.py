import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class WhisperNotFoundError(RuntimeError):
    pass


def transcribe(audio_path: Path, model: str = "base", language: str = "ja") -> str:
    """Run the openai-whisper CLI and return the transcript text."""
    whisper = shutil.which("whisper")
    if whisper is None:
        raise WhisperNotFoundError(
            "`whisper` CLI not found. See docs/llm/install-mac.md or docs/llm/install-windows.md for setup instructions."
        )
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        cmd = [
            whisper,
            str(audio_path),
            "--model",
            model,
            "--language",
            language,
            "--output_format",
            "txt",
            "--output_dir",
            str(out_dir),
            "--verbose",
            "False",
            "--fp16",
            "False",
        ]
        print(f"[transcribe] {' '.join(cmd)}", file=sys.stderr)
        subprocess.run(cmd, check=True)
        txt_path = out_dir / f"{audio_path.stem}.txt"
        if not txt_path.exists():
            raise RuntimeError(f"Whisper did not produce expected output: {txt_path}")
        return txt_path.read_text(encoding="utf-8")
