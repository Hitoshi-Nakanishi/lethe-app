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

APP_NAME = "Lethe"
APP_TAGLINE = "録音・文字起こし・議事録"

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
THEMES = {
    "midnight": {
        "label": "Midnight",
        "light": {
            "bg": "#eef2f7",
            "surface": "#ffffff",
            "surface_2": "#f6f8fb",
            "border": "#cfd7e5",
            "text": "#172033",
            "muted": "#647084",
            "accent": "#2563eb",
            "accent_dark": "#1d4ed8",
            "accent_soft": "#dbeafe",
            "danger": "#e0463e",
            "danger_dark": "#bf3a33",
            "ok": "#0f9f6e",
            "disabled_bg": "#e5eaf2",
            "disabled_fg": "#9aa6b8",
        },
        "dark": {
            "bg": "#070b12",
            "surface": "#101724",
            "surface_2": "#151f31",
            "border": "#243349",
            "text": "#edf4ff",
            "muted": "#91a0b8",
            "accent": "#5eead4",
            "accent_dark": "#14b8a6",
            "accent_soft": "#123b43",
            "danger": "#fb7185",
            "danger_dark": "#f43f5e",
            "ok": "#34d399",
            "disabled_bg": "#1b2535",
            "disabled_fg": "#66758c",
        },
    },
    "aurora": {
        "label": "Aurora",
        "light": {
            "bg": "#f0f7f4",
            "surface": "#ffffff",
            "surface_2": "#f5fbf8",
            "border": "#c7ded4",
            "text": "#14231d",
            "muted": "#60756c",
            "accent": "#0f9f6e",
            "accent_dark": "#087f5b",
            "accent_soft": "#dff7ec",
            "danger": "#e05252",
            "danger_dark": "#bf3f3f",
            "ok": "#16835e",
            "disabled_bg": "#e4eee9",
            "disabled_fg": "#91a19a",
        },
        "dark": {
            "bg": "#07110e",
            "surface": "#10201a",
            "surface_2": "#152a22",
            "border": "#244137",
            "text": "#ecfff7",
            "muted": "#9ab8ac",
            "accent": "#7dd3fc",
            "accent_dark": "#38bdf8",
            "accent_soft": "#123447",
            "danger": "#fb7185",
            "danger_dark": "#f43f5e",
            "ok": "#86efac",
            "disabled_bg": "#1d3028",
            "disabled_fg": "#6f887c",
        },
    },
    "ember": {
        "label": "Ember",
        "light": {
            "bg": "#f7f3ef",
            "surface": "#fffdfa",
            "surface_2": "#fbf4ec",
            "border": "#e0cfc0",
            "text": "#2b211b",
            "muted": "#7c6a5b",
            "accent": "#d9480f",
            "accent_dark": "#b83b0b",
            "accent_soft": "#ffe8d6",
            "danger": "#c92a2a",
            "danger_dark": "#a61e1e",
            "ok": "#2b8a3e",
            "disabled_bg": "#eee5dd",
            "disabled_fg": "#a19388",
        },
        "dark": {
            "bg": "#120c09",
            "surface": "#201610",
            "surface_2": "#2b1d14",
            "border": "#473325",
            "text": "#fff4ec",
            "muted": "#c2aa99",
            "accent": "#f97316",
            "accent_dark": "#ea580c",
            "accent_soft": "#4a2412",
            "danger": "#fb7185",
            "danger_dark": "#f43f5e",
            "ok": "#86efac",
            "disabled_bg": "#31231a",
            "disabled_fg": "#877367",
        },
    },
}

THEME_LABELS = {value["label"]: key for key, value in THEMES.items()}
BG = SURFACE = SURFACE_2 = BORDER = TEXT = TEXT_MUTED = ACCENT = ACCENT_DARK = ACCENT_SOFT = ""
DANGER = DANGER_DARK = OK_GREEN = DISABLED_BG = DISABLED_FG = ""


def _apply_palette(theme: str, dark_mode: bool) -> None:
    global BG, SURFACE, SURFACE_2, BORDER, TEXT, TEXT_MUTED, ACCENT, ACCENT_DARK, ACCENT_SOFT
    global DANGER, DANGER_DARK, OK_GREEN, DISABLED_BG, DISABLED_FG
    theme_key = theme if theme in THEMES else "midnight"
    mode = "dark" if dark_mode else "light"
    palette = THEMES[theme_key][mode]
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

PAD_X = 16
PAD_Y = 12

