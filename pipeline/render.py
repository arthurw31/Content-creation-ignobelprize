"""Assemble the final vertical MP4 with FFmpeg.

Pipeline order:
    1. draw one background card per segment (Pillow)
    2. synthesise voiceover per segment, and re-time the script to it
    3. write the word-by-word caption track (ASS)
    4. render each segment as a clip with a slow push-in
    5. concat, lay the audio under it, burn captions and a progress bar

Cuts are hard, not crossfaded. On a 40-second video a hard cut on every
beat reads as pace; a dissolve reads as a slideshow.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import captions, theme, tts, visuals
from .models import Prize, VideoScript
from .script_writer import PAUSE_AFTER, distribute_words


def find_ffmpeg() -> str:
    """Prefer a system ffmpeg, fall back to the npm ffmpeg-static binary."""
    env = os.environ.get("FFMPEG_BINARY")
    if env and Path(env).exists():
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in [
        "/opt/node22/lib/node_modules/ffmpeg-static/ffmpeg",
        "/usr/local/lib/node_modules/ffmpeg-static/ffmpeg",
        Path.home() / ".npm-global/lib/node_modules/ffmpeg-static/ffmpeg",
    ]:
        if Path(candidate).exists():
            return str(candidate)
    raise FileNotFoundError(
        "ffmpeg not found. Install it, or set FFMPEG_BINARY to its path."
    )


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(cmd[:6])} ...\n{tail}")


@dataclass
class RenderResult:
    video: Path
    script_json: Path
    duration: float
    voiced: bool


def retime_to_audio(script: VideoScript, audio: list[Path | None]) -> None:
    """Replace estimated timings with the real length of each voice clip."""
    clock = 0.0
    for seg, path in zip(script.segments, audio):
        if path is not None:
            spoken = tts.wav_duration(path)
        else:
            spoken = seg.duration - PAUSE_AFTER.get(seg.role, 0.15)
        seg.start = clock
        seg.duration = spoken + PAUSE_AFTER.get(seg.role, 0.15)
        clock = seg.end
    script.words = distribute_words(script.segments)


def build_segment_clip(card: Path, duration: float, index: int,
                       work: Path, ffmpeg: str) -> Path:
    """One still, pushed in slowly. Alternate direction so cuts feel varied."""
    frames = max(int(round(duration * theme.FPS)), 2)
    out = work / f"clip{index:02d}.mp4"

    # Zooming in on odd segments and out on even ones keeps a long video from
    # feeling like it is on a single continuous slider.
    if index % 2 == 0:
        zoom = "min(1.02+0.00045*on,1.18)"
    else:
        zoom = "max(1.18-0.00045*on,1.02)"

    vf = (
        f"scale={theme.BG_WIDTH}:{theme.BG_HEIGHT},"
        f"zoompan=z='{zoom}':d={frames}:x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':s={theme.WIDTH}x{theme.HEIGHT}:fps={theme.FPS},"
        f"format=yuv420p"
    )

    run([
        ffmpeg, "-y", "-loglevel", "error",
        "-loop", "1", "-framerate", str(theme.FPS), "-t", f"{duration:.3f}",
        "-i", str(card),
        "-vf", vf,
        "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        str(out),
    ])
    return out


def build_segment_audio(voice: Path | None, duration: float, index: int,
                        work: Path, ffmpeg: str) -> Path:
    """Pad (or trim) each voice clip to exactly its segment length."""
    out = work / f"audio{index:02d}.wav"
    if voice is None:
        run([
            ffmpeg, "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", f"{duration:.3f}", str(out),
        ])
    else:
        run([
            ffmpeg, "-y", "-loglevel", "error", "-i", str(voice),
            "-af", f"apad,atrim=0:{duration:.3f},asetpts=N/SR/TB",
            "-ac", "1", "-ar", "44100", str(out),
        ])
    return out


def concat(paths: list[Path], out: Path, work: Path, ffmpeg: str) -> Path:
    listing = work / f"concat_{out.stem}.txt"
    listing.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in paths), encoding="utf-8"
    )
    run([
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(listing),
        "-c", "copy", str(out),
    ])
    return out


def render(prize: Prize, script: VideoScript, out_dir: Path,
           tts_provider: str = "auto", music: Path | None = None,
           music_gain_db: float = -22.0, keep_work: bool = False) -> RenderResult:
    ffmpeg = find_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / f".work-{prize.id}"
    work.mkdir(parents=True, exist_ok=True)

    voice = tts.synthesize(script.segments, tts_provider, work / "voice", ffmpeg)
    voiced = any(v is not None for v in voice)
    if voiced:
        retime_to_audio(script, voice)

    ass_path = captions.build_ass(script, work / "captions.ass")

    clips, tracks = [], []
    for seg, voice_path in zip(script.segments, voice):
        card = visuals.render_card(
            seg, prize.badge, len(script.segments),
            work / f"card{seg.index:02d}.png", seed=abs(hash(prize.id)) % 9999,
        )
        clips.append(build_segment_clip(card, seg.duration, seg.index, work, ffmpeg))
        tracks.append(build_segment_audio(voice_path, seg.duration, seg.index,
                                          work, ffmpeg))

    silent_video = concat(clips, work / "video.mp4", work, ffmpeg)
    voice_track = concat(tracks, work / "voice.wav", work, ffmpeg)

    duration = script.duration
    accent = theme.ffmpeg_colour(theme.ACCENT)

    # libass needs the filter argument escaped, not the shell.
    ass_arg = str(ass_path.resolve()).replace("\\", "/").replace(":", r"\:")
    bar_h = 10
    video_chain = (
        f"[0:v]subtitles='{ass_arg}':fontsdir=/usr/share/fonts,"
        f"drawbox=x=0:y={theme.HEIGHT - bar_h}:w='iw*t/{duration:.3f}':"
        f"h={bar_h}:color={accent}@0.95:t=fill[v]"
    )

    cmd = [ffmpeg, "-y", "-loglevel", "error",
           "-i", str(silent_video), "-i", str(voice_track)]

    if music and music.exists():
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        audio_chain = (
            f"[2:a]volume={music_gain_db}dB,atrim=0:{duration:.3f},"
            f"afade=t=out:st={max(duration - 1.2, 0):.3f}:d=1.2[m];"
            f"[1:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]"
        )
        filter_complex = f"{video_chain};{audio_chain}"
        maps = ["-map", "[v]", "-map", "[a]"]
    else:
        filter_complex = video_chain
        maps = ["-map", "[v]", "-map", "1:a"]

    final = out_dir / f"{prize.year}-{prize.id}.mp4"
    cmd += ["-filter_complex", filter_complex, *maps,
            "-c:v", "libx264", "-preset", "slow", "-crf", "20",
            "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-movflags", "+faststart", "-shortest", str(final)]
    run(cmd)

    script_json = out_dir / f"{prize.year}-{prize.id}.script.json"
    script.to_json(script_json)

    if not keep_work:
        shutil.rmtree(work, ignore_errors=True)

    return RenderResult(video=final, script_json=script_json,
                        duration=duration, voiced=voiced)
