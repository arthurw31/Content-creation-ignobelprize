"""Generate a HyperFrames composition from a prize script.

HyperFrames renders HTML in a headless browser, so a scene is markup and a
GSAP timeline rather than an FFmpeg filter graph. That is what makes real
motion graphics practical: a count-up, a lower third, a wipe are all just
elements being tweened.

Layer plan, one track each so the linter's no-overlap rule holds:

    0  scenes       one per narration segment; an AI clip when one exists,
                    otherwise a generated gradient card
    1  transitions  short wipes over the cuts
    2  graphics     stat call-outs and the twist card, one full-length clip
    3  captions     word-by-word, one full-length clip
    4  progress     the bar along the bottom

Everything is animated with tweens, never `tl.call()`. HyperFrames reported
that a `tl.call()` side effect is "not seek-safe" and disabled its static-frame
dedup optimisation — tweens keep the render deterministic and faster.
"""

from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .captions import chunk_words
from .models import Prize, VideoScript
from . import theme

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "hyperframes"

ACCENT = "#ffc700"
ACCENT_ALT = "#ff5c3c"
CREAM = "#f7f6f2"

ROLE_BG = {
    "hook": "radial-gradient(circle at 50% 38%, #2b2846 0%, #101018 72%)",
    "beat": "radial-gradient(circle at 42% 45%, #1b1f28 0%, #0b0c10 72%)",
    "twist": "radial-gradient(circle at 50% 45%, #7a2418 0%, #2b0f0c 70%)",
    "kicker": "radial-gradient(circle at 55% 50%, #162624 0%, #0b1211 72%)",
}

@dataclass
class _Scene:
    """A scene on track 0: either one shot, or one narration segment."""

    index: int
    role: str
    start: float
    duration: float


ROLE_LABEL = {"hook": "", "beat": "THE SETUP", "twist": "THE TWIST",
              "kicker": "AND YET"}

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "twenty": 20, "thirty": 30, "fifty": 50, "hundred": 100,
}


def find_stat(text: str) -> tuple[int, str] | None:
    """Pull a number and its noun out of a beat, for a count-up call-out.

    Only the first one: two competing numbers on screen read as a chart, not
    as a fact.
    """
    digits = re.search(r"\b(\d[\d,]*)\b\s+([a-z]+)", text.lower())
    if digits:
        return int(digits.group(1).replace(",", "")), digits.group(2)
    hits = []
    for word, value in NUMBER_WORDS.items():
        match = re.search(rf"\b{word}\b\s+([a-z]+)", text.lower())
        if match:
            hits.append((match.start(), value, match.group(1)))
    if hits:
        _, value, noun = min(hits)  # the one stated first, not the first key
        return value, noun
    return None


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def collect_clips(prize: Prize, count: int) -> list[str | None]:
    """Copy any generated AI clips into assets/ and return their paths."""
    source = ROOT / "out" / f".ai-{prize.id}" / "graded"
    assets = PROJECT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    found: list[str | None] = []
    for i in range(count):
        clip = source / f"shot{i:02d}.mp4"
        if clip.exists():
            dst = assets / f"{prize.id}-shot{i:02d}.mp4"
            shutil.copy2(clip, dst)
            found.append(f"assets/{dst.name}")
        else:
            found.append(None)
    return found


