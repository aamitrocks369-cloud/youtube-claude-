#!/usr/bin/env python3
"""
Dark "tape" renderer. Same narration + sound pipeline as build_episode.py, but
the picture follows the reference motion grammar:

  - one shot per narrated line, cut slightly ahead of the voice
  - constant slow push-in on every shot
  - glowing white pictograms on black, accent colours only for meaning
    (yellow = light, red = danger, green = safe)
  - persistent tape HUD: brand/file top-left, timecode top-right,
    seven rule boxes top-centre
  - typed rule title cards
  - RGB-split / tear glitch on flagged lines
  - red takeover for the final twist

Usage:
    python3 scripts/build_episode_v2.py episodes/001-elevator/episode_v2.json \
        --voice voices/en-us-ryan-medium.onnx --out build/001v2 [--preview]
"""
import argparse
import copy
import json
import math
import os
import subprocess
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_episode as v1  # noqa: E402

W, H = 1920, 1080
FPS = 24
BLACK = (2, 2, 2)
WHITE = (238, 238, 232)
GREY = (120, 118, 114)
DIM = (52, 51, 50)
FAINT = (28, 28, 28)
YELLOW = (244, 192, 74)
RED = (226, 44, 40)
GREEN = (86, 206, 118)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, "assets", "fonts")
_fonts = {}


def mont(weight, size):
    key = (weight, size)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(os.path.join(FONT_DIR, f"montserrat-latin-{weight}-normal.woff"), size)
    return _fonts[key]


def spaced_width(d, text, f, spacing):
    return sum(d.textlength(c, font=f) for c in text) + spacing * max(0, len(text) - 1)


def spaced_text(d, xy, text, f, fill, spacing=0, anchor="l"):
    x, y = xy
    w = spaced_width(d, text, f, spacing)
    if anchor == "m":
        x -= w / 2
    elif anchor == "r":
        x -= w
    for c in text:
        d.text((x, y), c, font=f, fill=fill)
        x += d.textlength(c, font=f) + spacing
    return w


def ease(p):
    p = min(1.0, max(0.0, p))
    return p * p * (3 - 2 * p)


def pop(p):
    """Overshoot pop-in 0..1."""
    p = min(1.0, max(0.0, p))
    return 1 + 0.12 * math.sin(p * math.pi) * (1 - p) if p < 1 else 1.0


# ----------------------------------------------------------------------------
# Primitives (white-fill pictogram style)
# ----------------------------------------------------------------------------


def person(d, x, y, s=1.0, fill=WHITE, pose="stand", facing=1):
    v1.figure(d, x, y, scale=s, pose=pose, fill=fill, facing=facing)


def elevator_frame(d, cx, cy, w, h, open_frac, hallway=True, door=DIM, light=None):
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    if hallway:
        d.rectangle([x0, y0, x1, y1], fill=BLACK)
        vx, vy = cx, cy - h * 0.05
        for k in range(7):
            d.line([(x0 + k * w / 6, y1), (vx, vy)], fill=FAINT, width=3)
        d.line([(x0, y0 + h * 0.12), (vx, vy)], fill=FAINT, width=3)
        d.line([(x1, y0 + h * 0.12), (vx, vy)], fill=FAINT, width=3)
        if light:
            d.rectangle([vx - 26, vy - 46, vx + 26, vy + 10], fill=light)
        else:
            d.rectangle([vx - 22, vy - 42, vx + 22, vy + 8], outline=DIM, width=3)
    gap = (w / 2) * open_frac
    d.rectangle([x0, y0, cx - gap, y1], fill=door)
    d.rectangle([cx + gap, y0, x1, y1], fill=door)
    d.rectangle([x0 - 14, y0 - 14, x1 + 14, y1 + 14], outline=WHITE, width=12)


def display(d, x, y, text, w=230, h=130, color=RED, on=True):
    d.rounded_rectangle([x, y, x + w, y + h], radius=14, outline=WHITE, width=6)
    if on:
        f = mont(800, int(h * 0.58))
        tw = d.textlength(text, font=f)
        d.text((x + w / 2 - tw / 2, y + h * 0.16), text, font=f, fill=color)


def big_x(d, cx, cy, s=90, w=18, color=RED):
    v1.thick_line(d, [(cx - s, cy - s), (cx + s, cy + s)], w, color)
    v1.thick_line(d, [(cx - s, cy + s), (cx + s, cy - s)], w, color)


def check(d, cx, cy, s=90, w=20):
    v1.thick_line(d, [(cx - s, cy), (cx - s * 0.2, cy + s * 0.8), (cx + s, cy - s * 0.7)], w, GREEN)


def dotted(d, a, b, color=WHITE, step=26, r=5, phase=0.0, upto=1.0):
    (x0, y0), (x1, y1) = a, b
    n = int(math.hypot(x1 - x0, y1 - y0) / step)
    for i in range(int(n * upto)):
        t = (i + phase % 1) / max(1, n)
        x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)


def card(d, x, y, number, w=320, h=200, strike=False, color=WHITE, num_color=None):
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, outline=color, width=8)
    f = mont(800, 110)
    num_color = num_color or color
    tw = d.textlength(number, font=f)
    d.text((x + w / 2 - tw / 2, y + 28), number, font=f, fill=num_color)
    f2 = mont(600, 20)
    spaced_text(d, (x + w / 2, y + h - 40), "FLOORS", f2, GREY, 4, anchor="m")
    if strike:
        v1.thick_line(d, [(x + 50, y + 95), (x + w - 50, y + 95)], 12, RED)


def floor_board(d, x, y, n, reveal=1.0, red_top=False, w=440):
    rh = 50
    h = n * rh + 90
    d.rounded_rectangle([x, y, x + w, y + h], radius=16, outline=WHITE, width=6)
    spaced_text(d, (x + 34, y + 26), "FLOOR DIRECTORY", mont(600, 22), GREY, 4)
    f = mont(700, 34)
    shown = int(math.ceil(n * reveal))
    for i in range(shown):
        lab = str(n - i)
        yy = y + 74 + i * rh
        col, dx = WHITE, 0
        if red_top and i == 0:
            col, dx = RED, 8
        d.text((x + 40 + dx, yy), f"{lab:>2}", font=f, fill=col)
        d.line([(x + 120 + dx, yy + 22), (x + w - 40 + dx, yy + 22)], fill=col if col == RED else DIM, width=4)


# ----------------------------------------------------------------------------
# Rigged figure. Angles are degrees in screen space, measured from straight
# down; positive swings toward +x. `facing` mirrors the whole pose.
# ----------------------------------------------------------------------------

