"""BPM and musical-key (Camelot) detection using only numpy + scipy.

BPM: spectral-flux onset envelope -> autocorrelation with a tempo prior.
Key: chroma vector -> Krumhansl-Schmuckler profile correlation (major/minor).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import audio

# ---------------------------------------------------------------------------
# Note / Camelot tables
# ---------------------------------------------------------------------------
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# pitch-class -> Camelot code, for major and minor keys.
_MAJOR_CAMELOT = {0: "8B", 1: "3B", 2: "10B", 3: "5B", 4: "12B", 5: "7B",
                  6: "2B", 7: "9B", 8: "4B", 9: "11B", 10: "6B", 11: "1B"}
_MINOR_CAMELOT = {9: "8A", 10: "3A", 11: "10A", 0: "5A", 1: "12A", 2: "7A",
                  3: "2A", 4: "9A", 5: "4A", 6: "11A", 7: "6A", 8: "1A"}

# Krumhansl-Schmuckler key profiles.
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19,
                           2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75,
                           3.98, 2.69, 3.34, 3.17])


def camelot(pitch_class: int, mode: str) -> str:
    return (_MAJOR_CAMELOT if mode == "major" else _MINOR_CAMELOT)[pitch_class % 12]


@dataclass
class Analysis:
    bpm: float
    key_name: str      # e.g. "A minor"
    camelot: str       # e.g. "8A"
    energy: float      # loudness proxy, dBFS (higher = more energetic)


# ---------------------------------------------------------------------------
# Spectrogram helper
# ---------------------------------------------------------------------------
def _magnitude_spectrogram(y: np.ndarray, n_fft: int, hop: int):
    if len(y) < n_fft:
        y = np.pad(y, (0, n_fft - len(y)))
    window = np.hanning(n_fft).astype(np.float32)
    n_frames = 1 + (len(y) - n_fft) // hop
    frames = np.lib.stride_tricks.as_strided(
        y, shape=(n_frames, n_fft),
        strides=(y.strides[0] * hop, y.strides[0]),
    )
    spec = np.fft.rfft(frames * window, axis=1)
    return np.abs(spec).astype(np.float32)


# ---------------------------------------------------------------------------
# BPM
# ---------------------------------------------------------------------------
def estimate_bpm(y: np.ndarray, sr: int, n_fft: int = 1024, hop: int = 512,
                 bpm_min: float = 60.0, bpm_max: float = 200.0) -> float:
    mag = _magnitude_spectrogram(y, n_fft, hop)
    # Spectral flux: positive frame-to-frame magnitude change.
    flux = np.maximum(0.0, np.diff(mag, axis=0)).sum(axis=1)
    if flux.size < 4 or not np.any(flux):
        return 0.0
    flux -= flux.mean()

    fr = sr / hop  # onset-envelope frame rate (Hz)
    # Autocorrelation via FFT.
    n = 1 << int(np.ceil(np.log2(len(flux) * 2)))
    F = np.fft.rfft(flux, n)
    ac = np.fft.irfft(F * np.conj(F), n)[: len(flux)]
    ac[ac < 0] = 0.0

    lag_min = int(fr * 60.0 / bpm_max)
    lag_max = int(fr * 60.0 / bpm_min)
    lag_max = min(lag_max, len(ac) - 1)
    if lag_max <= lag_min:
        return 0.0

    lags = np.arange(lag_min, lag_max + 1)
    cand = ac[lag_min:lag_max + 1].copy()
    # Gaussian prior around ~120 BPM to curb octave errors.
    bpms = 60.0 * fr / lags
    prior = np.exp(-0.5 * ((np.log2(bpms / 120.0)) / 0.9) ** 2)
    best_i = int(np.argmax(cand * prior))
    best = lags[best_i]
    # Parabolic interpolation around the peak for sub-frame lag precision.
    peak = float(best)
    if 0 < best_i < len(cand) - 1:
        a, b, c = cand[best_i - 1], cand[best_i], cand[best_i + 1]
        denom = a - 2 * b + c
        if denom != 0:
            peak = best + 0.5 * (a - c) / denom
    bpm = 60.0 * fr / peak

    # Fold into a sensible DJ range.
    while bpm < 70:
        bpm *= 2
    while bpm >= 180:
        bpm /= 2
    return round(float(bpm), 1)


# ---------------------------------------------------------------------------
# Key
# ---------------------------------------------------------------------------
def _chroma(y: np.ndarray, sr: int, n_fft: int = 4096, hop: int = 2048):
    mag = _magnitude_spectrogram(y, n_fft, hop)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    chroma = np.zeros(12)
    lo, hi = 65.0, 2000.0  # C2..~B6
    valid = (freqs >= lo) & (freqs <= hi)
    idx = np.where(valid)[0]
    if idx.size == 0:
        return chroma
    pitch = 69 + 12 * np.log2(freqs[idx] / 440.0)
    pc = np.round(pitch).astype(int) % 12
    energy = mag[:, idx].sum(axis=0)
    for c in range(12):
        chroma[c] = energy[pc == c].sum()
    return chroma


def estimate_key(y: np.ndarray, sr: int):
    chroma = _chroma(y, sr)
    if not np.any(chroma):
        return 0, "major"
    chroma = chroma / chroma.sum()

    def corr(a, b):
        a = a - a.mean()
        b = b - b.mean()
        d = np.sqrt((a * a).sum() * (b * b).sum())
        return (a * b).sum() / d if d else 0.0

    best_score, best_pc, best_mode = -2.0, 0, "major"
    for tonic in range(12):
        rot = np.roll(chroma, -tonic)
        for mode, profile in (("major", _MAJOR_PROFILE), ("minor", _MINOR_PROFILE)):
            score = corr(rot, profile)
            if score > best_score:
                best_score, best_pc, best_mode = score, tonic, mode
    return best_pc, best_mode


def analyze_file(path: str, sr: int = 22050) -> Analysis:
    """Full analysis of one audio file. Analyzes up to ~90s from the middle
    for speed and stability (intros/outros are often misleading)."""
    dur = audio.probe_duration(path)
    if dur > 120:
        offset, length = max(0.0, dur / 2 - 45), 90.0
    else:
        offset, length = 0.0, None
    y = audio.decode(path, sr=sr, mono=True, offset=offset, duration=length)
    if y.size == 0:
        raise RuntimeError("boş ses verisi")
    # Loudness proxy from the raw signal (before peak-normalizing).
    rms = float(np.sqrt(np.mean(y ** 2)))
    energy = 20.0 * np.log10(rms + 1e-9)
    # Normalize for BPM/key.
    peak = np.max(np.abs(y))
    if peak > 0:
        y = y / peak
    bpm = estimate_bpm(y, sr)
    pc, mode = estimate_key(y, sr)
    key_name = f"{NOTE_NAMES[pc]} {'major' if mode == 'major' else 'minor'}"
    return Analysis(bpm=bpm, key_name=key_name, camelot=camelot(pc, mode),
                    energy=round(float(energy), 2))
