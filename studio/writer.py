#!/usr/bin/env python3
"""
Title → story.json, written by Claude through the Claude Code CLI on this
computer (`claude -p`), so it runs on the user's own Claude account.

    python3 studio/writer.py "शर्मा अंकल हर रात 2:14 बजे" --out studio/stories/002-x/story.json \
        [--length 45] [--genre horror|crime|tragedy] [--notes "…"]

The story is validated against what the 3D engine can actually render; if
anything is wrong, the errors go back to Claude for one repair round.
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import catalog  # noqa: E402

STYLE_GUIDE = """
You write 30–60 second vertical Shorts for a Hindi YouTube channel of 3D animated
tragedies, crime and horror stories set in ordinary Indian life (Kota coaching,
housing societies, night shifts, loan apps, family pressure). Same recurring
cast every episode. The look and editing copy the "Last Soul" formula:

1. Hook in the first 2 seconds: an exact time or an odd detail, in first person.
2. One ordinary routine, repeated (the viewer must learn the pattern).
3. A phone screen (chat) or a small detail that breaks the pattern.
4. The realisation, said in very few words.
5. A callback: the opening shot or line returns, now meaning something else.
6. End on a black card with 2–4 words (a command or a question) – no moral lecture.

Rules
- Simple spoken Hindi (Hinglish words are fine: shift, group, message). Short sentences.
- Every line of dialogue is ≤ 12 words; the narrator speaks in first person as the main character.
- 6–10 scenes. Each scene shows ONE thing. Reuse sets; vary camera angle and size.
- No emoji anywhere (the fonts cannot draw them). ₹ is fine.
- No real people, no real crimes, no suicide or self-harm, no gore. Suggest, don't show.
- Fictional and safe for advertisers, but genuinely unsettling or sad.
"""


def schema_text(cast):
    sets = json.dumps(catalog.SETS, ensure_ascii=False, indent=1)
    people = json.dumps({k: v.get("role", "") for k, v in cast.items()}, ensure_ascii=False, indent=1)
    example = open(os.path.join(HERE, "stories", "001-sharma-uncle", "story.json"), encoding="utf-8").read()
    return f"""
STORY FILE FORMAT (JSON). Return ONLY the JSON object, no prose, no code fence.
Top level: title (Hindi), title_en, language "hi", aspect "9:16", speed (0.9–1.0),
voices: speaker → one of {list(catalog.VOICES)} ({catalog.VOICES}); must include "narrator"
(usually the same voice as the main character), thumbnail_scene (index of the most striking scene),
scenes: list of scenes.

A 3D scene: set, mood, actors, camera, lines, optional overlay, sfx, min (seconds), line_start.
  actor: who (cast name), at (anchor name or [x,y,z]), facing (degrees; 0 faces the default camera at -Y,
         180 faces away toward +Y), pose (combine with +: {catalog.POSES}), expr ({catalog.EXPRESSIONS}),
         prop ({catalog.PROPS}), actions: list of {{t, pose}} {{t, expr}} {{t, look:[yaw,pitch]}} {{t, turn:deg}}
         {{t, walk_to: anchor, dur}}.
  camera: pos [x,y,z], look (actor name or [x,y,z]), lens (25–70), move ({catalog.CAMERA_MOVES}), amount (0.05–0.2).
  lines: list of {{who, text}} spoken in order (who = "narrator" or a cast name).
  overlay: {{"type":"clock","text":"2:14 AM","from":s,"to":s}} or
           {{"type":"phone","from":0,"to":99,"spec":{{"title":"…","time":"9:12",
             "messages":[{{"t":s,"from":"them"|"me","who":"(group only)","text":"…"}}]}}}}
  sfx: list of {{t, name}} with name in {catalog.SFX}.
A card scene (black screen with serif text): {{"card":{{"text":"…","sub":"…"}},"lines":[],"min":2.6}}

SETS (anchors and camera hints):
{sets}

CAST (use only these names):
{people}

EXAMPLE STORY:
{example}
"""


def ask_claude(prompt, model=None):
    cmd = ["claude", "-p", prompt, "--output-format", "text"]
    if model:
        cmd += ["--model", model]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise SystemExit("claude CLI failed: " + r.stderr[-2000:])
    return r.stdout


def extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    a, b = text.find("{"), text.rfind("}")
    return json.loads(text[a: b + 1])


def write_story(title, length=45, genre="horror", notes="", cast_name="default", model=None):
    cast = json.load(open(os.path.join(HERE, "cast", cast_name + ".json"), encoding="utf-8"))
    prompt = (STYLE_GUIDE + schema_text(cast) +
              f"\nWRITE A NEW STORY.\nTitle / idea: {title}\nGenre: {genre}\nTarget length: about {length} seconds"
              f"\nExtra notes: {notes or '-'}\n")
    story = extract_json(ask_claude(prompt, model))
    errs = catalog.validate(story, cast)
    if errs:
        fix = (prompt + "\nYOUR PREVIOUS ANSWER:\n" + json.dumps(story, ensure_ascii=False) +
               "\nIT HAS THESE PROBLEMS, FIX THEM AND RETURN THE WHOLE CORRECTED JSON:\n- " + "\n- ".join(errs))
        story = extract_json(ask_claude(fix, model))
        errs = catalog.validate(story, cast)
        if errs:
            raise SystemExit("story still invalid:\n- " + "\n- ".join(errs))
    return story


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("title")
    ap.add_argument("--out", required=True)
    ap.add_argument("--length", type=int, default=45)
    ap.add_argument("--genre", default="horror")
    ap.add_argument("--notes", default="")
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    story = write_story(a.title, a.length, a.genre, a.notes, model=a.model)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(story, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("wrote", a.out, f"({len(story['scenes'])} scenes)")


if __name__ == "__main__":
    main()
