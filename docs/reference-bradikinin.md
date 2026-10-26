# Reference breakdown: Bradikinin (@BradikininVideos)

Ten uploads (Oct 11 – Oct 25, 2026), measured with `scripts/analyze_reference.py`
plus frame strips at 0.25 s steps.

## Per-video numbers (upload order)

| File | Length | Shots | Median shot | Cuts/min | Glitch shots | Captions on screen |
|---|---|---|---|---|---|---|
| Dog stands on two legs | 4:33 | 20 | 10.2 s | 4.4 | 4 | 42 % |
| GTA 6 | 5:33 | 50 | 5.0 s | 9.0 | 21 | 46 % |
| Old phone, no SIM | 5:43 | 60 | 3.3 s | 10.5 | 13 | 24 % |
| Cat watches you sleep | 6:37 | 92 | 3.0 s | 13.9 | 16 | 30 % |
| Phone charges to 101 % | 4:41 | 46 | 3.9 s | 9.8 | 8 | 32 % |
| Dog throws the ball | 4:49 | 24 | 6.1 s | 5.0 | 2 | 52 % |
| Uber drives past | 5:37 | 91 | 2.4 s | 16.2 | 10 | 28 % |
| Screen time 25 h | 5:09 | 45 | 4.5 s | 8.7 | 7 | 34 % |
| MrBeast offers money | 8:56 | 183 | 2.3 s | 20.5 | 33 | 25 % |
| Spider disappears | 5:44 | 54 | 3.8 s | 9.4 | 11 | 45 % |

Static (locked-off) time is 0–2 % in every file. Audio sits around −19 dB
median, about 5 dB louder than Last Soul. Narration is chopped into short
lines with frequent 0.4–0.75 s pauses (20 such pauses in the first minute of
the dog file).

Our File 001 for comparison: median shot 16 s, 3.8 cuts/min, 46 % static,
beige background.

## Visual system

- **Black void.** 65–80 % of every frame is near-black `#010101`. Pictograms are
  solid white fills with a soft glow (bloom), with no outlines. Shapes are
  rounded and chunky: round heads, rounded furniture.
- **Accent colours used sparingly:** warm yellow for light sources (moon,
  lamp, flashlight cone, map pin), red for danger (X, "people who failed",
  and the whole frame tinted red at the climax), green for safe (check, arrow).
- **Tape HUD on every frame.** Top-left: `FILE 041 // BRADIKININ`, small,
  grey, letter-spaced. Top-right: a running timecode (`00:00:25:00`).
  Top-centre (later files): seven small boxes that show which rule is active.
- **Captions.** Every narrated line appears centred in the lower third, in
  uppercase white geometric sans (Montserrat-like semibold), slightly
  letter-spaced, one line at a time, synced to the voice.
- **Rule title cards** (later files): `RULE [4]` large with the number boxed,
  the rule name typed on letter by letter, a red underline, the seven-box
  progress bar, then the spoken rule as a caption.
- **"Exhibit" inserts.** Real black-and-white photos in a slightly tilted
  white print frame with corner brackets, plus a label with a red bar
  (`EXHIBIT B / YEAR: 1910 / STATUS: WATCHING`). Real evidence mixed into
  the fiction.
- **The Agent.** A narrator-character pictogram (sunglasses, tie, sometimes
  behind a desk) who breaks the fourth wall ("That… that was not in the
  file."), with flying papers and sweat drops. This is the comic relief.
- **Data shots.** Big numbers (`1,457 MORNINGS`), rows of white and red
  figures for statistics, a five-panel sequence (moon phases over five
  nights), and mock phone UI (Uber map, timer `10:14`).

## Motion grammar

- **Nothing is ever still.** Every shot has a slow push-in (about 5–10 % scale
  over the shot).
- **Characters are actually animated:** walk cycles (figure carrying a pillow
  to the couch), thought bubbles that pop in behind small trailing circles,
  dotted "stare" lines that draw on, lights that warm up.
- **Glitch on the key lines.** An RGB split, horizontal tearing and scanline
  streaks for 2–6 frames on the most important sentences ("And do not let it
  see that you noticed.").
- **One shot per narrated line** in later files, so cutting speeds up with the
  narration.
- **The climax recolours the scene red,** then cuts straight to the next shot.

## How the channel evolved

The first file had 4.4 cuts/min with 10 s shots; the ninth had 20.5 cuts/min,
2.3 s shots and ran almost 9 minutes. Pacing, length and glitch use rise over
the two weeks. The rule title cards and the progress HUD appear after the
first file.

## What to adopt, and what to keep different

Adopt the motion grammar: one shot per line, a constant push-in, glitch on
key lines, rule title cards with progress, synced uppercase captions, data
shots and evidence inserts, an accent colour system, and a red climax.

Keep our own identity: the beige safety-manual paper look (or a dark variant
with our own HUD wording), the Bureau and file branding, our own narrator
gimmick instead of the Agent, and our own insert format instead of "Exhibit".
