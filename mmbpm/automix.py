"""Harmonic/energy ordering, editable mix plans, and per-transition rendering.

A MixPlan is an ordered list of clips joined by transitions. render_plan()
stretches every clip to a common BPM (beatmatch) and joins them with the
chosen transition type, streaming straight to disk via ffmpeg.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

import numpy as np
from scipy import signal

from . import analysis, audio
from .models import MixPlan, Track, Transition


# ---------------------------------------------------------------------------
# Camelot harmonic distance
# ---------------------------------------------------------------------------
def _parse_camelot(code: str):
    code = code.strip().upper()
    return int(code[:-1]), code[-1]


def camelot_distance(c1: str, c2: str) -> float:
    """0 = same key, small = harmonically adjacent, large = a clash."""
    try:
        n1, l1 = _parse_camelot(c1)
        n2, l2 = _parse_camelot(c2)
    except Exception:
        return 5.0
    wheel = min(abs(n1 - n2), 12 - abs(n1 - n2))
    if l1 == l2:
        return float(wheel)
    if n1 == n2:
        return 0.5
    return 2.0 + wheel


def transition_cost(a: Track, b: Track, bpm_weight: float = 0.08) -> float:
    cost = camelot_distance(a.camelot, b.camelot)
    cost += bpm_weight * abs(a.bpm - b.bpm)
    return cost


def relationship(a, b):
    """How well does `b` mix with `a`?  Returns (level, key_reason, bpm_note).

    level: 'perfect' | 'good' | 'weak' | 'none' — plain-language reasons in TR.
    """
    n1, l1 = _parse_camelot(a.camelot)
    n2, l2 = _parse_camelot(b.camelot)
    wheel_d = min(abs(n1 - n2), 12 - abs(n1 - n2))
    bpm_diff = abs((a.bpm or 0) - (b.bpm or 0))

    if a.camelot == b.camelot:
        level, reason = "perfect", "Aynı ton"
    elif l1 == l2 and wheel_d == 1:
        level, reason = "perfect", "Komşu ton — yumuşak geçiş"
    elif n1 == n2 and l1 != l2:
        level, reason = "good", "Majör–minör eşi — mood değişimi"
    elif l1 == l2 and wheel_d == 2:
        level, reason = "weak", "İki adım — dikkatli"
    else:
        level, reason = "none", "Uyumsuz ton"

    if bpm_diff <= 3:
        bpm_note = "tempo çok yakın"
    elif bpm_diff <= 6:
        bpm_note = "tempo yakın"
    elif bpm_diff <= 10:
        bpm_note = f"tempo farkı ~{bpm_diff:.0f}"
    else:
        bpm_note = f"tempo uzak ({bpm_diff:.0f})"
        if level in ("perfect", "good"):
            level = "weak"          # big tempo gap drags it down
    return level, reason, bpm_note


def compatible_with(track, pool, max_bpm_diff: float = 8.0):
    out = []
    for o in pool:
        if o is track:
            continue
        if camelot_distance(track.camelot, o.camelot) <= 1.0 and \
                abs(track.bpm - o.bpm) <= max_bpm_diff:
            out.append(o)
    out.sort(key=lambda o: transition_cost(track, o))
    return out


def energy_scale(tracks) -> dict:
    """Map each analyzed track -> 1..10 energy rank (relative to the set)."""
    vals = [t for t in tracks if t.energy is not None]
    if not vals:
        return {}
    lo = min(t.energy for t in vals)
    hi = max(t.energy for t in vals)
    span = (hi - lo) or 1.0
    return {id(t): 1 + int(round(9 * (t.energy - lo) / span)) for t in vals}


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------
def order_tracks(tracks, mode: str = "harmonic"):
    """mode: 'harmonic' (smoothest key path) or 'energy' (build weak->strong)."""
    tracks = [t for t in tracks if t.bpm and t.camelot]
    if len(tracks) <= 2:
        return list(tracks)
    remaining = list(tracks)
    if mode == "energy" and all(t.energy is not None for t in tracks):
        current = min(remaining, key=lambda t: t.energy)   # quietest first
    else:
        current = min(remaining, key=lambda t: t.bpm)      # slowest first
    remaining.remove(current)
    order = [current]
    while remaining:
        def score(t):
            c = transition_cost(current, t)
            if mode == "energy" and t.energy is not None and current.energy is not None:
                # reward rising energy, penalise big drops
                c += 0.3 * max(0.0, current.energy - t.energy)
            return c
        nxt = min(remaining, key=score)
        remaining.remove(nxt)
        order.append(nxt)
        current = nxt
    return order


def compatible_chain(tracks, mode: str = "harmonic",
                     key_tol: float = 1.0, bpm_tol: float = 8.0):
    """Longest chain of *mutually compatible* tracks (each transition passes the
    Camelot + BPM tolerance). Returns (chain, excluded). This keeps incompatible
    songs OUT so the mix doesn't turn into a mess."""
    pool = [t for t in tracks if t.bpm and t.camelot]
    if len(pool) <= 1:
        return list(pool), []

    have_energy = all(t.energy is not None for t in pool)
    use_energy = mode == "energy" and have_energy

    def step_score(cur, t):
        c = transition_cost(cur, t)
        if use_energy:
            c += 0.6 * max(0.0, cur.energy - t.energy)   # strongly prefer rising
        return c

    def build(seed):
        chain = [seed]
        remaining = [t for t in pool if t is not seed]
        cur = seed
        while remaining:
            cands = [t for t in remaining
                     if camelot_distance(cur.camelot, t.camelot) <= key_tol
                     and abs(cur.bpm - t.bpm) <= bpm_tol]
            if not cands:
                break
            nxt = min(cands, key=lambda t: step_score(cur, t))
            chain.append(nxt)
            remaining.remove(nxt)
            cur = nxt
        return chain

    def quality(chain):
        """Lower is better — the mode-specific tiebreak among longest chains."""
        if use_energy:
            start = chain[0].energy
            drops = sum(max(0.0, chain[i].energy - chain[i + 1].energy)
                        for i in range(len(chain) - 1))
            return (start, drops)             # start quiet, avoid energy drops
        cost = sum(transition_cost(chain[i], chain[i + 1])
                   for i in range(len(chain) - 1))
        return (cost, chain[0].bpm or 0)      # smoothest keys, slowest start

    chains = [build(seed) for seed in pool]
    maxlen = max(len(c) for c in chains)
    best = min((c for c in chains if len(c) == maxlen), key=quality)
    excluded = [t for t in pool if t not in best]
    return best, excluded


