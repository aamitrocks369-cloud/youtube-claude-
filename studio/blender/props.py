"""Hand props that follow a character: phone (glowing screen), book, bag."""
import math

import bpy

from character import _mat


def _cube(name, scale, parent, loc, rot, mat):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    o.data.materials.append(mat)
    o.parent = parent
    o.location, o.rotation_euler = loc, rot
    return o


def phone(j, hand="handR", glow=6.0):
    body = _mat("phone_body", (0.02, 0.02, 0.02), rough=0.3)
    scr = _mat("phone_screen", (0.6, 0.75, 1.0), emit=glow)
    p = _cube("phone", (0.07, 0.008, 0.14), j[hand], (0.05, -0.02, -0.07),
              (math.radians(70), 0, math.radians(-20)), body)
    bpy.ops.mesh.primitive_plane_add(size=1)
    s = bpy.context.object
    s.scale = (0.9, 0.92, 1)
    s.rotation_euler.x = math.radians(90)
    s.data.materials.append(scr)
    s.parent = p
    s.location = (0, -0.6, 0)
    d = bpy.data.lights.new("phone_light", "POINT")
    d.color, d.energy, d.shadow_soft_size = (0.6, 0.75, 1.0), 6, 0.05
    lo = bpy.data.objects.new("phone_light", d)
    bpy.context.collection.objects.link(lo)
    lo.parent = p
    lo.location = (0, -3.0, 0.3)
    return p


def book(j, hand="handL"):
    cover = _mat("book_cover", (0.15, 0.3, 0.6), rough=0.7)
    return _cube("book", (0.16, 0.03, 0.22), j[hand], (0.0, -0.04, -0.08), (math.radians(60), 0, 0), cover)


def bag(j, hand="handR"):
    m = _mat("bag", (0.1, 0.15, 0.3), rough=0.9)
    return _cube("bag", (0.16, 0.07, 0.2), j[hand], (0, 0, -0.14), (0, 0, 0), m)


PROPS = {"phone": phone, "book": book, "bag": bag}


def attach(kind, j):
    return PROPS[kind](j)
