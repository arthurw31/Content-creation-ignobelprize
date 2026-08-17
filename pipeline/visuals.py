"""Generate the background card for each segment with Pillow.

Deliberately typographic rather than photographic: no stock footage, no
generated imagery, so nothing in the output carries a licence question and
the whole render works offline.
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from . import theme
from .models import Segment


def _radial_glow(size: tuple[int, int], centre: tuple[float, float],
                 radius: float, colour: tuple[int, int, int],
                 strength: float) -> Image.Image:
    """A soft coloured glow, built small and upscaled so it stays cheap."""
    w, h = size
    small = (max(w // 8, 1), max(h // 8, 1))
    layer = Image.new("L", small, 0)
    draw = ImageDraw.Draw(layer)
    cx, cy = centre[0] / 8, centre[1] / 8
    r = radius / 8
    steps = 24
    for i in range(steps, 0, -1):
        frac = i / steps
        value = int(255 * strength * (1 - frac) ** 2)
        draw.ellipse(
            [cx - r * frac, cy - r * frac, cx + r * frac, cy + r * frac],
            fill=value,
        )
    layer = layer.filter(ImageFilter.GaussianBlur(radius=6))
    layer = layer.resize(size, Image.BICUBIC)

    glow = Image.new("RGB", size, colour)
    out = Image.new("RGB", size, (0, 0, 0))
    out.paste(glow, (0, 0), layer)
    return out


def _grain(size: tuple[int, int], amount: int, seed: int) -> Image.Image:
    """Film grain, so large flat areas don't band after H.264 compression."""
    rng = random.Random(seed)
    w, h = size
    small = (w // 3, h // 3)
    noise = Image.new("L", small)
    noise.putdata([rng.randint(0, amount) for _ in range(small[0] * small[1])])
    return noise.resize(size, Image.BICUBIC).convert("RGB")


def render_card(segment: Segment, badge: str, total_segments: int,
                out_path: Path, seed: int = 0) -> Path:
    """Draw one background card. Captions are burned in later by libass."""
    size = (theme.BG_WIDTH, theme.BG_HEIGHT)
    tint = theme.ROLE_TINT.get(segment.role, theme.ROLE_TINT["beat"])
    accent = theme.ROLE_ACCENT.get(segment.role, theme.ACCENT)

    base = Image.new("RGB", size, tint)

    # Two offset glows give the card depth and stop it reading as flat colour.
    rng = random.Random(seed + segment.index * 977)
    for _ in range(2):
        centre = (
            rng.uniform(0.15, 0.85) * size[0],
            rng.uniform(0.12, 0.6) * size[1],
        )
        glow = _radial_glow(size, centre, rng.uniform(0.5, 0.9) * size[0],
                            accent, rng.uniform(0.10, 0.20))
        base = _screen(base, glow)

    base = _screen(base, _grain(size, 10, seed + segment.index))

    # Everything else is drawn on a transparent layer and composited once.
    # Drawing straight onto an RGB image silently discards the alpha channel,
    # which turns a faint background numeral into a solid slab of colour.
    base = base.convert("RGBA")
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    bold = theme.font_bold()
    regular = theme.font_regular()

    scale = theme.OVERSCAN
    margin = int(90 * scale)

    # --- top badge ----------------------------------------------------------
    badge_font = ImageFont.truetype(bold, int(34 * scale))
    badge_w = draw.textlength(badge, font=badge_font)
    pad_x, pad_y = int(28 * scale), int(18 * scale)
    bx0, by0 = margin, int(theme.SAFE_TOP * scale * 0.55)
    bx1 = bx0 + badge_w + pad_x * 2
    by1 = by0 + int(34 * scale) + pad_y * 2
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=int(14 * scale),
                           fill=(*accent, 235))
    draw.text((bx0 + pad_x, by0 + pad_y), badge, font=badge_font,
              fill=(*theme.INK, 255))

    # --- oversized watermark digit -----------------------------------------
    # A huge, very low contrast numeral gives the frame a focal anchor behind
    # the captions without competing with them.
    ghost_font = ImageFont.truetype(bold, int(680 * scale))
    ghost = str(segment.index + 1)
    gw = draw.textlength(ghost, font=ghost_font)
    draw.text((size[0] - gw - margin // 2, int(size[1] * 0.56)), ghost,
              font=ghost_font, fill=(*accent, 34))

    # --- role label ---------------------------------------------------------
    label = {
        "hook": "",
        "beat": "THE SETUP",
        "twist": "THE TWIST",
        "kicker": "AND YET",
    }.get(segment.role, "")
    if label:
        label_font = ImageFont.truetype(regular, int(30 * scale))
        ly = int(size[1] * 0.30)
        draw.text((margin, ly), label, font=label_font, fill=(*accent, 190))
        lw = draw.textlength(label, font=label_font)
        draw.line([(margin, ly + int(46 * scale)),
                   (margin + lw, ly + int(46 * scale))],
                  fill=(*accent, 190), width=max(int(3 * scale), 2))

    # --- segment dots -------------------------------------------------------
    dot_r = int(7 * scale)
    gap = int(26 * scale)
    dy = size[1] - int(theme.SAFE_BOTTOM * scale * 0.45)
    for i in range(total_segments):
        dx = margin + i * gap
        filled = i <= segment.index
        draw.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r],
                     fill=(*accent, 255) if filled else (*accent, 60))

    base = Image.alpha_composite(base, overlay).convert("RGB")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base.save(out_path, quality=95)
    return out_path


def _screen(a: Image.Image, b: Image.Image) -> Image.Image:
    """Screen blend: lightens without the clipping plain addition gives."""
    return ImageChops.screen(a, b)
