"""Turn a Prize record into a timed, shot-listed script.

The structure is fixed on purpose, because it is the structure that holds
retention on vertical video:

    hook   - 2s, poses a question, never mentions the prize
    beats  - the setup, escalating
    twist  - the payoff, the single most surprising fact
    kicker - reframes the absurdity as legitimate science

Timing here is an *estimate* used when there is no voiceover. When TTS is
enabled, pipeline.timing overwrites these numbers with the real ones.
"""

from __future__ import annotations

import re

from .models import Prize, Segment, VideoScript

# Short-form narration pace. Deliberately fast: on TikTok/Reels a relaxed
# read is a scroll. 2.9 w/s is brisk but still intelligible.
WORDS_PER_SECOND = 2.9

# Silence inserted after a segment, by role. The pause before the twist is
# the most valuable half-second in the video.
PAUSE_AFTER = {
    "hook": 0.28,
    "beat": 0.18,
    "twist": 0.30,
    "kicker": 0.0,
}

MIN_SEGMENT_SECONDS = 1.1


def build_segments(prize: Prize) -> list[Segment]:
    parts: list[tuple[str, str]] = [("hook", prize.hook)]
    parts += [("beat", b) for b in prize.beats]
    parts.append(("twist", prize.twist))
    parts.append(("kicker", prize.kicker))

    segments: list[Segment] = []
    for i, (role, text) in enumerate(parts):
        text = " ".join(text.split())
        if not text:
            continue
        segments.append(Segment(role=role, text=text, index=len(segments)))
    return segments


def estimate_durations(segments: list[Segment]) -> None:
    """Assign start/duration in place, from word count."""
    clock = 0.0
    for seg in segments:
        n_words = len(seg.text.split())
        spoken = max(n_words / WORDS_PER_SECOND, MIN_SEGMENT_SECONDS)
        seg.start = clock
        seg.duration = spoken + PAUSE_AFTER.get(seg.role, 0.15)
        clock = seg.end


def tokenize(text: str) -> list[str]:
    """Split into caption tokens, keeping punctuation attached to its word."""
    return [t for t in re.findall(r"\S+", text) if t]


def distribute_words(segments: list[Segment]) -> list:
    """Spread each segment's words across its spoken time.

    Longer words get proportionally more screen time, which tracks how they
    are actually said and keeps the captions from drifting out of sync.
    """
    from .models import Word

    words: list[Word] = []
    for seg in segments:
        tokens = tokenize(seg.text)
        if not tokens:
            continue
        pause = PAUSE_AFTER.get(seg.role, 0.15)
        speaking = max(seg.duration - pause, 0.4)

        weights = [max(len(t.strip(".,!?:;\"'")), 2) for t in tokens]
        total = sum(weights)

        clock = seg.start
        for token, weight in zip(tokens, weights):
            share = speaking * (weight / total)
            words.append(
                Word(
                    text=token,
                    start=clock,
                    end=clock + share,
                    segment_index=seg.index,
                )
            )
            clock += share
    return words


def write_script(prize: Prize) -> VideoScript:
    segments = build_segments(prize)
    estimate_durations(segments)
    script = VideoScript(prize_id=prize.id, badge=prize.badge, segments=segments)
    script.words = distribute_words(segments)
    return script
