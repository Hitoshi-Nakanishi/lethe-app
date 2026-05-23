# Lethe

**録音・文字起こし・議事録** — A desktop voice recorder, transcriber, and
meeting-minutes app.

Lethe records audio from any input device (microphone or a BlackHole
aggregate carrying Zoom / YouTube playback), transcribes it locally with
Whisper, lets you correct it against typed notes, and turns the transcript
into Markdown meeting minutes via a local Ollama model. **All processing
is local.** No audio, transcript, or note leaves the machine.

```
録音  →  ① 高精度で文字起こし  →  メモに用語を記入  →  ② メモで校正  →  ③ 議事録を作成
```

## Quick start

```sh
git clone <this repo> lethe-app
cd lethe-app
python -m venv .venv && source .venv/bin/activate
pip install -e .
lethe
```

That puts you at a window with a record button. Press it (or `Space`),
talk, press it again. The transcript appears below. macOS pyenv users
will need a one-time Tcl/Tk rebuild — see the setup guide.

## Documentation

- **[docs/setup.md](docs/setup.md)** — install, Tcl/Tk rebuild for pyenv,
  Ollama, BlackHole capture, first-run model download, verification.
- **[docs/usage.md](docs/usage.md)** — the workflow in detail, every
  control, keyboard shortcuts, file formats, accuracy tips, known
  limitations.

## Features

- **Two-tier transcription**: a 5s-chunked live preview (Whisper medium)
  while recording, then an accurate single-pass over the whole audio
  with [Whisper large-v3](https://huggingface.co/openai/whisper-large-v3)
  when you stop. Models default to accuracy; swap to smaller ones in
  `src/audios/lethe.py` if you need speed.
- **Click-to-seek playback**: every transcript line is prefixed with a
  clickable `[MM:SS]`; click it to jump there in the built-in player and
  verify the wording.
- **Editable transcript**: fix what the model missed in place.
- **Notes-driven accuracy**: type proper nouns and jargon in the notes
  pane. Notes feed Whisper's `initial_prompt` live, then drive an Ollama
  refinement pass that rewrites the transcript to match.
- **One-click minutes**: Ollama produces Markdown minutes (要約・論点・
  アクションアイテム) from the corrected transcript.
- **Session bundles**: audio + transcript + notes save into a single
  `.zip` and reopen as one.
- **Disk-backed recording**: writes straight to a temp WAV, so a 2-hour
  meeting stays RAM-flat.
- **Cross-platform**: macOS and Windows. Tested on Python 3.14.

## Requirements

- Python 3.11+
- A Tk-enabled Python (pyenv builds need a small rebuild step — see
  [docs/setup.md](docs/setup.md))
- Optional: [Ollama](https://ollama.com) with `llama3.1:8b` for the
  refinement and minutes steps. Lethe is fully usable without Ollama;
  just don't press ② or ③.

## Tests

```sh
pytest -q
```

23 unit tests covering the audio preprocessing, the timestamp helpers,
the settings round-trip, and the player. None of them touch an audio
device, display, or network.

## Project layout

```
src/audios/lethe.py          # GUI (Tkinter)
src/audios/preprocess.py     # bandpass + spectral noise reduction
src/audios/settings.py       # persisted preferences + temp-file sweep
src/audios/recorder.py       # (legacy) Windows WASAPI loopback CLI
src/llm/transcribe_stream.py # 5s live preview
src/llm/transcribe_final.py  # single-pass HQ transcription
src/llm/refine.py            # Ollama-driven term correction
src/llm/summarize.py         # Ollama-driven minutes generation
src/llm/whisper_models.py    # process-wide WhisperModel cache
tests/                       # 23 unit tests
```

## Why "Lethe"?

The river of forgetfulness in Greek mythology. The point of recording
something is to free yourself from having to remember it.

## Origin

Lethe grew inside the [qrxarts](../qrxarts) repository through ~10
feature passes and was extracted as a standalone project at qrxarts
commit `3a287e1f`. Its full development history remains in that repo;
this one starts fresh.
