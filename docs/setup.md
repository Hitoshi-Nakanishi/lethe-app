# Lethe Setup Guide

Japanese version: [setup.ja.md](setup.ja.md)

## Requirements

- Python 3.14.4 (the standard project environment in `.python-version`)
- Tk-enabled Python
- Several GB of free disk space for Whisper model downloads
- Optional: Ollama for transcript correction and minutes generation

## Install

Using Task:

```sh
git clone <this repo> lethe-app
cd lethe-app
task setup
task run
```

`task setup` bootstraps uv when it is not available on PATH.

List configured models and pre-download the configured set: Whisper `medium`,
`large-v3`; Ollama `llama3.1:8b`, `qwen2.5:7b`, `mistral:7b`.

```sh
task model-list
task download-models
```

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

Install Ollama, start the service, and pull a model that is not already covered
by `task download-models`:

```sh
ollama serve
task download-llm-model -- llama3.1:8b
```

Lethe can record and transcribe without Ollama. Correction and minutes
generation require it.

## Configuration

Edit `default.toml` to choose where Lethe stores settings, temporary WAV files,
the shared dataset/output folder used by save/open dialogs, the default MP3
filename pattern, and the LLM model choices shown in the app. Set
`LETHE_CONFIG` to point to another TOML file when you want a machine-local
config outside the repo.

Initial UI defaults are also configurable. They apply before a value is saved
in `settings.json`; after that, the user's saved choice wins. For example:

```toml
[defaults]
mic_capture = true
noise_reduce = false
live = false
llm_model = "qwen2.5:7b"
theme = "midnight"
dark_mode = true
language = "en"
```

MP3 save dialogs use the `[filenames]` section to suggest a selectable filename.
The user can still edit the filename in the dialog.

```toml
[filenames]
mp3_template = "{timestamp}_{meeting_name}.mp3"
meeting_name = "team_sync"
timestamp_format = "%Y%m%d_%H%M"
```

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
