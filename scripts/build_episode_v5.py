#!/usr/bin/env python3
"""
v5: music, sound effects and transitions.

Builds on v4 (sentence-level narration, continuous camera, crossfades) and adds:
  - a procedural horror-ambient score that intensifies rule by rule
    (drone, bells in the pauses, heartbeat from rule 4, rule-7 swell),
    ducked under the narration
  - sound effects driven by the same timeline as the animation
    (footsteps, elevator ding/doors, blips, clicks, badge beeps, scratch,
    shutter, heartbeat, glitch, tape stop…)
  - transition grammar:
      glide  – same set, camera moves (v4)
      dip    – into every rule card / new section: fade to black with a VHS
               tracking roll, riser + boom
      whip   – between different sets: horizontal whip-pan with motion blur
      glitch – flagged key lines: hard glitch cut
      xfade  – everything else

Usage:
    python3 scripts/build_episode_v5.py episodes/002-badge/episode.json \
        --model voices/en-us-ryan-medium.onnx --out build/002v5 [--preview]
"""
import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_episode as v1  # noqa: E402
import build_episode_v2 as v2  # noqa: E402
import build_episode_v3 as v3  # noqa: E402
import build_episode_v4 as v4  # noqa: E402
import sound_v5 as snd  # noqa: E402

W, H = v4.W, v4.H
BLACK = v4.BLACK
ease = v4.ease
SR = v4.SR
SETS = v4.SETS
DIP = 0.28
WHIP = 0.3
XFADE = 0.22
GLIDE = 0.7


class Plan(v4.Plan):
    def __init__(self, ep, beats, segs, total):
        super().__init__(ep, beats, segs, total)
        for k, sh in enumerate(self.shots):
            prev = self.shots[k - 1] if k else None
            if prev is None:
                sh["transition"] = "none"
            elif sh["continuous"]:
                sh["transition"] = "glide"
            elif sh["glitch"]:
                sh["transition"] = "glitch"
            elif sh["beat"] == "rule_card" or sh["seg"] != prev["seg"]:
                sh["transition"] = "dip"
            elif sh["beat"] in SETS and prev["beat"] in SETS:
                sh["transition"] = "whip"
            else:
                sh["transition"] = "xfade"
        # a dip needs the outgoing shot to fade out too
        for k in range(len(self.shots) - 1):
            self.shots[k]["dip_out"] = self.shots[k + 1]["transition"] == "dip"


PLAN = None


def init_worker(plan):
    global PLAN
    PLAN = plan


