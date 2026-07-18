"""Low-level audio I/O built entirely on ffmpeg + numpy.

No librosa / pydub — those are fragile on modern Python (pydub needs the
removed `audioop`, librosa needs numba). Everything here shells out to
ffmpeg for decode/encode and keeps samples as plain float32 numpy arrays.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import numpy as np

def _resolve(name: str) -> str:
    """Find an ffmpeg/ffprobe binary: bundled next to the app first (so a
    packaged .exe is self-contained), then PATH, then a common install dir."""
    exe = name + (".exe" if sys.platform == "win32" else "")
    # 1) PyInstaller bundle (files added via --add-binary land in _MEIPASS)
    base = getattr(sys, "_MEIPASS", None)
    if base:
        for sub in (("ffmpeg",), ()):
            cand = os.path.join(base, *sub, exe)
            if os.path.exists(cand):
                return cand
    # 2) next to the executable / script
    app_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False)
                              else os.path.dirname(os.path.abspath(__file__)))
    for cand in (os.path.join(app_dir, exe), os.path.join(app_dir, "ffmpeg", exe)):
        if os.path.exists(cand):
            return cand
    # 3) PATH, then a common Windows location
    return shutil.which(name) or (rf"C:\ffmpeg\bin\{exe}")


FFMPEG = _resolve("ffmpeg")
FFPROBE = _resolve("ffprobe")

# Hide the console window that subprocess would otherwise flash on Windows.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_CREATE_NO_WINDOW,
        **kw,
    )


def ffmpeg_available() -> bool:
    return os.path.exists(FFMPEG) or shutil.which("ffmpeg") is not None


def probe_duration(path: str) -> float:
    """Duration in seconds, or 0.0 if it can't be read."""
    try:
        out = _run([
            FFPROBE, "-v", "error", "-show_entries", "format=duration",
            "-of", "json", path,
        ]).stdout
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        return 0.0


def decode(path: str, sr: int = 22050, mono: bool = True,
           offset: float = 0.0, duration: float | None = None) -> np.ndarray:
    """Decode any audio file to a float32 numpy array in [-1, 1].

    Mono returns shape (n,); stereo returns shape (2, n).
    """
    cmd = [FFMPEG, "-v", "error"]
    if offset > 0:
        cmd += ["-ss", f"{offset}"]
    cmd += ["-i", path]
    if duration is not None:
        cmd += ["-t", f"{duration}"]
    ch = 1 if mono else 2
    cmd += ["-ac", str(ch), "-ar", str(sr), "-f", "f32le", "-acodec",
            "pcm_f32le", "-"]
    proc = _run(cmd)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[:400])
    data = np.frombuffer(proc.stdout, dtype=np.float32)
    if mono:
        return data.copy()
    return data.reshape(-1, 2).T.copy()


def encode(samples: np.ndarray, path: str, sr: int = 44100) -> None:
    """Write a numpy array (mono (n,) or stereo (2, n)) to disk via ffmpeg.

    Format is inferred from the output extension (.wav, .mp3, ...).
    """
    if samples.ndim == 1:
        ch = 1
        interleaved = samples
    else:
        ch = samples.shape[0]
        interleaved = samples.T.reshape(-1)
    interleaved = np.clip(interleaved, -1.0, 1.0).astype("<f4")
    cmd = [
        FFMPEG, "-v", "error", "-y",
        "-f", "f32le", "-ar", str(sr), "-ac", str(ch), "-i", "pipe:0",
    ]
    if path.lower().endswith(".mp3"):
        cmd += ["-b:a", "320k"]
    cmd += [path]
    proc = _run(cmd, input=interleaved.tobytes())
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[:400])


def waveform_peaks(path: str, buckets: int = 900, sr: int = 8000) -> np.ndarray:
    """Downsampled amplitude envelope (0..1) for drawing a waveform.

    Returns an array of length `buckets` with the peak magnitude in each slice.
    """
    y = decode(path, sr=sr, mono=True)
    if y.size == 0:
        return np.zeros(buckets)
    y = np.abs(y)
    edges = np.linspace(0, len(y), buckets + 1).astype(int)
    # per-bucket max via reduceat, guarding empty buckets
    starts = edges[:-1]
    peaks = np.maximum.reduceat(y, starts)
    empty = np.diff(edges) == 0
    peaks[empty] = 0.0
    m = peaks.max()
    return peaks / m if m > 0 else peaks


def time_stretch(path: str, out_path: str, ratio: float, sr: int = 44100) -> None:
    """Change tempo by `ratio` (out_bpm/in_bpm) WITHOUT changing pitch.

    Uses ffmpeg's atempo, chained to cover ratios outside [0.5, 2.0].
    ratio > 1 speeds up, < 1 slows down.
    """
    ratio = float(ratio)
    if abs(ratio - 1.0) < 1e-3:
        # No stretch needed — just transcode to the working format.
        _run([FFMPEG, "-v", "error", "-y", "-i", path, "-ar", str(sr),
              "-ac", "2", out_path])
        return
    factors = []
    r = ratio
    while r > 2.0:
        factors.append(2.0)
        r /= 2.0
    while r < 0.5:
        factors.append(0.5)
        r /= 0.5
    factors.append(r)
    chain = ",".join(f"atempo={f:.6f}" for f in factors)
    proc = _run([FFMPEG, "-v", "error", "-y", "-i", path, "-filter:a", chain,
                 "-ar", str(sr), "-ac", "2", out_path])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[:400])
