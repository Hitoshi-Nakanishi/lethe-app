# Lethe

Cross-platform desktop recorder, local Whisper transcription, and
Ollama-backed meeting minutes for macOS and Windows. Audio, transcripts, and
notes stay on your machine.

Japanese documentation: [README.ja.md](README.ja.md)

## Quick Start

Install [Task](https://taskfile.dev/) and [uv](https://docs.astral.sh/uv/),
then run:

```sh
task setup
task run
```

`task setup` syncs the Python environment with `uv sync --dev`.
`task run` starts the Lethe desktop app.

## Common Tasks

```sh
task test      # run pytest
task check     # run Ruff lint checks
task format    # format Python files
task default   # format, lint, typecheck, test
task list      # show available tasks
```

## Features

- Local Whisper transcription with live preview and a high-quality final pass.
- Editable timestamped transcript with click-to-seek playback.
- Notes-assisted correction for proper nouns, jargon, and names.
- Ollama-backed Markdown minutes generation.
- Session bundles for audio, transcript, notes, and metadata.

## Documentation

- [Setup guide](docs/setup.md)
- [Usage guide](docs/usage.md)
- [Japanese usage guide](docs/usage.ja.md)

