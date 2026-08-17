"""Generate the platform metadata that ships alongside each video."""

from __future__ import annotations

import json
from pathlib import Path

from .models import Prize

BASE_TAGS = ["ignobel", "ignobelprize", "science", "weirdscience",
             "sciencefacts", "didyouknow"]

TAGS_BY_TOPIC = {
    "animals": ["animals", "animalfacts", "wildlife"],
    "physics": ["physics", "sciencetok"],
    "medicine": ["medicine", "medicaltok", "health"],
    "psychology": ["psychology", "psychologyfacts", "brain"],
    "biology": ["biology", "nature"],
    "gross": ["grossfacts", "weird"],
    "sex": ["relationships"],
    "useful": ["lifehack", "actuallyuseful"],
    "engineering": ["engineering", "design"],
    "food": ["foodfacts"],
}


def hashtags(prize: Prize, limit: int = 12) -> list[str]:
    tags = list(BASE_TAGS)
    for topic in prize.tags:
        tags += TAGS_BY_TOPIC.get(topic, [])
    seen, ordered = set(), []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            ordered.append(tag)
    return [f"#{t}" for t in ordered[:limit]]


def title(prize: Prize) -> str:
    """The on-platform title is the hook. Never lead with the prize name."""
    return prize.hook.rstrip(".")


def description(prize: Prize) -> str:
    lines = [
        prize.hook,
        "",
        f"Ig Nobel Prize, {prize.category}, {prize.year} — {prize.laureates}.",
        f'"{prize.citation}"',
        "",
        " ".join(hashtags(prize)),
    ]
    return "\n".join(lines)


def sources_block(prize: Prize) -> str:
    if not prize.refs:
        return ""
    return "Sources:\n" + "\n".join(f"- {r}" for r in prize.refs)


def build(prize: Prize, out_dir: Path) -> Path:
    payload = {
        "prize_id": prize.id,
        "title": title(prize),
        "description": description(prize),
        "hashtags": hashtags(prize),
        "sources": prize.refs,
        "verified": prize.verified,
        "pin_comment": sources_block(prize),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{prize.year}-{prize.id}.metadata.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
