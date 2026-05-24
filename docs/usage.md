# Lethe Usage Guide

Japanese version: [usage.ja.md](usage.ja.md)

## Basic Workflow

```text
Record -> Transcribe -> Add notes -> Correct with notes -> Generate minutes
```

## Record Audio

1. Choose an input device from the input selector.
2. Enable noise reduction when the room has steady fan or air-conditioner noise.
3. Click **Record** or press `Space`.
4. Watch the wave meter react while speaking.
5. Click **Stop** to finish recording.

If live transcription is enabled, Lethe shows a rough preview while recording.
After recording stops, run the high-quality transcription pass for the final
timestamped transcript.

## Transcribe

Click the high-quality transcription button after recording or after opening an
existing audio file. Lethe uses Whisper, keeps timestamps, and displays one
segment per line. Click a timestamp such as `[02:15]` to play the audio from
that point. During transcription and other analysis steps, the same meter shows
an animated analysis wave and progress fill.

## Add Notes

Use the notes pane for proper nouns, names, product names, and jargon. One term
per line is easiest to review. Notes are used as Whisper context during live
transcription and as authoritative spellings during the correction step.

## Correct With Notes

Click the correction button after transcription and notes are ready. Ollama
rewrites likely misrecognitions so they match your notes while preserving the
meaning, order, and timestamps.

Choose the LLM model from the **LLM** selector before running correction or
minutes generation. Edit `default.toml` to add or remove model choices.

## Generate Minutes

Click the minutes button to create Markdown minutes from the transcript. The
result opens in a separate editable window and can be saved as `.md`.

## Sessions

Use the File menu to save or open a session bundle. A session `.zip` contains:

```text
audio.wav
transcript.txt
notes.txt
meta.json
```

## Save Locations

Default save/open folders are configured in `default.toml` under `[paths]`.
Leave a value empty to use the operating system default.

## Themes

Use the header theme selector to switch between Midnight, Aurora, and Ember.
The **Dark** toggle switches each theme between light and dark palettes.

## Shortcuts

| Key | Action |
|---|---|
| `Space` | Start or stop recording when focus is not inside a text field |
| `Cmd/Ctrl+S` | Save transcript |
| `Cmd/Ctrl+O` | Open audio file |
| `Cmd/Ctrl+Z` | Undo text edits |

## Tips

- Record close to the speaker when possible.
- Add names and domain-specific words to notes before or during recording.
- Use timestamp click-to-seek for manual transcript review.
- Use a smaller Whisper model when speed matters more than accuracy.
