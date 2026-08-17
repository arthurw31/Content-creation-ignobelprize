"""Drive the whole generative render: sheets, stills, clips, grade, assembly.

Order matters, and it is the order that buys coherence:

    1. character sheets   one reference still per recurring subject
    2. shot stills        image model, each carrying its subjects' sheets
    3. clips              video model, image-to-video from those stills
    4. grade              one colour pass over every clip, unifying them
    5. assembly           clips + voiceover + burned captions

Steps 1-3 all spend money. Everything is cached on disk by filename, so a
re-run after a failure resumes instead of paying twice, and you can delete a
single bad shot's files to regenerate only that shot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import openrouter, style
from .plan import plan_shots
from .style import Shot, Subject
from ..models import Prize, VideoScript
from ..render import find_ffmpeg, run
from .. import captions as captions_mod
from .. import theme


@dataclass
class Budget:
    """Hard spending cap. Nothing is generated until this is accepted."""

    limit_usd: float
    per_video_second_usd: float = 0.20
    per_image_usd: float = 0.04

    def estimate(self, shots: list[Shot], sheets: int) -> float:
        video = sum(s.generate_seconds for s in shots) * self.per_video_second_usd
        images = (len(shots) + sheets) * self.per_image_usd
        return video + images

    def check(self, shots: list[Shot], sheets: int) -> float:
        cost = self.estimate(shots, sheets)
        if cost > self.limit_usd:
            raise RuntimeError(
                f"Estimated ${cost:.2f} exceeds the --budget of "
                f"${self.limit_usd:.2f}. Raise the budget or cut shots.\n"
                f"Note: the per-unit prices are estimates. Check the real ones "
                f"on your OpenRouter dashboard after the first run and update "
                f"Budget's defaults."
            )
        return cost


def build_sheets(subjects: dict[str, Subject], work: Path) -> None:
    """One reference still per subject, generated once and reused everywhere."""
    for subject in subjects.values():
        path = work / "sheets" / f"{subject.key}.png"
        if not path.exists():
            openrouter.generate_image(subject.sheet_prompt(), path)
        subject.reference_image = str(path)


def build_stills(shots: list[Shot], subjects: dict[str, Subject],
                 work: Path) -> None:
    """The opening frame of each shot, anchored to the subject sheets."""
    for shot in shots:
        path = work / "stills" / f"shot{shot.index:02d}.png"
        if not path.exists():
            reference = None
            for key in shot.subjects:
                subject = subjects.get(key)
                if subject and subject.reference_image:
                    reference = subject.reference_image
                    break
            openrouter.generate_image(shot.image_prompt(), path,
                                      reference_image=reference)
        shot.still_path = str(path)


def build_clips(shots: list[Shot], work: Path) -> None:
    """Animate each still. Image-to-video, never text-to-video."""
    for shot in shots:
        path = work / "clips" / f"shot{shot.index:02d}.mp4"
        if not path.exists():
            openrouter.generate_video(
                shot.video_prompt(),
                seconds=shot.generate_seconds,
                out_path=path,
                reference_image=shot.still_path,
                negative_prompt=style.NEGATIVE_PROMPT,
                seed=style.SEED,
                aspect_ratio="9:16",
            )
        shot.clip_path = str(path)


# A single grade applied to every clip. This is what rescues the coherence
# that prompting alone does not deliver: even clips that drift apart in
# colour temperature land in the same place after this.
GRADE = (
    "curves=r='0/0.02 0.5/0.5 1/0.97':g='0/0.01 0.5/0.49 1/0.96':"
    "b='0/0.05 0.5/0.47 1/0.92',"
    "eq=contrast=1.08:saturation=0.82:gamma=0.98,"
    "vignette=PI/5"
)


def grade_and_normalise(shots: list[Shot], work: Path, ffmpeg: str) -> list[Path]:
    """Grade every clip and force them all to one format, size and frame rate.

    Clips come back from the model at whatever size and rate it felt like.
    Concatenating those without normalising is the classic way to end up with
    a video that stutters at every cut.
    """
    out: list[Path] = []
    for shot in shots:
        dst = work / "graded" / f"shot{shot.index:02d}.mp4"
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            # Stretch the generated clip to exactly fill its segment.
            ratio = max(shot.seconds / shot.generate_seconds, 1.0)
            retime = f"setpts={ratio:.4f}*PTS," if ratio > 1.001 else ""
            run([
                ffmpeg, "-y", "-loglevel", "error", "-i", str(shot.clip_path),
                "-vf", (retime + f"scale={theme.WIDTH}:{theme.HEIGHT}:force_original_"
                        f"aspect_ratio=increase,crop={theme.WIDTH}:{theme.HEIGHT},"
                        f"fps={theme.FPS},{GRADE},format=yuv420p"),
                "-t", f"{shot.seconds:.3f}",
                "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                str(dst),
            ])
        out.append(dst)
    return out


def produce(prize: Prize, script: VideoScript, out_dir: Path,
            budget: Budget, dry_run: bool = False,
            voice: bool = True) -> Path | None:
    ffmpeg = find_ffmpeg()
    work = out_dir / f".ai-{prize.id}"
    work.mkdir(parents=True, exist_ok=True)

    shots, subjects = plan_shots(prize, script)

    if dry_run:
        from .plan import describe
        cost = budget.estimate(shots, len(subjects))
        print(describe(shots, subjects))
        print(f"\nestimated spend: ${cost:.2f} (nothing generated)")
        if cost > budget.limit_usd:
            print(f"over the ${budget.limit_usd:.2f} budget — rerun with "
                  f"--budget {cost + 1:.0f} to allow it")
        return None

    cost = budget.check(shots, len(subjects))
    print(f"estimated spend ${cost:.2f}, budget ${budget.limit_usd:.2f}\n")

    print(f"Generating {len(subjects)} reference sheets ...")
    build_sheets(subjects, work)
    print(f"Generating {len(shots)} stills ...")
    build_stills(shots, subjects, work)
    print(f"Generating {len(shots)} clips ...")
    build_clips(shots, work)

    print("Grading and normalising ...")
    graded = grade_and_normalise(shots, work, ffmpeg)

    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in graded),
                       encoding="utf-8")
    silent = work / "video.mp4"
    run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", str(silent)])

    audio = work / "voice.mp3"
    if voice and not audio.exists():
        print("Generating voiceover ...")
        openrouter.generate_speech(script.narration, audio,
                                   instructions=NARRATION_STYLE)

    ass_path = captions_mod.build_ass(script, work / "captions.ass")
    ass_arg = str(ass_path.resolve()).replace("\\", "/").replace(":", r"\:")

    final = out_dir / f"{prize.year}-{prize.id}.ai.mp4"
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(silent)]
    if voice and audio.exists():
        cmd += ["-i", str(audio)]
        maps = ["-map", "0:v", "-map", "1:a"]
    else:
        maps = ["-map", "0:v"]
    cmd += ["-vf", f"subtitles='{ass_arg}':fontsdir=/usr/share/fonts", *maps,
            "-c:v", "libx264", "-preset", "slow", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", "-shortest", str(final)]
    run(cmd)

    print(f"\n{final}")
    print(f"work files kept in {work} — delete a shot's files to regenerate it")
    return final


NARRATION_STYLE = (
    "Deadpan documentary narrator. Dry, confident, slightly amused. "
    "Never jokey. Let the facts be the joke."
)