POSES = {
    "stand":    dict(lean=0, head=0, lh=-5, lk=0, rh=5, rk=0, ls=-10, le=0, rs=10, re=0, bob=0),
    "look_up":  dict(lean=-4, head=-18, lh=-5, lk=0, rh=5, rk=0, ls=-14, le=0, rs=14, re=0, bob=0),
    "reach":    dict(lean=6, head=6, lh=-4, lk=0, rh=8, rk=4, ls=-12, le=0, rs=95, re=-10, bob=0),
    "point":    dict(lean=2, head=0, lh=-5, lk=0, rh=5, rk=0, ls=-12, le=0, rs=110, re=0, bob=0),
    "ears":     dict(lean=0, head=0, lh=-6, lk=0, rh=6, rk=0, ls=-150, le=-40, rs=150, re=40, bob=4),
    "flinch":   dict(lean=-10, head=-10, lh=-12, lk=10, rh=10, rk=6, ls=-60, le=-80, rs=50, re=90, bob=8),
    "hunch":    dict(lean=8, head=14, lh=-4, lk=4, rh=4, rk=4, ls=-6, le=10, rs=6, re=-10, bob=6),
    "read":     dict(lean=0, head=10, lh=-5, lk=0, rh=5, rk=0, ls=-40, le=-100, rs=40, re=100, bob=0),
    "lean_in":  dict(lean=12, head=8, lh=-2, lk=0, rh=10, rk=6, ls=-6, le=0, rs=16, re=0, bob=0),
    "step_out": dict(lean=8, head=4, lh=-10, lk=4, rh=26, rk=14, ls=-16, le=0, rs=18, re=0, bob=-2),
    "carry":    dict(lean=2, head=0, lh=-5, lk=0, rh=5, rk=0, ls=60, le=60, rs=70, re=60, bob=0),
}


def blend(p, q, k):
    k = min(1.0, max(0.0, k))
    return {key: p[key] + (q[key] - p[key]) * k for key in p}


def walk_pose(phase, speed=1.0):
    s = math.sin(phase)
    c = math.cos(phase)
    amp = 24 * speed
    return dict(lean=4 * speed, head=0,
                lh=amp * s, lk=max(0, 30 * speed * -c),
                rh=-amp * s, rk=max(0, 30 * speed * c),
                ls=-amp * 0.9 * s, le=12, rs=amp * 0.9 * s, re=12,
                bob=-abs(c) * 8 * speed + 4 * speed)


def breathe(pose, t, amt=1.0):
    p = dict(pose)
    p["bob"] += math.sin(t * 2.2) * 2.5 * amt
    p["ls"] += math.sin(t * 2.2) * 2 * amt
    p["rs"] -= math.sin(t * 2.2) * 2 * amt
    return p


def _pt(origin, ang, length, f):
    a = math.radians(ang) * f
    return origin[0] + math.sin(a) * length, origin[1] + math.cos(a) * length


def rig(d, x, y, s=1.0, pose=None, facing=1, fill=WHITE):
    p = pose or POSES["stand"]
    f = 1 if facing >= 0 else -1
    hip = (x, y - 172 * s + p["bob"] * s)
    neck = _pt(hip, 180 + p["lean"], 128 * s, f)
    head = _pt(neck, 180 + p["lean"] + p["head"], 54 * s, f)
    lw = max(4, int(26 * s))
    for side in ("l", "r"):
        knee = _pt(hip, p[side + "h"], 88 * s, f)
        foot = _pt(knee, p[side + "h"] - p[side + "k"], 88 * s, f)
        v1.thick_line(d, [hip, knee, foot], lw, fill)
    v1.thick_line(d, [hip, neck], max(6, int(66 * s)), fill)
    sh = (neck[0], neck[1] + 14 * s)
    for side in ("l", "r"):
        elbow = _pt(sh, p[side + "s"], 74 * s, f)
        hand = _pt(elbow, p[side + "s"] + p[side + "e"], 70 * s, f)
        v1.thick_line(d, [sh, elbow, hand], max(4, int(22 * s)), fill)
    r = 36 * s
    d.ellipse([head[0] - r, head[1] - r, head[0] + r, head[1] + r], fill=fill)
    return {"head": head, "neck": neck, "hip": hip}


def walker(d, t, x0, x1, y, s, t0, t1, end_pose="stand", fill=WHITE, speed=1.0):
    """Walk from x0 to x1 between t0..t1, then settle into end_pose."""
    if t < t0:
        rig(d, x0, y, s, breathe(POSES["stand"], t), facing=1 if x1 >= x0 else -1, fill=fill)
        return x0
    if t < t1:
        k = (t - t0) / (t1 - t0)
        x = x0 + (x1 - x0) * k
        rig(d, x, y, s, walk_pose(t * 9.5 * speed, speed), facing=1 if x1 >= x0 else -1, fill=fill)
        return x
    k = ease((t - t1) / 0.35)
    pose = blend(walk_pose(t1 * 9.5 * speed, speed), POSES[end_pose], k)
    rig(d, x1, y, s, breathe(pose, t, k), facing=1 if x1 >= x0 else -1, fill=fill)
    return x1


def fade(col, k):
    k = min(1.0, max(0.0, k))
    return tuple(int(c * k) for c in col)


def appear(t, t0, dur=0.35):
    """0..1 entrance progress with overshoot scale."""
    k = (t - t0) / dur
    if k <= 0:
        return 0.0, 0.0
    if k >= 1:
        return 1.0, 1.0
    return ease(k), 1 + 0.18 * math.sin(k * math.pi) * (1 - k)


def scaled_box(cx, cy, w, h, sc):
    return [cx - w * sc / 2, cy - h * sc / 2, cx + w * sc / 2, cy + h * sc / 2]


def shake(t, amt=6, freq=40):
    return math.sin(t * freq) * amt, math.cos(t * freq * 1.3) * amt


# ----------------------------------------------------------------------------
# Shots. Signature: (d, img, t, dur, args, ctx); t = seconds into the shot.
# Every shot has continuous motion: figures walk / breathe / react, and
# elements enter with motion rather than appearing.
# ----------------------------------------------------------------------------


def shot_elevator_wide(d, img, t, dur, a, ctx):
    doors = a.get("doors", "closed")
    if doors == "open":
        of = ease(t / 1.2)
    elif doors == "opening":
        of = ease((t - 0.4) / 3.2)
    else:
        of = 0.0
    elevator_frame(d, 820, 560, 520, 640, of)
    flick = (int(t * 10) % 23) != 7
    k, sc = appear(t, 0.2)
    if k:
        display(d, 1230, 240, a.get("panel", "13"), on=flick)
    if a.get("you") == "inside":
        if a.get("x"):
            # steps toward the threshold, catches itself, steps back
            if t < 0.9:
                pose = blend(POSES["stand"], POSES["step_out"], ease(t / 0.9))
            elif t < 1.4:
                pose = POSES["step_out"]
            else:
                pose = blend(POSES["step_out"], POSES["flinch"], ease((t - 1.4) / 0.35))
            xoff = 18 * ease(t / 0.9) - 40 * ease((t - 1.4) / 0.4)
            rig(d, 820 + xoff, 960, 0.95, breathe(pose, t, 0.5), facing=1)
            if t > 1.2:
                kk = ease((t - 1.2) / 0.25)
                d.line([(560, 885), (560 + 520 * kk, 885)], fill=RED, width=8)
                big_x(d, 1345, 560, s=70 * appear(t, 1.2)[1], w=16)
        elif doors == "opening":
            pose = blend(POSES["stand"], POSES["lean_in"], ease((t - 2.0) / 1.2))
            rig(d, 820, 960, 0.95, breathe(pose, t), facing=1)
        else:
            pose = POSES["stand"] if t < 2.2 else blend(POSES["stand"], POSES["step_out"], ease((t - 2.2) / 0.6))
            rig(d, 820, 960, 0.95, breathe(pose, t), facing=1)