def tracking_roll(img, amount, seed):
    """VHS tracking error: a band of displaced, noisy rows rolling down."""
    if amount <= 0:
        return img
    a = np.asarray(img).copy()
    rng = np.random.default_rng(seed)
    band_y = int((seed * 37) % H)
    band_h = int(60 + 140 * amount)
    for y in range(band_y, min(H, band_y + band_h), 2):
        a[y] = np.roll(a[y], int(rng.integers(-40, 40) * amount), axis=0)
    noise = (rng.random((band_h // 2 + 1, W, 1)) * 255 * 0.35 * amount).astype(np.uint8)
    ys = slice(band_y, min(H, band_y + band_h), 2)
    rows = a[ys]
    a[ys] = np.clip(rows.astype(np.int16) + noise[: rows.shape[0]], 0, 255).astype(np.uint8)
    return Image.fromarray(a)


def hblur(img, amount):
    if amount <= 0.02:
        return img
    f = max(2, int(2 + 30 * amount))
    small = img.resize((max(8, W // f), H), Image.BILINEAR)
    return small.resize((W, H), Image.BILINEAR)


def shot_image(sh, tl, prev=None):
    cam = v4.cam_of(sh, tl)
    if sh["transition"] == "glide" and prev is not None and tl < GLIDE:
        pc = v4.cam_of(prev, prev["end"] - prev["start"])
        g = ease(tl / GLIDE)
        cam = tuple(pc[j] + (cam[j] - pc[j]) * g for j in range(3))
    return v4.scene_layer(sh, tl, cam)


def render_frame(i, fps, scale):
    plan = PLAN
    t = i / fps
    out = Image.new("RGB", (W, H), BLACK)
    if t >= plan.shots[0]["start"] and not any(a <= t < b for a, b in plan.blackouts):
        k = max(j for j, s in enumerate(plan.shots) if s["start"] <= t)
        sh = plan.shots[k]
        prev = plan.shots[k - 1] if k else None
        tl = t - sh["start"]
        img = shot_image(sh, tl, prev)
        tr = sh["transition"]
        blackout_edge = any(abs(sh["start"] - b) < 0.3 for _, b in plan.blackouts)
        if prev is not None and not blackout_edge:
            pt = prev["end"] - prev["start"] + tl
            if tr == "glide" and tl < 0.12:
                img = Image.blend(shot_image(prev, pt), img, ease(tl / 0.12))
            elif tr == "xfade" and tl < XFADE:
                img = Image.blend(shot_image(prev, pt), img, ease(tl / XFADE))
            elif tr == "whip" and tl < WHIP:
                p = ease(tl / WHIP)
                blur = math.sin(math.pi * tl / WHIP)
                a_img = hblur(shot_image(prev, pt), blur)
                b_img = hblur(img, blur)
                canvas = Image.new("RGB", (W, H), BLACK)
                off = int(W * p)
                canvas.paste(a_img, (-off, 0))
                canvas.paste(b_img, (W - off, 0))
                img = canvas
            elif tr == "dip" and tl < DIP:
                img = Image.blend(Image.new("RGB", (W, H), BLACK), img, ease(tl / DIP))
                img = tracking_roll(img, 1 - tl / DIP, i)
        if sh.get("dip_out") and t > sh["end"] - DIP:
            q = (t - (sh["end"] - DIP)) / DIP
            img = Image.blend(img, Image.new("RGB", (W, H), BLACK), ease(q))
            img = tracking_roll(img, q, i)
        out = img
        d = ImageDraw.Draw(out)
        v2.draw_hud(d, plan.ep, t, sh["rule"])
        if sh["beat"] != "end_card" and sh["voice_start"] - 0.05 <= t <= sh["voice_end"] + 0.25:
            v4.draw_caption(d, sh["text"], ease((t - sh["voice_start"] + 0.05) / 0.12))
        if sh["glitch"] and tl < 0.15:
            out = v2.glitch(out, i)
    if scale != 1.0:
        out = out.resize((int(W * scale), int(H * scale)), Image.BILINEAR)
    return out.tobytes()


def _render(a):
    return render_frame(*a)


def render_video(plan, path, fps, scale, workers):
    from multiprocessing import Pool
    w, h = int(W * scale), int(H * scale)
    n = int(math.ceil(plan.total * fps))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
           "-i", "-", "-vf", "noise=alls=5:allf=t+u,vignette=PI/5,format=yuv420p", "-c:v", "libx264",
           "-preset", "slow", "-crf", "20", "-maxrate", "10M", "-bufsize", "20M", "-r", str(fps), path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(workers, initializer=init_worker, initargs=(plan,)) as pool:
        for k, buf in enumerate(pool.imap(_render, ((i, fps, scale) for i in range(n)), chunksize=8)):
            proc.stdin.write(buf)
            if k % (fps * 30) == 0:
                print(f"  render {100 * k // n:3d}%", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")


def build_audio(ep, voice, out_dir):
    narr, beats, segs, total = v4.build_timeline(ep, voice)
    plan = Plan(ep, beats, segs, total)
    raw, fx = os.path.join(out_dir, "narr_raw.wav"), os.path.join(out_dir, "narr_fx.wav")
    v1.write_wav(raw, SR, narr)
    v4.voice_fx(raw, fx)
    _, nf = v1.read_wav(fx)
    nf = nf[: len(narr)] if len(nf) >= len(narr) else np.pad(nf, (0, len(narr) - len(nf)))
    venv = snd.voice_envelope(nf)
    bed = v1.design_bed(SR, total, segs) * 0.22
    music = snd.score(total, segs, venv)
    fxs = snd.effects(total, plan)
    n = min(len(nf), len(bed), len(music), len(fxs))
    stems = {"voice": nf[:n], "bed": bed[:n], "music": music[:n] * 0.55, "sfx": fxs[:n] * 0.8}
    mix = sum(stems.values())
    mix = v3.master(mix, SR)
    master = os.path.join(out_dir, "master.wav")
    v1.write_wav(master, SR, mix)
    for name, x in stems.items():
        v1.write_wav(os.path.join(out_dir, f"stem_{name}.wav"), SR, np.clip(x / (np.max(np.abs(x)) + 1e-9) * 0.9, -1, 1))
    json.dump({"total": total, "beats": beats, "segments": segs}, open(os.path.join(out_dir, "timeline.json"), "w"), indent=1)
    return plan, master, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode_json")
    ap.add_argument("--engine", choices=["piper", "kokoro"], default="piper")
    ap.add_argument("--model", required=True)
    ap.add_argument("--voices", default=None)
    ap.add_argument("--voice", default="am_michael")
    ap.add_argument("--speed", type=float, default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    args = ap.parse_args()
    ep = json.load(open(args.episode_json))
    os.makedirs(args.out, exist_ok=True)
    speed = args.speed if args.speed is not None else (1.25 if args.engine == "piper" else 0.9)
    print("1/4 narration + score + sfx…", flush=True)
    voice = v4.Voice(args.engine, args.model, args.voices, args.voice, speed, os.path.join(args.out, "tts_cache"))
    plan, master, total = build_audio(ep, voice, args.out)
    counts = {}
    for sh in plan.shots:
        counts[sh["transition"]] = counts.get(sh["transition"], 0) + 1
    print(f"    runtime {total:.1f}s, transitions {counts}", flush=True)
    if args.audio_only:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", master, "-b:a", "192k",
                        os.path.join(args.out, "master.mp3")], check=True)
        print("audio only → master.mp3")
        return
    print("2/4 frames…", flush=True)
    fps = 12 if args.preview else v4.FPS
    scale = 0.5 if args.preview else 1.0
    vid = os.path.join(args.out, "video_only.mp4")
    render_video(plan, vid, fps, scale, args.workers)
    print("3/4 mux…", flush=True)
    final = os.path.join(args.out, f"file{ep['file_number']}_v5{'_preview' if args.preview else ''}.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", vid, "-i", master, "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", final], check=True)
    os.remove(vid)
    print("4/4 thumbnail…", flush=True)
    v3.render_thumbnail(ep, os.path.join(args.out, f"thumbnail_v5.jpg"))
    print("done →", final)


if __name__ == "__main__":
    main()
