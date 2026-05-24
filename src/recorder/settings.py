"""Persisted Lethe preferences and stale temp-file cleanup.

Settings live in ``~/.lethe/settings.json``. Only the keys in ``DEFAULTS``
are read or written, so an old or hand-edited file can never inject
unexpected keys into the GUI. Every function degrades quietly: a missing
or corrupt file just yields defaults, and a write failure is swallowed --
preferences are a convenience, not something worth crashing over.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import tomllib
from pathlib import Path

DEFAULT_SETTINGS_PATH = Path.home() / ".lethe" / "settings.json"
SETTINGS_PATH = DEFAULT_SETTINGS_PATH
CONFIG_ENV = "LETHE_CONFIG"
CONFIG_PATH = Path.cwd() / "default.toml"

DEFAULT_CONFIG: dict = {
    "paths": {
        "settings_dir": "~/.lethe",
        "temp_dir": "",
        "audio_dir": "",
        "transcripts_dir": "",
        "notes_dir": "",
        "minutes_dir": "",
        "sessions_dir": "",
    },
    "models": {
        "whisper_live_model": "medium",
        "whisper_final_model": "large-v3",
        "whisper_language": "ja",
        "ollama_url": "http://localhost:11434",
        "default_llm_model": "llama3.1:8b",
        "llm_models": ["llama3.1:8b", "qwen2.5:7b", "mistral:7b"],
    },
}

DEFAULTS: dict = {
    "device_index": None,
    "mic_capture": True,
    "noise_reduce": False,
    "live": False,
    "geometry": "",
    "llm_model": "",
    "theme": "midnight",
    "dark_mode": True,
    "language": "ja",
}

# Temp-WAV name patterns Lethe creates; swept on startup.
_TEMP_PATTERNS = ("micrec-*.wav", "session-audio-*.wav", "session-load-*.wav")


def _config_path() -> Path:
    return Path(os.environ.get(CONFIG_ENV, CONFIG_PATH)).expanduser()


def _merge_config(data: dict) -> dict:
    out = {
        "paths": dict(DEFAULT_CONFIG["paths"]),
        "models": dict(DEFAULT_CONFIG["models"]),
    }
    paths = data.get("paths") if isinstance(data, dict) else None
    if isinstance(paths, dict):
        out["paths"].update({k: str(v) for k, v in paths.items() if k in out["paths"] and v is not None})
    models = data.get("models") if isinstance(data, dict) else None
    if isinstance(models, dict):
        for key, value in models.items():
            if key not in out["models"] or value is None:
                continue
            if key == "llm_models" and isinstance(value, list):
                out["models"][key] = [str(item) for item in value if str(item).strip()]
            elif key != "llm_models":
                out["models"][key] = str(value)
    return out


def load_config(path: str | Path | None = None) -> dict:
    """Return ``default.toml`` values merged onto built-in defaults."""
    config_path = Path(path).expanduser() if path is not None else _config_path()
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return _merge_config({})
    return _merge_config(data)


def configured_path(key: str, *, create: bool = False) -> Path | None:
    """Return an expanded path from ``[paths]`` or ``None`` when unset."""
    config_path = _config_path()
    value = load_config(config_path)["paths"].get(key, "")
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    """Return the effective settings.json path.

    Tests can still monkeypatch ``SETTINGS_PATH`` directly. In normal app use,
    ``[paths].settings_dir`` in ``default.toml`` controls the parent directory.
    """
    if SETTINGS_PATH != DEFAULT_SETTINGS_PATH:
        return SETTINGS_PATH
    settings_dir = configured_path("settings_dir", create=False)
    return (settings_dir or DEFAULT_SETTINGS_PATH.parent) / "settings.json"


def temp_dir() -> Path:
    """Return the configured temp directory, or the OS temp directory."""
    return configured_path("temp_dir", create=True) or Path(tempfile.gettempdir())


def temp_path(name: str) -> Path:
    """Return a path for a Lethe temporary file in the configured temp dir."""
    return temp_dir() / name


def model_config() -> dict:
    return load_config()["models"]


def llm_models() -> list[str]:
    models = model_config().get("llm_models", [])
    default = str(model_config().get("default_llm_model", "")).strip()
    out = [str(item).strip() for item in models if str(item).strip()]
    if default and default not in out:
        out.insert(0, default)
    return out


def load_settings() -> dict:
    """Return saved settings merged onto defaults; defaults if absent/corrupt."""
    out = dict(DEFAULTS)
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    if isinstance(data, dict):
        out.update({k: v for k, v in data.items() if k in DEFAULTS})
    return out


def save_settings(values: dict) -> None:
    """Write the known keys of ``values`` to the settings file; ignore errors."""
    try:
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        keep = {k: values[k] for k in DEFAULTS if k in values}
        path.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def sweep_temp_files(max_age_hours: float = 6.0) -> int:
    """Delete leftover Lethe temp WAVs older than ``max_age_hours``.

    Recording streams to a temp WAV; a crash leaves it orphaned. Sweeping on
    startup keeps the temp directory from filling up. Returns the count
    removed.
    """
    cutoff = time.time() - max_age_hours * 3600
    tmp_dir = temp_dir()
    removed = 0
    for pattern in _TEMP_PATTERNS:
        for path in tmp_dir.glob(pattern):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
    return removed
