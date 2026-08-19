#!/usr/bin/env python3
"""Generate the HyperFrames composition for a prize, then lint / check / render.

    python scripts/make_hyperframes.py --prize polyester-rats
    python scripts/make_hyperframes.py --prize polyester-rats --render

Without --render it only writes hyperframes/index.html and runs the linter,
which is the fast loop while you are shaping a video.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import render as ffrender, tts  # noqa: E402
from pipeline.aiclip.plan import describe, plan_shots  # noqa: E402
from pipeline.hyperframes_build import PROJECT, build  # noqa: E402
from pipeline.models import Prize, load_prize  # noqa: E402
from pipeline.script_writer import write_script  # noqa: E402

DATA = ROOT / "data" / "prizes.json"


def build_voice(prize: Prize, script, provider: str) -> Path | None:
    """Synthesise the narration, then re-fit the script to the real audio.

    Order matters: the segments are re-timed to the lengths the voice actually
    came back with *before* the composition is generated, so captions and cuts
    land on the words rather than on an estimate.
    """
    resolved = tts.available_provider(provider)
    if resolved == "none":
        print("no voice: no TTS key found (captions-only render)")
        return None

    ffmpeg = ffrender.find_ffmpeg()
    work = ROOT / "out" / f".voice-{prize.id}"
    work.mkdir(parents=True, exist_ok=True)

    print(f"synthesising narration with {resolved} ...")
    segment_audio = tts.synthesize(script.segments, resolved, work, ffmpeg)
    ffrender.retime_to_audio(script, segment_audio)

    padded = [
        ffrender.build_segment_audio(path, seg.duration, seg.index, work, ffmpeg)
        for seg, path in zip(script.segments, segment_audio)
    ]
    track = ffrender.concat(padded, work / "voice.wav", work, ffmpeg)
    print(f"narration ready, {script.duration:.1f}s")
    return track


def npx() -> str:
    """Resolve npx properly. On Windows it is npx.cmd, and subprocess without
    a shell will not find the bare name."""
    # On Windows the extensionless "npx" is a shell script that CreateProcess
    # rejects with WinError 193; the .cmd shim is the runnable one.
    names = ["npx.cmd", "npx"] if os.name == "nt" else ["npx"]
    found = next((shutil.which(n) for n in names if shutil.which(n)), None)
    if not found:
        raise FileNotFoundError(
            "npx not found. Install Node.js and reopen the terminal."
        )
    return found


def hf(*args: str) -> int:
    return subprocess.run([npx(), "--yes", "hyperframes@0.7.110", *args],
                          cwd=PROJECT).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prize", required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--check", action="store_true",
                        help="full check: lint, runtime, layout, motion, contrast")
    parser.add_argument("--shots", action="store_true",
                        help="print the shot list with its narration timings")
    parser.add_argument("--voice", default="auto",
                        choices=["auto", "none", "elevenlabs", "openrouter", "openai"])
    args = parser.parse_args()

    prize = load_prize(DATA, args.prize)
    script = write_script(prize)
    voice_track = build_voice(prize, script, args.voice)

    # Shots are planned after the script is re-timed to the real narration, so
    # each cue lands on the moment its words are actually spoken.
    shots, _ = plan_shots(prize, script)
    if args.shots:
        print(describe(shots, {}))
    path = build(prize, script, voice_track=voice_track, shots=shots)
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
