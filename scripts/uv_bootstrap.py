"""Run uv, installing it for the current Python when it is not available.

Task commands use this wrapper so `task setup` can work on a fresh checkout
where `uv` is not on PATH yet.
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def _run(cmd: list[str]) -> int:
    return subprocess.run(cmd, check=False).returncode


def _uv_cmd() -> list[str] | None:
    uv = shutil.which("uv")
    if uv:
        return [uv]
    probe = subprocess.run(
        [sys.executable, "-m", "uv", "--version"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if probe.returncode == 0:
        return [sys.executable, "-m", "uv"]
    return None


def _install_uv() -> None:
    target = [] if sys.prefix != sys.base_prefix else ["--user"]
    cmd = [sys.executable, "-m", "pip", "install", *target, "uv"]
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    cmd = _uv_cmd()
    if cmd is None:
        _install_uv()
        cmd = _uv_cmd()
    if cmd is None:
        print("uv was installed but still cannot be executed with this Python.", file=sys.stderr)
        return 1
    return _run([*cmd, *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
