#!/usr/bin/env python3
"""Render one Ig Nobel video, or a whole batch.

    python scripts/make_video.py --prize polyester-rats
    python scripts/make_video.py --all --tts openai
    python scripts/make_video.py --list
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import publish, render  # noqa: E402
from pipeline.models import Prize, load_prize, load_prizes  # noqa: E402
from pipeline.script_writer import write_script  # noqa: E402

DATA = ROOT / "data" / "prizes.json"
OUT = ROOT / "out"


def render_one(prize: Prize, args: argparse.Namespace) -> None:
    started = time.time()
    script = write_script(prize)

    if args.dry_run:
        print(f"\n[{prize.id}] {prize.badge}")
        print(f"  estimated {script.duration:.1f}s, "
              f"{len(script.narration.split())} words")
        for seg in script.segments:
            print(f"  {seg.start:5.1f}s {seg.role:<7} {seg.text}")
        return

    music = Path(args.music) if args.music else None
    result = render.render(
        prize, script, OUT,
        tts_provider=args.tts,
        music=music,
        keep_work=args.keep_work,
    )
    meta = publish.build(prize, OUT)

    voice = "voiced" if result.voiced else "captions only (no TTS key)"
    print(f"[{prize.id}] {result.duration:5.1f}s  {voice}  "
          f"{time.time() - started:.0f}s to render")
    print(f"  video    {result.video.relative_to(ROOT)}")
    print(f"  script   {result.script_json.relative_to(ROOT)}")
    print(f"  metadata {meta.relative_to(ROOT)}")
    if prize.verified != "pubmed":
        print("  ! facts not source-verified. Check before publishing.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prize", help="prize id from data/prizes.json")
    parser.add_argument("--all", action="store_true", help="render every prize")
    parser.add_argument("--list", action="store_true", help="list prize ids")
    parser.add_argument("--tts", default="auto",
                        choices=["auto", "none", "openai", "elevenlabs"])
    parser.add_argument("--music", help="path to a background music file")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the timed script without rendering")
    parser.add_argument("--keep-work", action="store_true",
                        help="keep intermediate frames and clips")
    args = parser.parse_args()

    if args.list:
        for p in load_prizes(DATA):
            flag = " " if p.verified == "pubmed" else "?"
            print(f"{flag} {p.id:<28} {p.year}  {p.category}")
        print("\n? = facts not source-verified yet")
        return 0

    if args.all:
        for prize in load_prizes(DATA):
            render_one(prize, args)
        return 0

    if not args.prize:
        parser.error("pass --prize ID, or --all, or --list")

    render_one(load_prize(DATA, args.prize), args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
