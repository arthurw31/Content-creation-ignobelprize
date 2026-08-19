"""Turn a written script into a shot list for the generative models.

Shots are cut against the narration, not against the paragraph. Each shot
declares a `cue` — the words it illustrates — and its start is taken from
when those words are actually spoken. So when the narrator says "tiny
polyester pants", the frame showing tiny polyester pants is already on
screen.

That is the difference between a video with pictures in it and a video that
is *illustrated*. It costs more shots: roughly one every three seconds
instead of one per paragraph.

Shot text is written in two registers on purpose:

    still  -> for the image model. A frozen frame. Composition and subject.
    action -> for the video model. What moves, and how little.

"How little" matters. Generative video degrades in proportion to how much you
ask it to move. Slow push-ins and small gestures hold; anything acrobatic
turns to soup.
"""

from __future__ import annotations

import re

from .style import Shot, Subject, default_subjects
from ..models import Prize, VideoScript

# Current video models hold together for about five seconds. Past that they
# drift and warp. Shots this short are also cheaper and cut better.
MAX_SHOT_SECONDS = 5.0
TARGET_SHOT_SECONDS = 3.0
MIN_SHOT_SECONDS = 1.4

# Hand-written shot lists, keyed by prize. `cue` is the phrase in the
# narration that the shot illustrates; timing comes from when it is spoken.
HANDWRITTEN: dict[str, list[dict]] = {
    # "asset" is a stable name for the generated media, so the edit can be
    # reordered without regenerating anything: files live under
    # out/.ai-<prize>/{stills,graded}/<asset>.{png,mp4}, not under a position.
    # "cue" is the phrase the shot illustrates; its start comes from when
    # those words are actually spoken.
    "polyester-rats": [
        # The most absurd image in the whole story is the first frame. Opening
        # on an establishing shot wastes the only second that decides whether
        # anyone stays.
        {"cue": "Tiny polyester trousers", "asset": "trousers",
         "still": "Extreme close-up of tiny tailored trousers of shiny "
                  "synthetic fabric on the hind legs of a white laboratory rat",
         "action": "The rat shifts its weight. Very slow push-in",
         "subjects": []},
        {"cue": "seventy-five rats", "asset": "cages-rows",
         "still": "Overhead view of many wire cages in rows on a laboratory "
                  "rack, a white rat in each",
         "action": "The camera rises slowly over the rows of cages",
         "subjects": ["lab"]},
        {"cue": "destroyed their sex life", "asset": "still-rat",
         "still": "A single white rat in tiny synthetic trousers sitting "
                  "motionless in the corner of a tank, cold light",
         "action": "The rat stays completely still. The camera creeps in",
         "subjects": []},
        {"cue": "tailored them himself", "asset": "swatches",
         "still": "Four fabric swatches side by side on a dark bench, raking "
                  "side light showing the weave",
         "action": "The camera pushes in slowly across the swatches",
         "subjects": []},
        {"cue": "Five groups", "asset": "five-tanks",
         "still": "Five glass tanks in a row on a bench, each with a "
                  "handwritten label card",
         "action": "The camera drifts along the row, left to right",
         "subjects": ["lab"]},
        {"cue": "left naked", "asset": "cage",
         "still": "A white laboratory rat inside a wire cage on a cluttered "
                  "1970s laboratory bench, looking out through the bars",
         "action": "The rat sniffs at the bars and turns its head",
         "subjects": ["lab"]},
        {"cue": "waited a full year", "asset": "calendar",
         "still": "A wall calendar in a laboratory, months crossed off in "
                  "pen, dust drifting in a hard side light",
         "action": "Dust drifts through the light. The camera holds still",
         "subjects": ["lab"]},
        {"cue": "counting how often", "asset": "notebook",
         "still": "Close-up of a hand adding tally marks to a column in a "
                  "paper notebook",
         "action": "The hand adds two marks, then pauses",
         "subjects": ["scientist"]},
        {"cue": "Cotton and wool", "asset": "two-rats",
         "still": "Two lively white rats moving around a clean tank with "
                  "wood shavings, warm soft light",
         "action": "The rats move about, sniffing and turning",
         "subjects": ["lab"]},
        {"cue": "almost completely stopped", "asset": "glow",
         "still": "A rat seen through the glass of a tank, lit from one "
                  "side, faint blue electrical glow on the glass",
         "action": "The glow pulses faintly. The rat does not move",
         "subjects": []},
        {"cue": "generating static electricity", "asset": "fibres",
         "still": "Macro shot of synthetic fabric fibres lit from the side, "
                  "tiny blue static sparks arcing between the threads",
         "action": "Sparks flicker across the fibres. The camera pushes in",
         "subjects": []},
        {"cue": "Take the trousers off", "asset": "free-rat",
         "still": "A white rat with no trousers, grooming itself in a clean "
                  "tank, warm light, shot from slightly below",
         "action": "The rat grooms its face, then settles",
         "subjects": ["lab"]},
        {"cue": "Ig Nobel Prize", "asset": "journal",
         "still": "An open academic journal page on a desk under a lamp, "
                  "dense typeset columns, a diagram in the margin",
         "action": "The camera drifts down the printed column",
         "subjects": []},
    ],
}


