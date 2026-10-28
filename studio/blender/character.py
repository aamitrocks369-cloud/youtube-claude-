"""
Procedural character rig in the Last Soul style.

Matte black sphere head, white oval eyes with eyelids (no mouth), tube limbs,
black mitten hands. Identity comes from outfit colours plus one accessory.
Every joint is an empty, so poses are plain Euler rotations per joint and
the same rig is reused for every character.

    from character import build_character, set_pose
    ravi = build_character("ravi", shirt=(0.8, 0.12, 0.1), pants=(0.12, 0.12, 0.15),
                           accessory="headband", accent=(0.85, 0.1, 0.1))
    set_pose(ravi, "sit_slump", frame=1)
"""
import math

import bpy
from mathutils import Vector

# body proportions (metres; a character is ~1.25 m tall, head ~0.42 m)
HIP_H = 0.52
TORSO_LEN = 0.36
NECK = 0.05
HEAD_R = 0.21
UPPER_ARM = 0.2
FOREARM = 0.19
THIGH = 0.25
SHIN = 0.24
LIMB_R = 0.045
LID_OPEN = 0.092
SHOULDER_W = 0.13
HIP_W = 0.07


def _mat(name, color, rough=0.6, emit=0.0, spec=0.3):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = spec
    if emit:
        b.inputs["Emission Color"].default_value = (*color, 1)
        b.inputs["Emission Strength"].default_value = emit
    return m


def _empty(name, parent, loc):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.04
    e.rotation_mode = "XYZ"
    bpy.context.collection.objects.link(e)
    e.parent = parent
    e.location = loc
    return e


def _attach(obj, parent, mat):
    obj.parent = parent
    obj.data.materials.append(mat)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def _capsule(name, length, radius, parent, mat, down=True):
    """A rounded limb hanging from its joint (along -Z when down)."""
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=length, vertices=20,
                                        location=(0, 0, -length / 2 if down else length / 2))
    cyl = bpy.context.object
    cyl.name = name
    _attach(cyl, parent, mat)
    for z in (0, -length if down else length):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=20, ring_count=10, location=(0, 0, z))
        _attach(bpy.context.object, parent, mat)
    return cyl


def _sphere(name, radius, loc, parent, mat, scale=(1, 1, 1), segments=32):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=segments, ring_count=segments // 2, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    return _attach(o, parent, mat)


