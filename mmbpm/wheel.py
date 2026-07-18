"""Camelot wheel drawing, shared by the main window and the Compatibility Map."""
from __future__ import annotations

import math
import tkinter as tk

BG = "#0e1015"; PANEL = "#171a22"; PANEL2 = "#1e222c"
ACCENT = "#00e0a4"; ACCENT2 = "#ff5c8a"; BLUE = "#4f7cff"
MUTED = "#868ea3"; LINE = "#272c38"


def _parse(code: str):
    return int(code[:-1]), code[-1]


def neighbors(code: str) -> set:
    """The keys that mix harmonically with `code` (self, ±1, relative)."""
    n, l = _parse(code)
    return {code,
            f"{n}{'A' if l == 'B' else 'B'}",
            f"{(n % 12) + 1}{l}",
            f"{((n - 2) % 12) + 1}{l}"}


def draw(canvas: tk.Canvas, present: set, highlight: str | None = None,
         title: str = "CAMELOT") -> None:
    c = canvas
    c.delete("all")
    W = c.winfo_width();  W = int(c["width"]) if W <= 1 else W
    H = c.winfo_height(); H = int(c["height"]) if H <= 1 else H
    cx, cy = W / 2, H / 2 + 8
    r_out = min(W, H) / 2 - 10
    r_mid = r_out * 0.68
    r_in = r_out * 0.38

    hi_keys = neighbors(highlight) if highlight else set()
    if title:
        c.create_text(cx, 10, text=title, fill=MUTED,
                      font=("Segoe UI Semibold", 9))
    for k in range(12):
        number = k + 1
        start = 90 - k * 30 + 15
        for letter, r2 in (("B", r_out), ("A", r_mid)):
            code = f"{number}{letter}"
            base = PANEL2
            if code in present:
                base = BLUE if letter == "B" else "#3a5bd0"
            if code in hi_keys:
                base = ACCENT if code == highlight else ACCENT2
            c.create_arc(cx - r2, cy - r2, cx + r2, cy + r2,
                         start=start, extent=-30, style=tk.PIESLICE,
                         fill=base, outline=BG, width=2)
        ang = math.radians(90 - k * 30)
        lr = (r_mid + r_out) / 2
        c.create_text(cx + lr * math.cos(ang), cy - lr * math.sin(ang),
                      text=f"{number}B", fill="#ffffff",
                      font=("Segoe UI Semibold", 7))
        lr2 = (r_in + r_mid) / 2
        c.create_text(cx + lr2 * math.cos(ang), cy - lr2 * math.sin(ang),
                      text=f"{number}A", fill="#cfd4e0", font=("Segoe UI", 7))
    c.create_oval(cx - r_in, cy - r_in, cx + r_in, cy + r_in,
                  fill=PANEL, outline=LINE)