def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def find_cue(script: VideoScript, cue: str) -> float | None:
    """Start time of the first place `cue` is spoken, or None."""
    target = [_norm(w) for w in cue.split() if _norm(w)]
    if not target:
        return None
    words = [_norm(w.text) for w in script.words]
    for i in range(len(words) - len(target) + 1):
        if words[i:i + len(target)] == target:
            return script.words[i].start
    return None


def _role_at(script: VideoScript, when: float) -> str:
    for seg in script.segments:
        if seg.start <= when < seg.end:
            return seg.role
    return script.segments[-1].role


def plan_shots(prize: Prize, script: VideoScript) -> tuple[list[Shot], dict[str, Subject]]:
    """Build the shot list, cut against the narration."""
    subjects = default_subjects()
    specs = HANDWRITTEN.get(prize.id)
    total = script.duration

    if specs:
        placed: list[tuple[float, dict]] = []
        for spec in specs:
            start = find_cue(script, spec["cue"])
            if start is None:
                print(f"  ! cue not found in narration: {spec['cue']!r}")
                continue
            placed.append((start, spec))
        placed.sort(key=lambda item: item[0])
        # First shot always opens the video, whatever its cue's timing.
        if placed:
            placed[0] = (0.0, placed[0][1])
    else:
        placed = [(start, spec) for start, spec in _generic_shots(prize, script)]

    shots: list[Shot] = []
    for i, (start, spec) in enumerate(placed):
        end = placed[i + 1][0] if i + 1 < len(placed) else total
        seconds = round(max(end - start, MIN_SHOT_SECONDS), 2)
        shots.append(Shot(
            index=len(shots),
            seconds=seconds,
            generate_seconds=round(min(seconds, MAX_SHOT_SECONDS), 2),
            still=spec["still"],
            action=spec["action"],
            subjects=spec.get("subjects", []),
            role=_role_at(script, start),
            asset=spec.get("asset"),
        ))
        shots[-1].start = start

    needed = {key for shot in shots for key in shot.subjects}
    return shots, {k: v for k, v in subjects.items() if k in needed}


def _generic_shots(prize: Prize, script: VideoScript) -> list[tuple[float, dict]]:
    """Fallback: slice each segment into roughly TARGET_SHOT_SECONDS pieces.

    Deliberately conservative descriptions — a documentary insert rather than
    an attempt to literally illustrate the sentence. Literal illustration by a
    generic template is what produces the uncanny, obviously-generated look;
    literal illustration is worth doing by hand, in HANDWRITTEN.
    """
    setting = f"{prize.category.lower()} research, 1970s university laboratory"
    out: list[tuple[float, dict]] = []
    for seg in script.segments:
        pieces = max(int(round(seg.duration / TARGET_SHOT_SECONDS)), 1)
        step = seg.duration / pieces
        for p in range(pieces):
            if seg.role == "twist":
                still = (f"Extreme close-up detail relating to {setting}, "
                         f"dramatic side light, dark background")
                action = "The camera pushes in very slowly on the detail"
                used = []
            elif seg.role == "hook":
                still = (f"Wide establishing shot of a {setting}, one figure "
                         f"at work in the middle distance")
                action = "The camera holds nearly still, drifting forward"
                used = ["lab"]
            else:
                still = (f"Documentary insert shot of {setting}, equipment and "
                         f"paperwork in frame")
                action = "Minimal movement. A slow, steady camera drift"
                used = ["lab", "scientist"]
            out.append((seg.start + p * step,
                        {"still": still, "action": action, "subjects": used}))
    return out


def describe(shots: list[Shot], subjects: dict[str, Subject]) -> str:
    generated = sum(s.generate_seconds for s in shots)
    lines = [f"{len(shots)} shots, {sum(s.seconds for s in shots):.1f}s on screen, "
             f"{generated:.1f}s generated",
             f"average shot length {sum(s.seconds for s in shots) / len(shots):.1f}s"]
    if subjects:
        lines.append(f"reference sheets: {', '.join(subjects)}")
    lines.append("")
    for shot in shots:
        refs = f" [{', '.join(shot.subjects)}]" if shot.subjects else ""
        lines.append(f"  {shot.index + 1:2d}. {shot.start:5.1f}s +{shot.seconds:4.1f}s "
                     f"{shot.role}{refs}")
        lines.append(f"      {shot.still[:96]}")
    return "\n".join(lines)