def build_character(name, shirt, pants, shoes=(0.08, 0.08, 0.09), accessory=None, accent=(0.9, 0.2, 0.2),
                    hair=None, location=(0, 0, 0), facing=0.0):
    """Builds a character and returns {joint_name: empty} plus 'root'."""
    black = _mat("skin_black", (0.012, 0.012, 0.014), rough=0.62, spec=0.22)
    white = _mat("eye_white", (0.95, 0.95, 0.92), rough=0.3, emit=0.4)
    m_shirt = _mat(f"{name}_shirt", shirt, rough=0.85, spec=0.1)
    m_pants = _mat(f"{name}_pants", pants, rough=0.85, spec=0.1)
    m_shoes = _mat(f"{name}_shoes", shoes, rough=0.5)
    m_acc = _mat(f"{name}_accent", accent, rough=0.7, spec=0.1)

    j = {}
    root = _empty(f"{name}", None, location)
    root.rotation_euler.z = facing
    j["root"] = root
    j["hips"] = _empty(f"{name}.hips", root, (0, 0, HIP_H))
    j["chest"] = _empty(f"{name}.chest", j["hips"], (0, 0, 0.02))
    # torso: a slightly tapered rounded block
    bpy.ops.mesh.primitive_cylinder_add(radius=0.13, depth=TORSO_LEN, vertices=24, location=(0, 0, TORSO_LEN / 2))
    torso = bpy.context.object
    torso.name = f"{name}.torso"
    torso.scale = (1.0, 0.72, 1.0)
    _attach(torso, j["chest"], m_shirt)
    bev = torso.modifiers.new("bevel", "BEVEL")
    bev.width, bev.segments = 0.05, 4
    j["neck"] = _empty(f"{name}.neck", j["chest"], (0, 0, TORSO_LEN))
    j["head"] = _empty(f"{name}.head", j["neck"], (0, 0, NECK))
    _sphere(f"{name}.skull", HEAD_R, (0, 0, HEAD_R), j["head"], black, segments=48)
    # eyes: flattened white ovals on the front (-Y faces camera by default)
    j["eyes"] = []
    for side in (-1, 1):
        eye_root = _empty(f"{name}.eye{side}", j["head"], (side * 0.075, -HEAD_R * 0.9, HEAD_R * 1.08))
        _sphere(f"{name}.eyeball{side}", 0.04, (0, 0, 0), eye_root, white, scale=(0.72, 0.3, 1.12))
        # eyelid: a black slab in front of the eye that slides down over it
        lid = _empty(f"{name}.lid{side}", eye_root, (0, 0, LID_OPEN))
        _sphere(f"{name}.lidmesh{side}", 0.046, (0, -0.005, 0), lid, black, scale=(0.85, 0.2, 1.0))
        j["eyes"].append((eye_root, lid))
    # arms
    for side, s in (("L", 1), ("R", -1)):
        sh = _empty(f"{name}.shoulder{side}", j["chest"], (s * SHOULDER_W, 0, TORSO_LEN - 0.05))
        _capsule(f"{name}.uarm{side}", UPPER_ARM, LIMB_R, sh, m_shirt)
        el = _empty(f"{name}.elbow{side}", sh, (0, 0, -UPPER_ARM))
        _capsule(f"{name}.farm{side}", FOREARM * 0.55, LIMB_R * 0.97, el, m_shirt)
        _capsule(f"{name}.wrist{side}", FOREARM * 0.45, LIMB_R * 0.8, _empty(f"{name}.cuff{side}", el, (0, 0, -FOREARM * 0.55)), black)
        hand = _empty(f"{name}.hand{side}", el, (0, 0, -FOREARM))
        _sphere(f"{name}.mitten{side}", 0.05, (0, 0, -0.03), hand, black, scale=(0.75, 0.55, 1.0))
        _sphere(f"{name}.thumb{side}", 0.022, (s * -0.025, -0.02, -0.01), hand, black)
        j[f"shoulder{side}"], j[f"elbow{side}"], j[f"hand{side}"] = sh, el, hand
    # legs
    for side, s in (("L", 1), ("R", -1)):
        hp = _empty(f"{name}.hip{side}", j["hips"], (s * HIP_W, 0, 0))
        _capsule(f"{name}.thigh{side}", THIGH, LIMB_R * 1.15, hp, m_pants)
        kn = _empty(f"{name}.knee{side}", hp, (0, 0, -THIGH))
        _capsule(f"{name}.shin{side}", SHIN, LIMB_R * 1.05, kn, m_pants)
        ft = _empty(f"{name}.foot{side}", kn, (0, 0, -SHIN))
        _sphere(f"{name}.shoe{side}", 0.06, (0, -0.035, -0.02), ft, m_shoes, scale=(0.85, 1.5, 0.6))
        j[f"hip{side}"], j[f"knee{side}"], j[f"foot{side}"] = hp, kn, ft
    # hips block so the shirt/pants join looks clean
    _sphere(f"{name}.pelvis", 0.12, (0, 0, 0.0), j["hips"], m_pants, scale=(1.05, 0.75, 0.6))
    _add_accessory(name, accessory, j["head"], m_acc, black)
    if hair:
        _add_accessory(name, hair, j["head"], black, black)
    return j


def _add_accessory(name, kind, head, mat, black):
    if not kind:
        return
    if kind == "headband":
        bpy.ops.mesh.primitive_torus_add(major_radius=HEAD_R * 0.93, minor_radius=0.02, location=(0, 0, HEAD_R * 1.4),
                                         rotation=(math.radians(-8), 0, 0))
        o = bpy.context.object
        o.scale = (1, 1, 1.9)
        _attach(o, head, mat)
    elif kind == "cap":
        _sphere(f"{name}.cap", HEAD_R * 1.04, (0, 0, HEAD_R * 1.2), head, mat, scale=(1, 1, 0.62))
        bpy.ops.mesh.primitive_cylinder_add(radius=HEAD_R * 0.75, depth=0.015, location=(0, -HEAD_R * 0.75, HEAD_R * 1.32))
        o = bpy.context.object
        o.scale = (1, 0.8, 1)
        _attach(o, head, mat)
    elif kind == "bun":  # hair bun with a coloured scrunchie
        _sphere(f"{name}.bun", 0.09, (0, 0.06, HEAD_R * 2.05), head, black)
        bpy.ops.mesh.primitive_torus_add(major_radius=0.075, minor_radius=0.03, location=(0, 0.04, HEAD_R * 1.9))
        _attach(bpy.context.object, head, mat)
    elif kind == "dupatta":  # a scarf around the neck
        bpy.ops.mesh.primitive_torus_add(major_radius=0.13, minor_radius=0.045, location=(0, 0, -0.01))
        o = bpy.context.object
        o.scale = (1, 0.8, 0.7)
        _attach(o, head, mat)
    elif kind == "glasses":
        for s in (-1, 1):
            bpy.ops.mesh.primitive_torus_add(major_radius=0.045, minor_radius=0.006,
                                             location=(s * 0.075, -HEAD_R * 0.97, HEAD_R * 1.08),
                                             rotation=(math.radians(90), 0, 0))
            _attach(bpy.context.object, head, mat)
    elif kind == "long_hair":
        _sphere(f"{name}.hair", HEAD_R * 1.06, (0, 0.03, HEAD_R * 1.05), head, black, scale=(1.02, 1.0, 1.08))
        _sphere(f"{name}.hairback", HEAD_R * 0.8, (0, 0.12, HEAD_R * 0.45), head, black, scale=(1.0, 0.6, 1.3))


