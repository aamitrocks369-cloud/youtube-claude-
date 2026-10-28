"""Smoke test: one character in the bedroom set, rendered as a 9:16 still.

blender -b -P test_scene.py -- out.png [CYCLES|BLENDER_EEVEE_NEXT]
"""
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import character as ch  # noqa: E402
import sets  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
out = os.path.abspath(args[0])
engine = args[1] if len(args) > 1 else "CYCLES"

bpy.ops.wm.read_factory_settings(use_empty=True)
anchors = sets.bedroom("night")
ravi = ch.build_character("ravi", shirt=(0.75, 0.1, 0.08), pants=(0.1, 0.1, 0.13), accessory="headband",
                          accent=(0.9, 0.1, 0.1), location=anchors["bed_sit"][:2] + (0,), facing=math.radians(55))
ch.set_pose(ravi, "sit+phone", seat=anchors["bed_sit"][2])
ch.set_expression(ravi, "tired")
# the phone: an emissive screen in his hands lights his face
scr = ch._mat("phone_screen", (0.6, 0.75, 1.0), emit=6.0)
body = ch._mat("phone_body", (0.02, 0.02, 0.02), rough=0.3)
bpy.ops.mesh.primitive_cube_add(size=1)
phone = bpy.context.object
phone.scale = (0.07, 0.008, 0.14)
phone.data.materials.append(body)
phone.parent = ravi["handR"]
phone.location = (0.05, -0.02, -0.07)
phone.rotation_euler = (math.radians(70), 0, math.radians(-20))
bpy.ops.mesh.primitive_plane_add(size=1)
glow = bpy.context.object
glow.scale = (0.06, 0.12, 1)
glow.rotation_euler.x = math.radians(90)
glow.data.materials.append(scr)
glow.parent = phone
glow.location = (0, 0.6, 0)
d = bpy.data.lights.new("phone_light", "POINT")
d.color, d.energy, d.shadow_soft_size = (0.6, 0.75, 1.0), 6, 0.05
pl = bpy.data.objects.new("phone_light", d)
bpy.context.collection.objects.link(pl)
pl.parent = phone
pl.location = (0, 0, 0)

cam_d = bpy.data.cameras.new("cam")
cam_d.lens = 45
cam_d.dof.use_dof = True
cam_d.dof.aperture_fstop = 2.8
cam = bpy.data.objects.new("cam", cam_d)
bpy.context.collection.objects.link(cam)
cam.location = (0.3, -1.4, 1.2)
tgt = bpy.data.objects.new("cam_target", None)
bpy.context.collection.objects.link(tgt)
tgt.location = (anchors["bed_sit"][0], anchors["bed_sit"][1], 0.75)
c = cam.constraints.new("TRACK_TO")
c.target = tgt
cam_d.dof.focus_object = tgt
bpy.context.scene.camera = cam

sc = bpy.context.scene
sc.render.engine = engine
sc.render.resolution_x, sc.render.resolution_y = 1080, 1920
sc.render.resolution_percentage = 50
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
if engine == "CYCLES":
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.cycles.device = "CPU"
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print("WROTE", out)
