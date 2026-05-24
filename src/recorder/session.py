"""Detached start/stop control for ``recorder record``.

A *session* is a directory holding three small files:

  - ``pid``     — the recorder process PID
  - ``output``  — path of the WAV being written
  - ``stop``    — empty flag file; the recorder polls it once per chunk
                  and finalizes the WAV cleanly when it appears

This deliberately avoids signals on Windows (where ``SIGTERM`` is a hard
``TerminateProcess`` and would leave the WAV header with wrong frame counts).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Session:
    dir: Path

    @property
    def pid_file(self) -> Path:
        return self.dir / "pid"

    @property
    def output_file(self) -> Path:
        return self.dir / "output"

    @property
    def stop_flag(self) -> Path:
        return self.dir / "stop"

    @property
    def log_file(self) -> Path:
        return self.dir / "log"

    def pid(self) -> int | None:
        try:
            return int(self.pid_file.read_text().strip())
        except FileNotFoundError:
            return None

    def output(self) -> Path | None:
        try:
            return Path(self.output_file.read_text().strip())
        except FileNotFoundError:
            return None

    def is_running(self) -> bool:
        pid = self.pid()
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # process exists, we just can't signal it
        except OSError:
            return False
        return True

    def clear(self) -> None:
        for f in (self.pid_file, self.output_file, self.stop_flag):
            f.unlink(missing_ok=True)


def default_session_dir() -> Path:
    base = os.environ.get("DATA_PATH")
    if base:
        return Path(base) / "recordings" / ".session"
    return Path.home() / ".recorder-session"


def start(
    output: Path,
    duration: float | None,
    samplerate: int,
    channels: int,
    session_dir: Path,
    wait_seconds: float = 1.5,
) -> Session:
    """Spawn a detached recorder. Returns the Session once we've confirmed it's alive."""
    sess = Session(session_dir)
    if sess.is_running():
        raise RuntimeError(
            f"recorder already running (pid={sess.pid()}, output={sess.output()}). run `python -m recorder stop` first."
        )
    sess.dir.mkdir(parents=True, exist_ok=True)
    sess.clear()
    sess.output_file.write_text(str(output))

    cmd = [
        sys.executable,
        "-m",
        "recorder",
        "_serve",
        "--session",
        str(sess.dir),
        "-o",
        str(output),
        "--samplerate",
        str(samplerate),
        "--channels",
        str(channels),
    ]
    if duration is not None:
        cmd += ["--duration", str(duration)]

    log = sess.log_file.open("wb")
    if os.name == "nt":
        # Detach so closing the parent shell doesn't kill the recorder.
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    else:
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    sess.pid_file.write_text(str(proc.pid))

    # Give the child a moment to initialize so we can report startup failures.
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if not sess.is_running():
            tail = _read_log_tail(sess.log_file)
            raise RuntimeError(f"recorder exited immediately. log tail:\n{tail}")
        time.sleep(0.1)
    return sess


def stop(session_dir: Path, timeout: float = 10.0) -> Path | None:
    """Signal the running recorder to finalize the WAV. Returns the output path."""
    sess = Session(session_dir)
    out = sess.output()
    if not sess.is_running():
        sess.clear()
        return out

    sess.stop_flag.touch()
    deadline = time.time() + timeout
    while sess.is_running() and time.time() < deadline:
        time.sleep(0.2)

    if sess.is_running():
        # Recorder didn't honor the flag in time; hard-kill as a fallback.
        pid = sess.pid()
        if pid is not None:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            time.sleep(0.5)
    sess.clear()
    return out


def status(session_dir: Path) -> dict[str, object]:
    sess = Session(session_dir)
    return {
        "running": sess.is_running(),
        "pid": sess.pid(),
        "output": sess.output(),
        "session_dir": sess.dir,
    }


def _read_log_tail(path: Path, n_bytes: int = 4096) -> str:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return "(no log)"
    return data[-n_bytes:].decode("utf-8", errors="replace")