def shot_office_night(d, img, t, dur, a, ctx):
    d.rectangle([300, 230, 620, 520], outline=WHITE, width=10)
    d.line([(460, 230), (460, 520)], fill=WHITE, width=8)
    d.line([(300, 375), (620, 375)], fill=WHITE, width=8)
    my = 330 - 30 * ease(t / max(1, dur))
    d.ellipse([500, my - 35, 570, my + 35], fill=YELLOW)
    d.ellipse([522, my - 43, 592, my + 27], fill=BLACK)
    d.rounded_rectangle([860, 700, 1500, 730], radius=8, fill=WHITE)
    d.rectangle([900, 730, 924, 930], fill=WHITE)
    d.rectangle([1436, 730, 1460, 930], fill=WHITE)
    x = walker(d, t, 520, 1080, 930, 1.0, 0.0, 2.2, end_pose="read")
    lamp_on = t > 2.4
    if lamp_on:
        k = ease((t - 2.4) / 0.2) * (0.8 + 0.2 * math.sin(t * 2.0))
        d.polygon([(1340, 560), (1250, 700), (1460, 700)], fill=fade(YELLOW, 0.45 * k))
    v1.thick_line(d, [(1340, 700), (1340, 560), (1300, 540)], 10, WHITE)
    d.ellipse([1270, 520, 1330, 560], fill=YELLOW if lamp_on else DIM)
    cx, cy, r = 1560, 300, 80
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE, width=8)
    a1 = math.radians(t * 90)
    a2 = math.radians(330 + t * 8)
    v1.thick_line(d, [(cx, cy), (cx + math.sin(a1) * 58, cy - math.cos(a1) * 58)], 6, WHITE)
    v1.thick_line(d, [(cx, cy), (cx + math.sin(a2) * 40, cy - math.cos(a2) * 40)], 10, WHITE)


def shot_seven_rules(d, img, t, dur, a, ctx):
    f = mont(800, 70)
    step = max(0.22, (dur - 0.8) / 7)
    for i in range(7):
        k, sc = appear(t, 0.1 + i * step)
        if not k:
            continue
        cx, cy = 405 + i * 190, 520
        latest = i == min(6, int((t - 0.1) / step))
        d.rounded_rectangle(scaled_box(cx, cy, 150, 200, sc), radius=14, outline=fade(WHITE, k), width=6,
                            fill=WHITE if latest else None)
        s = str(i + 1)
        fs = mont(800, int(70 * sc))
        d.text((cx - d.textlength(s, font=fs) / 2, cy - 45 * sc), s, font=fs, fill=BLACK if latest else fade(WHITE, k))
    dotted(d, (330, 680), (1620, 680), color=GREY, upto=ease(t / max(0.5, dur - 0.4)), phase=t * 2)


def shot_rules_shuffled(d, img, t, dur, a, ctx):
    order = [3, 1, 6, 2, 7, 4, 5]
    f = mont(800, 70)
    rng = np.random.default_rng(3)
    for i, num in enumerate(order):
        # start in correct slot, then scatter to shuffled slot
        home_x = 330 + (num - 1) * 190
        dest_x = 330 + i * 190
        k = ease((t - 0.3 - i * 0.06) / 0.9)
        x = home_x + (dest_x - home_x) * k
        dy = float(rng.integers(-60, 60))
        ang0 = float(rng.uniform(-14, 14))
        y = 420 + dy * k + math.sin(t * 3 + i) * 4
        ang = ang0 * k + math.sin(t * 2 + i) * 1.5
        tile = Image.new("RGBA", (170, 220), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile)
        wrong = num != i + 1
        col = RED if wrong and t > 1.4 + i * 0.12 else WHITE
        td.rounded_rectangle([10, 10, 160, 210], radius=14, outline=col, width=6)
        s = str(num)
        td.text((85 - td.textlength(s, font=f) / 2, 65), s, font=f, fill=col)
        tile = tile.rotate(ang, resample=Image.BICUBIC, expand=True)
        img.paste(tile, (int(x) - 10, int(y) - 10), tile)


def shot_rule_card(d, img, t, dur, a, ctx):
    rule = ctx["rule"]
    name = ctx["rule_name"]
    f = mont(800, 150)
    word = "RULE"
    tw = d.textlength(word, font=f)
    box = 170
    total = tw + 40 + box
    x0 = W / 2 - total / 2
    y0 = 300
    k = ease(t / 0.35)
    d.text((x0 - 60 * (1 - k), y0), word, font=f, fill=fade(WHITE, k))
    bk, bsc = appear(t, 0.25)
    if bk:
        bx = x0 + tw + 40
        d.rounded_rectangle(scaled_box(bx + box / 2, y0 + 18 + box / 2, box, box, bsc), radius=16, fill=WHITE)
        fn = mont(800, int(130 * bsc))
        s = str(rule)
        d.text((bx + box / 2 - d.textlength(s, font=fn) / 2, y0 + 18 + box / 2 - 88 * bsc), s, font=fn, fill=BLACK)
    n = int(len(name) * ease((t - 0.5) / 1.0))
    f2 = mont(700, 54)
    spaced_text(d, (W / 2, 560), name[:n], f2, WHITE, 6, anchor="m")
    if n < len(name) and int(t * 6) % 2 == 0:
        cw = spaced_width(d, name[:n], f2, 6)
        full = spaced_width(d, name, f2, 6)
        d.rectangle([W / 2 - full / 2 + cw + 6, 566, W / 2 - full / 2 + cw + 30, 616], fill=WHITE)
    full_w = spaced_width(d, name, f2, 6)
    ul = full_w * ease((t - 0.5) / 1.0)
    d.rectangle([W / 2 - full_w / 2, 640, W / 2 - full_w / 2 + ul, 648], fill=RED)
    for i in range(7):
        pk, psc = appear(t, 0.9 + i * 0.05, 0.25)
        if not pk:
            continue
        bx = W / 2 - 7 * 52 / 2 + i * 52 + 19
        on = i + 1 == rule
        done = i + 1 < rule
        d.rounded_rectangle(scaled_box(bx, 719, 38, 38, psc), radius=6,
                            outline=WHITE if (on or done) else DIM, width=3, fill=WHITE if on else None)
        fs = mont(700, 20)
        ss = str(i + 1)
        d.text((bx - d.textlength(ss, font=fs) / 2, 707), ss, font=fs, fill=BLACK if on else (WHITE if done else DIM))


