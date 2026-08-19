"""Voiceover generation, with a provider you can swap without touching render.

Providers:
    none        - silent track, captions carry the video (works offline)
    elevenlabs  - ELEVENLABS_API_KEY, its own service and its own key
    openrouter  - OPENROUTER_API_KEY, routes to OpenAI/Gemini/Grok/Voxtral
    openai      - OPENAI_API_KEY

ElevenLabs is not resold through OpenRouter, so the two are separate keys.
Preference order in "auto" mode is ElevenLabs first, because it is still the
best read for a deadpan documentary narrator.

Each segment is synthesised separately. That is what lets the renderer
re-time the video to the real audio instead of guessing, and it means one
bad line can be regenerated without redoing the whole video.
"""

from __future__ import annotations

import os
import subprocess
import wave
from pathlib import Path

from . import config  # noqa: F401  (loads .env on import)
from .models import Segment

OPENAI_VOICE = os.environ.get("IGNOBEL_OPENAI_VOICE", "onyx")
OPENAI_MODEL = os.environ.get("IGNOBEL_OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
ELEVEN_VOICE = os.environ.get("IGNOBEL_ELEVEN_VOICE", "JBFqnCBsd6RMkjVDRZzb")
ELEVEN_MODEL = os.environ.get("IGNOBEL_ELEVEN_MODEL", "eleven_multilingual_v2")

NARRATION_STYLE = (
    "Deadpan documentary narrator. Dry, confident, slightly amused. "
    "Never jokey. Let the facts be the joke."
)


class TTSUnavailable(RuntimeError):
    pass


def available_provider(requested: str) -> str:
    """Resolve 'auto' to whatever this machine actually has keys for."""
    if requested != "auto":
        return requested
    if os.environ.get("ELEVENLABS_API_KEY"):
        return "elevenlabs"
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "none"


def synthesize(segments: list[Segment], provider: str, out_dir: Path,
               ffmpeg: str) -> list[Path | None]:
    """Return one audio path per segment, or None where there is no voice."""
    provider = available_provider(provider)
    out_dir.mkdir(parents=True, exist_ok=True)

    if provider == "none":
        return [None] * len(segments)

    paths: list[Path | None] = []
    for seg in segments:
        raw = out_dir / f"seg{seg.index:02d}.raw"
        wav = out_dir / f"seg{seg.index:02d}.wav"
        if not wav.exists():
            if provider == "openai":
                _openai(seg.text, raw)
            elif provider == "openrouter":
                _openrouter(seg.text, raw)
            elif provider == "elevenlabs":
                _elevenlabs(seg.text, raw)
            else:
                raise TTSUnavailable(f"Unknown TTS provider {provider!r}")
            _to_wav(raw, wav, ffmpeg)
        paths.append(wav)
    return paths


def _openai(text: str, out_path: Path) -> None:
    import json
    import urllib.request

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise TTSUnavailable("OPENAI_API_KEY is not set")

    payload = json.dumps({
        "model": OPENAI_MODEL,
        "voice": OPENAI_VOICE,
        "input": text,
        "instructions": NARRATION_STYLE,
        "response_format": "mp3",
    }).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=payload,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        out_path.write_bytes(resp.read())


def _openrouter(text: str, out_path: Path) -> None:
    """Delegate to the verified client, which writes a WAV directly.

    OpenRouter's /audio/speech endpoint rejects every model name on this
    account; speech only comes back as PCM deltas over a streamed chat
    completion. That logic lives in aiclip.openrouter, so it is not
    duplicated here.
    """
    from .aiclip.openrouter import generate_speech

    generate_speech(text, out_path, instructions=NARRATION_STYLE)


def _elevenlabs(text: str, out_path: Path) -> None:
    import json
    import urllib.request

    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise TTSUnavailable("ELEVENLABS_API_KEY is not set")

    payload = json.dumps({
        "text": text,
        "model_id": ELEVEN_MODEL,
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.75},
    }).encode()

    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE}",
        data=payload,
        headers={"xi-api-key": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        out_path.write_bytes(resp.read())


# TTS clips arrive with a beat of silence at each end. Left in, they stack
# into real dead air between segments — a measured 3.1s across one 36s video,
# which on vertical video is a scroll trigger, not a dramatic pause. The
# script's own PAUSE_AFTER puts the pauses back where they are wanted.
TRIM_SILENCE = (
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,"
    "areverse,"
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,"
    "areverse"
)


def _to_wav(src: Path, dst: Path, ffmpeg: str) -> None:
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(src),
         "-af", TRIM_SILENCE,
         "-ac", "1", "-ar", "44100", str(dst)],
        check=True,
    )


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


