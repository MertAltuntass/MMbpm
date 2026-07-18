# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for MMBpm (one-file Windows .exe).

If a ./ffmpeg_bin folder exists (CI downloads a small ffmpeg build into it),
ffmpeg.exe/ffprobe.exe are bundled so the .exe is fully self-contained.
"""
import os

binaries = []
ff_dir = os.path.join(os.getcwd(), "ffmpeg_bin")
if os.path.isdir(ff_dir):
    for exe in ("ffmpeg.exe", "ffprobe.exe"):
        p = os.path.join(ff_dir, exe)
        if os.path.exists(p):
            binaries.append((p, "ffmpeg"))   # -> _MEIPASS/ffmpeg/<exe>

datas = [("mmbpm/assets", "mmbpm/assets")]

a = Analysis(
    ["MMBpm.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=["scipy.signal", "scipy.special"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "librosa", "pydub", "numba", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MMBpm",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,                         # GUI app, no console window
    icon="mmbpm/assets/icon.ico",
)
