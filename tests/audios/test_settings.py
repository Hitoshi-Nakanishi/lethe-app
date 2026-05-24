"""Tests for Lethe settings persistence and temp-file sweeping."""

from __future__ import annotations

import os
import tempfile
import time

from audios import settings as st


def test_load_missing_file_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "SETTINGS_PATH", tmp_path / "settings.json")
    assert st.load_settings() == st.DEFAULTS


def test_load_returns_independent_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "SETTINGS_PATH", tmp_path / "settings.json")
    loaded = st.load_settings()
    loaded["device_index"] = 99
    assert st.DEFAULTS["device_index"] is None  # mutating the copy must not touch DEFAULTS


def test_save_then_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "SETTINGS_PATH", tmp_path / "nested" / "settings.json")
    st.save_settings({"device_index": 3, "noise_reduce": True, "live": True, "geometry": "800x600", "junk": "ignored"})
    loaded = st.load_settings()
    assert loaded["device_index"] == 3
    assert loaded["noise_reduce"] is True
    assert loaded["live"] is True
    assert loaded["geometry"] == "800x600"
    assert "junk" not in loaded  # unknown keys are dropped


def test_load_config_merges_default_toml_paths(tmp_path):
    config = tmp_path / "default.toml"
    config.write_text(
        """
[paths]
settings_dir = "~/custom-lethe"
transcripts_dir = "exports/transcripts"
unknown = "ignored"
""",
        encoding="utf-8",
    )

    loaded = st.load_config(config)

    assert loaded["paths"]["settings_dir"] == "~/custom-lethe"
    assert loaded["paths"]["transcripts_dir"] == "exports/transcripts"
    assert "unknown" not in loaded["paths"]
    assert "sessions_dir" in loaded["paths"]


def test_settings_path_uses_default_toml_settings_dir(tmp_path, monkeypatch):
    config = tmp_path / "default.toml"
    config.write_text("[paths]\nsettings_dir = \"configured\"\n", encoding="utf-8")
    monkeypatch.setattr(st, "CONFIG_PATH", config)
    monkeypatch.chdir(tmp_path)

    assert st.settings_path() == tmp_path / "configured" / "settings.json"


def test_load_corrupt_file_returns_defaults(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(st, "SETTINGS_PATH", path)
    assert st.load_settings() == st.DEFAULTS


def test_sweep_temp_files_removes_only_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    stale = tmp_path / "micrec-123-456.wav"
    stale.write_bytes(b"old")
    old_ts = time.time() - 10 * 3600
    os.utime(stale, (old_ts, old_ts))
    fresh = tmp_path / "micrec-999-999.wav"
    fresh.write_bytes(b"new")
    unrelated = tmp_path / "keepme.wav"
    unrelated.write_bytes(b"keep")

    removed = st.sweep_temp_files(max_age_hours=6.0)

    assert removed == 1
    assert not stale.exists()
    assert fresh.exists()
    assert unrelated.exists()


def test_sweep_temp_files_uses_configured_temp_dir(tmp_path, monkeypatch):
    configured = tmp_path / "configured-temp"
    config = tmp_path / "default.toml"
    config.write_text(f"[paths]\ntemp_dir = {str(configured)!r}\n", encoding="utf-8")
    monkeypatch.setattr(st, "CONFIG_PATH", config)

    stale = configured / "session-load-1.wav"
    configured.mkdir()
    stale.write_bytes(b"old")
    old_ts = time.time() - 10 * 3600
    os.utime(stale, (old_ts, old_ts))

    assert st.sweep_temp_files(max_age_hours=6.0) == 1
    assert not stale.exists()
