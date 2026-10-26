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
# Shots. Signature: (d, img, t, dur, args, ctx) where t is seconds into shot.
# ----------------------------------------------------------------------------


def shot_elevator_wide(d, img, t, dur, a, ctx):
    doors = a.get("doors", "closed")
    if doors == "open":
        of = 1.0
    elif doors == "opening":
        of = ease(t / 3.0)
    else:
        of = 0.0
    elevator_frame(d, 820, 560, 520, 640, of)
    if a.get("you") == "inside":
        person(d, 820, 960, s=0.95)
    flick = (int(t * 10) % 23) != 7
    display(d, 1230, 240, a.get("panel", "13"), on=flick)
    if a.get("x"):
        d.line([(560, 885), (1080, 885)], fill=RED, width=8)
        big_x(d, 1345, 560, s=70, w=16)


def shot_office_night(d, img, t, dur, a, ctx):
    # window + moon
    d.rectangle([300, 230, 620, 520], outline=WHITE, width=10)
    d.line([(460, 230), (460, 520)], fill=WHITE, width=8)
    d.line([(300, 375), (620, 375)], fill=WHITE, width=8)
    d.ellipse([500, 270, 570, 340], fill=YELLOW)
    d.ellipse([522, 262, 592, 332], fill=BLACK)
    # desk, lamp pool, person
    d.rounded_rectangle([860, 700, 1500, 730], radius=8, fill=WHITE)
    d.rectangle([900, 730, 924, 930], fill=WHITE)
    d.rectangle([1436, 730, 1460, 930], fill=WHITE)
    glow = 0.75 + 0.25 * math.sin(t * 2.0)
    d.polygon([(1340, 560), (1250, 700), (1460, 700)], fill=tuple(int(c * glow * 0.45) for c in YELLOW))
    v1.thick_line(d, [(1340, 700), (1340, 560), (1300, 540)], 10, WHITE)
    d.ellipse([1270, 520, 1330, 560], fill=YELLOW)
    person(d, 1080, 930, s=1.05)
    # clock
    cx, cy, r = 1560, 300, 80
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE, width=8)
    a1 = math.radians(330 + t * 6)
    v1.thick_line(d, [(cx, cy), (cx + math.sin(a1) * 55, cy - math.cos(a1) * 55)], 8, WHITE)
    v1.thick_line(d, [(cx, cy), (cx, cy - 40)], 10, WHITE)


def shot_seven_rules(d, img, t, dur, a, ctx):
    n_on = min(7, int(t / max(0.3, (dur - 0.6) / 7)) + 1)
    f = mont(800, 70)
    for i in range(7):
        x = 330 + i * 190
        y = 420
        on = i < n_on
        d.rounded_rectangle([x, y, x + 150, y + 200], radius=14, outline=WHITE if on else DIM, width=6,
                            fill=WHITE if on and i == n_on - 1 else None)
        col = BLACK if on and i == n_on - 1 else (WHITE if on else DIM)
        s = str(i + 1)
        d.text((x + 75 - d.textlength(s, font=f) / 2, y + 55), s, font=f, fill=col)
    dotted(d, (330, 680), (330 + 6 * 190 + 150, 680), color=GREY, upto=n_on / 7)


def shot_rules_shuffled(d, img, t, dur, a, ctx):
    order = [3, 1, 6, 2, 7, 4, 5]
    f = mont(800, 70)
    rng = np.random.default_rng(3)
    for i, num in enumerate(order):
        x = 330 + i * 190
        y = 420 + int(rng.integers(-60, 60)) * ease(t / 1.2)
        ang = float(rng.uniform(-14, 14)) * ease(t / 1.2)
        tile = Image.new("RGBA", (170, 220), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile)
        wrong = num != i + 1
        col = RED if wrong and t > 1.4 else WHITE
        td.rounded_rectangle([10, 10, 160, 210], radius=14, outline=col, width=6)
        s = str(num)
        td.text((85 - td.textlength(s, font=f) / 2, 65), s, font=f, fill=col)
        tile = tile.rotate(ang, resample=Image.BICUBIC, expand=True)
        img.paste(tile, (x - 10, int(y) - 10), tile)


