#!/usr/bin/env python3
"""
Build a Bureau "instruction file" episode: synthesize narration, measure every
line, render pictogram scenes timed to the real audio, mix tape-style sound
design, and encode the final MP4 + thumbnail.

Usage:
    python3 scripts/build_episode.py episodes/001-elevator \
        --voice voices/en-us-ryan-medium.onnx [--out build/001] [--preview]

--preview renders at half resolution / 12 fps for a quick check.
"""
import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ----------------------------------------------------------------------------
# Look
# ----------------------------------------------------------------------------
W, H = 1920, 1080
FPS = 24
BG = (232, 226, 211)        # beige safety-sign paper
INK = (20, 20, 20)
ORANGE = (224, 102, 26)     # hazard accent
RED = (179, 38, 30)
GREEN = (46, 110, 60)
DARK = (14, 14, 14)
GREY = (120, 116, 108)

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
MONO = os.path.join(FONT_DIR, "DejaVuSansMono.ttf")
MONO_B = os.path.join(FONT_DIR, "DejaVuSansMono-Bold.ttf")
SANS_B = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

_font_cache = {}


def font(path, size):
    key = (path, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(path, size)
    return _font_cache[key]


RULE_WORDS = {1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE", 6: "SIX", 7: "SEVEN"}

# ----------------------------------------------------------------------------
# Narration
# ----------------------------------------------------------------------------


def synth_line(text, voice, cfg, out_wav, vcfg):
    cmd = [
        sys.executable, "-m", "piper", "-m", voice, "-c", cfg,
        "--length-scale", str(vcfg.get("length_scale", 1.2)),
        "--noise-scale", str(vcfg.get("noise_scale", 0.45)),
        "--noise-w-scale", str(vcfg.get("noise_w_scale", 0.7)),
        "--sentence-silence", str(vcfg.get("sentence_silence", 0.4)),
        "-f", out_wav,
    ]
    subprocess.run(cmd, input=text.encode(), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def read_wav(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
        if w.getnchannels() == 2:
            data = data.reshape(-1, 2).mean(axis=1)
    return sr, data


def write_wav(path, sr, data):
    data = np.clip(data, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((data * 32767).astype(np.int16).tobytes())


def build_timeline(ep, voice, cfg, workdir):
    """Synthesize every line, return (sr, narration_track, timeline)."""
    vcfg = ep.get("voice", {})
    sr = None
    clips = []  # (segment_index, line_index, samples)
    for si, seg in enumerate(ep["segments"]):
        for li, line in enumerate(seg["lines"]):
            path = os.path.join(workdir, f"{seg['id']}_{li:02d}.wav")
            if not os.path.exists(path):
                synth_line(line, voice, cfg, path, vcfg)
            s, d = read_wav(path)
            # trim leading/trailing silence so pauses are ours, not piper's
            thr = 0.01
            idx = np.where(np.abs(d) > thr)[0]
            if len(idx):
                d = d[max(0, idx[0] - int(0.05 * s)): min(len(d), idx[-1] + int(0.25 * s))]
            sr = sr or s
            clips.append((si, li, d))

    t = 0.0
    pieces = []
    timeline = []  # per segment: dict(start, end, lines=[(start,end,text)])
    for si, seg in enumerate(ep["segments"]):
        t += seg.get("pre_pause", 1.2)
        seg_t = {"id": seg["id"], "scene": seg["scene"], "rule": seg.get("rule"),
                 "start": t, "lines": [], "silence_before": seg.get("silence_before", False)}
        gap = seg.get("line_gap", 0.55)
        for li, line in enumerate(seg["lines"]):
            d = next(c for c in clips if c[0] == si and c[1] == li)[2]
            dur = len(d) / sr
            pieces.append((t, d))
            seg_t["lines"].append({"start": t, "end": t + dur, "text": line})
            t += dur + gap
        t -= gap
        t += seg.get("post_pause", 0.0)
        seg_t["end"] = t
        timeline.append(seg_t)
    total = t + 1.0
    # extend each segment to the start of the next so scenes hold through pauses
    for i in range(len(timeline) - 1):
        timeline[i]["end"] = timeline[i + 1]["start"]
    timeline[-1]["end"] = total

    track = np.zeros(int(total * sr) + sr, dtype=np.float32)
    for start, d in pieces:
        a = int(start * sr)
        track[a:a + len(d)] += d
    return sr, track, timeline, total


# ----------------------------------------------------------------------------
# Sound design
# ----------------------------------------------------------------------------


def tape_process(in_wav, out_wav):
    """Narrow the band, pitch down a touch, soft compress: a tired instruction tape."""
    af = ("highpass=f=140,lowpass=f=5200,"
          "asetrate=22050*0.965,aresample=22050,"
          "acompressor=threshold=-18dB:ratio=3:attack=15:release=200:makeup=4dB,"
          "volume=0.9")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", in_wav, "-af", af, out_wav], check=True)


def one_pole_lowpass(x, sr, cutoff):
    rc = 1.0 / (2 * math.pi * cutoff)
    a = (1.0 / sr) / (rc + 1.0 / sr)
    y = np.empty_like(x)
    acc = 0.0
    # vectorised IIR via lfilter-free loop in chunks (fast enough for a few minutes)
    for i in range(0, len(x), 1):
        acc += a * (x[i] - acc)
        y[i] = acc
    return y


def design_bed(sr, total, timeline):
    """Hiss + rising drone, with a hard cut to silence before the silence_before segment."""
    n = int(total * sr) + sr
    rng = np.random.default_rng(7)
    t = np.arange(n) / sr

    # hiss: filtered noise, very low
    hiss = rng.standard_normal(n).astype(np.float32)
    # cheap lowpass via moving average, then highpass-ish by subtracting slower average
    k = 6
    hiss = np.convolve(hiss, np.ones(k) / k, mode="same")
    hiss *= 0.012

    # drone: detuned low sines with slow LFO, amplitude stepping up per rule
    env = np.zeros(n, dtype=np.float32)
    for seg in timeline:
        a, b = int(seg["start"] * sr), int(seg["end"] * sr)
        if seg["rule"]:
            level = 0.025 + 0.012 * seg["rule"]
        elif seg["scene"] == "directory_13":
            level = 0.10
        elif seg["id"] == "card":
            level = 0.02
        else:
            level = 0.0
        env[a:b] = level
    # smooth the envelope so steps don't click
    env = np.convolve(env, np.ones(int(sr * 0.8)) / int(sr * 0.8), mode="same")
    lfo = 0.5 + 0.5 * np.sin(2 * math.pi * 0.11 * t)
    drone = (np.sin(2 * math.pi * 55.0 * t) * 0.6
             + np.sin(2 * math.pi * 55.6 * t) * 0.4
             + np.sin(2 * math.pi * 110.0 * t) * 0.25 * lfo).astype(np.float32)
    drone *= env

    bed = hiss + drone

    # hard silence: 1.6 s of nothing before any segment flagged silence_before
    for seg in timeline:
        if seg["silence_before"]:
            b = int(seg["start"] * sr)
            a = max(0, b - int(1.6 * sr))
            bed[a:b] = 0.0
    # fade out at the very end
    fade = int(2.0 * sr)
    bed[-fade:] *= np.linspace(1, 0, fade)
    return bed


# ----------------------------------------------------------------------------
# Pictogram drawing helpers
# ----------------------------------------------------------------------------


def thick_line(d, pts, width, fill=INK):
    d.line(pts, fill=fill, width=width, joint="curve")
    r = width // 2
    for (x, y) in (pts[0], pts[-1]):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def figure(d, x, y, scale=1.0, pose="stand", fill=INK, facing=1):
    """ISO-style stick person. (x, y) = feet centre. facing: 1 right, -1 left."""
    s = scale
    head_r = 30 * s
    lw = int(max(6, 20 * s))
    hip = y - 150 * s
    shoulder = y - 300 * s
    head_c = y - 350 * s
    # torso
    d.rounded_rectangle([x - 36 * s, shoulder - 10 * s, x + 36 * s, hip + 10 * s], radius=26 * s, fill=fill)
    # head
    d.ellipse([x - head_r, head_c - head_r, x + head_r, head_c + head_r], fill=fill)
    # legs
    if pose == "run":
        thick_line(d, [(x - 10 * s, hip), (x - 70 * s, y)], lw, fill)
        thick_line(d, [(x + 10 * s, hip), (x + 60 * s, y - 40 * s)], lw, fill)
    else:
        thick_line(d, [(x - 18 * s, hip), (x - 28 * s, y)], lw, fill)
        thick_line(d, [(x + 18 * s, hip), (x + 28 * s, y)], lw, fill)
    # arms
    if pose == "point":
        thick_line(d, [(x + 30 * s * facing, shoulder + 20 * s), (x + 140 * s * facing, shoulder - 20 * s)], lw, fill)
        thick_line(d, [(x - 30 * s * facing, shoulder + 20 * s), (x - 40 * s * facing, hip)], lw, fill)
    elif pose == "look_up":
        thick_line(d, [(x + 30 * s, shoulder + 20 * s), (x + 60 * s, hip)], lw, fill)
        thick_line(d, [(x - 30 * s, shoulder + 20 * s), (x - 60 * s, hip)], lw, fill)
    elif pose == "run":
        thick_line(d, [(x + 30 * s, shoulder + 20 * s), (x + 110 * s, shoulder - 30 * s)], lw, fill)
        thick_line(d, [(x - 30 * s, shoulder + 20 * s), (x - 100 * s, hip - 20 * s)], lw, fill)
    elif pose == "hands_ears":
        thick_line(d, [(x + 30 * s, shoulder + 20 * s), (x + 40 * s, head_c)], lw, fill)
        thick_line(d, [(x - 30 * s, shoulder + 20 * s), (x - 40 * s, head_c)], lw, fill)
    else:  # stand
        thick_line(d, [(x + 30 * s, shoulder + 20 * s), (x + 42 * s, hip)], lw, fill)
        thick_line(d, [(x - 30 * s, shoulder + 20 * s), (x - 42 * s, hip)], lw, fill)


def elevator(d, cx, cy, w, h, open_frac=0.0, inside=DARK, frame=INK, door=(205, 198, 182)):
    """Elevator door frame centred at (cx, cy). open_frac 0 closed .. 1 open."""
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    d.rectangle([x0 - 22, y0 - 22, x0, y1 + 22], fill=frame)
    d.rectangle([x1, y0 - 22, x1 + 22, y1 + 22], fill=frame)
    d.rectangle([x0 - 22, y0 - 22, x1 + 22, y0], fill=frame)
    d.rectangle([x0 - 22, y1, x1 + 22, y1 + 22], fill=frame)
    if inside is not None:
        d.rectangle([x0, y0, x1, y1], fill=inside)
    gap = (w / 2) * open_frac
    # left door
    d.rectangle([x0, y0, cx - gap, y1], fill=door)
    # right door
    d.rectangle([cx + gap, y0, x1, y1], fill=door)
    # seam
    if open_frac < 0.02:
        d.line([(cx, y0), (cx, y1)], fill=frame, width=6)
    return (x0, y0, x1, y1)


def panel(d, x, y, text, w=260, h=150, fill=INK, text_fill=ORANGE, flicker=1.0):
    d.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=fill)
    d.rounded_rectangle([x + 16, y + 16, x + w - 16, y + h - 16], radius=8, fill=(30, 30, 30))
    if flicker > 0.5:
        f = font(MONO_B, int(h * 0.62))
        tw = d.textlength(text, font=f)
        d.text((x + w / 2 - tw / 2, y + h * 0.17), text, font=f, fill=text_fill)


def directory_board(d, x, y, floors, w=520, misaligned=None, highlight=None, show_upto=None):
    """Floor directory list. floors: list of labels, drawn top-down."""
    rows = len(floors)
    rh = 58 if rows <= 12 else 50
    h = rows * rh + 60
    d.rectangle([x, y, x + w, y + h], fill=INK)
    d.rectangle([x + 10, y + 10, x + w - 10, y + h - 10], fill=BG)
    f = font(MONO_B, 36)
    f_small = font(MONO, 30)
    d.text((x + 30, y + 22), "FLOOR DIRECTORY", font=f_small, fill=INK)
    for i, lab in enumerate(floors):
        if show_upto is not None and i >= show_upto:
            break
        yy = y + 70 + i * rh
        dx = 0
        col = INK
        if misaligned is not None and lab == misaligned:
            dx = 9
            yy += 4
            col = RED
        d.text((x + 40 + dx, yy), f"{lab:>3}", font=f, fill=col)
        d.line([(x + 140 + dx, yy + 24), (x + w - 40 + dx, yy + 24)], fill=col if col == RED else GREY, width=3)
        if highlight == lab:
            d.rectangle([x + 24, yy - 6, x + w - 24, yy + 50], outline=ORANGE, width=5)


def red_x(d, cx, cy, size=80, width=18):
    s = size
    thick_line(d, [(cx - s, cy - s), (cx + s, cy + s)], width, RED)
    thick_line(d, [(cx - s, cy + s), (cx + s, cy - s)], width, RED)


def green_check(d, cx, cy, size=80, width=18):
    s = size
    thick_line(d, [(cx - s, cy), (cx - s * 0.2, cy + s * 0.8), (cx + s, cy - s * 0.7)], width, GREEN)


def speech_lines(d, x, y, n=3, phase=0.0, fill=INK):
    for i in range(n):
        if (i + phase) % n < n - 0.5:
            r = 40 + i * 42
            d.arc([x - r, y - r, x + r, y + r], start=-35, end=35, fill=fill, width=10)


def extinguisher(d, x, y, h=160):
    w = h * 0.36
    d.rounded_rectangle([x - w / 2, y - h, x + w / 2, y], radius=w / 2, fill=RED)
    d.rectangle([x - w * 0.18, y - h - 26, x + w * 0.18, y - h], fill=INK)
    d.line([(x, y - h - 10), (x + w * 0.9, y - h * 0.65)], fill=INK, width=10)


def hand_finger(d, x, y, scale=1.0, fill=INK):
    """Pointing hand, fingertip at (x, y), coming from bottom-left."""
    s = scale
    thick_line(d, [(x - 170 * s, y + 170 * s), (x - 40 * s, y + 40 * s)], int(46 * s), fill)
    thick_line(d, [(x - 40 * s, y + 40 * s), (x, y)], int(24 * s), fill)


def header(d, text, sub=None):
    f = font(MONO_B, 44)
    d.text((80, 56), text, font=f, fill=INK)
    if sub:
        f2 = font(MONO, 30)
        d.text((80, 112), sub, font=f2, fill=GREY)
    d.line([(80, 160), (W - 80, 160)], fill=INK, width=4)


def footer(d, file_no):
    f = font(MONO, 26)
    d.text((80, H - 60), f"OAB · FILE {file_no} · INTERNAL", font=f, fill=GREY)


def caption(d, text, color=INK, bg=None):
    """Bottom caption, wrapped to width."""
    f = font(MONO_B, 40)
    maxw = W - 320
    words = text.split()
    lines, cur = [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if d.textlength(trial, font=f) <= maxw:
            cur = trial
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    lh = 54
    y = H - 110 - lh * len(lines)
    for ln in lines:
        tw = d.textlength(ln, font=f)
        x = W / 2 - tw / 2
        if bg is not None:
            d.rectangle([x - 18, y - 6, x + tw + 18, y + lh - 4], fill=bg)
        d.text((x, y), ln, font=f, fill=color)
        y += lh


def ease(p):
    p = min(1.0, max(0.0, p))
    return p * p * (3 - 2 * p)


# ----------------------------------------------------------------------------
# Scenes. Each receives (draw, p, t_in_scene, seg, ep) where p = progress 0..1,
# and the index of the active line (or -1) plus progress within that line.
# ----------------------------------------------------------------------------


def scene_black_title(img, d, p, ts, seg, ep, li, lp):
    d.rectangle([0, 0, W, H], fill=DARK)
    # title line types itself in over the spoken line
    if li >= 0:
        txt = seg["lines"][0]["text"]
        n = int(len(txt) * min(1.0, lp * 1.15))
        f = font(MONO_B, 52)
        shown = txt[:n]
        # wrap
        words = shown.split(" ")
        lines, cur = [], ""
        for w_ in words:
            trial = (cur + " " + w_).strip()
            if d.textlength(trial, font=f) <= W - 300:
                cur = trial
            else:
                lines.append(cur)
                cur = w_
        lines.append(cur)
        y = H / 2 - 30 * len(lines)
        for ln in lines:
            tw = d.textlength(ln, font=f)
            d.text((W / 2 - tw / 2, y), ln, font=f, fill=(225, 220, 205))
            y += 66
    elif ts > 0.3:
        pass
    # tiny tape counter
    f = font(MONO, 26)
    d.text((80, H - 70), f"PLAY  ▶   {int(ts // 60):02d}:{int(ts % 60):02d}", font=f, fill=(120, 120, 110))


def scene_bureau_card(img, d, p, ts, seg, ep, li, lp):
    d.rectangle([0, 0, W, H], fill=BG)
    # border
    d.rectangle([60, 60, W - 60, H - 60], outline=INK, width=6)
    d.rectangle([84, 84, W - 84, H - 84], outline=INK, width=2)
    f = font(SANS_B, 64)
    t1 = ep["bureau"]
    d.text((W / 2 - d.textlength(t1, font=f) / 2, 200), t1, font=f, fill=INK)
    f2 = font(MONO_B, 54)
    t2 = f"FILE {ep['file_number']}"
    d.text((W / 2 - d.textlength(t2, font=f2) / 2, 310), t2, font=f2, fill=ORANGE)
    f3 = font(MONO, 34)
    t3 = ep["classification"]
    d.text((W / 2 - d.textlength(t3, font=f3) / 2, 400), t3, font=f3, fill=GREY)
    # orange band
    d.rectangle([160, 500, W - 160, 600], fill=ORANGE)
    f4 = font(MONO_B, 46)
    t4 = "THIS FILE CONTAINS SEVEN RULES"
    d.text((W / 2 - d.textlength(t4, font=f4) / 2, 523), t4, font=f4, fill=BG)
    # stamp appears later
    if p > 0.45:
        f5 = font(MONO_B, 40)
        t5 = "FOLLOW IN ORDER"
        tw = d.textlength(t5, font=f5)
        x, y = W / 2 - tw / 2, 700
        d.rectangle([x - 30, y - 18, x + tw + 30, y + 60], outline=RED, width=6)
        d.text((x, y), t5, font=f5, fill=RED)
    footer(d, ep["file_number"])


def scene_directory(img, d, p, ts, seg, ep, li, lp):
    d.rectangle([0, 0, W, H], fill=BG)
    header(d, "RULE ONE", "Know how many floors your building has.")
    floors = [str(i) for i in range(12, 0, -1)]
    # rows appear one by one during first line
    show = len(floors) if li >= 1 else int(ease(min(1.0, ts / 3.0)) * len(floors))
    directory_board(d, 1060, 240, floors, show_upto=show)
    figure(d, 780, 920, scale=1.3, pose="look_up")
    if li >= 1:
        # wallet card
        x, y = 200, 300
        d.rounded_rectangle([x, y, x + 300, y + 190], radius=16, fill=INK)
        d.rounded_rectangle([x + 14, y + 14, x + 286, y + 176], radius=10, fill=BG)
        f = font(MONO_B, 96)
        d.text((x + 150 - d.textlength("12", font=f) / 2, y + 40), "12", font=f, fill=INK)
        f2 = font(MONO, 24)
        d.text((x + 24, y + 150), "FLOORS · KEEP ON PERSON", font=f2, fill=GREY)
    footer(d, ep["file_number"])


def scene_doors_open_13(img, d, p, ts, seg, ep, li, lp):
    d.rectangle([0, 0, W, H], fill=BG)
    header(d, "RULE TWO", "If the display shows a number not on your list, remain inside.")
    # doors open slowly starting with line 2
    open_frac = 0.0
    if li >= 1:
        open_frac = ease(min(1.0, (ts - seg["lines"][1]["start"] + seg["start"]) / 5.0))
    # hallway inside (drawn before doors cover it)
    x0, y0, x1, y1 = 760 - 300, 300, 760 + 300, 980
    d.rectangle([x0, y0, x1, y1], fill=DARK)
    # perspective lines of a hallway, dim
    vx, vy = 760, 640
    for k in range(-3, 4):
        d.line([(x0 + k * 100 + 300, y1), (vx, vy)], fill=(40, 40, 40), width=3)
    d.line([(x0, y0 + 80), (vx, vy)], fill=(40, 40, 40), width=3)
    d.line([(x1, y0 + 80), (vx, vy)], fill=(40, 40, 40), width=3)
    elevator(d, 760, 640, 600, 680, open_frac=open_frac, inside=None)
    # you: standing beside the car, not in the doorway
    figure(d, 1230, 980, scale=1.15)
    # panel with 13 flicker
    flick = 1.0 if (int(ts * 9) % 7 != 0) else 0.0
    panel(d, 1420, 280, "13", flicker=flick)
    f = font(MONO, 30)
    d.text((1420, 450), "NOT ON YOUR LIST", font=f, fill=RED)
    if li >= 3:
        red_x(d, 1560, 700, size=80)
        f2 = font(MONO_B, 36)
        d.text((1420, 820), "DO NOT CONFIRM", font=f2, fill=RED)
    footer(d, ep["file_number"])


def scene_close_button(img, d, p, ts, seg, ep, li, lp):
    d.rectangle([0, 0, W, H], fill=BG)
    header(d, "RULE THREE", "Do not press the door close button.")
    # big panel
    px, py = 1150, 280
    d.rounded_rectangle([px, py, px + 420, py + 620], radius=20, fill=INK)
    d.rounded_rectangle([px + 20, py + 20, px + 400, py + 600], radius=14, fill=(200, 194, 178))
    # buttons grid
    f = font(MONO_B, 40)
    labels = [["9", "10", "11"], ["6", "7", "8"], ["3", "4", "5"], ["G", "1", "2"]]
    for r, row in enumerate(labels):
        for c, lab in enumerate(row):
            bx = px + 70 + c * 110
            by = py + 60 + r * 100
            d.ellipse([bx, by, bx + 70, by + 70], fill=INK)
            d.text((bx + 35 - d.textlength(lab, font=f) / 2, by + 12), lab, font=f, fill=BG)
    # door close button, highlighted
    bx, by = px + 180, py + 480
    d.ellipse([bx - 10, by - 10, bx + 80, by + 80], fill=ORANGE)
    d.ellipse([bx, by, bx + 70, by + 70], fill=INK)
    f2 = font(MONO_B, 34)
    d.text((bx + 35 - d.textlength(">|<", font=f2) / 2, by + 16), ">|<", font=f2, fill=BG)
    # finger approaches during line 0, X stamps during line 1+
    approach = ease(min(1.0, ts / 3.5))
    fx = bx + 35 - (1 - approach) * 500
    fy = by + 40 + (1 - approach) * 300
    hand_finger(d, fx, fy, scale=1.0)
    if li >= 1:
        red_x(d, bx + 35, by + 35, size=120, width=22)
    if li >= 3:
        f3 = font(MONO_B, 40)
        d.text((240, 420), "FLOORS REMEMBER", font=f3, fill=RED)
        d.text((240, 480), "WHO IS IN A HURRY.", font=f3, fill=RED)
    figure(d, 520, 950, scale=1.1, pose="point", facing=1)
    footer(d, ep["file_number"])


def scene_hallway_voice(img, d, p, ts, seg, ep, li, lp):
    d.rectangle([0, 0, W, H], fill=BG)
    header(d, "RULE FOUR", "If someone on the floor says your name, do not answer.")
    # open elevator, hallway, distant silhouette
    cx, cy = 700, 640
    x0, y0, x1, y1 = cx - 320, 290, cx + 320, 990
    d.rectangle([x0, y0, x1, y1], fill=DARK)
    vx, vy = cx, 620
    for k in range(-3, 4):
        d.line([(x0 + (k + 3) * 106, y1), (vx, vy)], fill=(42, 42, 42), width=3)
    # silhouette: grows very slightly closer over the segment
    sc = 0.55 + 0.25 * ease(p)
    figure(d, cx + 40, 760 + 60 * ease(p), scale=sc, fill=(135, 135, 128))
    speech_lines(d, cx + 40 + 70 * sc, 760 + 60 * ease(p) - 330 * sc, n=3, phase=ts * 2.0, fill=(200, 200, 190))
    elevator(d, cx, cy, 640, 700, open_frac=1.0, inside=None)
    # you, beside the car, hands over ears from line 1
    figure(d, 1560, 980, scale=1.15, pose="hands_ears" if li >= 1 else "stand")
    if li >= 1:
        # stats card
        x, y = 1120, 200
        d.rectangle([x, y, x + 560, y + 250], fill=INK)
        f = font(MONO_B, 44)
        f2 = font(MONO, 28)
        d.text((x + 30, y + 24), "100%", font=f, fill=ORANGE)
        d.text((x + 180, y + 34), "correct about the name", font=f2, fill=BG)
        if li >= 2:
            d.text((x + 30, y + 130), "  0%", font=f, fill=ORANGE)
            d.text((x + 180, y + 140), "were a coworker", font=f2, fill=BG)
    footer(d, ep["file_number"])


def scene_countdown(img, d, p, ts, seg, ep, li, lp):
    d.rectangle([0, 0, W, H], fill=BG)
    header(d, "RULE FIVE", "The doors will close on their own in approximately ninety seconds.")
    seg_dur = seg["end"] - seg["start"]
    close_frac = ease(ts / max(1.0, seg_dur - 1.5))
    # inside hallway dark
    cx, cy = 700, 640
    d.rectangle([cx - 300, 300, cx + 300, 980], fill=DARK)
    elevator(d, cx, cy, 600, 680, open_frac=1.0 - close_frac)
    figure(d, 1150, 980, scale=1.1)
    # analog clock
    ccx, ccy, r = 1560, 400, 140
    d.ellipse([ccx - r, ccy - r, ccx + r, ccy + r], fill=INK)
    d.ellipse([ccx - r + 14, ccy - r + 14, ccx + r - 14, ccy + r - 14], fill=BG)
    for k in range(12):
        a = math.radians(k * 30)
        d.line([(ccx + math.sin(a) * (r - 30), ccy - math.cos(a) * (r - 30)),
                (ccx + math.sin(a) * (r - 46), ccy - math.cos(a) * (r - 46))], fill=INK, width=5)
    # second hand sweeps 90 "seconds" over the segment (feels longer)
    count = min(90.0, 90.0 * (ts / max(1.0, seg_dur - 2.0)))
    a = math.radians(count * 4.0)
    thick_line(d, [(ccx, ccy), (ccx + math.sin(a) * (r - 40), ccy - math.cos(a) * (r - 40))], 10, RED)
    d.ellipse([ccx - 12, ccy - 12, ccx + 12, ccy + 12], fill=INK)
    f = font(MONO_B, 72)
    shown = int(count)
    label = f"{shown:02d}"
    if li >= 2 and shown >= 89:
        # the glitch: counter slips past 90
        slip = int(ts * 3) % 4
        label = ["90", "91", "...", "01"][slip]
    d.text((ccx - d.textlength(label, font=f) / 2, ccy + r + 30), label, font=f, fill=INK)
    if li >= 3:
        f2 = font(MONO_B, 40)
        d.text((1330, 760), "DO NOT SKIP", font=f2, fill=RED)
        d.text((1330, 810), "NUMBERS.", font=f2, fill=RED)
    if li >= 4:
        f3 = font(MONO_B, 40)
        d.text((1330, 880), "IT NOTICES.", font=f3, fill=RED)
    footer(d, ep["file_number"])


def scene_face_away(img, d, p, ts, seg, ep, li, lp):
    d.rectangle([0, 0, W, H], fill=BG)
    header(d, "RULE SIX", "When the elevator moves again, do not look at the display.")
    if li < 2:
        # figure facing away from panel (back to it)
        panel_x, panel_y = 1200, 300
        cycle = ["4", "F", "??", "13", "7", "Ø"]
        txt = cycle[int(ts * 2.3) % len(cycle)]
        panel(d, panel_x, panel_y, txt)
        # eye-line blocked: a bar
        red_x(d, panel_x + 130, panel_y + 75, size=110, width=20)
        figure(d, 700, 980, scale=1.3, facing=-1)
        f = font(MONO_B, 36)
        d.text((1180, 500), "PRESS NOTHING", font=f, fill=RED)
    else:
        # the correct hallway: lit, with extinguisher
        cx, cy = 760, 640
        x0, y0, x1, y1 = cx - 300, 300, cx + 300, 980
        d.rectangle([x0, y0, x1, y1], fill=(205, 198, 182))
        vx, vy = cx, 620
        for k in range(7):
            d.line([(x0 + k * 100, y1), (vx, vy)], fill=(170, 164, 150), width=3)
        extinguisher(d, cx + 160, 820, h=170)
        elevator(d, cx, cy, 600, 680, open_frac=1.0, inside=None)
        green_check(d, 1400, 560, size=110, width=24)
        f = font(MONO_B, 36)
        d.text((1200, 720), "EXIT ONLY HERE", font=f, fill=GREEN)
        if li >= 3:
            f2 = font(MONO, 30)
            d.text((1200, 790), "The extra floor has never", font=f2, fill=GREY)
            d.text((1200, 830), "bothered to install one.", font=f2, fill=GREY)
        figure(d, 1050, 1000, scale=1.0, pose="run")
    footer(d, ep["file_number"])


def scene_directory_13(img, d, p, ts, seg, ep, li, lp):
    d.rectangle([0, 0, W, H], fill=BG)
    header(d, "RULE SEVEN", "Check your floor directory again.")
    floors = [str(i) for i in range(13, 0, -1)]
    # "13" only appears when line 1 is spoken ("check your floor directory again")
    show_mis = li >= 1
    board_floors = floors if show_mis else floors[1:]
    # slow zoom: scale board up over segment by drawing on a temp layer
    zoom = 1.0 + 0.18 * ease(p)
    bw = int(520 * zoom)
    bx = int(1060 - (bw - 520) / 2)
    by = int(230 - (bw - 520) / 2 * 0.4)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    directory_board(ld, 1060, 230, board_floors, misaligned="13" if show_mis else None)
    layer = layer.resize((int(W * zoom), int(H * zoom)), Image.BILINEAR)
    ox = int((W - layer.width) * 0.62)  # zoom toward the board, which is right of centre
    oy = int((H - layer.height) * 0.4)
    img.paste(layer, (ox, oy), layer)
    figure(d, 640, 960, scale=1.3, pose="look_up")
    if li >= 3:
        x, y = 240, 330
        d.rounded_rectangle([x, y, x + 300, y + 190], radius=16, fill=INK)
        d.rounded_rectangle([x + 14, y + 14, x + 286, y + 176], radius=10, fill=BG)
        f = font(MONO_B, 96)
        old = "12"
        d.text((x + 150 - d.textlength(old, font=f) / 2, y + 40), old, font=f, fill=GREY)
        thick_line(d, [(x + 70, y + 90), (x + 230, y + 90)], 10, RED)
        f2 = font(MONO_B, 60)
        d.text((x + 200, y + 100), "13", font=f2, fill=RED)
    footer(d, ep["file_number"])


def scene_end_of_file(img, d, p, ts, seg, ep, li, lp):
    d.rectangle([0, 0, W, H], fill=DARK)
    f = font(MONO_B, 60)
    t1 = "END OF FILE"
    d.text((W / 2 - d.textlength(t1, font=f) / 2, H / 2 - 80), t1, font=f, fill=(225, 220, 205))
    if li >= 1:
        f2 = font(MONO, 34)
        t2 = "Further training materials are available."
        d.text((W / 2 - d.textlength(t2, font=f2) / 2, H / 2 + 20), t2, font=f2, fill=(150, 150, 140))
    f3 = font(MONO, 26)
    d.text((80, H - 70), f"STOP  ■   FILE {ep['file_number']}", font=f3, fill=(120, 120, 110))


SCENES = {
    "black_title": scene_black_title,
    "bureau_card": scene_bureau_card,
    "directory": scene_directory,
    "doors_open_13": scene_doors_open_13,
    "close_button": scene_close_button,
    "hallway_voice": scene_hallway_voice,
    "countdown": scene_countdown,
    "face_away": scene_face_away,
    "directory_13": scene_directory_13,
    "end_of_file": scene_end_of_file,
}


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------


def active_line(seg, t):
    for i, ln in enumerate(seg["lines"]):
        if ln["start"] <= t <= ln["end"] + 0.35:
            return i, min(1.0, (t - ln["start"]) / max(0.01, ln["end"] - ln["start"]))
    # between lines: report the last finished line so scene state persists
    last = -1
    for i, ln in enumerate(seg["lines"]):
        if t > ln["end"]:
            last = i
    return last, 1.0


def render_frame(t, timeline, ep):
    seg = next((s for s in timeline if s["start"] <= t < s["end"]), timeline[-1])
    # pre-roll before the first segment: black
    if t < timeline[0]["start"]:
        img = Image.new("RGB", (W, H), DARK)
        return img
    p = (t - seg["start"]) / max(0.01, seg["end"] - seg["start"])
    ts = t - seg["start"]
    li, lp = active_line(seg, t)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # hard cut to black for 1.6 s before a silence_before segment
    nxt_idx = timeline.index(seg) + 1
    if nxt_idx < len(timeline) and timeline[nxt_idx]["silence_before"] and t > timeline[nxt_idx]["start"] - 1.6:
        d.rectangle([0, 0, W, H], fill=DARK)
        return img
    SCENES[seg["scene"]](img, d, p, ts, seg, ep, li, lp)
    # caption of the line currently being spoken
    if li >= 0 and t <= seg["lines"][li]["end"] + 0.35:
        dark_scene = seg["scene"] in ("black_title", "end_of_file")
        if not dark_scene:
            caption(d, seg["lines"][li]["text"], color=BG, bg=INK)
    return img


def render_video(timeline, ep, total, out_path, fps, scale, hard_cut_times):
    w, h = int(W * scale), int(H * scale)
    nframes = int(math.ceil(total * fps))
    vf = ("noise=alls=9:allf=t+u,"
          "eq=contrast=1.06:saturation=0.82:gamma=0.98,"
          "vignette=PI/4.6,"
          "format=yuv420p")
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
           "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-maxrate", "9M", "-bufsize", "18M",
           "-r", str(fps), out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    last_pct = -1
    for i in range(nframes):
        t = i / fps
        img = render_frame(t, timeline, ep)
        if scale != 1.0:
            img = img.resize((w, h), Image.BILINEAR)
        proc.stdin.write(img.tobytes())
        pct = int(100 * i / nframes)
        if pct // 10 != last_pct // 10:
            print(f"  render {pct:3d}%", flush=True)
            last_pct = pct
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise SystemExit("ffmpeg video encode failed")


def render_thumbnail(ep, out_path):
    img = Image.new("RGB", (1280, 720), BG)
    d = ImageDraw.Draw(img)
    # scaled pictogram: open elevator, dark, 13
    d.rectangle([0, 0, 1280, 720], fill=BG)
    d.rectangle([40, 40, 1240, 680], outline=INK, width=8)
    # elevator
    x0, y0, x1, y1 = 120, 120, 620, 560
    d.rectangle([x0 - 18, y0 - 18, x1 + 18, y1 + 18], fill=INK)
    d.rectangle([x0, y0, x1, y1], fill=DARK)
    vx, vy = 370, 330
    for k in range(6):
        d.line([(x0 + k * 100, y1), (vx, vy)], fill=(45, 45, 45), width=3)
    figure(d, 400, 500, scale=0.5, fill=(110, 110, 105))
    figure(d, 720, 600, scale=0.95, fill=INK)
    panel(d, 860, 130, "13", w=200, h=120)
    red_x(d, 960, 380, size=70, width=16)
    # orange band with command
    d.rectangle([0, 560, 1280, 720], fill=ORANGE)
    f = font(SANS_B, 92)
    t = ep["thumbnail_command"]
    while d.textlength(t, font=f) > 1180:
        f = font(SANS_B, f.size - 4)
    d.text((640 - d.textlength(t, font=f) / 2, 585), t, font=f, fill=BG)
    f2 = font(MONO_B, 34)
    d.text((860, 470), f"FILE {ep['file_number']}", font=f2, fill=INK)
    img.save(out_path, quality=92)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode_dir")
    ap.add_argument("--voice", required=True, help="path to piper .onnx (config = same + .json)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()

    ep_path = os.path.join(args.episode_dir, "episode.json")
    with open(ep_path) as f:
        ep = json.load(f)
    out_dir = args.out or os.path.join(args.episode_dir, "build")
    os.makedirs(out_dir, exist_ok=True)
    lines_dir = os.path.join(out_dir, "lines")
    os.makedirs(lines_dir, exist_ok=True)

    cfg = args.voice + ".json"
    print("1/5 synthesizing narration…", flush=True)
    sr, narration, timeline, total = build_timeline(ep, args.voice, cfg, lines_dir)
    print(f"    total runtime {total:.1f}s ({int(total // 60)}:{int(total % 60):02d})")
    with open(os.path.join(out_dir, "timeline.json"), "w") as f:
        json.dump({"total": total, "segments": timeline}, f, indent=2)

    print("2/5 tape processing…", flush=True)
    raw = os.path.join(out_dir, "narration_raw.wav")
    fx = os.path.join(out_dir, "narration_fx.wav")
    write_wav(raw, sr, narration)
    tape_process(raw, fx)
    sr2, narr_fx = read_wav(fx)
    # asetrate shifts length slightly (pitch-down stretches); re-align to timeline length
    target = len(narration)
    if len(narr_fx) != target:
        idx = np.linspace(0, len(narr_fx) - 1, target)
        narr_fx = np.interp(idx, np.arange(len(narr_fx)), narr_fx).astype(np.float32)

    print("3/5 sound design…", flush=True)
    bed = design_bed(sr, total, timeline)
    n = min(len(bed), len(narr_fx))
    mix = narr_fx[:n] + bed[:n]
    peak = np.max(np.abs(mix)) or 1.0
    mix = mix / peak * 0.89
    master = os.path.join(out_dir, "master.wav")
    write_wav(master, sr, mix)

    print("4/5 rendering frames…", flush=True)
    fps = 12 if args.preview else FPS
    scale = 0.5 if args.preview else 1.0
    video_only = os.path.join(out_dir, "video_only.mp4")
    render_video(timeline, ep, total, video_only, fps, scale, [])

    print("5/5 muxing…", flush=True)
    final = os.path.join(out_dir, f"file{ep['file_number']}{'_preview' if args.preview else ''}.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video_only, "-i", master,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-shortest", "-movflags", "+faststart", final], check=True)
    render_thumbnail(ep, os.path.join(out_dir, "thumbnail.jpg"))
    os.remove(video_only)
    print(f"done → {final}")


if __name__ == "__main__":
    main()
