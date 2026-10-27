# Lethe Setup Guide

Japanese version: [setup.ja.md](setup.ja.md)

## Requirements

Use Python 3.14.4 (the version in `.python-version`) with Tk support, [Task](https://taskfile.dev/) and several GB of free disk
space for speech models. Ollama is optional for correction and minutes. Model downloads need an internet connection; processing
uses local models afterward.

## Install

From the checkout:

```sh
task setup
task download-whisper-models
task run
```

`task setup` prepares uv when needed and syncs the Python environment. For other installation methods, see below.

## Models

The configured defaults are:

| Purpose | Model |
| --- | --- |
| Speech transcription | `efwkjn/faster-whisper-ja-760M` (Japanese only) |
| Correction and minutes | `qwen3.5:9b`, `gemma4:12b` through Ollama |

After `task setup`, use these commands:

| Command | Action |
| --- | --- |
| `task model-list` | Show configured models |
| `task download-whisper-models` | Download speech models |
| `task download-llm-models` | Download LLMs; Ollama must be installed and running |
| `task download-models` | Download both groups; Ollama must be running |
| `task download-llm-model -- <model>` | Download a specific Ollama model |

Start Ollama with its app or `ollama serve`. Recording and transcription do not require it.

For another language, choose a multilingual Whisper model in `default.toml` or your private `LETHE_CONFIG`. For example:

```toml
[models]
whisper_live_model = "large-v3-turbo"
whisper_final_model = "large-v3-turbo"
whisper_language = "en"
```

Download the configured models again, then select the model in the app. The interface language is a separate setting.

## Configuration

`default.toml` controls storage, models and initial UI settings. Set `LETHE_CONFIG` to use a private TOML file outside the
checkout. Saved user choices in `settings.json` take precedence over `[defaults]`.

| Section | Settings |
| --- | --- |
| `[paths]` | Settings directory, temporary WAV files, and `datasets_dir` for save/open dialogs |
| `[models]` | Speech models and language, `ollama_url`, and LLM choices |
| `[defaults]` | Capture options, live preview, theme, dark mode, language and zoom |
| `[filenames]` | MP3 and dataset name templates using `{timestamp}` and `{meeting_name}` |

Leave optional paths empty for OS defaults. Suggested filenames remain editable in the save dialog. See
[default.toml](../default.toml) for the complete layout and [usage](usage.md#save-locations) for saved files.

## Other installation methods

With uv already installed:

```sh
uv sync --dev
uv run lethe
```

Or activate a virtual environment and install with pip:

```sh
python -m pip install -e .
lethe
```

Both methods use the same model configuration. Model task commands also work after setup.

## Docker Development Environment

For containerized development checks:

```sh
docker compose up -d --build app
docker compose exec app task default
```

The image includes Python 3.14.4, Tk, PortAudio and ffmpeg. It uses [docker/default.toml](../docker/default.toml), writes
runtime data to ignored `.docker-data/`, and keeps Whisper/uv caches in named volumes. Use `docker compose exec app bash` for a
shell.

Interactive GUI and recording require host display/audio forwarding. On Linux, configure X11/Wayland and PulseAudio in `.env`
and mount audio devices as needed. On macOS and Windows, host Python is usually simpler for interactive use.

For containerized Ollama:

```sh
docker compose --profile ollama up -d ollama
docker compose --profile ollama exec ollama ollama pull qwen3.5:9b
```

The Docker config uses `http://ollama:11434`. To use host Ollama, copy [.env.example](../.env.example) to `.env` and set
`LETHE_DOCKER_CONFIG` to a private TOML with `ollama_url = "http://host.docker.internal:11434"` under `[models]`. Use
`docker compose exec app task run` only when display and audio forwarding are configured.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `_tkinter` import error | Use a Python build with Tcl/Tk support |
| Ollama connection error | Start Ollama and download the selected model |
| Recording does not start | Check microphone permissions and device use by other apps |
| Empty transcription | Confirm the input meter moves; try disabling noise reduction |

On macOS, pyenv Python needs Tcl/Tk support at build time. Install Tcl/Tk and rebuild Python, or use a Python installer that
includes Tk. Verify with:

```sh
python -c "import tkinter, _tkinter; print(_tkinter.TK_VERSION)"
```

For development checks, see [Contributing](../CONTRIBUTING.md).
