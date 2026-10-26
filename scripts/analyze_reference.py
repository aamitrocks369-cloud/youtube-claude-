#!/usr/bin/env python3
"""
Frame-level analysis of a reference video (e.g. a competitor's episode) so its
animation style can be studied and reproduced.

Reports:
  - shot list (cut times, lengths), average shot length, cut histogram
  - per-shot motion profile: how much the picture moves per second
    (0 = static hold, higher = animated), split into "hold / slow / fast"
  - per-shot motion type guess: static, push/zoom, slide, flicker, full motion
  - dominant palette (k-means over sampled frames) + per-shot brightness
  - caption/text presence estimate (high-contrast horizontal structure in the lower third)
  - audio: loudness curve, spectral centroid (dull vs bright), silence gaps
  - a contact sheet with one frame per shot

Usage:
    python3 scripts/analyze_reference.py path/to/video.mp4 --out analysis_dir
"""
import argparse
import json
import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def probe(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height,r_frame_rate,duration:format=duration",
               "-of", "json", path]).stdout
    j = json.loads(out)
    s = j["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    fps = float(num) / float(den)
    dur = float(s.get("duration") or j["format"]["duration"])
    return int(s["width"]), int(s["height"]), fps, dur


def decode_small(path, fps=6, w=192, h=108):
    """Decode the whole video at low res as a uint8 array [n, h, w, 3]."""
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={fps},scale={w}:{h}",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    return np.frombuffer(raw, dtype=np.uint8).reshape(n, h, w, 3)


def detect_shots(frames, fps, thresh=0.02):
    """Cut = big jump in mean absolute difference, relative to local motion."""
    g = frames.astype(np.float32).mean(axis=3) / 255.0
    diff = np.abs(np.diff(g, axis=0)).mean(axis=(1, 2))  # per frame pair
    cuts = [0]
    k = max(2, int(round(fps * 0.4)))  # a real cut persists; a glitch flash reverts within ~0.4 s
    for i in range(1, len(diff)):
        local = np.median(diff[max(0, i - 6):i]) if i > 1 else 0
        before = g[max(0, i - 1)]
        after = g[min(len(g) - 1, i + 1 + k)]
        persists = np.abs(after - before).mean() > 0.5 * diff[i]
        if diff[i] > thresh and diff[i] > 6 * (local + 0.002) and persists:
            if (i + 1) - cuts[-1] >= int(fps * 0.4):
                cuts.append(i + 1)
    cuts.append(len(frames))
    shots = [(cuts[i] / fps, cuts[i + 1] / fps) for i in range(len(cuts) - 1)]
    return shots, diff


def motion_profile(frames, shots, fps):
    g = frames.astype(np.float32).mean(axis=3) / 255.0
    out = []
    for (a, b) in shots:
        i0, i1 = int(a * fps), int(b * fps)
        seg = g[i0:i1]
        if len(seg) < 2:
            out.append({"motion": 0.0, "type": "static", "flicker": 0.0, "zoom": 0.0, "slide": 0.0})
            continue
        d = np.abs(np.diff(seg, axis=0))
        per_frame = d.mean(axis=(1, 2))
        motion = float(per_frame.mean() * fps)  # mean abs change per second
        # flicker: alternating bright/dark whole-frame changes
        mean_lum = seg.mean(axis=(1, 2))
        flicker = float(np.abs(np.diff(mean_lum)).mean() * fps)
        # slide vs zoom: compare motion in centre vs edges and left vs right
        h, w = seg.shape[1:]
        c = d[:, h // 4:3 * h // 4, w // 4:3 * w // 4].mean()
        e = d.mean()
        zoom = float(e - c)  # edges move more than centre => zoom/push
        lr = float(abs(d[:, :, :w // 2].mean() - d[:, :, w // 2:].mean()))
        if motion < 0.015:
            t = "static hold"
        elif flicker > 0.5 * motion and flicker > 0.03:
            t = "flicker / strobe"
        elif motion < 0.12:
            t = "slow push/zoom" if zoom > 0.004 else ("slow slide" if lr > 0.01 else "subtle motion")
        else:
            t = "full motion"
        out.append({"motion": round(motion, 3), "type": t, "flicker": round(flicker, 3),
                    "zoom": round(zoom, 4), "slide": round(lr, 4)})
    return out


def palette(frames, k=6, samples=4000, iters=12):
    px = frames.reshape(-1, 3)
    rng = np.random.default_rng(1)
    px = px[rng.choice(len(px), min(samples * 20, len(px)), replace=False)].astype(np.float32)
    cent = px[rng.choice(len(px), k, replace=False)].copy()
    for _ in range(iters):
        dist = ((px[:, None, :] - cent[None, :, :]) ** 2).sum(axis=2)
        lab = dist.argmin(axis=1)
        for j in range(k):
            m = px[lab == j]
            if len(m):
                cent[j] = m.mean(axis=0)
    dist = ((px[:, None, :] - cent[None, :, :]) ** 2).sum(axis=2)
    lab = dist.argmin(axis=1)
    share = np.bincount(lab, minlength=k) / len(lab)
    order = np.argsort(-share)
    return [("#%02x%02x%02x" % tuple(int(v) for v in cent[j]), round(float(share[j]), 3)) for j in order]


def text_presence(frames):
    """Rough: lower-third rows with strong horizontal edge energy = captions."""
    g = frames.astype(np.float32).mean(axis=3)
    lower = g[:, int(g.shape[1] * 0.72):, :]
    edge = np.abs(np.diff(lower, axis=2)).mean(axis=(1, 2))
    upper = g[:, : int(g.shape[1] * 0.3), :]
    edge_u = np.abs(np.diff(upper, axis=2)).mean(axis=(1, 2))
    return float((edge > edge_u * 1.6 + 2).mean())


def audio_profile(path, out_dir):
    wav = os.path.join(out_dir, "audio.wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", wav])
    w = wave.open(wav)
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    sr = 16000
    win = sr // 4  # 250 ms
    n = len(x) // win
    rms = np.array([np.sqrt((x[i * win:(i + 1) * win] ** 2).mean()) for i in range(n)])
    db = 20 * np.log10(rms + 1e-6)
    # spectral centroid per window
    freqs = np.fft.rfftfreq(win, 1 / sr)
    cents = []
    for i in range(n):
        sp = np.abs(np.fft.rfft(x[i * win:(i + 1) * win] * np.hanning(win)))
        cents.append((sp * freqs).sum() / (sp.sum() + 1e-9))
    cents = np.array(cents)
    silence = db < (np.median(db) - 18)
    gaps = []
    i = 0
    while i < n:
        if silence[i]:
            j = i
            while j < n and silence[j]:
                j += 1
            if (j - i) * 0.25 >= 0.8:
                gaps.append((round(i * 0.25, 2), round(j * 0.25, 2)))
            i = j
        else:
            i += 1
    lo = ((np.abs(np.fft.rfft(x[: sr * 30]))[: int(200 * 30)]).sum())
    tot = np.abs(np.fft.rfft(x[: sr * 30])).sum() + 1e-9
    return {
        "loudness_db_median": round(float(np.median(db)), 1),
        "loudness_db_p95": round(float(np.percentile(db, 95)), 1),
        "spectral_centroid_hz_median": round(float(np.median(cents)), 0),
        "sub_200hz_energy_share_first30s": round(float(lo / tot), 3),
        "silence_gaps_over_0.8s": gaps[:40],
        "silence_gap_count": len(gaps),
    }


def contact_sheet(path, shots, motion, out_png, cols=5):
    thumbs = []
    for (a, b), m in zip(shots, motion):
        t = a + min(1.0, (b - a) * 0.4)
        png = out_png + f".tmp.png"
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1",
             "-vf", "scale=384:-1", png])
        im = Image.open(png).convert("RGB")
        thumbs.append((im, f"{a:5.1f}s  {b - a:4.1f}s  {m['type']}"))
    os.remove(out_png + ".tmp.png")
    if not thumbs:
        return
    w, h = thumbs[0][0].size
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * (h + 22)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype(FONT, 13)
    for i, (im, lab) in enumerate(thumbs):
        x, y = (i % cols) * w, (i // cols) * (h + 22)
        sheet.paste(im, (x, y + 22))
        d.text((x + 4, y + 4), lab, font=f, fill=(0, 0, 0))
    sheet.save(out_png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default=None)
    ap.add_argument("--fps", type=float, default=6.0)
    args = ap.parse_args()
    out = args.out or os.path.splitext(args.video)[0] + "_analysis"
    os.makedirs(out, exist_ok=True)

    W, H, src_fps, dur = probe(args.video)
    frames = decode_small(args.video, fps=args.fps)
    shots, diff = detect_shots(frames, args.fps)
    motion = motion_profile(frames, shots, args.fps)
    pal = palette(frames)
    txt = text_presence(frames)
    aud = audio_profile(args.video, out)

    lengths = np.array([b - a for a, b in shots])
    mot = np.array([m["motion"] for m in motion])
    types = {}
    for m in motion:
        types[m["type"]] = types.get(m["type"], 0) + 1
    report = {
        "file": os.path.basename(args.video),
        "resolution": f"{W}x{H}", "fps": round(src_fps, 2), "duration_s": round(dur, 1),
        "shots": len(shots),
        "avg_shot_len_s": round(float(lengths.mean()), 2),
        "median_shot_len_s": round(float(np.median(lengths)), 2),
        "longest_shot_s": round(float(lengths.max()), 2),
        "cuts_per_minute": round(len(shots) / (dur / 60), 1),
        "share_of_time_static": round(float(lengths[mot < 0.015].sum() / lengths.sum()), 3),
        "share_of_time_subtle_motion": round(float(lengths[(mot >= 0.015) & (mot < 0.12)].sum() / lengths.sum()), 3),
        "share_of_time_full_motion": round(float(lengths[mot >= 0.12].sum() / lengths.sum()), 3),
        "shot_types": types,
        "palette_hex_share": pal,
        "mean_brightness_0_255": round(float(frames.mean()), 1),
        "lower_third_text_share": round(txt, 3),
        "audio": aud,
        "shot_list": [{"start": round(a, 2), "end": round(b, 2), **m} for (a, b), m in zip(shots, motion)],
    }
    with open(os.path.join(out, "report.json"), "w") as f:
        json.dump(report, f, indent=2)
    contact_sheet(args.video, shots, motion, os.path.join(out, "shots.png"))

    print(f"{report['file']}  {report['resolution']} @ {report['fps']}fps  {dur:.0f}s")
    print(f"shots {len(shots)}  avg {report['avg_shot_len_s']}s  median {report['median_shot_len_s']}s  "
          f"cuts/min {report['cuts_per_minute']}")
    print(f"time static {report['share_of_time_static']:.0%}  subtle {report['share_of_time_subtle_motion']:.0%}  "
          f"full motion {report['share_of_time_full_motion']:.0%}")
    print("shot types", types)
    print("palette", pal[:5])
    print("lower-third text share", f"{txt:.0%}")
    print("audio", {k: v for k, v in aud.items() if k != 'silence_gaps_over_0.8s'})
    print("→", out)


if __name__ == "__main__":
    main()
