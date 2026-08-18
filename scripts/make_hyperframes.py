#!/usr/bin/env python3
"""Generate the HyperFrames composition for a prize, then lint / check / render.

    python scripts/make_hyperframes.py --prize polyester-rats
    python scripts/make_hyperframes.py --prize polyester-rats --render

Without --render it only writes hyperframes/index.html and runs the linter,
which is the fast loop while you are shaping a video.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.hyperframes_build import PROJECT, build  # noqa: E402
from pipeline.models import load_prize  # noqa: E402
from pipeline.script_writer import write_script  # noqa: E402

DATA = ROOT / "data" / "prizes.json"


def hf(*args: str) -> int:
    return subprocess.run(["npx", "--yes", "hyperframes@0.7.110", *args],
                          cwd=PROJECT).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prize", required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--check", action="store_true",
                        help="full check: lint, runtime, layout, motion, contrast")
    args = parser.parse_args()

    prize = load_prize(DATA, args.prize)
    script = write_script(prize)
    path = build(prize, script)
    print(f"wrote {path.relative_to(ROOT)}  ({script.duration:.1f}s)")

    if hf("lint") != 0:
        print("\nlint failed — fix the composition before rendering")
        return 1
    if args.check and hf("check") != 0:
        print("\ncheck reported problems")
        return 1
    if args.render:
        out = ROOT / "out" / f"{prize.year}-{prize.id}.hf.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        if hf("render", "--output", str(out)) != 0:
            return 1
        print(f"\n{out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
