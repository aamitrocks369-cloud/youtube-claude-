"""
Reusable 3D sets. Each builder makes the geometry and its default lights and
returns named anchor points (where characters stand or sit, where props go).
"""
import math

import bpy

from character import _mat


def _box(name, size, loc, mat, rot=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = size
    o.data.materials.append(mat)
    if bevel:
        bpy.ops.object.transform_apply(scale=True)
        m = o.modifiers.new("bevel", "BEVEL")
        m.width, m.segments = bevel, 3
    return o


def _area(name, loc, rot, size, color, energy, shape="RECTANGLE", size_y=None):
    d = bpy.data.lights.new(name, "AREA")
    d.shape = shape
    d.size = size
    if size_y:
        d.size_y = size_y
    d.color = color
    d.energy = energy
    o = bpy.data.objects.new(name, d)
    bpy.context.collection.objects.link(o)
    o.location, o.rotation_euler = loc, rot
    return o


def _point(name, loc, color, energy, radius=0.05):
    d = bpy.data.lights.new(name, "POINT")
    d.color, d.energy, d.shadow_soft_size = color, energy, radius
    o = bpy.data.objects.new(name, d)
    bpy.context.collection.objects.link(o)
    o.location = loc
    return o


def world(color=(0.01, 0.012, 0.02), strength=1.0):
    w = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*color, 1)
    bg.inputs["Strength"].default_value = strength


def bedroom(mood="night"):
    """A small Indian bedroom: bed, study desk with lamp, window with a
    curtain, a poster and a shelf. mood = night | day."""
    wall = _mat("bedroom_wall", (0.42, 0.45, 0.5) if mood == "night" else (0.78, 0.72, 0.6), rough=0.95, spec=0.05)
    floor = _mat("bedroom_floor", (0.3, 0.24, 0.2), rough=0.6)
    wood = _mat("wood_dark", (0.2, 0.12, 0.07), rough=0.55)
    sheet = _mat("bed_sheet", (0.75, 0.75, 0.78), rough=0.9, spec=0.05)
    blanket = _mat("bed_blanket", (0.15, 0.2, 0.42), rough=0.95, spec=0.05)
    curtain = _mat("curtain", (0.55, 0.32, 0.18), rough=0.95, spec=0.05)
    glass = _mat("window_glass", (0.25, 0.35, 0.6), rough=0.2, emit=1.5 if mood == "night" else 6.0)
    poster = _mat("poster", (0.75, 0.25, 0.15), rough=0.8)
    book_cols = [(0.7, 0.2, 0.15), (0.15, 0.35, 0.6), (0.85, 0.7, 0.2), (0.2, 0.5, 0.3)]

    _box("floor", (5, 5, 0.05), (0, 0, -0.025), floor)
    _box("wall_back", (5, 0.1, 3), (0, 1.6, 1.5), wall)
    _box("wall_left", (0.1, 5, 3), (-2.0, 0, 1.5), wall)
    # window on the back wall
    _box("window", (0.9, 0.02, 1.0), (-0.9, 1.54, 1.55), glass)
    _box("sill", (1.05, 0.15, 0.05), (-0.9, 1.5, 1.03), wood)
    for x in (-0.9,):
        _box("mullion_v", (0.03, 0.04, 1.0), (x, 1.53, 1.55), wood)
    _box("mullion_h", (0.9, 0.04, 0.03), (-0.9, 1.53, 1.55), wood)
    for k, x in enumerate((-1.48, -0.32)):
        c = _box(f"curtain{k}", (0.25, 0.06, 1.5), (x, 1.48, 1.45), curtain, bevel=0.03)
    # bed against the left wall
    _box("bed_frame", (1.0, 2.0, 0.2), (-1.45, 0.45, 0.1), wood, bevel=0.02)
    _box("mattress", (0.95, 1.95, 0.14), (-1.45, 0.45, 0.27), sheet, bevel=0.05)
    _box("blanket", (0.97, 1.0, 0.05), (-1.45, -0.05, 0.35), blanket, bevel=0.02)
    _box("pillow", (0.6, 0.35, 0.1), (-1.45, 1.2, 0.39), sheet, bevel=0.04)
    _box("headboard", (1.0, 0.06, 0.55), (-1.45, 1.47, 0.42), wood, bevel=0.02)
    # study desk on the right of the window
    _box("desk_top", (1.1, 0.55, 0.04), (0.75, 1.25, 0.75), wood, bevel=0.01)
    for dx in (-0.5, 0.5):
        _box(f"desk_leg{dx}", (0.04, 0.5, 0.75), (0.75 + dx, 1.25, 0.375), wood)
    for k in range(9):
        _box(f"book{k}", (0.03, 0.18, 0.22 + 0.03 * (k % 3)), (0.35 + k * 0.035, 1.38, 0.88 + 0.015 * (k % 3)),
             _mat(f"book{k % 4}", book_cols[k % 4], rough=0.8))
    lamp_mat = _mat("lamp_shade", (1.0, 0.75, 0.4), rough=0.6, emit=3.0)
    _box("lamp_base", (0.1, 0.1, 0.03), (1.15, 1.3, 0.78), wood)
    _box("lamp_arm", (0.02, 0.02, 0.35), (1.15, 1.3, 0.95), wood)
    _box("lamp_shade", (0.16, 0.12, 0.08), (1.1, 1.25, 1.12), lamp_mat, bevel=0.02)
    _box("poster", (0.5, 0.01, 0.7), (0.75, 1.545, 1.75), poster)
    _box("chair_seat", (0.4, 0.4, 0.04), (0.75, 0.8, 0.32), wood, bevel=0.01)
    _box("chair_back", (0.4, 0.04, 0.4), (0.75, 0.6, 0.52), wood, bevel=0.01)

    if mood == "night":
        world((0.008, 0.01, 0.022), 1.0)
        _area("moon", (-0.9, 2.4, 2.2), (math.radians(-60), 0, 0), 1.2, (0.55, 0.65, 1.0), 120)
        _point("desk_lamp", (1.1, 1.2, 1.02), (1.0, 0.7, 0.4), 25, radius=0.08)
        _area("fill", (1.5, -2.5, 2.5), (math.radians(55), 0, math.radians(30)), 3.0, (0.4, 0.45, 0.7), 40)
        _area("rim", (-0.5, 2.0, 1.6), (math.radians(-75), 0, math.radians(180)), 1.0, (0.6, 0.7, 1.0), 60)
    else:
        world((0.5, 0.55, 0.65), 0.6)
        _area("sun_window", (-0.9, 2.4, 2.0), (math.radians(-65), 0, 0), 1.5, (1.0, 0.9, 0.75), 600)
        _area("fill", (1.5, -2.5, 2.5), (math.radians(55), 0, math.radians(30)), 3.0, (0.9, 0.9, 1.0), 150)

    return {
        # (x, y, seat height); sit there with set_pose(j, "sit", seat=z)
        "bed_sit": (-1.02, 0.55, 0.34),
        "bed_lie": (-1.45, 0.6, 0.36),
        "desk_chair": (0.75, 0.82, 0.34),
        "door_spot": (0.9, -1.2, 0.0),
        "centre": (0.0, 0.2, 0.0),
    }