def shot_directory(d, img, t, dur, a, ctx):
    n = a.get("floors", 12)
    reveal = ease((t - 0.6) / 2.0)
    floor_board(d, 1060, 150 if n == 13 else 175, n, reveal=reveal, red_top=(n == 13 and t > 1.0))
    if n == 13:
        rig(d, 640, 930, 1.25, breathe(blend(POSES["look_up"], POSES["flinch"], ease((t - 1.0) / 0.3)), t), facing=1)
        return
    if t <= 0.9:
        walker(d, t, 300, 640, 930, 1.25, 0.0, 0.9, end_pose="look_up")
        return
    # head nods down the list as each floor is counted
    rows = n * reveal
    pose = blend(walk_pose(0.9 * 9.5), POSES["look_up"], ease((t - 0.9) / 0.35))
    pose["head"] = -18 + (rows / n) * 30 + (math.sin(t * 9) * 3 if reveal < 1 else 0)
    rig(d, 640, 930, 1.25, breathe(pose, t), facing=1)
    if reveal >= 1:
        k, sc = appear(t, 2.6)
        if k:
            fb = mont(800, int(70 * sc))
            d.text((740, 330), str(n), font=fb, fill=YELLOW)


def shot_card_vs_panel(d, img, t, dur, a, ctx):
    k = ease(t / 0.6)
    card(d, 380 - 500 * (1 - k), 380, "12")
    k2 = ease((t - 0.3) / 0.6)
    display(d, 1260 + 600 * (1 - k2), 410, "13", w=300, h=170, on=(int(t * 10) % 19 != 7))
    pk, sc = appear(t, 0.9)
    if pk:
        sx, sy = shake(t, 5 if t < 1.6 else 2)
        fs = mont(800, int(130 * sc))
        on = int(t * 3) % 2 == 0
        d.text((W / 2 - d.textlength("≠", font=fs) / 2 + sx, 380 + sy), "≠", font=fs, fill=RED if on else WHITE)


def hallway(d, x0, y0, w, h, warm=False, light=True):
    vx, vy = x0 + w / 2, y0 + h * 0.42
    base = fade(YELLOW, 0.22) if warm else BLACK
    d.rectangle([x0, y0, x0 + w, y0 + h], fill=base)
    line = fade(YELLOW, 0.6) if warm else DIM
    for k in range(9):
        d.line([(x0 + k * w / 8, y0 + h), (vx, vy)], fill=line, width=3)
    d.line([(x0, y0 + 60), (vx, vy)], fill=line, width=3)
    d.line([(x0 + w, y0 + 60), (vx, vy)], fill=line, width=3)
    if light:
        d.ellipse([vx - 60, y0 - 10, vx + 60, y0 + 30], fill=YELLOW if warm else DIM)
    d.rectangle([x0, y0, x0 + w, y0 + h], outline=WHITE, width=10)
    return vx, vy


def shot_hallway_compare(d, img, t, dur, a, ctx):
    for i, lab in enumerate(["YOUR HALLWAY", "THIS HALLWAY"]):
        k, sc = appear(t, i * 0.35)
        if not k:
            continue
        x0 = 210 + i * 780
        cx = x0 + 360
        d.rounded_rectangle(scaled_box(cx, 460, 720, 520, sc), radius=12, outline=WHITE, width=6)
        vx, vy = cx, 440
        for kk in range(7):
            d.line([(x0 + kk * 120, 720), (vx, vy)], fill=DIM, width=3)
        d.line([(x0, 260), (vx, vy)], fill=DIM, width=3)
        d.line([(x0 + 720, 260), (vx, vy)], fill=DIM, width=3)
        d.rectangle([vx - 24, vy - 50, vx + 24, vy + 6], outline=WHITE, width=4)
        if i == 0:
            d.rounded_rectangle([x0 + 560, 470, x0 + 600, 580], radius=18, fill=RED)
        # a small figure walks toward camera in each; the right one stops and turns its head
        walk_t = min(t, 2.6) if i == 0 else min(t, 2.0)
        depth = ease(walk_t / 2.6)
        fs_ = 0.18 + 0.32 * depth
        fy = vy + 10 + 250 * depth
        pose = walk_pose(t * 8, 0.6) if (i == 0 and t < 2.6) or (i == 1 and t < 2.0) else POSES["stand"]
        if i == 1 and t > 2.0:
            pose = dict(POSES["stand"])
            pose["head"] = 22 * ease((t - 2.0) / 0.4)
        rig(d, cx - 60, fy, fs_, pose, facing=1, fill=WHITE if i == 0 else GREY)
        spaced_text(d, (cx, 750), lab, mont(700, 28), WHITE if i == 0 else GREY, 5, anchor="m")
        if i == 1 and t > dur * 0.55:
            d.rounded_rectangle([x0 + 548, 460, x0 + 612, 592], radius=18, outline=GREY, width=3)
            big_x(d, x0 + 580, 526, s=26 * appear(t, dur * 0.55)[1], w=6)


def shot_button_wire(d, img, t, dur, a, ctx):
    cx, cy = 560, 540
    k, sc = appear(t, 0.0)
    r = 150 * sc
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE, width=12)
    f = mont(800, int(90 * sc))
    d.text((cx - d.textlength(">|<", font=f) / 2, cy - 60 * sc), ">|<", font=f, fill=WHITE)
    end = ease((t - 0.3) / 1.6)
    n = int(((1500 - cx - 160) / 26) * end)
    pulse = (t * 14) % 40
    for i in range(n):
        x = cx + 160 + i * 26
        fd = max(0.0, 1 - i / 40)
        near = abs(i - pulse) < 1.5
        col = fade(YELLOW, fd) if near else fade(WHITE, fd)
        rr = 8 if near else 5
        d.ellipse([x - rr, cy - rr, x + rr, cy + rr], fill=col)
    qk, qsc = appear(t, 1.8)
    if qk:
        f2 = mont(800, int(120 * qsc))
        d.text((1520, 460 + math.sin(t * 3) * 8), "?", font=f2, fill=GREY)


def shot_button_press(d, img, t, dur, a, ctx):
    cx, cy = 960, 520
    tp = min(1.4, dur * 0.5)
    hit = t > tp
    sx, sy = shake(t, 7) if tp < t < tp + 0.25 else (0, 0)
    cx += sx
    cy += sy
    if hit:
        for ring in range(3):
            rt = t - tp - ring * 0.25
            if rt > 0:
                r = 150 + 220 * ease(rt / 0.9)
                d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=fade(RED, max(0, 1 - rt / 0.9)), width=8)
    press = 0.9 if tp < t < tp + 0.3 else 1.0
    r = 150 * press
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=RED if hit else WHITE, width=12)
    f = mont(800, int(90 * press))
    d.text((cx - d.textlength(">|<", font=f) / 2, cy - 60 * press), ">|<", font=f, fill=RED if hit else WHITE)
    p = ease(t / tp)
    back = ease((t - tp - 0.4) / 0.5) * 120
    fx, fy = cx + 40 + (1 - p) * 520 + back, cy + 60 + (1 - p) * 420 + back
    v1.thick_line(d, [(fx + 260, fy + 300), (fx + 60, fy + 70)], 70, WHITE)
    v1.thick_line(d, [(fx + 60, fy + 70), (fx, fy)], 34, WHITE)