def shot_rule_card(d, img, t, dur, a, ctx):
    rule = ctx["rule"]
    name = ctx["rule_name"]
    fade = ease(t / 0.35)
    col = tuple(int(c * fade) for c in WHITE)
    f = mont(800, 150)
    word = "RULE"
    tw = d.textlength(word, font=f)
    box = 170
    total = tw + 40 + box
    x0 = W / 2 - total / 2
    y0 = 300
    d.text((x0, y0), word, font=f, fill=col)
    bx = x0 + tw + 40
    d.rounded_rectangle([bx, y0 + 18, bx + box, y0 + 18 + box], radius=16, fill=col)
    fn = mont(800, 130)
    s = str(rule)
    d.text((bx + box / 2 - d.textlength(s, font=fn) / 2, y0 + 30), s, font=fn, fill=BLACK)
    # typed rule name
    n = int(len(name) * ease((t - 0.35) / 1.1))
    f2 = mont(700, 54)
    shown = name[:n]
    spaced_text(d, (W / 2, 560), shown, f2, col, 6, anchor="m")
    full_w = spaced_width(d, name, f2, 6)
    ul = full_w * ease((t - 0.35) / 1.1)
    d.rectangle([W / 2 - full_w / 2, 640, W / 2 - full_w / 2 + ul, 648], fill=RED)
    # progress boxes
    for i in range(7):
        bx = W / 2 - 7 * 52 / 2 + i * 52
        on = i + 1 == rule
        done = i + 1 < rule
        d.rounded_rectangle([bx, 700, bx + 38, 738], radius=6,
                            outline=WHITE if (on or done) else DIM, width=3, fill=WHITE if on else None)
        fs = mont(700, 20)
        ss = str(i + 1)
        d.text((bx + 19 - d.textlength(ss, font=fs) / 2, 707), ss, font=fs,
               fill=BLACK if on else (WHITE if done else DIM))


def shot_directory(d, img, t, dur, a, ctx):
    n = a.get("floors", 12)
    floor_board(d, 1060, 150 if n == 13 else 175, n, reveal=ease(t / 2.2), red_top=(n == 13 and t > 1.0))
    person(d, 640, 930, s=1.25, pose="look_up")


def shot_card_vs_panel(d, img, t, dur, a, ctx):
    card(d, 380, 380, "12")
    display(d, 1260, 410, "13", w=300, h=170, on=(int(t * 10) % 19 != 7))
    f = mont(800, 130)
    on = int(t * 3) % 2 == 0
    d.text((W / 2 - d.textlength("≠", font=f) / 2, 380), "≠", font=f, fill=RED if on else WHITE)


def shot_hallway_compare(d, img, t, dur, a, ctx):
    for i, lab in enumerate(["YOUR HALLWAY", "THIS HALLWAY"]):
        x0 = 210 + i * 780
        d.rounded_rectangle([x0, 200, x0 + 720, 720], radius=12, outline=WHITE, width=6)
        vx, vy = x0 + 360, 440
        for k in range(7):
            d.line([(x0 + k * 120, 720), (vx, vy)], fill=DIM, width=3)
        d.line([(x0, 260), (vx, vy)], fill=DIM, width=3)
        d.line([(x0 + 720, 260), (vx, vy)], fill=DIM, width=3)
        d.rectangle([vx - 24, vy - 50, vx + 24, vy + 6], outline=WHITE, width=4)
        # extinguisher only in YOUR hallway
        if i == 0:
            d.rounded_rectangle([x0 + 560, 470, x0 + 600, 580], radius=18, fill=RED)
        spaced_text(d, (x0 + 360, 750), lab, mont(700, 28), WHITE if i == 0 else GREY, 5, anchor="m")
        if i == 1 and t > dur * 0.55:
            d.rounded_rectangle([x0 + 548, 460, x0 + 612, 592], radius=18, outline=GREY, width=3)
            big_x(d, x0 + 580, 526, s=26, w=6)


def shot_button_wire(d, img, t, dur, a, ctx):
    cx, cy = 560, 540
    d.ellipse([cx - 150, cy - 150, cx + 150, cy + 150], outline=WHITE, width=12)
    f = mont(800, 90)
    d.text((cx - d.textlength(">|<", font=f) / 2, cy - 60), ">|<", font=f, fill=WHITE)
    end = 0.25 + 0.75 * ease(t / 2.0)
    x1 = cx + 160 + (1500 - cx - 160) * end
    n = int((x1 - cx - 160) / 26)
    for i in range(n):
        x = cx + 160 + i * 26
        fade = max(0.0, 1 - i / 40)
        c = tuple(int(v * fade) for v in WHITE)
        d.ellipse([x - 5, cy - 5, x + 5, cy + 5], fill=c)
    if t > 1.8:
        f2 = mont(800, 120)
        d.text((1520, 460), "?", font=f2, fill=GREY)


