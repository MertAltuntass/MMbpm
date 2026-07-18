"""MMBpm — modern harmonic AutoMix GUI (tkinter, dark theme)."""
from __future__ import annotations

import json
import os
import queue
import tempfile
import threading

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import (analysis, audio, automix, cache, compat, config, logo, result,
               wheel)
from .models import Track
from .widgets import StepBar, ToolTip

try:
    import pygame
    pygame.mixer.init()
    _AUDIO_OK = True
except Exception:
    _AUDIO_OK = False

# ---- palette -------------------------------------------------------------
BG      = "#0e1015"
PANEL   = "#171a22"
PANEL2  = "#1e222c"
ACCENT  = "#00e0a4"
ACCENT2 = "#ff5c8a"
BLUE    = "#4f7cff"
TEXT    = "#e7e9f0"
MUTED   = "#868ea3"
LINE    = "#272c38"

AUDIO_EXT = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma")


class MMBpmApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.tracks: list[Track] = []
        self.busy = False
        self.mix_path: str | None = None
        self._uiq: queue.Queue = queue.Queue()   # cross-thread UI marshaling
        self._mix_seq = 0                         # unique temp filename counter

        root.title("MMBpm · Harmonic AutoMix")
        root.geometry("1120x720")
        root.minsize(960, 640)
        root.configure(bg=BG)
        self._icon = logo.apply_window_icon(root)

        self._init_style()
        self._build_header()
        self._build_steps()
        self._build_toolbar()
        self._build_body()
        self._build_footer()
        self._update_empty_state()
        self._poll_ui()
        self._set_status("Hazır. Başlamak için bir müzik klasörü açın." if _AUDIO_OK
                         else "Ses aygıtı yok — analiz/miks çalışır, oynatma devre dışı.")
        if not config.get("welcomed"):
            self.root.after(300, self._show_welcome)

    # ------------------------------------------------------------------ style
    def _init_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL,
                    bordercolor=LINE, font=("Segoe UI", 10))
        s.configure("Card.TFrame", background=PANEL)
        s.configure("TLabel", background=BG, foreground=TEXT)
        s.configure("Muted.TLabel", background=BG, foreground=MUTED)
        s.configure("CardMuted.TLabel", background=PANEL, foreground=MUTED)
        s.configure("Card.TLabel", background=PANEL, foreground=TEXT)
        s.configure("H1.TLabel", background=BG, foreground=TEXT,
                    font=("Segoe UI Semibold", 18))
        s.configure("H2.TLabel", background=PANEL, foreground=TEXT,
                    font=("Segoe UI Semibold", 11))
        # buttons
        s.configure("TButton", background=PANEL2, foreground=TEXT, borderwidth=0,
                    focuscolor=PANEL2, padding=(12, 8))
        s.map("TButton", background=[("active", LINE)])
        s.configure("Accent.TButton", background=ACCENT, foreground="#04120d",
                    font=("Segoe UI Semibold", 10), padding=(14, 9))
        s.map("Accent.TButton", background=[("active", "#28e9b6")])
        s.configure("Ghost.TButton", background=PANEL, foreground=TEXT)
        s.map("Ghost.TButton", background=[("active", PANEL2)])
        # treeview
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                    foreground=TEXT, borderwidth=0, rowheight=26,
                    font=("Cascadia Mono", 10) if self._has_font("Cascadia Mono")
                    else ("Consolas", 10))
        s.configure("Treeview.Heading", background=PANEL2, foreground=MUTED,
                    borderwidth=0, font=("Segoe UI Semibold", 9))
        s.map("Treeview.Heading", background=[("active", LINE)])
        s.map("Treeview", background=[("selected", BLUE)],
              foreground=[("selected", "#ffffff")])
        s.configure("TProgressbar", background=ACCENT, troughcolor=PANEL2,
                    borderwidth=0, thickness=8)
        s.configure("Horizontal.TScale", background=PANEL, troughcolor=PANEL2)
        s.configure("TCheckbutton", background=PANEL, foreground=TEXT)
        s.map("TCheckbutton", background=[("active", PANEL)])
        s.configure("TSpinbox", fieldbackground=PANEL2, background=PANEL2,
                    foreground=TEXT, arrowcolor=TEXT, borderwidth=0)

    def _has_font(self, name):
        try:
            import tkinter.font as tkfont
            return name in tkfont.families()
        except Exception:
            return False

    # ----------------------------------------------------------------- header
    def _build_header(self):
        h = tk.Frame(self.root, bg=BG)
        h.pack(fill=tk.X, padx=20, pady=(14, 2))
        mark = tk.Canvas(h, width=44, height=44, bg=BG, highlightthickness=0)
        mark.pack(side=tk.LEFT)
        logo.draw(mark, 22, 23, 15)
        tk.Label(h, text="MM", bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 20)).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(h, text="Bpm", bg=BG, fg=ACCENT,
                 font=("Segoe UI Semibold", 20)).pack(side=tk.LEFT)
        tk.Label(h, text="   harmonic auto-mix", bg=BG, fg=MUTED,
                 font=("Segoe UI", 12)).pack(side=tk.LEFT, pady=(6, 0))
        help_btn = ttk.Button(h, text="?  Nasıl Çalışır", command=self._show_welcome)
        help_btn.pack(side=tk.RIGHT)
        ToolTip(help_btn, "Adım adım kullanım rehberini aç.")

    def _build_steps(self):
        self.step = StepBar(self.root, [(1, "Klasör Aç"), (2, "Analiz Et"),
                                        (3, "Miks Yap")])
        self.step.pack(fill=tk.X, padx=20, pady=(0, 2))

    # ---------------------------------------------------------------- toolbar
    def _build_toolbar(self):
        t = tk.Frame(self.root, bg=BG)
        t.pack(fill=tk.X, padx=20, pady=6)
        magic = ttk.Button(t, text="🪄  Otomatik Miks Yap", style="Accent.TButton",
                           command=self.magic_mix)
        magic.pack(side=tk.LEFT)
        ToolTip(magic, "Yeni başlıyorsan buradan başla: klasörü seç, gerisini "
                       "MMBpm halleder — analiz eder, uyumlu parçaları miksler ve "
                       "dinlemen için hazırlar.")
        b1 = ttk.Button(t, text="📁  Klasör Aç", command=self.open_folder)
        b1.pack(side=tk.LEFT, padx=(8, 0))
        ToolTip(b1, "İçinde şarkılar (mp3/wav/flac…) olan bir klasör seç.")
        b2 = ttk.Button(t, text="⚡  Tümünü Analiz Et", command=self.analyze_all)
        b2.pack(side=tk.LEFT, padx=(8, 0))
        ToolTip(b2, "Her şarkının BPM'ini, tonunu (Camelot) ve enerjisini bulur.")
        b4 = ttk.Button(t, text="🧩  Uyum Haritası", command=self.open_compat)
        b4.pack(side=tk.LEFT, padx=(8, 0))
        ToolTip(b4, "Hangi şarkı hangisiyle uyumlu? Bir şarkı seç, eşleşenleri gör.")
        b3 = ttk.Button(t, text="💾  Analizi Dışa Aktar", command=self.export_json)
        b3.pack(side=tk.LEFT, padx=(8, 0))
        ToolTip(b3, "Analiz sonuçlarını JSON dosyası olarak kaydet.")
        self.pbar = ttk.Progressbar(t, mode="determinate", length=200)
        self.pbar.pack(side=tk.RIGHT)

    # ------------------------------------------------------------------- body
    def _build_body(self):
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=6)

        # --- library table (left) ---
        left = tk.Frame(body, bg=PANEL)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cols = ("cam", "bpm", "key", "en", "dur", "file")
        self.tree = ttk.Treeview(left, columns=cols, show="headings",
                                 selectmode="extended")
        heads = {"cam": ("KEY", 56), "bpm": ("BPM", 64), "key": ("TON", 84),
                 "en": ("ENERJİ", 74), "dur": ("SÜRE", 60), "file": ("DOSYA", 330)}
        self._sort_state = (None, False)
        for c, (txt, w) in heads.items():
            self.tree.heading(c, text=txt, command=lambda col=c: self._sort_by(col))
            anchor = tk.W if c == "file" else tk.CENTER
            self.tree.column(c, width=w, anchor=anchor,
                             stretch=(c == "file"))
        self.tree.tag_configure("odd", background=PANEL)
        self.tree.tag_configure("even", background="#141821")
        self.tree.tag_configure("hot", foreground=ACCENT)
        vs = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self.preview_selected())

        # empty-state overlay (shown when the library is empty)
        self.empty = tk.Frame(left, bg=PANEL)
        tk.Label(self.empty, text="🎵", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 40)).pack(pady=(0, 6))
        tk.Label(self.empty, text="Kütüphanen boş", bg=PANEL, fg=TEXT,
                 font=("Segoe UI Semibold", 14)).pack()
        tk.Label(self.empty, text="Başlamak için müzik klasörünü seç.\n"
                 "Yeni misin? “🪄 Otomatik Miks Yap” sana yeter.",
                 bg=PANEL, fg=MUTED, justify=tk.CENTER,
                 font=("Segoe UI", 10)).pack(pady=(4, 12))
        ttk.Button(self.empty, text="📁  Klasör Aç", style="Accent.TButton",
                   command=self.open_folder).pack()
        self.recent_btn = ttk.Button(self.empty, text="", command=self.open_last_folder)

        # --- right column ---
        right = tk.Frame(body, bg=BG, width=304)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(14, 0))
        right.pack_propagate(False)

        self.wheel = tk.Canvas(right, width=284, height=176, bg=PANEL,
                               highlightthickness=0)
        self.wheel.pack(fill=tk.X)
        self.wheel.bind("<Configure>", lambda e: self._draw_wheel())
        self._draw_wheel()
        ToolTip(self.wheel, "Camelot çarkı: her dilim bir müzik tonu. Yan yana / "
                            "aynı sayıdaki tonlar birbiriyle uyumludur. Bir parça "
                            "seçince uyumlu komşuları vurgulanır.")

        # --- mixing card ---
        card = tk.Frame(right, bg=PANEL)
        card.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        tk.Label(card, text="MİKS OLUŞTUR", bg=PANEL, fg=ACCENT,
                 font=("Segoe UI Semibold", 10)).pack(anchor=tk.W, padx=16, pady=(12, 6))

        tk.Label(card, text="Sıralama düzeni", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 9)).pack(anchor=tk.W, padx=16)
        self.sort_mode = tk.StringVar(value="harmonic")
        mrow = tk.Frame(card, bg=PANEL); mrow.pack(anchor=tk.W, padx=16, pady=(2, 2))
        rh = ttk.Radiobutton(mrow, text="Harmonik", value="harmonic",
                             variable=self.sort_mode, command=self._sort_mode_hint)
        rh.pack(side=tk.LEFT)
        ToolTip(rh, "Tonları en akıcı şekilde bağlar (uyumlu geçişler).")
        re_ = ttk.Radiobutton(mrow, text="Enerji", value="energy",
                              variable=self.sort_mode, command=self._sort_mode_hint)
        re_.pack(side=tk.LEFT, padx=(10, 0))
        ToolTip(re_, "Sakin başlayıp giderek enerjiyi yükseltir (zayıf → güçlü).")
        self.mode_hint = tk.Label(card, text="", bg=PANEL, fg=ACCENT,
                                  justify=tk.LEFT, wraplength=260,
                                  font=("Segoe UI", 8))
        self.mode_hint.pack(anchor=tk.W, padx=16, pady=(0, 2))
        self._sort_mode_hint()

        make_btn = ttk.Button(card, text="🎚  Miksi Oluştur", style="Accent.TButton",
                              command=self.make_mix)
        make_btn.pack(fill=tk.X, padx=16, pady=(10, 2))
        ToolTip(make_btn, "Sadece birbiriyle uyumlu parçaları otomatik miksler ve "
                          "dinlemen için hazırlar. Uyumsuzlar dışarıda kalır.")
        tk.Label(card, text="Seçim yapmazsan tüm kütüphane kullanılır;\n"
                            "yalnızca uyumlu olanlar mikse girer.",
                 bg=PANEL, fg=MUTED, justify=tk.LEFT,
                 font=("Segoe UI", 8)).pack(anchor=tk.W, padx=16)

        prow = tk.Frame(card, bg=PANEL); prow.pack(fill=tk.X, padx=16, pady=(10, 3))
        pm = ttk.Button(prow, text="▶ Son Miks", command=self.play_mix)
        pm.pack(side=tk.LEFT, expand=True, fill=tk.X)
        ToolTip(pm, "En son oluşturduğun miksi çal.")
        ttk.Button(prow, text="⏹", width=4,
                   command=self.stop_audio).pack(side=tk.LEFT, padx=(6, 0))
        pv = ttk.Button(card, text="▶ Seçili Parçayı Önizle",
                        command=self.preview_selected)
        pv.pack(fill=tk.X, padx=16, pady=(0, 10))
        ToolTip(pv, "Tabloda seçili şarkıyı çal (çift tıkla da olur).")

    # ----------------------------------------------------------------- footer
    def _build_footer(self):
        f = tk.Frame(self.root, bg=PANEL2)
        f.pack(fill=tk.X, side=tk.BOTTOM)
        self.status = tk.Label(f, text="", bg=PANEL2, fg=MUTED, anchor=tk.W,
                               font=("Segoe UI", 9), padx=16, pady=6)
        self.status.pack(side=tk.LEFT)
        self.now = tk.Label(f, text="", bg=PANEL2, fg=ACCENT, anchor=tk.E,
                            font=("Segoe UI", 9), padx=16)
        self.now.pack(side=tk.RIGHT)

    # ============================================================ UI helpers
    def _ui(self, fn):
        """Queue a callable to run on the Tk main thread (safe from any thread).

        Do NOT touch Tkinter here — even root.after() is unsafe off-thread on
        Python 3.14. The main-thread poller drains the queue instead."""
        self._uiq.put(fn)

    def _poll_ui(self):
        try:
            while True:
                fn = self._uiq.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except queue.Empty:
            pass
        self.root.after(40, self._poll_ui)

    def _set_status(self, msg):
        self._ui(lambda: self.status.config(text=msg))

    def _set_now(self, msg):
        self._ui(lambda: self.now.config(text=msg))

    def _fmt_dur(self, s):
        s = int(s or 0)
        return f"{s // 60}:{s % 60:02d}"

    def _update_empty_state(self):
        if self.tracks:
            self.empty.place_forget()
        else:
            last = config.get("last_folder")
            if last and os.path.isdir(last):
                self.recent_btn.config(text=f"↩  Son klasör: {os.path.basename(last)}")
                self.recent_btn.pack(pady=(8, 0))
            else:
                self.recent_btn.pack_forget()
            self.empty.place(relx=0.5, rely=0.42, anchor="center")

    def _sort_mode_hint(self):
        if self.sort_mode.get() == "energy":
            short, full = ("⚡ Sakin başlar, enerjiyi yükseltir",
                           "Enerji: en sessiz parçadan başlar, sırayı giderek "
                           "yükselen enerjiye göre kurar.")
        else:
            short, full = ("🎹 En akıcı ton geçişleri",
                           "Harmonik: parçaları en akıcı ton geçişlerine göre "
                           "sıralar (Camelot komşuları).")
        self.mode_hint.config(text=short)
        self._set_status(full)

    def _mark_analyzed_step(self):
        if any(t.analyzed for t in self.tracks):
            self.step.mark_done(1)
            self.step.set_active(2)

    # ----------------------------------------------------------- welcome / help
    def _show_welcome(self):
        w = tk.Toplevel(self.root)
        w.title("MMBpm'e Hoş Geldin")
        w.configure(bg=BG)
        w.geometry("560x540")
        w.transient(self.root)
        w.resizable(False, False)
        logo.apply_window_icon(w)
        dont = tk.BooleanVar(value=bool(config.get("welcomed")))

        def close():
            config.set("welcomed", bool(dont.get()))
            w.destroy()
        w.protocol("WM_DELETE_WINDOW", close)

        # --- bottom action bar FIRST so it's always visible ---
        bar = tk.Frame(w, bg=BG)
        bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 14))
        ttk.Button(bar, text="Hadi başlayalım  →", style="Accent.TButton",
                   command=close).pack()
        tk.Checkbutton(bar, text="Bunu bir daha gösterme", variable=dont,
                       bg=BG, fg=MUTED, selectcolor=PANEL2, activebackground=BG,
                       activeforeground=TEXT, font=("Segoe UI", 9),
                       highlightthickness=0, bd=0).pack(pady=(8, 0))

        # --- content ---
        tk.Label(w, text="🎧 3 adımda ilk miksin", bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 16)).pack(pady=(20, 2))
        tk.Label(w, text="Müzikten hiç anlamasan da olur — MMBpm gerisini halleder.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(pady=(0, 12))
        steps = [
            ("1  ·  Klasör Aç",
             "Şarkılarının olduğu klasörü seç (mp3, wav, flac…)."),
            ("2  ·  Analiz Et",
             "MMBpm her şarkının temposunu (BPM), tonunu ve enerjisini bulur."),
            ("3  ·  Miksi Oluştur",
             "Yalnızca birbiriyle uyumlu parçaları birleştirir; dinle ve kaydet."),
            ("🧩  Uyum Haritası",
             "Bir şarkıya tıkla, onunla uyumlu olan diğer şarkıları gör."),
            ("🪄  Acelen mi var?",
             "Tek düğme: “Otomatik Miks Yap”. Klasörü seç, miks hazır gelsin."),
        ]
        for title, body in steps:
            row = tk.Frame(w, bg=PANEL)
            row.pack(fill=tk.X, padx=22, pady=4)
            tk.Label(row, text=title, bg=PANEL, fg=ACCENT,
                     font=("Segoe UI Semibold", 11), anchor=tk.W).pack(
                fill=tk.X, padx=12, pady=(7, 0))
            tk.Label(row, text=body, bg=PANEL, fg=TEXT, justify=tk.LEFT,
                     wraplength=480, anchor=tk.W, font=("Segoe UI", 9)).pack(
                fill=tk.X, padx=12, pady=(0, 7))

    # --------------------------------------------------------- one-click magic
    def magic_mix(self):
        if self.busy:
            return
        if not self.tracks:
            self.open_folder()
        if not self.tracks:
            return
        mode = self.sort_mode.get()          # read Tk var on the main thread
        threading.Thread(target=self._magic_worker, args=(mode,),
                         daemon=True).start()

    def _magic_worker(self, mode):
        self.busy = True
        self._analyze_pending()
        self._ui(self._mark_analyzed_step)
        analyzed = [t for t in self.tracks if t.analyzed]
        if len(analyzed) < 2:
            self.busy = False
            self._ui(lambda: messagebox.showinfo(
                "MMBpm", "Miks için en az iki analiz edilebilir parça gerekli."))
            return
        self._render_result(analyzed, mode)

    def make_mix(self):
        """Card action: build a mix from the selection (or whole library)."""
        if self.busy:
            return
        analyzed = [t for t in self.tracks if t.analyzed]
        sel = [self.tracks[i] for i in self._selected_indices() if self.tracks[i].analyzed]
        pool = sel if len(sel) >= 2 else analyzed
        if len(pool) < 2:
            messagebox.showinfo("MMBpm",
                                "Önce en az iki parçayı analiz et (⚡ veya 🪄).")
            return
        mode = self.sort_mode.get()          # read Tk var on the main thread
        threading.Thread(target=self._render_result, args=(pool, mode),
                         daemon=True).start()

    DEFAULT_XFADE = 10.0

    def _render_result(self, pool, mode="harmonic"):
        """Build + render a mix of only-compatible tracks, then show the result."""
        self.busy = True
        try:
            plan = automix.build_plan(pool, xfade=self.DEFAULT_XFADE, mode=mode)
            if len(plan.clips) < 2:
                self._set_status("Uyumlu parça bulunamadı.")
                self._ui(lambda: messagebox.showinfo(
                    "Uyumlu değil",
                    "Bu parçalar birbiriyle yeterince uyumlu değil, miks karışık "
                    "olurdu.\n\nUyum Haritası'ndan (🧩) birbiriyle uyumlu parçaları "
                    "görüp öyle seçebilirsin."))
                self.busy = False
                return
            self._render_plan_and_show(plan, mode, self.DEFAULT_XFADE)
        except Exception as e:
            self._set_status(f"Miks hatası: {e}")
            self._ui(lambda: messagebox.showerror("Hata", str(e)))
            self.busy = False

    def rebuild_mix(self, plan, xfade, kind, mode):
        """Re-render an existing plan with a new transition length / style."""
        if self.busy:
            return
        for tr in plan.transitions:
            tr.kind = kind
            tr.seconds = float(xfade)
        self.busy = True
        threading.Thread(target=self._render_plan_and_show,
                         args=(plan, mode, float(xfade)), daemon=True).start()

    def _render_plan_and_show(self, plan, mode, xfade):
        """Render `plan` to the preview file and open the result screen."""
        self.busy = True
        try:
            # Unique filename each time — never overwrite a file pygame may still
            # hold open (that caused "Errno 22 Invalid argument" on Windows).
            self._mix_seq += 1
            tmp = os.path.join(tempfile.gettempdir(),
                               f"mmbpm_mix_{os.getpid()}_{self._mix_seq}.mp3")
            prev = self.mix_path
            if prev and prev != tmp and "mmbpm_mix_" in os.path.basename(prev):
                try:
                    os.remove(prev)           # best-effort cleanup of the old one
                except OSError:
                    pass

            def cb(frac, msg):
                self._set_status(msg)
                self._ui(lambda f=frac: self.pbar.config(maximum=100, value=int(f * 100)))

            summ = automix.render_plan(plan, tmp, progress_cb=cb)
            self.mix_path = tmp
            self._ui(lambda: (self.step.mark_done(2), self.step.set_active(2)))
            ex = len(plan.excluded)
            self._set_status(f"✓ Miks hazır · {summ['tracks']} şarkı · "
                             f"{summ['target_bpm']:.0f} BPM"
                             + (f" · {ex} uyumsuz parça atlandı" if ex else ""))
            self._ui(lambda: result.MixResult(self.root, self, plan, summ, tmp,
                                              mode, xfade))
        except Exception as e:
            self._set_status(f"Miks hatası: {e}")
            self._ui(lambda: messagebox.showerror("Hata", str(e)))
        finally:
            self.busy = False

    # ============================================================ library ops
    def open_folder(self, folder=None):
        if self.busy:
            return
        if folder is None:
            folder = filedialog.askdirectory(title="Müzik klasörü seç")
        if not folder or not os.path.isdir(folder):
            return
        config.set("last_folder", folder)
        self.tracks.clear()
        cached = 0
        for name in sorted(os.listdir(folder)):
            if name.lower().endswith(AUDIO_EXT):
                p = os.path.join(folder, name)
                tr = Track(name, p, duration=audio.probe_duration(p))
                c = cache.get(p)                       # reuse prior analysis
                if c:
                    tr.bpm = c.get("bpm"); tr.key_name = c.get("key_name")
                    tr.camelot = c.get("camelot"); tr.energy = c.get("energy")
                    cached += 1
                self.tracks.append(tr)
        self._refresh_table()
        self._update_empty_state()
        if self.tracks:
            self.step.mark_done(0)
            self.step.set_active(2 if cached == len(self.tracks) else 1)
            if cached:
                self._mark_analyzed_step()
        extra = f" ({cached} tanesi önbellekten hazır)" if cached else ""
        self._set_status(f"{len(self.tracks)} parça yüklendi{extra}. "
                         "'Tümünü Analiz Et' ile analiz edin (veya 🪄 Otomatik Miks).")

    def open_last_folder(self):
        last = config.get("last_folder")
        if last and os.path.isdir(last):
            self.open_folder(last)

    def _energy_label(self, tr, scale):
        rank = scale.get(id(tr))
        if rank is None:
            return "—"
        return f"{'▮' * rank}{'▯' * (10 - rank)} {rank}"

    def _row_values(self, tr, scale):
        return (tr.camelot or "—",
                f"{tr.bpm:.1f}" if tr.bpm else "—",
                tr.key_name or "—",
                self._energy_label(tr, scale),
                self._fmt_dur(tr.duration),
                tr.filename)

    def _refresh_table(self):
        scale = automix.energy_scale(self.tracks)
        self.tree.delete(*self.tree.get_children())
        for i, tr in enumerate(self.tracks):
            tag = "even" if i % 2 else "odd"
            self.tree.insert("", tk.END, iid=str(i),
                             values=self._row_values(tr, scale), tags=(tag,))
        self._draw_wheel()

    def _update_row(self, i):
        scale = automix.energy_scale(self.tracks)
        self.tree.item(str(i), values=self._row_values(self.tracks[i], scale))

    def _selected_indices(self):
        return [int(i) for i in self.tree.selection()]

    def _sort_by(self, col):
        """Sort the library by a clicked column header (toggle asc/desc)."""
        prev_col, prev_desc = self._sort_state
        desc = not prev_desc if col == prev_col else False
        big = float("inf")

        def key(t):
            if col == "bpm":
                return t.bpm if t.bpm is not None else big
            if col == "en":
                return t.energy if t.energy is not None else -big
            if col == "dur":
                return t.duration or 0
            if col == "cam":
                if not t.camelot:
                    return (99, "Z")
                return (int(t.camelot[:-1]), t.camelot[-1])
            if col == "key":
                return t.key_name or "zz"
            return t.filename.lower()
        self.tracks.sort(key=key, reverse=desc)
        self._sort_state = (col, desc)
        self._refresh_table()
        arrow = " ↓" if desc else " ↑"
        for c in ("cam", "bpm", "key", "en", "dur", "file"):
            base = self.tree.heading(c, "text").rstrip(" ↑↓")
            self.tree.heading(c, text=base + (arrow if c == col else ""))

    # ------------------------------------------------------------- analysis
    def analyze_all(self):
        if self.busy or not self.tracks:
            if not self.tracks:
                messagebox.showinfo("MMBpm", "Önce bir klasör açın.")
            return
        threading.Thread(target=self._analyze_worker, daemon=True).start()

    def _analyze_pending(self):
        """Analyze every not-yet-analyzed track. Runs in a worker thread."""
        pending = [i for i, t in enumerate(self.tracks) if not t.analyzed]
        total = len(pending)
        if total == 0:
            return
        self._ui(lambda: self.pbar.config(maximum=total, value=0))
        for done, i in enumerate(pending, 1):
            tr = self.tracks[i]
            self._set_status(f"Analiz ediliyor ({done}/{total}): {tr.filename}")
            try:
                a = analysis.analyze_file(tr.path)
                tr.bpm, tr.key_name, tr.camelot = a.bpm, a.key_name, a.camelot
                tr.energy = a.energy
                cache.put(tr.path, {"bpm": a.bpm, "key_name": a.key_name,
                                    "camelot": a.camelot, "energy": a.energy})
            except Exception as e:
                self._set_status(f"Hata ({tr.filename}): {e}")
            self._ui(lambda i=i: self._update_row(i))
            self._ui(lambda d=done: self.pbar.config(value=d))
        self._ui(self._draw_wheel)

    def _analyze_worker(self):
        self.busy = True
        self._analyze_pending()
        self._set_status("Analiz tamamlandı. 🎚 Miksi Oluştur ile miksle "
                         "ya da 🧩 Uyum Haritası'na bak.")
        self._ui(self._mark_analyzed_step)
        self.busy = False

    # ------------------------------------------------------------- selection
    def _on_select(self, _evt=None):
        idx = self._selected_indices()
        if not idx:
            return
        tr = self.tracks[idx[0]]
        if tr.analyzed:
            comp = automix.compatible_with(tr, self.tracks)
            self._set_status(
                f"{tr.filename}  ·  {tr.camelot} {tr.key_name} {tr.bpm:.1f} BPM"
                f"  ·  {len(comp)} uyumlu parça")
        self._draw_wheel(highlight=tr if tr.analyzed else None)

    # ------------------------------------------------------------- export
    def export_json(self):
        data = [t.to_dict() for t in self.tracks if t.analyzed]
        if not data:
            messagebox.showinfo("MMBpm", "Dışa aktarılacak analiz verisi yok.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._set_status(f"Kaydedildi: {path}")

    # ============================================================ compatibility
    def open_compat(self):
        analyzed = [t for t in self.tracks if t.analyzed]
        if len(analyzed) < 2:
            messagebox.showinfo("MMBpm",
                                "Önce en az iki parçayı analiz edin — sonra uyum "
                                "haritasını açabilirsiniz.")
            return
        compat.CompatibilityMap(self.root, self, analyzed)

    # ============================================================ automix
    # ============================================================ playback
    def _play_file(self, path, label):
        if not _AUDIO_OK:
            messagebox.showinfo("MMBpm", "Bu ortamda ses aygıtı yok, oynatma devre dışı.")
            return
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            self._set_now(f"▶ {label}")
        except Exception as e:
            messagebox.showerror("Oynatma hatası", str(e))

    def preview_selected(self):
        idx = self._selected_indices()
        if not idx:
            messagebox.showinfo("MMBpm", "Önizlemek için bir parça seçin.")
            return
        tr = self.tracks[idx[0]]
        self._play_file(tr.path, tr.filename)

    def play_mix(self):
        if not self.mix_path or not os.path.exists(self.mix_path):
            messagebox.showinfo("MMBpm", "Önce bir AutoMix oluşturun.")
            return
        self._play_file(self.mix_path, "AutoMix")

    def stop_audio(self):
        if _AUDIO_OK:
            pygame.mixer.music.stop()
        self._set_now("")

    # ============================================================ camelot wheel
    def _draw_wheel(self, highlight: Track | None = None):
        present = {t.camelot for t in self.tracks if t.analyzed}
        wheel.draw(self.wheel, present,
                   highlight.camelot if highlight else None)


def main():
    if not audio.ffmpeg_available():
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("MMBpm", "ffmpeg bulunamadı. Lütfen ffmpeg kurun ve PATH'e ekleyin.")
        return
    root = tk.Tk()
    MMBpmApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
