#!/usr/bin/env python3
"""
v3 renderer — closes the gaps found in docs/audit/file001-vs-competition.md:

  1. phrase-level beats: narration is synthesized per phrase and every phrase
     gets its own visual beat (cut, reframe or action)
  2. figures drawn stroke-then-fill (black separation lines), neck gap, faces
     with expressions, props in hand, softer glow
  3. four reusable dressed sets (lobby, elevator interior, hallway, office)
     with a floor line, framed by a per-beat camera (wide / medium / close)
  4. glitch on flagged beats plus every 4th cut
  5. colour discipline: amber displays, yellow light sources, red for danger
  6. no camera drift; motion comes from character action + push-in
  7. louder master (voiced median ~-16 dB) and a longer script
  8. own formats: SURVEILLANCE RECORD inserts and the Compliance Officer

Usage:
    python3 scripts/build_episode_v3.py episodes/001-elevator/episode_v3.json \
        --voice voices/en-us-ryan-medium.onnx --out build/001v3 [--preview]
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_episode as v1  # noqa: E402
import build_episode_v2 as v2  # noqa: E402

W, H, FPS = v2.W, v2.H, v2.FPS
BLACK, WHITE, GREY, DIM, FAINT = v2.BLACK, v2.WHITE, v2.GREY, v2.DIM, v2.FAINT
YELLOW, RED, GREEN = v2.YELLOW, v2.RED, v2.GREEN
AMBER = (255, 170, 60)
mont, spaced_text, spaced_width = v2.mont, v2.spaced_text, v2.spaced_width
ease, fade, appear, shake, blend, breathe, walk_pose, POSES = (
    v2.ease, v2.fade, v2.appear, v2.shake, v2.blend, v2.breathe, v2.walk_pose, v2.POSES)
thick = v1.thick_line
FLOOR = 900

POSES.setdefault("write", dict(lean=6, head=12, lh=-5, lk=0, rh=5, rk=0, ls=-10, le=0, rs=60, re=40, bob=0))
POSES.setdefault("hold", dict(lean=0, head=6, lh=-5, lk=0, rh=5, rk=0, ls=-10, le=0, rs=40, re=70, bob=0))
POSES.setdefault("freeze", dict(lean=-6, head=-8, lh=-6, lk=0, rh=6, rk=0, ls=-30, le=-30, rs=30, re=30, bob=-4))
POSES.setdefault("run", dict(lean=14, head=4, lh=0, lk=0, rh=0, rk=0, ls=0, le=40, rs=0, re=40, bob=0))


# ----------------------------------------------------------------------------
# Figure: stroke-then-fill so overlapping limbs separate, neck gap, face
# ----------------------------------------------------------------------------


def _pt(o, ang, length, f):
    a = math.radians(ang) * f
    return o[0] + math.sin(a) * length, o[1] + math.cos(a) * length


def _limb(d, pts, lw, o, fill):
    thick(d, pts, lw + 2 * o, BLACK)
    thick(d, pts, lw, fill)


def rig3(d, x, y, s=1.0, pose=None, facing=1, fill=WHITE, face=None, expr="neutral", prop=None,
         hat=None, sweat=False):
    p = pose or POSES["stand"]
    f = 1 if facing >= 0 else -1
    o = max(3, int(6 * s))
    hip = (x, y - 172 * s + p["bob"] * s)
    neck = _pt(hip, 180 + p["lean"], 124 * s, f)
    head = _pt(neck, 180 + p["lean"] + p["head"], 60 * s, f)
    lw = max(4, int(26 * s))
    aw = max(4, int(22 * s))
    sh = (neck[0], neck[1] + 16 * s)

    def leg(side):
        knee = _pt(hip, p[side + "h"], 88 * s, f)
        foot = _pt(knee, p[side + "h"] - p[side + "k"], 88 * s, f)
        _limb(d, [hip, knee, foot], lw, o, fill)

    def arm(side):
        elbow = _pt(sh, p[side + "s"], 74 * s, f)
        hand = _pt(elbow, p[side + "s"] + p[side + "e"], 70 * s, f)
        _limb(d, [sh, elbow, hand], aw, o, fill)
        return hand

    arm("l")
    leg("l")
    _limb(d, [hip, neck], max(6, int(64 * s)), o, fill)
    leg("r")
    hand = arm("r")
    r = 38 * s
    d.ellipse([head[0] - r - o, head[1] - r - o, head[0] + r + o, head[1] + r + o], fill=BLACK)
    d.ellipse([head[0] - r, head[1] - r, head[0] + r, head[1] + r], fill=fill)
    if hat == "hardhat":
        d.chord([head[0] - r * 1.15, head[1] - r * 1.25, head[0] + r * 1.15, head[1] + r * 0.6], 180, 360, fill=YELLOW)
        d.rectangle([head[0] - r * 1.3, head[1] - r * 0.36, head[0] + r * 1.3, head[1] - r * 0.22], fill=YELLOW)
    if face:
        ink = BLACK
        ey = head[1] - 2 * s
        er = max(2, 5 * s)
        if face == "side":
            ex = head[0] + 15 * s * f
            d.ellipse([ex - er, ey - er, ex + er, ey + er], fill=ink)
        else:
            for sx in (-1, 1):
                ex = head[0] + sx * 13 * s
                if expr == "closed":
                    d.line([(ex - 7 * s, ey), (ex + 7 * s, ey)], fill=ink, width=max(2, int(4 * s)))
                elif expr == "wide":
                    d.ellipse([ex - er * 1.7, ey - er * 1.7, ex + er * 1.7, ey + er * 1.7], fill=ink)
                elif expr == "side":
                    d.ellipse([ex + 5 * s - er, ey - er, ex + 5 * s + er, ey + er], fill=ink)
                else:
                    d.ellipse([ex - er, ey - er, ex + er, ey + er], fill=ink)
                if expr == "worried":
                    d.line([(ex - 9 * s, ey - 14 * s + sx * 4 * s), (ex + 9 * s, ey - 14 * s - sx * 4 * s)],
                           fill=ink, width=max(2, int(4 * s)))
    if sweat:
        sx, sy = head[0] + r * 0.9, head[1] - r * 0.5
        d.ellipse([sx - 6 * s, sy, sx + 6 * s, sy + 14 * s], fill=(150, 200, 255))
        d.polygon([(sx - 5 * s, sy + 4 * s), (sx + 5 * s, sy + 4 * s), (sx, sy - 10 * s)], fill=(150, 200, 255))
    if prop:
        hx, hy = hand
        if prop == "card":
            d.rounded_rectangle([hx - 4 * s, hy - 30 * s, hx + 48 * s, hy + 2 * s], radius=4 * s, fill=WHITE, outline=BLACK, width=o)
        elif prop == "paper":
            d.rectangle([hx - 10 * s, hy - 70 * s, hx + 50 * s, hy + 6 * s], fill=WHITE, outline=BLACK, width=o)
            for k in range(4):
                d.line([(hx, hy - 55 * s + k * 14 * s), (hx + 40 * s, hy - 55 * s + k * 14 * s)], fill=GREY, width=max(1, int(3 * s)))
        elif prop == "clipboard":
            d.rectangle([hx - 6 * s, hy - 64 * s, hx + 46 * s, hy + 6 * s], fill=(200, 170, 120), outline=BLACK, width=o)
            d.rectangle([hx + 2 * s, hy - 54 * s, hx + 38 * s, hy - 2 * s], fill=WHITE)
    return {"head": head, "hand": hand, "neck": neck, "hip": hip}


# all reused v2 shots draw figures through v2.rig → upgrade them in place
def _rig_compat(d, x, y, s=1.0, pose=None, facing=1, fill=WHITE):
    return rig3(d, x, y, s, pose, facing, fill, face="side" if facing else None)


v2.rig = _rig_compat


def actor(d, t, a, x, y, s, default="stand", facing=1, prop=None, face="side", expr="neutral", fill=WHITE):
    """Named actions for the figure inside a set."""
    act = a.get("you", default)
    if act == "walk_in":
        x0 = x - 520 * facing
        if t < 1.6:
            xx = x0 + (x - x0) * (t / 1.6)
            return rig3(d, xx, y, s, walk_pose(t * 9.5), facing, fill, face=face)
        k = ease((t - 1.6) / 0.35)
        return rig3(d, x, y, s, breathe(blend(walk_pose(1.6 * 9.5), POSES["stand"], k), t, k), facing, fill, face=face)
    if act == "run":
        xx = x - 700 + t * 520
        return rig3(d, xx, y, s, walk_pose(t * 15, 1.4), 1, fill, face="side", expr="wide")
    if act == "look_up":
        k = ease(t / 0.5)
        return rig3(d, x, y, s, breathe(blend(POSES["stand"], POSES["look_up"], k), t), facing, fill, face=face)
    if act == "nod":
        pose = dict(POSES["look_up"])
        pose["head"] = -18 + 26 * ((t * 1.6) % 1)
        return rig3(d, x, y, s, breathe(pose, t), facing, fill, face=face)
    if act == "step_back":
        k = ease(t / 0.45)
        pose = blend(POSES["stand"], POSES["flinch"], k)
        return rig3(d, x - 40 * k * facing, y, s * (1 - 0.04 * k), breathe(pose, t), facing, fill, face=face, expr="wide")
    if act == "ears":
        k = ease(t / 0.35)
        return rig3(d, x, y, s, breathe(blend(POSES["stand"], POSES["ears"], k), t, 1.6), facing, fill, face=face, expr="closed")
    if act == "hunch":
        k = ease(t / 0.5)
        tr = 2.5 * math.sin(t * 31) if t > 0.8 else 0
        return rig3(d, x + tr, y, s, breathe(blend(POSES["stand"], POSES["hunch"], k), t), facing, fill, face=face)
    if act == "read":
        return rig3(d, x, y, s, breathe(POSES["hold"], t), facing, fill, face=face, prop="paper")
    if act == "freeze":
        k = ease(t / 0.3)
        return rig3(d, x, y, s, blend(POSES["hold"], POSES["freeze"], k), facing, fill, face=face, expr="wide", prop="paper")
    return rig3(d, x, y, s, breathe(POSES["stand"], t), facing, fill, face=face, prop=prop)


# ----------------------------------------------------------------------------
# Sets (world space 1920x1080, floor line at FLOOR)
# ----------------------------------------------------------------------------


def ceiling_light(d, x, y, on=True, warm=True, cone=True):
    col = YELLOW if on else DIM
    if on and cone:
        d.polygon([(x - 40, y + 10), (x - 260, FLOOR), (x + 260, FLOOR), (x + 40, y + 10)], fill=fade(YELLOW, 0.07))
    d.rounded_rectangle([x - 60, y - 6, x + 60, y + 12], radius=6, fill=col)


def ground(d, x0=0, x1=W):
    d.rectangle([x0, FLOOR, x1, FLOOR + 6], fill=WHITE)
    for k in range(int(x0), int(x1), 140):
        d.line([(k, FLOOR + 6), (k - 60, FLOOR + 60)], fill=FAINT, width=2)


def plant(d, x):
    d.polygon([(x - 34, FLOOR), (x + 34, FLOOR), (x + 44, FLOOR - 70), (x - 44, FLOOR - 70)], fill=WHITE)
    for ang in (-50, -20, 10, 40):
        a = math.radians(ang)
        ex, ey = x + math.sin(a) * 110, FLOOR - 80 - math.cos(a) * 110
        d.ellipse([ex - 22, ey - 40, ex + 22, ey + 40], fill=WHITE)
        d.line([(x, FLOOR - 70), (ex, ey)], fill=BLACK, width=4)


def elevator_doors(d, x0, x1, top, open_frac=0.0, label="12", label_col=AMBER):
    d.rectangle([x0 - 16, top - 16, x1 + 16, FLOOR], outline=WHITE, width=10)
    cx = (x0 + x1) / 2
    gap = (x1 - x0) / 2 * open_frac
    d.rectangle([x0, top, x1, FLOOR], fill=BLACK)
    d.rectangle([x0, top, cx - gap, FLOOR], fill=(196, 196, 190))
    d.rectangle([cx + gap, top, x1, FLOOR], fill=(196, 196, 190))
    if open_frac < 0.02:
        d.line([(cx, top), (cx, FLOOR)], fill=BLACK, width=6)
    d.rounded_rectangle([cx - 70, top - 110, cx + 70, top - 40], radius=8, outline=WHITE, width=5)
    f = mont(800, 44)
    d.text((cx - d.textlength(label, font=f) / 2, top - 103), label, font=f, fill=label_col)


def set_lobby(d, t, a):
    ground(d)
    for x in (360, 960, 1560):
        ceiling_light(d, x, 90)
    elevator_doors(d, 220, 560, 380, label="G")
    plant(d, 820)
    n = a.get("floors", 12)
    reveal = ease(t / 1.2) if a.get("you") == "nod" else 1.0
    bx, by, bw = 1080, 140 if n == 13 else 170, 460
    rh = 50
    d.rounded_rectangle([bx, by, bx + bw, by + n * rh + 100], radius=14, fill=WHITE)
    spaced_text(d, (bx + 36, by + 26), "FLOOR DIRECTORY", mont(800, 24), BLACK, 4)
    fb = mont(800, 34)
    for i in range(int(math.ceil(n * reveal))):
        yy = by + 78 + i * rh
        col = RED if (n == 13 and i == 0) else BLACK
        dx = 8 if (n == 13 and i == 0) else 0
        d.text((bx + 40 + dx, yy), f"{n - i:>2}", font=fb, fill=col)
        d.line([(bx + 120 + dx, yy + 22), (bx + bw - 40 + dx, yy + 22)], fill=col if col == RED else GREY, width=4)
    actor(d, t, a, 880, FLOOR, 1.4, facing=1, face="side")


def hallway_beyond(d, box, kind, t):
    x0, y0, x1, y1 = box
    warm = kind == "warm"
    d.rectangle(box, fill=fade(YELLOW, 0.18) if warm else (6, 6, 6))
    vx, vy = (x0 + x1) / 2, y0 + (y1 - y0) * 0.45
    line = fade(YELLOW, 0.55) if warm else (40, 40, 40)
    for k in range(7):
        d.line([(x0 + k * (x1 - x0) / 6, y1), (vx, vy)], fill=line, width=3)
    d.line([(x0, y0 + 40), (vx, vy)], fill=line, width=3)
    d.line([(x1, y0 + 40), (vx, vy)], fill=line, width=3)
    if warm:
        d.rounded_rectangle([x1 - 80, y1 - 210, x1 - 46, y1 - 120], radius=14, fill=RED)
        d.ellipse([vx - 30, y0 + 8, vx + 30, y0 + 24], fill=YELLOW)
    if kind == "voice":
        k = 0.35 + 0.15 * math.sin(t * 2)
        rig3(d, vx, vy + 150 + 30 * ease(t / 3), 0.42 + 0.06 * ease(t / 3), POSES["stand"], 1, fill=fade(WHITE, k))
        for j in range(3):
            rr = 30 + j * 26
            ph = (t * 1.5 + j * 0.33) % 1
            d.arc([vx + 30 - rr, vy - 10 - rr, vx + 30 + rr, vy - 10 + rr], -40, 40, fill=fade(WHITE, 0.6 * (1 - ph)), width=6)


def set_elevator(d, t, a):
    """Elevator interior, looking at the doors from inside the car."""
    # perspective box
    bx0, by0, bx1, by1 = 660, 220, 1260, 820
    d.line([(bx0, by1), (180, 1080)], fill=GREY, width=4)
    d.line([(bx1, by1), (1740, 1080)], fill=GREY, width=4)
    d.line([(bx0, by0), (180, -40)], fill=GREY, width=4)
    d.line([(bx1, by0), (1740, -40)], fill=GREY, width=4)
    d.line([(bx0, by1), (bx1, by1)], fill=GREY, width=4)
    # handrails
    d.line([(300, 640), (bx0, 590)], fill=WHITE, width=10)
    d.line([(1620, 640), (bx1, 590)], fill=WHITE, width=10)
    # ceiling light
    d.polygon([(860, 60), (1060, 60), (1100, 90), (820, 90)], fill=YELLOW if not a.get("moving") or int(t * 7) % 9 else DIM)
    # side button panel on right wall
    d.polygon([(1340, 400), (1420, 380), (1420, 640), (1340, 620)], outline=WHITE, width=5)
    for k in range(5):
        cy = 420 + k * 42
        d.ellipse([1365, cy, 1395, cy + 26], outline=WHITE, width=3)
    # doors
    doors = a.get("doors", "closed")
    of = {"closed": 0.0, "open": 1.0}.get(doors)
    if doors == "opening":
        of = ease((t - 0.3) / 2.0)
    elif doors == "closing":
        of = 1.0 - ease((t - 0.2) / 1.6)
    elif doors == "closing_slow":
        of = 1.0 - 0.35 * ease(t / 4.0)
    beyond = a.get("beyond", "dark")
    box = (bx0 + 70, by0 + 60, bx1 - 70, by1)
    hallway_beyond(d, box, beyond, t)
    x0, y0, x1, y1 = box
    cx = (x0 + x1) / 2
    gap = (x1 - x0) / 2 * of
    d.rectangle([x0, y0, cx - gap, y1], fill=(196, 196, 190))
    d.rectangle([cx + gap, y0, x1, y1], fill=(196, 196, 190))
    for dx in (cx - gap - 40, cx + gap + 40):
        d.line([(dx, y0 + 30), (dx, y1 - 30)], fill=(140, 140, 136), width=4)
    if of < 0.02:
        d.line([(cx, y0), (cx, y1)], fill=BLACK, width=6)
    d.rectangle([x0 - 14, y0 - 14, x1 + 14, y1 + 2], outline=WHITE, width=10)
    # floor display above doors
    disp = a.get("display", "12")
    if a.get("moving"):
        disp = ["12", "13", "??", "13", "7"][int(t * 3) % 5] if disp == "??" else disp
    flick = (int(t * 10) % 23) != 7
    d.rounded_rectangle([cx - 90, y0 - 140, cx + 90, y0 - 50], radius=10, outline=WHITE, width=6)
    if flick:
        f = mont(800, 56)
        col = RED if (a.get("x") and t > 0.6) else AMBER
        d.text((cx - d.textlength(disp, font=f) / 2, y0 - 132), disp, font=f, fill=col)
    if a.get("moving"):
        sx, sy = shake(t, 2, 23)
        d.line([(bx0 + sx, by1 + 4 + sy), (bx1 + sx, by1 + 4 + sy)], fill=DIM, width=3)
    # you, in the car, back to camera
    act = a.get("you", "stand")
    actor(d, t, a, cx, 1000, 1.15, facing=1, face=None)
    if a.get("x") and t > 0.5:
        kk = ease((t - 0.5) / 0.25)
        d.line([(x0, y1 - 4), (x0 + (x1 - x0) * kk, y1 - 4)], fill=RED, width=10)
        v2.big_x(d, x0 - 230, 400, s=70 * appear(t, 0.5)[1], w=16)


def set_hallway(d, t, a):
    warm = a.get("warm")
    dark = a.get("dark")
    if warm:
        d.rectangle([0, 0, W, FLOOR], fill=fade(YELLOW, 0.08))
    ground(d)
    d.line([(0, 140), (W, 140)], fill=GREY, width=4)
    hl = a.get("highlight")
    for i, x in enumerate((300, 760, 1220, 1680)):
        on = not dark or (int(t * 6 + i) % 11 != 0)
        if hl == "lights":
            on = t > i * 0.25
        ceiling_light(d, x, 150, on=on and not (dark and i == 2), cone=not dark)
    elevator_doors(d, 80, 360, 380, label="13", label_col=AMBER)
    for i, x in enumerate((560, 1000)):
        d.rectangle([x, 380, x + 200, FLOOR], fill=WHITE)
        d.rectangle([x + 26, 410, x + 174, 600], outline=BLACK, width=5)
        d.rectangle([x + 26, 630, x + 174, FLOOR - 30], outline=BLACK, width=5)
        d.ellipse([x + 150, 610, x + 172, 632], fill=BLACK)
        d.rounded_rectangle([x + 60, 330, x + 140, 362], radius=4, outline=GREY, width=3)
    # extinguisher cabinet
    if a.get("no_ext"):
        pulse = 0.5 + 0.5 * math.sin(t * 5)
        for k in range(14):
            ang = k / 14 * 2 * math.pi + t * 0.5
            px, py = 1500 + 36 * math.cos(ang), 600 + 90 * math.sin(ang)
            d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=fade(GREY, pulse))
        if a.get("x"):
            v2.big_x(d, 1500, 600, s=110 * appear(t, 0.3)[1], w=20)
    else:
        d.rectangle([1450, 470, 1550, 730], outline=WHITE, width=6)
        d.rounded_rectangle([1475, 520, 1525, 710], radius=24, fill=RED)
        if hl == "ext":
            k = 0.5 + 0.5 * math.sin(t * 6)
            d.rectangle([1430, 450, 1570, 750], outline=fade(GREEN, k), width=6)
    # exit sign
    ex_on = hl != "exit" or int(t * 4) % 2 == 0
    d.rounded_rectangle([1600, 200, 1760, 260], radius=6, fill=GREEN if ex_on else DIM)
    spaced_text(d, (1680, 210), "EXIT", mont(800, 34), BLACK, 4, anchor="m")
    if hl == "carpet":
        k = ease(t / 0.6)
        d.rectangle([0, FLOOR, W * k, FLOOR + 6], fill=AMBER)
    act = a.get("you")
    if act:
        actor(d, t, a, 1180, FLOOR, 1.35, facing=1, face="side")


def set_office(d, t, a):
    ground(d)
    # window + moon
    d.rectangle([180, 200, 520, 520], outline=WHITE, width=10)
    d.line([(350, 200), (350, 520)], fill=WHITE, width=8)
    d.line([(180, 360), (520, 360)], fill=WHITE, width=8)
    d.ellipse([400, 240, 470, 310], fill=YELLOW)
    d.ellipse([422, 232, 492, 302], fill=BLACK)
    # clock
    cx, cy, r = 760, 260, 70
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE, width=8)
    sp = 400 if a.get("clock_fast") else 30
    a1 = math.radians(t * sp)
    a2 = math.radians(354 + t * sp / 12)
    thick(d, [(cx, cy), (cx + math.sin(a1) * 52, cy - math.cos(a1) * 52)], 6, WHITE)
    thick(d, [(cx, cy), (cx + math.sin(a2) * 34, cy - math.cos(a2) * 34)], 10, WHITE)
    # filing cabinet
    d.rectangle([1600, 520, 1780, FLOOR], fill=WHITE)
    for k in range(3):
        y = 560 + k * 110
        d.line([(1600, y + 90), (1780, y + 90)], fill=BLACK, width=6)
        d.rectangle([1660, y + 30, 1720, y + 44], fill=BLACK)
    plant(d, 1480)
    # desk + monitor + lamp
    d.rounded_rectangle([860, 640, 1380, 668], radius=8, fill=WHITE)
    d.rectangle([890, 668, 914, FLOOR], fill=WHITE)
    d.rectangle([1326, 668, 1350, FLOOR], fill=WHITE)
    d.rounded_rectangle([1120, 470, 1330, 610], radius=8, outline=WHITE, width=8)
    glow = 0.25 + 0.05 * math.sin(t * 3)
    d.rectangle([1132, 482, 1318, 598], fill=fade((180, 200, 255), glow))
    d.rectangle([1215, 610, 1235, 640], fill=WHITE)
    lamp = 1.0
    if a.get("tremble") and int(t * 7) % 9 == 0:
        lamp = 0.2
    d.polygon([(960, 500), (880, 640), (1050, 640)], fill=fade(YELLOW, 0.35 * lamp))
    thick(d, [(960, 640), (960, 500), (930, 480)], 10, WHITE)
    d.ellipse([900, 462, 960, 500], fill=fade(YELLOW, lamp))
    # mysterious elevator door appearing at the left (rule 3 payoff)
    if a.get("door13"):
        k = ease(t / 1.2)
        elevator_doors(d, 120, 380, 420, open_frac=0.12 * k, label="13", label_col=fade(RED, k))
    act = a.get("you", "read")
    tr = 3 * math.sin(t * 38) if a.get("tremble") and t > 0.6 else 0
    if act == "walk_in":
        actor(d, t, a, 1000, FLOOR, 1.3, facing=1, face="side")
    else:
        actor(d, t, dict(a, you=act), 1000 + tr, FLOOR, 1.3, facing=1, face="side")


# ----------------------------------------------------------------------------
# Beats
# ----------------------------------------------------------------------------


def beat_elevator(d, img, t, dur, a, ctx):
    set_elevator(d, t, a)


def beat_lobby(d, img, t, dur, a, ctx):
    set_lobby(d, t, a)


def beat_hallway(d, img, t, dur, a, ctx):
    set_hallway(d, t, a)


def beat_office(d, img, t, dur, a, ctx):
    set_office(d, t, a)


def beat_display_close(d, img, t, dur, a, ctx):
    seq = a.get("seq", ["13"])
    i = min(len(seq) - 1, int(t / a.get("every", 1.0)))
    txt = seq[i]
    local = t - i * a.get("every", 1.0)
    d.rounded_rectangle([560, 260, 1360, 740], radius=40, outline=WHITE, width=16)
    d.rounded_rectangle([600, 300, 1320, 700], radius=24, fill=(14, 12, 10))
    for yy in range(300, 700, 8):
        d.line([(600, yy), (1320, yy)], fill=(22, 20, 16), width=2)
    f = mont(800, 300)
    col = RED if (a.get("red_last") and i == len(seq) - 1) else AMBER
    roll = 80 * (1 - ease(local / 0.18)) if i > 0 else 0
    if (int(t * 10) % 23) != 7:
        d.text((960 - d.textlength(txt, font=f) / 2, 330 - roll), txt, font=f, fill=col)
    d.polygon([(960, 200), (920, 240), (1000, 240)], fill=WHITE)


def beat_face(d, img, t, dur, a, ctx):
    expr = a.get("expr", "neutral")
    cx, cy = 960 + 14 * math.sin(t * 0.8), 420 + 6 * math.sin(t * 1.1)
    r = 250
    d.ellipse([cx - 420, cy + 250, cx + 420, cy + 620], fill=WHITE)
    d.rectangle([cx - 420, cy + 430, cx + 420, cy + 520], fill=WHITE)
    d.rectangle([0, cy + 520, W, H], fill=BLACK)
    d.ellipse([cx - r - 14, cy - r - 14, cx + r + 14, cy + r + 14], fill=BLACK)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
    look = 18 * math.sin(t * 1.3)
    if expr == "side":
        look = 60 * ease(t / 0.4) * (1 if int(t / 1.4) % 2 == 0 else -1)
    blink = 0.3 < (t % 3.1) < 0.42
    for sx in (-1, 1):
        ex, ey = cx + sx * 95 + look, cy - 10
        if blink:
            d.line([(ex - 30, ey), (ex + 30, ey)], fill=BLACK, width=12)
        else:
            d.ellipse([ex - 26, ey - 26, ex + 26, ey + 26], fill=BLACK)
    if a.get("sweat") and t > 0.5:
        sy = cy - 140 + 60 * ((t - 0.5) % 1.5)
        d.ellipse([cx + 190, sy, cx + 220, sy + 40], fill=(150, 200, 255))
        d.polygon([(cx + 193, sy + 12), (cx + 217, sy + 12), (cx + 205, sy - 18)], fill=(150, 200, 255))


def beat_card_write(d, img, t, dur, a, ctx):
    num = a.get("number", "12")
    x, y, w, h = 560, 300, 800, 440
    d.rounded_rectangle([x, y, x + w, y + h], radius=24, fill=WHITE)
    for k in range(5):
        d.line([(x + 40, y + 120 + k * 60), (x + w - 40, y + 120 + k * 60)], fill=(170, 190, 220), width=3)
    d.line([(x + 110, y), (x + 110, y + h)], fill=(230, 140, 140), width=3)
    spaced_text(d, (x + 140, y + 34), "FLOORS IN MY BUILDING", mont(700, 28), GREY, 3)
    f = mont(800, 200)
    if a.get("rewrite"):
        d.text((x + 170, y + 130), "12", font=f, fill=BLACK)
        sk = ease((t - 0.2) / 0.4)
        thick(d, [(x + 160, y + 240), (x + 160 + 260 * sk, y + 240)], 16, RED)
        start, colr = 0.7, RED
        tx = x + 470
    else:
        start, colr = 0.1, BLACK
        tx = x + 300
    k = ease((t - start) / 0.9)
    if k > 0:
        tile = Image.new("RGBA", (360, 260), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((10, 0), num, font=f, fill=colr)
        tile = tile.crop((0, 0, max(1, int(360 * k)), 260))
        img.paste(tile, (int(tx), y + 130), tile)
        px = tx + 330 * k
        thick(d, [(px + 160, y + 520), (px + 10, y + 300)], 22, BLACK)
        thick(d, [(px + 160, y + 520), (px + 10, y + 300)], 14, AMBER)
        rig_hand = (px + 190, y + 560)
        d.ellipse([rig_hand[0] - 50, rig_hand[1] - 50, rig_hand[0] + 50, rig_hand[1] + 50], fill=WHITE, outline=BLACK, width=6)


def beat_wallet(d, img, t, dur, a, ctx):
    num = a.get("number", "12")
    red = a.get("red")
    v2.SHOTS["wallet"](d, img, t, dur, {}, ctx) if not red else None
    if red:
        v2.SHOTS["wallet"](d, img, t, dur, {}, ctx)


def beat_people_row(d, img, t, dur, a, ctx):
    trust = a.get("trust")
    # a panel on the wall that everyone faces
    d.rounded_rectangle([1500, 220, 1700, 320], radius=10, outline=WHITE, width=6)
    f = mont(800, 60)
    d.text((1600 - d.textlength("12", font=f) / 2, 232), "12", font=f, fill=AMBER)
    ground(d, 120, 1800)
    for i in range(9):
        x = 200 + i * 140
        k, sc = appear(t, i * 0.06, 0.3)
        if not k:
            continue
        counter = i == 2
        pose = dict(POSES["look_up"] if (trust and not counter) else POSES["stand"])
        col = WHITE if counter else (GREY if trust else WHITE)
        rig3(d, x, FLOOR, 0.62 * sc, breathe(pose, t + i, 0.5), 1, col, face="side",
             prop="card" if counter else None)
    if trust:
        for i in range(9):
            if i == 2:
                continue
            x = 200 + i * 140
            v2.dotted(d, (x + 20, 560), (1500, 290), color=fade(GREY, 0.6), step=34, r=3, phase=t,
                      upto=ease((t - 0.2) / 0.6))
    else:
        spaced_text(d, (480, 470), "1 IN 9", mont(800, 40), YELLOW, 6, anchor="m")


def beat_card_vs_panel(d, img, t, dur, a, ctx):
    stage = a.get("stage", 1)
    k = ease(t / 0.5)
    v2.card(d, 300 - 400 * (1 - k), 360, "12")
    if stage == 2:
        k2 = ease(t / 0.5)
        v2.display(d, 1300 + 500 * (1 - k2), 380, "13", w=320, h=180, color=AMBER, on=(int(t * 10) % 19 != 7))
        pk, sc = appear(t, 0.6)
        if pk:
            sx, sy = shake(t, 6)
            c0, c1 = 960 + sx, 460 + sy
            L = 80 * sc
            thick(d, [(c0 - L, c1 - 26 * sc), (c0 + L, c1 - 26 * sc)], int(18 * sc), RED)
            thick(d, [(c0 - L, c1 + 26 * sc), (c0 + L, c1 + 26 * sc)], int(18 * sc), RED)
            thick(d, [(c0 + 40 * sc, c1 - 90 * sc), (c0 - 40 * sc, c1 + 90 * sc)], int(16 * sc), RED)
    else:
        rig3(d, 1100, FLOOR, 1.2, breathe(POSES["hold"], t), -1, face="side", prop="card")


def beat_hallway_compare(d, img, t, dur, a, ctx):
    v2.SHOTS["hallway_compare"](d, img, t, dur, a, ctx)


def beat_evidence(d, img, t, dur, a, ctx):
    """SURVEILLANCE RECORD: a tilted CCTV still of a set, with a record tag."""
    scene = a.get("scene", "step_out")
    still = Image.new("RGB", (W, H), BLACK)
    sd = ImageDraw.Draw(still)
    set_hallway(sd, 2.0, {"dark": True})
    if scene == "step_out":
        rig3(sd, 470, FLOOR, 1.1, walk_pose(2.0), 1, face="side")
    if scene in ("cart", "cart_empty"):
        cx0 = 820
        sd.rectangle([cx0, 640, cx0 + 240, 840], fill=WHITE)
        sd.rectangle([cx0 + 20, 600, cx0 + 90, 640], fill=WHITE)
        sd.line([(cx0 + 240, 660), (cx0 + 300, 560)], fill=WHITE, width=10)
        for wx in (cx0 + 30, cx0 + 210):
            sd.ellipse([wx - 26, 846, wx + 26, 898], fill=WHITE, outline=BLACK, width=6)
        if scene == "cart":
            rig3(sd, cx0 + 360, FLOOR, 1.1, POSES["stand"], -1, face="side")
    gray = ImageOps.grayscale(still).point(lambda v: int(v * 0.85))
    still = ImageOps.colorize(gray, (8, 10, 8), (215, 230, 215)).resize((960, 540))
    sdd = ImageDraw.Draw(still)
    for yy in range(0, 540, 4):
        sdd.line([(0, yy), (960, yy)], fill=(0, 0, 0), width=1)
    sdd.text((24, 18), "CAM 04", font=mont(700, 26), fill=(230, 240, 230))
    sdd.text((720, 18), f"02:13:{int(7 + t) % 60:02d}", font=mont(700, 26), fill=(230, 240, 230))
    if int(t * 2) % 2 == 0:
        sdd.ellipse([24, 500, 44, 520], fill=RED)
        sdd.text((54, 494), "REC", font=mont(700, 24), fill=(230, 240, 230))
    frame = Image.new("RGBA", (1000, 580), (238, 238, 232, 255))
    frame.paste(still, (20, 20))
    z = 1.0 + (0.25 * ease(t / 2.5) if a.get("zoom") else 0.0)
    if z > 1.0:
        cw, ch = 1000 / z, 580 / z
        frame = frame.crop(((1000 - cw) * 0.35, (580 - ch) * 0.6, (1000 - cw) * 0.35 + cw, (580 - ch) * 0.6 + ch)).resize((1000, 580))
    k = ease(t / 0.35)
    frame = frame.rotate(-3 * k, resample=Image.BICUBIC, expand=True)
    img.paste(frame, (180, int(200 + 40 * (1 - k))), frame)
    # brackets
    for (bx, by, sx, sy) in ((160, 180, 1, 1), (1200, 180, -1, 1), (160, 820, 1, -1), (1200, 820, -1, -1)):
        d.line([(bx, by), (bx + 40 * sx, by)], fill=WHITE, width=4)
        d.line([(bx, by), (bx, by + 40 * sy)], fill=WHITE, width=4)
    # tag
    d.rectangle([1290, 250, 1300, 300], fill=YELLOW)
    spaced_text(d, (1320, 250), f"RECORD {a.get('record', 7)}", mont(800, 42), WHITE, 4)
    tag = [("LOCATION", a.get("location", "OHIO")), ("FLOOR", "13"), ("STATUS", a.get("status", "OPEN"))]
    for i, (kk, vv) in enumerate(tag):
        if t > 0.3 + i * 0.25:
            spaced_text(d, (1320, 330 + i * 46), f"{kk}: {vv}", mont(600, 26),
                        RED if kk == "STATUS" and vv in ("PROMOTED", "MISSING") else GREY, 3)


def beat_officer(d, img, t, dur, a, ctx):
    """The Compliance Officer: hard hat, clipboard, podium, deadpan acting."""
    ground(d, 560, 1360)
    d.polygon([(780, FLOOR), (1140, FLOOR), (1100, 640), (820, 640)], fill=WHITE)
    d.rectangle([800, 620, 1120, 650], fill=WHITE)
    spaced_text(d, (960, 720), "OAB", mont(800, 54), BLACK, 10, anchor="m")
    # reads the clipboard, looks up at the camera, gestures with the free hand
    read = POSES["hold"]
    look = dict(POSES["hold"], head=-4)
    gesture = dict(POSES["hold"], head=-2, ls=-70, le=-50)
    if t < 0.7:
        pose = blend(read, dict(read, head=18), ease(t / 0.4))
        expr = "closed"
    elif t < 1.4:
        pose = blend(dict(read, head=18), look, ease((t - 0.7) / 0.3))
        expr = a.get("expr", "neutral")
    else:
        pose = blend(look, gesture, ease((t - 1.4) / 0.3) * (0.5 + 0.5 * math.sin((t - 1.4) * 3)))
        expr = a.get("expr", "neutral")
    if a.get("act") == "read":
        pose = blend(read, dict(read, head=18), 0.5 + 0.5 * math.sin(t * 2))
    blink = 0.25 < (t % 2.7) < 0.35
    rig3(d, 960 + 4 * math.sin(t * 0.9), 640 - 2, 1.25, breathe(pose, t, 1.2), 1, face="front",
         expr="closed" if blink else expr, prop="clipboard", hat="hardhat", sweat=a.get("sweat", False) and t > 0.6)
    d.rectangle([1230, 300, 1240, 400], fill=YELLOW)
    spaced_text(d, (1262, 300), "COMPLIANCE", mont(800, 34), WHITE, 6)
    spaced_text(d, (1262, 350), "OFFICER", mont(600, 28), GREY, 6)


def beat_voice_bubble(d, img, t, dur, a, ctx):
    set_hallway(d, t, {"dark": True})
    k, sc = appear(t, 0.2)
    bx, by = 520, 250
    if k:
        d.rounded_rectangle(v2.scaled_box(bx, by, 380, 240, sc), radius=40, outline=WHITE, width=8, fill=BLACK)
        d.polygon([(bx - 60, by + 110 * sc), (bx - 120, by + 190 * sc), (bx - 10, by + 115 * sc)], fill=WHITE)
        # manager icon: head + tie
        rig3(d, bx, by + 95 * sc, 0.55 * sc, POSES["stand"], 1, face="front")
        d.polygon([(bx - 10, by - 18 * sc), (bx + 10, by - 18 * sc), (bx + 16, by + 40 * sc), (bx, by + 54 * sc), (bx - 16, by + 40 * sc)], fill=BLACK)
    rig3(d, 1150, FLOOR, 1.15, breathe(POSES["freeze"] if t > 0.6 else POSES["stand"], t), -1, face="side", expr="wide")


def beat_rule_card(d, img, t, dur, a, ctx):
    rule, name = ctx["rule"], ctx["rule_name"]
    f = mont(800, 150)
    word = "RULE"
    tw = d.textlength(word, font=f)
    box = 170
    x0 = W / 2 - (tw + 40 + box) / 2
    y0 = 250
    k = ease(t / 0.3)
    d.text((x0 - 50 * (1 - k), y0), word, font=f, fill=fade(WHITE, k))
    bk, bsc = appear(t, 0.2)
    if bk:
        bx = x0 + tw + 40
        d.rounded_rectangle(v2.scaled_box(bx + box / 2, y0 + 18 + box / 2, box, box, bsc), radius=16, fill=WHITE)
        fn = mont(800, int(130 * bsc))
        d.text((bx + box / 2 - d.textlength(str(rule), font=fn) / 2, y0 + 18 + box / 2 - 88 * bsc), str(rule), font=fn, fill=BLACK)
    total = tw + 40 + box
    ul = total * ease((t - 0.35) / 0.5)
    d.rectangle([W / 2 - total / 2, y0 + 220, W / 2 - total / 2 + ul, y0 + 228], fill=RED)
    n = int(len(name) * ease((t - 0.5) / 0.8))
    spaced_text(d, (W / 2, y0 + 262), name[:n], mont(700, 58), WHITE, 6, anchor="m")
    for i in range(7):
        pk, psc = appear(t, 0.8 + i * 0.05, 0.25)
        if not pk:
            continue
        bx = W / 2 - 7 * 64 / 2 + i * 64 + 24
        on, done = i + 1 == rule, i + 1 < rule
        d.rounded_rectangle(v2.scaled_box(bx, y0 + 380, 48, 48, psc), radius=8,
                            outline=WHITE if (on or done) else DIM, width=3, fill=WHITE if on else None)
        fs = mont(700, 24)
        d.text((bx - d.textlength(str(i + 1), font=fs) / 2, y0 + 366), str(i + 1), font=fs,
               fill=BLACK if on else (WHITE if done else DIM))


def beat_button(d, img, t, dur, a, ctx):
    mode = a.get("mode", "hover")
    if mode == "wire":
        return v2.SHOTS["button_wire"](d, img, t, dur, a, ctx)
    if mode == "press":
        return v2.SHOTS["button_press"](d, img, t, dur, a, ctx)
    cx, cy = 960, 500
    d.rounded_rectangle([700, 160, 1220, 860], radius=30, outline=WHITE, width=10)
    labs = [">|<", "<|>", "13", "12"]
    for i, lab in enumerate(labs):
        yy = 250 + i * 150
        hot = i == 0
        col = (RED if mode == "withdraw" and hot else WHITE) if hot else GREY
        d.ellipse([890, yy, 1030, yy + 140], outline=col, width=8)
        f = mont(800, 44)
        d.text((960 - d.textlength(lab, font=f) / 2, yy + 44), lab, font=f, fill=col)
    if mode == "hover":
        p = ease(t / 1.2)
        fx, fy = 1000 + (1 - p) * 500, 330 + (1 - p) * 400 + 10 * math.sin(t * 6) * p
    else:  # withdraw: hand pulls away
        p = ease(t / 0.6)
        fx, fy = 1000 + p * 600, 330 + p * 500
    thick(d, [(fx + 270, fy + 320), (fx + 70, fy + 80)], 86, BLACK)
    thick(d, [(fx + 270, fy + 320), (fx + 70, fy + 80)], 70, WHITE)
    thick(d, [(fx + 70, fy + 80), (fx + 4, fy + 4)], 46, BLACK)
    thick(d, [(fx + 70, fy + 80), (fx + 4, fy + 4)], 34, WHITE)


def beat_counter(d, img, t, dur, a, ctx):
    if a.get("silent"):
        f = mont(800, 260)
        s = "90"
        d.text((W / 2 - d.textlength(s, font=f) / 2, 250), s, font=f, fill=WHITE)
        spaced_text(d, (W / 2, 560), "SECONDS", mont(700, 40), GREY, 10, anchor="m")
        cx, cy, r = W / 2, 420, 280
        d.arc([cx - r, cy - r, cx + r, cy + r], -90, -90 + 360 * (1 - ease(t / max(1, dur))) , fill=AMBER, width=10)
        return
    v2.SHOTS["counter"](d, img, t, dur, a, ctx)


def beat_counter_loop(d, img, t, dur, a, ctx):
    v2.SHOTS["counter_loop"](d, img, t + (0 if a.get("upto") else 1.1), dur, a, ctx)


def passthrough(name):
    def f(d, img, t, dur, a, ctx):
        return v2.SHOTS[name](d, img, t, dur, a, ctx)
    return f


BEATS = {k[5:]: v for k, v in dict(globals()).items() if k.startswith("beat_")}
for _n in ("seven_rules", "rules_shuffled", "stat", "org_chart", "number_row", "eye", "building_floors", "end_card"):
    BEATS[_n] = passthrough(_n)


# ----------------------------------------------------------------------------
# Timeline (phrase-level synthesis)
# ----------------------------------------------------------------------------


def build_timeline(ep, voice, out_dir):
    vcfg = ep.get("voice", {})
    lines_dir = os.path.join(out_dir, "phrases")
    os.makedirs(lines_dir, exist_ok=True)
    t = 0.0
    sr = None
    pieces, beats, segs = [], [], []
    for si, seg in enumerate(ep["segments"]):
        t += seg.get("pre_pause", 1.2)
        seg_start = t
        for bi, bt in enumerate(seg["beats"]):
            text = bt["text"]
            key = re.sub(r"[^a-z0-9]+", "_", text.lower())[:60]
            path = os.path.join(lines_dir, f"{seg['id']}_{bi:02d}_{key}.wav")
            if not os.path.exists(path):
                v1.synth_line(text, voice, voice + ".json", path, vcfg)
            s, x = v1.read_wav(path)
            idx = np.where(np.abs(x) > 0.01)[0]
            if len(idx):
                x = x[max(0, idx[0] - int(0.04 * s)): min(len(x), idx[-1] + int(0.2 * s))]
            sr = sr or s
            dur = len(x) / sr
            pieces.append((t, x))
            beats.append({"seg": si, "start": t, "end": t + dur, **bt})
            last = bi == len(seg["beats"]) - 1
            sentence_end = text.rstrip().endswith((".", "?", "!", "..."))
            t += dur + (0.0 if last else (0.95 if sentence_end else 0.44))
        t += seg.get("post_pause", 0.0)
        segs.append({"id": seg["id"], "scene": seg["id"], "rule": seg.get("rule"), "start": seg_start, "end": t,
                     "silence_before": seg.get("silence_before", False), "rule_name": seg.get("rule_name", "")})
    for i in range(len(segs) - 1):
        segs[i]["end"] = segs[i + 1]["start"]
    total = t + 1.0
    segs[-1]["end"] = total
    track = np.zeros(int(total * sr) + sr, dtype=np.float32)
    for st, x in pieces:
        a = int(st * sr)
        track[a:a + len(x)] += x
    return sr, track, beats, segs, total


def master(mix, sr, target_db=-16.0):
    win = int(0.05 * sr)
    n = len(mix) // win
    db = 20 * np.log10(np.sqrt((mix[: n * win].reshape(n, win) ** 2).mean(axis=1)) + 1e-6)
    voiced = db > np.percentile(db, 10) + 12
    cur = np.median(db[voiced]) if voiced.any() else -30
    g = 10 ** ((target_db - cur) / 20)
    y = mix * g
    ceil = 10 ** (-1 / 20)
    return np.tanh(y / ceil) * ceil


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------


class Plan:
    def __init__(self, ep, beats, segs, total):
        self.ep, self.segs, self.total = ep, segs, total
        lead = 0.12
        self.shots = []
        for k, b in enumerate(beats):
            start = max(0.0, b["start"] - lead)
            end = beats[k + 1]["start"] - lead if k + 1 < len(beats) else total
            seg = ep["segments"][b["seg"]]
            prev_flag = any(beats[j].get("glitch") for j in range(max(0, k - 2), k))
            auto_glitch = (k % 7 == 3) and not prev_flag and b["beat"] not in ("rule_card", "end_card", "officer")
            self.shots.append({"start": start, "end": max(start + 0.4, end), "voice_start": b["start"],
                               "voice_end": b["end"], "text": b["text"], "beat": b["beat"],
                               "args": b.get("args", {}), "glitch": b.get("glitch", False) or auto_glitch,
                               "rule": seg.get("rule"), "rule_name": seg.get("rule_name", "")})
        self.blackouts = [(s["start"] - 2.4, s["start"] - 0.15) for s in segs if s["silence_before"]]


PLAN = None


def init_worker(plan):
    global PLAN
    PLAN = plan


def add_glow(img):
    small = img.resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(4))
    big = ImageEnhance.Brightness(small.resize((W, H), Image.BILINEAR)).enhance(0.42)
    return ImageChops.add(img, big)


def draw_caption(d, text, k):
    f = mont(700, 46)
    text = text.upper()
    words = text.split()
    lines, cur = [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if spaced_width(d, trial, f, 2) <= 1250:
            cur = trial
        else:
            lines.append(cur)
            cur = w_
    lines.append(cur)
    y = 905 if len(lines) == 1 else 880
    wmax = max(spaced_width(d, ln, f, 2) for ln in lines)
    d.rounded_rectangle([W / 2 - wmax / 2 - 28, y - 14, W / 2 + wmax / 2 + 28, y + 58 * len(lines) + 4],
                        radius=10, fill=BLACK)
    for ln in lines:
        spaced_text(d, (W / 2, y), ln, f, fade(WHITE, k), 2, anchor="m")
        y += 58


def render_frame(i, fps, scale):
    plan = PLAN
    t = i / fps
    out = Image.new("RGB", (W, H), BLACK)
    if t >= plan.shots[0]["start"] and not any(a <= t < b for a, b in plan.blackouts):
        sh = next((s for s in reversed(plan.shots) if s["start"] <= t), plan.shots[0])
        ctx = {"rule": sh["rule"], "rule_name": sh["rule_name"]}
        tl, dur = t - sh["start"], sh["end"] - sh["start"]
        layer = Image.new("RGB", (W, H), BLACK)
        ld = ImageDraw.Draw(layer)
        BEATS[sh["beat"]](ld, layer, tl, dur, sh["args"], ctx)
        cx, cy, z = sh["args"].get("cam", [960, 540, 1.0])
        z = z * (1.0 + 0.06 * ease(tl / max(dur, 0.5)))
        cw, ch = W / z, H / z
        x0 = min(max(0, cx - cw / 2), W - cw)
        y0 = min(max(0, cy - ch / 2), H - ch)
        layer = layer.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch)))
        if sh["beat"] in ("rule_card", "end_card"):
            layer = layer.resize((W, H), Image.BILINEAR)
        else:
            fit = 0.84
            small = layer.resize((int(W * fit), int(H * fit)), Image.BILINEAR)
            layer = Image.new("RGB", (W, H), BLACK)
            layer.paste(small, (int(W / 2 - W * fit / 2), int(70)))
        layer = add_glow(layer)
        if sh["args"].get("red"):
            layer = v2.red_takeover(layer)
        out = layer
        d = ImageDraw.Draw(out)
        v2.draw_hud(d, plan.ep, t, sh["rule"])
        if sh["beat"] != "end_card":
            if sh["voice_start"] - 0.05 <= t <= sh["voice_end"] + 0.3:
                k = ease((t - sh["voice_start"] + 0.05) / 0.12)
                draw_caption(d, sh["text"], k)
        if sh["glitch"] and tl < 0.17:
            out = v2.glitch(out, i)
    if scale != 1.0:
        out = out.resize((int(W * scale), int(H * scale)), Image.BILINEAR)
    return out.tobytes()


def _render(args):
    return render_frame(*args)


def render_video(plan, path, fps, scale, workers):
    w, h = int(W * scale), int(H * scale)
    n = int(math.ceil(plan.total * fps))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
           "-i", "-", "-vf", "noise=alls=6:allf=t+u,vignette=PI/5,format=yuv420p", "-c:v", "libx264",
           "-preset", "slow", "-crf", "21", "-maxrate", "9M", "-bufsize", "18M", "-r", str(fps), path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(workers, initializer=init_worker, initargs=(plan,)) as pool:
        for k, buf in enumerate(pool.imap(_render, ((i, fps, scale) for i in range(n)), chunksize=8)):
            proc.stdin.write(buf)
            if k % (fps * 30) == 0:
                print(f"  render {100 * k // n:3d}%", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")


def render_thumbnail(ep, path):
    img = Image.new("RGB", (W, H), BLACK)
    d = ImageDraw.Draw(img)
    set_elevator(d, 3.0, {"display": "13", "doors": "open", "you": "stand", "beyond": "voice"})
    img = add_glow(img)
    img = img.crop((300, 0, 1620, 742)).resize((W, int(742 * W / 1320)))
    out = Image.new("RGB", (W, H), BLACK)
    out.paste(img, (0, -40))
    d = ImageDraw.Draw(out)
    d.rectangle([0, 840, W, H], fill=RED)
    spaced_text(d, (W / 2, 862), ep["thumbnail_command"], mont(800, 150), WHITE, 6, anchor="m")
    spaced_text(d, (W - 70, 50), f"FILE {ep['file_number']}", mont(700, 44), GREY, 8, anchor="r")
    out.resize((1280, 720), Image.LANCZOS).save(path, quality=92)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode_json")
    ap.add_argument("--voice", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    args = ap.parse_args()
    ep = json.load(open(args.episode_json))
    os.makedirs(args.out, exist_ok=True)

    print("1/5 narration (per phrase)…", flush=True)
    sr, narr, beats, segs, total = build_timeline(ep, args.voice, args.out)
    print(f"    {len(beats)} beats, runtime {total:.1f}s ({int(total // 60)}:{int(total % 60):02d})", flush=True)
    json.dump({"total": total, "beats": beats, "segments": segs}, open(os.path.join(args.out, "timeline.json"), "w"), indent=1)

    print("2/5 tape processing…", flush=True)
    raw, fx = os.path.join(args.out, "narr_raw.wav"), os.path.join(args.out, "narr_fx.wav")
    v1.write_wav(raw, sr, narr)
    v1.tape_process(raw, fx)
    _, nf = v1.read_wav(fx)
    if len(nf) != len(narr):
        nf = np.interp(np.linspace(0, len(nf) - 1, len(narr)), np.arange(len(nf)), nf).astype(np.float32)

    print("3/5 sound bed + master…", flush=True)
    bed = v1.design_bed(sr, total, segs)
    n = min(len(bed), len(nf))
    mix = nf[:n] + bed[:n] * 0.8
    plan = Plan(ep, beats, segs, total)
    rng = np.random.default_rng(11)
    for sh in plan.shots:
        if sh["glitch"]:
            a = int(sh["start"] * sr)
            L = int(0.17 * sr)
            if 0 <= a < n - L:
                mix[a:a + L] += rng.standard_normal(L).astype(np.float32) * 0.04
    mix = master(mix, sr)
    v1.write_wav(os.path.join(args.out, "master.wav"), sr, mix)

    print("4/5 frames…", flush=True)
    fps = 12 if args.preview else FPS
    scale = 0.5 if args.preview else 1.0
    vid = os.path.join(args.out, "video_only.mp4")
    render_video(plan, vid, fps, scale, args.workers)

    print("5/5 mux…", flush=True)
    final = os.path.join(args.out, f"file{ep['file_number']}_v3{'_preview' if args.preview else ''}.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", vid, "-i", os.path.join(args.out, "master.wav"),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
                    "-movflags", "+faststart", final], check=True)
    os.remove(vid)
    render_thumbnail(ep, os.path.join(args.out, "thumbnail_v3.jpg"))
    print("done →", final)


if __name__ == "__main__":
    main()
