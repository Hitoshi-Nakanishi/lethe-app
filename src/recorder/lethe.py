"""Lethe -- a desktop voice recorder, transcriber and minutes tool.

Run with:
    lethe                     # console-script entry point
    python -m recorder.lethe  # equivalent

Lethe records the microphone (or any input device, including a BlackHole
aggregate that carries Zoom/YouTube audio), transcribes it with Whisper,
and turns the transcript into Markdown meeting minutes.

Workflow: 録音 → ① 高精度で文字起こし → (メモに用語を記入) → ② メモで校正
→ ③ 議事録を作成.

Highlights:
- Recording streams straight to a temp WAV (RAM stays flat for long
  meetings); a live VU meter confirms the mic is picking up sound.
- Live transcribe gives a fast 5s-chunked preview; on stop, an accurate
  full-file pass (Whisper large-v3) replaces it with timestamped segments.
- Every transcript line carries a clickable [MM:SS] timestamp that seeks
  the built-in player, so a suspect line can be re-listened to.
- Notes feed Whisper's initial_prompt and the Ollama refinement step.
- Sessions (audio + transcript + notes) save/open as a single .zip.
- Preferences persist between launches; stale temp files are swept.
- Shortcuts: Space = start/stop, Cmd/Ctrl+S = export transcript,
  Cmd/Ctrl+O = open audio file.
"""

from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
import wave
import zipfile
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np

from recorder import settings as settings_store
from recorder.i18n import (
    LABEL_PAUSE,
    LANGUAGE_CODES,
    LANGUAGES,
    MIC_HELP,
    SYSTEM_AUDIO_HELP,
    TOOLTIP_EXPORT_TXT,
    TOOLTIP_HQ,
    TOOLTIP_HQ_MODEL,
    TOOLTIP_HQ_MODEL_EN,
    TOOLTIP_LIVE,
    TOOLTIP_MIC_CAPTURE,
    TOOLTIP_MINUTES,
    TOOLTIP_MP3,
    TOOLTIP_NR,
    TOOLTIP_OPEN,
    TOOLTIP_PLAY,
    TOOLTIP_RECORD,
    TOOLTIP_REFINE,
    TOOLTIP_SYSTEM_CAPTURE,
    text_for,
)
from recorder.theme import THEME_LABELS, THEMES, palette_for
from recorder.ui import Switch, Tooltip, UiColors, WaveMeter

APP_NAME = "Lethe"
APP_TAGLINE = "録音・文字起こし・議事録"
DEFAULT_FONT_SIZE = 11
MIN_FONT_SIZE = 9
MAX_FONT_SIZE = 18
UI_FONT_FAMILY = "Segoe UI" if sys.platform.startswith("win") else "SF Pro Text" if sys.platform == "darwin" else "Noto Sans"

SAMPLE_RATE = 44100
CHANNELS = 1
DTYPE = "int16"
RECORDER_CHUNK_SECONDS = 0.1
LOOPBACK_CHANNELS = 2
MP3_BITRATE = 128
_MODEL_CONFIG = settings_store.model_config()
WHISPER_MODEL = _MODEL_CONFIG["whisper_live_model"]
WHISPER_LANGUAGE = _MODEL_CONFIG["whisper_language"]
WHISPER_CHUNK_SECONDS = 5.0
HQ_MODEL = _MODEL_CONFIG["whisper_final_model"]
HQ_MODEL_LABEL = HQ_MODEL
OLLAMA_MODEL = _MODEL_CONFIG["default_llm_model"]
OLLAMA_URL = _MODEL_CONFIG["ollama_url"]
PLAYBACK_SR = 16000  # opened files / sessions are decoded to 16 kHz mono for playback

# --- themes (ttk "clam" with app-owned palettes) ---
BG = SURFACE = SURFACE_2 = BORDER = TEXT = TEXT_MUTED = ACCENT = ACCENT_DARK = ACCENT_SOFT = ""
DANGER = DANGER_DARK = OK_GREEN = DISABLED_BG = DISABLED_FG = ""


def _apply_palette(theme: str, dark_mode: bool) -> None:
    global BG, SURFACE, SURFACE_2, BORDER, TEXT, TEXT_MUTED, ACCENT, ACCENT_DARK, ACCENT_SOFT
    global DANGER, DANGER_DARK, OK_GREEN, DISABLED_BG, DISABLED_FG
    palette = palette_for(theme, dark_mode)
    BG = palette["bg"]
    SURFACE = palette["surface"]
    SURFACE_2 = palette["surface_2"]
    BORDER = palette["border"]
    TEXT = palette["text"]
    TEXT_MUTED = palette["muted"]
    ACCENT = palette["accent"]
    ACCENT_DARK = palette["accent_dark"]
    ACCENT_SOFT = palette["accent_soft"]
    DANGER = palette["danger"]
    DANGER_DARK = palette["danger_dark"]
    OK_GREEN = palette["ok"]
    DISABLED_BG = palette["disabled_bg"]
    DISABLED_FG = palette["disabled_fg"]


def _ui_colors() -> UiColors:
    return {
        "surface": SURFACE,
        "surface_2": SURFACE_2,
        "border": BORDER,
        "text": TEXT,
        "muted": TEXT_MUTED,
        "accent": ACCENT,
        "accent_dark": ACCENT_DARK,
        "disabled_bg": DISABLED_BG,
        "disabled_fg": DISABLED_FG,
    }


PAD_X = 16
PAD_Y = 12

DATASET_AUDIO = "audio.mp3"
DATASET_TRANSCRIPT = "transcript.md"
DATASET_MEMO = "memo.md"
DATASET_MANIFEST = "manifest.json"

AUDIO_FILETYPES = [
    ("音声ファイル", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.mp4 *.mov"),
    ("すべてのファイル", "*.*"),
]
TIMESTAMP_RE = re.compile(r"^\[(?:(\d+):)?(\d{1,2}):(\d{2})\]")
FILENAME_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
FILENAME_SPACE_RE = re.compile(r"\s+")
FILENAME_UNDERSCORE_RE = re.compile(r"_+")


def _fmt_time(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _parse_leading_timestamp(line: str) -> float | None:
    """Parse a leading ``[MM:SS]`` / ``[H:MM:SS]`` prefix into seconds."""
    m = TIMESTAMP_RE.match(line.strip())
    if not m:
        return None
    hours = int(m.group(1) or 0)
    return hours * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def _is_connection_error(exc: Exception) -> bool:
    """Heuristic: does this exception look like 'service not reachable'?"""
    blob = f"{type(exc).__name__} {exc}".lower()
    return any(s in blob for s in ("connect", "refused", "11434", "timed out", "timeout"))


def ollama_help(model: str = OLLAMA_MODEL, ollama_url: str = OLLAMA_URL) -> str:
    return (
        f"Ollama に接続できませんでした（{ollama_url}）。\n\n"
        "ターミナルで次を実行してから、もう一度お試しください:\n"
        f"  ollama serve\n  ollama pull {model}"
    )


def describe_error(
    exc: Exception,
    *,
    ollama: bool = False,
    model: str = OLLAMA_MODEL,
    ollama_url: str = OLLAMA_URL,
) -> str:
    """Turn a worker exception into an actionable Japanese message."""
    if ollama and _is_connection_error(exc):
        return ollama_help(model, ollama_url)
    return f"{type(exc).__name__}: {exc}"


def _coerce_font_size(value: object) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = DEFAULT_FONT_SIZE
    return max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, size))


def _safe_filename_part(value: object, fallback: str = "meeting") -> str:
    text = str(value or "").strip()
    text = FILENAME_UNSAFE_RE.sub("_", text)
    text = FILENAME_SPACE_RE.sub("_", text)
    text = FILENAME_UNDERSCORE_RE.sub("_", text)
    text = text.strip("._ ")
    return text or fallback


def _suggested_mp3_filename(now: float | None = None) -> str:
    config = settings_store.filename_config()
    timestamp_format = str(config.get("timestamp_format") or "%Y%m%d_%H%M")
    clock = time.localtime(now) if now is not None else time.localtime()
    try:
        timestamp = time.strftime(timestamp_format, clock)
    except ValueError:
        timestamp = time.strftime("%Y%m%d_%H%M", clock)
    values = {
        "timestamp": _safe_filename_part(timestamp, fallback=time.strftime("%Y%m%d_%H%M", clock)),
        "meeting_name": _safe_filename_part(config.get("meeting_name"), fallback="meeting"),
    }
    template = str(config.get("mp3_template") or "{timestamp}_{meeting_name}.mp3")
    try:
        filename = template.format(**values)
    except (KeyError, IndexError, ValueError):
        filename = "{timestamp}_{meeting_name}.mp3".format(**values)
    filename = _safe_filename_part(filename, fallback="recording")
    return filename if filename.lower().endswith(".mp3") else f"{filename}.mp3"


def _suggested_dataset_name(now: float | None = None) -> str:
    config = settings_store.filename_config()
    timestamp_format = str(config.get("timestamp_format") or "%Y%m%d_%H%M")
    clock = time.localtime(now) if now is not None else time.localtime()
    try:
        timestamp = time.strftime(timestamp_format, clock)
    except ValueError:
        timestamp = time.strftime("%Y%m%d_%H%M", clock)
    values = {
        "timestamp": _safe_filename_part(timestamp, fallback=time.strftime("%Y%m%d_%H%M", clock)),
        "meeting_name": _safe_filename_part(config.get("meeting_name"), fallback="meeting"),
    }
    template = str(config.get("dataset_template") or "{timestamp}_{meeting_name}")
    try:
        name = template.format(**values)
    except (KeyError, IndexError, ValueError):
        name = "{timestamp}_{meeting_name}".format(**values)
    return _safe_filename_part(name, fallback="dataset")


def _initialdir_option(key: str) -> dict[str, str]:
    path = settings_store.configured_path(key, create=True)
    return {"initialdir": str(path)} if path is not None else {}


def _encode_mp3_float32(path: str | Path, audio_f32: np.ndarray, sample_rate: int) -> None:
    import lameenc

    audio = np.clip(np.asarray(audio_f32, dtype=np.float32).reshape(-1) * 32768.0, -32768, 32767).astype(np.int16)
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(MP3_BITRATE)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(CHANNELS)
    encoder.set_quality(2)
    mp3 = encoder.encode(audio.tobytes())
    mp3 += encoder.flush()
    Path(path).write_bytes(mp3)


def _dataset_manifest(dataset_id: str, duration_seconds: float) -> dict:
    return {
        "version": 1,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset_id": dataset_id,
        "duration_seconds": round(duration_seconds, 2),
        "path_mapping": {
            "audio": DATASET_AUDIO,
            "transcript": DATASET_TRANSCRIPT,
            "memo": DATASET_MEMO,
        },
        "files": [
            {"role": "audio", "path": DATASET_AUDIO, "media_type": "audio/mpeg"},
            {"role": "transcript", "path": DATASET_TRANSCRIPT, "media_type": "text/markdown"},
            {"role": "memo", "path": DATASET_MEMO, "media_type": "text/markdown"},
        ],
    }


def hq_model_cached(model_id: str = HQ_MODEL) -> bool:
    """True if the HQ model already sits in the Hugging Face cache on disk."""
    from llm.whisper_models import is_model_cached

    return is_model_cached(model_id)


def _format_gb(value: float) -> str:
    if value < 1.0:
        return f"{int(round(value * 1024))} MB"
    if value < 10:
        return f"{value:.1f} GB"
    return f"{int(round(value))} GB"


def _rating_bar(value: int, maximum: int = 5) -> str:
    value = max(0, min(value, maximum))
    return "●" * value + "○" * (maximum - value)


def list_input_devices() -> list[tuple[str, int | None]]:
    """Return [(label, device_index), ...] for the system default + every input device.

    sounddevice can surface the same physical mic multiple times when more than
    one host API is active (Core Audio + AVAudio on macOS, WDM + WASAPI on
    Windows). Dedupe by ``(name, channel count)`` so each mic appears once;
    prefer the first occurrence's index because earlier entries usually map to
    the OS's preferred backend.
    """
    import sounddevice as sd

    out: list[tuple[str, int | None]] = [("システム既定", None)]
    try:
        devices = sd.query_devices()
    except Exception:
        return out
    seen: set[tuple[str, int]] = set()
    for i, dev in enumerate(devices):
        channels = int(dev.get("max_input_channels", 0) or 0)
        if channels <= 0:
            continue
        name = str(dev.get("name", "")).strip()
        key = (name.casefold(), channels)
        if key in seen:
            continue
        seen.add(key)
        out.append((f"{name} ({channels}ch)", i))
    return out


