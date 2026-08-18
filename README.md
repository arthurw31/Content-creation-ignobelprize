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

### The easy way (no terminal)

1. Download the repository: green **Code** button on GitHub -> **Download ZIP**.
2. Unzip it.
3. Double-click **`start.bat`** (Windows) or **`start.command`** (Mac).

That script checks Python, builds an isolated environment, installs FFmpeg,
asks for your OpenRouter key, tests it, and offers to render. It spends
nothing without asking.

The only prerequisite is Python 3.10+. If it is missing the script says so and
links the installer. On Windows, tick **"Add Python to PATH"** during that
install.

### The manual way

```bash
pip install -r requirements.txt
```

FFmpeg arrives with `imageio-ffmpeg`, so nothing extra is needed. To use your
own build instead, point `FFMPEG_BINARY` at it:

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

## AI-generated clips

The typographic version above needs no keys and no network. The AI version
replaces the cards with generated footage, via OpenRouter:

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
python -m pipeline.aiclip.openrouter --probe            # check the key first
python scripts/make_ai_video.py --prize polyester-rats --dry-run
python scripts/make_ai_video.py --prize polyester-rats --budget 8
```

Style coherence across a 30s video is enforced structurally, not by prompt
luck. See `pipeline/aiclip/style.py` — one locked style suffix on every
prompt, image-to-video rather than text-to-video, reference sheets for
recurring subjects, one seed, and a single colour grade over all clips.

Spending is gated. `--dry-run` generates nothing; `--budget` refuses to start
above its cap; every intermediate is cached so a failed run resumes instead of
paying twice.

**Verify `openrouter.py` before trusting it.** openrouter.ai was unreachable
from the machine it was written on, so the request shapes follow the
documented conventions but were never run against the live API. `--probe`
reports what the API actually returns and which fields need adjusting.

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
  aiclip/
    style.py              the style bible — locked look, seed, subjects
    plan.py               script -> shot list for the generative models
    openrouter.py         video / image / speech client (run --probe first)
    produce.py            sheets -> stills -> clips -> grade -> assembly
scripts/
  make_video.py           CLI, typographic version
  make_ai_video.py        CLI, AI-clip version
  start.py                all-in-one launcher used by start.bat/.command
  fetch_winners.py        dataset scraper
start.bat / start.command double-click entry points
out/                      rendered videos (gitignored)
```

Rebranding is `pipeline/theme.py` alone — palette, fonts, caption size and
position, platform safe areas.
