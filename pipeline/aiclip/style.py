"""The style bible.

Coherence across a 30-second AI video is not won at assembly time — it is won
here, by making every shot inherit the same locked description. Six clips
generated from six freely-written prompts will look like six different videos,
no matter how good each one is.

Three rules the rest of the module enforces:

1. Every prompt gets STYLE_SUFFIX appended verbatim. Never paraphrase it per
   shot — paraphrasing is exactly what causes drift.
2. Shots are generated image-to-video, never text-to-video. The still fixes
   composition, palette and subject; the video model only animates it. This is
   the single biggest lever available.
3. A recurring subject carries a reference image into every shot that contains
   it, so "the scientist" is the same person in shot 1 and shot 6.

Residual drift is cleaned up by a single colour grade over all clips at
assembly time by GRADE in produce.py. Prompting gets you 80% of the way; the grade
hides most of the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- the locked look -------------------------------------------------------
# Edit this to rebrand the channel. Change it once, and every future video
# changes with it. Do not edit it per video.

STYLE_SUFFIX = (
    "shot on 16mm film, subtle grain, shallow depth of field, "
    "warm tungsten key light with deep amber shadows, muted desaturated palette "
    "of ochre, oxblood and off-white, 1970s scientific documentary aesthetic, "
    "static or very slow camera move, no text, no captions, no watermark, "
    "no on-screen writing"
)

NEGATIVE_PROMPT = (
    "text, captions, subtitles, watermark, logo, signature, distorted hands, "
    "extra limbs, deformed anatomy, modern smartphone, modern clothing, "
    "cartoon, 3d render, oversaturated, neon, lens flare"
)

# One seed for the whole video. Models that accept a seed will hold their look
# far more tightly across shots when it does not change between them.
SEED = 20160922

PALETTE = {
    "ochre": "#C8912F",
    "oxblood": "#5E1F18",
    "bone": "#EDE6D6",
    "ink": "#14100E",
}


@dataclass
class Subject:
    """A recurring person, animal or object that must look identical throughout.

    `reference_image` is filled in by produce.py once the character sheet has
    been generated, then passed into every shot that lists this subject.
    """

    key: str
    description: str
    reference_image: str | None = None

    def sheet_prompt(self) -> str:
        """Prompt for the reference still this subject is locked to."""
        return (
            f"Character reference portrait. {self.description}. "
            f"Neutral expression, centred, three-quarter view, plain background. "
            f"{STYLE_SUFFIX}"
        )


@dataclass
class Shot:
    """One generated clip."""

    index: int
    seconds: float  # how long it is on screen
    action: str  # what happens, written for a video model
    still: str  # what the opening frame looks like, written for an image model
    generate_seconds: float = 5.0  # how long we ask the model for
    subjects: list[str] = field(default_factory=list)
    role: str = "beat"  # hook | beat | twist | kicker
    start: float = 0.0  # when it appears, taken from the narration
    still_path: str | None = None
    clip_path: str | None = None

    def image_prompt(self) -> str:
        return f"{self.still}. {STYLE_SUFFIX}"

    def video_prompt(self) -> str:
        return f"{self.action}. {STYLE_SUFFIX}"


def default_subjects() -> dict[str, Subject]:
    """Subjects reused across the Ig Nobel channel.

    Keeping a shared cast means the channel itself looks consistent, not just
    each individual video.
    """
    return {
        "scientist": Subject(
            key="scientist",
            description=(
                "A man in his fifties in a white lab coat over a brown shirt, "
                "thick dark-rimmed glasses, receding grey hair, tired serious "
                "expression, 1970s researcher"
            ),
        ),
        "lab": Subject(
            key="lab",
            description=(
                "A cramped 1970s university laboratory, beige equipment, "
                "yellowing paper notes taped to cabinets, single desk lamp"
            ),
        ),
    }
