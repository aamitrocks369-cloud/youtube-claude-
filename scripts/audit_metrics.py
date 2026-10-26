#!/usr/bin/env python3
"""
Extended style metrics for comparing our renders against reference videos.
All videos are decoded at the same size and rate so numbers are comparable.

    python3 scripts/audit_metrics.py out.json video1.mp4 video2.mp4 ...
"""
import json
import subprocess
import sys

import numpy as np
from scipy import ndimage

FPS = 6
W, H = 256, 144


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={FPS},scale={W}:{H}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)


def audio(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    win = 800  # 50 ms
    n = len(x) // win
    db = 20 * np.log10(np.sqrt((x[: n * win].reshape(n, win) ** 2).mean(axis=1)) + 1e-6)
    floor = np.percentile(db, 10)
    voiced = db > floor + 12
    # pauses: runs of unvoiced >= 0.4 s
    pauses, run = [], 0
    for v in voiced:
        if not v:
            run += 1
        else:
            if run * 0.05 >= 0.4:
                pauses.append(run * 0.05)
            run = 0
    mins = n * 0.05 / 60
    return {
        "loudness_median_db": round(float(np.median(db[voiced])) if voiced.any() else -99, 1),
        "dynamic_range_db": round(float(np.percentile(db, 95) - np.percentile(db, 10)), 1),
        "voiced_share": round(float(voiced.mean()), 3),
        "pauses_per_min": round(len(pauses) / mins, 1),
        "median_pause_s": round(float(np.median(pauses)) if pauses else 0, 2),
        "long_pauses_over_1_5s_per_min": round(sum(p >= 1.5 for p in pauses) / mins, 2),
    }


def metrics(path):
    f = decode(path)
    rgb = f.astype(np.int16)
    lum = rgb.mean(axis=3)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    ink = lum > 40
    bright = lum > 150
    halo = (lum > 25) & (lum <= 110)
    red = (r > 150) & (g < 90) & (b < 90)
    yellow = (r > 170) & (g > 130) & (b < 110)
    green = (g > 140) & (r < 130) & (b < 150)
    # motion between consecutive frames, excluding cuts
    d = np.abs(np.diff(lum, axis=0))
    md = d.mean(axis=(1, 2))
    cut = md > np.median(md) * 8 + 2
    moving_px = (d > 12).mean(axis=(1, 2))
    mv = moving_px[~cut]
    # elements per frame (connected bright blobs), sampled every 1 s
    comps = []
    for i in range(0, len(f), FPS):
        lab, n = ndimage.label(ink[i])
        sizes = np.bincount(lab.ravel())[1:]
        comps.append(int((sizes > 14).sum()))
    # spatial spread of ink: share of a 4x4 grid with any ink
    grid = ink[:, : H // 4 * 4, : W // 4 * 4].reshape(len(f), 4, H // 4, 4, W // 4).any(axis=(2, 4)).mean(axis=(1, 2))
    # lower-third caption band activity vs scene area
    return {
        "duration_s": round(len(f) / FPS, 1),
        "ink_coverage": round(float(ink.mean()), 3),
        "bright_coverage": round(float(bright.mean()), 3),
        "glow_halo_ratio": round(float(halo.sum() / max(1, bright.sum())), 2),
        "red_share": round(float(red.mean()), 4),
        "yellow_share": round(float(yellow.mean()), 4),
        "green_share": round(float(green.mean()), 4),
        "frames_with_red": round(float((red.mean(axis=(1, 2)) > 0.002).mean()), 3),
        "frames_moving": round(float((mv > 0.002).mean()), 3),
        "moving_area_median": round(float(np.median(mv)), 4),
        "moving_area_p90": round(float(np.percentile(mv, 90)), 4),
        "elements_per_frame_median": float(np.median(comps)),
        "screen_spread": round(float(np.median(grid)), 3),
        "audio": audio(path),
    }


if __name__ == "__main__":
    out = {}
    for p in sys.argv[2:]:
        print("…", p, flush=True)
        out[p] = metrics(p)
    json.dump(out, open(sys.argv[1], "w"), indent=2)
