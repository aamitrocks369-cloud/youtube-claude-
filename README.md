# Occupational Anomaly Bureau: instruction-file episodes

Pictogram analog-horror "training files". Each episode is a JSON script. The
build pipeline synthesizes the narration offline (Piper TTS) phrase by phrase,
times every visual beat to the real audio, renders the animated pictogram
scenes, mixes tape-style sound design, and encodes the MP4 and thumbnail.

## Build (current renderer: v3)

    pip install piper-tts numpy pillow scipy     # ffmpeg must be on PATH
    # voice: Piper "ryan medium" (US male)
    curl -L -o ryan.tar.gz https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-en-us-ryan-medium.tar.gz
    mkdir -p voices && tar xzf ryan.tar.gz -C voices/
    python3 scripts/build_episode_v3.py episodes/001-elevator/episode_v3.json \
        --voice voices/en-us-ryan-medium.onnx --out build/001
    # add --preview for a fast half-resolution, 12 fps check

Outputs: `fileNNN_v3.mp4`, `thumbnail_v3.jpg`, `master.wav`, and
`timeline.json` (exact start and end of every spoken phrase).

## Writing an episode (v3 format)

Copy `episodes/001-elevator/episode_v3.json`. An episode is a list of
segments (cold open, intro, rules 1–7, outro). Each segment holds **beats**,
and one beat is one spoken phrase with one visual:

```json
{"text": "Do not confirm it.",
 "beat": "elevator",
 "args": {"display": "13", "doors": "open", "you": "step_back", "x": true,
          "cam": [960, 620, 1.25]},
 "glitch": true}
```

- Keep phrases short (2–8 words). Every phrase is a new picture, which is
  what sets the pace.
- `cam` is `[x, y, zoom]` in the 1920×1080 world. Use 1.0 for wide, about
  1.5 for medium and about 2 for close.
- Sets: `lobby`, `elevator`, `hallway`, `office`. Each takes a `you` action:
  `walk_in`, `look_up`, `nod`, `step_back`, `ears`, `hunch`, `read`,
  `freeze`, `run`.
- Formats: `rule_card`, `display_close`, `face`, `card_write`, `wallet`,
  `people_row`, `card_vs_panel`, `hallway_compare`, `button`, `stat`,
  `org_chart`, `counter`, `counter_loop`, `number_row`, `eye`,
  `building_floors`, `evidence` (surveillance record), `officer` (the
  Compliance Officer), `voice_bubble`, `end_card`.
- `"red": true` turns the frame red (use it for the twist only).
  `"silence_before": true` on a segment cuts to black and silence before it.

## Tools

- `scripts/analyze_reference.py VIDEO`: shot list, pacing, motion and palette,
  plus a contact sheet.
- `scripts/audit_metrics.py OUT.json VIDEO…`: same-scale style metrics for
  comparing against reference channels.
- `docs/`: reference breakdowns and the difference audit.