def build_plan(tracks, target_bpm: float | None = None, xfade: float = 10.0,
               mode: str = "harmonic", strict: bool = True) -> MixPlan:
    if strict:
        order, excluded = compatible_chain(tracks, mode=mode)
    else:
        order, excluded = order_tracks(tracks, mode=mode), []
    if target_bpm is None and order:
        target_bpm = round(float(np.median([t.bpm for t in order])), 1)
    plan = MixPlan(target_bpm=target_bpm or 120.0, clips=list(order),
                   excluded=list(excluded))
    for a, b in zip(order, order[1:]):
        kind = "crossfade" if camelot_distance(a.camelot, b.camelot) <= 1.0 else "cut"
        plan.transitions.append(Transition(kind=kind,
                                           seconds=xfade if kind != "cut" else 1.0))
    plan.normalize()
    return plan


# ---------------------------------------------------------------------------
# Transition blenders  (prev_tail, next_head -> mixed block of length L)
# Each operates on stereo arrays shaped (2, L).
# ---------------------------------------------------------------------------
def _ramps(L):
    t = np.linspace(0, 1, L)
    return t


def _blend_crossfade(prev, nxt, sr):
    L = prev.shape[1]
    t = np.linspace(0, np.pi / 2, L)
    fin = np.sin(t)          # equal-power: fin^2 + fout^2 == 1 (no mid dip)
    fout = np.cos(t)
    return prev * fout + nxt * fin


def _blend_fade(prev, nxt, sr):
    L = prev.shape[1]
    t = _ramps(L)
    return prev * (1 - t) + nxt * t


