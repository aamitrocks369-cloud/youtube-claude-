# Reference breakdown: Last Soul (@lastsoulorigin)

Measured with `scripts/analyze_reference.py` on two uploads:

| | *Just 5 More Minutes (It's 2:14 AM)* | *I Told Mom I Had Friends. I Had None.* |
|---|---|---|
| Length | 3:13 | 3:37 |
| Format | 1920×1080, 30 fps | 1920×1080, 30 fps |
| Shots | 41 | 49 |
| Median shot | 3.5 s | 3.6 s |
| Cuts per minute | 12.7 | 13.6 |
| Static holds | 7 % of runtime | 12 % |
| Slow camera drift / subtle motion | 67 % | 72 % |
| Full motion | 26 % | 16 % |
| Frames that change, per second | 29 / 29 (animated on 1s) | 29 / 29 |
| Dominant colours | `#0b0c0f` `#292628` `#4e4d4c` `#8e806f` `#cec2af` | `#48413f` `#2a2626` `#6a5f5a` `#080708` `#95877e` |
| Audio loudness | −24 dB median, dull (745 Hz centroid) | −23 dB median, 900 Hz centroid |

For comparison, our File 001: median shot 16 s, 3.8 cuts/min, 46 % static.

## Technique

- **3D, not 2D.** Real-time-style render (Blender Eevee or similar): soft lighting,
  ambient occlusion, shadows, depth of field, vignette, gentle film grade.
- **One character rig, re-dressed.** Matte black sphere head, white oval eyes,
  eyelids and brows for every emotion, no mouth, a thin light rim around the
  head. Tube limbs, black cartoon hands. Identity comes from one accessory:
  headband, cap, hair bun with scrunchie, sun hat with glasses.
- **Detailed reusable sets.** Gym, bedroom, apartment hallway and elevator,
  bus stop, rooftop. Each set is reused across many shots.
- **Camera never stops.** Almost every shot has a slow push, drift or pan;
  only ~10 % of runtime is locked off. Shots are short (3–4 s) and alternate
  wide → over-the-shoulder → close-up → insert.
- **POV inserts as a signature.** First-person hands holding a phone with
  realistic UI (clock, alarm, messages, store page). The clock times carry the
  story (9:30 → 9:59 → 10:00 alarm → 2:14).
- **Dialogue is on-screen text.** A hand-lettered comic font placed next to
  the speaker, one colour per character (blue, red, orange). Inner thoughts are
  small italics. Theme lines are serif italics on full black cards
  ("Silence feels safer than small talk." / "Safer. Quieter. Lonelier.").
- **Colour arc.** The problem plays in dark, blue-grey night tones; the payoff
  shifts to warm gold (string lights, sunset, arena lights).
- **Story shape.** Habit → cost → low point → one mentor line → small change
  → payoff → callback to the opening image, all in about 3½ minutes.

## What to borrow for the Bureau files

1. Cut every 3–5 s instead of holding one picture per rule.
2. Add a slow push or drift to every shot.
3. Alternate shot sizes: wide, close-up, insert.
4. Add POV inserts: hands holding the badge or phone, or pressing the panel.
5. Add depth of field, vignette and a colour arc (cold during the rules,
   one warm "safe" shot in Rule 6, cold again for the Rule 7 twist).
