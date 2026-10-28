"""
Render one shot from a JSON description to numbered PNG frames.

blender -b -P render_shot.py -- shot.json cast.json out_dir \
    [--engine CYCLES|BLENDER_EEVEE_NEXT] [--fps 24] [--scale 0.5] [--samples 24]

shot.json:
{
  "set": "bedroom", "mood": "night", "duration": 3.0, "aspect": "9:16",
  "actors": [{"who": "ravi", "at": "bed_sit", "facing": 55, "pose": "sit+phone",
              "expr": "tired", "prop": "phone", "actions": [...]}],
  "camera": {"pos": [0.3, -1.4, 1.2], "look": "ravi", "lens": 45, "move": "push", "amount": 0.15}
}
cast.json: {"ravi": {"shirt": [r,g,b], "pants": [...], "accessory": "headband", "accent": [...]}}
"""
import argparse
import json
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import animate  # noqa: E402
import character as ch  # noqa: E402
import props  # noqa: E402
import sets  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("shot")
    ap.add_argument("cast")
    ap.add_argument("out")
    ap.add_argument("--engine", default="CYCLES")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--still", type=float, default=None, help="render a single frame at this time (s)")
    a = ap.parse_args(argv)
    shot = json.load(open(a.shot))
    cast = json.load(open(a.cast))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    anchors = sets.SETS[shot["set"]](shot.get("mood", "night"))
    actors = {}
    for spec in shot.get("actors", []):
        look = cast[spec["who"]]
        j = ch.build_character(spec["who"], shirt=tuple(look["shirt"]), pants=tuple(look["pants"]),
                               accessory=look.get("accessory"), accent=tuple(look.get("accent", (0.9, 0.2, 0.2))),
                               hair=look.get("hair"))
        if spec.get("prop"):
            props.attach(spec["prop"], j)
        actors[spec["who"]] = (j, animate.ActorTrack(spec, anchors))

    cs = shot["camera"]
    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = cs.get("lens", 40)
    cam_d.dof.use_dof = cs.get("dof", True)
    cam_d.dof.aperture_fstop = cs.get("fstop", 2.8)
    cam = bpy.data.objects.new("cam", cam_d)
    bpy.context.collection.objects.link(cam)
    tgt = bpy.data.objects.new("cam_target", None)
    bpy.context.collection.objects.link(tgt)
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    cam_d.dof.focus_object = tgt

    sc = bpy.context.scene
    sc.camera = cam
    fps = a.fps
    n = max(1, round(shot["duration"] * fps))
    sc.render.fps = fps
    sc.frame_start, sc.frame_end = 1, n
    frames = range(1, n + 1)
    if a.still is not None:
        f = 1 + round(a.still * fps)
        frames = range(1, f + 1)  # key up to the frame so blends are right
        sc.frame_start = sc.frame_end = f
    for f in frames:
        for j, track in actors.values():
            animate.key_actor(j, track, f, fps)
        animate.key_camera(cam, tgt, cs, anchors, actors, f, fps, shot["duration"])
    for obj in bpy.data.objects:
        if obj.animation_data and obj.animation_data.action:
            for fc in obj.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"

    w, h = (1080, 1920) if shot.get("aspect", "9:16") == "9:16" else (1920, 1080)
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = int(a.scale * 100)
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.render.engine = a.engine
    if a.engine == "CYCLES":
        sc.cycles.samples = a.samples
        sc.cycles.use_denoising = True
        sc.cycles.device = "CPU"
        sc.cycles.max_bounces = 4
    else:
        sc.eevee.taa_render_samples = a.samples
    sc.render.image_settings.file_format = "PNG"
    os.makedirs(a.out, exist_ok=True)
    sc.render.filepath = os.path.join(os.path.abspath(a.out), "f_")
    bpy.ops.render.render(animation=True)
    print("SHOT_DONE", n if a.still is None else 1, "frames →", a.out)


main()
