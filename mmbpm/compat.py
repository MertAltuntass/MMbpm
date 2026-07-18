"""Uyum Haritası — a beginner-friendly helper that shows, for any song, which
other songs mix well with it and *why* (in plain Turkish)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import automix, logo, wheel

BG = "#0e1015"; PANEL = "#171a22"; PANEL2 = "#1e222c"
ACCENT = "#00e0a4"; ACCENT2 = "#ff5c8a"; BLUE = "#4f7cff"
TEXT = "#e7e9f0"; MUTED = "#868ea3"; LINE = "#272c38"
AMBER = "#f2c14e"

_LEVEL = {
    "perfect": ("✓ Mükemmel", ACCENT),
    "good":    ("○ İyi", BLUE),
    "weak":    ("△ Dikkatli", AMBER),
    "none":    ("✕ Uyumsuz", MUTED),
}
_RANK = {"perfect": 0, "good": 1, "weak": 2, "none": 3}


class _RowTip:
    """Hover tooltip that shows a Treeview row's full text (e.g. long filenames)."""
    def __init__(self, tree, col_index):
        self.tree = tree
        self.col = col_index
        self.tip = None
        self.row = None
        tree.bind("<Motion>", self._motion, add="+")
        tree.bind("<Leave>", lambda e: self._hide(), add="+")

    def _motion(self, e):
        row = self.tree.identify_row(e.y)
        if row == self.row:
            return
        self._hide()
        self.row = row
        if not row:
            return
        vals = self.tree.item(row, "values")
        if self.col >= len(vals):
            return
        text = str(vals[self.col])
        self.tip = tw = tk.Toplevel(self.tree)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{self.tree.winfo_rootx() + e.x + 14}"
                       f"+{self.tree.winfo_rooty() + e.y + 16}")
        tw.configure(bg=LINE)
        tk.Label(tw, text=text, bg=PANEL2, fg=TEXT, font=("Segoe UI", 9),
                 padx=9, pady=5).pack(padx=1, pady=1)

    def _hide(self):
        self.row = None
        if self.tip:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


