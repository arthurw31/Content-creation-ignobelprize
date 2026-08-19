#!/usr/bin/env python3
"""Generate the narration and one still per shot, then report what it cost.

OpenRouter serves no video model on this account, so footage comes from
generated stills that the composition animates with a camera move. Everything
else about the coherence system is unchanged: one locked style suffix, a
reference sheet per recurring subject carried into every shot it appears in,
and one fixed look across the video.

    python scripts/make_ai_stills.py --prize polyester-rats --dry-run
    python scripts/make_ai_stills.py --prize polyester-rats --budget 2

Files are cached by name. A re-run after a failure resumes instead of paying
twice, and deleting one still regenerates only that shot.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import config, render as ffrender, tts  # noqa: E402
from pipeline.aiclip import openrouter, style  # noqa: E402
from pipeline.aiclip.plan import describe, plan_shots  # noqa: E402
from pipeline.models import load_prize  # noqa: E402
from pipeline.script_writer import write_script  # noqa: E402

DATA = ROOT / "data" / "prizes.json"

# Measured on 2026-08-19: gemini-2.5-flash-image bills 1290 image tokens at
# $0.00003, so $0.0387 a still. Narration is a rounding error beside it.
IMAGE_USD = 0.0387
VOICE_USD = 0.03


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prize", required=True)
    parser.add_argument("--budget", type=float, default=2.0,
                        help="hard spending cap in USD")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--voice", default="openrouter",
                        choices=["openrouter", "elevenlabs", "openai", "none"])
    args = parser.parse_args()

    prize = load_prize(DATA, args.prize)
    script = write_script(prize)
    work = ROOT / "out" / f".ai-{prize.id}"
    voice_dir = ROOT / "out" / f".voice-{prize.id}"

    # Shots are planned against the estimated script first, only to count them
    # and price the run. They get replanned after the real narration lands.
    shots, subjects = plan_shots(prize, script)
    n_images = len(shots) + len(subjects)
    estimate = n_images * IMAGE_USD + VOICE_USD

    print(f"{prize.badge}")
    print(f"  {len(shots)} shots + {len(subjects)} reference sheets "
          f"= {n_images} images")
    print(f"  estimated spend  ${estimate:.2f}   budget ${args.budget:.2f}")

    if args.dry_run:
        print()
        print(describe(shots, subjects))
        print("\nnothing generated")
        return 0

    if estimate > args.budget:
        print(f"\nrefusing to start: ${estimate:.2f} exceeds the "
              f"${args.budget:.2f} budget")
        return 1

    spent = 0.0

    # 1. Narration first, so the shot cues land on the real spoken timings.
    if args.voice != "none":
        print("\nnarration ...")
        ffmpeg = ffrender.find_ffmpeg()
        segment_audio = tts.synthesize(script.segments, args.voice, voice_dir,
                                       ffmpeg)
        ffrender.retime_to_audio(script, segment_audio)
        print(f"  {script.duration:.1f}s")
        shots, subjects = plan_shots(prize, script)

    # 2. One reference sheet per recurring subject, generated once.
    print(f"\n{len(subjects)} reference sheets ...")
    for subject in subjects.values():
        path = work / "sheets" / f"{subject.key}.png"
        if path.exists():
            print(f"  {subject.key}: cached")
        else:
            _, cost = openrouter.generate_image(subject.sheet_prompt(), path)
            spent += cost
            print(f"  {subject.key}: ${cost:.4f}")
        subject.reference_image = str(path)

    # 3. One still per shot, anchored to its subjects' sheets.
    print(f"\n{len(shots)} stills ...")
    for shot in shots:
        path = work / "stills" / f"shot{shot.index:02d}.png"
        if path.exists():
            print(f"  {shot.index + 1:2d}: cached")
            continue
        reference = next(
            (subjects[k].reference_image for k in shot.subjects
             if k in subjects and subjects[k].reference_image), None)
        try:
            _, cost = openrouter.generate_image(shot.image_prompt(), path,
                                                reference_image=reference)
            spent += cost
            print(f"  {shot.index + 1:2d}: ${cost:.4f}  {shot.still[:58]}")
        except openrouter.OpenRouterError as exc:
            print(f"  {shot.index + 1:2d}: FAILED — {exc}")
        if spent > args.budget:
            print(f"\nstopping: spent ${spent:.2f}, over the budget")
            return 1

    print(f"\nspent ${spent:.4f}")
    print(f"stills in {work / 'stills'}")
    print("next: python scripts/make_hyperframes.py --prize "
          f"{prize.id} --voice {args.voice} --render")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