def build(prize: Prize, script: VideoScript, out_path: Path | None = None,
          voice_track: Path | None = None, shots: list | None = None) -> Path:
    out_path = out_path or PROJECT / "index.html"
    duration = round(script.duration, 2)
    segments = script.segments

    # Scenes come from the shot list when there is one, so the picture cuts on
    # the words it illustrates. Without a shot list each narration segment is
    # its own scene, which is far less illustrated but needs no generation.
    if shots:
        scene_specs = [{"start": sh.start, "role": sh.role} for sh in shots]
    else:
        scene_specs = [{"start": sg.start, "role": sg.role} for sg in segments]
    clips = collect_clips(prize, len(scene_specs))

    # The voiceover is one element spanning the whole composition. Segment
    # timings were already re-fitted to this exact file before we got here,
    # so it lines up with the captions by construction.
    voice_html = ""
    if voice_track and voice_track.exists():
        assets = PROJECT / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        dst = assets / f"{prize.id}-voice{voice_track.suffix}"
        shutil.copy2(voice_track, dst)
        voice_html = (
            f'<audio class="clip" id="voice" src="assets/{dst.name}" '
            f'data-start="0" data-duration="{duration}" data-track-index="5" '
            f'data-volume="1"></audio>'
        )

    scenes: list[str] = []
    tweens: list[str] = []
    graphics: list[str] = []
    transitions: list[str] = []

    # Scene boundaries are snapped to the same 2dp the markup is written at,
    # and each scene's length is derived from the next one's start. Rounding
    # start and duration independently leaves 10ms gaps or overlaps, and the
    # linter rejects overlapping clips on one track.
    marks = [round(spec["start"], 2) for spec in scene_specs] + [duration]
    span = {i: round(marks[i + 1] - marks[i], 2)
            for i in range(len(scene_specs))}

    # --- scenes -------------------------------------------------------------
    previous_role = None
    for i, spec in enumerate(scene_specs):
        seg = _Scene(index=i, role=spec["role"], start=marks[i],
                     duration=span[i])
        sid = f"sc{seg.index}"
        clip = clips[seg.index]
        if clip:
            media = (f'<video id="{sid}v" class="media" src="{clip}" muted '
                     f'playsinline></video>')
        else:
            media = f'<div id="{sid}v" class="media gradient"></div>'

        label = ROLE_LABEL.get(seg.role, "") if seg.role != previous_role else ""
        previous_role = seg.role
        label_html = (f'<div class="role-label" id="{sid}l">{esc(label)}</div>'
                      if label else "")

        scenes.append(
            f'<div class="clip scene" id="{sid}" data-start="{marks[seg.index]:.2f}" '
            f'data-duration="{span[seg.index]:.2f}" data-track-index="0" '
            f'style="--bg:{ROLE_BG.get(seg.role, ROLE_BG["beat"])}">'
            f'{media}{label_html}</div>'
        )

        # A slow push-in on every scene, so nothing ever sits perfectly still.
        tweens.append(
            f'tl.fromTo(q("{sid}v"), {{scale:1.0}}, '
            f'{{scale:1.12, duration:{span[seg.index]:.2f}, ease:"none"}}, '
            f'{marks[seg.index]:.2f});'
        )
        if label:
            tweens.append(
                f'tl.fromTo(q("{sid}l"), {{opacity:0, x:-30}}, '
                f'{{opacity:1, x:0, duration:0.45, ease:"power3.out"}}, '
                f'{seg.start + 0.1:.2f});'
            )

    # --- transitions --------------------------------------------------------
    for i in range(1, len(scene_specs)):
        seg = _Scene(index=i, role=scene_specs[i]["role"], start=marks[i],
                     duration=span[i])
        tid = f"wp{seg.index}"
        start = max(marks[seg.index] - 0.18, 0)
        colour = ACCENT_ALT if seg.role == "twist" else ACCENT
        transitions.append(
            f'<div class="clip wipe" id="{tid}" data-start="{start:.2f}" '
            f'data-duration="0.36" data-track-index="1" '
            f'style="background:{colour}"></div>'
        )
        tweens.append(
            f'tl.fromTo(q("{tid}"), {{xPercent:-100}}, '
            f'{{xPercent:0, duration:0.18, ease:"power2.in"}}, {start:.2f});'
        )
        tweens.append(
            f'tl.to(q("{tid}"), {{xPercent:100, duration:0.18, '
            f'ease:"power2.out"}}, {start + 0.18:.2f});'
        )

    # --- stat call-outs -----------------------------------------------------
    # This is the "motion graphics for the concepts and the numbers" layer:
    # when a beat states a figure, the figure counts up on screen.
    for seg in segments:
        if seg.role not in {"hook", "beat"}:
            continue
        stat = find_stat(seg.text)
        if not stat:
            continue
        value, noun = stat
        gid = f"st{seg.index}"
        graphics.append(
            f'<div class="stat" id="{gid}">'
            f'<div class="stat-number" id="{gid}n">0</div>'
            f'<div class="stat-label">{esc(noun.upper())}</div>'
            f'<div class="bar-track"><div class="bar-fill" id="{gid}b"></div></div>'
            f'</div>'
        )
        appear = marks[seg.index] + 0.25
        tweens.append(
            f'tl.fromTo(q("{gid}"), {{opacity:0, y:40}}, '
            f'{{opacity:1, y:0, duration:0.4, ease:"power3.out"}}, {appear:.2f});'
        )
        tweens.append(
            f'tl.to({{v:0}}, {{v:{value}, duration:0.9, ease:"power2.out", '
            f'onUpdate:function(){{q("{gid}n").textContent = '
            f'Math.round(this.targets()[0].v);}}}}, {appear + 0.1:.2f});'
        )
        tweens.append(
            f'tl.fromTo(q("{gid}b"), {{width:"0%"}}, '
            f'{{width:"100%", duration:1.1, ease:"power2.out"}}, {appear + 0.1:.2f});'
        )
        tweens.append(
            f'tl.to(q("{gid}"), {{opacity:0, duration:0.3}}, '
            f'{max(marks[seg.index] + span[seg.index] - 0.45, appear + 0.6):.2f});'
        )

    # --- captions -----------------------------------------------------------
    caption_html: list[str] = []
    for ci, chunk in enumerate(chunk_words(script.words)):
        role = segments[chunk[0].segment_index].role
        colour = ACCENT_ALT if role == "twist" else ACCENT
        words = "".join(
            f'<span id="cw{ci}_{wi}">{esc(w.text)}</span> ' for wi, w in enumerate(chunk)
        )
        caption_html.append(f'<div class="cap" id="cap{ci}">{words}</div>')

        start, end = chunk[0].start, chunk[-1].end
        tweens.append(
            f'tl.fromTo(q("cap{ci}"), {{opacity:0, scale:0.9}}, '
            f'{{opacity:1, scale:1, duration:0.12, ease:"back.out(2)"}}, {start:.2f});'
        )
        tweens.append(
            f'tl.to(q("cap{ci}"), {{opacity:0, duration:0.08}}, '
            f'{max(end - 0.10, start + 0.05):.2f});'
        )
        for wi, word in enumerate(chunk):
            tweens.append(
                f'tl.to(q("cw{ci}_{wi}"), {{color:"{colour}", duration:0.05}}, '
                f'{word.start:.2f});'
            )
            tweens.append(
                f'tl.to(q("cw{ci}_{wi}"), {{color:"{CREAM}", duration:0.05}}, '
                f'{word.end:.2f});'
            )

    tweens.append(
        f'tl.fromTo(q("progfill"), {{width:"0%"}}, '
        f'{{width:"100%", duration:{duration}, ease:"none"}}, 0);'
    )

    body = f'''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>{esc(prize.badge)}</title>
    <script src="node_modules/gsap/dist/gsap.min.js"></script>
    <style>
      html, body {{
        margin:0; padding:0; width:{theme.WIDTH}px; height:{theme.HEIGHT}px;
        overflow:hidden; background:#08080a;
        font-family:"DejaVu Sans", Arial, Helvetica, sans-serif;
      }}
      #main-composition {{ position:relative; width:{theme.WIDTH}px; height:{theme.HEIGHT}px; overflow:hidden; }}
      .scene {{ position:absolute; inset:0; overflow:hidden; }}
      .media {{
        position:absolute; top:50%; left:50%; width:112%; height:112%;
        object-fit:cover; transform:translate(-50%,-50%); will-change:transform;
      }}
      .gradient {{ background:var(--bg); }}
      .vignette {{
        position:absolute; inset:0;
        background:radial-gradient(ellipse at 50% 40%, rgba(0,0,0,0) 32%, rgba(0,0,0,.78) 100%);
      }}
      .badge {{
        position:absolute; top:120px; left:70px; z-index:6;
        background:{ACCENT}; color:#14100e; font-weight:700; font-size:32px;
        letter-spacing:2px; padding:16px 26px; border-radius:14px;
      }}
      .role-label {{
        position:absolute; left:70px; top:320px;
        color:{ACCENT}; font-size:30px; letter-spacing:4px;
        border-bottom:3px solid {ACCENT}; padding-bottom:12px;
      }}
      .wipe {{ position:absolute; inset:0; z-index:8; }}
      .stat {{ position:absolute; left:70px; top:400px; width:940px; opacity:0; }}
      .stat-number {{ color:{ACCENT}; font-size:200px; font-weight:700; line-height:1.06; }}
      .stat-label {{ color:{CREAM}; font-size:34px; font-weight:700; letter-spacing:4px; margin:34px 0 26px; }}
      .bar-track {{ height:16px; background:rgba(255,255,255,.16); border-radius:8px; }}
      .bar-fill {{ height:100%; width:0%; background:{ACCENT}; border-radius:8px; }}
      .caption-layer {{ position:absolute; inset:0; z-index:7; }}
      .cap {{
        position:absolute; left:80px; right:80px; top:{theme.CAPTION_Y}px;
        transform:translateY(-50%); text-align:center; opacity:0;
        color:{CREAM}; font-size:86px; font-weight:700; line-height:1.12;
        text-shadow:0 6px 22px rgba(0,0,0,.9);
      }}
      .progress {{ position:absolute; left:0; right:0; bottom:0; height:10px;
        background:rgba(255,255,255,.14); z-index:9; }}
      .progress-fill {{ height:100%; width:0%; background:{ACCENT}; }}
    </style>
  </head>
  <body>
    <div id="main-composition" data-composition-id="ignobel" data-start="0"
         data-width="{theme.WIDTH}" data-height="{theme.HEIGHT}"
         data-duration="{duration}">

      {"".join(scenes)}
      {"".join(transitions)}

      <div class="clip graphics-layer" id="gfx" data-start="0"
           data-duration="{duration}" data-track-index="2">
        <div class="vignette"></div>
        <div class="badge">{esc(prize.badge)}</div>
        {"".join(graphics)}
      </div>

      <div class="clip caption-layer" id="caps" data-start="0"
           data-duration="{duration}" data-track-index="3">
        {"".join(caption_html)}
      </div>

      <div class="clip progress" id="prog" data-start="0"
           data-duration="{duration}" data-track-index="4">
        <div class="progress-fill" id="progfill"></div>
      </div>

      {voice_html}
    </div>

    <script>
      (function () {{
        const q = (id) => document.getElementById(id);
        window.__timelines = window.__timelines || {{}};
        const tl = gsap.timeline({{paused:true}});
        window.__timelines["ignobel"] = tl;
        {chr(10) + "        ".join(tweens)}
      }})();
    </script>
  </body>
</html>
'''
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")
    return out_path