def shot_building_floors(d, img, t, dur, a, ctx):
    x0, w = 760, 400
    fh = 52
    for i in range(13):
        y = 900 - (i + 1) * fh
        k = ease((t - i * 0.09) / 0.2)
        if k <= 0:
            continue
        is13 = i == 12
        col = RED if is13 else WHITE
        yy = y - 30 * (1 - k)
        d.rectangle([x0, yy, x0 + w, yy + fh - 10], outline=fade(col, k), width=4,
                    fill=(RED if is13 and k >= 1 and (int(t * 4) % 2 == 0) else None))
        if not is13:
            for kk in range(4):
                wx = x0 + 40 + kk * 90
                on = ((i * 7 + kk) % 5 == 0) ^ (int(t * 1.5 + i + kk) % 7 == 0)
                d.rectangle([wx, yy + 12, wx + 40, yy + 30], fill=fade(YELLOW, k) if on else FAINT)
    d.rectangle([x0 - 30, 900, x0 + w + 30, 912], fill=WHITE)
    # a hurried figure runs past; floor 13 follows it with a dotted stare
    if t > 1.2:
        rx = 1250 + (t - 1.2) * 320
        rig(d, rx, 900, 0.8, walk_pose(t * 15, 1.4), facing=1)
        dotted(d, (x0 + w + 10, 900 - 13 * fh + 20), (rx, 650), color=RED,
               upto=ease((t - 1.4) / 0.6), phase=t * 3)


def shot_stat(d, img, t, dur, a, ctx):
    val = a.get("value", 100)
    red = a.get("red", False)
    p = ease(t / 1.0)
    shown = int(round(val * p)) if val > 0 else int(round(100 * (1 - p)))
    f = mont(800, 230)
    s = f"{shown}%"
    sx, sy = shake(t, 4) if red and t > 1.0 else (0, 0)
    d.text((W / 2 - d.textlength(s, font=f) / 2 + sx, 230 + sy), s, font=f, fill=RED if red else WHITE)
    spaced_text(d, (W / 2, 520), a.get("label", ""), mont(700, 34), GREY, 7, anchor="m")
    for i in range(10):
        x = W / 2 - 10 * 90 / 2 + i * 90 + 45
        k, sc = appear(t, 0.15 + i * 0.08, 0.3)
        if not k:
            continue
        if red:
            dim_k = ease((t - 1.0 - i * 0.08) / 0.3)
            col = tuple(int(WHITE[c] + (DIM[c] - WHITE[c]) * dim_k) for c in range(3))
        else:
            col = WHITE
        pose = breathe(POSES["stand"], t + i, 0.6)
        rig(d, x, 860 + (1 - k) * 30, 0.42 * sc, pose, facing=1, fill=col)


def shot_org_chart(d, img, t, dur, a, ctx):
    f = mont(700, 28)

    def box(x, y, label, col=WHITE, w=300, h=90, sc=1.0):
        d.rounded_rectangle(scaled_box(x, y + h / 2, w, h, sc), radius=10, outline=col, width=5)
        spaced_text(d, (x, y + 28), label, f, col, 4, anchor="m")

    k, sc = appear(t, 0.0)
    box(W / 2, 200, "FLOOR 13", col=fade(RED, 0.6 + 0.4 * math.sin(t * 4)), w=360, sc=sc * (1 + 0.02 * math.sin(t * 4)))
    lk = ease((t - 0.3) / 0.4)
    d.line([(W / 2, 290), (W / 2, 290 + 90 * lk)], fill=GREY, width=4)
    if lk >= 1:
        hk = ease((t - 0.7) / 0.4)
        d.line([(W / 2 - 520 * hk, 380), (W / 2 + 520 * hk, 380)], fill=GREY, width=4)
    for i, x in enumerate([W / 2 - 520, W / 2, W / 2 + 520]):
        vk = ease((t - 1.1) / 0.3)
        if vk <= 0:
            continue
        d.line([(x, 380), (x, 380 + 60 * vk)], fill=GREY, width=4)
        if i < 2:
            box(x, 440, "OCCUPIED", col=DIM)
            rig(d, x, 760, 0.45, breathe(POSES["stand"], t + i * 2), facing=1, fill=DIM)
    x = W / 2 + 520
    if t > 1.3:
        nk, nsc = appear(t, 1.3)
        box(x, 440, "NEW HIRE", col=WHITE, sc=nsc)
        # you walk in from the right edge into the empty slot
        walker(d, t, 1900, x, 760, 0.45, 1.3, 2.6, end_pose="stand")
        if t > 2.7 and int(t * 3) % 3 != 0:
            spaced_text(d, (x, 790), "YOU", mont(800, 30), RED, 6, anchor="m")
        if t > 2.7:
            dotted(d, (W / 2, 290), (x, 560), color=RED, phase=t * 2, upto=ease((t - 2.7) / 0.6))


def shot_counter(d, img, t, dur, a, ctx):
    n = 1 + int(t * 1.4)
    frac = (t * 1.4) % 1
    f = mont(800, 260)
    s = f"{min(n, 90):02d}"
    slide = 40 * (1 - ease(frac / 0.25))
    d.text((W / 2 - d.textlength(s, font=f) / 2, 260 - slide), s, font=f, fill=fade(WHITE, ease(frac / 0.25)))
    cx, cy, r = W / 2, 430, 260
    prog = min(t * 1.4, 90) / 90
    d.arc([cx - r, cy - r, cx + r, cy + r], start=-90, end=-90 + 360 * prog, fill=YELLOW, width=10)
    d.arc([cx - r, cy - r, cx + r, cy + r], start=-90 + 360 * prog, end=270, fill=FAINT, width=10)
    spaced_text(d, (W / 2, 750), "OF 90", mont(700, 34), GREY, 8, anchor="m")
    # you, counting out loud: speech arcs pulse on every number
    rig(d, 360, 900, 0.9, breathe(POSES["stand"], t), facing=1)
    pulse = 1 - frac
    for j in range(3):
        rr = 40 + j * 34
        d.arc([440 - rr, 560 - rr, 440 + rr, 560 + rr], start=-40, end=40, fill=fade(WHITE, pulse * (1 - j * 0.25)), width=8)