def shot_button_press(d, img, t, dur, a, ctx):
    cx, cy = 960, 520
    hit = t > min(1.4, dur * 0.5)
    if hit:
        r = 150 + 140 * ease((t - 1.4) / 0.8)
        alpha = max(0.0, 1 - (t - 1.4) / 0.9)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=tuple(int(c * alpha) for c in RED), width=10)
    d.ellipse([cx - 150, cy - 150, cx + 150, cy + 150], outline=RED if hit else WHITE, width=12)
    f = mont(800, 90)
    d.text((cx - d.textlength(">|<", font=f) / 2, cy - 60), ">|<", font=f, fill=RED if hit else WHITE)
    p = ease(t / 1.4)
    fx, fy = cx + 40 + (1 - p) * 520, cy + 60 + (1 - p) * 420
    v1.thick_line(d, [(fx + 260, fy + 300), (fx + 60, fy + 70)], 70, WHITE)
    v1.thick_line(d, [(fx + 60, fy + 70), (fx, fy)], 34, WHITE)


def shot_building_floors(d, img, t, dur, a, ctx):
    x0, w = 760, 400
    fh = 52
    for i in range(13):
        y = 900 - (i + 1) * fh
        lit = i < int(t / 0.12)
        is13 = i == 12
        col = (RED if is13 else WHITE) if lit else DIM
        d.rectangle([x0, y, x0 + w, y + fh - 10], outline=col, width=4,
                    fill=(RED if is13 and lit and (int(t * 4) % 2 == 0) else None))
        if lit and not is13:
            for k in range(4):
                wx = x0 + 40 + k * 90
                d.rectangle([wx, y + 12, wx + 40, y + 30], fill=YELLOW if (i * 7 + k) % 5 == 0 else FAINT)
    d.rectangle([x0 - 30, 900, x0 + w + 30, 912], fill=WHITE)
    if t > 1.6:
        # the floor "notes" a hurried figure
        person(d, 1380, 900, s=0.8, pose="run")
        dotted(d, (x0 + w + 10, 900 - 13 * fh + 20), (1370, 640), color=RED, upto=ease((t - 1.6) / 0.8))


def shot_stat(d, img, t, dur, a, ctx):
    val = a.get("value", 100)
    red = a.get("red", False)
    p = ease(t / 1.0)
    shown = int(round(val * p)) if val > 0 else int(round(100 * (1 - p)))
    f = mont(800, 230)
    s = f"{shown}%"
    col = RED if red else WHITE
    d.text((W / 2 - d.textlength(s, font=f) / 2, 230), s, font=f, fill=col)
    spaced_text(d, (W / 2, 520), a.get("label", ""), mont(700, 34), GREY, 7, anchor="m")
    for i in range(10):
        x = W / 2 - 10 * 90 / 2 + i * 90 + 45
        lit = (i < round(shown / 10)) if not red else False
        person(d, x, 860, s=0.42, fill=WHITE if lit else DIM)


def shot_org_chart(d, img, t, dur, a, ctx):
    f = mont(700, 28)

    def box(x, y, label, col=WHITE, w=300, h=90):
        d.rounded_rectangle([x - w / 2, y, x + w / 2, y + h], radius=10, outline=col, width=5)
        spaced_text(d, (x, y + 28), label, f, col, 4, anchor="m")

    box(W / 2, 200, "FLOOR 13", col=RED, w=360)
    d.line([(W / 2, 290), (W / 2, 380)], fill=GREY, width=4)
    d.line([(W / 2 - 520, 380), (W / 2 + 520, 380)], fill=GREY, width=4)
    for i, x in enumerate([W / 2 - 520, W / 2, W / 2 + 520]):
        d.line([(x, 380), (x, 440)], fill=GREY, width=4)
        if i < 2:
            box(x, 440, "OCCUPIED", col=DIM)
            person(d, x, 760, s=0.45, fill=DIM)
    x = W / 2 + 520
    p = ease((t - 0.6) / 1.0)
    if p > 0:
        col = tuple(int(c * p) for c in WHITE)
        box(x, 440, "NEW HIRE", col=col)
        person(d, x, 760, s=0.45, fill=col)
        if t > 1.8:
            spaced_text(d, (x, 790), "YOU", mont(800, 30), RED, 6, anchor="m")


