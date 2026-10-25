# Lethe

[![Tests](https://github.com/Hitoshi-Nakanishi/lethe-app/actions/workflows/tests.yml/badge.svg)](https://github.com/Hitoshi-Nakanishi/lethe-app/actions/workflows/tests.yml)
[![Version](https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2FHitoshi-Nakanishi%2Flethe-app%2Fmain%2Fpyproject.toml&query=%24.project.version&label=version)](pyproject.toml)
![Python](https://img.shields.io/badge/python-3.14.4-blue)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Lethe is a desktop app for turning meetings, calls, interviews, and recorded
desktop audio into transcripts and Markdown minutes. It records from a
microphone or another available input device, transcribes locally with Whisper,
uses your notes to correct names and domain terms, and can generate minutes
with Ollama. Audio, transcripts, and notes stay on your machine.

Japanese documentation: [README.ja.md](README.ja.md)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/lethe-en-dark.png">
  <img alt="Lethe with a transcript and notes open" src="docs/assets/lethe-en-light.png">
</picture>

The left sidebar chooses the input and output devices, capture options, and
models. Recording and the three processing steps sit above the transcript:
**① Transcribe** runs the high-quality Whisper pass, **② Correct with notes**
fixes names and terms using the notes pane, and **③ Create minutes** writes
Markdown minutes. Click a timestamp to play the audio from that point. The
status bar shows progress and the recording time.

## Motivation

Meetings and calls often happen across a messy mix of rooms, headsets, video
calls, browser players, and local apps. Lethe is built to keep that capture and
review workflow local: record the parts you need, turn them into a searchable
timestamped transcript, fix the words that matter, and produce minutes without
sending private audio to an external service.

## Quick Start

Install [Task](https://taskfile.dev/) and Python 3.14.4, then run:

```sh
task setup
task run
```

`task setup` bootstraps [uv](https://docs.astral.sh/uv/) when needed and
syncs the Python environment with `uv sync --dev`.
`task run` starts the Lethe desktop app.

Drag the dividers to resize the panes. Use the header's − / + controls or
Ctrl/Cmd + − / + to change the text size; click the percentage or press
Ctrl/Cmd + 0 to reset it. ◐ switches between light and dark; the theme
(Midnight, Aurora, Ember) and the language (English, Japanese) are under ⚙.

Docker is also supported for development and CI-like checks:

```sh
docker compose up -d --build app
docker compose exec app task default
```

The Docker image uses Python 3.14.4, installs the native Tk, PortAudio, and
ffmpeg libraries Lethe needs, and stores local container data under
`.docker-data/`. Desktop GUI and audio capture from Docker still require host
display/audio forwarding; see the [setup guide](docs/setup.md) for details.

Before downloading models:

- Run `task setup` so the Python/uv environment exists.
- For LLM model downloads, install Ollama and start it with `ollama serve`.

List the configured models:

```sh
task model-list
```

Download both model groups:

```sh
task download-models
```

`task download-models` downloads both:

- Whisper speech model for transcription: `efwkjn/faster-whisper-ja-760M`
- Ollama LLM models for correction/minutes: `qwen3.5:9b`, `gemma4:12b`

To download only one group:

```sh
task download-whisper-models
task download-llm-models
```

## Features

- Record microphone speech plus Windows PC output audio by default.
- Optionally disable microphone or PC audio capture per session.
- Run local Whisper transcription with live preview and a high-quality final
  pass; the sidebar shows whether each Whisper model is installed.
- Edit timestamped transcripts and click timestamps to play from that point.
- Use notes as authoritative spellings for names, proper nouns, and jargon.
- Generate Markdown minutes through a local Ollama model.
- Save sessions containing audio, transcript, notes, and metadata.
- Export analysis-ready dataset folders with MP3 audio, transcript Markdown,
  notes Markdown, and a manifest path mapping.

## Documentation

- [Setup guide](docs/setup.md)
- [Usage guide](docs/usage.md)
- [Japanese usage guide](docs/usage.ja.md)
- [Architecture and source layout](docs/architecture.md)

## For Developers

Use `task default` before sending changes. It runs formatting, linting, type
checks, and tests.

```sh
task default
```

The [Tests workflow](.github/workflows/tests.yml) runs the same checks and
builds the package on Windows and macOS for every push and pull request.

## Name

Lethe is named after the river of forgetfulness in Greek mythology. The point
of recording a meeting is to stop carrying it in your head.