class CompatibilityMap(tk.Toplevel):
    def __init__(self, master, app, tracks):
        super().__init__(master)
        self.app = app
        self.tracks = [t for t in tracks if t.analyzed]
        self.focus_tr = None

        self.title("MMBpm · Uyum Haritası")
        self.configure(bg=BG)
        self.geometry("1360x730")
        self.minsize(1120, 620)
        self._icon = logo.apply_window_icon(self)
        self.energy = automix.energy_scale(self.tracks)

        self._build()
        if self.tracks:
            self.left.selection_set("0")
            self._on_pick()

    # ------------------------------------------------------------------ build
    def _build(self):
        head = tk.Frame(self, bg=BG); head.pack(fill=tk.X, padx=16, pady=(14, 4))
        tk.Label(head, text="🧩 Uyum Haritası", bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 15)).pack(side=tk.LEFT)
        tk.Label(head, text="  Soldan bir şarkı seç → onunla uyumlu şarkıları gör",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(side=tk.LEFT, pady=(5, 0))

        body = tk.Frame(self, bg=BG); body.pack(fill=tk.BOTH, expand=True,
                                                padx=16, pady=6)

        # --- left: all tracks (wide name column) ---
        left = tk.Frame(body, bg=PANEL, width=500)
        left.pack(side=tk.LEFT, fill=tk.Y); left.pack_propagate(False)
        tk.Label(left, text="ŞARKILARIN", bg=PANEL, fg=MUTED,
                 font=("Segoe UI Semibold", 9)).pack(anchor=tk.W, padx=12, pady=(10, 4))
        self.left = ttk.Treeview(left, columns=("k", "b", "f"), show="headings",
                                 selectmode="browse")
        for c, t, w in (("k", "KEY", 50), ("b", "BPM", 54), ("f", "DOSYA", 380)):
            self.left.heading(c, text=t)
            self.left.column(c, width=w, anchor=tk.W if c == "f" else tk.CENTER,
                             stretch=(c == "f"))
        _RowTip(self.left, 2)          # hover shows full filename
        self.left.pack(fill=tk.BOTH, expand=True, padx=(8, 8), pady=(0, 10))
        for i, t in enumerate(self.tracks):
            self.left.insert("", tk.END, iid=str(i),
                             values=(t.camelot, f"{t.bpm:.0f}", t.filename))
        self.left.bind("<<TreeviewSelect>>", lambda e: self._on_pick())

        # --- right: focus + matches ---
        right = tk.Frame(body, bg=BG); right.pack(side=tk.LEFT, fill=tk.BOTH,
                                                  expand=True, padx=(14, 0))
        top = tk.Frame(right, bg=BG); top.pack(fill=tk.X)
        self.wheel = tk.Canvas(top, width=210, height=196, bg=PANEL,
                               highlightthickness=0)
        self.wheel.pack(side=tk.LEFT)
        info = tk.Frame(top, bg=BG); info.pack(side=tk.LEFT, fill=tk.BOTH,
                                               expand=True, padx=(14, 0))
        self.focus_lbl = tk.Label(info, text="", bg=BG, fg=TEXT, justify=tk.LEFT,
                                  anchor=tk.NW, font=("Segoe UI Semibold", 13))
        self.focus_lbl.pack(anchor=tk.NW, pady=(6, 2))
        self.focus_sub = tk.Label(info, text="", bg=BG, fg=MUTED, justify=tk.LEFT,
                                  anchor=tk.NW, wraplength=380, font=("Segoe UI", 10))
        self.focus_sub.pack(anchor=tk.NW)
        # legend
        leg = tk.Frame(info, bg=BG); leg.pack(anchor=tk.NW, pady=(10, 0))
        for lvl in ("perfect", "good", "weak"):
            txt, col = _LEVEL[lvl]
            tk.Label(leg, text="● ", bg=BG, fg=col, font=("Segoe UI", 10)).pack(side=tk.LEFT)
            tk.Label(leg, text=txt.split(" ", 1)[1] + "   ", bg=BG, fg=MUTED,
                     font=("Segoe UI", 9)).pack(side=tk.LEFT)

        self.count_lbl = tk.Label(right, text="", bg=BG, fg=TEXT, anchor=tk.W,
                                  font=("Segoe UI Semibold", 10))
        self.count_lbl.pack(fill=tk.X, pady=(12, 4))

        self.matches = ttk.Treeview(right,
                                    columns=("s", "k", "b", "d", "e", "r", "f"),
                                    show="headings", selectmode="browse")
        cols = (("s", "DURUM", 90), ("k", "KEY", 44), ("b", "BPM", 50),
                ("d", "ΔBPM", 48), ("e", "ENERJİ", 128), ("r", "TON İLİŞKİSİ", 200),
                ("f", "DOSYA", 300))
        for c, t, w in cols:
            self.matches.heading(c, text=t)
            self.matches.column(c, width=w, anchor=tk.W if c in ("r", "f") else tk.CENTER,
                                stretch=(c == "f"))
        for lvl, (_txt, col) in _LEVEL.items():
            self.matches.tag_configure(lvl, foreground=col)
        self.matches.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
        self.matches.bind("<Double-1>", self._focus_from_match)
        _RowTip(self.matches, 6)       # hover shows full filename

        tk.Label(self, text="💡 İpucu: bir eşleşmeye çift tıklarsan onu odak yaparsın; "
                            "böyle zincir kurabilirsin.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor=tk.W,
                                                             padx=16, pady=(0, 12))

    # ------------------------------------------------------------------ logic
    def _on_pick(self):
        sel = self.left.selection()
        if not sel:
            return
        self.focus_tr = self.tracks[int(sel[0])]
        self._refresh()

    def _focus_from_match(self, _evt=None):
        sel = self.matches.selection()
        if not sel:
            return
        i = sel[0]                       # iid == index in self.tracks
        self.left.selection_set(i)
        self.left.see(i)
        self._on_pick()

    def _refresh(self):
        f = self.focus_tr
        wheel.draw(self.wheel, {t.camelot for t in self.tracks}, f.camelot)
        er = self.energy.get(id(f))
        self.focus_lbl.config(text=f"🎵 {f.filename}")
        self.focus_sub.config(
            text=f"{f.camelot} · {f.key_name} · {f.bpm:.0f} BPM"
                 + (f" · enerji {er}/10" if er else "") + "\n"
                 "TON İLİŞKİSİ = harmonik uyum (yeşil en güvenli).  "
                 "ENERJİ = geçişte enerji ▲ yükselir / ▼ düşer.")

        rows = []
        for t in self.tracks:
            if t is f:
                continue
            level, reason, bpm_note = automix.relationship(f, t)
            rows.append((level, reason, bpm_note, t))
        rows.sort(key=lambda r: (_RANK[r[0]], abs((r[3].bpm or 0) - (f.bpm or 0))))

        self.matches.delete(*self.matches.get_children())
        fr = self.energy.get(id(f))
        good = 0
        for i, (level, reason, bpm_note, t) in enumerate(rows):
            if level in ("perfect", "good"):
                good += 1
            badge = _LEVEL[level][0]
            tr_ = self.energy.get(id(t))
            if fr is not None and tr_ is not None:
                if tr_ > fr:
                    energy_txt = f"{fr}→{tr_}  ▲ yükselir"
                elif tr_ < fr:
                    energy_txt = f"{fr}→{tr_}  ▼ düşer"
                else:
                    energy_txt = f"{fr}→{tr_}  ≈ benzer"
            else:
                energy_txt = "—"
            self.matches.insert("", tk.END, iid=str(self.tracks.index(t)),
                                values=(badge, t.camelot, f"{t.bpm:.0f}",
                                        f"{abs(t.bpm - f.bpm):.0f}",
                                        energy_txt, reason, t.filename),
                                tags=(level,))
        self.count_lbl.config(
            text=f"“{f.filename}” ile geçiş yapılabilecek {good} güçlü eşleşme")
