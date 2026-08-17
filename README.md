# Ig Nobel — short-form video pipeline

Turns an Ig Nobel Prize into a finished vertical video (1080×1920, MP4, ready
for TikTok / Reels / Shorts) from a single command.

```bash
python scripts/make_video.py --prize polyester-rats
```

Output lands in `out/`: the video, the timed script, and the title /
description / hashtags for the platform.

## Why not OpenCut

The original plan was to drive [OpenCut](https://github.com/OpenCut-app/OpenCut)
programmatically. It cannot be done today. OpenCut is mid-rewrite: the Editor
API, MCP server, headless mode and scripting tab are all on the roadmap, none
are built. The shipping version (`opencut-classic`) is archived, browser-only,
and stores projects in IndexedDB with no exportable project format — there is
no machine entry point at all.

So the renderer here is FFmpeg. It is genuinely free, has no licence
threshold, and does everything this format needs. OpenCut is still useful as
the manual finishing tool when a rendered video needs a human touch.

[Remotion](https://www.remotion.dev/) is the upgrade path if the visuals ever
need to get more ambitious. Note its licence: free for individuals and
companies of 3 or fewer employees, commercial use included, paid above that.

## Install

```bash
pip install -r requirements.txt
```

FFmpeg must be on `PATH`. If it isn't, point `FFMPEG_BINARY` at the binary:

```bash
export FFMPEG_BINARY=/path/to/ffmpeg
```

## The format

Every video follows the same four-part structure, because it is the structure
that holds retention on vertical video:

| part | job |
|---|---|
| **hook** | ~2s. Pose a question. Never mention the prize — that is the payoff, not the intro. |
| **beats** | The setup, escalating. 3–4 of them. |
| **twist** | The single most surprising fact. Gets its own colour so it lands visually first. |
| **kicker** | Reframe the absurdity as legitimate science. This is what makes it shareable. |

Visuals are typographic — generated cards plus word-by-word captions. Nothing
is scraped, stock, or AI-generated, so no clip in the output carries a
copyright question. **Do not use footage from the official Ig Nobel ceremony**;
it belongs to the *Annals of Improbable Research* and it is the fastest way to
get a growing channel taken down.

## Voiceover

Off by default — with no API key the video renders captions-only, which is a
perfectly normal format on these platforms. Set one key and it turns on:

```bash
export OPENAI_API_KEY=...        # or ELEVENLABS_API_KEY=...
python scripts/make_video.py --prize polyester-rats
```

Each segment is synthesised separately, and the video is then **re-timed to
the real audio** rather than to the word-count estimate — so captions stay in
sync, and one bad line can be regenerated without redoing the video.

Word timings within a segment are interpolated from word length. That is
accurate enough for karaoke captions. For frame-exact timing, run Whisper on
the generated voice track and overwrite `script.words`.

## Commands

```bash
python scripts/make_video.py --list                    # every prize in the dataset
python scripts/make_video.py --prize wombat-cubes --dry-run   # read the script first
python scripts/make_video.py --prize wombat-cubes             # render one
python scripts/make_video.py --all                            # render everything
python scripts/make_video.py --prize X --music bed.mp3        # add a music bed
```

Roughly 2–3 minutes of render time per video on a modest CPU. Batch overnight.

## The dataset

`data/prizes.json` ships with 30 hand-written prizes. Each carries the source
citation and a `verified` flag.

**Only `polyester-rats` is source-verified** (against PubMed: Shafik A, *Effect
of different types of textiles on sexual activity*, Eur Urol 1993, PMID
8262106). Every other entry is written from model knowledge and is marked
`unverified`. `--list` flags them with `?`, and the renderer prints a warning.

Check facts before publishing. A science channel survives on being right.

To expand toward the full ~350 prizes:

```bash
python scripts/fetch_winners.py --check    # audit the seed entries
python scripts/fetch_winners.py --merge    # append everything missing
```

That script needs open network access (it was written blind — the build
container blocks improbable.com — so expect to adjust `PRIZE_RE` if the page
layout has moved). Merged entries arrive with empty `hook`/`beats`/`twist`:
they are raw material, and writing those four fields is the actual creative
work.

## Layout

```
data/prizes.json          source material, one record per prize
pipeline/
  theme.py                colours, type, safe areas — edit this to rebrand
  models.py               Prize, Segment, Word, VideoScript
  script_writer.py        prize -> timed segments and word timings
  visuals.py              background cards (Pillow)
  captions.py             word-by-word ASS caption track
  tts.py                  pluggable voiceover
  render.py               FFmpeg assembly
  publish.py              title, description, hashtags
scripts/
  make_video.py           CLI
  fetch_winners.py        dataset scraper
out/                      rendered videos (gitignored)
```

Rebranding is `pipeline/theme.py` alone — palette, fonts, caption size and
position, platform safe areas.
