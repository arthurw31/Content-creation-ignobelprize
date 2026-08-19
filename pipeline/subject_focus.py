"""Decide where captions can sit without covering the subject.

Captions parked at a fixed height land on the rat's face about a third of the
time. Rather than guess, this samples frames from each shot, measures how much
detail sits in each candidate caption band, and picks the quietest one.

Edge energy is a decent proxy for "the subject is here": fur, eyes, hands and
labels all carry high-frequency detail, while a wall, a bench top or a
shallow-focus background does not.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter

from . import theme

# Where a caption block is allowed to sit, as a fraction of frame height.
# Nothing below 0.74: that is where the platform stacks its own UI.
CANDIDATES = (0.30, 0.46, 0.70)

# Half-height of the band a caption occupies, in fractions of frame height.
# Two lines of 86px type plus its outline is roughly 220px on a 1920 frame.
BAND_HALF = 0.058

SAMPLES = 3


@dataclass
class Placement:
    """Where this shot's captions go, and why."""

    shot_index: int
    y: int
    energy: dict[float, float]

    @property
    def chosen_fraction(self) -> float:
        return self.y / theme.HEIGHT


def _sample_frames(media: Path, count: int, ffmpeg: str,
                   work: Path) -> list[Image.Image]:
    """Grab evenly spaced frames. Works for both a clip and a still."""
    work.mkdir(parents=True, exist_ok=True)
    if media.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        return [Image.open(media).convert("L")]

    frames: list[Image.Image] = []
    for i in range(count):
        # Offsets inside the clip rather than at its very edges, where a
        # generated clip sometimes still has a settling frame.
        at = 0.25 + i * (0.5 / max(count - 1, 1))
        out = work / f"probe{i}.png"
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-ss", f"{at:.2f}",
             "-i", str(media), "-frames:v", "1", str(out)],
            capture_output=True,
        )
        if out.exists():
            frames.append(Image.open(out).convert("L"))
    return frames


def _band_energy(frame: Image.Image, centre: float) -> float:
    """Mean edge magnitude inside the caption band at `centre`."""
    width, height = frame.size
    top = int(max(centre - BAND_HALF, 0.0) * height)
    bottom = int(min(centre + BAND_HALF, 1.0) * height)
    band = frame.crop((0, top, width, bottom))
    edges = band.filter(ImageFilter.FIND_EDGES)
    data = list(edges.getdata())
    return sum(data) / len(data) if data else 0.0


def place_captions(media_by_shot: dict[int, Path], ffmpeg: str, work: Path,
                   blocked: dict[int, set[float]] | None = None,
                   ) -> dict[int, Placement]:
    """One caption position per shot, avoiding whatever is busiest.

    `blocked` marks candidate bands a shot cannot use for other reasons —
    a stat call-out already occupying that part of the frame, for instance.
    """
    blocked = blocked or {}
    placements: dict[int, Placement] = {}

    for index, media in sorted(media_by_shot.items()):
        if not media or not media.exists():
            placements[index] = Placement(index, theme.CAPTION_Y, {})
            continue

        frames = _sample_frames(media, SAMPLES, ffmpeg, work / f"s{index:02d}")
        if not frames:
            placements[index] = Placement(index, theme.CAPTION_Y, {})
            continue

        energy = {
            c: sum(_band_energy(f, c) for f in frames) / len(frames)
            for c in CANDIDATES
        }
        allowed = [c for c in CANDIDATES if c not in blocked.get(index, set())]
        if not allowed:
            allowed = list(CANDIDATES)

        best = min(allowed, key=lambda c: energy[c])
        placements[index] = Placement(index, int(best * theme.HEIGHT), energy)

    return placements


def report(placements: dict[int, Placement]) -> str:
    lines = ["shot  caption   energy by band (lower is emptier)"]
    for index, p in sorted(placements.items()):
        bands = "  ".join(f"{c:.2f}:{p.energy.get(c, 0):5.1f}" for c in CANDIDATES)
        lines.append(f"{index + 1:4d}  y={p.y:<5d} {bands}   -> "
                     f"{p.chosen_fraction:.2f}")
    return "\n".join(lines)