def _blend_eq_swap(prev, nxt, sr, xover=180.0):
    """Bass-swap: outgoing track keeps highs while its lows roll off; the
    incoming track brings the lows in. Classic house/techno transition."""
    L = prev.shape[1]
    sos_lp = signal.butter(4, xover, "low", fs=sr, output="sos")
    sos_hp = signal.butter(4, xover, "high", fs=sr, output="sos")

    def split(x):
        low = signal.sosfilt(sos_lp, x, axis=1)
        high = signal.sosfilt(sos_hp, x, axis=1)
        return low, high
    plow, phigh = split(prev)
    nlow, nhigh = split(nxt)
    t = _ramps(L)
    ang = np.linspace(0, np.pi / 2, L)
    fin = np.sin(ang)        # equal-power highs
    fout = np.cos(ang)
    # highs crossfade smoothly; lows hand off harder (bass swap near the middle)
    low_sw = np.clip((t - 0.35) / 0.3, 0, 1)     # 0 -> prev lows, 1 -> next lows
    lows = plow * (1 - low_sw) + nlow * low_sw
    highs = phigh * fout + nhigh * fin
    return lows + highs


def _blend_filter(prev, nxt, sr):
    """Filter sweep: a low-pass closes on the outgoing track (muffling it out)
    while a low-pass opens on the incoming track."""
    L = prev.shape[1]
    n_fft = 2048
    hop = 512
    freqs = np.fft.rfftfreq(n_fft, 1 / sr)

    def sweep(x, opening):
        out = np.zeros_like(x)
        win = np.hanning(n_fft)
        for start in range(0, L - n_fft, hop):
            frac = start / max(1, L - n_fft)
            cutoff = 300 + (frac if opening else (1 - frac)) ** 2 * (sr / 2 - 300)
            mask = (freqs <= cutoff).astype(np.float32)
            for ch in range(2):
                seg = x[ch, start:start + n_fft] * win
                spec = np.fft.rfft(seg) * mask
                out[ch, start:start + n_fft] += np.fft.irfft(spec, n_fft) * win
        return out
    return sweep(prev, opening=False) + sweep(nxt, opening=True)


def _blend_echo(prev, nxt, sr, delay=0.25, feedback=0.45):
    """Echo tail on the outgoing track as the incoming one fades in."""
    L = prev.shape[1]
    d = int(delay * sr)
    echoed = prev.copy()
    if d < L:
        buf = prev.copy()
        for _ in range(4):
            buf = np.pad(buf, ((0, 0), (d, 0)))[:, :L] * feedback
            echoed += buf
    ang = np.linspace(0, np.pi / 2, L)
    return echoed * np.cos(ang) + nxt * np.sin(ang)


_BLENDERS = {
    "crossfade": _blend_crossfade,
    "fade": _blend_fade,
    "eq_swap": _blend_eq_swap,
    "filter": _blend_filter,
    "echo": _blend_echo,
}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _normalize(y, peak=0.89):
    m = np.max(np.abs(y))
    return y * (peak / m) if m > 0 else y


def _trim_silence(y, sr, thresh=0.02):
    mono = np.abs(y).mean(axis=0)
    above = np.where(mono > thresh)[0]
    return y[:, above[0]:above[-1] + 1] if above.size else y


# ---------------------------------------------------------------------------
# Beat-grid alignment
# ---------------------------------------------------------------------------
def _onset_env(y, sr, hop=256, n_fft=1024):
    """Broadband onset-strength envelope (per-frame spectral flux)."""
    mono = y.mean(axis=0) if y.ndim == 2 else y
    mag = analysis._magnitude_spectrogram(mono, n_fft, hop)
    flux = np.maximum(0.0, np.diff(mag, axis=0)).sum(axis=1)
    m = flux.max() if flux.size else 0.0
    return flux / m if m > 0 else flux, hop


def _beat_align_trim(prev_tail, incoming, sr, beat_samples, in_len):
    """How many samples to trim off `incoming`'s head so its beats line up
    with `prev_tail` during the crossfade. Result is in [0, beat_samples)."""
    if in_len < sr // 8:                       # overlap too short to bother
        return 0
    a = prev_tail
    b = incoming[:, :in_len + beat_samples + 1]
    env_a, hop = _onset_env(a, sr)
    env_b, _ = _onset_env(b, sr, hop)
    if env_a.size < 4 or env_b.size < 4 or not np.any(env_a) or not np.any(env_b):
        return 0
    max_lag = int(beat_samples / hop)
    L = min(len(env_a), len(env_b) - max_lag)
    if L <= 4:
        return 0
    a_seg = env_a[:L]
    scores = np.array([np.dot(a_seg, env_b[lag:lag + L])
                       for lag in range(max_lag + 1)])
    best = int(np.argmax(scores))
    return min(best * hop, beat_samples - 1)


