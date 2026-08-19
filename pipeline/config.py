"""Load secrets from a local .env file.

Environment variables set with `setx` on Windows only reach processes started
afterwards, which is awkward when an agent session is already running. A .env
file in the repo root sidesteps that: it is read at import time, it survives
restarts, and it is gitignored so the key never leaves the machine.

Values already present in the real environment always win, so exporting a key
for one run still overrides the file.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"


def load_env(path: Path | None = None) -> dict[str, str]:
    """Read KEY=value lines into os.environ without clobbering what is set."""
    path = path or ENV_FILE
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        loaded[key] = value
        os.environ.setdefault(key, value)
    return loaded


def describe() -> str:
    """Which credentials are visible, without printing any of them."""
    load_env()
    lines = []
    for key in ("OPENROUTER_API_KEY", "ELEVENLABS_API_KEY", "OPENAI_API_KEY"):
        value = os.environ.get(key)
        lines.append(f"  {key:22s} {'set (...' + value[-6:] + ')' if value else 'absent'}")
    return "\n".join(lines)


# Loaded on import so every entry point picks the file up for free.
load_env()
