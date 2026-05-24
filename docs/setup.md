# Lethe Setup Guide

Japanese version: [setup.ja.md](setup.ja.md)

## Requirements

- Python 3.11 or newer
- Tk-enabled Python
- Several GB of free disk space for Whisper model downloads
- Optional: Ollama for transcript correction and minutes generation

## Install

Using uv:

```sh
git clone <this repo> lethe-app
cd lethe-app
uv sync --dev
uv run lethe
```

Using venv and pip:

```sh
git clone <this repo> lethe-app
cd lethe-app
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
```

Run the app:

```sh
lethe
```

## Optional Ollama Setup

Install Ollama, start the service, and pull a model:

```sh
ollama serve
ollama pull llama3.1:8b
```

Lethe can record and transcribe without Ollama. Correction and minutes
generation require it.

## Configuration

Edit `default.toml` to choose where Lethe stores settings, temporary WAV files,
the initial folders used by save/open dialogs, and the LLM model choices shown
in the app. Set `LETHE_CONFIG` to point to another TOML file when you want a
machine-local config outside the repo.

## macOS Tk Note

If a pyenv Python was built without Tcl/Tk, Tkinter will fail to import. Install
Tcl/Tk through Homebrew and rebuild Python with Tk support, or use an official
Python installer that includes Tk.

Verify Tk:

```sh
python -c "import tkinter, _tkinter; print(_tkinter.TK_VERSION)"
```

## Verify

```sh
pytest -q
lethe
```

With uv:

```sh
uv run pytest -q
uv run lethe
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `_tkinter` import error | Use a Python build with Tcl/Tk enabled |
| Ollama connection error | Start `ollama serve` and pull the configured model |
| Recording does not start | Check microphone permissions and whether another app is using the device |
| Transcription is empty | Confirm the input level moves and try disabling noise reduction |
