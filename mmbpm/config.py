"""Tiny persisted settings (first-run flag, last folder)."""
from __future__ import annotations

import json
import os

_PATH = os.path.join(os.path.expanduser("~"), ".mmbpm.json")


def load() -> dict:
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save(data: dict) -> None:
    try:
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def get(key, default=None):
    return load().get(key, default)


def set(key, value) -> None:
    d = load()
    d[key] = value
    save(d)