def shot_counter_loop(d, img, t, dur, a, ctx):
    seq = ["98", "99", "100", "01"]
    i = min(3, int(t / 0.55))
    local = t - i * 0.55
    f = mont(800, 260)
    s = seq[i]
    col = RED if s in ("100", "01") else WHITE
    slide = 60 * (1 - ease(local / 0.2))
    d.text((W / 2 - d.textlength(s, font=f) / 2, 260 + slide), s, font=f, fill=fade(col, ease(local / 0.2)))
    cx, cy, r = W / 2, 430, 280
    spin = (t * 120) % 360
    d.arc([cx - r, cy - r, cx + r, cy + r], start=-80 + spin, end=250 + spin, fill=GREY, width=8)
    ang = math.radians(250 + spin)
    ax, ay = cx + r * math.cos(ang), cy + r * math.sin(ang)
    d.ellipse([ax - 14, ay - 14, ax + 14, ay + 14], fill=GREY)


def shot_number_row(d, img, t, dur, a, ctx):
    nums = list(range(84, 97))
    f = mont(700, 64)
    for i, n in enumerate(nums):
        x = 170 + i * 122
        k, sc = appear(t, i * 0.07, 0.25)
        if not k:
            continue
        if n == 90:
            sx, sy = shake(t, 5)
            d.rounded_rectangle([x - 6 + sx, 470 + sy, x + 100 + sx, 570 + sy], radius=8, outline=RED, width=5)
            if int(t * 3) % 2 == 0:
                d.text((x + 6 + sx, 480 + sy), "??", font=f, fill=RED)
            continue
        fs = mont(700, int(64 * sc))
        d.text((x, 480 - (1 - k) * 30), str(n), font=fs, fill=fade(WHITE, k))


def shot_eye(d, img, t, dur, a, ctx):
    cx, cy = W / 2, 500
    open_ = ease(t / 0.8)
    blink_t = t - 1.6
    if 0 < blink_t < 0.18:
        open_ *= abs(blink_t - 0.09) / 0.09
    w, h = 520, 230 * open_
    d.ellipse([cx - w, cy - h - 4, cx + w, cy + h + 4], fill=WHITE)
    if open_ > 0.3:
        # pupil darts, then locks onto the viewer
        if t < 1.2:
            px = cx + 180 * math.sin(t * 7) * (1 - ease((t - 0.8) / 0.4))
        else:
            px = cx
        pr = 120 * open_
        d.ellipse([px - pr, cy - pr, px + pr, cy + pr], fill=BLACK)
        rr = 52 * open_ * (1 + 0.08 * math.sin(t * 6))
        d.ellipse([px - rr, cy - rr, px + rr, cy + rr], fill=RED)


def shot_face_away(d, img, t, dur, a, ctx):
    cycle = ["4", "F", "??", "13", "7", "Ø"]
    sym = cycle[int(t * 2.4) % len(cycle)]
    display(d, 1250, 200, sym, color=YELLOW if sym in ("4", "7") else RED)
    # starts facing the panel, then turns away and hunches
    turn = ease((t - 0.5) / 0.3)
    facing = 1 if turn < 0.5 else -1
    pose = POSES["look_up"] if turn < 0.5 else blend(POSES["stand"], POSES["hunch"], ease((t - 0.8) / 0.6))
    squash = 1 - 0.12 * math.sin(turn * math.pi)
    tremble = 3 * math.sin(t * 31) if t > 1.4 else 0
    rig(d, 760 + tremble, 960, 1.35 * squash, breathe(pose, t, 1.5), facing=facing)
    if t > 0.8:
        dotted(d, (790, 520), (1240, 300), color=DIM, phase=t * 2, upto=ease((t - 0.8) / 0.5))
        big_x(d, 1020, 410, s=55 * appear(t, 1.1)[1], w=14)
        spaced_text(d, (1365, 380), "PRESS NOTHING", mont(700, 26), RED, 5, anchor="m")


def shot_safe_hallway(d, img, t, dur, a, ctx):
    hallway(d, 420, 180, 900, 720, warm=True)
    d.rounded_rectangle([1130, 560, 1190, 720], radius=26, fill=RED)
    d.rectangle([1148, 530, 1172, 560], fill=WHITE)
    # elevator doors slide open over the hallway, then you walk out
    of = ease(t / 0.9)
    gap = 450 * of
    d.rectangle([420, 180, 870 - gap, 900], fill=DIM)
    d.rectangle([870 + gap, 180, 1320, 900], fill=DIM)
    d.rectangle([420, 180, 1320, 900], outline=WHITE, width=10)
    if t > 0.9:
        depth = ease((t - 0.9) / 1.8)
        rig(d, 870, 1000 - 220 * depth, 1.1 - 0.6 * depth, walk_pose(t * 9, 0.7), facing=1)
    ck, csc = appear(t, 1.4)
    if ck:
        check(d, 1580, 480, s=90 * csc)
        spaced_text(d, (1580, 620), "EXIT HERE", mont(700, 30), GREEN, 6, anchor="m")


def shot_missing_extinguisher(d, img, t, dur, a, ctx):
    on = not (1.0 < t % 2.3 < 1.12) and not (1.25 < t % 2.3 < 1.3)
    hallway(d, 420, 180, 900, 720, warm=False, light=on)
    pulse = 0.6 + 0.4 * math.sin(t * 5)
    for k in range(10):
        ang = k / 10 * 2 * math.pi + t * 0.6
        x = 1160 + 32 * math.cos(ang)
        y = 640 + 80 * math.sin(ang)
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=fade(GREY, pulse))
    # you stay inside: step back from the doorway
    back = ease((t - 0.6) / 0.6)
    rig(d, 870, 960 + 30 * back, 1.1 + 0.1 * back, breathe(blend(POSES["stand"], POSES["flinch"], back), t), facing=1)
    xk, xsc = appear(t, 1.0)
    if xk:
        big_x(d, 1580, 500, s=80 * xsc, w=18)


def shot_desk_reading(d, img, t, dur, a, ctx):
    d.rounded_rectangle([560, 700, 1360, 730], radius=8, fill=WHITE)
    d.rectangle([600, 730, 624, 930], fill=WHITE)
    d.rectangle([1296, 730, 1320, 930], fill=WHITE)
    rig(d, 960, 930, 1.0, breathe(POSES["read"], t), facing=1)
    tremble = 0 if t < 1.0 else 3 * math.sin(t * 38)
    px, py = 900 + tremble, 470 + tremble * 0.5
    d.rectangle([px, py, px + 200, py + 250], fill=WHITE)
    spaced_text(d, (px + 100, py + 30), "FILE 001", mont(800, 26), BLACK, 3, anchor="m")
    for k in range(6):
        d.line([(px + 28, py + 90 + k * 24), (px + 172, py + 90 + k * 24)], fill=GREY, width=5)
    glow = (0.8 + 0.2 * math.sin(t * 9)) if t > 1.2 else 1.0
    if 1.6 < t % 2.0 < 1.7:
        glow = 0.2
    d.polygon([(760, 520), (650, 700), (870, 700)], fill=fade(YELLOW, 0.4 * glow))
    d.ellipse([730, 500, 790, 540], fill=fade(YELLOW, glow))
    v1.thick_line(d, [(760, 700), (760, 540)], 10, WHITE)


