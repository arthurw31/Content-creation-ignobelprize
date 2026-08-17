"""Channel look and feel. Change this file to rebrand every future video."""

from __future__ import annotations

from pathlib import Path

# --- canvas -----------------------------------------------------------------
WIDTH, HEIGHT = 1080, 1920
FPS = 30

# Backgrounds are drawn oversized so the slow zoom never softens the image.
OVERSCAN = 1.5
BG_WIDTH = int(WIDTH * OVERSCAN)
BG_HEIGHT = int(HEIGHT * OVERSCAN)

# --- palette ----------------------------------------------------------------
INK = (10, 10, 12)
PAPER = (247, 246, 242)
ACCENT = (255, 199, 0)  # Ig Nobel yellow
ACCENT_ALT = (255, 92, 60)  # reserved for the twist

# Per-role background tint. The twist gets its own colour so the payoff
# lands visually a beat before it lands verbally.
ROLE_TINT = {
    "hook": (28, 26, 46),
    "beat": (16, 18, 24),
    "twist": (46, 20, 18),
    "kicker": (14, 22, 22),
}

ROLE_ACCENT = {
    "hook": ACCENT,
    "beat": ACCENT,
    "twist": ACCENT_ALT,
    "kicker": ACCENT,
}

# --- type -------------------------------------------------------------------
FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
]
FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
]

# libass looks fonts up by family name, not by path.
CAPTION_FONT_FAMILY = "DejaVu Sans"
CAPTION_SIZE = 92
CAPTION_OUTLINE = 6

# Captions sit slightly above centre: the lower third is where the platform
# stacks its own UI (username, caption, buttons).
CAPTION_Y = int(HEIGHT * 0.46)

SAFE_TOP = 260  # below the platform's top chrome
SAFE_BOTTOM = 420  # above the caption/description overlay


def pick_font(candidates: list[str]) -> str:
    for path in candidates:
        if Path(path).exists():
            return path
    raise FileNotFoundError(
        "No usable font found. Install DejaVu or Liberation fonts, or edit "
        "FONT_CANDIDATES_* in pipeline/theme.py."
    )


def font_bold() -> str:
    return pick_font(FONT_CANDIDATES_BOLD)


def font_regular() -> str:
    return pick_font(FONT_CANDIDATES_REGULAR)


def ass_colour(rgb: tuple[int, int, int], alpha: int = 0) -> str:
    """ASS wants &HAABBGGRR - alpha first, then reversed RGB."""
    r, g, b = rgb
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def ffmpeg_colour(rgb: tuple[int, int, int]) -> str:
    return "0x%02X%02X%02X" % rgb