# ---------------------------------------------------------------- poses
# Euler degrees per joint. Unlisted joints return to zero.
POSES = {
    "stand": {"shoulderL": (0, 6, 0), "shoulderR": (0, -6, 0), "elbowL": (8, 0, 0), "elbowR": (8, 0, 0)},
    "phone": {"shoulderL": (-30, 14, 0), "elbowL": (-85, 0, -35), "shoulderR": (-30, -14, 0), "elbowR": (-85, 0, 35),
              "neck": (10, 0, 0), "head": (6, 0, 0)},
    "sad": {"neck": (22, 0, 0), "head": (10, 0, 0), "chest": (8, 0, 0), "shoulderL": (0, 3, 0), "shoulderR": (0, -3, 0)},
    "sit": {"hipL": (-90, 0, 0), "hipR": (-90, 0, 0), "kneeL": (90, 0, 0), "kneeR": (90, 0, 0)},
    "wave": {"shoulderR": (0, -150, 0), "elbowR": (0, -20, 0)},
    "walk_a": {"hipL": (-25, 0, 0), "hipR": (20, 0, 0), "kneeL": (10, 0, 0), "kneeR": (30, 0, 0),
               "shoulderL": (18, 0, 0), "shoulderR": (-18, 0, 0)},
    "walk_b": {"hipL": (20, 0, 0), "hipR": (-25, 0, 0), "kneeL": (30, 0, 0), "kneeR": (10, 0, 0),
               "shoulderL": (-18, 0, 0), "shoulderR": (18, 0, 0)},
}
JOINTS = ["hips", "chest", "neck", "head", "shoulderL", "shoulderR", "elbowL", "elbowR",
          "hipL", "hipR", "kneeL", "kneeR", "handL", "handR", "footL", "footR"]


def set_pose(j, pose, frame=None, extra=None, seat=0.34):
    """Apply one or more poses ('sit+phone') and optionally keyframe them.
    seat is the seat height when sitting."""
    rot = {}
    for p in pose.split("+"):
        rot.update(POSES[p])
    rot.update(extra or {})
    for name in JOINTS:
        e = j[name]
        e.rotation_euler = tuple(math.radians(a) for a in rot.get(name, (0, 0, 0)))
        if frame is not None:
            e.keyframe_insert("rotation_euler", frame=frame)
    if "sit" in pose.split("+"):
        j["hips"].location.z = seat + LIMB_R * 1.15
    else:
        j["hips"].location.z = HIP_H
    if frame is not None:
        j["hips"].keyframe_insert("location", frame=frame)


# lid height above the eye centre (0 = closed) and tilt in degrees
EXPRESSIONS = {"open": (LID_OPEN, 0), "tired": (0.045, 0), "sad": (0.055, 22), "angry": (0.055, -22),
               "closed": (0.0, 0), "happy": (LID_OPEN, 0)}


def set_expression(j, expr, frame=None):
    """Eyelids: open, tired (half), sad / angry (tilted), closed."""
    z, tilt = EXPRESSIONS[expr]
    for k, (eye_root, lid) in enumerate(j["eyes"]):
        lid.location.z = z
        lid.rotation_euler.y = math.radians(tilt * (1 if k == 0 else -1))
        if frame is not None:
            lid.keyframe_insert("location", frame=frame)
            lid.keyframe_insert("rotation_euler", frame=frame)


def look_at_point(j, target):
    """Turn the whole character on Z to face a world point."""
    root = j["root"]
    d = Vector(target) - root.location
    root.rotation_euler.z = math.atan2(d.x, -d.y)
