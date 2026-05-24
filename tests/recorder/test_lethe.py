"""Tests for Lethe pure-logic helpers and the Player.

These exercise only headless logic -- no audio device, display, or
network is touched. Importing ``recorder.lethe`` imports tkinter, which is
safe without a display; only ``tk.Tk()`` would need one, and it is never
called here.
"""

from __future__ import annotations

import json
import time
import wave
import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import recorder.lethe as lethe
from recorder import ui
from recorder.lethe import (
    PLAYBACK_SR,
    App,
    Player,
    _coerce_font_size,
    _fmt_time,
    _is_connection_error,
    _parse_leading_timestamp,
    _safe_filename_part,
    _suggested_dataset_name,
    _suggested_mp3_filename,
    describe_error,
    text_for,
)


def test_fmt_time_minutes_and_hours():
    assert _fmt_time(0) == "00:00"
    assert _fmt_time(125) == "02:05"
    assert _fmt_time(599) == "09:59"
    assert _fmt_time(3725) == "1:02:05"
    assert _fmt_time(-5) == "00:00"


def test_coerce_font_size_clamps_invalid_and_extreme_values():
    assert _coerce_font_size("bad") == 11
    assert _coerce_font_size(3) == 9
    assert _coerce_font_size(99) == 18
    assert _coerce_font_size("13") == 13


def test_suggested_mp3_filename_uses_configured_template(monkeypatch):
    monkeypatch.setattr(
        lethe.settings_store,
        "filename_config",
        lambda: {
            "mp3_template": "{timestamp}_{meeting_name}.mp3",
            "meeting_name": "Weekly Sync",
            "timestamp_format": "%Y%m%d_%H%M",
        },
    )
    now = time.mktime((2026, 5, 25, 9, 8, 0, 0, 0, -1))

    assert _suggested_mp3_filename(now) == "20260525_0908_Weekly_Sync.mp3"


def test_suggested_mp3_filename_sanitizes_parts_and_adds_extension(monkeypatch):
    monkeypatch.setattr(
        lethe.settings_store,
        "filename_config",
        lambda: {
            "mp3_template": "{meeting_name}_{timestamp}",
            "meeting_name": 'Client/A: "Planning"',
            "timestamp_format": "%Y/%m/%d %H:%M",
        },
    )
    now = time.mktime((2026, 5, 25, 9, 8, 0, 0, 0, -1))

    assert _suggested_mp3_filename(now) == "Client_A_Planning_2026_05_25_09_08.mp3"


def test_suggested_dataset_name_uses_configured_template(monkeypatch):
    monkeypatch.setattr(
        lethe.settings_store,
        "filename_config",
        lambda: {
            "dataset_template": "{timestamp}_{meeting_name}_dataset",
            "meeting_name": "Design Review",
            "timestamp_format": "%Y%m%d_%H%M",
        },
    )
    now = time.mktime((2026, 5, 25, 9, 8, 0, 0, 0, -1))

    assert _suggested_dataset_name(now) == "20260525_0908_Design_Review_dataset"


def test_safe_filename_part_falls_back_when_empty():
    assert _safe_filename_part(":/") == "meeting"


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
    quiet = ui._wave_bar_heights(0.0, 0.0, count=8)
    loud = ui._wave_bar_heights(1.0, 0.0, count=8)

    assert len(quiet) == 8
    assert len(loud) == 8
    assert all(0.0 < value <= 1.0 for value in quiet + loud)
    assert sum(loud) > sum(quiet)


def test_text_for_switches_between_japanese_and_english():
    assert text_for("ja", "record") == "●  録音開始"
    assert text_for("en", "record") == "●  Record"
    assert text_for("en", "system_default_input") == "System default"
    assert text_for("en", "refresh_input") == "Refresh"
    assert text_for("ja", "mic_capture") == "マイク音声を取る"
    assert text_for("en", "mic_off_tag") == "Mic off"
    assert text_for("missing", "record") == "●  録音開始"
    assert text_for("en", "stopped", seconds=1.25) == "Stopped · 1.2s"


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
        _tr=lambda key, **kwargs: text_for("ja", key, **kwargs),
    )

    App.open_session(app)

    assert notes.value == "新しいメモ\n"
    assert transcript_holder["value"] == "新しい文字起こし\n"
    assert recorder.cleaned is True
    assert player.has_audio is False
    assert playback_enabled == [False]
    assert statuses[-1] == (f"セッションを読み込みました · {Path(bundle).name}", "ready")


def test_export_dataset_writes_one_to_one_folder_mapping(tmp_path, monkeypatch):
    folder = tmp_path / "20260525_0908_standup"
    monkeypatch.setattr(lethe.filedialog, "asksaveasfilename", lambda **_kwargs: str(folder))
    infos: list[tuple[str, str]] = []
    monkeypatch.setattr(lethe.messagebox, "showinfo", lambda title, message: infos.append((title, message)))

    class DummyText:
        def __init__(self, value: str) -> None:
            self.value = value

        def get(self, *_args) -> str:
            return self.value

    app = SimpleNamespace(
        transcript=DummyText("[00:00] hello\n"),
        notes_text=DummyText("# Notes\n- Alice\n"),
        recorder=SimpleNamespace(has_recording=False),
        _player=SimpleNamespace(has_audio=True, duration=12.34),
        _write_dataset_audio=lambda path: Path(path).write_bytes(b"mp3"),
        _tr=lambda key, **kwargs: text_for("en", key, **kwargs),
    )

    App.export_dataset(app)

    audio = folder / "audio.mp3"
    transcript = folder / "transcript.md"
    memo = folder / "memo.md"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert audio.read_bytes() == b"mp3"
    assert transcript.read_text(encoding="utf-8") == "[00:00] hello\n"
    assert memo.read_text(encoding="utf-8") == "# Notes\n- Alice\n"
    assert manifest["dataset_id"] == folder.name
    assert manifest["path_mapping"] == {
        "audio": "audio.mp3",
        "transcript": "transcript.md",
        "memo": "memo.md",
    }
    assert [item["role"] for item in manifest["files"]] == ["audio", "transcript", "memo"]
    assert infos[-1] == ("Saved", f"Dataset saved to:\n{folder}")
