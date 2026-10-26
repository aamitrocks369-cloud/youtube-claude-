# Reference breakdown: Bradikinin (@BradikininVideos)

Ten uploads (Oct 11 – Oct 25, 2026), measured with `scripts/analyze_reference.py`
plus frame strips at 0.25 s steps.

## Per-video numbers (upload order)

"Picture changes" counts hard cuts plus new elements popping into the
frame. Glitch flashes that revert within 0.4 s are excluded. The first version
of this table used a fixed threshold that missed most changes on near-black
frames and wrongly suggested he had sped up from 4 to 20 per minute. The
corrected detector shows he has been fast from the first file.

| File | Length | Picture changes | Median hold | Per minute |
|---|---|---|---|---|
| Dog stands on two legs | 4:33 | 90 | 2.6 s | 19.8 |
| GTA 6 | 5:33 | 119 | 2.3 s | 21.4 |
| Old phone, no SIM | 5:43 | 132 | 2.3 s | 23.1 |
| Cat watches you sleep | 6:37 | 153 | 2.2 s | 23.1 |
| Phone charges to 101 % | 4:41 | 106 | 2.2 s | 22.7 |
| Dog throws the ball | 4:49 | 100 | 2.5 s | 20.7 |
| Uber drives past | 5:37 | 135 | 2.2 s | 24.1 |
| Screen time 25 h | 5:09 | 120 | 2.2 s | 23.3 |
| MrBeast offers money | 8:56 | 234 | 2.1 s | 26.2 |
| Spider disappears | 5:44 | 110 | 2.4 s | 19.2 |

Same detector on the others: Last Soul 17–19 per minute (median hold
3.0–3.3 s). Our File 001 v1: 10.0 per minute (5.5 s). File 001 v2: 11.7 per
minute (4.8 s).

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

Pacing was already about 20 changes per minute in the first file and rose
only slightly (26 per minute in the 9-minute MrBeast file). What did change:
the rule title cards and the progress HUD appear after the first file, and
the videos get longer.

## What to adopt, and what to keep different

Adopt the motion grammar: one shot per line, a constant push-in, glitch on
key lines, rule title cards with progress, synced uppercase captions, data
shots and evidence inserts, an accent colour system, and a red climax.

Keep our own identity: the beige safety-manual paper look (or a dark variant
with our own HUD wording), the Bureau and file branding, our own narrator
gimmick instead of the Agent, and our own insert format instead of "Exhibit".
