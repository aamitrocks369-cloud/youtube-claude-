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


def _text(name, body, loc, size, mat, rot=(math.radians(90), 0, 0), align="CENTER"):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.extrude = 0.002
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.location, o.rotation_euler = loc, rot
    o.data.materials.append(mat)
    return o


def _tube_light(name, loc, length=0.9, energy=30, color=(0.85, 0.95, 1.0)):
    m = _mat("tube", color, rough=0.3, emit=8.0)
    _box(name, (length, 0.04, 0.04), loc, m)
    _area(f"{name}_light", (loc[0], loc[1] - 0.15, loc[2] - 0.05), (math.radians(30), 0, 0), length, color, energy,
          size_y=0.1)


def _fan(name, loc):
    metal = _mat("fan_metal", (0.55, 0.55, 0.52), rough=0.5)
    _box(f"{name}_rod", (0.03, 0.03, 0.35), (loc[0], loc[1], loc[2] + 0.17), metal)
    _box(f"{name}_hub", (0.16, 0.16, 0.07), loc, metal, bevel=0.03)
    for k in range(3):
        a = k * 2 * math.pi / 3
        _box(f"{name}_blade{k}", (0.55, 0.11, 0.01),
             (loc[0] + 0.33 * math.cos(a), loc[1] + 0.33 * math.sin(a), loc[2]), metal, rot=(0, 0, a))


def classroom(mood="day"):
    """A Kota-style coaching classroom: whiteboard with formulas, rows of
    benches, tube lights, ceiling fans, a grilled window and a TARGET poster.
    Camera usually looks toward +Y (the board)."""
    wall = _mat("class_wall", (0.72, 0.74, 0.66), rough=0.95, spec=0.05)
    lower = _mat("class_wall_low", (0.25, 0.36, 0.32), rough=0.9, spec=0.05)
    floor = _mat("class_floor", (0.45, 0.43, 0.4), rough=0.5)
    board = _mat("whiteboard", (0.92, 0.93, 0.95), rough=0.25, emit=0.15)
    ink = _mat("board_ink", (0.08, 0.15, 0.55), rough=0.6)
    red_ink = _mat("board_ink_red", (0.7, 0.08, 0.08), rough=0.6)
    bench = _mat("bench_wood", (0.35, 0.22, 0.12), rough=0.6)
    metal = _mat("bench_metal", (0.18, 0.2, 0.22), rough=0.5)
    poster = _mat("poster_yellow", (0.95, 0.75, 0.15), rough=0.8)
    dark = _mat("text_dark", (0.05, 0.05, 0.06), rough=0.8)

    _box("floor", (8, 10, 0.05), (0, 0, -0.025), floor)
    _box("wall_front", (8, 0.1, 3.2), (0, 3.0, 1.6), wall)
    _box("wall_front_low", (8, 0.12, 0.9), (0, 2.99, 0.45), lower)
    _box("wall_left", (0.1, 10, 3.2), (-3.0, 0, 1.6), wall)
    _box("wall_left_low", (0.12, 10, 0.9), (-2.99, 0, 0.45), lower)
    _box("ceiling", (8, 10, 0.05), (0, 0, 3.2), wall)
    _box("board_frame", (2.9, 0.04, 1.3), (0.2, 2.94, 1.65), metal)
    _box("board", (2.8, 0.04, 1.2), (0.2, 2.92, 1.65), board)
    for k, line in enumerate(["F = ma", "v² = u² + 2as", "∫ x dx = x²/2", "JEE  2027"]):
        _text(f"formula{k}", line, (-0.9 + 0.05 * k, 2.89, 2.05 - k * 0.27), 0.17, red_ink if k == 3 else ink,
              align="LEFT")
    _box("teacher_desk", (1.0, 0.5, 0.75), (1.9, 2.3, 0.375), bench, bevel=0.01)
    _box("poster", (0.7, 0.02, 0.95), (-2.0, 2.94, 1.7), poster)
    _text("poster_t1", "TARGET", (-2.0, 2.92, 1.95), 0.15, dark)
    _text("poster_t2", "AIR 1", (-2.0, 2.92, 1.65), 0.22, red_ink)
    _text("poster_t3", "No Excuses", (-2.0, 2.92, 1.4), 0.08, dark)
    # three rows of two-seat benches (desk + seat in one)
    seats = {}
    for r in range(3):
        for c, x in enumerate((-1.4, 0.0, 1.4)):
            y = 1.2 - r * 1.1
            _box(f"desk_{r}_{c}", (1.1, 0.4, 0.04), (x, y, 0.62), bench, bevel=0.01)
            _box(f"seat_{r}_{c}", (1.1, 0.3, 0.04), (x, y - 0.5, 0.36), bench, bevel=0.01)
            for dx in (-0.5, 0.5):
                _box(f"leg_{r}_{c}_{dx}", (0.04, 0.85, 0.04), (x + dx, y - 0.25, 0.02), metal)
                _box(f"post_{r}_{c}_{dx}", (0.04, 0.04, 0.62), (x + dx, y, 0.31), metal)
            seats[f"seat_{r}_{c}a"] = (x - 0.25, y - 0.48, 0.38)
            seats[f"seat_{r}_{c}b"] = (x + 0.25, y - 0.48, 0.38)
    # grilled window on the left wall
    sky = _mat("class_window", (0.75, 0.82, 0.95), rough=0.2, emit=4.0 if mood == "day" else 0.3)
    _box("window", (0.02, 1.4, 1.0), (-2.94, 0.3, 1.7), sky)
    for k in range(8):
        _box(f"grill{k}", (0.03, 0.02, 1.0), (-2.92, -0.35 + k * 0.19, 1.7), metal)
    for k, y in enumerate((1.6, -0.6)):
        _tube_light(f"tube{k}", (0.0, y, 3.1), energy=40 if mood == "day" else 25)
        _fan(f"fan{k}", (0.0, y - 0.3, 2.75))
    if mood == "day":
        world((0.6, 0.62, 0.65), 0.5)
        _area("window_sun", (-3.6, 0.3, 2.2), (0, math.radians(-70), 0), 1.6, (1.0, 0.92, 0.78), 500)
        _area("fill", (1.5, -3.5, 2.6), (math.radians(60), 0, math.radians(20)), 4.0, (0.95, 0.95, 1.0), 220)
    else:
        world((0.02, 0.025, 0.04), 1.0)
        _area("fill", (1.5, -3.5, 2.6), (math.radians(60), 0, math.radians(20)), 4.0, (0.6, 0.65, 0.9), 60)
    anchors = {"board": (0.2, 2.5, 0.0), "teacher": (1.3, 2.2, 0.0), "door_spot": (2.5, -2.5, 0.0),
               "aisle": (0.7, -0.5, 0.0)}
    anchors.update(seats)
    return anchors


