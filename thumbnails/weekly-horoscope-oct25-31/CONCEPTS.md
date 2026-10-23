# Thumbnail concepts — "25th Oct to 31st October Weekly Horoscope - ALL 12 Signs | Jupiter Big Transit in Leo"

Three finished variants are rendered next to this file (`thumbnail_a/b/c.png` at
1920x1080 for archive, `thumbnail_a/b/c.jpg` at 1280x720 ready to upload — all
under YouTube's 2 MB limit). Regenerate or tweak with:

    python3 thumbnails/make_horoscope_thumbnail.py --variant all

## Shared design rules

- **Three-second read.** One hero phrase ("JUPITER IN LEO"), one supporting
  phrase ("WEEKLY HOROSCOPE"), one promise ("ALL 12 SIGNS"), one date. Nothing
  else competes.
- **Hierarchy by size, not by count.** Hero text is 3–4x the date pill. The
  red "BIG TRANSIT" tag is the only saturated red on the canvas, so the eye lands
  there second.
- **Palette.** Deep navy/violet cosmos + metallic gold text + one red accent.
  Gold-on-dark is the highest-contrast combo that still reads "astrology" rather
  than "finance". White (slightly blue-tinted) is used only for the secondary
  line so the gold hero stays dominant.
- **Leo is always highlighted.** In every variant the Leo glyph ♌ is the one
  sign in a filled gold disc with a glow; the other eleven are outlined. A
  returning viewer sees "this week is about Leo" before reading a word.
- **Safe zones.** Nothing important in the bottom-right corner (YouTube's
  duration badge) and 60 px of breathing room on every edge.
- **Procedural art, no stock.** Jupiter is a shaded, banded sphere with the
  Great Red Spot, lit from the text side so the planet's bright limb points at
  the headline.

## Variant A — "Jupiter on the Wheel" (recommended default)

Left: date pill → WEEKLY HOROSCOPE → giant gold JUPITER / IN LEO ♌ → gold
ALL 12 SIGNS bar → strip of all twelve glyphs. Right: large Jupiter inside a
zodiac ring with Leo lit up at the top-left of the ring, pointing at the
headline; red BIG TRANSIT tag under the planet.

Why it works: the ring literally shows "Jupiter is in the zodiac, and Leo is
the one that's lit". Most information-dense while still reading at feed size.
Best for subscribers who watch every week and scan for the transit.

## Variant B — "Leo Sun Emblem"

Warm magenta/maroon sky. Huge white WEEKLY HOROSCOPE as the hero, a radiant
gold sun-mane disc (Leo is ruled by the Sun) carrying the ♌ glyph, and a small
Jupiter sweeping in along a glowing arrow into the sun. Bottom line in gold:
JUPITER ENTERS LEO with the red BIG TRANSIT tag.

Why it works: boldest silhouette of the three — the sun-burst is readable
even at 120 px. Best for browse/suggested traffic where the viewer is not yet
a subscriber and just needs "weekly horoscope" + a striking symbol.

## Variant C — "All Twelve Signs"

A labelled row of all twelve signs across the top (Leo highlighted), the
hero text block lower-left, and a very large Jupiter bleeding off the right
edge with a Leo medallion overlapping it.

Why it works: delivers on the "ALL 12 Signs" promise visually — every viewer
can spot their own sign in the thumbnail. Best when the audience is mixed and
the "Jupiter in Leo" hook is secondary to "my sign this week".

## Suggested A/B plan

1. Publish with **A**. It carries the most specific hook (the transit) and the
   wheel differentiates it from generic weekly-horoscope thumbnails.
2. If CTR is below the channel's weekly-video average after ~48 h, swap to
   **B** (strongest silhouette) for the next 48 h.
3. Keep **C** for the Community post / Shorts teaser, where the row of signs
   invites comments ("Leo gang ♌").

## Quick customisation ideas

- Swap the headline to a sign-specific hook ("LEO, YOUR LUCK TURNS") for
  sign-cut Shorts: change the `fancy_text` strings in the variant function.
- Add the host: paste a cut-out photo at roughly x 1000–1350 in variant B
  (between the headline and the sun) — the layout already leaves that gap.
- Localise the date pill text; everything is plain strings in the script.
