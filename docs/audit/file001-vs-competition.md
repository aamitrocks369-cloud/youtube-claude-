# Difference audit: File 001 (animated) vs Bradikinin and Last Soul

Inputs: `file001_animated.mp4`, all 10 Bradikinin files, and both Last Soul
files. Every video was decoded at the same size and frame rate
(`scripts/audit_metrics.py` and `scripts/analyze_reference.py`). Bradikinin
figures are the median of 10 files, with the range in brackets. The matched
visual comparison is in `side_by_side.jpg`.

## 1. Measurements

| Metric | File 001 | Bradikinin | Last Soul | Verdict |
|---|---|---|---|---|
| Length | 2:54 | 5:35 (4:33–8:56) | 3:25 | **Half his length** |
| Picture changes per minute | 12.1 | 22.9 (19.2–26.2) | 18.1 | **Half his pace** |
| Median hold | 4.6 s | 2.25 s | 3.15 s | **2× too long** |
| Glitch hits per minute | 0.35 | 4.2 (2.7–7.2) | 0.9 | **12× too few** |
| Still-frame share | 14 % | 3 % (0–10 %) | 19 % | Close |
| Frames with any motion | 94 % | 61 % | 79 % | Ours is mostly camera drift (see 2.3) |
| Ink on screen | 6.3 % | 12 % (7–17 %) | 62 % | **Scenes too small / empty** |
| Solid white on screen | 2.1 % | 6.2 % (4.4–9.2 %) | — | **Figures too thin / small** |
| Glow halo per bright pixel | 2.18 | 1.14 | — | **Glow ~2× too strong** |
| Frame area used (4×4 grid) | 56 % | 75 % (69–88 %) | 100 % | **Compositions too centred** |
| Frames containing red | 40 % | 11 % (4–27 %) | 28 % | **Red overused ~4×** |
| Yellow pixels | 0.02 % | 0.15 % | 0.69 % | **Yellow underused ~7×** |
| Captions on screen | 50 % | 33 % | 6 % | Ours never leaves the screen |
| Loudness (voiced) | −18.6 dB | −16.1 dB | −16.8 dB | **2.5 dB too quiet** |
| Speech share | 57 % | 46 % | 16 % | Ours talks more and breathes less |
| Pauses ≥ 0.4 s per minute | 19.7 | 26.6 | 13.1 | Ours has fewer, longer phrases |

## 2. Visual differences (see `side_by_side.jpg`)

### 2.1 Figure design (biggest visual gap)
- **His** figure is a clean white body with **black separation lines**, so an
  arm crossing the torso, a hand holding a pillow or a bent knee all read
  clearly. There is a visible neck gap, even limb thickness, crisp edges and
  only a light glow. Props are held in the hands.
- **Ours** is a single glowing blob. The limbs merge into the torso, the glow
  smears the head into the body, and nothing is held.
- **Fix:** draw a 4–6 px black outline around every limb and the head
  before filling (stroke-then-fill), add a neck gap, cut the glow strength
  roughly in half, and add hand-held props (badge, phone, card, pillow).

### 2.2 Sets, not voids
- **His** shots sit on a **ground line inside a dressed room** (bed, window
  with curtain, door, picture frame, cobweb, clothes on the floor). One set is
  reused from many angles across a file, so viewers learn the space.
- **Ours** is one figure and one prop floating in black, with no floor and
  no room.
- **Fix:** build 3 reusable sets for File 001 (elevator car, hallway, office
  desk) with a floor line and 4–6 props each, and stage most shots inside
  them. This alone roughly doubles ink coverage and frame usage.

### 2.3 What moves
- **His** motion is local and purposeful: the figure walks, a bubble pops,
  a line draws on, and the camera is still between actions (61 % of frames
  move).
- **Ours** drifts the whole frame constantly (94 % of frames move) while
  characters often stand idle. The drift feels floaty, not alive.
- **Fix:** reduce camera drift to near zero, keep the slow push-in, and spend
  the motion budget on two character actions per line.

### 2.4 Faces and close-ups
- **His** close-ups are of the **character's face**: a round head with
  simple line eyes (closed, open, wide) and expressions that carry the beat.
- **Ours** uses an abstract eye. Our figures have no faces at all.
- **Fix:** give the head 3–4 eye states (dots, lines, wide, closed) and add
  a face close-up for each key reaction.

### 2.5 Captions
- **His** captions are short phrases (5–8 words, at most 2 lines), larger
  type placed just under the scene, and shown only while the line is spoken.
- **Ours** shows full sentences of up to 17 words, pinned to the bottom edge
  and on screen 50 % of the time.
- **Fix:** split narration into phrases, show one phrase per beat (this also
  doubles picture changes), raise the type size about 10 %, move it up about
  60 px, and hide it in pauses.

### 2.6 Rule card
Very close already. His rule card keeps the spoken line as a caption under
the card, puts the red underline under `RULE 4` (not under the name), and
uses larger progress boxes. Small fixes.

### 2.7 Things he has that we don't
- **Evidence inserts:** real archival photos in a tilted print frame with a
  labelled tag.
- **A recurring narrator character** (the Agent) for comic relief and
  fourth-wall breaks.
- **Thought bubbles,** and fake phone or app screens.
- **Sequence panels** (the same scene over five nights).

## 3. Priority fixes (impact ÷ effort)

| # | Fix | Closes |
|---|---|---|
| 1 | Split narration into short phrases, one visual beat each | Pace (12 → ~22/min), caption length, pause rhythm |
| 2 | Figure redraw: black separation strokes, neck gap, eye states, props, half glow | Figure design, glow, faces |
| 3 | Three reusable dressed sets with a ground line | Empty frames, ink and frame use |
| 4 | Glitch on 3–4 lines per minute, not one per section | Glitch frequency |
| 5 | Colour rebalance: red only for danger and the twist; yellow for every light source | Red overuse, yellow underuse |
| 6 | Kill camera drift; two character actions per line | What moves |
| 7 | Script to ~4:30 (2 more lines per rule), master to −16 dB | Length, loudness |
| 8 | Add an evidence-insert format and a narrator character of our own | Missing formats |