def shot_counter(d, img, t, dur, a, ctx):
    n = 1 + int(t * 1.4)
    f = mont(800, 260)
    s = f"{min(n, 90):02d}"
    d.text((W / 2 - d.textlength(s, font=f) / 2, 260), s, font=f, fill=WHITE)
    cx, cy, r = W / 2, 430, 260
    d.arc([cx - r, cy - r, cx + r, cy + r], start=-90, end=-90 + 360 * min(n, 90) / 90, fill=YELLOW, width=10)
    d.arc([cx - r, cy - r, cx + r, cy + r], start=-90 + 360 * min(n, 90) / 90, end=270, fill=FAINT, width=10)
    spaced_text(d, (W / 2, 750), "OF 90", mont(700, 34), GREY, 8, anchor="m")


def shot_counter_loop(d, img, t, dur, a, ctx):
    seq = ["98", "99", "100", "01"]
    i = min(3, int(t / 0.55))
    f = mont(800, 260)
    s = seq[i]
    col = RED if s in ("100", "01") else WHITE
    d.text((W / 2 - d.textlength(s, font=f) / 2, 260), s, font=f, fill=col)
    cx, cy, r = W / 2, 430, 280
    d.arc([cx - r, cy - r, cx + r, cy + r], start=-80, end=250, fill=GREY, width=8)
    ax, ay = cx + r * math.cos(math.radians(250)), cy + r * math.sin(math.radians(250))
    d.polygon([(ax - 26, ay - 4), (ax + 20, ay - 26), (ax + 10, ay + 26)], fill=GREY)


def shot_number_row(d, img, t, dur, a, ctx):
    nums = list(range(84, 97))
    f = mont(700, 64)
    for i, n in enumerate(nums):
        x = 170 + i * 122
        if n == 90:
            d.rounded_rectangle([x - 6, 470, x + 100, 570], radius=8, outline=RED, width=5)
            if int(t * 3) % 2 == 0:
                d.text((x + 6, 480), "??", font=f, fill=RED)
            continue
        col = WHITE if i <= int(t * 9) else DIM
        d.text((x, 480), str(n), font=f, fill=col)


def shot_eye(d, img, t, dur, a, ctx):
    cx, cy = W / 2, 500
    open_ = ease(t / 1.0)
    w, h = 520, 230 * open_
    d.chord([cx - w, cy - h - 4, cx + w, cy + h + 4], 180, 360, fill=WHITE)
    d.chord([cx - w, cy - h - 4, cx + w, cy + h + 4], 0, 180, fill=WHITE)
    if open_ > 0.3:
        pr = 120 * open_
        d.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=BLACK)
        rr = 52 * open_
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=RED)


def shot_face_away(d, img, t, dur, a, ctx):
    cycle = ["4", "F", "??", "13", "7", "Ø"]
    sym = cycle[int(t * 2.4) % len(cycle)]
    display(d, 1250, 200, sym, color=YELLOW if sym in ("4", "7") else RED)
    person(d, 760, 960, s=1.35, facing=-1)
    dotted(d, (790, 520), (1240, 300), color=DIM, phase=t)
    big_x(d, 1020, 410, s=55, w=14)
    spaced_text(d, (1365, 380), "PRESS NOTHING", mont(700, 26), RED, 5, anchor="m")


def hallway(d, x0, y0, w, h, warm=False, light=True):
    vx, vy = x0 + w / 2, y0 + h * 0.42
    base = tuple(int(c * 0.22) for c in YELLOW) if warm else BLACK
    d.rectangle([x0, y0, x0 + w, y0 + h], fill=base)
    line = tuple(int(c * 0.6) for c in YELLOW) if warm else DIM
    for k in range(9):
        d.line([(x0 + k * w / 8, y0 + h), (vx, vy)], fill=line, width=3)
    d.line([(x0, y0 + 60), (vx, vy)], fill=line, width=3)
    d.line([(x0 + w, y0 + 60), (vx, vy)], fill=line, width=3)
    if light:
        d.ellipse([vx - 60, y0 - 10, vx + 60, y0 + 30], fill=YELLOW if warm else DIM)
    d.rectangle([x0, y0, x0 + w, y0 + h], outline=WHITE, width=10)
    return vx, vy


