# Lethe Usage Guide

Japanese version: [usage.ja.md](usage.ja.md)

## Basic Workflow

```text
Record -> Transcribe -> Add notes -> Correct with notes -> Generate minutes
```

## Record Audio

1. Choose an input device from the input selector.
2. Turn off **Capture microphone** when you do not want to record mic audio. In that mode, Lethe does not create an audio file, live transcript, or transcription.
3. Enable noise reduction when the room has steady fan or air-conditioner noise.
4. Click **Record** or press `Space`.
5. Watch the wave meter react while speaking.
6. Click **Stop** to finish recording.

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

## Datasets

Use **File -> Export dataset...** to write analysis-ready files into one
folder. Lethe creates a 1:1 role-to-path mapping with fixed filenames:

```text
<dataset>/audio.mp3
<dataset>/transcript.md
<dataset>/memo.md
<dataset>/manifest.json
```

`manifest.json` records the dataset id, duration, and relative paths for the
audio, transcript, and memo so downstream analyzers can pick up the dataset
without guessing filenames.

## Save Locations

The shared save/open folder is configured by `datasets_dir` in `default.toml`
under `[paths]`. Leave it empty to use the operating system default.

The default MP3 filename shown in the save dialog is configured in
`default.toml` under `[filenames]`. The built-in pattern is
`YYYYMMDD_HHMM_<meeting_name>.mp3`, and the suggested name remains editable in
the save dialog.
The default dataset folder name uses the same timestamp and meeting-name
placeholders via `dataset_template`.

## Themes

Use the header theme selector to switch between Midnight, Aurora, and Ember.
The **Dark** toggle switches each theme between light and dark palettes.

## Language

Use the header language selector to switch the app UI between Japanese and
English. The selected language is saved and restored on the next launch.

## Shortcuts

| Key | Action |
|---|---|
| `Space` | Start or stop recording when focus is not inside a text field |
| `Cmd/Ctrl+S` | Save transcript |
| `Cmd/Ctrl+O` | Open audio file |
| `Cmd/Ctrl++` | Increase app font size |
| `Cmd/Ctrl+-` | Decrease app font size |
| `Cmd/Ctrl+Z` | Undo text edits |

## Tips

- Record close to the speaker when possible.
- Add names and domain-specific words to notes before or during recording.
- Use timestamp click-to-seek for manual transcript review.
- Use a smaller Whisper model when speed matters more than accuracy.