def system_output_capture_available() -> bool:
    """Return True when Lethe can try OS speaker-loopback capture."""
    return sys.platform.startswith("win")


def list_output_devices() -> list[tuple[str, str | None]]:
    """Return [(label, speaker_name), ...] for the default + known speakers."""
    out: list[tuple[str, str | None]] = [("システム既定", None)]
    if not system_output_capture_available():
        return out
    try:
        import soundcard as sc  # type: ignore[import-not-found]

        speakers = sc.all_speakers()
    except Exception:
        return out
    seen: set[str] = set()
    for speaker in speakers:
        name = str(getattr(speaker, "name", "")).strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append((name, name))
    return out


def _int16_peak(chunk: np.ndarray) -> float:
    if chunk.size == 0:
        return 0.0
    return float(np.abs(chunk.astype(np.float32)).max()) / 32768.0


def _as_mono_int16(data: np.ndarray) -> np.ndarray:
    arr = np.asarray(data)
    if arr.ndim > 1:
        arr = arr.mean(axis=1)
    if arr.dtype.kind == "f":
        arr = np.clip(arr, -1.0, 1.0) * 32767.0
    return np.clip(arr, -32768.0, 32767.0).astype(np.int16).reshape(-1, 1)


def _mix_int16_chunks(chunks: list[np.ndarray]) -> np.ndarray:
    arrays = [np.asarray(chunk, dtype=np.int16).reshape(-1) for chunk in chunks if chunk.size]
    if not arrays:
        return np.zeros((0, 1), dtype=np.int16)
    frames = max(arr.size for arr in arrays)
    mixed = np.zeros(frames, dtype=np.float32)
    for arr in arrays:
        if arr.size < frames:
            padded = np.zeros(frames, dtype=np.float32)
            padded[: arr.size] = arr.astype(np.float32)
            mixed += padded
        else:
            mixed += arr.astype(np.float32)
    return np.clip(mixed, -32768.0, 32767.0).astype(np.int16).reshape(-1, 1)


class MicRecorder:
    """Records microphone and/or Windows speaker loopback to one temp WAV.

    Source threads enqueue fixed-size mono int16 chunks. A mixer/writer thread
    drains those queues, writes a single mixed WAV, and optionally forwards the
    same mixed chunks to live transcription.
    """

    def __init__(self, on_chunk: Callable[[np.ndarray], None] | None = None) -> None:
        self._mic_queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._system_queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._mic_stream = None
        self._system_thread: threading.Thread | None = None
        self._writer_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._on_chunk = on_chunk
        self._wav_path: Path | None = None
        self._frames_written = 0
        self._level = 0.0
        self._mic_level = 0.0
        self._system_level = 0.0
        self._capture_mic = False
        self._capture_system = False

    def start(
        self,
        device: int | None = None,
        *,
        capture_mic: bool = True,
        capture_system: bool = False,
        output_device_id: str | None = None,
    ) -> None:
        if not capture_mic and not capture_system:
            return

        self._wav_path = settings_store.temp_path(f"micrec-{os.getpid()}-{int(time.time() * 1000)}.wav")
        self._frames_written = 0
        self._level = 0.0
        self._mic_level = 0.0
        self._system_level = 0.0
        self._capture_mic = capture_mic
        self._capture_system = capture_system
        self._mic_queue = queue.Queue()
        self._system_queue = queue.Queue()
        self._stop_event = threading.Event()

        try:
            if capture_system:
                self._start_system_loopback(output_device_id)
            if capture_mic:
                self._start_mic_stream(device)
            self._writer_thread = threading.Thread(target=self._writer, args=(self._wav_path,), daemon=True)
            self._writer_thread.start()
        except Exception:
            self.stop()
            self.cleanup()
            raise

    def _start_mic_stream(self, device: int | None) -> None:
        import sounddevice as sd

        chunk_frames = max(1, int(SAMPLE_RATE * RECORDER_CHUNK_SECONDS))
        self._mic_stream = sd.InputStream(
            device=device,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=chunk_frames,
            callback=self._mic_callback,
        )
        self._mic_stream.start()

    def _start_system_loopback(self, output_device_id: str | None) -> None:
        if not system_output_capture_available():
            raise RuntimeError("PC audio capture is only available on Windows.")
        ready = threading.Event()
        errors: list[BaseException] = []
        self._system_thread = threading.Thread(
            target=self._system_loopback_worker,
            args=(output_device_id, ready, errors),
            daemon=True,
        )
        self._system_thread.start()
        if not ready.wait(timeout=5.0):
            self._stop_event.set()
            raise RuntimeError("Timed out while starting PC audio capture.")
        if errors:
            raise errors[0]

    def _mic_callback(self, indata, frames, time_info, status) -> None:
        chunk = _as_mono_int16(indata.copy())
        self._mic_level = _int16_peak(chunk)
        self._mic_queue.put(chunk)

    def _system_loopback_worker(
        self,
        output_device_id: str | None,
        ready: threading.Event,
        errors: list[BaseException],
    ) -> None:
        import ctypes

        # soundcard uses COM, which must be initialized per thread (else WASAPI
        # calls fail with 0x800401f0). 0 = COINIT_MULTITHREADED; S_OK/S_FALSE
        # mean this thread now holds a reference that must be released.
        com_initialized = ctypes.windll.ole32.CoInitializeEx(None, 0) in (0, 1)
        try:
            import soundcard as sc  # type: ignore[import-not-found]

            speaker_name = output_device_id or str(sc.default_speaker().name)
            loopback_mic = sc.get_microphone(id=speaker_name, include_loopback=True)
            chunk_frames = max(1, int(SAMPLE_RATE * RECORDER_CHUNK_SECONDS))
            with loopback_mic.recorder(samplerate=SAMPLE_RATE, channels=LOOPBACK_CHANNELS) as source:
                ready.set()
                while not self._stop_event.is_set():
                    data = source.record(numframes=chunk_frames)
                    chunk = _as_mono_int16(data)
                    self._system_level = _int16_peak(chunk)
                    self._system_queue.put(chunk)
        except BaseException as exc:
            errors.append(exc)
            ready.set()
        finally:
            self._system_queue.put(None)
            if com_initialized:
                ctypes.windll.ole32.CoUninitialize()

    def _writer(self, path: Path) -> None:
        mic_done = not self._capture_mic
        system_done = not self._capture_system
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            while not (mic_done and system_done):
                chunks: list[np.ndarray] = []
                if not mic_done:
                    mic_chunk = self._mic_queue.get()
                    if mic_chunk is None:
                        mic_done = True
                    else:
                        chunks.append(mic_chunk)
                if not system_done:
                    system_chunk = self._system_queue.get()
                    if system_chunk is None:
                        system_done = True
                    else:
                        chunks.append(system_chunk)
                mixed = _mix_int16_chunks(chunks)
                if not mixed.size:
                    continue
                self._level = _int16_peak(mixed)
                wav.writeframes(mixed.tobytes())
                self._frames_written += mixed.shape[0]
                if self._on_chunk is not None:
                    self._on_chunk(mixed)

    def stop(self) -> None:
        if self._mic_stream is not None:
            self._mic_stream.stop()
            self._mic_stream.close()
            self._mic_stream = None
            self._mic_queue.put(None)
        self._stop_event.set()
        if self._system_thread is not None:
            self._system_thread.join(timeout=10)
            self._system_thread = None
        if self._capture_system:
            self._system_queue.put(None)
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=10)
            self._writer_thread = None
        self._level = 0.0
        self._mic_level = 0.0
        self._system_level = 0.0
        self._capture_mic = False
        self._capture_system = False

    @property
    def level(self) -> float:
        return self._level

    @property
    def mic_level(self) -> float:
        return self._mic_level

    @property
    def system_level(self) -> float:
        return self._system_level

    @property
    def has_recording(self) -> bool:
        return self._wav_path is not None and self._wav_path.exists() and self._frames_written > 0

    @property
    def duration_seconds(self) -> float:
        return self._frames_written / SAMPLE_RATE

    @property
    def wav_path(self) -> Path | None:
        return self._wav_path

    @property
    def audio_float32(self) -> np.ndarray:
        """The whole recording read back from disk as 1-D float32 in [-1, 1]."""
        if not self.has_recording:
            return np.zeros(0, dtype=np.float32)
        with wave.open(str(self._wav_path), "rb") as wav:
            raw = wav.readframes(wav.getnframes())
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    def encode_mp3(
        self,
        path: str | Path,
        preprocessor: Callable[[np.ndarray, int], np.ndarray] | None = None,
    ) -> None:
        if not self.has_recording:
            raise RuntimeError("No recording available")
        audio_f32 = self.audio_float32
        if preprocessor is not None:
            audio_f32 = preprocessor(audio_f32, SAMPLE_RATE)
        _encode_mp3_float32(path, audio_f32, SAMPLE_RATE)

    def cleanup(self) -> None:
        """Delete the temp WAV file, if any."""
        if self._wav_path is not None and self._wav_path.exists():
            try:
                self._wav_path.unlink()
            except OSError:
                pass


