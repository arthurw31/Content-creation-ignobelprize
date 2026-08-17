"""Build the burned-in caption track as an ASS subtitle file.

Word-by-word captions with the active word highlighted are the single
highest-impact retention device on vertical video, and libass renders them
far better than ffmpeg's drawtext can.
"""

from __future__ import annotations

from pathlib import Path

from . import theme
from .models import VideoScript, Word

MAX_WORDS_PER_CHUNK = 3
MAX_CHARS_PER_CHUNK = 26


def _ts(seconds: float) -> str:
    """ASS timestamps are H:MM:SS.cc with centisecond precision."""
    seconds = max(seconds, 0.0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _clean(text: str) -> str:
    """ASS treats braces as override blocks, so they cannot survive in text."""
    return text.replace("{", "(").replace("}", ")").replace("\\", "/")


def chunk_words(words: list[Word]) -> list[list[Word]]:
    """Group words into on-screen phrases, never spanning two segments."""
    chunks: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        crosses_segment = current and word.segment_index != current[0].segment_index
        too_long = len(" ".join(w.text for w in current + [word])) > MAX_CHARS_PER_CHUNK
        if crosses_segment or len(current) >= MAX_WORDS_PER_CHUNK or (current and too_long):
            chunks.append(current)
            current = []
        current.append(word)
    if current:
        chunks.append(current)
    return chunks


def build_ass(script: VideoScript, out_path: Path) -> Path:
    white = theme.ass_colour(theme.PAPER)
    outline = theme.ass_colour(theme.INK)
    shadow = theme.ass_colour(theme.INK, alpha=0x60)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {theme.WIDTH}
PlayResY: {theme.HEIGHT}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{theme.CAPTION_FONT_FAMILY},{theme.CAPTION_SIZE},{white},{white},{outline},{shadow},-1,0,0,0,100,100,2,0,1,{theme.CAPTION_OUTLINE},4,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines: list[str] = []
    for chunk in chunk_words(script.words):
        seg_index = chunk[0].segment_index
        role = script.segments[seg_index].role
        accent = theme.ass_colour(theme.ROLE_ACCENT.get(role, theme.ACCENT))

        for position, word in enumerate(chunk):
            rendered = []
            for other in chunk:
                text = _clean(other.text)
                if other is word:
                    rendered.append(f"{{\\c{accent}}}{text}{{\\c{white}}}")
                else:
                    rendered.append(text)
            body = " ".join(rendered)

            # A short scale-up on the first word of each phrase gives the
            # captions a beat without turning into constant motion.
            intro = ""
            if position == 0:
                intro = "{\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}"

            prefix = f"{{\\an5\\pos({theme.WIDTH // 2},{theme.CAPTION_Y})}}"
            lines.append(
                f"Dialogue: 0,{_ts(word.start)},{_ts(word.end)},Caption,,0,0,0,,"
                f"{prefix}{intro}{body}"
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return out_path
