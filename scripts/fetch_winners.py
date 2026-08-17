#!/usr/bin/env python3
"""Scrape the official Ig Nobel winners list and expand data/prizes.json.

Run this on a machine with open network access. The container this repo was
built in blocks outbound HTTP to improbable.com, so the shipped dataset is a
hand-written seed. This script pulls the full list (roughly 350 prizes,
1991 to today) and merges it in.

    python scripts/fetch_winners.py --check    # verify the seed entries
    python scripts/fetch_winners.py --merge    # add every missing prize

Merged entries arrive with empty hook/beats/twist fields. They are raw
material, not scripts: fill those in (by hand or with an LLM) before
rendering, and keep verified='unverified' until you have read the source.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "prizes.json"
SOURCE = "https://improbable.com/ig/winners/"
UA = "Mozilla/5.0 (compatible; ignobel-pipeline/1.0)"

YEAR_RE = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")
PRIZE_RE = re.compile(
    r"(?P<category>[A-Z][A-Za-z &,\-]{2,40}?)\s+PRIZE\s*[:—\-]\s*(?P<body>.+)",
    re.IGNORECASE,
)


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_html(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&#8217;", "'").replace("&#8220;", '"')
    text = text.replace("&#8221;", '"').replace("&#8212;", "—")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def parse(text: str) -> list[dict]:
    """Walk the page top to bottom, tracking the most recent year heading."""
    prizes, year = [], None
    for line in text.splitlines():
        heading = YEAR_RE.search(line)
        if heading and len(line) < 60:
            year = int(heading.group(1))
        match = PRIZE_RE.search(line)
        if not match or year is None:
            continue
        category = match.group("category").strip().title()
        body = match.group("body").strip()
        laureates, _, citation = body.partition(", for ")
        if not citation:
            laureates, _, citation = body.partition(" for ")
        prizes.append({
            "year": year,
            "category": category,
            "laureates": laureates.strip(" ,."),
            "citation": citation.strip().rstrip(".") + "." if citation else body,
        })
    return prizes


def slug(prize: dict) -> str:
    words = re.findall(r"[a-z]+", prize["citation"].lower())
    stop = {"for", "the", "and", "that", "with", "their", "a", "an", "of",
            "to", "in", "on", "by", "is", "are", "it", "its", "when", "what"}
    keep = [w for w in words if w not in stop and len(w) > 3][:3]
    return "-".join(keep) or f"{prize['category'].lower()}-{prize['year']}"


def load() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def check(scraped: list[dict], existing: dict) -> int:
    """Flag seed entries whose year/category don't appear in the official list."""
    index = {(p["year"], p["category"].lower()) for p in scraped}
    problems = 0
    for prize in existing["prizes"]:
        key = (prize["year"], prize["category"].lower())
        if key not in index:
            print(f"  MISMATCH  {prize['id']}: no {prize['category']} prize "
                  f"listed for {prize['year']}")
            problems += 1
    print(f"\n{len(existing['prizes']) - problems} of "
          f"{len(existing['prizes'])} seed entries matched the official list.")
    return problems


def merge(scraped: list[dict], existing: dict) -> int:
    have = {(p["year"], p["category"].lower()) for p in existing["prizes"]}
    ids = {p["id"] for p in existing["prizes"]}
    added = 0
    for prize in scraped:
        if (prize["year"], prize["category"].lower()) in have:
            continue
        base = slug(prize)
        prize_id = base
        n = 2
        while prize_id in ids:
            prize_id = f"{base}-{n}"
            n += 1
        ids.add(prize_id)
        existing["prizes"].append({
            "id": prize_id,
            "year": prize["year"],
            "category": prize["category"],
            "laureates": prize["laureates"],
            "citation": prize["citation"],
            "hook": "",
            "beats": [],
            "twist": "",
            "kicker": "",
            "tags": [],
            "verified": "unverified",
            "refs": [],
        })
        added += 1
    existing["prizes"].sort(key=lambda p: (-p["year"], p["category"]))
    DATA.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify seed entries against the official list")
    parser.add_argument("--merge", action="store_true",
                        help="append every prize missing from the dataset")
    parser.add_argument("--url", default=SOURCE)
    args = parser.parse_args()

    if not (args.check or args.merge):
        parser.error("pass --check or --merge")

    try:
        html = fetch(args.url)
    except Exception as exc:  # network is the expected failure here
        print(f"Could not reach {args.url}: {exc}", file=sys.stderr)
        print("This script needs open outbound network access.", file=sys.stderr)
        return 2

    scraped = parse(strip_html(html))
    print(f"Parsed {len(scraped)} prizes from {args.url}\n")
    if len(scraped) < 100:
        print("WARNING: that is far fewer than expected. The page layout has "
              "probably changed and PRIZE_RE needs updating.\n", file=sys.stderr)

    existing = load()
    status = 0
    if args.check:
        status = 1 if check(scraped, existing) else 0
    if args.merge:
        added = merge(scraped, existing)
        print(f"Added {added} prizes. Total: {len(existing['prizes'])}.")
        print("New entries have empty hook/beats/twist. Write those before "
              "rendering.")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