def shot_safe_hallway(d, img, t, dur, a, ctx):
    hallway(d, 420, 180, 900, 720, warm=True)
    d.rounded_rectangle([1130, 560, 1190, 720], radius=26, fill=RED)
    d.rectangle([1148, 530, 1172, 560], fill=WHITE)
    if t > 0.8:
        check(d, 1580, 480, s=90 * pop((t - 0.8) / 0.4))
        spaced_text(d, (1580, 620), "EXIT HERE", mont(700, 30), GREEN, 6, anchor="m")


def shot_missing_extinguisher(d, img, t, dur, a, ctx):
    on = not (1.0 < t % 2.3 < 1.12)
    hallway(d, 420, 180, 900, 720, warm=False, light=on)
    for k in range(10):
        ang = k / 10 * 2 * math.pi
        x = 1160 + 32 * math.cos(ang)
        y = 640 + 80 * math.sin(ang)
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=GREY)
    if t > 1.0:
        big_x(d, 1580, 500, s=80 * pop((t - 1.0) / 0.4), w=18)


def shot_desk_reading(d, img, t, dur, a, ctx):
    d.rounded_rectangle([560, 700, 1360, 730], radius=8, fill=WHITE)
    d.rectangle([600, 730, 624, 930], fill=WHITE)
    d.rectangle([1296, 730, 1320, 930], fill=WHITE)
    person(d, 960, 930, s=1.0)
    # paper held up
    px, py = 1000, 470
    d.rectangle([px, py, px + 200, py + 250], fill=WHITE)
    spaced_text(d, (px + 100, py + 30), "FILE 001", mont(800, 26), BLACK, 3, anchor="m")
    for k in range(6):
        d.line([(px + 28, py + 90 + k * 24), (px + 172, py + 90 + k * 24)], fill=GREY, width=5)
    # lamp
    glow = 0.8 + 0.2 * math.sin(t * 9) if t > 1.2 else 1.0
    d.polygon([(760, 520), (650, 700), (870, 700)], fill=tuple(int(c * 0.4 * glow) for c in YELLOW))
    d.ellipse([730, 500, 790, 540], fill=YELLOW)
    v1.thick_line(d, [(760, 700), (760, 540)], 10, WHITE)


def shot_card_rewrite(d, img, t, dur, a, ctx):
    card(d, 640, 380, "12", w=640, h=320, strike=t > 0.5)
    if t > 1.0:
        f = mont(800, 120)
        d.text((1320, 470), "13", font=f, fill=RED)


def shot_wallet(d, img, t, dur, a, ctx):
    d.rounded_rectangle([560, 420, 1360, 860], radius=40, outline=WHITE, width=12)
    d.line([(960, 420), (960, 860)], fill=WHITE, width=8)
    y = 120 + (430 - 120) * ease(t / 1.2)
    card(d, 1000, y, "13", w=300, h=190, num_color=RED)
    d.rectangle([980, 640, 1340, 850], fill=BLACK)
    d.rounded_rectangle([980, 640, 1340, 850], radius=12, outline=WHITE, width=8)


def shot_end_card(d, img, t, dur, a, ctx):
    f = mont(800, 96)
    spaced_text(d, (W / 2, 420), "END OF FILE", f, WHITE, 12, anchor="m")
    if a.get("sub"):
        spaced_text(d, (W / 2, 560), "FURTHER TRAINING MATERIALS ARE AVAILABLE", mont(600, 30), GREY, 6, anchor="m")


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
        # push-in
        z = 1.0 + 0.075 * ease(tl / max(dur, 0.5))
        cw, ch = W / z, H / z
        box = (int((W - cw) / 2), int((H - ch) / 2), int((W + cw) / 2), int((H + ch) / 2))
        if sh["shot"] in ("rule_card", "end_card"):
            layer = layer.crop(box).resize((W, H), Image.BILINEAR)
        else:
            fit = 0.86
            small = layer.crop(box).resize((int(W * fit), int(H * fit)), Image.BILINEAR)
            layer = Image.new("RGB", (W, H), BLACK)
            layer.paste(small, (int(W / 2 - W * fit / 2), int(380 - 380 * fit)))
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
