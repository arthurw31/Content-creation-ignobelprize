#!/usr/bin/env python3
"""Download clips for jobs that were already submitted and paid for.

A crash between submitting and downloading loses the files, not the money:
the jobs keep running server-side. This reads job ids from a JSON map and
finishes the download-grade-trim half.

    python scripts/recover_clips.py --prize polyester-rats --jobs jobs.json

jobs.json is {"<shot index>": "<job id>"}.
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
from pipeline.aiclip import openrouter  # noqa: E402
from pipeline.aiclip.plan import plan_shots  # noqa: E402
from pipeline.models import load_prize  # noqa: E402
from pipeline.script_writer import write_script  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from make_ai_clips import grade_and_trim  # noqa: E402

DATA = ROOT / "data" / "prizes.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prize", required=True)
    parser.add_argument("--jobs", required=True)
    args = parser.parse_args()

    prize = load_prize(DATA, args.prize)
    script = write_script(prize)
    ffmpeg = ffrender.find_ffmpeg()
    segment_audio = tts.synthesize(script.segments, "openrouter",
                                   ROOT / "out" / f".voice-{prize.id}", ffmpeg)
    ffrender.retime_to_audio(script, segment_audio)
    shots, _ = plan_shots(prize, script)
    by_index = {s.index: s for s in shots}

    work = ROOT / "out" / f".ai-{prize.id}"
    (work / "graded").mkdir(parents=True, exist_ok=True)
    (work / "clips").mkdir(parents=True, exist_ok=True)

    pending = {int(k): v for k, v in
               json.loads(Path(args.jobs).read_text(encoding="utf-8-sig")).items()}
    print(f"recovering {len(pending)} jobs")

    spent = 0.0
    deadline = time.time() + 1800
    while pending and time.time() < deadline:
        for index in list(pending):
            job = pending[index]
            try:
                state = openrouter.poll_video(job)
            except openrouter.OpenRouterError as exc:
                print(f"  {index + 1:2d}: poll error {exc}")
                continue
            status = state.get("status")
            if status in {"completed", "succeeded"}:
                raw = work / "clips" / f"shot{index:02d}.mp4"
                openrouter.fetch_video(job, raw)
                cost = float((state.get("usage") or {}).get("cost") or 0.0)
                spent += cost
                shot = by_index.get(index)
                seconds = shot.seconds if shot else 3.0
                grade_and_trim(raw, work / "graded" / f"shot{index:02d}.mp4",
                               seconds, ffmpeg)
                print(f"  {index + 1:2d}: recovered  ${cost:.4f}")
                pending.pop(index)
            elif status in {"failed", "error", "cancelled"}:
                print(f"  {index + 1:2d}: {status}")
                pending.pop(index)
        if pending:
            time.sleep(10)

    print(f"\nrecovered spend ${spent:.4f}")
    if pending:
        print(f"still pending: {pending}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

