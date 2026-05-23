"""Local audio-to-minutes pipeline.

- ``transcribe``: file-based Whisper CLI transcription (`python -m llm`).
- ``transcribe_stream``: realtime-style streaming transcription via
  faster-whisper, used by `audios.mic_gui` live mode (fast preview).
- ``transcribe_final``: one-shot high-accuracy full-file pass
  (kotoba-whisper) run when recording stops.
- ``refine``: Ollama-driven post-processing that reconciles a transcript
  against user-typed notes (proper nouns, jargon).
- ``summarize``: Ollama-driven Markdown minutes generation.
"""
