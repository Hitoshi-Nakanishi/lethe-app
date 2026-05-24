# Lethe

Cross-platform desktop recorder, local transcription, and meeting-minutes
tool for macOS and Windows.

Lethe is built for meetings, calls, videos, and browser-based audio you do not
want to lose. It records from a microphone or another input device, transcribes
the audio locally with Whisper, lets you correct the transcript with notes, and
generates Markdown minutes with an Ollama model. Audio, transcripts, and notes
stay on your machine.

The goal is to make one tool that can capture both sides of modern desktop
work:

- On macOS and Windows, record ordinary microphone speech for in-person notes,
  narration, interviews, or your side of a call.
- Capture playback from Zoom, YouTube, embedded web players, and other desktop
  audio sources when they are routed through an available input or loopback
  device.
- Keep the workflow local so private meeting audio can become a searchable
  transcript and minutes without sending recordings to an external service.

Japanese documentation: [README.ja.md](README.ja.md)

## Quick Start

```sh
git clone <this repo> lethe-app
cd lethe-app
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
lethe
```

With uv:

```sh
uv sync --dev
uv run lethe
```

With Task:

```sh
task run
```

## Documentation

- [Setup guide](docs/setup.md)
- [Usage guide](docs/usage.md)
- [Japanese usage guide](docs/usage.ja.md)

## Features

- Local Whisper transcription with live preview and a high-quality final pass.
- Editable timestamped transcript with click-to-seek playback.
- Notes-assisted correction for proper nouns, jargon, and names.
- Ollama-backed Markdown minutes generation.
- Session bundles that save audio, transcript, notes, and metadata together.
- Disk-backed recording so long meetings do not grow memory usage.
- Cross-platform macOS and Windows support.

## Requirements

- Python 3.11+
- Tk-enabled Python
- Optional: [Ollama](https://ollama.com) for correction and minutes generation

## Tests

```sh
pytest -q
```

With uv:

```sh
uv run pytest -q
```

With Task:

```sh
task default
task format
task check
task typecheck
task test
```

## Project Layout

```text
src/recorder/lethe.py        Tkinter GUI
src/recorder/settings.py     persisted preferences and temp-file cleanup
src/recorder/preprocess.py   audio preprocessing
src/recorder/loopback.py     Windows WASAPI loopback recorder
src/llm/transcribe_stream.py live transcription
src/llm/transcribe_final.py  high-quality transcription
src/llm/refine.py            transcript correction via Ollama
src/llm/summarize.py         minutes generation via Ollama
tests/                       headless unit tests
```

## Name

Lethe is named after the river of forgetfulness. The point of recording a
meeting is to stop carrying it in your head.
