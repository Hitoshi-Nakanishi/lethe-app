import argparse
import os
import sys
import time
from pathlib import Path

from audios import session as sessionmod
from audios.recorder import LoopbackUnavailableError, list_devices, record


def _default_output() -> Path:
    """Default to $DATA_PATH/audios/<timestamp>.wav, else cwd, per AGENTS.md output policy."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = os.environ.get("DATA_PATH")
    if base:
        return Path(base) / "audios" / f"{stamp}.wav"
    return Path.cwd() / f"{stamp}.wav"


def _add_capture_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output WAV path. Defaults to $DATA_PATH/audios/<timestamp>.wav, or ./<timestamp>.wav.",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=float,
        default=None,
        help="Max seconds to record. Omit for unlimited (stop via Ctrl+C or `audios stop`).",
    )
    parser.add_argument("--samplerate", type=int, default=48000, help="Sample rate Hz. Default: 48000.")
    parser.add_argument("--channels", type=int, default=2, help="Channel count. Default: 2 (stereo).")


def _add_session_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--session",
        type=Path,
        default=None,
        help="Session control dir. Defaults to $DATA_PATH/audios/.session/, or ~/.audios-session/.",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m audios",
        description=(
            "Capture system audio (Zoom calls, browser <video>, anything playing through the "
            "default speaker) via WASAPI loopback on Windows and save it as a WAV file."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="Record in the foreground (stop with Ctrl+C).")
    _add_capture_args(rec)

    sub.add_parser("devices", help="List speakers and loopback microphones.")

    start = sub.add_parser("start", help="Spawn a detached recorder; return immediately.")
    _add_capture_args(start)
    _add_session_arg(start)

    stop = sub.add_parser("stop", help="Signal the detached recorder to finalize and exit.")
    _add_session_arg(stop)

    status = sub.add_parser("status", help="Show whether a detached recorder is running.")
    _add_session_arg(status)

    serve = sub.add_parser("_serve", help="(internal) recorder body spawned by `start`.")
    _add_capture_args(serve)
    _add_session_arg(serve)

    return p


def _resolve_session(args: argparse.Namespace) -> Path:
    return args.session or sessionmod.default_session_dir()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "devices":
            print(list_devices())
            return 0

        if args.cmd == "record":
            out = args.output or _default_output()
            record(out, seconds=args.duration, samplerate=args.samplerate, channels=args.channels)
            print(f"wrote {out}", file=sys.stderr)
            return 0

        if args.cmd == "start":
            out = args.output or _default_output()
            sess = sessionmod.start(
                output=out,
                duration=args.duration,
                samplerate=args.samplerate,
                channels=args.channels,
                session_dir=_resolve_session(args),
            )
            print(f"recording (pid={sess.pid()}) -> {out}", file=sys.stderr)
            print(f"stop with: python -m audios stop", file=sys.stderr)
            return 0

        if args.cmd == "stop":
            out = sessionmod.stop(_resolve_session(args))
            if out is None:
                print("no active recorder session.", file=sys.stderr)
                return 1
            print(f"wrote {out}", file=sys.stderr)
            return 0

        if args.cmd == "status":
            st = sessionmod.status(_resolve_session(args))
            print(f"running: {st['running']}")
            print(f"pid:     {st['pid']}")
            print(f"output:  {st['output']}")
            print(f"session: {st['session_dir']}")
            return 0 if st["running"] else 1

        if args.cmd == "_serve":
            sess = sessionmod.Session(_resolve_session(args))
            out = args.output or _default_output()
            record(
                out,
                seconds=args.duration,
                samplerate=args.samplerate,
                channels=args.channels,
                stop_flag=sess.stop_flag,
            )
            print(f"wrote {out}", file=sys.stderr)
            return 0

    except LoopbackUnavailableError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 0
