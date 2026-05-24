"""Tests for Lethe pure-logic helpers and the Player.

These exercise only headless logic -- no audio device, display, or
network is touched. Importing ``audios.lethe`` imports tkinter, which is
safe without a display; only ``tk.Tk()`` would need one, and it is never
called here.
"""

from __future__ import annotations

import wave
import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import audios.lethe as lethe
from audios.lethe import PLAYBACK_SR, App, Player, _fmt_time, _is_connection_error, _parse_leading_timestamp, describe_error


def test_fmt_time_minutes_and_hours():
    assert _fmt_time(0) == "00:00"
    assert _fmt_time(125) == "02:05"
    assert _fmt_time(599) == "09:59"
    assert _fmt_time(3725) == "1:02:05"
    assert _fmt_time(-5) == "00:00"


def test_parse_leading_timestamp():
    assert _parse_leading_timestamp("[00:04] hello") == 4
    assert _parse_leading_timestamp("[02:05] x") == 125
    assert _parse_leading_timestamp("[1:02:05] x") == 3725
    assert _parse_leading_timestamp("  [00:10] indented") == 10
    assert _parse_leading_timestamp("no timestamp here") is None
    assert _parse_leading_timestamp("") is None


def test_connection_error_detection():
    assert _is_connection_error(ConnectionRefusedError("connection refused"))
    assert _is_connection_error(RuntimeError("could not connect to localhost:11434"))
    assert not _is_connection_error(ValueError("bad transcript"))


def test_describe_error_ollama_gives_guidance():
    msg = describe_error(ConnectionRefusedError("refused"), ollama=True)
    assert "ollama serve" in msg
    custom = describe_error(ConnectionRefusedError("refused"), ollama=True, model="qwen2.5:7b", ollama_url="http://example")
    assert "qwen2.5:7b" in custom
    assert "http://example" in custom
    plain = describe_error(ValueError("boom"), ollama=True)
    assert plain == "ValueError: boom"


def test_apply_palette_switches_theme_globals():
    lethe._apply_palette("ember", True)
    assert lethe.BG == lethe.THEMES["ember"]["dark"]["bg"]
    assert lethe.ACCENT == lethe.THEMES["ember"]["dark"]["accent"]

    lethe._apply_palette("missing", False)
    assert lethe.BG == lethe.THEMES["midnight"]["light"]["bg"]


def test_wave_bar_heights_are_normalized_and_react_to_level():
    quiet = lethe._wave_bar_heights(0.0, 0.0, count=8)
    loud = lethe._wave_bar_heights(1.0, 0.0, count=8)

    assert len(quiet) == 8
    assert len(loud) == 8
    assert all(0.0 < value <= 1.0 for value in quiet + loud)
    assert sum(loud) > sum(quiet)


def test_player_load_duration_and_position():
    player = Player()
    assert not player.has_audio
    assert player.duration == 0.0
    player.load(np.zeros(16000 * 3, dtype=np.float32), 16000)
    assert player.has_audio
    assert abs(player.duration - 3.0) < 1e-6
    assert player.position == 0.0
    assert not player.is_playing


def test_player_write_wav_roundtrip(tmp_path):
    player = Player()
    audio = np.linspace(-0.5, 0.5, 8000, dtype=np.float32)
    player.load(audio, 16000)
    out = tmp_path / "out.wav"
    player.write_wav(out)
    with wave.open(str(out), "rb") as wav:
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1
        assert wav.getnframes() == 8000


def test_open_session_without_audio_clears_previous_playback(tmp_path, monkeypatch):
    bundle = tmp_path / "session.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("transcript.txt", "新しい文字起こし\n")
        zf.writestr("notes.txt", "新しいメモ\n")

    monkeypatch.setattr(lethe.filedialog, "askopenfilename", lambda **_kwargs: str(bundle))

    class DummyText:
        def __init__(self) -> None:
            self.value = ""

        def delete(self, *_args) -> None:
            self.value = ""

        def insert(self, *_args) -> None:
            self.value = _args[-1]

    class DummyButton:
        def __init__(self) -> None:
            self.state = None

        def config(self, **kwargs) -> None:
            if "state" in kwargs:
                self.state = kwargs["state"]

    class DummyRecorder:
        def __init__(self) -> None:
            self.cleaned = False

        def cleanup(self) -> None:
            self.cleaned = True

    player = Player()
    player.load(np.ones(1600, dtype=np.float32), PLAYBACK_SR)
    assert player.has_audio

    notes = DummyText()
    recorder = DummyRecorder()
    playback_enabled: list[bool] = []
    statuses: list[tuple[str, str]] = []
    transcript_holder = {"value": ""}
    app = SimpleNamespace(
        is_recording=False,
        _busy=False,
        notes_text=notes,
        _on_notes_change=lambda _event: None,
        _replace_transcript=lambda text: transcript_holder.__setitem__("value", text),
        recorder=recorder,
        export_mp3_button=DummyButton(),
        hq_button=DummyButton(),
        _player=player,
        _load_playback_bytes=lambda _audio_bytes: (_ for _ in ()).throw(AssertionError("unexpected audio")),
        _set_playback_enabled=lambda enabled: playback_enabled.append(enabled),
        _sync_transcript_actions=lambda: None,
        _set_status=lambda text, kind: statuses.append((text, kind)),
    )

    App.open_session(app)

    assert notes.value == "新しいメモ\n"
    assert transcript_holder["value"] == "新しい文字起こし\n"
    assert recorder.cleaned is True
    assert player.has_audio is False
    assert playback_enabled == [False]
    assert statuses[-1] == (f"セッションを読み込みました · {Path(bundle).name}", "ready")