def shot_card_rewrite(d, img, t, dur, a, ctx):
    x, y, w, h = 640, 380, 640, 320
    card(d, x, y, "12", w=w, h=h)
    sk = ease((t - 0.3) / 0.5)
    if sk > 0:
        v1.thick_line(d, [(x + 50, y + 95), (x + 50 + (w - 100) * sk, y + 95)], 12, RED)
    if t > 0.9:
        f = mont(800, 120)
        rk = ease((t - 0.9) / 0.7)
        tile = Image.new("RGBA", (260, 160), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((10, 0), "13", font=f, fill=RED)
        tile = tile.crop((0, 0, max(1, int(260 * rk)), 160))
        img.paste(tile, (1320, 470), tile)
        # pen tip rides along the writing
        tipx = 1330 + 240 * rk
        v1.thick_line(d, [(tipx + 140, 760), (tipx, 590)], 16, WHITE)


def shot_wallet(d, img, t, dur, a, ctx):
    fk = ease((t - 1.4) / 0.6)
    # right half (holds the card)
    d.rounded_rectangle([960, 420, 1360, 860], radius=40, outline=WHITE, width=12)
    y = 120 + (430 - 120) * ease(t / 1.0)
    card(d, 1000, y, "13", w=300, h=190, num_color=RED)
    d.rectangle([980, 640, 1340, 850], fill=BLACK)
    d.rounded_rectangle([980, 640, 1340, 850], radius=12, outline=WHITE, width=8)
    # left flap folds over the hinge at x=960
    span = 400 * math.cos(fk * math.pi)
    if span > 0:
        d.rounded_rectangle([960 - span, 420, 960, 860], radius=40, outline=WHITE, width=12)
    elif span < 0:
        d.rounded_rectangle([960, 420, 960 - span, 860], radius=40, outline=WHITE, width=12, fill=BLACK)
    d.line([(960, 420), (960, 860)], fill=WHITE, width=8)


def shot_end_card(d, img, t, dur, a, ctx):
    f = mont(800, 96)
    text = "END OF FILE"
    n = int(len(text) * ease(t / 0.8)) if not a.get("sub") else len(text)
    spaced_text(d, (W / 2 - spaced_width(d, text, f, 12) / 2, 420), text[:n], f, WHITE, 12)
    if a.get("sub"):
        k = ease(t / 0.6)
        spaced_text(d, (W / 2, 560), "FURTHER TRAINING MATERIALS ARE AVAILABLE", mont(600, 30), fade(GREY, k), 6, anchor="m")


SHOTS = {k[5:]: v for k, v in globals().items() if k.startswith("shot_")}


# ----------------------------------------------------------------------------
# Compositing
# ----------------------------------------------------------------------------


def timecode(t):
    fr = int((t % 1) * FPS)
    s = int(t)
    return f"00:{s // 60:02d}:{s % 60:02d}:{fr:02d}"


def draw_hud(d, ep, t, rule):
    f = mont(600, 20)
    spaced_text(d, (60, 44), f"{ep['brand']}  //  FILE {ep['file_number']}", f, GREY, 4)
    spaced_text(d, (W - 60, 44), timecode(t), f, GREY, 3, anchor="r")
    if rule:
        fs = mont(700, 14)
        for i in range(7):
            bx = W / 2 - 7 * 30 / 2 + i * 30
            on = i + 1 == rule
            done = i + 1 < rule
            d.rectangle([bx, 42, bx + 22, 64], outline=WHITE if (on or done) else DIM, width=2,
                        fill=WHITE if on else None)
            ss = str(i + 1)
            d.text((bx + 11 - d.textlength(ss, font=fs) / 2, 45), ss, font=fs,
                   fill=BLACK if on else (GREY if done else DIM))


def draw_caption(d, text):
    f = mont(700, 40)
    text = text.upper()
    words = text.split()
    lines, cur = [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if spaced_width(d, trial, f, 2) <= 1400:
            cur = trial
        else:
            lines.append(cur)
            cur = w_
    lines.append(cur)
    y = 1036 - 56 * len(lines)
    for ln in lines:
        spaced_text(d, (W / 2, y), ln, f, WHITE, 2, anchor="m")
        y += 56


def glitch(img, seed):
    rng = np.random.default_rng(seed)
    a = np.asarray(img).copy()
    shift = int(rng.integers(10, 26))
    a[:, :, 0] = np.roll(a[:, :, 0], shift, axis=1)
    a[:, :, 2] = np.roll(a[:, :, 2], -shift, axis=1)
    for _ in range(int(rng.integers(4, 9))):
        y0 = int(rng.integers(0, H - 40))
        h = int(rng.integers(6, 60))
        a[y0:y0 + h] = np.roll(a[y0:y0 + h], int(rng.integers(-90, 90)), axis=1)
    a[::3] = (a[::3] * 0.55).astype(np.uint8)
    return Image.fromarray(a)


def add_glow(img):
    small = img.resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(5))
    big = small.resize((W, H), Image.BILINEAR)
    big = ImageEnhance.Brightness(big).enhance(0.85)
    return ImageChops.add(img, big)


def red_takeover(img):
    gray = ImageOps.grayscale(img)
    return ImageOps.colorize(gray, black=(0, 0, 0), white=(255, 52, 44))


class Plan:
    def __init__(self, ep, timeline):
        self.ep = ep
        self.shots = []  # dicts: start, end, line, seg
        lead = 0.25
        flat = []
        for si, seg in enumerate(timeline["segments"]):
            for li, ln in enumerate(seg["lines"]):
                flat.append((si, li, ln))
        for k, (si, li, ln) in enumerate(flat):
            start = max(0.0, ln["start"] - lead)
            if k + 1 < len(flat):
                end = max(start + 0.5, flat[k + 1][2]["start"] - lead)
            else:
                end = timeline["total"]
            src = ep["segments"][si]["lines"][li]
            self.shots.append({"start": start, "end": end, "voice_end": ln["end"], "text": ln["text"],
                               "shot": src["shot"], "args": src.get("args", {}), "glitch": src.get("glitch", False),
                               "voice_start": ln["start"], "seg": ep["segments"][si],
                               "seg_start": timeline["segments"][si]["start"]})
        # black hold before any silence_before segment
        self.blackouts = []
        for si, seg in enumerate(ep["segments"]):
            if seg.get("silence_before"):
                st = timeline["segments"][si]["start"]
                self.blackouts.append((st - 1.6, st - 0.25))
        self.total = timeline["total"]


PLAN = None


def init_worker(plan):
    global PLAN
    PLAN = plan


def render_frame(i, fps, scale):
    plan = PLAN
    t = i / fps
    canvas = Image.new("RGB", (W, H), BLACK)
    if t < plan.shots[0]["start"] or any(a <= t < b for a, b in plan.blackouts):
        out = canvas
    else:
        sh = next((s for s in reversed(plan.shots) if s["start"] <= t), plan.shots[0])
        seg = sh["seg"]
        ctx = {"rule": seg.get("rule"), "rule_name": seg.get("rule_name", "")}
        tl = t - sh["start"]
        dur = sh["end"] - sh["start"]
        layer = Image.new("RGB", (W, H), BLACK)
        ld = ImageDraw.Draw(layer)
        SHOTS[sh["shot"]](ld, layer, tl, dur, sh["args"], ctx)
        for k in range(22):
            px = (k * 397 + t * (14 + k % 5 * 6)) % W
            py = (k * 233 + math.sin(t * 0.7 + k) * 40 + t * (6 + k % 3 * 4)) % H
            c = 40 + (k * 37) % 50
            ld.ellipse([px - 2, py - 2, px + 2, py + 2], fill=(c, c, c))
        # push-in
        z = 1.0 + 0.075 * ease(tl / max(dur, 0.5))
        cw, ch = W / z, H / z
        box = (int((W - cw) / 2), int((H - ch) / 2), int((W + cw) / 2), int((H + ch) / 2))
        # handheld drift: never a locked-off frame
        dx = 7 * math.sin(t * 0.61) + 3 * math.sin(t * 1.7)
        dy = 5 * math.sin(t * 0.47 + 1.0) + 2 * math.sin(t * 1.3)
        if sh["shot"] in ("rule_card", "end_card"):
            full = layer.crop(box).resize((W, H), Image.BILINEAR)
            layer = Image.new("RGB", (W, H), BLACK)
            layer.paste(full, (int(dx), int(dy)))
        else:
            fit = 0.86
            small = layer.crop(box).resize((int(W * fit), int(H * fit)), Image.BILINEAR)
            layer = Image.new("RGB", (W, H), BLACK)
            layer.paste(small, (int(W / 2 - W * fit / 2 + dx), int(380 - 380 * fit + dy)))
        layer = add_glow(layer)
        if sh["args"].get("red_takeover"):
            layer = red_takeover(layer)
        out = layer
        d = ImageDraw.Draw(out)
        draw_hud(d, plan.ep, t, ctx["rule"])
        if sh["shot"] not in ("rule_card", "end_card"):
            draw_caption(d, sh["text"])
        # glitch hits: on the cut, and once more mid-line
        if sh["glitch"]:
            mid = sh["voice_start"] + (sh["voice_end"] - sh["voice_start"]) * 0.55
            if tl < 0.17 or abs(t - mid) < 0.09:
                out = glitch(out, i)
    if scale != 1.0:
        out = out.resize((int(W * scale), int(H * scale)), Image.BILINEAR)
    return out.tobytes()


def _render(args):
    i, fps, scale = args
    return render_frame(i, fps, scale)


def render_video(plan, out_path, fps, scale, workers):
    w, h = int(W * scale), int(H * scale)
    n = int(math.ceil(plan.total * fps))
    vf = "noise=alls=7:allf=t+u,vignette=PI/5,format=yuv420p"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
           "-r", str(fps), "-i", "-", "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "21",
           "-maxrate", "9M", "-bufsize", "18M", "-r", str(fps), out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(workers, initializer=init_worker, initargs=(plan,)) as pool:
        for k, buf in enumerate(pool.imap(_render, ((i, fps, scale) for i in range(n)), chunksize=8)):
            proc.stdin.write(buf)
            if k % (fps * 20) == 0:
                print(f"  render {100 * k // n:3d}%", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")


def render_thumbnail(ep, path):
    img = Image.new("RGB", (W, H), BLACK)
    d = ImageDraw.Draw(img)
    elevator_frame(d, 620, 470, 560, 680, 1.0)
    person(d, 620, 890, s=1.0)
    display(d, 1040, 170, "13", w=300, h=170)
    big_x(d, 1190, 520, s=90, w=22)
    img = add_glow(img)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 830, W, H], fill=RED)
    f = mont(800, 150)
    t = ep["thumbnail_command"]
    spaced_text(d, (W / 2, 850), t, f, WHITE, 6, anchor="m")
    spaced_text(d, (W - 80, 60), f"FILE {ep['file_number']}", mont(700, 44), GREY, 8, anchor="r")
    img.resize((1280, 720), Image.LANCZOS).save(path, quality=92)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode_json")
    ap.add_argument("--voice", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    args = ap.parse_args()

    with open(args.episode_json) as f:
        ep = json.load(f)
    os.makedirs(args.out, exist_ok=True)
    lines_dir = os.path.join(args.out, "lines")
    os.makedirs(lines_dir, exist_ok=True)

    # narration + timing via the v1 pipeline (text-only view of the episode)
    ep_txt = copy.deepcopy(ep)
    for seg in ep_txt["segments"]:
        seg["lines"] = [ln["text"] for ln in seg["lines"]]
        seg.setdefault("scene", seg["id"])
    print("1/5 narration…", flush=True)
    sr, narration, timeline, total = v1.build_timeline(ep_txt, args.voice, args.voice + ".json", lines_dir)
    tl = {"total": total, "segments": timeline}
    with open(os.path.join(args.out, "timeline.json"), "w") as f:
        json.dump(tl, f, indent=2)
    print(f"    runtime {total:.1f}s", flush=True)

    print("2/5 tape processing…", flush=True)
    raw, fx = os.path.join(args.out, "narration_raw.wav"), os.path.join(args.out, "narration_fx.wav")
    v1.write_wav(raw, sr, narration)
    v1.tape_process(raw, fx)
    _, narr = v1.read_wav(fx)
    if len(narr) != len(narration):
        idx = np.linspace(0, len(narr) - 1, len(narration))
        narr = np.interp(idx, np.arange(len(narr)), narr).astype(np.float32)

    print("3/5 sound bed…", flush=True)
    bed = v1.design_bed(sr, total, timeline)
    n = min(len(bed), len(narr))
    mix = narr[:n] + bed[:n]
    # glitch hits get a short burst of static
    plan = Plan(ep, tl)
    rng = np.random.default_rng(11)
    for sh in plan.shots:
        if sh["glitch"]:
            for at in (sh["start"], sh["voice_start"] + (sh["voice_end"] - sh["voice_start"]) * 0.55 - 0.09):
                a = int(at * sr)
                L = int(0.17 * sr)
                if 0 <= a < n - L:
                    mix[a:a + L] += rng.standard_normal(L).astype(np.float32) * 0.05
    mix = mix / (np.max(np.abs(mix)) or 1) * 0.89
    master = os.path.join(args.out, "master.wav")
    v1.write_wav(master, sr, mix)

    print("4/5 frames…", flush=True)
    fps = 12 if args.preview else FPS
    scale = 0.5 if args.preview else 1.0
    vid = os.path.join(args.out, "video_only.mp4")
    render_video(plan, vid, fps, scale, args.workers)

    print("5/5 mux…", flush=True)
    final = os.path.join(args.out, f"file{ep['file_number']}_v2{'_preview' if args.preview else ''}.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", vid, "-i", master, "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", final], check=True)
    os.remove(vid)
    render_thumbnail(ep, os.path.join(args.out, "thumbnail_v2.jpg"))
    print("done →", final)


if __name__ == "__main__":
    main()
