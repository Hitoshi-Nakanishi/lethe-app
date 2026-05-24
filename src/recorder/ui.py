"""Reusable Tk UI widgets for Lethe."""

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable
from typing import TypedDict

FontSpec = tuple[str, int] | tuple[str, int, str]


class UiColors(TypedDict):
    surface: str
    surface_2: str
    border: str
    text: str
    muted: str
    accent: str
    accent_dark: str
    disabled_bg: str
    disabled_fg: str


ColorProvider = Callable[[], UiColors]


class Tooltip:
    """A small hover-help popup for a Tk/ttk widget."""

    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 450) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after = self.widget.after(self.delay_ms, self._show)

    def _cancel(self) -> None:
        if self._after is not None:
            self.widget.after_cancel(self._after)
            self._after = None

    def _show(self) -> None:
        if self._tip is not None:
            return
        x = self.widget.winfo_rootx() + 14
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self._tip,
            text=self.text,
            justify="left",
            background="#2b2f38",
            foreground="#f4f5f7",
            relief="flat",
            font=("", 10),
            padx=10,
            pady=7,
            wraplength=340,
        ).pack()

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class Switch(tk.Frame):
    """Compact iOS-style switch with a ttk.Checkbutton-compatible state surface."""

    def __init__(
        self,
        master: tk.Widget,
        *,
        text: str,
        variable: tk.BooleanVar,
        colors: ColorProvider,
        command: Callable[[], None] | None = None,
        font: FontSpec | None = None,
        default_font_size: int = 11,
    ) -> None:
        self._colors = colors
        palette = self._colors()
        super().__init__(master, background=palette["surface"], bd=0, highlightthickness=0, takefocus=1)
        self._text = text
        self._variable = variable
        self._command = command
        self._font: FontSpec = font or ("", default_font_size)
        self._disabled = False
        self._width = 48
        self._height = 28

        self._label = tk.Label(self, text=text, font=self._font, anchor="w", bd=0)
        self._label.pack(side="left", padx=(0, 8) if text else (0, 0))
        self._canvas = tk.Canvas(self, width=self._width, height=self._height, bd=0, highlightthickness=0)
        self._canvas.pack(side="left")

        tk.Frame.bind(self, "<Button-1>", self._on_click, add="+")
        self._label.bind("<Button-1>", self._on_click, add="+")
        self._canvas.bind("<Button-1>", self._on_click, add="+")
        tk.Frame.bind(self, "<space>", self._on_key, add="+")
        tk.Frame.bind(self, "<Return>", self._on_key, add="+")
        self._variable.trace_add("write", lambda *_: self._draw())
        self.restyle()

    def bind(self, sequence=None, func=None, add=None):  # type: ignore[override]
        result = super().bind(sequence, func, add)
        if sequence is not None and func is not None and hasattr(self, "_label"):
            self._label.bind(sequence, func, add)
            self._canvas.bind(sequence, func, add)
        return result

    def set_text(self, text: str) -> None:
        self._text = text
        self._label.configure(text=self._text)
        self._label.pack_configure(padx=(0, 8) if text else (0, 0))

    def set_font(self, font: FontSpec) -> None:
        self._font = font
        self._label.configure(font=self._font)

    def state(self, states: list[str] | tuple[str, ...] | None = None):
        if states is None:
            return ("disabled",) if self._disabled else ()
        if "disabled" in states:
            self._disabled = True
        if "!disabled" in states:
            self._disabled = False
        self.restyle()
        return ("disabled",) if self._disabled else ()

    def restyle(self) -> None:
        palette = self._colors()
        cursor = "arrow" if self._disabled else "hand2"
        tk.Frame.configure(self, background=palette["surface"], cursor=cursor)
        self._label.configure(
            background=palette["surface"],
            foreground=palette["disabled_fg"] if self._disabled else palette["text"],
            cursor=cursor,
            font=self._font,
        )
        self._canvas.configure(background=palette["surface"], cursor=cursor)
        self._draw()

    def _on_click(self, _event=None) -> str:
        self.focus_set()
        if self._disabled:
            return "break"
        self._variable.set(not bool(self._variable.get()))
        if self._command is not None:
            self._command()
        return "break"

    def _on_key(self, _event=None) -> str:
        return self._on_click()

    def _draw(self) -> None:
        palette = self._colors()
        selected = bool(self._variable.get())
        track = palette["accent"] if selected and not self._disabled else palette["surface_2"]
        if self._disabled:
            track = palette["disabled_bg"]
        outline = palette["accent_dark"] if selected and not self._disabled else palette["border"]
        knob = palette["disabled_fg"] if self._disabled else "#ffffff"

        self._canvas.delete("all")
        pad = 2
        radius = (self._height - pad * 2) // 2
        left = pad
        top = pad
        right = self._width - pad
        bottom = self._height - pad
        self._canvas.create_oval(left, top, left + radius * 2, bottom, fill=track, outline=outline, width=1)
        self._canvas.create_oval(right - radius * 2, top, right, bottom, fill=track, outline=outline, width=1)
        self._canvas.create_rectangle(left + radius, top, right - radius, bottom, fill=track, outline=track)
        knob_radius = radius - 2
        knob_center = right - radius if selected else left + radius
        self._canvas.create_oval(
            knob_center - knob_radius,
            top + 2,
            knob_center + knob_radius,
            bottom - 2,
            fill=knob,
            outline=knob,
        )


