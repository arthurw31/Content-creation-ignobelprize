"""Turn a written script into a shot list for the generative models.

One shot per script segment, so the visuals cut exactly on the narration beats
that already exist. A 30-second video lands at 6 shots of about 5 seconds,
which is also the sweet spot for current video models — asking for longer
single clips is where they start to drift and warp.

Shot text is written in two registers on purpose:

    still  -> for the image model. A frozen frame. Composition and subject.
    action -> for the video model. What moves, and how little.

"How little" matters. Generative video degrades in proportion to how much you
ask it to move. Slow push-ins and small gestures hold; anything acrobatic
turns to soup.
"""

from __future__ import annotations

from .style import Shot, Subject, default_subjects
from ..models import Prize, VideoScript

# Current video models hold together for about five seconds. Past that they
# drift and warp. Longer beats are generated at this length and retimed to
# fill the segment during grading, which is invisible on slow documentary
# movement and costs less than generating the full length.
MAX_SHOT_SECONDS = 5.0

# Hand-written shot lists for prizes where the generic planner is too vague.
# Worth doing for anything you expect to perform: the difference between a
# generic prompt and a specific one is most of the quality.
HANDWRITTEN: dict[str, list[dict]] = {
    "polyester-rats": [
        {
            "still": "Close-up of a laboratory rat in a glass tank, wearing tiny "
                     "tailored trousers made of shiny synthetic fabric, seen from "
                     "the side, clinical light from above",
            "action": "The rat shifts its weight slightly and turns its head "
                      "toward camera. The camera pushes in very slowly",
            "subjects": ["lab"],
        },
        {
            "still": "Overhead view of five separate glass tanks arranged in a "
                     "row on a laboratory bench, each labelled with a "
                     "handwritten card, one rat in each",
            "action": "The camera drifts slowly along the row of tanks, left to "
                      "right, holding steady focus",
            "subjects": ["lab"],
        },
        {
            "still": "A researcher in a white lab coat writing in a paper "
                     "notebook beside the tanks, hands and notebook in focus, "
                     "face out of frame",
            "action": "The hand writes a line, then sets the pen down. Almost "
                      "no camera movement",
            "subjects": ["scientist", "lab"],
        },
        {
            "still": "A wall calendar in a laboratory with months crossed off in "
                     "pen, harsh side light, dust in the air",
            "action": "The camera holds still on the calendar. Dust drifts "
                      "slowly through the light",
            "subjects": ["lab"],
        },
        {
            "still": "Extreme close-up of synthetic fabric fibres lit from the "
                     "side, tiny sparks of static electricity arcing between "
                     "the threads, dark background",
            "action": "Small static sparks flicker across the fabric surface. "
                      "The camera pushes in very slowly",
            "subjects": [],
        },
        {
            "still": "A rat sitting calmly with no trousers on, in a clean glass "
                     "tank, soft warm light, shot from slightly below",
            "action": "The rat grooms itself briefly and settles. The camera "
                      "holds still",
            "subjects": ["lab"],
        },
    ],
}


def plan_shots(prize: Prize, script: VideoScript) -> tuple[list[Shot], dict[str, Subject]]:
    """Build the shot list, one shot per narration segment."""
    subjects = default_subjects()
    handwritten = HANDWRITTEN.get(prize.id)

    shots: list[Shot] = []
    for i, segment in enumerate(script.segments):
        if handwritten and i < len(handwritten):
            spec = handwritten[i]
            still, action = spec["still"], spec["action"]
            used = spec.get("subjects", [])
        else:
            still, action, used = _generic(prize, segment.text, segment.role)

        shots.append(Shot(
            index=i,
            seconds=round(segment.duration, 2),
            generate_seconds=round(min(segment.duration, MAX_SHOT_SECONDS), 2),
            still=still,
            action=action,
            subjects=used,
            role=segment.role,
        ))

    needed = {key for shot in shots for key in shot.subjects}
    return shots, {k: v for k, v in subjects.items() if k in needed}


def _generic(prize: Prize, text: str, role: str) -> tuple[str, str, list[str]]:
    """Fallback when a prize has no hand-written shots.

    Deliberately conservative: a documentary insert rather than an attempt to
    literally illustrate the sentence. Literal illustration is what produces
    the uncanny, obviously-generated look.
    """
    setting = f"{prize.category.lower()} research, 1970s university laboratory"
    if role == "twist":
        still = (f"Extreme close-up detail relating to {setting}, dramatic side "
                 f"light, dark background, single subject isolated")
        action = "The camera pushes in very slowly on the detail"
        return still, action, []
    if role == "hook":
        still = (f"Wide establishing shot of a {setting}, one figure at work in "
                 f"the middle distance")
        action = "The camera holds nearly still. Slight drift forward"
        return still, action, ["lab"]
    still = (f"Documentary insert shot of {setting}, equipment and paperwork in "
             f"frame, natural composition")
    action = "Minimal movement. A slow, steady camera drift"
    return still, action, ["lab", "scientist"]


def describe(shots: list[Shot], subjects: dict[str, Subject]) -> str:
    generated = sum(s.generate_seconds for s in shots)
    lines = [f"{len(shots)} shots, {sum(s.seconds for s in shots):.1f}s on screen, "
             f"{generated:.1f}s generated"]
    if subjects:
        lines.append(f"reference sheets to generate: {', '.join(subjects)}")
    lines.append("")
    for shot in shots:
        refs = f" [refs: {', '.join(shot.subjects)}]" if shot.subjects else ""
        retime = ("" if abs(shot.generate_seconds - shot.seconds) < 0.05
                  else f" (generate {shot.generate_seconds:.1f}s, retimed)")
        lines.append(f"  {shot.index + 1}. {shot.seconds:4.1f}s  {shot.role}{refs}{retime}")
        lines.append(f"      still  : {shot.still}")
        lines.append(f"      action : {shot.action}")
    return "\n".join(lines)
