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

## Docker Development Environment

The repository includes a Docker setup for repeatable development checks and
containerized app runs:

```sh
docker compose up -d --build app
docker compose exec app task default
```

The image is based on Python 3.14.4 and pre-syncs the locked `uv` development
environment. It also installs the native libraries used by Lethe at runtime:
Tk for the desktop UI, PortAudio/ALSA/PulseAudio libraries for `sounddevice`,
and ffmpeg for audio conversion paths.

The app service uses [../docker/default.toml](../docker/default.toml). Container
settings, temp files, and exported datasets are written under `.docker-data/`,
which is ignored by git. Whisper and `uv` caches are persisted in Docker named
volumes so model downloads and dependency caches survive container restarts.

Open a shell in the app container:

```sh
docker compose exec app bash
```

Run the desktop app from the container:

```sh
docker compose exec app task run
```

GUI and audio forwarding depend on the host OS. On Linux, pass through your
X11/Wayland and PulseAudio settings in `.env` and add any host-specific device
mounts you need, such as `/dev/snd`. On Docker Desktop for macOS or Windows,
containerized tests and model-management commands are the reliable path; local
host Python is usually simpler for interactive microphone capture and Tk windows.

To use containerized Ollama, start the optional profile and pull a model:

```sh
docker compose --profile ollama up -d ollama
docker compose --profile ollama exec ollama ollama pull llama3.1:8b
```

The Docker config points Lethe to `http://ollama:11434`. If you prefer an
Ollama service running on the host, copy [.env.example](../.env.example) to
`.env` and set `LETHE_DOCKER_CONFIG` to a local TOML file whose
`[models].ollama_url` uses `http://host.docker.internal:11434`.

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
