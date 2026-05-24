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
    TOOLTIP_EXPORT_TXT,
    TOOLTIP_HQ,
    TOOLTIP_LIVE,
    TOOLTIP_MIC_CAPTURE,
    TOOLTIP_MINUTES,
    TOOLTIP_MP3,
    TOOLTIP_NR,
    TOOLTIP_OPEN,
    TOOLTIP_PLAY,
    TOOLTIP_RECORD,
    TOOLTIP_REFINE,
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
    folder = "models--" + model_id.replace("/", "--")
    return (Path.home() / ".cache" / "huggingface" / "hub" / folder).exists()


def list_input_devices() -> list[tuple[str, int | None]]:
    """Return [(label, device_index), ...] for the system default + every input device."""
    import sounddevice as sd

    out: list[tuple[str, int | None]] = [("システム既定", None)]
    try:
        devices = sd.query_devices()
    except Exception:
        return out
    for i, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) > 0:
            out.append((f"{dev['name']} ({dev['max_input_channels']}ch)", i))
    return out


class MicRecorder:
    """Records the chosen input device straight to a temp WAV file.

    A writer thread drains the PortAudio callback queue to disk, so RAM use
    stays flat regardless of recording length. ``level`` exposes the latest
    chunk's peak amplitude for a VU meter.
    """

    def __init__(self, on_chunk: Callable[[np.ndarray], None] | None = None) -> None:
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._stream = None
        self._on_chunk = on_chunk
        self._wav_path: Path | None = None
        self._writer_thread: threading.Thread | None = None
        self._frames_written = 0
        self._level = 0.0

    def start(self, device: int | None = None) -> None:
        import sounddevice as sd

        self._wav_path = settings_store.temp_path(f"micrec-{os.getpid()}-{int(time.time() * 1000)}.wav")
        self._frames_written = 0
        self._level = 0.0
        self._queue = queue.Queue()
        self._writer_thread = threading.Thread(target=self._writer, args=(self._wav_path,), daemon=True)
        self._writer_thread.start()
        self._stream = sd.InputStream(
            device=device,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time_info, status) -> None:
        chunk = indata.copy()
        if chunk.size:
            self._level = float(np.abs(chunk).max()) / 32768.0
        self._queue.put(chunk)
        if self._on_chunk is not None:
            self._on_chunk(chunk)

    def _writer(self, path: Path) -> None:
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            while True:
                chunk = self._queue.get()
                if chunk is None:
                    break
                wav.writeframes(chunk.tobytes())
                self._frames_written += chunk.shape[0]

    def stop(self) -> None:
        if self._stream is None:
            return
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self._level = 0.0
        self._queue.put(None)
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=10)
            self._writer_thread = None

    @property
    def level(self) -> float:
        return self._level

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
        self._transcript_queue: queue.Queue[str] = queue.Queue()
        self._refine_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._hq_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._minutes_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._progress_queue: queue.Queue[float] = queue.Queue()
        self._transcriber = None
        self._player = Player()
        self._settings = settings_store.load_settings()
        self._mic_capture_var = tk.BooleanVar(value=bool(self._settings.get("mic_capture", True)))
        self._live_var = tk.BooleanVar(value=bool(self._settings.get("live")))
        self._nr_var = tk.BooleanVar(value=bool(self._settings.get("noise_reduce")))
        self._llm_models = settings_store.llm_models()
        saved_llm = str(self._settings.get("llm_model") or "").strip()
        default_llm = saved_llm or OLLAMA_MODEL
        if default_llm not in self._llm_models:
            self._llm_models.insert(0, default_llm)
        self._llm_model_var = tk.StringVar(value=default_llm)
        self._ollama_url = settings_store.model_config()["ollama_url"]
        self._theme_var = tk.StringVar(value=THEMES.get(self._settings.get("theme"), THEMES["midnight"])["label"])
        self._dark_var = tk.BooleanVar(value=bool(self._settings.get("dark_mode")))
        saved_language = str(self._settings.get("language") or "ja")
        self._language_var = tk.StringVar(value=LANGUAGES.get(saved_language, LANGUAGES["ja"]))
        self._font_size = _coerce_font_size(self._settings.get("font_size"))
        _apply_palette(self._theme_key(), self._dark_var.get())
        self._device_index: int | None = self._settings.get("device_index")
        self._devices: list[tuple[str, int | None]] = [("システム既定", None)]
        self._notes_cache = ""
        self.recorder = MicRecorder()

        root.title(f"{APP_NAME} — {self._tr('tagline')}")
        root.geometry(self._settings.get("geometry") or "1180x780")
        root.minsize(1060, 720)
        root.configure(background=BG)

        self._configure_style()
        self._build_menu()
        self._build_header()

        main = ttk.PanedWindow(root, orient="vertical")
        main.pack(fill="both", expand=True, padx=10, pady=(6, 10))
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
        self.dark_check.set_text(self._tr("dark"))
        self.input_label.config(text=self._tr("input"))
        self.refresh_button.config(text=self._tr("refresh_input"))
        self._refresh_device_labels()
        self.mic_check.set_text(self._tr("mic_capture"))
        self.nr_check.set_text(self._tr("noise_reduce"))
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
        for widget_name in ("dark_check", "mic_check", "nr_check", "live_check"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.set_font(self._font())
                widget.restyle()

    def _restyle_direct_fonts(self) -> None:
        if hasattr(self, "status_icon"):
            self.status_icon.configure(font=self._font(-2, "bold"))
        if hasattr(self, "status"):
            self.status.configure(font=self._font(0, "bold"))
        for widget_name in ("language_combo", "theme_combo", "device_combo", "llm_combo"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.configure(font=self._font())

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
        header.pack(fill="x", padx=10, pady=(10, 0))
        inner = ttk.Frame(header, style="Header.TFrame")
        inner.pack(fill="x", padx=PAD_X, pady=10)
        inner.columnconfigure(1, weight=1)
        inner.columnconfigure(4, weight=1)
        ttk.Label(inner, text=APP_NAME, style="Wordmark.TLabel").grid(row=0, column=0, sticky="w")
        self.tagline_label = ttk.Label(inner, text=f"  {self._tr('tagline')}", style="Tagline.TLabel")
        self.tagline_label.grid(row=0, column=1, sticky="w", padx=(4, 12), pady=(6, 0))
        self.timer = ttk.Label(inner, text="00:00", style="Timer.TLabel")
        self.timer.grid(row=0, column=5, sticky="e")
        self.status_banner = tk.Frame(inner, bd=0, highlightthickness=1)
        self.status_banner.grid(row=1, column=5, sticky="e", pady=(8, 0), ipadx=10, ipady=4)
        self.status_icon = tk.Label(self.status_banner, text="OK", width=3, anchor="center", font=self._font(-2, "bold"))
        self.status_icon.pack(side="left", padx=(0, 7))
        self.status = tk.Label(self.status_banner, text=self._tr("status_ready"), font=self._font(0, "bold"))
        self.status.pack(side="left")
        self._set_status(self._tr("status_ready"), "ready")
        self.dark_check = Switch(
            inner,
            text=self._tr("dark"),
            variable=self._dark_var,
            colors=_ui_colors,
            command=self._on_theme_change,
            font=self._font(),
            default_font_size=DEFAULT_FONT_SIZE,
        )
        self.dark_check.grid(row=1, column=4, sticky="e", padx=(8, 10), pady=(8, 0))
        self.language_combo = ttk.Combobox(
            inner,
            state="readonly",
            width=9,
            values=list(LANGUAGE_CODES),
            textvariable=self._language_var,
            font=self._font(),
        )
        self.language_combo.grid(row=1, column=3, sticky="e", padx=(8, 0), pady=(8, 0))
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_change)
        self.theme_combo = ttk.Combobox(
            inner,
            state="readonly",
            width=10,
            values=list(THEME_LABELS),
            textvariable=self._theme_var,
            font=self._font(),
        )
        self.theme_combo.grid(row=1, column=2, sticky="e", padx=(8, 0), pady=(8, 0))
        self.theme_combo.bind("<<ComboboxSelected>>", self._on_theme_change)
        inner.bind("<Configure>", lambda event: self.tagline_label.configure(wraplength=max(120, event.width // 3)))

    # ---------- main layout ----------

    def _build_controls(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=3, uniform="controls")
        parent.columnconfigure(1, weight=2, uniform="controls")
        parent.columnconfigure(2, weight=3, uniform="controls")

        # --- source: input device + recording options ---
        source = ttk.Frame(parent, style="Card.TFrame")
        source.grid(row=0, column=0, sticky="nsew", padx=(PAD_X, 8), pady=(PAD_Y, 8))
        source.columnconfigure(1, weight=1)
        self.input_label = ttk.Label(source, text=self._tr("input"), style="Card.TLabel")
        self.input_label.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.device_combo = ttk.Combobox(source, state="readonly", width=26, font=self._font())
        self.device_combo.grid(row=0, column=1, sticky="w", padx=(8, 4), pady=(0, 6))
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_change)
        self.refresh_button = ttk.Button(source, text=self._tr("refresh_input"), width=8, command=self.refresh_devices)
        self.refresh_button.grid(row=0, column=2, sticky="w", pady=(0, 6))
        self.mic_check = Switch(
            source,
            text=self._tr("mic_capture"),
            variable=self._mic_capture_var,
            colors=_ui_colors,
            command=self._on_mic_capture_change,
            font=self._font(),
            default_font_size=DEFAULT_FONT_SIZE,
        )
        self.mic_check.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 4))
        Tooltip(self.mic_check, TOOLTIP_MIC_CAPTURE)
        ttk.Label(source, text="LLM", style="Card.TLabel").grid(row=1, column=0, sticky="w")
        self.llm_combo = ttk.Combobox(
            source,
            state="readonly",
            width=22,
            values=self._llm_models,
            textvariable=self._llm_model_var,
            font=self._font(),
        )
        self.llm_combo.grid(row=1, column=1, columnspan=2, sticky="w", padx=(8, 4), pady=(0, 6))
        self.nr_check = Switch(
            source,
            text=self._tr("noise_reduce"),
            variable=self._nr_var,
            colors=_ui_colors,
            font=self._font(),
            default_font_size=DEFAULT_FONT_SIZE,
        )
        self.nr_check.grid(row=3, column=0, columnspan=3, sticky="w")
        Tooltip(self.nr_check, TOOLTIP_NR)

        playback = ttk.Frame(source, style="Card.TFrame")
        playback.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(14, 0))
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
        self._update_mic_capture_controls()

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
        self._update_mic_capture_controls()
        self.export_mp3_button = ttk.Button(
            controls, text=self._tr("save_mp3"), width=11, command=self.export_mp3, state="disabled"
        )
        self.export_mp3_button.grid(row=2, column=1, sticky="ew", padx=(6, 0))
        Tooltip(self.export_mp3_button, TOOLTIP_MP3)
        self.open_button = ttk.Button(controls, text=self._tr("open_audio"), width=11, command=self.open_audio)
        self.open_button.grid(row=2, column=0, sticky="ew", padx=(0, 6))
        Tooltip(self.open_button, TOOLTIP_OPEN)

        # --- wave row: audio input while recording / analysis pulse while busy ---
        meter_row = ttk.Frame(controls, style="Card.TFrame")
        meter_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.meter_caption = ttk.Label(meter_row, text="", style="Hint.TLabel", width=16)
        self.meter_caption.pack(side="left")
        self.wave = WaveMeter(meter_row, colors=_ui_colors)
        self.wave.pack(side="left", fill="x", expand=True, padx=(6, 0))

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
        live = self._live_var.get() and mic_capture
        nr = self._nr_var.get() and mic_capture
        preprocessor = self._build_preprocessor() if nr else None
        self._player.reset()
        self.recorder.cleanup()  # drop the previous take's temp WAV
        if live:
            from llm.transcribe_stream import StreamingTranscriber

            self._transcriber = StreamingTranscriber(
                on_text=lambda t: self._transcript_queue.put(t),
                model_size=WHISPER_MODEL,
                language=WHISPER_LANGUAGE,
                source_sr=SAMPLE_RATE,
                chunk_seconds=WHISPER_CHUNK_SECONDS,
                prompt_provider=lambda: self._notes_cache,
                preprocessor=preprocessor,
            )
            self._clear_transcript()
            self._transcriber.start()
            self.recorder = MicRecorder(on_chunk=self._transcriber.feed_int16)
        else:
            self.recorder = MicRecorder()

        if mic_capture:
            try:
                self.recorder.start(device=self._device_index)
            except Exception as exc:
                if self._transcriber is not None:
                    self._transcriber.stop()
                    self._transcriber = None
                messagebox.showerror(self._tr("start_record_error"), f"{type(exc).__name__}: {exc}{MIC_HELP}")
                return

        self.is_recording = True
        self._elapsed = 0
        self.timer.config(text="00:00")
        tag_pairs = (
            (self._tr("mic_off_tag"), not mic_capture),
            (self._tr("live_tag"), live),
            (self._tr("noise_tag"), nr),
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
        self.live_check.state(["disabled"])
        self.nr_check.state(["disabled"])
        self.device_combo.state(["disabled"])
        self.refresh_button.config(state="disabled")
        self.meter_caption.config(text=self._tr("input_level") if mic_capture else self._tr("mic_off_level"))
        self.wave.set_mode("recording" if mic_capture else "idle")
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
        self._update_mic_capture_controls()
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
        if live_was_on and self.recorder.has_recording:
            self._run_hq(self.recorder.wav_path)

    def _build_preprocessor(self):
        """Return a callable(audio_f32, sr) -> audio_f32 that applies the pipeline."""
        from recorder.preprocess import preprocess_float32

        def run(audio_f32, sr):
            return preprocess_float32(audio_f32, sr, bandpass=True, denoise=True)

        return run

    # ---------- input device ----------

    def refresh_devices(self) -> None:
        self._devices = list_input_devices()
        self._refresh_device_labels()
        if self._device_index is not None:
            for i, (_label, idx) in enumerate(self._devices):
                if idx == self._device_index:
                    self.device_combo.current(i)
                    self._update_mic_capture_controls()
                    return
        self.device_combo.current(0)
        self._device_index = None
        self._update_mic_capture_controls()

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
        self._update_mic_capture_controls()

    def _update_mic_capture_controls(self) -> None:
        if self.is_recording:
            return
        if not all(hasattr(self, name) for name in ("device_combo", "refresh_button", "live_check", "nr_check")):
            return
        enabled = self._mic_capture_var.get()
        self.device_combo.state(["!disabled", "readonly"] if enabled else ["disabled"])
        self.refresh_button.config(state="normal" if enabled else "disabled")
        self.live_check.state(["!disabled"] if enabled else ["disabled"])
        self.nr_check.state(["!disabled"] if enabled else ["disabled"])

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
        self.export_mp3_button.config(state="disabled")  # opened file is already a file
        self._run_hq(Path(path), label=Path(path).name, load_playback=True)

    # ---------- high-quality pass ----------

    def hq_transcribe(self) -> None:
        if self.is_recording or self._busy or not self.recorder.has_recording:
            return
        self._run_hq(self.recorder.wav_path)

    def _run_hq(self, audio_path: Path | None, label: str | None = None, load_playback: bool = False) -> None:
        if audio_path is None:
            return
        notes = self._notes_cache
        preprocessor = self._build_preprocessor() if self._nr_var.get() else None
        self._busy = True
        self.hq_button.config(state="disabled", text=self._tr("transcribing"))
        self.open_button.config(state="disabled")
        self._set_transcript_actions(False)
        what = f" · {label}" if label else ""
        if hq_model_cached():
            self._set_status(self._tr("hq_running", model=HQ_MODEL_LABEL, what=what), "busy")
        else:
            self._set_status(self._tr("hq_download"), "download")
        self.meter_caption.config(text=self._tr("transcribe_progress"))
        self.wave.set_mode("analysis")
        self.wave.set_progress(0)

        def worker() -> None:
            try:
                from llm.transcribe_final import segments_to_text, transcribe_segments

                segments = transcribe_segments(
                    audio_path,
                    SAMPLE_RATE,
                    model_size=HQ_MODEL,
                    language=WHISPER_LANGUAGE,
                    initial_prompt=notes or None,
                    preprocessor=preprocessor,
                    progress_callback=lambda f: self._progress_queue.put(f),
                )
                text = segments_to_text(segments, timestamps=True)
                if load_playback:
                    self._load_playback_file(audio_path)
                self._hq_queue.put(("ok", text))
            except Exception as exc:
                self._hq_queue.put(("error", describe_error(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _load_playback_file(self, audio_path: Path) -> None:
        """Decode an opened file to 16 kHz mono so the player can use it."""
        try:
            from faster_whisper.audio import decode_audio

            decoded = np.asarray(decode_audio(str(audio_path), sampling_rate=PLAYBACK_SR), dtype=np.float32)
            self._player.load(decoded.reshape(-1), PLAYBACK_SR)
        except Exception:
            pass  # playback is a nicety; transcription already succeeded

    def _apply_hq_result(self, kind: str, payload: str) -> None:
        self._busy = False
        self.hq_button.config(text=self._tr("hq"))
        self.meter_caption.config(text="")
        self.wave.set_mode("idle")
        self.wave.set_progress(0)
        if self.recorder.has_recording:
            self.hq_button.config(state="normal")
        self.open_button.config(state="normal")
        self._set_playback_enabled(True)
        if kind == "ok":
            if payload.strip():
                self._replace_transcript(payload)
                self._set_status(self._tr("hq_done", model=HQ_MODEL_LABEL), "ok")
            else:
                self._set_status(self._tr("hq_empty"), "busy")
        elif kind == "error":
            self._set_status(self._tr("hq_failed"), "recording")
            messagebox.showerror(self._tr("hq_failed"), payload)
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
        self.export_mp3_button.config(state="disabled")
        self.hq_button.config(state="disabled")
        self._player.load(np.zeros(0, dtype=np.float32), PLAYBACK_SR)
        if audio_bytes is not None:
            self._load_playback_bytes(audio_bytes)
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
                text = self._transcript_queue.get_nowait()
            except queue.Empty:
                break
            self._append_transcript(text)
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

    def _update_playback(self) -> None:
        if not self._player.has_audio:
            return
        playing = self._player.is_playing
        self.position_label.config(text=f"{_fmt_time(self._player.position)} / {_fmt_time(self._player.duration)}")
        if not playing and self.play_button["text"] in {LABEL_PAUSE, text_for("en", "pause")}:
            self.play_button.config(text=self._tr("play"))

    # ---------- transcript helpers ----------

    def _append_transcript(self, text: str) -> None:
        if self.transcript.index("end-1c") != "1.0":
            self.transcript.insert("end", " ")
        self.transcript.insert("end", text)
        self.transcript.see("end")

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
                "mic_capture": bool(self._mic_capture_var.get()),
                "noise_reduce": bool(self._nr_var.get()),
                "live": bool(self._live_var.get()),
                "llm_model": self._selected_llm_model(),
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
