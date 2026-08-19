#!/usr/bin/env python3
"""Animate each generated still into a clip, then grade and trim it.

Image-to-video, never text-to-video: the still already fixes subject,
composition and palette, so the model only has to move it. That is what keeps
thirteen shots looking like one film.

    python scripts/make_ai_clips.py --prize polyester-rats --dry-run
    python scripts/make_ai_clips.py --prize polyester-rats --budget 3

Jobs are submitted together and polled as a batch, because each one takes
about ninety seconds and running them in series would take twenty minutes.
Finished clips are cached, so a re-run resumes instead of paying twice.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import config, render as ffrender, tts  # noqa: E402
from pipeline.aiclip import openrouter, style  # noqa: E402
from pipeline.aiclip.plan import plan_shots  # noqa: E402
from pipeline.models import load_prize  # noqa: E402
from pipeline.script_writer import write_script  # noqa: E402

DATA = ROOT / "data" / "prizes.json"

# Measured on 2026-08-19: a 4s 9:16 clip on seedance-2.0-mini billed $0.1222.
CLIP_USD = 0.13

# One grade over every clip, so shots that drift apart in colour land in the
# same place. Prompting gets most of the way; this closes the gap.
GRADE = (
    "curves=r='0/0.02 0.5/0.5 1/0.97':g='0/0.01 0.5/0.49 1/0.96':"
    "b='0/0.05 0.5/0.47 1/0.92',"
    "eq=contrast=1.06:saturation=0.88:gamma=0.98,vignette=PI/5"
)


def grade_and_trim(src: Path, dst: Path, seconds: float, ffmpeg: str) -> None:
    """Trim to the shot length, force one format, apply the shared grade."""
    from pipeline import theme

    dst.parent.mkdir(parents=True, exist_ok=True)
    ffrender.run([
        ffmpeg, "-y", "-loglevel", "error", "-i", str(src),
        "-t", f"{seconds:.3f}",
        "-vf", (f"scale={theme.WIDTH}:{theme.HEIGHT}:force_original_aspect_"
                f"ratio=increase,crop={theme.WIDTH}:{theme.HEIGHT},"
                f"fps={theme.FPS},{GRADE},format=yuv420p"),
        "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        str(dst),
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prize", required=True)
    parser.add_argument("--budget", type=float, default=3.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", default=openrouter.VIDEO_MODEL)
    args = parser.parse_args()

    prize = load_prize(DATA, args.prize)
    script = write_script(prize)
    work = ROOT / "out" / f".ai-{prize.id}"
    ffmpeg = ffrender.find_ffmpeg()

    # Re-fit to the real narration so shots match what the stills were made for.
    segment_audio = tts.synthesize(script.segments, "openrouter",
                                   ROOT / "out" / f".voice-{prize.id}", ffmpeg)
    ffrender.retime_to_audio(script, segment_audio)
    shots, _ = plan_shots(prize, script)

    todo = [s for s in shots
            if not (work / "graded" / f"shot{s.index:02d}.mp4").exists()]
    print(f"{prize.badge}")
    print(f"  {len(shots)} shots, {len(todo)} to generate, "
          f"{len(shots) - len(todo)} cached")
    print(f"  estimated ${len(todo) * CLIP_USD:.2f}   budget ${args.budget:.2f}")
    if args.dry_run:
        return 0
    if len(todo) * CLIP_USD > args.budget:
        print("refusing to start: over budget")
        return 1

    missing = [s for s in todo
               if not (work / "stills" / f"shot{s.index:02d}.png").exists()]
    if missing:
        print(f"\nno still for shot(s) {[s.index + 1 for s in missing]} — "
              f"run scripts/make_ai_stills.py first")
        return 1

    # Submit everything, then poll as a batch.
    print("\nsubmitting ...")
    jobs: dict[str, object] = {}
    for shot in todo:
        still = work / "stills" / f"shot{shot.index:02d}.png"
        try:
            job = openrouter.submit_video(
                shot.video_prompt(), shot.seconds, model=args.model,
                first_frame=still, seed=style.SEED, aspect_ratio="9:16",
            )
            jobs[job] = shot
            print(f"  {shot.index + 1:2d}: {job}")
            # Written after every submit: these jobs are billed the moment
            # they are queued, so a later crash must not lose the ids.
            ledger = work / "jobs.json"
            ledger.parent.mkdir(parents=True, exist_ok=True)
            ledger.write_text(json.dumps(
                {str(sh.index): j for j, sh in jobs.items()}, indent=2),
                encoding="utf-8")
        except openrouter.OpenRouterError as exc:
            print(f"  {shot.index + 1:2d}: FAILED to submit — {exc}")

    print(f"\npolling {len(jobs)} jobs ...")
    pending = dict(jobs)
    spent = 0.0
    deadline = time.time() + 1800
    while pending and time.time() < deadline:
        time.sleep(10)
        for job in list(pending):
            shot = pending[job]
            try:
                state = openrouter.poll_video(job)
            except openrouter.OpenRouterError as exc:
                print(f"  {shot.index + 1:2d}: poll error {exc}")
                continue
            status = state.get("status")
            if status in {"completed", "succeeded"}:
                raw = work / "clips" / f"shot{shot.index:02d}.mp4"
                openrouter.fetch_video(job, raw)
                cost = float((state.get("usage") or {}).get("cost") or 0.0)
                spent += cost
                grade_and_trim(raw, work / "graded" / f"shot{shot.index:02d}.mp4",
                               shot.seconds, ffmpeg)
                print(f"  {shot.index + 1:2d}: done  ${cost:.4f}")
                pending.pop(job)
            elif status in {"failed", "error", "cancelled"}:
                print(f"  {shot.index + 1:2d}: {status}")
                pending.pop(job)

    if pending:
        print(f"\n{len(pending)} jobs still running when the wait expired; "
              f"re-run to pick them up")

    print(f"\nspent ${spent:.4f}")
    print("next: python scripts/make_hyperframes.py --prize "
          f"{prize.id} --voice openrouter --render")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
