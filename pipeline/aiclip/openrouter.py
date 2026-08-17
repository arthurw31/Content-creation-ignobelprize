"""OpenRouter client: video, image and speech generation.

IMPORTANT — verify before trusting this file.

openrouter.ai is blocked by the network policy of the container this was
written in, so the request shapes below could not be checked against the live
API or its docs. They follow OpenRouter's documented conventions (OpenAI-
compatible auth, /api/v1 base, async submit-and-poll for video), but treat
them as a first draft.

Run this before anything else, on a machine with network access:

    python -m pipeline.aiclip.openrouter --probe

It calls the cheap read-only endpoints, prints what the API actually returns,
and tells you which of the shapes below need adjusting. Fix them once and the
rest of the pipeline works.

Never hard-code the key. Read it from OPENROUTER_API_KEY.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

BASE = "https://openrouter.ai/api/v1"

# Defaults chosen for cost, not maximum quality. A 30s video is 6 clips; at
# premium-model prices that adds up fast. Move up once the format is proven.
VIDEO_MODEL = os.environ.get("IGNOBEL_VIDEO_MODEL", "bytedance/seedance-2.0-fast")
IMAGE_MODEL = os.environ.get("IGNOBEL_IMAGE_MODEL", "google/gemini-2.5-flash-image")
TTS_MODEL = os.environ.get("IGNOBEL_TTS_MODEL", "openai/gpt-4o-mini-tts")
TTS_VOICE = os.environ.get("IGNOBEL_TTS_VOICE", "onyx")

POLL_INTERVAL = 5.0
POLL_TIMEOUT = 900.0


class OpenRouterError(RuntimeError):
    pass


def _key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not set.\n"
            "  export OPENROUTER_API_KEY=sk-or-v1-...\n"
            "Never paste the key into a file or a chat message."
        )
    return key


def _request(method: str, path: str, payload: dict | None = None,
             raw: bool = False, timeout: float = 120) -> dict | bytes:
    url = path if path.startswith("http") else f"{BASE}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {_key()}",
        "Content-Type": "application/json",
        # OpenRouter uses these for attribution on your dashboard.
        "HTTP-Referer": "https://github.com/arthurw31/Content-creation-ignobelprize",
        "X-Title": "Ig Nobel video pipeline",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        raise OpenRouterError(f"{method} {url} -> HTTP {exc.code}\n{detail}") from exc
    return body if raw else json.loads(body)


# --- account ---------------------------------------------------------------

def key_info() -> dict:
    return _request("GET", "/key")


def credits() -> dict:
    return _request("GET", "/credits")


def models() -> list[dict]:
    return _request("GET", "/models").get("data", [])


# --- video -----------------------------------------------------------------

@dataclass
class VideoJob:
    id: str
    status: str
    url: str | None = None


def submit_video(prompt: str, seconds: float, model: str = VIDEO_MODEL,
                 reference_image: Path | str | None = None,
                 negative_prompt: str | None = None,
                 seed: int | None = None,
                 aspect_ratio: str = "9:16") -> VideoJob:
    """Submit a generation. Returns immediately with a job id.

    `reference_image` switches this from text-to-video to image-to-video, which
    is what actually holds style across shots. Pass one whenever you have one.
    """
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "duration": seconds,
        "aspect_ratio": aspect_ratio,
    }
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    if seed is not None:
        payload["seed"] = seed
    if reference_image:
        payload["image"] = _as_data_uri(Path(reference_image))

    data = _request("POST", "/videos", payload)
    return VideoJob(
        id=data.get("id") or data.get("generation_id", ""),
        status=data.get("status", "queued"),
        url=_extract_video_url(data),
    )


def poll_video(job: VideoJob, timeout: float = POLL_TIMEOUT) -> VideoJob:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if job.status in {"completed", "succeeded"} and job.url:
            return job
        if job.status in {"failed", "cancelled", "error"}:
            raise OpenRouterError(f"Video job {job.id} ended as {job.status}")
        time.sleep(POLL_INTERVAL)
        data = _request("GET", f"/videos/{job.id}")
        job.status = data.get("status", job.status)
        job.url = _extract_video_url(data) or job.url
    raise OpenRouterError(f"Video job {job.id} still {job.status} after {timeout:.0f}s")


def generate_video(prompt: str, seconds: float, out_path: Path, **kwargs) -> Path:
    job = poll_video(submit_video(prompt, seconds, **kwargs))
    if not job.url:
        raise OpenRouterError(f"Job {job.id} completed without a video URL")
    return download(job.url, out_path)


# --- image -----------------------------------------------------------------

def generate_image(prompt: str, out_path: Path, model: str = IMAGE_MODEL,
                   reference_image: Path | str | None = None) -> Path:
    """Generate a still. Used for reference frames and character sheets."""
    content: list[dict] = [{"type": "text", "text": prompt}]
    if reference_image:
        content.append({
            "type": "image_url",
            "image_url": {"url": _as_data_uri(Path(reference_image))},
        })

    data = _request("POST", "/chat/completions", {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "modalities": ["image", "text"],
    })

    message = data["choices"][0]["message"]
    images = message.get("images") or []
    if not images:
        raise OpenRouterError(
            f"{model} returned no image. Response keys: {list(message)}"
        )
    url = images[0]["image_url"]["url"]
    return _write_data_uri_or_download(url, out_path)


# --- speech ----------------------------------------------------------------

def generate_speech(text: str, out_path: Path, model: str = TTS_MODEL,
                    voice: str = TTS_VOICE, instructions: str | None = None) -> Path:
    payload: dict = {"model": model, "input": text, "voice": voice,
                     "response_format": "mp3"}
    if instructions:
        payload["instructions"] = instructions
    audio = _request("POST", "/audio/speech", payload, raw=True, timeout=180)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(audio)  # type: ignore[arg-type]
    return out_path


# --- helpers ---------------------------------------------------------------

def _extract_video_url(data: dict) -> str | None:
    for key in ("url", "video_url", "output_url"):
        if isinstance(data.get(key), str):
            return data[key]
    for key in ("output", "data", "videos"):
        value = data.get(key)
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                for inner in ("url", "video_url"):
                    if isinstance(first.get(inner), str):
                        return first[inner]
    return None


def _as_data_uri(path: Path) -> str:
    import base64
    import mimetypes

    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def _write_data_uri_or_download(url: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if url.startswith("data:"):
        import base64

        out_path.write_bytes(base64.b64decode(url.split(",", 1)[1]))
        return out_path
    return download(url, out_path)


def download(url: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=300) as resp:
        out_path.write_bytes(resp.read())
    return out_path


# --- probe -----------------------------------------------------------------

def probe() -> int:
    """Check auth and report which models this key can actually reach."""
    print("Checking OPENROUTER_API_KEY ...")
    try:
        info = key_info()
    except OpenRouterError as exc:
        print(f"  FAILED\n{exc}")
        return 1
    print(f"  ok: {json.dumps(info, indent=2)[:400]}")

    print("\nLooking for video / image / speech models ...")
    try:
        catalogue = models()
    except OpenRouterError as exc:
        print(f"  could not list models: {exc}")
        return 1

    def by_output(kind: str) -> list[str]:
        found = []
        for m in catalogue:
            arch = m.get("architecture") or {}
            if kind in (arch.get("output_modalities") or []):
                found.append(m["id"])
        return found

    for kind in ("video", "image", "audio"):
        ids = by_output(kind)
        print(f"  {kind:6s}: {len(ids)} models")
        for model_id in ids[:8]:
            print(f"          {model_id}")

    for label, configured in (("video", VIDEO_MODEL), ("image", IMAGE_MODEL),
                              ("speech", TTS_MODEL)):
        known = {m["id"] for m in catalogue}
        mark = "ok" if configured in known else "NOT IN CATALOGUE - change it"
        print(f"\nconfigured {label} model: {configured}  [{mark}]")

    print(
        "\nIf a call later fails with HTTP 400, compare the error against the "
        "payloads in submit_video / generate_image / generate_speech and adjust "
        "the field names. They were written without access to the live docs."
    )
    return 0


if __name__ == "__main__":
    import sys

    if "--probe" in sys.argv:
        raise SystemExit(probe())
    print(__doc__)
