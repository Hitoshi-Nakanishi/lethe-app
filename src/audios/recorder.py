"""Record system audio via WASAPI loopback on Windows and write a 16-bit WAV.

The loopback endpoint of the default playback device captures the exact mix the
OS is sending to the speakers, so it picks up Zoom calls, browser <video>
playback, and anything else playing on the system without needing a virtual
cable.
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np


class LoopbackUnavailableError(RuntimeError):
    pass


def _import_soundcard():
    try:
        import soundcard as sc  # type: ignore[import-not-found]
    except ImportError as e:
        raise LoopbackUnavailableError("`soundcard` package not installed. See docs/audios/install-windows.md.") from e
    return sc


def record(
    output: Path,
    seconds: float | None,
    samplerate: int = 48000,
    channels: int = 2,
    chunk_seconds: float = 1.0,
    stop_flag: Path | None = None,
) -> Path:
    """Capture the default speaker's loopback to ``output`` as a 16-bit PCM WAV.

    Stops when any of these happens first:
      - ``seconds`` elapsed (if not None),
      - KeyboardInterrupt (Ctrl+C),
      - ``stop_flag`` file exists (polled once per chunk; used by `audios stop`).
    """
    sc = _import_soundcard()
    speaker = sc.default_speaker()
    mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    chunk_frames = max(1, int(samplerate * chunk_seconds))
    elapsed = 0.0
    label = "until Ctrl+C" if seconds is None else f"{seconds:.1f}s"
    print(f"[record] device={speaker.name!r} -> {output} ({label})", file=sys.stderr)

    with mic.recorder(samplerate=samplerate, channels=channels) as src, wave.open(str(output), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(samplerate)
        try:
            while seconds is None or elapsed < seconds:
                if stop_flag is not None and stop_flag.exists():
                    print("[record] stop flag detected", file=sys.stderr)
                    break
                data = src.record(numframes=chunk_frames)  # float32 in [-1, 1]
                pcm = np.clip(data * 32767.0, -32768.0, 32767.0).astype(np.int16)
                wav.writeframes(pcm.tobytes())
                elapsed += chunk_seconds
        except KeyboardInterrupt:
            print("\n[record] stopped by user", file=sys.stderr)
    return output


def list_devices() -> str:
    """Return a human-readable listing of speakers and loopback microphones."""
    sc = _import_soundcard()
    default_name = sc.default_speaker().name
    lines = ["[speakers]"]
    for s in sc.all_speakers():
        marker = " (default)" if s.name == default_name else ""
        lines.append(f"  - {s.name}{marker}")
    lines.append("[microphones (include_loopback=True)]")
    for m in sc.all_microphones(include_loopback=True):
        tag = " [LOOPBACK]" if getattr(m, "isloopback", False) else ""
        lines.append(f"  - {m.name}{tag}")
    return "\n".join(lines)
