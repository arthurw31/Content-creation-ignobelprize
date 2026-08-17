#!/usr/bin/env python3
"""Render an Ig Nobel video using AI-generated clips.

    export OPENROUTER_API_KEY=sk-or-v1-...
    python -m pipeline.aiclip.openrouter --probe          # verify the API first
    python scripts/make_ai_video.py --prize polyester-rats --dry-run
    python scripts/make_ai_video.py --prize polyester-rats --budget 8

--dry-run prints the shot list and a cost estimate without spending anything.
Always run it first.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.aiclip.produce import Budget, produce  # noqa: E402
from pipeline.models import load_prize  # noqa: E402
from pipeline.script_writer import write_script  # noqa: E402

DATA = ROOT / "data" / "prizes.json"
OUT = ROOT / "out"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prize", required=True)
    parser.add_argument("--budget", type=float, default=5.0,
                        help="hard spending cap in USD (default 5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the shot list and cost, generate nothing")
    parser.add_argument("--no-voice", action="store_true")
    args = parser.parse_args()

    prize = load_prize(DATA, args.prize)
    script = write_script(prize)

    if prize.verified != "pubmed" and not args.dry_run:
        print(f"! {prize.id} is not source-verified. Check the facts before "
              f"spending money rendering it.\n")

    produce(prize, script, OUT, Budget(limit_usd=args.budget),
            dry_run=args.dry_run, voice=not args.no_voice)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
