"""Shared data models: Track, Transition, MixPlan."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Track:
    filename: str
    path: str
    bpm: Optional[float] = None
    key_name: Optional[str] = None
    camelot: Optional[str] = None
    energy: Optional[float] = None      # loudness proxy, dBFS
    duration: float = 0.0

    @property
    def analyzed(self) -> bool:
        return self.bpm is not None and self.camelot is not None

    def to_dict(self) -> dict:
        return asdict(self)


# Transition kinds understood by the render engine (Stage 2).
TRANSITION_KINDS = ("crossfade", "cut", "fade", "eq_swap", "filter", "echo")

TRANSITION_LABELS = {
    "crossfade": "Crossfade",
    "cut": "Sert Kesme",
    "fade": "Yumuşak Fade",
    "eq_swap": "EQ Bass-Swap",
    "filter": "Filtre Süpürme",
    "echo": "Echo Kuyruğu",
}


@dataclass
class Transition:
    kind: str = "crossfade"
    seconds: float = 8.0


@dataclass
class MixPlan:
    """An ordered, editable mix: N clips joined by N-1 transitions."""
    target_bpm: float
    clips: list[Track] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    excluded: list[Track] = field(default_factory=list)  # left out: incompatible

    def normalize(self):
        """Keep transitions list length in sync with clips (N-1)."""
        need = max(0, len(self.clips) - 1)
        while len(self.transitions) < need:
            self.transitions.append(Transition())
        del self.transitions[need:]
        return self

    def move(self, i: int, direction: int):
        """Move clip i up (-1) or down (+1); transitions stay per-position."""
        j = i + direction
        if 0 <= i < len(self.clips) and 0 <= j < len(self.clips):
            self.clips[i], self.clips[j] = self.clips[j], self.clips[i]
            self.normalize()

    def remove(self, i: int):
        if 0 <= i < len(self.clips):
            self.clips.pop(i)
            self.normalize()
