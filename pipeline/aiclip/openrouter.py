"""OpenRouter client: images and speech.

Every request shape here was verified against the live API on 2026-08-19 with
a real key, not written from documentation. What that probe established:

* **No video models exist on this account.** The catalogue holds 415 models:
  400 text, 11 image+text, 4 audio+text. No Veo, Sora, Seedance or Wan, and
  `/api/v1/videos` returns 404. Generative *footage* is therefore not
  available through OpenRouter here; `generate_video` raises rather than
  pretending otherwise. Stills plus a camera move carry the picture instead.
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


# --- video (not available here) --------------------------------------------

def generate_video(*_args, **_kwargs):
    raise VideoUnavailable(
        "OpenRouter serves no video-generation model on this account: the "
        "catalogue has 400 text, 11 image and 4 audio models, and there is no "
        "/videos endpoint. Use generate_image and animate the still, or bring "
        "a dedicated video provider (fal.ai, Replicate, Higgsfield)."
    )


submit_video = generate_video


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
