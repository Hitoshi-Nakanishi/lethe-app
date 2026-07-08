"""Tests for the transcribe_stream pure helpers."""

from __future__ import annotations

import numpy as np

from llm.transcribe_stream import (
    CONTEXT_BUDGET,
    PROMPT_BUDGET,
    VAD_PARAMS,
    format_initial_prompt,
    resample_to_16k,
    strip_fillers,
)


def test_vad_params_relaxed():
    # Confirm the VAD config keeps more audio than faster-whisper's defaults.
    assert VAD_PARAMS["threshold"] < 0.5
    assert VAD_PARAMS["speech_pad_ms"] >= 400
    assert VAD_PARAMS["min_silence_duration_ms"] >= 500


def test_format_initial_prompt_empty():
    assert format_initial_prompt("") is None
    assert format_initial_prompt(None or "") is None
    assert format_initial_prompt("   \n") is None


def test_format_initial_prompt_wraps_directive():
    out = format_initial_prompt("クォンツ\nファクター投資\n中西")
    assert out is not None
    assert "正しい表記" in out
    assert "クォンツ" in out
    assert "ファクター投資" in out


def test_format_initial_prompt_caps_at_800_chars():
    notes = "あ" * 2000
    out = format_initial_prompt(notes)
    assert out is not None
    assert len(out) == 800


def test_format_initial_prompt_appends_context_tail():
    out = format_initial_prompt("防衛", "防衛費の増額について議論した")
    assert out is not None
    directive, context = out.split("\n")
    assert "防衛" in directive
    assert context == "防衛費の増額について議論した"


def test_format_initial_prompt_context_only():
    out = format_initial_prompt("", "前のチャンクの発話")
    assert out == "前のチャンクの発話"
    assert format_initial_prompt("", "") is None


def test_format_initial_prompt_notes_and_context_respect_budget():
    out = format_initial_prompt("あ" * 2000, "い" * 2000)
    assert out is not None
    assert len(out) <= PROMPT_BUDGET
    directive, context = out.split("\n")
    assert len(context) == CONTEXT_BUDGET
    assert context == "い" * CONTEXT_BUDGET


def test_strip_fillers_drops_elongated_fillers():
    assert strip_fillers("えーと、防衛費はですね") == "防衛費はですね"
    assert strip_fillers("あのー、そのー、うーん、はい") == "はい"


def test_strip_fillers_keeps_demonstrative_ano():
    assert strip_fillers("あの会社の防衛関連事業") == "あの会社の防衛関連事業"


def test_resample_to_16k_identity_when_already_target_rate():
    audio = np.linspace(-0.5, 0.5, 16000, dtype=np.float32)
    out = resample_to_16k(audio, 16000)
    assert np.array_equal(out, audio)


def test_resample_to_16k_changes_length_proportionally():
    audio = np.zeros(48000, dtype=np.float32)
    out = resample_to_16k(audio, 48000)
    assert out.dtype == np.float32
    # 48 kHz -> 16 kHz is a 1/3 downsample, length should be ~16000.
    assert 15800 <= out.size <= 16200