# Button labels (kept as constants because handlers also restore them).
LABEL_RECORD = "●  録音開始"
LABEL_STOP = "■  停止"
LABEL_HQ = "① 高精度で文字起こし"
LABEL_REFINE = "② メモで校正"
LABEL_MINUTES = "③ 議事録を作成"
LABEL_PLAY = "▶  再生"
LABEL_PAUSE = "❚❚  一時停止"

AUDIO_FILETYPES = [
    ("音声ファイル", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.mp4 *.mov"),
    ("すべてのファイル", "*.*"),
]
TIMESTAMP_RE = re.compile(r"^\[(?:(\d+):)?(\d{1,2}):(\d{2})\]")

TOOLTIP_RECORD = "マイク（選択した入力デバイス）の録音を開始／停止します。Space キーでも操作できます。"
TOOLTIP_LIVE = (
    "録音中、5 秒ごとに Whisper medium で暫定の文字起こしを表示します。"
    "停止すると自動で「① 高精度で文字起こし」が走り、より正確な結果に置き換わります。"
)
TOOLTIP_NR = "録音音声から定常ノイズ（ファン・空調音など）を除去し、文字起こしの精度を上げます。"
TOOLTIP_OPEN = "既存の音声ファイル(mp3/m4a/wav 等)を開き、「① 高精度で文字起こし」と同じ処理を実行します。"
TOOLTIP_MP3 = "録音した音声を MP3 ファイルとして保存します。"
TOOLTIP_HQ = (
    "録音または開いた音声の全体を Whisper large-v3 で文字起こしします。"
    "ライブ転写より時間はかかりますが、より正確です。"
)
TOOLTIP_REFINE = (
    "右の「メモ」に書いた固有名詞・専門用語を正しい表記とみなし、"
    "Ollama が文字起こしの誤変換を修正します。先にメモへ用語を入力してください。"
)
TOOLTIP_MINUTES = "文字起こしから Ollama が議事録（要約・論点・アクションアイテム）を Markdown 形式で生成します。"
TOOLTIP_EXPORT_TXT = "文字起こしテキストを .txt / .md ファイルに保存します。"
TOOLTIP_PLAY = "文字起こしの音声を再生します。行頭の [時刻] をクリックすると、その位置から再生できます。"
WORKFLOW_HINT = "手順:  録音  →  ① 文字起こし  →  メモに用語を記入  →  ② 校正  →  ③ 議事録"

MIC_HELP = (
    "\n\nマイクが他のアプリで使用中でないか、また\n"
    "システム設定 ＞ プライバシーとセキュリティ ＞ マイク で\n"
    "アクセスが許可されているかご確認ください。"
)


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


def _wave_bar_heights(level: float, phase: float, count: int = 32) -> list[float]:
    """Return normalized animated bar heights for the wave meter."""
    level = max(0.0, min(level, 1.0))
    heights = []
    for i in range(count):
        carrier = 0.5 + 0.5 * np.sin(phase + i * 0.58)
        ripple = 0.5 + 0.5 * np.sin(phase * 0.37 + i * 1.17)
        heights.append(max(0.06, min(1.0, 0.08 + level * (0.36 + 0.46 * carrier + 0.18 * ripple))))
    return heights


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


def _initialdir_option(key: str) -> dict[str, str]:
    path = settings_store.configured_path(key, create=True)
    return {"initialdir": str(path)} if path is not None else {}


def hq_model_cached(model_id: str = HQ_MODEL) -> bool:
    """True if the HQ model already sits in the Hugging Face cache on disk."""
    folder = "models--" + model_id.replace("/", "--")
    return (Path.home() / ".cache" / "huggingface" / "hub" / folder).exists()


class Tooltip:
    """A small hover-help popup for a Tk/ttk widget."""

    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 450) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after = self.widget.after(self.delay_ms, self._show)

    def _cancel(self) -> None:
        if self._after is not None:
            self.widget.after_cancel(self._after)
            self._after = None

    def _show(self) -> None:
        if self._tip is not None:
            return
        x = self.widget.winfo_rootx() + 14
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self._tip,
            text=self.text,
            justify="left",
            background="#2b2f38",
            foreground="#f4f5f7",
            relief="flat",
            font=("", 10),
            padx=10,
            pady=7,
            wraplength=340,
        ).pack()

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class WaveMeter(tk.Canvas):
    """Animated wave display for recording and analysis states."""

    def __init__(self, master: tk.Widget, *, height: int = 42) -> None:
        super().__init__(master, height=height, highlightthickness=1, bd=0, relief="flat")
        self.mode = "idle"
        self.level = 0.0
        self.progress = 0.0
        self.phase = 0.0
        self.configure(highlightbackground=BORDER, background=SURFACE_2)
        self.bind("<Configure>", lambda _event: self.draw())

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.draw()

    def set_level(self, level: float) -> None:
        self.level = max(0.0, min(level, 1.0))

    def set_progress(self, progress: float) -> None:
        self.progress = max(0.0, min(progress, 1.0))

    def restyle(self) -> None:
        self.configure(highlightbackground=BORDER, background=SURFACE_2)
        self.draw()

    def tick(self) -> None:
        if self.mode in {"recording", "analysis"}:
            self.phase += 0.24 if self.mode == "recording" else 0.16
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self.create_rectangle(0, 0, width, height, fill=SURFACE_2, outline=BORDER)
        if self.mode == "idle":
            self.create_line(12, height / 2, width - 12, height / 2, fill=BORDER, width=2)
            return

        level = self.level if self.mode == "recording" else 0.72
        bars = _wave_bar_heights(level, self.phase)
        gap = 3
        usable = max(1, width - 24)
        bar_w = max(2, (usable - gap * (len(bars) - 1)) / len(bars))
        x = 12
        for index, value in enumerate(bars):
            if self.mode == "analysis" and index / max(1, len(bars) - 1) > max(self.progress, 0.08):
                color = BORDER
            else:
                color = ACCENT if index % 3 else ACCENT_DARK
            bar_h = max(4, value * (height - 12))
            y0 = (height - bar_h) / 2
            self.create_rectangle(x, y0, x + bar_w, y0 + bar_h, fill=color, outline=color)
            x += bar_w + gap


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
        import lameenc

        if not self.has_recording:
            raise RuntimeError("No recording available")
        audio_f32 = self.audio_float32
        if preprocessor is not None:
            audio_f32 = preprocessor(audio_f32, SAMPLE_RATE)
        audio = np.clip(audio_f32 * 32768.0, -32768, 32767).astype(np.int16)
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(MP3_BITRATE)
        encoder.set_in_sample_rate(SAMPLE_RATE)
        encoder.set_channels(CHANNELS)
        encoder.set_quality(2)
        mp3 = encoder.encode(audio.tobytes())
        mp3 += encoder.flush()
        Path(path).write_bytes(mp3)

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
        _apply_palette(self._theme_key(), self._dark_var.get())
        self._device_index: int | None = self._settings.get("device_index")
        self._devices: list[tuple[str, int | None]] = [("システム既定", None)]
        self._notes_cache = ""
        self.recorder = MicRecorder()

        root.title(f"{APP_NAME} — {APP_TAGLINE}")
        root.geometry(self._settings.get("geometry") or "1060x740")
        root.minsize(900, 600)
        root.configure(background=BG)

        self._configure_style()
        self._build_menu()
        self._build_header()

        paned = ttk.PanedWindow(root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        left = ttk.Frame(paned, style="Card.TFrame")
        right = ttk.Frame(paned, style="Card.TFrame")
        paned.add(left, weight=3)
        paned.add(right, weight=2)

        self._build_left(left)
        self._build_right(right)
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

        style.configure(".", background=BG, foreground=TEXT, font=("", 11))
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=SURFACE)
        style.configure("Header.TFrame", background=SURFACE)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Card.TLabel", background=SURFACE, foreground=TEXT)
        style.configure("Title.TLabel", background=SURFACE, foreground=TEXT, font=("", 12, "bold"))
        style.configure("Hint.TLabel", background=SURFACE, foreground=TEXT_MUTED, font=("", 10))
        style.configure("Workflow.TLabel", background=SURFACE, foreground=ACCENT, font=("", 10))
        style.configure("Wordmark.TLabel", background=SURFACE, foreground=ACCENT, font=("", 22, "bold"))
        style.configure("Tagline.TLabel", background=SURFACE, foreground=TEXT_MUTED, font=("", 11))
        style.configure("Timer.TLabel", background=SURFACE, foreground=TEXT, font=("", 26, "bold"))
        style.configure("Status.TLabel", background=BG, foreground=TEXT, font=("", 12), padding=(10, 3))

        style.configure(
            "TButton",
            background=SURFACE,
            foreground=TEXT,
            bordercolor=BORDER,
            borderwidth=1,
            relief="flat",
            focuscolor=SURFACE,
            padding=(11, 6),
            font=("", 11),
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
                padding=(13, 7),
                font=("", 11, "bold"),
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
            padding=(11, 6),
            font=("", 11, "bold"),
        )
        style.map(
            "Step.TButton",
            background=[("pressed", ACCENT), ("active", ACCENT), ("disabled", DISABLED_BG)],
            foreground=[("pressed", "#ffffff"), ("active", "#ffffff"), ("disabled", DISABLED_FG)],
            bordercolor=[("disabled", DISABLED_BG)],
        )

        style.configure(
            "TCheckbutton",
            background=SURFACE_2,
            foreground=TEXT,
            focuscolor=SURFACE,
            indicatorcolor=SURFACE_2,
        )
        style.map(
            "TCheckbutton",
            background=[("active", SURFACE)],
            foreground=[("disabled", DISABLED_FG)],
            indicatorcolor=[("selected", ACCENT), ("active", ACCENT_SOFT)],
        )
        style.configure("TSeparator", background=BORDER)
        style.configure("TCombobox", fieldbackground=SURFACE_2, background=SURFACE, foreground=TEXT, bordercolor=BORDER, arrowcolor=TEXT)
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

    def _on_theme_change(self, _event=None) -> None:
        _apply_palette(self._theme_key(), self._dark_var.get())
        self.root.configure(background=BG)
        self._configure_style()
        self._restyle_text_widgets()
        self._set_status(self.status["text"], "ready")

    def _restyle_text_widgets(self) -> None:
        for widget_name in ("transcript", "notes_text"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.configure(
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

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="音声を開く…", command=self.open_audio, accelerator="Cmd/Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="セッションを開く…", command=self.open_session)
        file_menu.add_command(label="セッションを保存…", command=self.save_session)
        file_menu.add_separator()
        file_menu.add_command(label="文字起こしを保存…", command=self.export_transcript, accelerator="Cmd/Ctrl+S")
        file_menu.add_command(label="MP3 を保存…", command=self.export_mp3)
        menubar.add_cascade(label="ファイル", menu=file_menu)
        self.root.config(menu=menubar)

    def _build_header(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame")
        header.pack(fill="x", padx=10, pady=(10, 0))
        inner = ttk.Frame(header, style="Header.TFrame")
        inner.pack(fill="x", padx=PAD_X, pady=10)
        ttk.Label(inner, text=APP_NAME, style="Wordmark.TLabel").pack(side="left")
        ttk.Label(inner, text=f"  {APP_TAGLINE}", style="Tagline.TLabel").pack(side="left", anchor="s", pady=(0, 4))
        self.timer = ttk.Label(inner, text="00:00", style="Timer.TLabel")
        self.timer.pack(side="right")
        self.status = ttk.Label(inner, text="準備完了", style="Status.TLabel")
        self.status.pack(side="right", padx=(0, 16))
        self.dark_check = ttk.Checkbutton(inner, text="Dark", variable=self._dark_var, command=self._on_theme_change)
        self.dark_check.pack(side="right", padx=(0, 10))
        self.theme_combo = ttk.Combobox(
            inner,
            state="readonly",
            width=10,
            values=list(THEME_LABELS),
            textvariable=self._theme_var,
        )
        self.theme_combo.pack(side="right", padx=(0, 8))
        self.theme_combo.bind("<<ComboboxSelected>>", self._on_theme_change)

    # ---------- left pane (recorder + playback + transcript) ----------

    def _build_left(self, parent: ttk.Frame) -> None:
        # --- source row: input device + noise reduce ---
        source = ttk.Frame(parent, style="Card.TFrame")
        source.pack(fill="x", padx=PAD_X, pady=(PAD_Y, 4))
        ttk.Label(source, text="入力", style="Card.TLabel").pack(side="left")
        self.device_combo = ttk.Combobox(source, state="readonly", width=28)
        self.device_combo.pack(side="left", padx=(8, 0))
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_change)
        ttk.Button(source, text="↻", width=3, command=self.refresh_devices).pack(side="left", padx=(4, 0))
        ttk.Label(source, text="LLM", style="Card.TLabel").pack(side="left", padx=(16, 0))
        self.llm_combo = ttk.Combobox(
            source,
            state="readonly",
            width=18,
            values=self._llm_models,
            textvariable=self._llm_model_var,
        )
        self.llm_combo.pack(side="left", padx=(8, 0))
        self.nr_check = ttk.Checkbutton(source, text="ノイズ除去", variable=self._nr_var)
        self.nr_check.pack(side="right")
        Tooltip(self.nr_check, TOOLTIP_NR)
        self.refresh_devices()

        # --- controls: record + live | open audio + export mp3 ---
        controls = ttk.Frame(parent, style="Card.TFrame")
        controls.pack(fill="x", padx=PAD_X, pady=(6, 4))
        self.record_button = ttk.Button(
            controls, text=LABEL_RECORD, width=14, style="Accent.TButton", command=self.toggle_record
        )
        self.record_button.pack(side="left")
        Tooltip(self.record_button, TOOLTIP_RECORD)
        self.live_check = ttk.Checkbutton(controls, text="ライブ転写", variable=self._live_var)
        self.live_check.pack(side="left", padx=(12, 0))
        Tooltip(self.live_check, TOOLTIP_LIVE)
        self.export_mp3_button = ttk.Button(controls, text="MP3 保存", width=11, command=self.export_mp3, state="disabled")
        self.export_mp3_button.pack(side="right")
        Tooltip(self.export_mp3_button, TOOLTIP_MP3)
        self.open_button = ttk.Button(controls, text="音声を開く", width=11, command=self.open_audio)
        self.open_button.pack(side="right", padx=(0, 6))
        Tooltip(self.open_button, TOOLTIP_OPEN)

        # --- wave row: audio input while recording / analysis pulse while busy ---
        meter_row = ttk.Frame(parent, style="Card.TFrame")
        meter_row.pack(fill="x", padx=PAD_X, pady=(4, 10))
        self.meter_caption = ttk.Label(meter_row, text="", style="Hint.TLabel", width=16)
        self.meter_caption.pack(side="left")
        self.wave = WaveMeter(meter_row)
        self.wave.pack(side="left", fill="x", expand=True, padx=(6, 0))

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=PAD_X)

        # --- transcript section: title + export ---
        transcript_header = ttk.Frame(parent, style="Card.TFrame")
        transcript_header.pack(fill="x", padx=PAD_X, pady=(12, 4))
        ttk.Label(transcript_header, text="文字起こし", style="Title.TLabel").pack(side="left")
        self.export_txt_button = ttk.Button(
            transcript_header, text="保存", width=8, command=self.export_transcript, state="disabled"
        )
        self.export_txt_button.pack(side="right")
        Tooltip(self.export_txt_button, TOOLTIP_EXPORT_TXT)

        # --- numbered workflow actions ---
        actions = ttk.Frame(parent, style="Card.TFrame")
        actions.pack(fill="x", padx=PAD_X, pady=(0, 2))
        self.hq_button = ttk.Button(actions, text=LABEL_HQ, style="Step.TButton", command=self.hq_transcribe, state="disabled")
        self.hq_button.pack(side="left")
        Tooltip(self.hq_button, TOOLTIP_HQ)
        self.refine_button = ttk.Button(
            actions, text=LABEL_REFINE, style="Step.TButton", command=self.refine_transcript, state="disabled"
        )
        self.refine_button.pack(side="left", padx=(6, 0))
        Tooltip(self.refine_button, TOOLTIP_REFINE)
        self.minutes_button = ttk.Button(
            actions, text=LABEL_MINUTES, style="Step.TButton", command=self.generate_minutes, state="disabled"
        )
        self.minutes_button.pack(side="left", padx=(6, 0))
        Tooltip(self.minutes_button, TOOLTIP_MINUTES)

        ttk.Label(parent, text=WORKFLOW_HINT, style="Workflow.TLabel").pack(anchor="w", padx=PAD_X, pady=(4, 6))

        # --- playback bar ---
        playback = ttk.Frame(parent, style="Card.TFrame")
        playback.pack(fill="x", padx=PAD_X, pady=(0, 6))
        self.play_button = ttk.Button(playback, text=LABEL_PLAY, width=12, command=self.toggle_play, state="disabled")
        self.play_button.pack(side="left")
        Tooltip(self.play_button, TOOLTIP_PLAY)
        self.stop_play_button = ttk.Button(playback, text="■", width=4, command=self.stop_play, state="disabled")
        self.stop_play_button.pack(side="left", padx=(4, 0))
        self.position_label = ttk.Label(playback, text="00:00 / 00:00", style="Hint.TLabel")
        self.position_label.pack(side="left", padx=(10, 0))
        ttk.Label(playback, text="行頭の [時刻] をクリックでその位置から再生", style="Hint.TLabel").pack(side="right")

        text_frame = ttk.Frame(parent, style="Card.TFrame")
        text_frame.pack(fill="both", expand=True, padx=PAD_X, pady=(0, PAD_Y))
        self.transcript = tk.Text(
            text_frame,
            wrap="word",
            font=("", 12),
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

    # ---------- right pane (notes) ----------

    def _build_right(self, parent: ttk.Frame) -> None:
        notes_header = ttk.Frame(parent, style="Card.TFrame")
        notes_header.pack(fill="x", padx=PAD_X, pady=(PAD_Y, 4))
        ttk.Label(notes_header, text="メモ", style="Title.TLabel").pack(side="left")
        ttk.Button(notes_header, text="読込", width=8, command=self.load_notes).pack(side="right")
        ttk.Button(notes_header, text="保存", width=8, command=self.save_notes).pack(side="right", padx=(0, 6))

        ttk.Label(
            parent,
            text="固有名詞・専門用語・人名などを入力すると、ライブ転写と「② メモで校正」の両方で活用されます。",
            style="Hint.TLabel",
            wraplength=380,
            justify="left",
        ).pack(anchor="w", padx=PAD_X, pady=(0, 6))

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=PAD_X)

        notes_frame = ttk.Frame(parent, style="Card.TFrame")
        notes_frame.pack(fill="both", expand=True, padx=PAD_X, pady=(10, PAD_Y))
        self.notes_text = tk.Text(
            notes_frame,
            wrap="word",
            font=("", 12),
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

    # ---------- recording lifecycle ----------

    def toggle_record(self) -> None:
        if self.is_recording:
            self._stop_recording()
        elif not self._busy:
            self._start_recording()

    def _start_recording(self) -> None:
        live = self._live_var.get()
        nr = self._nr_var.get()
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

        try:
            self.recorder.start(device=self._device_index)
        except Exception as exc:
            if self._transcriber is not None:
                self._transcriber.stop()
                self._transcriber = None
            messagebox.showerror("録音を開始できませんでした", f"{type(exc).__name__}: {exc}{MIC_HELP}")
            return

        self.is_recording = True
        self._elapsed = 0
        self.timer.config(text="00:00")
        tags = [t for t, on in (("ライブ", live), ("ノイズ除去", nr)) if on]
        suffix = f"（{' / '.join(tags)}）" if tags else ""
        self._set_status(f"録音中{suffix}...", "recording")
        self.record_button.config(text=LABEL_STOP, style="Danger.TButton")
        self.export_mp3_button.config(state="disabled")
        self.open_button.config(state="disabled")
        self.hq_button.config(state="disabled")
        self._set_transcript_actions(False)
        self._set_playback_enabled(False)
        self.live_check.state(["disabled"])
        self.nr_check.state(["disabled"])
        self.device_combo.state(["disabled"])
        self.meter_caption.config(text="入力レベル")
        self.wave.set_mode("recording")
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
        self._set_status(f"停止 · {self.recorder.duration_seconds:.1f}秒", "ready")
        self.record_button.config(text=LABEL_RECORD, style="Accent.TButton")
        self.live_check.state(["!disabled"])
        self.nr_check.state(["!disabled"])
        self.device_combo.state(["!disabled"])
        self.open_button.config(state="normal")
        if self.recorder.has_recording:
            self.export_mp3_button.config(state="normal")
            self.hq_button.config(state="normal")
            self._player.load(self.recorder.audio_float32, SAMPLE_RATE)
            self._set_playback_enabled(True)
        if self._transcriber is not None:
            self._set_status("文字起こしを確定中...", "busy")
            self.root.update_idletasks()
            self._transcriber.stop()
            self._drain_transcript_queue()
            self._transcriber = None
            self._set_status(f"停止 · {self.recorder.duration_seconds:.1f}秒", "ready")
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
        self.device_combo["values"] = [label for label, _ in self._devices]
        if self._device_index is not None:
            for i, (_label, idx) in enumerate(self._devices):
                if idx == self._device_index:
                    self.device_combo.current(i)
                    return
        self.device_combo.current(0)
        self._device_index = None

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
            self.play_button.config(text=LABEL_PLAY)
        else:
            self._player.play()
            self.play_button.config(text=LABEL_PAUSE)

    def stop_play(self) -> None:
        self._player.reset()
        self.play_button.config(text=LABEL_PLAY)

    def _seek(self, seconds: float) -> None:
        if not self._player.has_audio:
            return
        self._player.play(from_seconds=seconds)
        self.play_button.config(text=LABEL_PAUSE)

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
            messagebox.showinfo("MP3 保存", "録音がありません。")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".mp3",
            filetypes=[("MP3 音声", "*.mp3"), ("すべてのファイル", "*.*")],
            initialfile="recording.mp3",
            title="録音を保存",
            **_initialdir_option("audio_dir"),
        )
        if not path:
            return
        preprocessor = self._build_preprocessor() if self._nr_var.get() else None
        try:
            self.recorder.encode_mp3(path, preprocessor=preprocessor)
        except Exception as exc:
            messagebox.showerror("エラー", f"保存できませんでした:\n{exc}")
            return
        messagebox.showinfo("保存しました", f"保存先:\n{path}")

    def export_transcript(self) -> None:
        if not self._has_transcript_text():
            messagebox.showinfo("文字起こしを保存", "文字起こしテキストがありません。")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("テキスト", "*.txt"), ("Markdown", "*.md"), ("すべてのファイル", "*.*")],
            initialfile="transcript.txt",
            title="文字起こしを保存",
            **_initialdir_option("transcripts_dir"),
        )
        if not path:
            return
        text = self.transcript.get("1.0", "end").rstrip() + "\n"
        try:
            Path(path).write_text(text, encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("エラー", f"保存できませんでした:\n{exc}")
            return
        messagebox.showinfo("保存しました", f"保存先:\n{path}")

    # ---------- notes ----------

    def _on_notes_change(self, _event) -> None:
        self._notes_cache = self.notes_text.get("1.0", "end").strip()

    def save_notes(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("テキスト", "*.txt"), ("Markdown", "*.md"), ("すべてのファイル", "*.*")],
            initialfile="notes.txt",
            title="メモを保存",
            **_initialdir_option("notes_dir"),
        )
        if not path:
            return
        text = self.notes_text.get("1.0", "end").rstrip() + "\n"
        try:
            Path(path).write_text(text, encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("エラー", f"保存できませんでした:\n{exc}")

    def load_notes(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("テキスト", "*.txt"), ("Markdown", "*.md"), ("すべてのファイル", "*.*")],
            title="メモを読み込み",
            **_initialdir_option("notes_dir"),
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("エラー", f"読み込めませんでした:\n{exc}")
            return
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", text)
        self._on_notes_change(None)

    # ---------- open existing audio file ----------

    def open_audio(self) -> None:
        if self.is_recording or self._busy:
            return
        path = filedialog.askopenfilename(
            title="音声ファイルを開く",
            filetypes=AUDIO_FILETYPES,
            **_initialdir_option("audio_dir"),
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
        self.hq_button.config(state="disabled", text="文字起こし中...")
        self.open_button.config(state="disabled")
        self._set_transcript_actions(False)
        what = f" · {label}" if label else ""
        if hq_model_cached():
            self._set_status(f"高精度で文字起こし中（{HQ_MODEL_LABEL}）{what}...", "busy")
        else:
            self._set_status("初回モデルをダウンロード中（数分かかります）...", "busy")
        self.meter_caption.config(text="文字起こし進捗")
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
        self.hq_button.config(text=LABEL_HQ)
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
                self._set_status(f"高精度文字起こし完了（{HQ_MODEL_LABEL}）", "ok")
            else:
                self._set_status("文字起こし結果が空でした", "busy")
        elif kind == "error":
            self._set_status("文字起こしに失敗しました", "recording")
            messagebox.showerror("文字起こしに失敗しました", payload)
        self._sync_transcript_actions()

    # ---------- refine ----------

    def refine_transcript(self) -> None:
        transcript = self.transcript.get("1.0", "end").strip()
        notes = self._notes_cache
        if not transcript:
            messagebox.showinfo("② メモで校正", "文字起こしテキストがありません。")
            return
        if not notes:
            messagebox.showinfo("② メモで校正", "メモが空です。固有名詞や用語をメモ欄に入力してから実行してください。")
            return
        model = self._selected_llm_model()
        self._busy = True
        self.refine_button.config(state="disabled", text="校正中...")
        self.hq_button.config(state="disabled")
        self.minutes_button.config(state="disabled")
        self._set_status(f"Ollama で校正中（{model}）...", "busy")
        self.meter_caption.config(text="解析中")
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
        self.refine_button.config(text=LABEL_REFINE)
        self.meter_caption.config(text="")
        self.wave.set_mode("idle")
        if kind == "ok":
            self._replace_transcript(payload)
            self._set_status("校正完了", "ok")
        elif kind == "error":
            self._set_status("校正に失敗しました", "recording")
            messagebox.showerror("校正に失敗しました", payload)
        if self.recorder.has_recording:
            self.hq_button.config(state="normal")
        self._sync_transcript_actions()

    # ---------- minutes ----------

    def generate_minutes(self) -> None:
        transcript = self.transcript.get("1.0", "end").strip()
        if not transcript:
            messagebox.showinfo("③ 議事録を作成", "文字起こしテキストがありません。")
            return
        model = self._selected_llm_model()
        self._busy = True
        self.minutes_button.config(state="disabled", text="生成中...")
        self.refine_button.config(state="disabled")
        self.hq_button.config(state="disabled")
        self._set_status(f"Ollama で議事録を生成中（{model}）...", "busy")
        self.meter_caption.config(text="解析中")
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
        self.minutes_button.config(text=LABEL_MINUTES)
        self.meter_caption.config(text="")
        self.wave.set_mode("idle")
        if self.recorder.has_recording:
            self.hq_button.config(state="normal")
        self._sync_transcript_actions()
        if kind == "ok":
            self._set_status("議事録ができました", "ok")
            self._show_minutes(payload)
        elif kind == "error":
            self._set_status("議事録の生成に失敗しました", "recording")
            messagebox.showerror("議事録の生成に失敗しました", payload)

    def _show_minutes(self, markdown: str) -> None:
        win = tk.Toplevel(self.root)
        win.title(f"{APP_NAME} — 議事録")
        win.geometry("680x600")
        win.configure(background=BG)
        frame = ttk.Frame(win, style="Card.TFrame")
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        text = tk.Text(
            frame,
            wrap="word",
            font=("", 12),
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
                title="議事録を保存",
                parent=win,
                **_initialdir_option("minutes_dir"),
            )
            if path:
                Path(path).write_text(text.get("1.0", "end").rstrip() + "\n", encoding="utf-8")

        ttk.Button(btn_row, text="閉じる", command=win.destroy).pack(side="right")
        ttk.Button(btn_row, text=".md として保存", style="Accent.TButton", command=save).pack(side="right", padx=(0, 6))

    # ---------- session save / restore ----------

    def save_session(self) -> None:
        transcript = self.transcript.get("1.0", "end").rstrip()
        notes = self.notes_text.get("1.0", "end").rstrip()
        if not self._player.has_audio and not transcript and not notes:
            messagebox.showinfo("セッションを保存", "保存する内容がありません。")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".zip",
            filetypes=[("セッション", "*.zip"), ("すべてのファイル", "*.*")],
            initialfile="session.zip",
            title="セッションを保存",
            **_initialdir_option("sessions_dir"),
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
            messagebox.showerror("セッションの保存に失敗しました", f"{type(exc).__name__}: {exc}")
            return
        messagebox.showinfo("保存しました", f"セッションの保存先:\n{path}")

    def open_session(self) -> None:
        if self.is_recording or self._busy:
            return
        path = filedialog.askopenfilename(
            title="セッションを開く",
            filetypes=[("セッション", "*.zip"), ("すべてのファイル", "*.*")],
            **_initialdir_option("sessions_dir"),
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
            messagebox.showerror("セッションを開けませんでした", f"{type(exc).__name__}: {exc}")
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
        self._set_status(f"セッションを読み込みました · {Path(path).name}", "ready")

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
            self.meter_caption.config(text=f"文字起こし進捗 · {pct}%")

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
        if not playing and self.play_button["text"] == LABEL_PAUSE:
            self.play_button.config(text=LABEL_PLAY)

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
        palette = {
            "ready": (BG, TEXT),
            "recording": ("#fce4e2", DANGER_DARK),
            "busy": ("#fff3d6", "#9a6b00"),
            "ok": ("#dff3e8", OK_GREEN),
        }
        bg, fg = palette.get(kind, (BG, TEXT))
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
                "noise_reduce": bool(self._nr_var.get()),
                "live": bool(self._live_var.get()),
                "llm_model": self._selected_llm_model(),
                "theme": self._theme_key(),
                "dark_mode": bool(self._dark_var.get()),
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
