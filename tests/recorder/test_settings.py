"""Tests for Lethe settings persistence and temp-file sweeping."""

from __future__ import annotations

import os
import tempfile
import time

import pytest

from recorder import settings as st


@pytest.fixture(autouse=True)
def clear_config_env(monkeypatch):
    monkeypatch.delenv(st.CONFIG_ENV, raising=False)


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
    st.save_settings(
        {
            "device_index": 3,
            "mic_capture": False,
            "noise_reduce": True,
            "live": True,
            "llm_model": "qwen2.5:7b",
            "theme": "ember",
            "dark_mode": False,
            "language": "en",
            "font_size": 13,
            "geometry": "800x600",
            "junk": "ignored",
        }
    )
    loaded = st.load_settings()
    assert loaded["device_index"] == 3
    assert loaded["mic_capture"] is False
    assert loaded["noise_reduce"] is True
    assert loaded["live"] is True
    assert loaded["llm_model"] == "qwen2.5:7b"
    assert loaded["theme"] == "ember"
    assert loaded["dark_mode"] is False
    assert loaded["language"] == "en"
    assert loaded["font_size"] == 13
    assert loaded["geometry"] == "800x600"
    assert "junk" not in loaded  # unknown keys are dropped


def test_load_config_merges_default_toml_paths(tmp_path):
    config = tmp_path / "default.toml"
    config.write_text(
        """
[paths]
settings_dir = "~/custom-lethe"
datasets_dir = "exports/datasets"
unknown = "ignored"

[models]
default_llm_model = "qwen2.5:7b"
llm_models = ["qwen2.5:7b", "mistral:7b"]

[filenames]
mp3_template = "{timestamp}_{meeting_name}.mp3"
meeting_name = "standup"
timestamp_format = "%Y%m%d_%H%M"

[defaults]
live = false
noise_reduce = true
llm_model = "mistral:7b"
language = "en"
font_size = 13
""",
        encoding="utf-8",
    )

    loaded = st.load_config(config)

    assert loaded["paths"]["settings_dir"] == "~/custom-lethe"
    assert loaded["paths"]["datasets_dir"] == "exports/datasets"
    assert "unknown" not in loaded["paths"]
    assert set(loaded["paths"]) == {"settings_dir", "temp_dir", "datasets_dir"}
    assert loaded["models"]["default_llm_model"] == "qwen2.5:7b"
    assert loaded["models"]["llm_models"] == ["qwen2.5:7b", "mistral:7b"]
    assert loaded["filenames"]["mp3_template"] == "{timestamp}_{meeting_name}.mp3"
    assert loaded["filenames"]["dataset_template"] == "{timestamp}_{meeting_name}"
    assert loaded["filenames"]["meeting_name"] == "standup"
    assert loaded["filenames"]["timestamp_format"] == "%Y%m%d_%H%M"
    assert loaded["defaults"]["live"] is False
    assert loaded["defaults"]["noise_reduce"] is True
    assert loaded["defaults"]["llm_model"] == "mistral:7b"
    assert loaded["defaults"]["language"] == "en"
    assert loaded["defaults"]["font_size"] == 13


def test_load_settings_uses_toml_defaults_before_saved_preferences(tmp_path, monkeypatch):
    config = tmp_path / "default.toml"
    config.write_text(
        """
[defaults]
mic_capture = false
noise_reduce = true
live = false
llm_model = "qwen2.5:7b"
theme = "aurora"
dark_mode = false
language = "en"
font_size = 12
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(st, "CONFIG_PATH", config)
    monkeypatch.setattr(st, "SETTINGS_PATH", tmp_path / "settings.json")

    loaded = st.load_settings()

    assert loaded["mic_capture"] is False
    assert loaded["noise_reduce"] is True
    assert loaded["live"] is False
    assert loaded["llm_model"] == "qwen2.5:7b"
    assert loaded["theme"] == "aurora"
    assert loaded["dark_mode"] is False
    assert loaded["language"] == "en"
    assert loaded["font_size"] == 12


def test_saved_settings_override_toml_defaults(tmp_path, monkeypatch):
    config = tmp_path / "default.toml"
    config.write_text('[defaults]\nlive = false\nllm_model = "qwen2.5:7b"\n', encoding="utf-8")
    monkeypatch.setattr(st, "CONFIG_PATH", config)
    monkeypatch.setattr(st, "SETTINGS_PATH", tmp_path / "settings.json")
    st.save_settings({"live": True, "llm_model": "mistral:7b"})

    loaded = st.load_settings()

    assert loaded["live"] is True
    assert loaded["llm_model"] == "mistral:7b"


def test_invalid_toml_defaults_are_ignored(tmp_path):
    config = tmp_path / "default.toml"
    config.write_text(
        """
[defaults]
live = "false"
llm_model = 123
font_size = "big"
""",
        encoding="utf-8",
    )

    loaded = st.load_config(config)

    assert loaded["defaults"]["live"] is True
    assert loaded["defaults"]["llm_model"] == ""
    assert loaded["defaults"]["font_size"] == 11


def test_llm_models_includes_default_when_missing(tmp_path, monkeypatch):
    config = tmp_path / "default.toml"
    config.write_text(
        """
[models]
default_llm_model = "custom:latest"
llm_models = ["llama3.1:8b"]
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(st, "CONFIG_PATH", config)

    assert st.llm_models() == ["custom:latest", "llama3.1:8b"]


def test_settings_path_uses_default_toml_settings_dir(tmp_path, monkeypatch):
    config = tmp_path / "default.toml"
    config.write_text('[paths]\nsettings_dir = "configured"\n', encoding="utf-8")
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
