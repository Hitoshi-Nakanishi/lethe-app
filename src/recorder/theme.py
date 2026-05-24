"""Theme palettes for Lethe."""

from __future__ import annotations

from typing import TypedDict


class Palette(TypedDict):
    bg: str
    surface: str
    surface_2: str
    border: str
    text: str
    muted: str
    accent: str
    accent_dark: str
    accent_soft: str
    danger: str
    danger_dark: str
    ok: str
    disabled_bg: str
    disabled_fg: str


class Theme(TypedDict):
    label: str
    light: Palette
    dark: Palette


THEMES: dict[str, Theme] = {
    "midnight": {
        "label": "Midnight",
        "light": {
            "bg": "#eef2f7",
            "surface": "#ffffff",
            "surface_2": "#f6f8fb",
            "border": "#cfd7e5",
            "text": "#172033",
            "muted": "#647084",
            "accent": "#2563eb",
            "accent_dark": "#1d4ed8",
            "accent_soft": "#dbeafe",
            "danger": "#e0463e",
            "danger_dark": "#bf3a33",
            "ok": "#0f9f6e",
            "disabled_bg": "#e5eaf2",
            "disabled_fg": "#9aa6b8",
        },
        "dark": {
            "bg": "#070b12",
            "surface": "#101724",
            "surface_2": "#151f31",
            "border": "#243349",
            "text": "#edf4ff",
            "muted": "#91a0b8",
            "accent": "#5eead4",
            "accent_dark": "#14b8a6",
            "accent_soft": "#123b43",
            "danger": "#fb7185",
            "danger_dark": "#f43f5e",
            "ok": "#34d399",
            "disabled_bg": "#1b2535",
            "disabled_fg": "#66758c",
        },
    },
    "aurora": {
        "label": "Aurora",
        "light": {
            "bg": "#f0f7f4",
            "surface": "#ffffff",
            "surface_2": "#f5fbf8",
            "border": "#c7ded4",
            "text": "#14231d",
            "muted": "#60756c",
            "accent": "#0f9f6e",
            "accent_dark": "#087f5b",
            "accent_soft": "#dff7ec",
            "danger": "#e05252",
            "danger_dark": "#bf3f3f",
            "ok": "#16835e",
            "disabled_bg": "#e4eee9",
            "disabled_fg": "#91a19a",
        },
        "dark": {
            "bg": "#07110e",
            "surface": "#10201a",
            "surface_2": "#152a22",
            "border": "#244137",
            "text": "#ecfff7",
            "muted": "#9ab8ac",
            "accent": "#7dd3fc",
            "accent_dark": "#38bdf8",
            "accent_soft": "#123447",
            "danger": "#fb7185",
            "danger_dark": "#f43f5e",
            "ok": "#86efac",
            "disabled_bg": "#1d3028",
            "disabled_fg": "#6f887c",
        },
    },
    "ember": {
        "label": "Ember",
        "light": {
            "bg": "#f7f3ef",
            "surface": "#fffdfa",
            "surface_2": "#fbf4ec",
            "border": "#e0cfc0",
            "text": "#2b211b",
            "muted": "#7c6a5b",
            "accent": "#d9480f",
            "accent_dark": "#b83b0b",
            "accent_soft": "#ffe8d6",
            "danger": "#c92a2a",
            "danger_dark": "#a61e1e",
            "ok": "#2b8a3e",
            "disabled_bg": "#eee5dd",
            "disabled_fg": "#a19388",
        },
        "dark": {
            "bg": "#120c09",
            "surface": "#201610",
            "surface_2": "#2b1d14",
            "border": "#473325",
            "text": "#fff4ec",
            "muted": "#c2aa99",
            "accent": "#f97316",
            "accent_dark": "#ea580c",
            "accent_soft": "#4a2412",
            "danger": "#fb7185",
            "danger_dark": "#f43f5e",
            "ok": "#86efac",
            "disabled_bg": "#31231a",
            "disabled_fg": "#877367",
        },
    },
}


THEME_LABELS = {value["label"]: key for key, value in THEMES.items()}


def palette_for(theme: str, dark_mode: bool) -> Palette:
    """Return the palette for a theme key, falling back to Midnight."""
    theme_key = theme if theme in THEMES else "midnight"
    mode = "dark" if dark_mode else "light"
    return THEMES[theme_key][mode]
