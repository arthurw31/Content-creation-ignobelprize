# Remotion vs HyperFrames — measured, not read

Both engines rendering the **same** 8-second Vox-style shot: 1080×1920, 30fps,
two archive photos with Ken Burns moves, a lower third that slides in and out,
a wipe transition, a stat that counts 0→75 with a growing bar, a punch-in twist
card, a caption rail and a progress bar.

Run on 4 cores / 15.7 GB RAM. Sources for both compositions are in this folder.

## Results

| | Remotion 4.0.512 | HyperFrames 0.7.110 |
|---|---|---|
| `npm install` | 23s · 245 packages · **247 MB** | 31s · 138 packages · **695 MB** |
| Browser setup | **Failed unattended.** Auto-download errored; regular Chrome rejected ("old Headless mode has been removed"); needed an explicit `--browser-executable` pointing at `headless_shell` | **Worked first try.** Downloaded its own Chrome (114 MB) with no intervention |
| Cold render | **52.4s** (includes bundling) | **34.3s** |
| Warm render | **26.8s** | **29.7s** |
| Output | 3.0 MB · 2993 kb/s | 1.9 MB · 1936 kb/s |
| Source size | ~260 lines TSX across 4 files + tsconfig | ~140 lines in 1 HTML file |
| Pre-render validation | none built in | `lint`, `check`, `validate`, `inspect`, `snapshot`, `compare` |
| Licence | Source-available. Free for ≤3 employees, paid above | **Apache 2.0**, no threshold |

Output size favours HyperFrames, but that is an encoder-preset difference, not
a quality gap. Both look effectively identical — see `side-by-side` frames.

Warm render is a tie. The cold-render gap is Remotion's bundling step, which
you pay once per session, not per video.

## The finding that actually mattered

I made a genuine mistake in the HyperFrames composition: GSAP's `xPercent`
overwrote the CSS `translate(-50%, -50%)` centring on the panning photo, which
left a **black band down the left edge** from t≈4s.

`hyperframes check` found it without being asked:

```
ℹ t=4s  container_overflow #p2 inside #s2 overflowed right 828.2px
✗ t=4.63-6.13s (15 samples) content_overlap #count inside div.stat-label "75"
   Two text blocks overlap and may render unreadable.
◇ Contrast: 14/14 text checks pass WCAG AA
```

It samples the timeline, inspects layout geometry at each sample, checks motion,
and runs WCAG contrast on every text element. `lint` had already caught two
structural errors *before* the first render (overlapping clips on one track, a
missing `data-start` on the root).

Remotion has no equivalent. You find that black band by watching the MP4.

**This is the decisive difference for an agent-driven pipeline.** It is the
difference between Claude rendering blind and Claude rendering, checking, and
fixing its own output before you ever see it.

## Other things measured along the way

- 536 MB of the HyperFrames install is `onnxruntime-node` — it ships local
  Whisper transcription, local TTS (Kokoro), local music generation (MusicGen)
  and beat detection. Heavy, but it covers voiceover, captions and beat-synced
  cutting without a single API key.
- HyperFrames has a `/faceless-explainer` workflow — arbitrary text → 60–90s
  faceless explainer. That is exactly this channel's format.
- Telemetry is **on by default**. Turn it off: `hyperframes telemetry disable`.
- HyperFrames reported `static-frame dedup: disabled (tl.call() side effect
  (not seek-safe))`. Using `tl.call()` for caption swaps cost a real
  optimisation; a seek-safe approach would render faster.
- Remotion's `interpolate`/`spring` gave exact control over transform
  composition. GSAP's implicit transform handling is where the bug came from.
  Remotion's model is more predictable; HyperFrames' is faster to write.

## Reproducing

```bash
# HyperFrames
cd hyperframes && npm i hyperframes gsap
npx hyperframes lint && npx hyperframes check
npx hyperframes render --output out.mp4

# Remotion
cd remotion && npm i
npx remotion render src/index.ts bench out.mp4 \
  --browser-executable=/path/to/chrome-headless-shell
```

Needs `ffmpeg` **and** `ffprobe` on `PATH` — HyperFrames checks for both and
refuses to start without them.
