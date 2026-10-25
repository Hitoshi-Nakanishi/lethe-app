"""Reusable Tk UI widgets for Lethe."""

from __future__ import annotations

import ctypes
import math
import sys
import tkinter as tk
from collections.abc import Callable
from typing import TypedDict

FontSpec = tuple[str, int] | tuple[str, int, str]


class UiColors(TypedDict):
    surface: str
    surface_2: str
    border: str
    hover: str
    text: str
    muted: str
    accent: str
    accent_dark: str
    disabled_bg: str
    disabled_fg: str


ColorProvider = Callable[[], UiColors]

# DwmSetWindowAttribute ids; Windows 10 ignores the corner and colour ids and keeps its own frame.
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def mix(color: str, other: str, amount: float) -> str:
    """Blend two ``#rrggbb`` colours: 0 keeps ``color``, 1 gives ``other``."""
    a, b = _rgb(color), _rgb(other)
    return "#{:02x}{:02x}{:02x}".format(*(round(x + (y - x) * amount) for x, y in zip(a, b, strict=True)))


def _coverage(x: int, y: int, width: int, height: int, radius: float) -> float:
    """Share of pixel (x, y) inside a rounded rectangle anchored at the origin."""
    inside = 0 <= x and x + 1 <= width and 0 <= y and y + 1 <= height
    if (radius <= x and x + 1 <= width - radius) or (radius <= y and y + 1 <= height - radius):
        return 1.0 if inside else 0.0
    hits = 0
    for i in range(4):
        px = x + (i + 0.5) / 4
        for j in range(4):
            py = y + (j + 0.5) / 4
            if not (0 <= px <= width and 0 <= py <= height):
                continue
            cx = min(max(px, radius), width - radius)
            cy = min(max(py, radius), height - radius)
            if (px - cx) ** 2 + (py - cy) ** 2 <= radius * radius:
                hits += 1
    return hits / 16


def paint_rounded(image: tk.PhotoImage, *, fill: str, outline: str, background: str, radius: float) -> None:
    """Fill ``image`` with an anti-aliased rounded rectangle and 1px outline over a known background.

    Tk 8.6 photos have no partial alpha, so edges are blended into ``background``.
    """
    width, height = image.width(), image.height()
    f, o, b = _rgb(fill), _rgb(outline), _rgb(background)
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            outer = _coverage(x, y, width, height, radius)
            inner = _coverage(x - 1, y - 1, width - 2, height - 2, max(0.0, radius - 1))
            channels = (b[k] * (1 - outer) + o[k] * (outer - inner) + f[k] * inner for k in range(3))
            row.append("#{:02x}{:02x}{:02x}".format(*(round(c) for c in channels)))
        rows.append("{" + " ".join(row) + "}")
    image.put(" ".join(rows))


def _colorref(color: str) -> int:
    r, g, b = _rgb(color)
    return r | g << 8 | b << 16


def _set_window_attributes(window: tk.Tk | tk.Toplevel, attributes: tuple[tuple[int, int], ...]) -> None:
    """Apply DWM attributes to a window's frame on Windows; other platforms keep their native frame."""
    if not sys.platform.startswith("win"):
        return
    try:
        window.update_idletasks()
        hwnd = int(window.wm_frame(), 16)
        for attribute, value in attributes:
            data = ctypes.c_int(value)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data))
    except (AttributeError, OSError, ValueError, tk.TclError):
        pass


