"""Persisted Lethe preferences and stale temp-file cleanup.

Settings live in ``~/.lethe/settings.json``. Only the keys in ``DEFAULTS``
are read or written, so an old or hand-edited file can never inject
unexpected keys into the GUI. Every function degrades quietly: a missing
or corrupt file just yields defaults, and a write failure is swallowed --
preferences are a convenience, not something worth crashing over.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

SETTINGS_PATH = Path.home() / ".lethe" / "settings.json"

DEFAULTS: dict = {
    "device_index": None,
    "noise_reduce": False,
    "live": False,
    "geometry": "",
}

# Temp-WAV name patterns Lethe creates; swept on startup.
_TEMP_PATTERNS = ("micrec-*.wav", "session-audio-*.wav", "session-load-*.wav")


def load_settings() -> dict:
    """Return saved settings merged onto defaults; defaults if absent/corrupt."""
    out = dict(DEFAULTS)
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return out
    if isinstance(data, dict):
        out.update({k: v for k, v in data.items() if k in DEFAULTS})
    return out


def save_settings(values: dict) -> None:
    """Write the known keys of ``values`` to the settings file; ignore errors."""
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        keep = {k: values[k] for k in DEFAULTS if k in values}
        SETTINGS_PATH.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def sweep_temp_files(max_age_hours: float = 6.0) -> int:
    """Delete leftover Lethe temp WAVs older than ``max_age_hours``.

    Recording streams to a temp WAV; a crash leaves it orphaned. Sweeping on
    startup keeps the temp directory from filling up. Returns the count
    removed.
    """
    cutoff = time.time() - max_age_hours * 3600
    tmp_dir = Path(tempfile.gettempdir())
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
