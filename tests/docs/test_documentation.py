"""Tests for the public documentation layout."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _links(markdown: str) -> list[str]:
    return [match.group(1) for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", markdown)]


def test_readmes_are_split_by_language():
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    japanese = (ROOT / "README.ja.md").read_text(encoding="utf-8")

    assert "Japanese documentation" in english
    assert "English documentation" in japanese
    assert "デスクトップアプリ" in japanese


def test_usage_docs_are_split_by_language():
    english = (ROOT / "docs" / "usage.md").read_text(encoding="utf-8")
    japanese = (ROOT / "docs" / "usage.ja.md").read_text(encoding="utf-8")

    assert "# Lethe Usage Guide" in english
    assert "# Lethe 使い方ガイド" in japanese
    assert "Japanese version" in english
    assert "English version" in japanese


def test_architecture_docs_are_split_by_language():
    english = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    japanese = (ROOT / "docs" / "architecture.ja.md").read_text(encoding="utf-8")

    assert "# Lethe Architecture" in english
    assert "# Lethe アーキテクチャ" in japanese
    assert "Japanese version" in english
    assert "English version" in japanese


def test_markdown_links_point_to_existing_local_files():
    for path in [
        ROOT / "README.md",
        ROOT / "README.ja.md",
        ROOT / "docs" / "setup.md",
        ROOT / "docs" / "setup.ja.md",
        ROOT / "docs" / "architecture.md",
        ROOT / "docs" / "architecture.ja.md",
        ROOT / "docs" / "usage.md",
        ROOT / "docs" / "usage.ja.md",
    ]:
        for href in _links(path.read_text(encoding="utf-8")):
            if "://" in href or href.startswith("#"):
                continue
            target = (path.parent / href.split("#", 1)[0]).resolve()
            assert target.exists(), f"{path.relative_to(ROOT)} links to missing {href}"