def style_title_bar(window: tk.Tk | tk.Toplevel, *, caption: str, text: str, border: str, dark: bool) -> None:
    """Colour the Windows title bar and frame to match the app."""
    _set_window_attributes(
        window,
        (
            (_DWMWA_USE_IMMERSIVE_DARK_MODE, int(dark)),
            (_DWMWA_CAPTION_COLOR, _colorref(caption)),
            (_DWMWA_TEXT_COLOR, _colorref(text)),
            (_DWMWA_BORDER_COLOR, _colorref(border)),
        ),
    )


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
            font="TkTooltipFont",
            padx=10,
            pady=7,
            wraplength=340,
        ).pack()

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class PopupMenu:
    """A themed drop-down list of commands; Tk's own menus keep a native light frame on Windows."""

    def __init__(self, master: tk.Misc, *, colors: ColorProvider, font: Callable[[], FontSpec]) -> None:
        self._master = master
        self._colors = colors
        self._font = font
        self._items: list[tuple[str, str, Callable[[], object]] | None] = []
        self._rows: list[tuple[list[tk.Label], Callable[[], object]]] = []
        self._active = -1
        self._window: tk.Toplevel | None = None

    def add_command(self, label: str, command: Callable[[], object], accelerator: str = "") -> None:
        self._items.append((label, accelerator, command))

    def add_separator(self) -> None:
        self._items.append(None)

    def post(self, x: int, y: int) -> None:
        self.unpost()
        palette = self._colors()
        window = tk.Toplevel(self._master, background=palette["border"])
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        body = tk.Frame(window, background=palette["surface"], padx=4, pady=4)
        body.pack(padx=1, pady=1)
        self._rows = []
        for row, item in enumerate(self._items):
            if item is None:
                rule = tk.Frame(body, height=1, background=palette["border"])
                rule.grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
                continue
            label, accelerator, command = item
            index = len(self._rows)
            cells = []
            for column, (text, color, anchor) in enumerate(
                ((label, palette["text"], "w"), (accelerator, palette["muted"], "e"))
            ):
                cell = tk.Label(
                    body,
                    text=text,
                    anchor=anchor,
                    padx=12,
                    pady=5,
                    font=self._font(),
                    background=palette["surface"],
                    foreground=color,
                )
                cell.grid(row=row, column=column, sticky="ew")
                cell.bind("<Enter>", lambda _event, i=index: self._highlight(i))
                cell.bind("<ButtonRelease-1>", lambda _event, i=index: self._invoke(i))
                cells.append(cell)
            self._rows.append((cells, command))
        window.geometry(f"+{x}+{y}")
        window.bind("<Escape>", lambda _event: self.unpost())
        window.bind("<Up>", lambda _event: self._highlight((self._active - 1) % len(self._rows)))
        window.bind("<Down>", lambda _event: self._highlight((self._active + 1) % len(self._rows)))
        window.bind("<Return>", lambda _event: self._invoke(self._active))
        window.bind("<ButtonPress>", self._on_press)
        window.bind("<FocusOut>", lambda _event: self._master.after(100, self._close_if_app_inactive))
        self._window = window
        self._active = -1
        _set_window_attributes(
            window, ((_DWMWA_WINDOW_CORNER_PREFERENCE, _DWMWCP_ROUND), (_DWMWA_BORDER_COLOR, _colorref(palette["border"])))
        )
        window.focus_force()
        window.grab_set()

    def unpost(self) -> None:
        window, self._window = self._window, None
        if window is not None:
            window.grab_release()
            window.destroy()

    def _close_if_app_inactive(self) -> None:
        # Focus also leaves for a moment while Windows activates the popup; only another application taking it closes.
        if self._window is not None and self._window.focus_get() is None:
            self.unpost()

    def _on_press(self, event: tk.Event) -> None:
        window = self._window
        if window is None:
            return
        x = event.x_root - window.winfo_rootx()
        y = event.y_root - window.winfo_rooty()
        if not (0 <= x < window.winfo_width() and 0 <= y < window.winfo_height()):
            self.unpost()

    def _highlight(self, index: int) -> None:
        palette = self._colors()
        for row, (cells, _command) in enumerate(self._rows):
            for cell in cells:
                cell.configure(background=palette["hover"] if row == index else palette["surface"])
        self._active = index

    def _invoke(self, index: int) -> None:
        if not 0 <= index < len(self._rows):
            return
        command = self._rows[index][1]
        self.unpost()
        command()


class Switch(tk.Frame):
    """Compact pill switch with a ttk.Checkbutton-compatible state surface."""

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
        self._width = 38
        self._height = 22
        self._track = tk.PhotoImage(master=self, width=self._width, height=self._height)
        self._knob = tk.PhotoImage(master=self, width=self._height - 6, height=self._height - 6)

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
        track = palette["accent_dark"] if selected else mix(palette["border"], palette["muted"], 0.45)
        if self._disabled:
            track = palette["disabled_bg"]
        knob = palette["disabled_fg"] if self._disabled else "#ffffff"
        radius = self._height / 2
        paint_rounded(self._track, fill=track, outline=track, background=palette["surface"], radius=radius)
        paint_rounded(self._knob, fill=knob, outline=knob, background=track, radius=self._knob.width() / 2)

        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=self._track)
        knob_x = self._width - self._height + 3 if selected else 3
        self._canvas.create_image(knob_x, 3, anchor="nw", image=self._knob)


class WaveMeter(tk.Canvas):
    """Animated wave display for recording and analysis states."""

    def __init__(self, master: tk.Widget, *, colors: ColorProvider, height: int = 42) -> None:
        super().__init__(master, height=height, highlightthickness=0, bd=0, relief="flat")
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
        self.configure(background=palette["surface"])
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
