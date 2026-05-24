# Lethe

Desktop voice recorder, local transcription, and meeting-minutes tool.

Lethe records audio from a microphone or another input device, transcribes it
locally with Whisper, lets you correct the transcript with notes, and generates
Markdown minutes with an Ollama model. Audio, transcripts, and notes stay on
your machine.

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
- macOS and Windows support.

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

## Project Layout

```text
src/audios/lethe.py          Tkinter GUI
src/audios/settings.py       persisted preferences and temp-file cleanup
src/audios/preprocess.py     audio preprocessing
src/llm/transcribe_stream.py live transcription
src/llm/transcribe_final.py  high-quality transcription
src/llm/refine.py            transcript correction via Ollama
src/llm/summarize.py         minutes generation via Ollama
tests/                       headless unit tests
```

## Name

Lethe is named after the river of forgetfulness. The point of recording a
meeting is to stop carrying it in your head.
