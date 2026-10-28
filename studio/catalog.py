"""
What the 3D engine can do, in one place, for the writer prompt and for
validating stories before anything is rendered. Keep in sync with
blender/sets.py, blender/character.py and blender/props.py.
"""
SETS = {
    "bedroom": {
        "about": "Small Indian bedroom: bed on the left, study desk with lamp, window with curtains. Camera looks toward +Y.",
        "moods": ["night", "day"],
        "anchors": {"bed_sit": "sitting on the bed edge (use pose sit…)", "bed_lie": "on the bed",
                    "desk_chair": "sitting at the study desk (pose sit…)", "door_spot": "standing near the door",
                    "centre": "standing in the middle of the room"},
        "camera_hint": {"pos": [0.3, -1.4, 1.2], "lens": 45},
    },
    "classroom": {
        "about": "Kota coaching classroom: whiteboard with formulas and 'JEE 2027', TARGET AIR 1 poster, 3 rows × 3 benches, "
                 "tube lights, ceiling fans. Students face +Y (the board); the teacher faces -Y (facing 0).",
        "moods": ["day", "night"],
        "anchors": {"board": "in front of the board", "teacher": "teacher's spot by the desk", "door_spot": "back of the room",
                    "aisle": "standing in the aisle",
                    **{f"seat_{r}_{c}{s}": f"bench row {r} column {c} seat {s} (pose sit…, facing 180)"
                       for r in range(3) for c in range(3) for s in "ab"}},
        "camera_hint": {"pos": [1.2, -2.6, 1.6], "lens": 30},
    },
    "stairwell": {
        "about": "Housing-society stairwell: two-tone walls, 10 steps up toward +Y to a landing with a flat door, meter box, "
                 "grilled window, one tube light. Walking up: walk_to from stairs_bottom to stair_mid / stairs_top.",
        "moods": ["night", "day"],
        "anchors": {"stairs_bottom": "foot of the stairs", "stair_mid": "halfway up", "stairs_top": "top of the stairs",
                    "door_front": "on the landing in front of the flat door"},
        "camera_hint": {"pos": [0.9, -2.2, 0.7], "lens": 32},
    },
}
POSES = ["stand", "sit", "phone", "sad", "wave"]  # combine with '+', e.g. "sit+phone", "stand+sad"
EXPRESSIONS = ["open", "happy", "tired", "sad", "angry", "closed"]
PROPS = ["phone", "book", "bag"]
CAMERA_MOVES = ["push", "pull", "drift", "rise", "static"]
OVERLAYS = ["clock", "phone"]
SFX = ["buzz", "sting", "boom"]
VOICES = {"hm_omega": "male, deeper", "hm_psi": "male", "hf_alpha": "female", "hf_beta": "female, softer"}


def validate(story, cast):
    """Returns a list of problems (empty if the story can be rendered)."""
    errs = []
    if "narrator" not in story.get("voices", {}):
        errs.append("voices must include 'narrator'")
    for k, sc in enumerate(story.get("scenes", [])):
        where = f"scene {k}"
        for ln in sc.get("lines", []):
            if ln.get("who") not in story.get("voices", {}):
                errs.append(f"{where}: no voice for speaker '{ln.get('who')}'")
        if "card" in sc:
            continue
        s = SETS.get(sc.get("set"))
        if not s:
            errs.append(f"{where}: unknown set '{sc.get('set')}'")
            continue
        if sc.get("mood", s["moods"][0]) not in s["moods"]:
            errs.append(f"{where}: mood must be one of {s['moods']}")
        for a in sc.get("actors", []):
            if a.get("who") not in cast:
                errs.append(f"{where}: '{a.get('who')}' is not in the cast")
            at = a.get("at")
            if isinstance(at, str) and at not in s["anchors"]:
                errs.append(f"{where}: anchor '{at}' not in set {sc['set']}")
            for p in [a.get("pose", "stand")] + [x["pose"] for x in a.get("actions", []) if "pose" in x]:
                for part in p.split("+"):
                    if part not in POSES:
                        errs.append(f"{where}: unknown pose '{part}'")
            for e in [a.get("expr", "open")] + [x["expr"] for x in a.get("actions", []) if "expr" in x]:
                if e not in EXPRESSIONS:
                    errs.append(f"{where}: unknown expression '{e}'")
            if a.get("prop") and a["prop"] not in PROPS:
                errs.append(f"{where}: unknown prop '{a['prop']}'")
            for x in a.get("actions", []):
                w = x.get("walk_to")
                if isinstance(w, str) and w not in s["anchors"]:
                    errs.append(f"{where}: walk_to anchor '{w}' not in set")
        cam = sc.get("camera", {})
        if "pos" not in cam:
            errs.append(f"{where}: camera needs pos")
        if cam.get("move", "push") not in CAMERA_MOVES:
            errs.append(f"{where}: camera move must be one of {CAMERA_MOVES}")
        o = sc.get("overlay")
        if o and o.get("type") not in OVERLAYS:
            errs.append(f"{where}: overlay type must be one of {OVERLAYS}")
        for e in sc.get("sfx", []):
            if e.get("name") not in SFX:
                errs.append(f"{where}: sfx must be one of {SFX}")
    return errs
