"""Theme palettes for Lethe."""

from __future__ import annotations

from typing import TypedDict


class Palette(TypedDict):
    bg: str
    surface: str
    surface_2: str
    border: str
    border_soft: str
    text: str
    ink_soft: str
    muted: str
    accent: str
    accent_dark: str
    accent_soft: str
    accent_line: str
    hover: str
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
            "bg": "#f3f6fb",
            "surface": "#ffffff",
            "surface_2": "#f6f8fa",
            "border": "#dce4ef",
            "border_soft": "#edf1f6",
            "text": "#132238",
            "ink_soft": "#40516a",
            "muted": "#718096",
            "accent": "#3157d5",
            "accent_dark": "#2545b5",
            "accent_soft": "#e9eeff",
            "accent_line": "#b9c7f1",
            "hover": "#eef2f6",
            "danger": "#e0463e",
            "danger_dark": "#bf3a33",
            "ok": "#0f9f6e",
            "disabled_bg": "#e5eaf2",
            "disabled_fg": "#9aa6b8",
        },
        "dark": {
            "bg": "#080b10",
            "surface": "#0f141b",
            "surface_2": "#141a23",
            "border": "#1f2733",
            "border_soft": "#171e28",
            "text": "#e6ebf2",
            "ink_soft": "#b3bdcc",
            "muted": "#7c8798",
            "accent": "#6f96ff",
            "accent_dark": "#3157d5",
            "accent_soft": "#1c263b",
            "accent_line": "#3a4e82",
            "hover": "#172031",
            "danger": "#fb7185",
            "danger_dark": "#f43f5e",
            "ok": "#34d399",
            "disabled_bg": "#171e28",
            "disabled_fg": "#7c8798",
        },
    },
    "aurora": {
        "label": "Aurora",
        "light": {
            "bg": "#f0f7f4",
            "surface": "#ffffff",
            "surface_2": "#f5fbf8",
            "border": "#c7ded4",
            "border_soft": "#e3efe9",
            "text": "#14231d",
            "ink_soft": "#34483f",
            "muted": "#60756c",
            "accent": "#0f9f6e",
            "accent_dark": "#087f5b",
            "accent_soft": "#dff7ec",
            "accent_line": "#a7dcc4",
            "hover": "#ecf6f1",
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
            "border_soft": "#1a3029",
            "text": "#ecfff7",
            "ink_soft": "#c3dcd2",
            "muted": "#9ab8ac",
            "accent": "#0ea5e9",
            "accent_dark": "#0284c7",
            "accent_soft": "#0c3144",
            "accent_line": "#155a7c",
            "hover": "#183128",
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
            "border_soft": "#efe4d9",
            "text": "#2b211b",
            "ink_soft": "#4f4035",
            "muted": "#7c6a5b",
            "accent": "#d9480f",
            "accent_dark": "#b83b0b",
            "accent_soft": "#ffe8d6",
            "accent_line": "#f4bf9c",
            "hover": "#f8efe6",
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
            "border_soft": "#33241a",
            "text": "#fff4ec",
            "ink_soft": "#e4d2c4",
            "muted": "#c2aa99",
            "accent": "#c2410c",
            "accent_dark": "#9a3412",
            "accent_soft": "#4a2412",
            "accent_line": "#7a3a16",
            "hover": "#35261b",
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
