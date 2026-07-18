"""Persistent analysis cache so a library isn't re-analyzed every time.

Keyed by absolute path; validated against file size + mtime so edited/replaced
files are re-analyzed automatically. Stored as one JSON file in the home dir.
"""
from __future__ import annotations

import json
import os

_PATH = os.path.join(os.path.expanduser("~"), ".mmbpm_cache.json")
_data: dict | None = None


def _load() -> dict:
    global _data
    if _data is None:
        try:
            with open(_PATH, "r", encoding="utf-8") as f:
                _data = json.load(f)
        except Exception:
            _data = {}
    return _data


def _sig(path: str):
    try:
        st = os.stat(path)
        return [int(st.st_size), int(st.st_mtime)]
    except OSError:
        return None


def get(path: str) -> dict | None:
    """Cached analysis for `path`, or None if missing/stale."""
    key = os.path.abspath(path)
    entry = _load().get(key)
    if not entry:
        return None
    if entry.get("sig") != _sig(path):
        return None
    return entry.get("data")


def put(path: str, data: dict) -> None:
    d = _load()
    d[os.path.abspath(path)] = {"sig": _sig(path), "data": data}
    try:
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass
