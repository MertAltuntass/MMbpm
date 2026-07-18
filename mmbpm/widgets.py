"""Small reusable UI helpers: tooltips and the 3-step guide bar."""
from __future__ import annotations

import tkinter as tk

BG = "#0e1015"; PANEL = "#171a22"; PANEL2 = "#1e222c"
ACCENT = "#00e0a4"; TEXT = "#e7e9f0"; MUTED = "#868ea3"; LINE = "#272c38"
DONE = "#2b6b57"


class ToolTip:
    """Lightweight hover tooltip for any widget."""
    def __init__(self, widget, text: str, delay: int = 450):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except Exception:
                pass
            self._after = None

    def _show(self):
        if self._tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 16
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        except Exception:
            return
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.configure(bg=LINE)
        tk.Label(tw, text=self.text, bg=PANEL2, fg=TEXT, justify=tk.LEFT,
                 font=("Segoe UI", 9), padx=10, pady=6, wraplength=280).pack(padx=1, pady=1)

    def _hide(self, _e=None):
        self._cancel()
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


class StepBar(tk.Canvas):
    """Horizontal 1-2-3 progress guide. Steps light up as the user advances."""
    def __init__(self, parent, steps, **kw):
        super().__init__(parent, height=72, bg=BG, highlightthickness=0, **kw)
        self.steps = steps
        self.active = 0
        self.done = set()
        self.bind("<Configure>", lambda e: self._draw())

    def set_active(self, i):
        self.active = i
        self._draw()

    def mark_done(self, i):
        self.done.add(i)
        self._draw()

    def _draw(self):
        self.delete("all")
        W = self.winfo_width() or 900
        n = len(self.steps)
        seg = W / n
        r = 15
        cy = 24
        for i, (num, label) in enumerate(self.steps):
            cx = seg * i + seg / 2
            # connector to next
            if i < n - 1:
                x2 = seg * (i + 1) + seg / 2
                col = ACCENT if i in self.done else LINE
                self.create_line(cx + r + 6, cy, x2 - r - 6, cy, fill=col, width=2)
            done = i in self.done
            active = i == self.active
            if done:
                fill, fg, edge = DONE, "#eafff7", ACCENT
                txt = "✓"
            elif active:
                fill, fg, edge = ACCENT, "#04120d", ACCENT
                txt = str(num)
            else:
                fill, fg, edge = PANEL2, MUTED, LINE
                txt = str(num)
            self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill,
                             outline=edge, width=2)
            self.create_text(cx, cy, text=txt, fill=fg,
                             font=("Segoe UI Semibold", 11))
            self.create_text(cx, cy + r + 12,
                             text=label, fill=TEXT if (active or done) else MUTED,
                             font=("Segoe UI Semibold", 9) if active else ("Segoe UI", 9))