def _prep_clip(track, target_bpm, sr, tmpdir, i):
    ratio = target_bpm / track.bpm
    stretched = os.path.join(tmpdir, f"s{i}.wav")
    audio.time_stretch(track.path, stretched, ratio, sr=sr)
    y = audio.decode(stretched, sr=sr, mono=False)
    os.remove(stretched)
    if y.ndim == 1:
        y = np.vstack([y, y])
    return _normalize(_trim_silence(y, sr))


def render_plan(plan: MixPlan, out_path: str, sr: int = 44100,
                beat_align: bool = True, progress_cb=None) -> dict:
    plan.normalize()
    clips = [c for c in plan.clips if c.bpm and c.camelot]
    if len(clips) < 2:
        raise ValueError("Miks için en az iki analiz edilmiş parça gerekli.")
    target = plan.target_bpm
    beat_samples = int(sr * 60.0 / target) if target else sr // 2

    cmd = [audio.FFMPEG, "-v", "error", "-y", "-f", "f32le", "-ar", str(sr),
           "-ac", "2", "-i", "pipe:0"]
    if out_path.lower().endswith(".mp3"):
        cmd += ["-b:a", "320k"]
    cmd += [out_path]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,
                           creationflags=audio._CREATE_NO_WINDOW)

    def emit(block):
        enc.stdin.write(block.T.reshape(-1).astype("<f4").tobytes())

    def overlap_len(i):
        """Overlap samples for the transition AFTER clip i (0-based).

        With beat-grid on, snap the crossfade to a whole number of beats so
        transitions land on the grid (phrase-friendly)."""
        if i >= len(plan.transitions):
            return 0
        tr = plan.transitions[i]
        if tr.kind == "cut":
            return 0
        if beat_align and beat_samples > 0:
            beats = max(1, round(tr.seconds * sr / beat_samples))
            return beats * beat_samples
        return max(1, int(tr.seconds * sr))

    tmpdir = tempfile.mkdtemp(prefix="mmbpm_")
    timeline = []
    running = 0.0
    prev_tail = None
    try:
        n = len(clips)
        for i, tr in enumerate(clips):
            if progress_cb:
                progress_cb(i / n, f"Hazırlanıyor: {tr.filename}")
            y = _prep_clip(tr, target, sr, tmpdir, i)
            in_len = overlap_len(i - 1)
            out_len = overlap_len(i)
            # beat-grid: nudge this clip so its beats align with the previous
            # clip's beats through the crossfade.
            if (prev_tail is not None and beat_align
                    and plan.transitions[i - 1].kind != "cut"):
                delta = _beat_align_trim(prev_tail, y, sr, beat_samples, in_len)
                if 0 < delta < y.shape[1] - (in_len + out_len + 1):
                    y = y[:, delta:]
            N = y.shape[1]
            if N < in_len + out_len + 1:
                y = np.pad(y, ((0, 0), (0, in_len + out_len + 1 - N)))
                N = y.shape[1]

            timeline.append((tr, round(running, 2)))
            if prev_tail is None:
                emit(y[:, :N - out_len])
                running += (N - out_len) / sr
            else:
                kind = plan.transitions[i - 1].kind
                blender = _BLENDERS.get(kind, _blend_crossfade)
                mixed = blender(prev_tail, y[:, :in_len], sr)
                emit(mixed)
                emit(y[:, in_len:N - out_len])
                running += (N - out_len) / sr
            prev_tail = y[:, N - out_len:].copy() if out_len else None

        if prev_tail is not None:
            emit(prev_tail)
            running += prev_tail.shape[1] / sr
        enc.stdin.close()
        err = enc.stderr.read().decode("utf-8", "replace")
        enc.wait()
        if enc.returncode != 0:
            raise RuntimeError(err[:400])
    finally:
        try:
            enc.stdin.close()
        except Exception:
            pass
        for f in os.listdir(tmpdir):
            try:
                os.remove(os.path.join(tmpdir, f))
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass

    if progress_cb:
        progress_cb(1.0, "Miks tamamlandı")
    return {"target_bpm": target, "duration_sec": round(running, 1),
            "tracks": len(clips), "timeline": timeline, "out_path": out_path,
            "beat_align": beat_align}
