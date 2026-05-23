"""Tests for the transcribe_final formatting helpers."""

from __future__ import annotations

from llm.transcribe_final import format_timestamp, segments_to_text


def test_format_timestamp_minutes():
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(65) == "01:05"
    assert format_timestamp(599) == "09:59"


def test_format_timestamp_hours():
    assert format_timestamp(3661) == "1:01:01"


def test_format_timestamp_negative_clamped():
    assert format_timestamp(-5) == "00:00"


def test_segments_to_text_with_timestamps():
    segments = [(0.0, 2.0, "こんにちは"), (4.2, 9.9, "本日の議題です")]
    assert segments_to_text(segments, timestamps=True) == "[00:00] こんにちは\n[00:04] 本日の議題です"


def test_segments_to_text_plain():
    segments = [(0.0, 2.0, "hello"), (2.0, 5.0, "world")]
    assert segments_to_text(segments, timestamps=False) == "hello world"


def test_segments_to_text_empty():
    assert segments_to_text([]) == ""
    assert segments_to_text([], timestamps=False) == ""
