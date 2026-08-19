"""OpenRouter client: images and speech.

Every request shape here was verified against the live API on 2026-08-19 with
a real key, not written from documentation. What that probe established:

* **Video is missing from `/api/v1/models`.** That catalogue lists only text,
  image and audio, which is misleading: video generation lives behind an
  asynchronous `POST /api/v1/videos`, and a plain GET on that path returns
  404 — which is what made an earlier probe wrongly conclude video was
  unavailable. Veo 3.1, Seedance and Grok Imagine are all reachable.
  Image-to-video through `frame_images` is what holds the look together.
* **Images** come from `/chat/completions` with `modalities: ["image","text"]`,
  and `image_config.aspect_ratio` is honoured — "9:16" returns 768x1344.
  Roughly $0.039 per image on gemini-2.5-flash-image.
* **Speech** is not on `/audio/speech`; every model name there 400s with
  "does not exist". It works through `/chat/completions` on an audio-output
  model, which refuses unless `stream: true`, and arrives as base64 PCM
  chunks in the SSE deltas.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
import wave
from pathlib import Path

from .. import config  # noqa: F401  (loads .env on import)

BASE = "https://openrouter.ai/api/v1"

IMAGE_MODEL = os.environ.get("IGNOBEL_IMAGE_MODEL", "google/gemini-2.5-flash-image")
TTS_MODEL = os.environ.get("IGNOBEL_TTS_MODEL", "openai/gpt-audio-mini")
TTS_VOICE = os.environ.get("IGNOBEL_TTS_VOICE", "onyx")

# The audio deltas are 24kHz mono signed 16-bit little-endian.
PCM_RATE = 24000
PCM_WIDTH = 2

NARRATION_STYLE = (
    "Deadpan documentary narrator. Dry, confident, slightly amused. "
    "Never jokey. Let the facts be the joke."
)


class OpenRouterError(RuntimeError):
    pass


class VideoUnavailable(OpenRouterError):
    """Raised because OpenRouter serves no video model on this account."""


def _key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not set. Put it in the .env file at the "
            "repo root, one line: OPENROUTER_API_KEY=sk-or-v1-..."
        )
    return key


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/arthurw31/Content-creation-ignobelprize",
        "X-Title": "Ig Nobel video pipeline",
    }


def _post(path: str, payload: dict, timeout: float = 240) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", data=json.dumps(payload).encode(),
                                 method="POST", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        raise OpenRouterError(f"POST {path} -> HTTP {exc.code}\n{detail}") from exc


def _get(path: str, timeout: float = 60) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        raise OpenRouterError(f"GET {path} -> HTTP {exc.code}\n{detail}") from exc


# --- account ---------------------------------------------------------------

def key_info() -> dict:
    return _get("/key")


def models() -> list[dict]:
    return _get("/models").get("data", [])


# --- images ----------------------------------------------------------------

def generate_image(prompt: str, out_path: Path, model: str = IMAGE_MODEL,
                   reference_image: Path | str | None = None,
                   aspect_ratio: str = "9:16") -> tuple[Path, float]:
    """Generate one still. Returns its path and what it cost in USD."""
    content: list[dict] = [{"type": "text", "text": prompt}]
    if reference_image:
        content.append({
            "type": "image_url",
            "image_url": {"url": _as_data_uri(Path(reference_image))},
        })

    data = _post("/chat/completions", {
        "model": model,
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": aspect_ratio},
        "messages": [{"role": "user", "content": content}],
    })

    message = data["choices"][0]["message"]
    images = message.get("images") or []
    if not images:
        refusal = message.get("refusal") or message.get("content") or ""
        raise OpenRouterError(
            f"{model} returned no image. refusal/content: {str(refusal)[:300]}"
        )

    url = images[0]["image_url"]["url"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if url.startswith("data:"):
        out_path.write_bytes(base64.b64decode(url.split(",", 1)[1]))
    else:
        download(url, out_path)
    return out_path, float((data.get("usage") or {}).get("cost") or 0.0)


# --- speech ----------------------------------------------------------------

def generate_speech(text: str, out_path: Path, model: str = TTS_MODEL,
                    voice: str = TTS_VOICE,
                    instructions: str = NARRATION_STYLE) -> tuple[Path, float]:
    """Synthesise narration to a WAV. Returns its path and cost in USD.

    Audio-output models refuse a non-streaming request, so this reads the SSE
    stream and concatenates the base64 PCM deltas.
    """
    payload = {
        "model": model,
        "stream": True,
        "modalities": ["text", "audio"],
        "audio": {"voice": voice, "format": "pcm16"},
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user",
             "content": f"Read this aloud exactly as written, and say nothing "
                        f"else:\n\n{text}"},
        ],
    }
    req = urllib.request.Request(f"{BASE}/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 method="POST",
                                 headers={**_headers(),
                                          "Accept": "text/event-stream"})

    chunks: list[bytes] = []
    cost = 0.0
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                try:
                    event = json.loads(body)
                except json.JSONDecodeError:
                    continue
                usage = event.get("usage")
                if usage and usage.get("cost"):
                    cost = float(usage["cost"])
                for choice in event.get("choices", []):
                    audio = (choice.get("delta") or {}).get("audio")
                    if isinstance(audio, dict) and audio.get("data"):
                        chunks.append(base64.b64decode(audio["data"]))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        raise OpenRouterError(f"speech -> HTTP {exc.code}\n{detail}") from exc

    if not chunks:
        raise OpenRouterError(f"{model} returned no audio for {text[:60]!r}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(PCM_WIDTH)
        handle.setframerate(PCM_RATE)
        handle.writeframes(b"".join(chunks))
    return out_path, cost


# --- video -----------------------------------------------------------------
# Video models are NOT listed by /api/v1/models — that catalogue only carries
# text, image and audio. They live behind POST /api/v1/videos, which is
# asynchronous: submit, poll, then download. A GET on that path returns 404,
# which is what made an earlier probe wrongly conclude video was unavailable.

VIDEO_MODEL = os.environ.get("IGNOBEL_VIDEO_MODEL", "bytedance/seedance-2.0-mini")

# Seedance refuses anything under four seconds. Shots are usually shorter than
# that, so clips get trimmed to the shot length afterwards.
MIN_VIDEO_SECONDS = 4


def submit_video(prompt: str, seconds: float, model: str = VIDEO_MODEL,
                 first_frame: Path | str | None = None,
                 seed: int | None = None,
                 aspect_ratio: str = "9:16") -> str:
    """Queue one generation. Returns the job id.

    Passing first_frame makes this image-to-video: the still fixes subject,
    composition and palette, and the model only has to animate it. That is
    what holds the look together across a dozen shots.
    """
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "duration": max(int(round(seconds)), MIN_VIDEO_SECONDS),
        "aspect_ratio": aspect_ratio,
    }
    if seed is not None:
        payload["seed"] = seed
    if first_frame:
        payload["frame_images"] = [{
            "type": "image_url",
            "image_url": {"url": _as_data_uri(Path(first_frame))},
            "frame_type": "first_frame",
        }]

    data = _post("/videos", payload)
    job = data.get("id")
    if not job:
        raise OpenRouterError(f"no job id in response: {str(data)[:300]}")
    return job


def poll_video(job: str) -> dict:
    """One status read. Terminal states are completed / failed."""
    return _get(f"/videos/{job}")


def fetch_video(job: str, out_path: Path) -> Path:
    req = urllib.request.Request(f"{BASE}/videos/{job}/content?index=0",
                                 headers=_headers())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=600) as resp:
        out_path.write_bytes(resp.read())
    return out_path


def generate_video(prompt: str, seconds: float, out_path: Path,
                   poll_interval: float = 6.0, timeout: float = 900,
                   **kwargs) -> tuple[Path, float]:
    """Submit, wait, download. Returns the path and cost in USD."""
    import time

    job = submit_video(prompt, seconds, **kwargs)
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = poll_video(job)
        status = state.get("status")
        if status in {"completed", "succeeded"}:
            cost = float((state.get("usage") or {}).get("cost") or 0.0)
            return fetch_video(job, out_path), cost
        if status in {"failed", "error", "cancelled"}:
            raise OpenRouterError(f"video job {job} {status}: {str(state)[:300]}")
        time.sleep(poll_interval)
    raise OpenRouterError(f"video job {job} still running after {timeout:.0f}s")


# --- helpers ---------------------------------------------------------------

def _as_data_uri(path: Path) -> str:
    import mimetypes

    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def download(url: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=300) as resp:
        out_path.write_bytes(resp.read())
    return out_path


# --- probe -----------------------------------------------------------------

def probe() -> int:
    print("Checking OPENROUTER_API_KEY ...")
    try:
        info = key_info().get("data", {})
    except OpenRouterError as exc:
        print(f"  FAILED\n{exc}")
        return 1
    limit = info.get("limit")
    remaining = info.get("limit_remaining")
    print(f"  ok — credit limit ${limit}, remaining ${remaining}, "
          f"used ${info.get('usage')}")

    catalogue = models()
    by_output: dict[str, list[str]] = {"video": [], "image": [], "audio": []}
    for m in catalogue:
        for kind in (m.get("architecture") or {}).get("output_modalities") or []:
            by_output.setdefault(kind, []).append(m["id"])

    print(f"\n{len(catalogue)} models visible")
    for kind in ("video", "image", "audio"):
        print(f"  {kind:6s}: {len(by_output.get(kind, []))}")

    if not by_output.get("video"):
        print("\n  No video model. Footage must come from stills plus a "
              "camera move, or from another provider.")

    known = {m["id"] for m in catalogue}
    for label, configured in (("image", IMAGE_MODEL), ("speech", TTS_MODEL)):
        mark = "ok" if configured in known else "NOT IN CATALOGUE"
        print(f"  configured {label}: {configured} [{mark}]")
    return 0


if __name__ == "__main__":
    import sys

    if "--probe" in sys.argv:
        raise SystemExit(probe())
    print(__doc__)
