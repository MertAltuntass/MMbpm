"""The 'your mix is ready' screen — the simple end of the one-click flow.

No editing, no jargon: listen, save, done."""
from __future__ import annotations

import os
import shutil
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import logo

try:
    import pygame
    _PG = True
except Exception:
    _PG = False

BG = "#0e1015"; PANEL = "#171a22"; PANEL2 = "#1e222c"
ACCENT = "#00e0a4"; TEXT = "#e7e9f0"; MUTED = "#868ea3"; LINE = "#272c38"


class MixResult(tk.Toplevel):
    def __init__(self, master, app, plan, summary, temp_path, mode="harmonic",
                 xfade=10.0):
        super().__init__(master)
        self.app = app
        self.mode = mode
        self.plan = plan
        self.summary = summary
        self.temp_path = temp_path
        self.xfade = float(xfade)

        self.title("MMBpm · Miksin Hazır")
        self.configure(bg=BG)
        self.geometry("560x600")
        self.resizable(False, False)
        self.transient(master)
        self._icon = logo.apply_window_icon(self)

        # transport state
        self.duration = float(summary.get("duration_sec", 0) or 0)
        self._pos = 0.0
        self._playing = False
        self._paused = False
        self._t0 = None
        self._seeking = False
        self._tick_id = None
        self.protocol("WM_DELETE_WINDOW", self._close)

        dur = int(self.duration)
        mmss = f"{dur // 60}:{dur % 60:02d}"

        tk.Label(self, text="🎉", bg=BG, font=("Segoe UI", 34)).pack(pady=(22, 0))
        tk.Label(self, text="Miksin hazır!", bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 18)).pack()
        tk.Label(self, text=f"{summary.get('tracks', 0)} şarkı  ·  {mmss}  ·  "
                            f"{summary.get('target_bpm', 0):.0f} BPM",
                 bg=BG, fg=ACCENT, font=("Segoe UI", 11)).pack(pady=(2, 12))

        # track order chain (with BPM + key)
        chain = tk.Frame(self, bg=PANEL); chain.pack(fill=tk.X, padx=24)
        order = "   →   ".join(c.camelot for c in plan.clips)
        sira_lbl = ("SIRA · enerji yükselen" if mode == "energy"
                    else "SIRA · akıcı ton geçişi")
        tk.Label(chain, text=sira_lbl, bg=PANEL, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(anchor=tk.W, padx=12, pady=(8, 0))
        tk.Label(chain, text=order, bg=PANEL, fg=ACCENT,
                 font=("Segoe UI Semibold", 12)).pack(anchor=tk.W, padx=12, pady=(0, 6))
        shown = plan.clips[:12]
        names = "\n".join(f"{i+1}.  {c.camelot} · {c.bpm:.0f} BPM · {c.filename}"
                          for i, c in enumerate(shown))
        if len(plan.clips) > 12:
            names += f"\n… ve {len(plan.clips) - 12} parça daha"
        tk.Label(chain, text=names, bg=PANEL, fg=TEXT, justify=tk.LEFT,
                 font=("Segoe UI", 9)).pack(anchor=tk.W, padx=12, pady=(0, 10))

        if plan.excluded:
            ex = ", ".join(t.filename for t in plan.excluded)
            tk.Label(self, text=f"⚠ {len(plan.excluded)} parça uyumsuz olduğu için "
                                f"eklenmedi: {ex}", bg=BG, fg=MUTED, justify=tk.LEFT,
                     wraplength=470, font=("Segoe UI", 9)).pack(padx=24, pady=(8, 0))

        # --- transition tuning (pinned bottom, above transport) ---
        tune = tk.Frame(self, bg=PANEL2)
        tune.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=(4, 8))
        r1 = tk.Frame(tune, bg=PANEL2); r1.pack(fill=tk.X, padx=12, pady=(8, 2))
        tk.Label(r1, text="Geçiş süresi", bg=PANEL2, fg=TEXT,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.xfade_var = tk.DoubleVar(value=self.xfade)
        self.xf_lbl = tk.Label(r1, text=f"{self.xfade:.0f}s", bg=PANEL2, fg=ACCENT,
                               width=4, font=("Segoe UI Semibold", 9))
        self.xf_lbl.pack(side=tk.RIGHT)
        ttk.Scale(r1, from_=3, to=24, variable=self.xfade_var, orient=tk.HORIZONTAL,
                  command=lambda v: self.xf_lbl.config(
                      text=f"{self.xfade_var.get():.0f}s")).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        r2 = tk.Frame(tune, bg=PANEL2); r2.pack(fill=tk.X, padx=12, pady=(2, 8))
        tk.Label(r2, text="Tarz:", bg=PANEL2, fg=TEXT,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)
        cur_kind = plan.transitions[0].kind if plan.transitions else "crossfade"
        self.kind_var = tk.StringVar(value=cur_kind if cur_kind in ("crossfade", "eq_swap")
                                     else "crossfade")
        for val, txt in (("crossfade", "Yumuşak"), ("eq_swap", "DJ (EQ bass-swap)")):
            tk.Radiobutton(r2, text=txt, value=val, variable=self.kind_var,
                           bg=PANEL2, fg=TEXT, selectcolor=BG, activebackground=PANEL2,
                           activeforeground=TEXT, font=("Segoe UI", 9),
                           highlightthickness=0, bd=0).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(r2, text="🔁 Yeniden oluştur", command=self._rebuild).pack(
            side=tk.RIGHT)

        # --- transport (pinned to bottom, always visible) ---
        tf = tk.Frame(self, bg=BG); tf.pack(side=tk.BOTTOM, fill=tk.X,
                                            padx=24, pady=(8, 14))
        # seek bar with time labels
        seek = tk.Frame(tf, bg=BG); seek.pack(fill=tk.X)
        self.cur_lbl = tk.Label(seek, text="0:00", bg=BG, fg=MUTED, width=5,
                                font=("Segoe UI", 9))
        self.cur_lbl.pack(side=tk.LEFT)
        self.posvar = tk.DoubleVar(value=0.0)
        self.scale = ttk.Scale(seek, from_=0, to=max(1.0, self.duration),
                               variable=self.posvar, orient=tk.HORIZONTAL,
                               command=self._on_scale)
        self.scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.scale.bind("<Button-1>", lambda e: setattr(self, "_seeking", True))
        self.scale.bind("<ButtonRelease-1>", self._seek_release)
        self.tot_lbl = tk.Label(seek, text=mmss, bg=BG, fg=MUTED, width=5,
                                font=("Segoe UI", 9))
        self.tot_lbl.pack(side=tk.LEFT)
        # controls
        ctr = tk.Frame(tf, bg=BG); ctr.pack(pady=(10, 0))
        ttk.Button(ctr, text="⏪ 10sn", command=lambda: self._seek_by(-10)).pack(side=tk.LEFT)
        self.play_btn = ttk.Button(ctr, text="▶  Dinle", command=self._toggle_play)
        self.play_btn.pack(side=tk.LEFT, padx=8)
        ttk.Button(ctr, text="10sn ⏩", command=lambda: self._seek_by(10)).pack(side=tk.LEFT)
        ttk.Button(ctr, text="💾  Kaydet", style="Accent.TButton",
                   command=self._save).pack(side=tk.LEFT, padx=(16, 0))
        if not _PG:
            self.play_btn.config(state="disabled")

    # ------------------------------------------------------------- transport
    @staticmethod
    def _fmt(sec):
        sec = max(0, int(sec))
        return f"{sec // 60}:{sec % 60:02d}"

    def _start_from(self, pos):
        if not _PG:
            return
        pos = max(0.0, min(pos, self.duration))
        try:
            pygame.mixer.music.load(self.temp_path)
            pygame.mixer.music.play(start=pos)
        except Exception as e:
            messagebox.showerror("Oynatma hatası", str(e), parent=self)
            return
        self._pos = pos
        self._t0 = time.monotonic()
        self._playing = True
        self._paused = False
        self.play_btn.config(text="⏸  Duraklat")
        self.app._set_now("▶ AutoMix")
        if self._tick_id is None:
            self._tick()

    def _toggle_play(self):
        if not _PG:
            return
        if not self._playing:
            start = 0.0 if self._pos >= self.duration - 0.1 else self._pos
            self._start_from(start)
        elif self._paused:
            pygame.mixer.music.unpause()
            self._paused = False
            self._t0 = time.monotonic()
            self.play_btn.config(text="⏸  Duraklat")
        else:
            pygame.mixer.music.pause()
            self._paused = True
            self.play_btn.config(text="▶  Devam")

    def _seek_by(self, delta):
        self._do_seek(self._pos + delta)

    def _on_scale(self, _v):
        if self._seeking:
            self.cur_lbl.config(text=self._fmt(self.posvar.get()))

    def _seek_release(self, _e):
        self._do_seek(self.posvar.get())
        self._seeking = False

    def _do_seek(self, pos):
        pos = max(0.0, min(pos, self.duration))
        self.posvar.set(pos)
        self.cur_lbl.config(text=self._fmt(pos))
        if self._playing and not self._paused:
            self._start_from(pos)          # restart audio at new position
        else:
            self._pos = pos                # move marker; play from here later

    def _tick(self):
        if self._playing and not self._paused:
            now = time.monotonic()
            self._pos += now - self._t0
            self._t0 = now
            if self._pos >= self.duration:
                self._pos = self.duration
                self._stop()
            else:
                if not self._seeking:
                    self.posvar.set(self._pos)
                    self.cur_lbl.config(text=self._fmt(self._pos))
        self._tick_id = self.after(200, self._tick)

    def _stop(self):
        if _PG:
            try:
                pygame.mixer.music.stop()
                if hasattr(pygame.mixer.music, "unload"):
                    pygame.mixer.music.unload()   # release the file handle
            except Exception:
                pass
        self._playing = False
        self._paused = False
        self.play_btn.config(text="▶  Dinle")
        self.app._set_now("")

    def _rebuild(self):
        xfade = self.xfade_var.get()
        kind = self.kind_var.get()
        self._close()
        self.app.rebuild_mix(self.plan, xfade, kind, self.mode)

    def _close(self):
        if self._tick_id is not None:
            try:
                self.after_cancel(self._tick_id)
            except Exception:
                pass
        self._stop()
        self.destroy()

    def _save(self):
        dest = filedialog.asksaveasfilename(
            parent=self, defaultextension=".mp3", initialfile="mmbpm_mix.mp3",
            filetypes=[("MP3", "*.mp3")])
        if not dest:
            return
        try:
            shutil.copyfile(self.temp_path, dest)
            self.app.mix_path = dest
            messagebox.showinfo("Kaydedildi", f"Miks kaydedildi:\n{dest}", parent=self)
        except Exception as e:
            messagebox.showerror("Hata", str(e), parent=self)