def stairwell(mood="night"):
    """An Indian housing-society stairwell: two-tone painted walls, a flight of
    stairs up to a landing, a grilled window, a meter box and one tube light.
    Stairs rise toward +Y; the camera usually sits low at -Y."""
    upper = _mat("stair_wall", (0.78, 0.72, 0.58), rough=0.95, spec=0.05)
    lower = _mat("stair_wall_low", (0.18, 0.3, 0.26), rough=0.9, spec=0.05)
    stone = _mat("stair_stone", (0.38, 0.36, 0.34), rough=0.55)
    rail = _mat("stair_rail", (0.08, 0.08, 0.08), rough=0.4)
    meter = _mat("meter_box", (0.55, 0.55, 0.5), rough=0.6)
    door = _mat("flat_door", (0.35, 0.18, 0.08), rough=0.5)
    brass = _mat("brass", (0.8, 0.6, 0.25), rough=0.3)

    _box("floor", (4, 3, 0.05), (0, -1.0, -0.025), stone)
    n, rise, run = 10, 0.15, 0.27
    for k in range(n):
        _box(f"step{k}", (1.2, run, rise * (k + 1)), (0.4, 0.5 + k * run, rise * (k + 1) / 2), stone, bevel=0.005)
    top = rise * n
    _box("landing", (2.4, 1.4, top), (0.4, 0.5 + n * run + 0.7, top / 2), stone)
    _box("wall_side", (0.1, 8, 4.5), (-0.25, 1.0, 2.25), upper)
    _box("wall_side_low", (0.12, 8, 1.0), (-0.24, 1.0, 0.5), lower)
    _box("wall_back", (4, 0.1, 4.5), (0.4, 0.5 + n * run + 1.45, 2.25), upper)
    _box("wall_back_low", (4, 0.12, 1.0), (0.4, 0.5 + n * run + 1.44, top + 0.5), lower)
    # railing on the open side
    for k in range(0, n, 2):
        _box(f"baluster{k}", (0.02, 0.02, 0.9), (1.0, 0.5 + k * run, rise * (k + 1) + 0.45), rail)
    hand_len = math.hypot(n * run, n * rise)
    _box("handrail", (0.04, hand_len, 0.04), (1.0, 0.5 + n * run / 2, top / 2 + 0.95), rail,
         rot=(math.atan2(rise, run), 0, 0))
    # landing: a flat door, meter box and grilled window
    yb = 0.5 + n * run + 1.38
    _box("door", (0.85, 0.06, 2.0), (1.0, yb, top + 1.0), door, bevel=0.01)
    _box("knob", (0.06, 0.04, 0.06), (0.7, yb - 0.05, top + 1.0), brass)
    _box("nameplate", (0.3, 0.02, 0.1), (1.0, yb - 0.04, top + 1.55), brass)
    _box("meter_box", (0.5, 0.15, 0.7), (-0.15, yb - 0.4, top + 1.6), meter)
    glass = _mat("stair_window", (0.2, 0.3, 0.55), rough=0.2, emit=1.2 if mood == "night" else 5.0)
    _box("window", (0.02, 0.8, 0.8), (-0.19, 1.6, 2.6), glass)
    for k in range(6):
        _box(f"wgrill{k}", (0.03, 0.02, 0.8), (-0.17, 1.25 + k * 0.14, 2.6), rail)
    _tube_light("tube", (0.4, yb - 0.1, top + 2.4), energy=35 if mood == "night" else 50, color=(0.8, 1.0, 0.85))
    if mood == "night":
        world((0.006, 0.008, 0.014), 1.0)
        _area("fill", (2.0, -2.5, 2.5), (math.radians(60), 0, math.radians(35)), 3.0, (0.35, 0.4, 0.6), 35)
    else:
        world((0.5, 0.52, 0.55), 0.5)
        _area("fill", (2.0, -2.5, 2.5), (math.radians(60), 0, math.radians(35)), 3.0, (0.95, 0.92, 0.85), 200)
    return {
        "stairs_bottom": (0.4, -0.2, 0.0),
        "stairs_top": (0.4, 0.5 + n * run + 0.4, top),
        "door_front": (1.0, yb - 0.6, top),
        "stair_mid": (0.4, 0.5 + (n // 2) * run, rise * (n // 2 + 1)),
    }


SETS = {"bedroom": bedroom, "classroom": classroom, "stairwell": stairwell}
