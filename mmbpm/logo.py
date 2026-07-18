"""The MMBpm mark (concept A: harmonic wheel + equalizer), drawn natively on a
tkinter canvas so the header logo is crisp at any size with no image file."""
from __future__ import annotations

import os
import sys
import tkinter as tk

MINT = "#00e0a4"
TEAL = "#4f7cff"
TILE_BG = "#0e1015"

# equalizer bars as (x-offset, height) fractions of the ring radius R
_BARS = [(-0.44, 0.71, MINT), (-0.15, 1.23, MINT),
         (0.15, 0.51, TEAL), (0.44, 0.93, MINT)]


def draw(canvas: tk.Canvas, cx: float, cy: float, R: float,
         bg: str = TILE_BG) -> None:
    """Draw the mark centred at (cx, cy) with ring radius R."""
    ring_w = max(3, R * 0.26)
    canvas.create_oval(cx - R, cy - R, cx + R, cy + R, outline=MINT,
                       width=ring_w)
    # top "key" node on the ring
    nr = max(2.5, R * 0.14)
    canvas.create_oval(cx - nr, cy - R - nr, cx + nr, cy - R + nr,
                       fill=bg, outline=MINT, width=max(2, R * 0.09))
    bw = max(3, R * 0.18)
    for dx, hf, col in _BARS:
        x = cx + dx * R
        h = hf * R
        canvas.create_line(x, cy - h / 2, x, cy + h / 2, fill=col,
                           width=bw, capstyle=tk.ROUND)


def icon_paths():
    """Absolute paths to the packaged icon files (may not exist)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = os.path.join(sys._MEIPASS, "mmbpm", "assets")
    else:
        base = os.path.join(os.path.dirname(__file__), "assets")
    return os.path.join(base, "icon.ico"), os.path.join(base, "icon.png")


def apply_window_icon(win: tk.Misc) -> tk.PhotoImage | None:
    """Set the window/taskbar icon. Returns the PhotoImage (keep a reference)."""
    ico, png = icon_paths()
    img = None
    try:
        if os.name == "nt" and os.path.exists(ico):
            win.iconbitmap(ico)
    except Exception:
        pass
    try:
        if os.path.exists(png):
            img = tk.PhotoImage(file=png)
            win.iconphoto(True, img)
    except Exception:
        img = None
    return img
