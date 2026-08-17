"""Core data structures shared by every stage of the pipeline."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class Prize:
    """One Ig Nobel Prize, as stored in data/prizes.json."""

    id: str
    year: int
    category: str
    laureates: str
    citation: str
    hook: str
    beats: list[str]
    twist: str
    kicker: str
    tags: list[str] = field(default_factory=list)
    verified: str = "unverified"
    refs: list[str] = field(default_factory=list)

    @property
    def badge(self) -> str:
        return f"IG NOBEL · {self.category.upper()} · {self.year}"


@dataclass
class Segment:
    """A spoken section of the video, backed by one background card.

    `role` drives the visual treatment: the hook and the twist get louder
    cards than the setup beats.
    """

    role: str  # hook | beat | twist | kicker
    text: str
    index: int
    start: float = 0.0
    duration: float = 0.0

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass
class Word:
    """One caption word with its own on-screen window."""

    text: str
    start: float
    end: float
    segment_index: int


@dataclass
class VideoScript:
    prize_id: str
    badge: str
    segments: list[Segment]
    words: list[Word] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.segments[-1].end if self.segments else 0.0

    @property
    def narration(self) -> str:
        return " ".join(s.text for s in self.segments)

    def to_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "prize_id": self.prize_id,
                    "badge": self.badge,
                    "duration": round(self.duration, 2),
                    "narration": self.narration,
                    "segments": [asdict(s) for s in self.segments],
                    "words": [asdict(w) for w in self.words],
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def load_prizes(path: Path) -> list[Prize]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Prize(**p) for p in raw["prizes"]]


def load_prize(path: Path, prize_id: str) -> Prize:
    prizes = load_prizes(path)
    for p in prizes:
        if p.id == prize_id:
            return p
    known = ", ".join(sorted(p.id for p in prizes))
    raise KeyError(f"No prize with id {prize_id!r}. Available: {known}")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