class WaveMeter(tk.Canvas):
    """Animated wave display for recording and analysis states."""

    def __init__(self, master: tk.Widget, *, colors: ColorProvider, height: int = 42) -> None:
        super().__init__(master, height=height, highlightthickness=1, bd=0, relief="flat")
        self._colors = colors
        self.mode = "idle"
        self.level = 0.0
        self.progress = 0.0
        self.phase = 0.0
        self.restyle()
        self.bind("<Configure>", lambda _event: self.draw())

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.draw()

    def set_level(self, level: float) -> None:
        self.level = max(0.0, min(level, 1.0))

    def set_progress(self, progress: float) -> None:
        self.progress = max(0.0, min(progress, 1.0))

    def restyle(self) -> None:
        palette = self._colors()
        self.configure(highlightbackground=palette["border"], background=palette["surface_2"])
        self.draw()

    def tick(self) -> None:
        if self.mode in {"recording", "analysis"}:
            self.phase += 0.24 if self.mode == "recording" else 0.16
        self.draw()

    def draw(self) -> None:
        palette = self._colors()
        self.delete("all")
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self.create_rectangle(0, 0, width, height, fill=palette["surface_2"], outline=palette["border"])
        if self.mode == "idle":
            self.create_line(12, height / 2, width - 12, height / 2, fill=palette["border"], width=2)
            return

        level = self.level if self.mode == "recording" else 0.72
        bars = _wave_bar_heights(level, self.phase)
        gap = 3
        usable = max(1, width - 24)
        bar_w = max(2, (usable - gap * (len(bars) - 1)) / len(bars))
        x = 12
        for index, value in enumerate(bars):
            if self.mode == "analysis" and index / max(1, len(bars) - 1) > max(self.progress, 0.08):
                color = palette["border"]
            else:
                color = palette["accent"] if index % 3 else palette["accent_dark"]
            bar_h = max(4, value * (height - 12))
            y0 = (height - bar_h) / 2
            self.create_rectangle(x, y0, x + bar_w, y0 + bar_h, fill=color, outline=color)
            x += bar_w + gap


def _wave_bar_heights(level: float, phase: float, count: int = 32) -> list[float]:
    """Return normalized animated bar heights for the wave meter."""
    level = max(0.0, min(level, 1.0))
    heights = []
    for i in range(count):
        carrier = 0.5 + 0.5 * math.sin(phase + i * 0.58)
        ripple = 0.5 + 0.5 * math.sin(phase * 0.37 + i * 1.17)
        heights.append(max(0.06, min(1.0, 0.08 + level * (0.36 + 0.46 * carrier + 0.18 * ripple))))
    return heights