class Player:
    """Minimal seekable audio player on top of ``sounddevice.play``.

    sounddevice has no native pause/seek, so "seek" simply restarts
    playback from the requested sample offset. Position is tracked against
    a wall clock, which is accurate enough for a transcript-verification
    scrubber.
    """

    def __init__(self) -> None:
        self._audio = np.zeros(0, dtype=np.float32)
        self._sr = PLAYBACK_SR
        self._playing = False
        self._start_pos = 0.0
        self._start_wall = 0.0

    def load(self, audio: np.ndarray, sr: int) -> None:
        self.reset()
        self._audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        self._sr = sr or PLAYBACK_SR

    @property
    def has_audio(self) -> bool:
        return self._audio.size > 0

    @property
    def duration(self) -> float:
        return self._audio.size / self._sr if self._sr else 0.0

    @property
    def audio_float32(self) -> np.ndarray:
        return self._audio.copy()

    @property
    def sample_rate(self) -> int:
        return self._sr

    @property
    def position(self) -> float:
        if self._playing:
            return min(self._start_pos + (time.monotonic() - self._start_wall), self.duration)
        return self._start_pos

    @property
    def is_playing(self) -> bool:
        if self._playing and self.position >= self.duration:
            self._playing = False
            self._start_pos = self.duration
        return self._playing

    def play(self, from_seconds: float | None = None) -> None:
        import sounddevice as sd

        if not self.has_audio:
            return
        pos = self.position if from_seconds is None else from_seconds
        if pos >= self.duration - 0.05:
            pos = 0.0
        pos = max(0.0, min(pos, self.duration))
        sd.stop()
        sd.play(self._audio[int(pos * self._sr) :], self._sr)
        self._start_pos = pos
        self._start_wall = time.monotonic()
        self._playing = True

    def pause(self) -> None:
        import sounddevice as sd

        if self._playing:
            self._start_pos = self.position
        self._playing = False
        sd.stop()

    def reset(self) -> None:
        import sounddevice as sd

        self._playing = False
        self._start_pos = 0.0
        sd.stop()

    def write_wav(self, path: str | Path) -> None:
        pcm = np.clip(self._audio * 32768.0, -32768, 32767).astype(np.int16)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self._sr)
            wav.writeframes(pcm.tobytes())


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.is_recording = False
        self._busy = False  # True while an HQ / refine / minutes worker runs
        self._status_kind = "ready"
        self._tick_job: str | None = None
        self._elapsed = 0
        self._meter_level = 0.0
        self._transcript_queue: queue.Queue[tuple[str, int, str]] = queue.Queue()
        self._refine_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._hq_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._minutes_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._progress_queue: queue.Queue[float] = queue.Queue()
        self._transcriber = None
        self._player = Player()
        self._settings = settings_store.load_settings()
        self._mic_capture_var = tk.BooleanVar(value=bool(self._settings.get("mic_capture", True)))
        self._system_capture_var = tk.BooleanVar(
            value=bool(self._settings.get("system_capture", system_output_capture_available()))
            and system_output_capture_available()
        )
        self._live_var = tk.BooleanVar(value=bool(self._settings.get("live")))
        self._nr_var = tk.BooleanVar(value=bool(self._settings.get("noise_reduce")))
        self._llm_models = settings_store.llm_models()
        saved_llm = str(self._settings.get("llm_model") or "").strip()
        default_llm = saved_llm or OLLAMA_MODEL
        if default_llm not in self._llm_models:
            self._llm_models.insert(0, default_llm)
        self._llm_model_var = tk.StringVar(value=default_llm)
        self._ollama_url = settings_store.model_config()["ollama_url"]
        saved_hq = str(self._settings.get("hq_model") or "").strip()
        self._hq_model = saved_hq or HQ_MODEL
        self._hq_model_var = tk.StringVar(value=self._hq_model)
        self._hq_combo_values: list[str] = []
        self._hq_combo_ids: list[str] = []
        self._downloading_model: str | None = None
        self._hq_should_run_after_download = False
        self._analysis_audio_path: Path | None = None
        self._settings_window: tk.Toplevel | None = None
        self.theme_combo: ttk.Combobox | None = None
        self.language_combo: ttk.Combobox | None = None
        self.dark_check: Switch | None = None
        self.theme_label_widget: ttk.Label | None = None
        self.language_label_widget: ttk.Label | None = None
        self.dark_label_widget: ttk.Label | None = None
        self._settings_tooltip: Tooltip | None = None
        self._theme_var = tk.StringVar(value=THEMES.get(self._settings.get("theme"), THEMES["midnight"])["label"])
        self._dark_var = tk.BooleanVar(value=bool(self._settings.get("dark_mode")))
        saved_language = str(self._settings.get("language") or "ja")
        self._language_var = tk.StringVar(value=LANGUAGES.get(saved_language, LANGUAGES["ja"]))
        self._font_size = _coerce_font_size(self._settings.get("font_size"))
        _apply_palette(self._theme_key(), self._dark_var.get())
        self._device_index: int | None = self._settings.get("device_index")
        self._output_device_id: str | None = self._settings.get("output_device_id") or None
        self._devices: list[tuple[str, int | None]] = [("システム既定", None)]
        self._output_devices: list[tuple[str, str | None]] = [("システム既定", None)]
        self._notes_cache = ""
        self.recorder = MicRecorder()

        root.title(f"{APP_NAME} — {self._tr('tagline')}")
        root.geometry(self._settings.get("geometry") or "1180x780")
        root.minsize(1060, 720)
        root.configure(background=BG)

        self._configure_style()
        self._build_menu()
        self._build_header()
        self._build_status_bar()

        main = ttk.PanedWindow(root, orient="vertical")
        main.pack(side="top", fill="both", expand=True, padx=10, pady=(6, 6))
        controls = ttk.Frame(main, style="Card.TFrame")
        editors = ttk.PanedWindow(main, orient="horizontal")
        transcript_panel = ttk.Frame(editors, style="Card.TFrame")
        notes_panel = ttk.Frame(editors, style="Card.TFrame")
        editors.add(transcript_panel, weight=1)
        editors.add(notes_panel, weight=1)
        main.add(controls, weight=0)
        main.add(editors, weight=1)

        self._build_controls(controls)
        self._build_transcript(transcript_panel)
        self._build_notes(notes_panel)
        self._bind_shortcuts()

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_queues)

    # ---------- styling / menu / header ----------

    def _configure_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=BG, foreground=TEXT, font=self._font())
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=SURFACE)
        style.configure("Header.TFrame", background=SURFACE)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Card.TLabel", background=SURFACE, foreground=TEXT)
        style.configure("Title.TLabel", background=SURFACE, foreground=TEXT, font=self._font(1, "bold"))
        style.configure("Hint.TLabel", background=SURFACE, foreground=TEXT_MUTED, font=self._font(-1))
        style.configure("Workflow.TLabel", background=SURFACE, foreground=ACCENT, font=self._font(-1))
        style.configure("Wordmark.TLabel", background=SURFACE, foreground=ACCENT, font=self._font(11, "bold"))
        style.configure("Tagline.TLabel", background=SURFACE, foreground=TEXT_MUTED, font=self._font())
        style.configure("Timer.TLabel", background=SURFACE, foreground=TEXT, font=self._font(15, "bold"))
        style.configure("Status.TLabel", background=BG, foreground=TEXT, font=self._font(1), padding=(10, 3))
        style.configure("StatusBar.TFrame", background=SURFACE)
        style.configure("StatusBarHint.TLabel", background=SURFACE, foreground=TEXT_MUTED, font=self._font(-1))
        style.configure("StatusTimer.TLabel", background=SURFACE, foreground=TEXT, font=self._font(6, "bold"))

        style.configure(
            "TButton",
            background=SURFACE,
            foreground=TEXT,
            bordercolor=BORDER,
            borderwidth=1,
            relief="flat",
            focuscolor=SURFACE,
            padding=(12, 7),
            font=self._font(),
        )
        style.map(
            "TButton",
            background=[("pressed", SURFACE_2), ("active", ACCENT_SOFT), ("disabled", DISABLED_BG)],
            foreground=[("disabled", DISABLED_FG)],
            bordercolor=[("disabled", DISABLED_BG)],
        )
        for name, base, dark in (("Accent", ACCENT, ACCENT_DARK), ("Danger", DANGER, DANGER_DARK)):
            style.configure(
                f"{name}.TButton",
                background=base,
                foreground="#ffffff",
                bordercolor=base,
                borderwidth=1,
                relief="flat",
                focuscolor=base,
                padding=(15, 9),
                font=self._font(1, "bold"),
            )
            style.map(
                f"{name}.TButton",
                background=[("pressed", dark), ("active", dark), ("disabled", DISABLED_BG)],
                foreground=[("disabled", DISABLED_FG)],
                bordercolor=[("disabled", DISABLED_BG)],
            )
        style.configure(
            "Ghost.TButton",
            background=SURFACE,
            foreground=TEXT_MUTED,
            bordercolor=SURFACE,
            borderwidth=0,
            relief="flat",
            focuscolor=SURFACE,
            padding=(6, 4),
            font=self._font(2),
        )
        style.map(
            "Ghost.TButton",
            background=[("pressed", SURFACE_2), ("active", ACCENT_SOFT), ("disabled", SURFACE)],
            foreground=[("active", ACCENT_DARK), ("disabled", DISABLED_FG)],
            bordercolor=[("active", SURFACE_2)],
        )
        # Numbered workflow buttons: accent-tinted so they read as the main path.
        style.configure(
            "Step.TButton",
            background=ACCENT_SOFT,
            foreground=ACCENT_DARK,
            bordercolor=ACCENT_SOFT,
            borderwidth=1,
            relief="flat",
            focuscolor=ACCENT_SOFT,
            padding=(12, 7),
            font=self._font(0, "bold"),
        )
        style.map(
            "Step.TButton",
            background=[("pressed", ACCENT), ("active", ACCENT), ("disabled", DISABLED_BG)],
            foreground=[("pressed", "#ffffff"), ("active", "#ffffff"), ("disabled", DISABLED_FG)],
            bordercolor=[("disabled", DISABLED_BG)],
        )

        style.configure("TSeparator", background=BORDER)
        style.configure(
            "TCombobox",
            background=SURFACE_2,
            fieldbackground=SURFACE_2,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            arrowcolor=ACCENT,
            selectbackground=ACCENT_SOFT,
            selectforeground=TEXT,
            relief="flat",
            borderwidth=1,
            padding=(9, 6),
            arrowsize=12,
            font=self._font(),
        )
        style.map(
            "TCombobox",
            background=[
                ("disabled", DISABLED_BG),
                ("pressed", SURFACE),
                ("active", SURFACE),
                ("readonly", SURFACE_2),
            ],
            fieldbackground=[
                ("disabled", DISABLED_BG),
                ("pressed", SURFACE),
                ("active", SURFACE),
                ("readonly", SURFACE_2),
            ],
            foreground=[("disabled", DISABLED_FG), ("readonly", TEXT)],
            bordercolor=[("disabled", DISABLED_BG), ("focus", ACCENT), ("active", ACCENT)],
            lightcolor=[("disabled", DISABLED_BG), ("focus", ACCENT), ("active", ACCENT)],
            darkcolor=[("disabled", DISABLED_BG), ("focus", ACCENT_DARK), ("active", ACCENT_DARK)],
            arrowcolor=[("disabled", DISABLED_FG), ("pressed", ACCENT_DARK), ("active", ACCENT_DARK), ("readonly", ACCENT)],
        )
        self.root.option_add("*TCombobox*Listbox.background", SURFACE_2)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_SOFT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", TEXT)
        self.root.option_add("*TCombobox*Listbox.activeStyle", "none")
        self.root.option_add("*TCombobox*Listbox.borderWidth", 1)
        self.root.option_add("*TCombobox*Listbox.highlightThickness", 1)
        self.root.option_add("*TCombobox*Listbox.highlightBackground", BORDER)
        self.root.option_add("*TCombobox*Listbox.highlightColor", ACCENT)
        self.root.option_add("*TCombobox*Listbox.font", self._font())
        style.configure(
            "Lethe.Horizontal.TProgressbar",
            background=ACCENT,
            troughcolor=DISABLED_BG,
            bordercolor=BORDER,
            lightcolor=ACCENT,
            darkcolor=ACCENT_DARK,
        )
        style.configure("TPanedwindow", background=BG)

    def _theme_key(self) -> str:
        return THEME_LABELS.get(self._theme_var.get(), "midnight")

    def _language_code(self) -> str:
        return LANGUAGE_CODES.get(self._language_var.get(), "ja")

    def _tr(self, key: str, **kwargs) -> str:
        return text_for(self._language_code(), key, **kwargs)

    def _font(self, delta: int = 0, weight: str | None = None) -> tuple[str, int] | tuple[str, int, str]:
        size = max(MIN_FONT_SIZE, self._font_size + delta)
        return (UI_FONT_FAMILY, size, weight) if weight else (UI_FONT_FAMILY, size)

    def _on_theme_change(self, _event=None) -> None:
        _apply_palette(self._theme_key(), self._dark_var.get())
        self.root.configure(background=BG)
        self._configure_style()
        self._restyle_direct_fonts()
        self._restyle_text_widgets()
        self._set_status(self.status["text"], self._status_kind)

    def _on_language_change(self, _event=None) -> None:
        self._build_menu()
        self._apply_language()

    def _apply_language(self) -> None:
        self.root.title(f"{APP_NAME} — {self._tr('tagline')}")
        self.tagline_label.config(text=f"  {self._tr('tagline')}")
        self.input_label.config(text=self._tr("input"))
        self.output_label.config(text=self._tr("output"))
        self.refresh_button.config(text="↻")
        self.output_refresh_button.config(text="↻")
        self._refresh_device_labels()
        self._refresh_output_labels()
        self.mic_label.config(text=self._tr("mic_capture"))
        self.system_label.config(text=self._tr("system_capture"))
        self.nr_label.config(text=self._tr("noise_reduce"))
        if hasattr(self, "hq_model_label"):
            self.hq_model_label.config(text=self._tr("hq_model_label"))
            self._refresh_hq_model_combo()
        if hasattr(self, "cancel_download_button"):
            self.cancel_download_button.configure(text=self._tr("cancel_download"))
        if hasattr(self, "settings_button"):
            self._refresh_settings_tooltip()
        if self._settings_window is not None and self.theme_label_widget is not None:
            self.theme_label_widget.config(text=self._tr("theme_label"))
            self.language_label_widget.config(text=self._tr("language_label"))
            self.dark_label_widget.config(text=self._tr("dark_label"))
            try:
                self._settings_window.title(self._tr("settings_title"))
            except tk.TclError:
                pass
        self.record_button.config(text=self._tr("stop" if self.is_recording else "record"))
        self.live_check.set_text(self._tr("live"))
        self.export_mp3_button.config(text=self._tr("save_mp3"))
        self.open_button.config(text=self._tr("open_audio"))
        self.transcript_title.config(text=self._tr("transcript"))
        self.export_txt_button.config(text=self._tr("save"))
        self.hq_button.config(
            text=self._tr("hq") if str(self.hq_button["state"]) != "disabled" or not self._busy else self.hq_button["text"]
        )
        self.refine_button.config(text=self._tr("refine") if not self._busy else self.refine_button["text"])
        self.minutes_button.config(text=self._tr("minutes") if not self._busy else self.minutes_button["text"])
        self.workflow_label.config(text=self._tr("workflow"))
        self.play_button.config(text=self._tr("pause") if self._player.is_playing else self._tr("play"))
        self.timestamp_hint.config(text=self._tr("click_timestamp"))
        self.notes_title.config(text=self._tr("notes"))
        self.notes_load_button.config(text=self._tr("load"))
        self.notes_save_button.config(text=self._tr("save"))
        self.notes_hint.config(text=self._tr("notes_hint"))
        if self.status["text"] in {text_for("ja", "status_ready"), text_for("en", "status_ready")}:
            self._set_status(self._tr("status_ready"), "ready")

    def _restyle_text_widgets(self) -> None:
        for widget_name in ("transcript", "notes_text"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.configure(
                    font=self._font(1),
                    background=SURFACE_2,
                    foreground=TEXT,
                    insertbackground=ACCENT,
                    highlightbackground=BORDER,
                    highlightcolor=ACCENT,
                    selectbackground=ACCENT_SOFT,
                    selectforeground=TEXT,
                )
        if hasattr(self, "wave"):
            self.wave.restyle()
        for widget_name in ("dark_check", "mic_check", "system_check", "nr_check", "live_check"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.set_font(self._font())
                widget.restyle()

    def _restyle_direct_fonts(self) -> None:
        if hasattr(self, "status_icon"):
            self.status_icon.configure(font=self._font(-2, "bold"))
        if hasattr(self, "status"):
            self.status.configure(font=self._font(0, "bold"))
        for widget_name in ("language_combo", "theme_combo", "device_combo", "output_combo", "llm_combo", "hq_model_combo"):
            widget = getattr(self, widget_name, None)
            if widget is None:
                continue
            try:
                widget.configure(font=self._font())
            except tk.TclError:
                pass

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label=self._tr("open_audio_menu"), command=self.open_audio, accelerator="Cmd/Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label=self._tr("open_session_menu"), command=self.open_session)
        file_menu.add_command(label=self._tr("save_session_menu"), command=self.save_session)
        file_menu.add_command(label=self._tr("export_dataset_menu"), command=self.export_dataset)
        file_menu.add_separator()
        file_menu.add_command(label=self._tr("save_transcript_menu"), command=self.export_transcript, accelerator="Cmd/Ctrl+S")
        file_menu.add_command(label=self._tr("save_mp3_menu"), command=self.export_mp3)
        menubar.add_cascade(label=self._tr("file_menu"), menu=file_menu)
        self.root.config(menu=menubar)

    def _build_header(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame")
        header.pack(side="top", fill="x", padx=10, pady=(10, 0))
        inner = ttk.Frame(header, style="Header.TFrame")
        inner.pack(fill="x", padx=PAD_X, pady=10)
        inner.columnconfigure(1, weight=1)
        ttk.Label(inner, text=APP_NAME, style="Wordmark.TLabel").grid(row=0, column=0, sticky="w")
        self.tagline_label = ttk.Label(inner, text=f"  {self._tr('tagline')}", style="Tagline.TLabel")
        self.tagline_label.grid(row=0, column=1, sticky="w", padx=(4, 12), pady=(2, 0))
        self.settings_button = ttk.Button(inner, text="⚙", width=3, command=self.open_settings, style="Ghost.TButton")
        self.settings_button.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self._settings_tooltip = Tooltip(self.settings_button, self._tr("settings"))
        inner.bind("<Configure>", lambda event: self.tagline_label.configure(wraplength=max(120, event.width // 2)))

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self.root, style="StatusBar.TFrame")
        bar.pack(side="bottom", fill="x")
        self._status_bar_top = tk.Frame(bar, bd=0, height=1, background=BORDER)
        self._status_bar_top.pack(side="top", fill="x")
        inner = ttk.Frame(bar, style="StatusBar.TFrame")
        inner.pack(side="top", fill="x", padx=PAD_X, pady=(6, 10))
        inner.columnconfigure(2, weight=1)

        self.status_banner = tk.Frame(inner, bd=0, highlightthickness=1)
        self.status_banner.grid(row=0, column=0, sticky="w", ipadx=8, ipady=3)
        self.status_icon = tk.Label(self.status_banner, text="OK", width=3, anchor="center", font=self._font(-2, "bold"))
        self.status_icon.pack(side="left", padx=(0, 7))
        self.status = tk.Label(self.status_banner, text=self._tr("status_ready"), font=self._font(0, "bold"))
        self.status.pack(side="left")
        self.cancel_download_button = ttk.Button(
            self.status_banner,
            text=self._tr("cancel_download"),
            command=self._cancel_active_download,
        )

        self.meter_caption = ttk.Label(inner, text="", style="StatusBarHint.TLabel")
        self.meter_caption.grid(row=0, column=1, sticky="w", padx=(12, 8))
        self.wave = WaveMeter(inner, colors=_ui_colors, height=32)
        self.wave.grid(row=0, column=2, sticky="ew")
        self.timer = ttk.Label(inner, text="00:00", style="StatusTimer.TLabel")
        self.timer.grid(row=0, column=3, sticky="e", padx=(14, 0))
        self._set_status(self._tr("status_ready"), "ready")

    # ---------- settings dialog ----------

    def open_settings(self) -> None:
        win = self._settings_window
        if win is not None:
            try:
                win.deiconify()
                win.lift()
                win.focus_set()
                return
            except tk.TclError:
                self._settings_window = None
        self._build_settings_dialog()

    def _build_settings_dialog(self) -> None:
        win = tk.Toplevel(self.root)
        self._settings_window = win
        win.title(self._tr("settings_title"))
        win.configure(background=BG)
        win.resizable(False, False)
        win.transient(self.root)
        x = self.root.winfo_rootx() + max(40, (self.root.winfo_width() - 360) // 2)
        y = self.root.winfo_rooty() + 80
        win.geometry(f"+{x}+{y}")

        body = ttk.Frame(win, style="Card.TFrame")
        body.pack(side="top", fill="both", expand=True, padx=PAD_X, pady=(PAD_Y, 6))
        body.columnconfigure(1, weight=1)

        self.theme_label_widget = ttk.Label(body, text=self._tr("theme_label"), style="Card.TLabel")
        self.theme_label_widget.grid(row=0, column=0, sticky="w", padx=(0, 16), pady=(0, 10))
        self.theme_combo = ttk.Combobox(
            body,
            state="readonly",
            width=18,
            values=list(THEME_LABELS),
            textvariable=self._theme_var,
            font=self._font(),
        )
        self.theme_combo.grid(row=0, column=1, sticky="ew", pady=(0, 10))
        self.theme_combo.bind("<<ComboboxSelected>>", self._on_theme_change)

        self.language_label_widget = ttk.Label(body, text=self._tr("language_label"), style="Card.TLabel")
        self.language_label_widget.grid(row=1, column=0, sticky="w", padx=(0, 16), pady=(0, 10))
        self.language_combo = ttk.Combobox(
            body,
            state="readonly",
            width=18,
            values=list(LANGUAGE_CODES),
            textvariable=self._language_var,
            font=self._font(),
        )
        self.language_combo.grid(row=1, column=1, sticky="ew", pady=(0, 10))
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_change)

        self.dark_label_widget = ttk.Label(body, text=self._tr("dark_label"), style="Card.TLabel")
        self.dark_label_widget.grid(row=2, column=0, sticky="w", padx=(0, 16), pady=(0, 4))
        self.dark_check = Switch(
            body,
            text="",
            variable=self._dark_var,
            colors=_ui_colors,
            command=self._on_theme_change,
            font=self._font(),
            default_font_size=DEFAULT_FONT_SIZE,
        )
        self.dark_check.grid(row=2, column=1, sticky="w")

        footer = ttk.Frame(win, style="Card.TFrame")
        footer.pack(side="bottom", fill="x", padx=PAD_X, pady=(6, PAD_Y))
        ttk.Button(footer, text=self._tr("close"), command=self._close_settings).pack(side="right")

        win.protocol("WM_DELETE_WINDOW", self._close_settings)
        win.bind("<Escape>", lambda _e: self._close_settings())

    def _close_settings(self) -> None:
        win = self._settings_window
        self._settings_window = None
        self.theme_combo = None
        self.language_combo = None
        self.dark_check = None
        self.theme_label_widget = None
        self.language_label_widget = None
        self.dark_label_widget = None
        if win is not None:
            try:
                win.destroy()
            except tk.TclError:
                pass

    def _refresh_settings_tooltip(self) -> None:
        if self._settings_tooltip is not None:
            self._settings_tooltip.text = self._tr("settings")

    # ---------- main layout ----------

    def _build_controls(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=4, uniform="controls")
        parent.columnconfigure(1, weight=3, uniform="controls")
        parent.columnconfigure(2, weight=3, uniform="controls")

        # --- source: input device + recording options ---
        source = ttk.Frame(parent, style="Card.TFrame")
        source.grid(row=0, column=0, sticky="nsew", padx=(PAD_X, 8), pady=(PAD_Y, 8))
        source.columnconfigure(0, minsize=130)
        source.columnconfigure(1, minsize=176)
        source.columnconfigure(2, weight=1)
        self.input_label = ttk.Label(source, text=self._tr("input"), style="Card.TLabel")
        self.input_label.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.device_combo = ttk.Combobox(source, state="readonly", width=19, font=self._font())
        self.device_combo.grid(row=0, column=1, sticky="w", padx=(8, 12), pady=(0, 6))
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_change)
        self.refresh_button = ttk.Button(source, text="↻", width=4, command=self.refresh_devices)
        self.refresh_button.grid(row=0, column=2, sticky="w", pady=(0, 6))
        Tooltip(self.refresh_button, self._tr("refresh_input"))
        self.output_label = ttk.Label(source, text=self._tr("output"), style="Card.TLabel")
        self.output_label.grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.output_combo = ttk.Combobox(source, state="readonly", width=19, font=self._font())
        self.output_combo.grid(row=1, column=1, sticky="w", padx=(8, 12), pady=(0, 6))
        self.output_combo.bind("<<ComboboxSelected>>", self._on_output_change)
        self.output_refresh_button = ttk.Button(source, text="↻", width=4, command=self.refresh_outputs)
        self.output_refresh_button.grid(row=1, column=2, sticky="w", pady=(0, 6))
        Tooltip(self.output_refresh_button, self._tr("refresh_output"))
        ttk.Label(source, text="LLM", style="Card.TLabel").grid(row=2, column=0, sticky="w")
        self.llm_combo = ttk.Combobox(
            source,
            state="readonly",
            width=19,
            values=self._llm_models,
            textvariable=self._llm_model_var,
            font=self._font(),
        )
        self.llm_combo.grid(row=2, column=1, sticky="w", padx=(8, 12), pady=(0, 6))
        self.mic_label = ttk.Label(source, text=self._tr("mic_capture"), style="Card.TLabel")
        self.mic_label.grid(row=3, column=0, sticky="w", pady=(4, 4))
        self.mic_check = Switch(
            source,
            text="",
            variable=self._mic_capture_var,
            colors=_ui_colors,
            command=self._on_mic_capture_change,
            font=self._font(),
            default_font_size=DEFAULT_FONT_SIZE,
        )
        self.mic_check.grid(row=3, column=1, sticky="w", padx=(8, 12), pady=(4, 4))
        Tooltip(self.mic_check, TOOLTIP_MIC_CAPTURE)
        self.system_label = ttk.Label(source, text=self._tr("system_capture"), style="Card.TLabel")
        self.system_label.grid(row=4, column=0, sticky="w", pady=(4, 4))
        self.system_check = Switch(
            source,
            text="",
            variable=self._system_capture_var,
            colors=_ui_colors,
            command=self._on_system_capture_change,
            font=self._font(),
            default_font_size=DEFAULT_FONT_SIZE,
        )
        self.system_check.grid(row=4, column=1, sticky="w", padx=(8, 12), pady=(4, 4))
        Tooltip(self.system_check, TOOLTIP_SYSTEM_CAPTURE)
        self.nr_label = ttk.Label(source, text=self._tr("noise_reduce"), style="Card.TLabel")
        self.nr_label.grid(row=5, column=0, sticky="w")
        self.nr_check = Switch(
            source,
            text="",
            variable=self._nr_var,
            colors=_ui_colors,
            font=self._font(),
            default_font_size=DEFAULT_FONT_SIZE,
        )
        self.nr_check.grid(row=5, column=1, sticky="w", padx=(8, 12))
        Tooltip(self.nr_check, TOOLTIP_NR)

        self.hq_model_label = ttk.Label(source, text=self._tr("hq_model_label"), style="Card.TLabel")
        self.hq_model_label.grid(row=6, column=0, sticky="w", pady=(8, 2))
        self.hq_model_combo = ttk.Combobox(
            source,
            state="readonly",
            width=19,
            textvariable=self._hq_model_var,
            font=self._font(),
        )
        self.hq_model_combo.grid(row=6, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 2))
        self.hq_model_combo.bind("<<ComboboxSelected>>", self._on_hq_model_change)
        self._hq_model_tooltip = Tooltip(self.hq_model_combo, TOOLTIP_HQ_MODEL)
        self.hq_model_status = ttk.Label(source, text="", style="Hint.TLabel")
        self.hq_model_status.grid(row=7, column=0, columnspan=3, sticky="w", padx=(0, 0), pady=(0, 4))
        self._refresh_hq_model_combo()

        playback = ttk.Frame(source, style="Card.TFrame")
        playback.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        playback.columnconfigure(2, weight=1)
        self.play_button = ttk.Button(playback, text=self._tr("play"), width=12, command=self.toggle_play, state="disabled")
        self.play_button.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 4))
        Tooltip(self.play_button, TOOLTIP_PLAY)
        self.stop_play_button = ttk.Button(playback, text="■", width=4, command=self.stop_play, state="disabled")
        self.stop_play_button.grid(row=0, column=1, sticky="w", padx=(4, 0), pady=(0, 4))
        self.position_label = ttk.Label(playback, text="00:00 / 00:00", style="Hint.TLabel")
        self.position_label.grid(row=0, column=2, sticky="w", padx=(10, 0), pady=(0, 4))
        self.timestamp_hint = ttk.Label(playback, text=self._tr("click_timestamp"), style="Hint.TLabel")
        self.timestamp_hint.grid(row=1, column=0, columnspan=3, sticky="w")
        playback.bind("<Configure>", lambda event: self.timestamp_hint.configure(wraplength=max(160, event.width)), add="+")
        self.refresh_devices()
        self.refresh_outputs()
        self._update_capture_controls()

        # --- controls: record + live | open audio + export mp3 ---
        controls = ttk.Frame(parent, style="Card.TFrame")
        controls.grid(row=0, column=1, sticky="nsew", padx=8, pady=(PAD_Y, 8))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)
        self.record_button = ttk.Button(
            controls, text=self._tr("record"), width=14, style="Accent.TButton", command=self.toggle_record
        )
        self.record_button.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        Tooltip(self.record_button, TOOLTIP_RECORD)
        self.live_check = Switch(
            controls,
            text=self._tr("live"),
            variable=self._live_var,
            colors=_ui_colors,
            font=self._font(),
            default_font_size=DEFAULT_FONT_SIZE,
        )
        self.live_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))
        Tooltip(self.live_check, TOOLTIP_LIVE)
        self._update_capture_controls()
        self.export_mp3_button = ttk.Button(
            controls, text=self._tr("save_mp3"), width=11, command=self.export_mp3, state="disabled"
        )
        self.export_mp3_button.grid(row=2, column=1, sticky="ew", padx=(6, 0))
        Tooltip(self.export_mp3_button, TOOLTIP_MP3)
        self.open_button = ttk.Button(controls, text=self._tr("open_audio"), width=11, command=self.open_audio)
        self.open_button.grid(row=2, column=0, sticky="ew", padx=(0, 6))
        Tooltip(self.open_button, TOOLTIP_OPEN)

        # --- numbered workflow actions ---
        actions = ttk.Frame(parent, style="Card.TFrame")
        actions.grid(row=0, column=2, sticky="nsew", padx=(8, PAD_X), pady=(PAD_Y, 8))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        self.hq_button = ttk.Button(
            actions, text=self._tr("hq"), style="Step.TButton", command=self.hq_transcribe, state="disabled"
        )
        self.hq_button.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        Tooltip(self.hq_button, TOOLTIP_HQ)
        self.refine_button = ttk.Button(
            actions, text=self._tr("refine"), style="Step.TButton", command=self.refine_transcript, state="disabled"
        )
        self.refine_button.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        Tooltip(self.refine_button, TOOLTIP_REFINE)
        self.minutes_button = ttk.Button(
            actions, text=self._tr("minutes"), style="Step.TButton", command=self.generate_minutes, state="disabled"
        )
        self.minutes_button.grid(row=2, column=0, columnspan=2, sticky="ew")
        Tooltip(self.minutes_button, TOOLTIP_MINUTES)

        self.workflow_label = ttk.Label(actions, text=self._tr("workflow"), style="Workflow.TLabel")
        self.workflow_label.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        actions.bind("<Configure>", lambda event: self.workflow_label.configure(wraplength=max(160, event.width)), add="+")

    def _build_transcript(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        transcript_header = ttk.Frame(parent, style="Card.TFrame")
        transcript_header.grid(row=0, column=0, sticky="ew", padx=PAD_X, pady=(PAD_Y, 6))
        self.transcript_title = ttk.Label(transcript_header, text=self._tr("transcript"), style="Title.TLabel")
        self.transcript_title.pack(side="left")
        self.export_txt_button = ttk.Button(
            transcript_header, text=self._tr("save"), width=8, command=self.export_transcript, state="disabled"
        )
        self.export_txt_button.pack(side="right")
        Tooltip(self.export_txt_button, TOOLTIP_EXPORT_TXT)

        text_frame = ttk.Frame(parent, style="Card.TFrame")
        text_frame.grid(row=1, column=0, sticky="nsew", padx=PAD_X, pady=(0, PAD_Y))
        self.transcript = tk.Text(
            text_frame,
            wrap="word",
            font=self._font(1),
            height=10,
            undo=True,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            background=SURFACE_2,
            foreground=TEXT,
            insertbackground=ACCENT,
            selectbackground=ACCENT_SOFT,
            padx=10,
            pady=8,
            spacing3=5,
        )
        scrollbar = ttk.Scrollbar(text_frame, command=self.transcript.yview)
        self.transcript.configure(yscrollcommand=scrollbar.set)
        self.transcript.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.transcript.bind("<KeyRelease>", lambda _e: self._sync_transcript_actions())
        self.transcript.tag_configure("seek", foreground=ACCENT, underline=True)
        self.transcript.tag_bind("seek", "<Button-1>", self._on_timestamp_click)
        self.transcript.tag_bind("seek", "<Enter>", lambda _e: self.transcript.config(cursor="hand2"))
        self.transcript.tag_bind("seek", "<Leave>", lambda _e: self.transcript.config(cursor="xterm"))

    def _build_notes(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(3, weight=1)
        parent.columnconfigure(0, weight=1)

        notes_header = ttk.Frame(parent, style="Card.TFrame")
        notes_header.grid(row=0, column=0, sticky="ew", padx=PAD_X, pady=(PAD_Y, 4))
        self.notes_title = ttk.Label(notes_header, text=self._tr("notes"), style="Title.TLabel")
        self.notes_title.pack(side="left")
        self.notes_load_button = ttk.Button(notes_header, text=self._tr("load"), width=8, command=self.load_notes)
        self.notes_load_button.pack(side="right")
        self.notes_save_button = ttk.Button(notes_header, text=self._tr("save"), width=8, command=self.save_notes)
        self.notes_save_button.pack(side="right", padx=(0, 6))

        self.notes_hint = ttk.Label(
            parent,
            text=self._tr("notes_hint"),
            style="Hint.TLabel",
            wraplength=380,
            justify="left",
        )
        self.notes_hint.grid(row=1, column=0, sticky="ew", padx=PAD_X, pady=(0, 6))
        parent.bind(
            "<Configure>", lambda event: self.notes_hint.configure(wraplength=max(160, event.width - PAD_X * 2)), add="+"
        )

        ttk.Separator(parent, orient="horizontal").grid(row=2, column=0, sticky="ew", padx=PAD_X)

        notes_frame = ttk.Frame(parent, style="Card.TFrame")
        notes_frame.grid(row=3, column=0, sticky="nsew", padx=PAD_X, pady=(10, PAD_Y))
        self.notes_text = tk.Text(
            notes_frame,
            wrap="word",
            font=self._font(1),
            undo=True,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            background=SURFACE_2,
            foreground=TEXT,
            insertbackground=ACCENT,
            selectbackground=ACCENT_SOFT,
            selectforeground=TEXT,
            padx=10,
            pady=8,
        )
        notes_scroll = ttk.Scrollbar(notes_frame, command=self.notes_text.yview)
        self.notes_text.configure(yscrollcommand=notes_scroll.set)
        self.notes_text.pack(side="left", fill="both", expand=True)
        notes_scroll.pack(side="right", fill="y")
        self.notes_text.bind("<KeyRelease>", self._on_notes_change)

    # ---------- keyboard shortcuts ----------

    def _bind_shortcuts(self) -> None:
        self.root.bind("<space>", self._on_space)
        for seq in ("<Command-s>", "<Control-s>"):
            self.root.bind(seq, lambda _e: self._shortcut_export())
        for seq in ("<Command-o>", "<Control-o>"):
            self.root.bind(seq, lambda _e: self.open_audio())
        for seq in ("<Command-comma>", "<Control-comma>"):
            self.root.bind(seq, lambda _e: self.open_settings())
        for seq in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>", "<Command-plus>", "<Command-equal>"):
            self.root.bind_all(seq, self._increase_font_size, add="+")
        for seq in ("<Control-minus>", "<Control-KP_Subtract>", "<Command-minus>"):
            self.root.bind_all(seq, self._decrease_font_size, add="+")

    def _on_space(self, _event):
        widget = self.root.focus_get()
        if widget is not None and widget.winfo_class() in ("Text", "Entry", "TEntry", "TCombobox", "TButton", "Button"):
            return None
        self.toggle_record()
        return "break"

    def _shortcut_export(self):
        if str(self.export_txt_button["state"]) == "normal":
            self.export_transcript()
        return "break"

    def _increase_font_size(self, _event=None):
        return self._adjust_font_size(1)

    def _decrease_font_size(self, _event=None):
        return self._adjust_font_size(-1)

    def _adjust_font_size(self, delta: int):
        new_size = _coerce_font_size(self._font_size + delta)
        if new_size == self._font_size:
            return "break"
        self._font_size = new_size
        self._configure_style()
        self._restyle_direct_fonts()
        self._restyle_text_widgets()
        return "break"

    # ---------- recording lifecycle ----------

    def toggle_record(self) -> None:
        if self.is_recording:
            self._stop_recording()
        elif not self._busy:
            self._start_recording()

    def _start_recording(self) -> None:
        mic_capture = self._mic_capture_var.get()
        system_capture = self._system_capture_var.get() and system_output_capture_available()
        audio_capture = mic_capture or system_capture
        live_requested = self._live_var.get() and audio_capture
        live_model_missing = False
        if live_requested:
            from llm.whisper_models import is_model_cached

            live_model_missing = not is_model_cached(WHISPER_MODEL)
        live = live_requested and not live_model_missing
        nr = self._nr_var.get() and mic_capture
        preprocessor = self._build_preprocessor() if nr else None
        self._player.reset()
        self._analysis_audio_path = None
        if audio_capture:
            self._clear_transcript()
        self.recorder.cleanup()  # drop the previous take's temp WAV
        if live:
            from llm.transcribe_stream import StreamingTranscriber

            self._transcriber = StreamingTranscriber(
                on_event=lambda e: self._transcript_queue.put(e),
                model_size=WHISPER_MODEL,
                language=WHISPER_LANGUAGE,
                source_sr=SAMPLE_RATE,
                chunk_seconds=WHISPER_CHUNK_SECONDS,
                prompt_provider=lambda: self._notes_cache,
                preprocessor=preprocessor,
            )
            self._transcriber.start()
            self.recorder = MicRecorder(on_chunk=self._transcriber.feed_int16)
        else:
            self.recorder = MicRecorder()

        if audio_capture:
            try:
                self.recorder.start(
                    device=self._device_index,
                    capture_mic=mic_capture,
                    capture_system=system_capture,
                    output_device_id=self._output_device_id,
                )
            except Exception as exc:
                if self._transcriber is not None:
                    self._transcriber.stop()
                    self._transcriber = None
                help_text = MIC_HELP
                if system_capture and not mic_capture:
                    help_text = SYSTEM_AUDIO_HELP
                elif system_capture:
                    help_text = f"{MIC_HELP}{SYSTEM_AUDIO_HELP}"
                messagebox.showerror(self._tr("start_record_error"), f"{type(exc).__name__}: {exc}{help_text}")
                return

        self.is_recording = True
        self._elapsed = 0
        self.timer.config(text="00:00")
        tag_pairs = (
            (self._tr("pc_audio_tag"), system_capture),
            (self._tr("mic_off_tag"), system_capture and not mic_capture),
            (self._tr("no_audio_tag"), not audio_capture),
            (self._tr("live_tag"), live),
            (self._tr("noise_tag"), nr),
            (self._tr("record_only_tag"), live_model_missing),
        )
        tags = [text for text, on in tag_pairs if on]
        suffix = f"（{' / '.join(tags)}）" if tags else ""
        self._set_status(f"{self._tr('recording')}{suffix}...", "recording")
        self.record_button.config(text=self._tr("stop"), style="Danger.TButton")
        self.export_mp3_button.config(state="disabled")
        self.open_button.config(state="disabled")
        self.hq_button.config(state="disabled")
        self._set_transcript_actions(False)
        self._set_playback_enabled(False)
        self.mic_check.state(["disabled"])
        self.system_check.state(["disabled"])
        self.live_check.state(["disabled"])
        self.nr_check.state(["disabled"])
        self.device_combo.state(["disabled"])
        self.refresh_button.config(state="disabled")
        self.output_combo.state(["disabled"])
        self.output_refresh_button.config(state="disabled")
        self.meter_caption.config(text=self._tr("input_level") if audio_capture else self._tr("mic_off_level"))
        self.wave.set_mode("recording" if audio_capture else "idle")
        self.wave.set_level(0)
        self._schedule_tick()

    def _stop_recording(self) -> None:
        live_was_on = self._transcriber is not None
        self.recorder.stop()
        self.is_recording = False
        self._cancel_tick()
        self._meter_level = 0.0
        self.wave.set_mode("idle")
        self.wave.set_level(0)
        self.meter_caption.config(text="")
        duration = self.recorder.duration_seconds if self.recorder.has_recording else float(self._elapsed)
        self._set_status(self._tr("stopped", seconds=duration), "ready")
        self.record_button.config(text=self._tr("record"), style="Accent.TButton")
        self.mic_check.state(["!disabled"])
        self.system_check.state(["!disabled"] if system_output_capture_available() else ["disabled"])
        self._update_capture_controls()
        self.open_button.config(state="normal")
        if self.recorder.has_recording:
            self.export_mp3_button.config(state="normal")
            self.hq_button.config(state="normal")
            self._player.load(self.recorder.audio_float32, SAMPLE_RATE)
            self._set_playback_enabled(True)
        if self._transcriber is not None:
            self._set_status(self._tr("finalizing"), "busy")
            self.root.update_idletasks()
            self._transcriber.stop()
            self._drain_transcript_queue()
            self._transcriber = None
            self._set_status(self._tr("stopped", seconds=duration), "ready")
        self._sync_transcript_actions()
        # Two-tier: when a live preview was shown, automatically run the
        # accurate full-file pass so the transcript settles on the HQ result.
        if self.recorder.has_recording and not hq_model_cached(self._hq_model):
            self._set_audio_ready_model_missing(self._hq_model)
        if live_was_on and self.recorder.has_recording:
            if hq_model_cached(self._hq_model):
                self._run_hq(self.recorder.wav_path, prompt_download=False)
            else:
                self._set_audio_ready_model_missing(self._hq_model)

    def _build_preprocessor(self):
        """Return a callable(audio_f32, sr) -> audio_f32 that applies the pipeline."""
        from recorder.preprocess import preprocess_float32

        def run(audio_f32, sr):
            return preprocess_float32(audio_f32, sr, bandpass=True, denoise=True)

        return run

    # ---------- HQ model selection ----------

    def _refresh_hq_model_combo(self) -> None:
        """Rebuild the HQ model dropdown with cache status + size/RAM/quality."""
        from llm.whisper_models import MODEL_CATALOG, is_model_cached

        catalog = list(MODEL_CATALOG)
        if not any(entry["id"] == self._hq_model for entry in catalog):
            # Keep an unrecognized configured value visible without specs.
            catalog.append(
                {
                    "id": self._hq_model,
                    "label": self._hq_model,
                    "disk_gb": 0.0,
                    "ram_gb": 0.0,
                    "quality": 0,
                    "speed": 0,
                    "note": "",
                    "note_en": "",
                }
            )
        values: list[str] = []
        ids: list[str] = []
        for entry in catalog:
            cached = is_model_cached(entry["id"])
            key = "hq_model_combo_entry_cached" if cached else "hq_model_combo_entry_uncached"
            values.append(
                self._tr(
                    key,
                    label=entry["label"],
                    size=_format_gb(entry["disk_gb"]) if entry["disk_gb"] else "?",
                    ram=_format_gb(entry["ram_gb"]) if entry["ram_gb"] else "?",
                    quality=_rating_bar(entry["quality"]),
                    speed=_rating_bar(entry["speed"]),
                )
            )
            ids.append(entry["id"])
        self._hq_combo_values = values
        self._hq_combo_ids = ids
        self.hq_model_combo["values"] = values
        try:
            idx = ids.index(self._hq_model)
        except ValueError:
            idx = 0
            self._hq_model = ids[0] if ids else self._hq_model
        self.hq_model_combo.current(idx)
        self._update_hq_model_status()
        tooltip_text = TOOLTIP_HQ_MODEL if self._language_code() == "ja" else TOOLTIP_HQ_MODEL_EN
        try:
            self._hq_model_tooltip.text = tooltip_text
        except AttributeError:
            pass

    def _update_hq_model_status(self) -> None:
        if not hasattr(self, "hq_model_status"):
            return
        from llm.whisper_models import is_model_cached, model_info

        def status_for(model_id: str) -> str:
            info = model_info(model_id)
            if is_model_cached(model_id):
                return self._tr("model_status_installed")
            if info and info["disk_gb"]:
                return self._tr("model_status_missing_with_size", size=_format_gb(info["disk_gb"]))
            return self._tr("model_status_missing")

        self.hq_model_status.config(
            text=self._tr(
                "model_install_status",
                live_model=WHISPER_MODEL,
                live_status=status_for(WHISPER_MODEL),
                hq_model=self._hq_model,
                hq_status=status_for(self._hq_model),
            )
        )

    def _on_hq_model_change(self, _event=None) -> None:
        idx = self.hq_model_combo.current()
        if 0 <= idx < len(self._hq_combo_ids):
            self._hq_model = self._hq_combo_ids[idx]
        self._update_hq_model_status()

    # ---------- input device ----------

    def refresh_devices(self) -> None:
        self._devices = list_input_devices()
        self._refresh_device_labels()
        if self._device_index is not None:
            for i, (_label, idx) in enumerate(self._devices):
                if idx == self._device_index:
                    self.device_combo.current(i)
                    self._update_capture_controls()
                    return
        self.device_combo.current(0)
        self._device_index = None
        self._update_capture_controls()

    def _refresh_device_labels(self) -> None:
        if not hasattr(self, "device_combo"):
            return
        current = self.device_combo.current()
        values = [
            self._tr("system_default_input") if i == 0 and idx is None else label
            for i, (label, idx) in enumerate(self._devices)
        ]
        self.device_combo["values"] = values
        if 0 <= current < len(values):
            self.device_combo.current(current)

    def _on_mic_capture_change(self) -> None:
        self._update_capture_controls()

    def _update_mic_capture_controls(self) -> None:
        self._update_capture_controls()

    def _on_system_capture_change(self) -> None:
        self._update_capture_controls()

    def refresh_outputs(self) -> None:
        self._output_devices = list_output_devices()
        self._refresh_output_labels()
        if self._output_device_id is not None:
            for i, (_label, device_id) in enumerate(self._output_devices):
                if device_id == self._output_device_id:
                    self.output_combo.current(i)
                    self._update_capture_controls()
                    return
        self.output_combo.current(0)
        self._output_device_id = None
        self._update_capture_controls()

    def _refresh_output_labels(self) -> None:
        if not hasattr(self, "output_combo"):
            return
        current = self.output_combo.current()
        values = [
            self._tr("system_default_output") if i == 0 and device_id is None else label
            for i, (label, device_id) in enumerate(self._output_devices)
        ]
        self.output_combo["values"] = values
        if 0 <= current < len(values):
            self.output_combo.current(current)

    def _on_output_change(self, _event) -> None:
        idx = self.output_combo.current()
        if 0 <= idx < len(self._output_devices):
            self._output_device_id = self._output_devices[idx][1]

    def _update_capture_controls(self) -> None:
        if self.is_recording:
            return
        if not all(
            hasattr(self, name)
            for name in (
                "device_combo",
                "refresh_button",
                "output_combo",
                "output_refresh_button",
                "system_check",
                "live_check",
                "nr_check",
            )
        ):
            return
        mic_enabled = self._mic_capture_var.get()
        system_available = system_output_capture_available()
        system_enabled = self._system_capture_var.get() and system_available
        if self._system_capture_var.get() and not system_available:
            self._system_capture_var.set(False)
            system_enabled = False

        self.device_combo.state(["!disabled", "readonly"] if mic_enabled else ["disabled"])
        self.refresh_button.config(state="normal" if mic_enabled else "disabled")
        self.output_combo.state(["!disabled", "readonly"] if system_available else ["disabled"])
        self.output_refresh_button.config(state="normal" if system_available else "disabled")
        self.system_check.state(["!disabled"] if system_available else ["disabled"])
        self.live_check.state(["!disabled"] if mic_enabled or system_enabled else ["disabled"])
        self.nr_check.state(["!disabled"] if mic_enabled else ["disabled"])

    def _on_device_change(self, _event) -> None:
        idx = self.device_combo.current()
        if 0 <= idx < len(self._devices):
            self._device_index = self._devices[idx][1]

    # ---------- playback ----------

    def _set_playback_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled and self._player.has_audio else "disabled"
        self.play_button.config(state=state)
        self.stop_play_button.config(state=state)

    def toggle_play(self) -> None:
        if not self._player.has_audio:
            return
        if self._player.is_playing:
            self._player.pause()
            self.play_button.config(text=self._tr("play"))
        else:
            self._player.play()
            self.play_button.config(text=self._tr("pause"))

    def stop_play(self) -> None:
        self._player.reset()
        self.play_button.config(text=self._tr("play"))

    def _seek(self, seconds: float) -> None:
        if not self._player.has_audio:
            return
        self._player.play(from_seconds=seconds)
        self.play_button.config(text=self._tr("pause"))

    def _on_timestamp_click(self, event):
        index = self.transcript.index(f"@{event.x},{event.y}")
        line_no = index.split(".")[0]
        line_text = self.transcript.get(f"{line_no}.0", f"{line_no}.end")
        seconds = _parse_leading_timestamp(line_text)
        if seconds is not None:
            self._seek(seconds)
        return "break"

    def _retag_timestamps(self) -> None:
        """(Re)apply the clickable 'seek' tag to every leading [MM:SS] prefix."""
        self.transcript.tag_remove("seek", "1.0", "end")
        last_line = int(self.transcript.index("end-1c").split(".")[0])
        for line_no in range(1, last_line + 1):
            line_text = self.transcript.get(f"{line_no}.0", f"{line_no}.end")
            m = TIMESTAMP_RE.match(line_text)
            if m:
                self.transcript.tag_add("seek", f"{line_no}.0", f"{line_no}.{m.end()}")

    # ---------- exports ----------

    def export_mp3(self) -> None:
        if not self.recorder.has_recording:
            messagebox.showinfo(self._tr("save_mp3"), self._tr("no_recording"))
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".mp3",
            filetypes=[("MP3 音声", "*.mp3"), ("すべてのファイル", "*.*")],
            initialfile=_suggested_mp3_filename(),
            title=self._tr("save_recording_title"),
            **_initialdir_option("datasets_dir"),
        )
        if not path:
            return
        preprocessor = self._build_preprocessor() if self._nr_var.get() else None
        try:
            self.recorder.encode_mp3(path, preprocessor=preprocessor)
        except Exception as exc:
            messagebox.showerror(self._tr("generic_error"), self._tr("save_error", error=exc))
            return
        messagebox.showinfo(self._tr("saved"), self._tr("save_to", path=path))

    def export_transcript(self) -> None:
        if not self._has_transcript_text():
            messagebox.showinfo(self._tr("save_transcript_title"), self._tr("no_transcript"))
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("テキスト", "*.txt"), ("Markdown", "*.md"), ("すべてのファイル", "*.*")],
            initialfile="transcript.txt",
            title=self._tr("save_transcript_title"),
            **_initialdir_option("datasets_dir"),
        )
        if not path:
            return
        text = self.transcript.get("1.0", "end").rstrip() + "\n"
        try:
            Path(path).write_text(text, encoding="utf-8")
        except Exception as exc:
            messagebox.showerror(self._tr("generic_error"), self._tr("save_error", error=exc))
            return
        messagebox.showinfo(self._tr("saved"), self._tr("save_to", path=path))

    def export_dataset(self) -> None:
        transcript = self.transcript.get("1.0", "end").rstrip()
        notes = self.notes_text.get("1.0", "end").rstrip()
        if not (self.recorder.has_recording or self._player.has_audio):
            messagebox.showinfo(self._tr("export_dataset_title"), self._tr("no_audio"))
            return
        if not transcript:
            messagebox.showinfo(self._tr("export_dataset_title"), self._tr("no_transcript"))
            return
        path = filedialog.asksaveasfilename(
            filetypes=[("Dataset folder", "*")],
            initialfile=_suggested_dataset_name(),
            title=self._tr("export_dataset_title"),
            **_initialdir_option("datasets_dir"),
        )
        if not path:
            return
        folder = Path(path)
        dataset_id = _safe_filename_part(folder.name, fallback="dataset")
        audio_path = folder / DATASET_AUDIO
        transcript_path = folder / DATASET_TRANSCRIPT
        memo_path = folder / DATASET_MEMO
        manifest_path = folder / DATASET_MANIFEST
        try:
            folder.mkdir(parents=True, exist_ok=True)
            self._write_dataset_audio(audio_path)
            transcript_path.write_text(transcript + "\n", encoding="utf-8")
            memo_path.write_text(notes + "\n", encoding="utf-8")
            duration = self.recorder.duration_seconds if self.recorder.has_recording else self._player.duration
            manifest = _dataset_manifest(dataset_id, duration)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            messagebox.showerror(self._tr("dataset_save_failed"), f"{type(exc).__name__}: {exc}")
            return
        messagebox.showinfo(self._tr("saved"), self._tr("dataset_save_to", path=folder))

    def _write_dataset_audio(self, path: str | Path) -> None:
        preprocessor = self._build_preprocessor() if self.recorder.has_recording and self._nr_var.get() else None
        if self.recorder.has_recording:
            self.recorder.encode_mp3(path, preprocessor=preprocessor)
            return
        _encode_mp3_float32(path, self._player.audio_float32, self._player.sample_rate)

    # ---------- notes ----------

    def _on_notes_change(self, _event) -> None:
        self._notes_cache = self.notes_text.get("1.0", "end").strip()

    def save_notes(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("テキスト", "*.txt"), ("Markdown", "*.md"), ("すべてのファイル", "*.*")],
            initialfile="notes.txt",
            title=self._tr("save_notes_title"),
            **_initialdir_option("datasets_dir"),
        )
        if not path:
            return
        text = self.notes_text.get("1.0", "end").rstrip() + "\n"
        try:
            Path(path).write_text(text, encoding="utf-8")
        except Exception as exc:
            messagebox.showerror(self._tr("generic_error"), self._tr("save_error", error=exc))

    def load_notes(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("テキスト", "*.txt"), ("Markdown", "*.md"), ("すべてのファイル", "*.*")],
            title=self._tr("load_notes_title"),
            **_initialdir_option("datasets_dir"),
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except Exception as exc:
            messagebox.showerror(self._tr("generic_error"), self._tr("load_error", error=exc))
            return
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", text)
        self._on_notes_change(None)

    # ---------- open existing audio file ----------

    def open_audio(self) -> None:
        if self.is_recording or self._busy:
            return
        path = filedialog.askopenfilename(
            title=self._tr("open_audio_title"),
            filetypes=AUDIO_FILETYPES,
            **_initialdir_option("datasets_dir"),
        )
        if not path:
            return
        self._clear_transcript()
        self.recorder.cleanup()
        self.recorder = MicRecorder()
        self._analysis_audio_path = Path(path)
        self.export_mp3_button.config(state="disabled")  # opened file is already a file
        self._load_playback_file(Path(path))
        self._set_playback_enabled(self._player.has_audio)
        self.hq_button.config(state="normal")
        if hq_model_cached(self._hq_model):
            self._run_hq(Path(path), label=Path(path).name, prompt_download=False)
        else:
            self._set_audio_ready_model_missing(self._hq_model)

    # ---------- high-quality pass ----------

    def hq_transcribe(self) -> None:
        if self.is_recording or self._busy:
            return
        audio, source_sr, label = self._analysis_audio_source()
        if audio is None:
            return
        self._run_hq(audio, source_sr=source_sr, label=label)

    def _has_analysis_audio(self) -> bool:
        return self.recorder.has_recording or self._analysis_audio_path is not None or self._player.has_audio

    def _analysis_audio_source(self) -> tuple[Path | np.ndarray | None, int, str | None]:
        if self.recorder.has_recording:
            return self.recorder.wav_path, SAMPLE_RATE, None
        if self._analysis_audio_path is not None:
            return self._analysis_audio_path, SAMPLE_RATE, self._analysis_audio_path.name
        if self._player.has_audio:
            return self._player.audio_float32, self._player.sample_rate, self._tr("loaded_audio_label")
        return None, SAMPLE_RATE, None

    def _set_audio_ready_model_missing(self, model: str) -> None:
        self._set_status(self._tr("audio_ready_model_missing", model=model), "ready")
        if hasattr(self, "hq_button") and self._has_analysis_audio():
            self.hq_button.config(state="normal", text=self._tr("hq"))
        if hasattr(self, "hq_model_combo"):
            self._refresh_hq_model_combo()

    def _run_hq(
        self,
        audio: Path | np.ndarray | None,
        *,
        source_sr: int = SAMPLE_RATE,
        label: str | None = None,
        prompt_download: bool = True,
    ) -> None:
        if audio is None:
            return
        from llm.whisper_models import is_model_cached, model_info

        model_size = self._hq_model
        if not is_model_cached(model_size):
            if not prompt_download:
                self._set_audio_ready_model_missing(model_size)
                return
            info = model_info(model_size)
            size_text = _format_gb(info["disk_gb"]) if info and info["disk_gb"] else "?"
            ram_text = _format_gb(info["ram_gb"]) if info and info["ram_gb"] else "?"
            confirm = messagebox.askyesno(
                self._tr("hq_download_confirm_title"),
                self._tr("hq_download_confirm_message", model=model_size, size=size_text, ram=ram_text),
            )
            if not confirm:
                self._set_audio_ready_model_missing(model_size)
                return
            needs_download = True
        else:
            needs_download = False

        notes = self._notes_cache
        preprocessor = self._build_preprocessor() if self._nr_var.get() else None
        self._busy = True
        self._active_hq_model = model_size
        self.hq_button.config(state="disabled", text=self._tr("transcribing"))
        self.open_button.config(state="disabled")
        self._set_transcript_actions(False)
        what = f" · {label}" if label else ""
        if needs_download:
            self._downloading_model = model_size
            self._set_status(self._tr("hq_download", model=model_size), "download")
            self._show_cancel_button(True)
        else:
            self._set_status(self._tr("hq_running", model=model_size, what=what), "busy")
        self.meter_caption.config(text=self._tr("transcribe_progress"))
        self.wave.set_mode("analysis")
        self.wave.set_progress(0)

        run_status_text = self._tr("hq_running", model=model_size, what=what)

        def worker() -> None:
            from llm.whisper_models import ModelDownloadCancelled, download_model

            try:
                if needs_download:
                    try:
                        download_model(model_size)
                    except ModelDownloadCancelled:
                        self._hq_queue.put(("cancelled", model_size))
                        return
                    self._hq_queue.put(("download_complete", run_status_text))
                from llm.transcribe_final import segments_to_text, transcribe_segments

                segments = transcribe_segments(
                    audio,
                    source_sr,
                    model_size=model_size,
                    language=WHISPER_LANGUAGE,
                    initial_prompt=notes or None,
                    preprocessor=preprocessor,
                    progress_callback=lambda f: self._progress_queue.put(f),
                )
                text = segments_to_text(segments, timestamps=True)
                self._hq_queue.put(("ok", text))
            except Exception as exc:
                self._hq_queue.put(("error", describe_error(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _show_cancel_button(self, visible: bool) -> None:
        """Pack/unpack the inline Cancel button inside the status banner."""
        if not hasattr(self, "cancel_download_button"):
            return
        if visible:
            self.cancel_download_button.configure(text=self._tr("cancel_download"))
            self.cancel_download_button.pack(side="left", padx=(10, 0))
        else:
            self.cancel_download_button.pack_forget()

    def _cancel_active_download(self) -> None:
        """User clicked Cancel during a first-time model download."""
        model = self._downloading_model
        if not model:
            return
        from llm.whisper_models import cancel_download

        cancel_download(model)
        self.cancel_download_button.configure(state="disabled")

    def _load_playback_file(self, audio_path: Path) -> None:
        """Decode an opened file to 16 kHz mono so the player can use it."""
        try:
            from faster_whisper.audio import decode_audio

            decoded = np.asarray(decode_audio(str(audio_path), sampling_rate=PLAYBACK_SR), dtype=np.float32)
            self._player.load(decoded.reshape(-1), PLAYBACK_SR)
        except Exception:
            pass  # Playback is optional; the original path can still be transcribed later.

    def _apply_hq_result(self, kind: str, payload: str) -> None:
        if kind == "download_complete":
            # First stage finished; transition the banner from download to busy.
            self._set_status(payload, "busy")
            self._show_cancel_button(False)
            self._downloading_model = None
            try:
                self.cancel_download_button.configure(state="normal")
            except Exception:
                pass
            self._refresh_hq_model_combo()
            return
        self._busy = False
        self._show_cancel_button(False)
        try:
            self.cancel_download_button.configure(state="normal")
        except Exception:
            pass
        self._downloading_model = None
        active_model = getattr(self, "_active_hq_model", self._hq_model)
        self.hq_button.config(text=self._tr("hq"))
        self.meter_caption.config(text="")
        self.wave.set_mode("idle")
        self.wave.set_progress(0)
        if self._has_analysis_audio():
            self.hq_button.config(state="normal")
        self.open_button.config(state="normal")
        self._set_playback_enabled(True)
        if kind == "ok":
            if payload.strip():
                self._replace_transcript(payload)
                self._set_status(self._tr("hq_done", model=active_model), "ok")
            else:
                self._set_status(self._tr("hq_empty"), "busy")
        elif kind == "cancelled":
            self._set_status(self._tr("hq_download_cancelled", model=payload or active_model), "ready")
        elif kind == "error":
            self._set_status(self._tr("hq_failed"), "ready")
            messagebox.showerror(self._tr("hq_failed"), payload)
        self._refresh_hq_model_combo()
        self._sync_transcript_actions()

    # ---------- refine ----------

    def refine_transcript(self) -> None:
        transcript = self.transcript.get("1.0", "end").strip()
        notes = self._notes_cache
        if not transcript:
            messagebox.showinfo(self._tr("refine"), self._tr("no_transcript"))
            return
        if not notes:
            messagebox.showinfo(self._tr("refine"), self._tr("empty_notes"))
            return
        model = self._selected_llm_model()
        self._busy = True
        self.refine_button.config(state="disabled", text=self._tr("refining"))
        self.hq_button.config(state="disabled")
        self.minutes_button.config(state="disabled")
        self._set_status(self._tr("refine_running", model=model), "busy")
        self.meter_caption.config(text=self._tr("analysis"))
        self.wave.set_mode("analysis")
        self.wave.set_progress(0)

        def worker() -> None:
            try:
                from llm.refine import refine_transcript as do_refine

                refined = do_refine(transcript, notes, model=model, ollama_url=self._ollama_url)
                self._refine_queue.put(("ok", refined))
            except Exception as exc:
                self._refine_queue.put(("error", describe_error(exc, ollama=True, model=model, ollama_url=self._ollama_url)))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_refine_result(self, kind: str, payload: str) -> None:
        self._busy = False
        self.refine_button.config(text=self._tr("refine"))
        self.meter_caption.config(text="")
        self.wave.set_mode("idle")
        if kind == "ok":
            self._replace_transcript(payload)
            self._set_status(self._tr("refine_done"), "ok")
        elif kind == "error":
            self._set_status(self._tr("refine_failed"), "recording")
            messagebox.showerror(self._tr("refine_failed"), payload)
        if self.recorder.has_recording:
            self.hq_button.config(state="normal")
        self._sync_transcript_actions()

    # ---------- minutes ----------

    def generate_minutes(self) -> None:
        transcript = self.transcript.get("1.0", "end").strip()
        if not transcript:
            messagebox.showinfo(self._tr("minutes"), self._tr("no_transcript"))
            return
        model = self._selected_llm_model()
        self._busy = True
        self.minutes_button.config(state="disabled", text=self._tr("minutes_generating"))
        self.refine_button.config(state="disabled")
        self.hq_button.config(state="disabled")
        self._set_status(self._tr("minutes_running", model=model), "busy")
        self.meter_caption.config(text=self._tr("analysis"))
        self.wave.set_mode("analysis")
        self.wave.set_progress(0)

        def worker() -> None:
            try:
                from llm.summarize import summarize

                md = summarize(transcript, model=model, ollama_url=self._ollama_url)
                self._minutes_queue.put(("ok", md))
            except Exception as exc:
                self._minutes_queue.put(("error", describe_error(exc, ollama=True, model=model, ollama_url=self._ollama_url)))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_minutes_result(self, kind: str, payload: str) -> None:
        self._busy = False
        self.minutes_button.config(text=self._tr("minutes"))
        self.meter_caption.config(text="")
        self.wave.set_mode("idle")
        if self.recorder.has_recording:
            self.hq_button.config(state="normal")
        self._sync_transcript_actions()
        if kind == "ok":
            self._set_status(self._tr("minutes_done"), "ok")
            self._show_minutes(payload)
        elif kind == "error":
            self._set_status(self._tr("minutes_failed"), "recording")
            messagebox.showerror(self._tr("minutes_failed"), payload)

    def _show_minutes(self, markdown: str) -> None:
        win = tk.Toplevel(self.root)
        win.title(f"{APP_NAME} — {self._tr('minutes_window')}")
        win.geometry("680x600")
        win.configure(background=BG)
        frame = ttk.Frame(win, style="Card.TFrame")
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        text = tk.Text(
            frame,
            wrap="word",
            font=self._font(1),
            undo=True,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            background=SURFACE_2,
            foreground=TEXT,
            insertbackground=ACCENT,
            selectbackground=ACCENT_SOFT,
            selectforeground=TEXT,
            padx=10,
            pady=8,
        )
        sb = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=sb.set)
        text.insert("1.0", markdown)
        text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        btn_row = ttk.Frame(win)
        btn_row.pack(fill="x", padx=12, pady=(0, 12))

        def save() -> None:
            path = filedialog.asksaveasfilename(
                defaultextension=".md",
                filetypes=[("Markdown", "*.md"), ("テキスト", "*.txt"), ("すべてのファイル", "*.*")],
                initialfile="minutes.md",
                title=self._tr("save_minutes_title"),
                parent=win,
                **_initialdir_option("datasets_dir"),
            )
            if path:
                Path(path).write_text(text.get("1.0", "end").rstrip() + "\n", encoding="utf-8")

        ttk.Button(btn_row, text=self._tr("close"), command=win.destroy).pack(side="right")
        ttk.Button(btn_row, text=self._tr("save_as_md"), style="Accent.TButton", command=save).pack(side="right", padx=(0, 6))

    # ---------- session save / restore ----------

    def save_session(self) -> None:
        transcript = self.transcript.get("1.0", "end").rstrip()
        notes = self.notes_text.get("1.0", "end").rstrip()
        if not self._player.has_audio and not transcript and not notes:
            messagebox.showinfo(self._tr("save_session_title"), self._tr("nothing_to_save"))
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".zip",
            filetypes=[("セッション", "*.zip"), ("すべてのファイル", "*.*")],
            initialfile="session.zip",
            title=self._tr("save_session_title"),
            **_initialdir_option("datasets_dir"),
        )
        if not path:
            return
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("transcript.txt", transcript + "\n")
                bundle.writestr("notes.txt", notes + "\n")
                meta = {
                    "app": APP_NAME,
                    "version": 1,
                    "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "duration_seconds": round(self._player.duration, 2),
                    "has_audio": self._player.has_audio,
                }
                bundle.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
                if self._player.has_audio:
                    tmp = settings_store.temp_path(f"session-audio-{os.getpid()}.wav")
                    self._player.write_wav(tmp)
                    bundle.write(tmp, "audio.wav")
                    tmp.unlink(missing_ok=True)
        except Exception as exc:
            messagebox.showerror(self._tr("session_save_failed"), f"{type(exc).__name__}: {exc}")
            return
        messagebox.showinfo(self._tr("saved"), self._tr("session_save_to", path=path))

    def open_session(self) -> None:
        if self.is_recording or self._busy:
            return
        path = filedialog.askopenfilename(
            title=self._tr("open_session_title"),
            filetypes=[("セッション", "*.zip"), ("すべてのファイル", "*.*")],
            **_initialdir_option("datasets_dir"),
        )
        if not path:
            return
        try:
            with zipfile.ZipFile(path) as bundle:
                names = set(bundle.namelist())
                transcript = bundle.read("transcript.txt").decode("utf-8") if "transcript.txt" in names else ""
                notes = bundle.read("notes.txt").decode("utf-8") if "notes.txt" in names else ""
                audio_bytes = bundle.read("audio.wav") if "audio.wav" in names else None
        except Exception as exc:
            messagebox.showerror(self._tr("session_open_failed"), f"{type(exc).__name__}: {exc}")
            return

        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", notes)
        self._on_notes_change(None)
        self._replace_transcript(transcript)
        self.recorder.cleanup()
        self.recorder = MicRecorder()  # the session's audio is not a fresh recording
        self._analysis_audio_path = None
        self.export_mp3_button.config(state="disabled")
        self.hq_button.config(state="disabled")
        self._player.load(np.zeros(0, dtype=np.float32), PLAYBACK_SR)
        if audio_bytes is not None:
            self._load_playback_bytes(audio_bytes)
        if self._player.has_audio:
            self.hq_button.config(state="normal")
        self._set_playback_enabled(self._player.has_audio)
        self._sync_transcript_actions()
        self._set_status(self._tr("session_loaded", name=Path(path).name), "ready")

    def _load_playback_bytes(self, wav_bytes: bytes) -> None:
        tmp = settings_store.temp_path(f"session-load-{os.getpid()}.wav")
        try:
            tmp.write_bytes(wav_bytes)
            with wave.open(str(tmp), "rb") as wav:
                sr = wav.getframerate()
                raw = wav.readframes(wav.getnframes())
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            self._player.load(audio, sr)
        except Exception:
            pass
        finally:
            tmp.unlink(missing_ok=True)

    # ---------- queues / polling ----------

    def _poll_queues(self) -> None:
        self._drain_transcript_queue()
        self._drain_simple_queue(self._refine_queue, self._apply_refine_result)
        self._drain_simple_queue(self._hq_queue, self._apply_hq_result)
        self._drain_simple_queue(self._minutes_queue, self._apply_minutes_result)
        self._drain_progress_queue()
        self._update_meter()
        self._update_playback()
        self.wave.tick()
        self.root.after(100, self._poll_queues)

    def _drain_transcript_queue(self) -> None:
        appended = False
        while True:
            try:
                kind, block_id, text = self._transcript_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "polished":
                self._replace_transcript_block(block_id, text)
            else:
                self._append_transcript(text, block_id)
            appended = True
        if appended and not self.is_recording:
            self._sync_transcript_actions()

    def _drain_simple_queue(self, q: queue.Queue, handler: Callable[[str, str], None]) -> None:
        while True:
            try:
                kind, payload = q.get_nowait()
            except queue.Empty:
                break
            handler(kind, payload)

    def _drain_progress_queue(self) -> None:
        fraction = None
        while True:
            try:
                fraction = self._progress_queue.get_nowait()
            except queue.Empty:
                break
        if fraction is not None and self._busy:
            pct = int(max(0.0, min(fraction, 1.0)) * 100)
            self.wave.set_progress(pct / 100)
            self.meter_caption.config(text=self._tr("transcribe_progress_pct", pct=pct))

    def _update_meter(self) -> None:
        if not self.is_recording:
            return
        # Peak level with a VU-style decay so the bar doesn't flicker.
        target = min(self.recorder.level * 3.0, 1.0)
        self._meter_level = max(target, self._meter_level * 0.75)
        self.wave.set_level(self._meter_level)
        if self.recorder.has_recording:
            self.meter_caption.config(
                text=self._tr(
                    "capture_levels",
                    mix=int(self.recorder.level * 100),
                    mic=int(self.recorder.mic_level * 100),
                    system=int(self.recorder.system_level * 100),
                )
            )

    def _update_playback(self) -> None:
        if not self._player.has_audio:
            return
        playing = self._player.is_playing
        self.position_label.config(text=f"{_fmt_time(self._player.position)} / {_fmt_time(self._player.duration)}")
        if not playing and self.play_button["text"] in {LABEL_PAUSE, text_for("en", "pause")}:
            self.play_button.config(text=self._tr("play"))

    # ---------- transcript helpers ----------

    def _append_transcript(self, text: str, block_id: int | None = None) -> None:
        tags = (f"liveblk-{block_id}",) if block_id is not None else ()
        prefix = "" if self.transcript.index("end-1c") == "1.0" else " "
        self.transcript.insert("end", prefix + text, tags)
        self.transcript.see("end")

    def _replace_transcript_block(self, block_id: int, text: str) -> None:
        """Swap a block's live preview lines for their polished re-transcription.

        The block is located by its text tag, so this is a no-op once the HQ
        pass (or anything else) has rewritten the transcript.
        """
        tag = f"liveblk-{block_id}"
        ranges = self.transcript.tag_ranges(tag)
        if not ranges:
            return
        start = self.transcript.index(ranges[0])
        starts_at_top = start == "1.0"
        self.transcript.delete(ranges[0], ranges[-1])
        self.transcript.insert(start, ("" if starts_at_top else " ") + text, (tag,))

    def _replace_transcript(self, text: str) -> None:
        self.transcript.delete("1.0", "end")
        self.transcript.insert("1.0", text)
        self._retag_timestamps()
        self.transcript.see("1.0")

    def _clear_transcript(self) -> None:
        self.transcript.delete("1.0", "end")
        self.transcript.tag_remove("seek", "1.0", "end")
        while not self._transcript_queue.empty():
            try:
                self._transcript_queue.get_nowait()
            except queue.Empty:
                break

    def _has_transcript_text(self) -> bool:
        return self.transcript.get("1.0", "end").strip() != ""

    def _set_transcript_actions(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.export_txt_button.config(state=state)
        self.refine_button.config(state=state)
        self.minutes_button.config(state=state)

    def _sync_transcript_actions(self) -> None:
        """Enable the transcript toolbar iff there is text and nothing is running."""
        self._set_transcript_actions(self._has_transcript_text() and not self.is_recording and not self._busy)

    def _selected_llm_model(self) -> str:
        return self._llm_model_var.get().strip() or OLLAMA_MODEL

    # ---------- status / timer ----------

    def _set_status(self, text: str, kind: str = "ready") -> None:
        self._status_kind = kind
        palette = {
            "ready": (SURFACE_2, BORDER, TEXT_MUTED, "OK", TEXT_MUTED),
            "recording": ("#fce4e2", DANGER, DANGER_DARK, "REC", "#ffffff"),
            "busy": (ACCENT_SOFT, ACCENT, ACCENT_DARK, "RUN", "#ffffff"),
            "download": (ACCENT_SOFT, ACCENT, ACCENT_DARK, "DL", "#ffffff"),
            "ok": ("#dff3e8", OK_GREEN, OK_GREEN, "OK", "#ffffff"),
        }
        bg, border, fg, icon, icon_fg = palette.get(kind, palette["ready"])
        if self._dark_var.get():
            palette = {
                "ready": (SURFACE_2, BORDER, TEXT_MUTED, "OK", TEXT_MUTED),
                "recording": ("#351923", DANGER, "#ffd7df", "REC", BG),
                "busy": (ACCENT_SOFT, ACCENT, TEXT, "RUN", BG),
                "download": (ACCENT_SOFT, ACCENT, TEXT, "DL", BG),
                "ok": ("#123828", OK_GREEN, "#d9ffee", "OK", BG),
            }
            bg, border, fg, icon, icon_fg = palette.get(kind, palette["ready"])
        self.status_banner.config(background=bg, highlightbackground=border, highlightcolor=border)
        self.status_icon.config(text=icon, background=border, foreground=icon_fg)
        self.status.config(text=text, background=bg, foreground=fg)

    def _schedule_tick(self) -> None:
        self._tick_job = self.root.after(1000, self._tick)

    def _cancel_tick(self) -> None:
        if self._tick_job is not None:
            self.root.after_cancel(self._tick_job)
            self._tick_job = None

    def _tick(self) -> None:
        if not self.is_recording:
            return
        self._elapsed += 1
        mins, secs = divmod(self._elapsed, 60)
        self.timer.config(text=f"{mins:02d}:{secs:02d}")
        self._schedule_tick()

    def _on_close(self) -> None:
        if self.is_recording:
            self.recorder.stop()
        if self._transcriber is not None:
            self._transcriber.stop()
        self._player.reset()
        self.recorder.cleanup()
        settings_store.save_settings(
            {
                "device_index": self._device_index,
                "output_device_id": self._output_device_id,
                "mic_capture": bool(self._mic_capture_var.get()),
                "system_capture": bool(self._system_capture_var.get()) and system_output_capture_available(),
                "noise_reduce": bool(self._nr_var.get()),
                "live": bool(self._live_var.get()),
                "llm_model": self._selected_llm_model(),
                "hq_model": self._hq_model,
                "theme": self._theme_key(),
                "dark_mode": bool(self._dark_var.get()),
                "language": self._language_code(),
                "font_size": self._font_size,
                "geometry": self.root.winfo_geometry(),
            }
        )
        self.root.destroy()


def main() -> int:
    settings_store.sweep_temp_files()
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
