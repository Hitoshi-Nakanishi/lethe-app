# Lethe Architecture

Japanese version: [architecture.ja.md](architecture.ja.md)

## Source Layout

```text
src/recorder/lethe.py        Tkinter GUI
src/recorder/settings.py     persisted preferences and temp-file cleanup
src/recorder/preprocess.py   audio preprocessing
src/recorder/loopback.py     Windows WASAPI loopback recorder
src/llm/transcribe_stream.py live transcription
src/llm/transcribe_final.py  high-quality transcription
src/llm/refine.py            transcript correction via Ollama
src/llm/summarize.py         minutes generation via Ollama
tests/                       headless unit tests
```

## Runtime Shape

Lethe keeps the desktop workflow in `recorder.lethe`. The GUI owns recording
state, session save/load, playback, and worker thread coordination. Audio is
written to temporary WAV files while recording so long sessions do not grow
memory usage.

Whisper integrations live under `src/llm`. Live transcription consumes short
audio chunks for preview text, while the final transcription path reads the
full audio source and returns timestamped segments. Ollama-backed correction
and minutes generation operate on transcript and notes text.
