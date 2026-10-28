#!/usr/bin/env python3
"""
Story file → finished vertical Short.

    python3 studio/make_short.py studio/stories/001-sharma-uncle/story.json \
        --blender /path/to/blender --out build/001 [--fps 12] [--scale 0.5] [--samples 16]

Steps
  1. voice   every line with Kokoro (Hindi voices), timed per scene
  2. render  each 3D scene with Blender (cached: unchanged scenes are skipped)
  3. compose captions, clock stamps, phone chats, theme cards, crossfades
  4. sound   drone bed, footsteps, phone buzzes, stings, narration; master
  5. mux     MP4 (1080×1920) plus a thumbnail frame
"""
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import overlays as ov  # noqa: E402
import sound_v5 as snd  # noqa: E402

SR = 24000
W, H = ov.W, ov.H
LINE_GAP = 0.35
XFADE = 0.25


# ------------------------------------------------------------------ voice
class Voice:
    def __init__(self, model, voices, cache):
        from kokoro_onnx import Kokoro
        self.k = Kokoro(model, voices)
        self.cache = cache
        os.makedirs(cache, exist_ok=True)

    def say(self, text, voice, speed, lang="hi"):
        key = hashlib.sha1(f"{voice}|{speed}|{lang}|{text}".encode()).hexdigest()[:16]
        path = os.path.join(self.cache, key + ".npy")
        if os.path.exists(path):
            return np.load(path)
        a, sr = self.k.create(text, voice=voice, speed=speed, lang=lang)
        assert sr == SR, sr
        a = np.asarray(a, dtype=np.float32)
        # trim silence at both ends
        idx = np.where(np.abs(a) > 0.01)[0]
        if len(idx):
            a = a[max(0, idx[0] - 240): idx[-1] + 2400]
        np.save(path, a)
        return a


def plan_timeline(story, voice):
    """Adds start/dur to scenes and lines; returns total length."""
    t = 0.0
    speed = story.get("speed", 1.0)
    for sc in story["scenes"]:
        sc["start"] = t
        lt = sc.get("line_start", 0.35)
        for ln in sc.get("lines", []):
            v = story["voices"].get(ln["who"], story["voices"]["narrator"])
            ln["audio"] = voice.say(ln["text"], v, speed, story.get("language", "hi"))
            ln["start"] = lt
            ln["dur"] = len(ln["audio"]) / SR
            lt += ln["dur"] + LINE_GAP
        sc["dur"] = max(sc.get("min", 2.0), lt + sc.get("tail", 0.35))
        t += sc["dur"]
    return t


# ------------------------------------------------------------------ render
def render_scenes(story, args, out):
    cast = os.path.join(HERE, "cast", story.get("cast", "default") + ".json")
    rendered = {}
    for k, sc in enumerate(story["scenes"]):
        if "card" in sc:
            continue
        shot = {key: sc[key] for key in ("set", "mood", "actors", "camera") if key in sc}
        shot["duration"] = round(sc["dur"], 3)
        shot["aspect"] = story.get("aspect", "9:16")
        blob = json.dumps(shot, sort_keys=True) + f"|{args.fps}|{args.scale}|{args.samples}|{args.engine}"
        h = hashlib.sha1(blob.encode()).hexdigest()[:12]
        d = os.path.join(out, "frames", f"{k:02d}_{h}")
        n = max(1, round(shot["duration"] * args.fps))
        rendered[k] = (d, n)
        if os.path.isdir(d) and len([f for f in os.listdir(d) if f.endswith(".png")]) >= n:
            print(f"  scene {k}: cached", flush=True)
            continue
        sp = os.path.join(out, "shots", f"{k:02d}.json")
        os.makedirs(os.path.dirname(sp), exist_ok=True)
        json.dump(shot, open(sp, "w"), indent=1)
        print(f"  scene {k}: rendering {n} frames…", flush=True)
        r = subprocess.run([args.blender, "-b", "-P", os.path.join(HERE, "blender", "render_shot.py"), "--",
                            sp, cast, d, "--engine", args.engine, "--fps", str(args.fps),
                            "--scale", str(args.scale), "--samples", str(args.samples)],
                           capture_output=True, text=True)
        if "SHOT_DONE" not in r.stdout:
            print(r.stdout[-3000:], r.stderr[-3000:])
            raise SystemExit(f"scene {k} failed")
    return rendered


# ------------------------------------------------------------------ compose
def scene_at(story, t):
    for k, sc in enumerate(story["scenes"]):
        if sc["start"] <= t < sc["start"] + sc["dur"]:
            return k
    return len(story["scenes"]) - 1


def base_frame(story, rendered, k, tl, args, cache):
    sc = story["scenes"][k]
    if "card" in sc:
        img = Image.new("RGBA", (W, H), (4, 4, 6, 255))
        a = ov.ease(tl / 0.4)
        return ov.card(img, sc["card"]["text"], sc["card"].get("sub"), a)
    d, n = rendered[k]
    i = min(n, 1 + int(tl * args.fps))
    key = (k, i)
    if key not in cache:
        cache.clear()
        im = Image.open(os.path.join(d, f"f_{i:04d}.png")).convert("RGBA")
        cache[key] = im.resize((W, H), Image.BICUBIC) if im.size != (W, H) else im
    return cache[key].copy()


def decorate(story, k, tl, img):
    sc = story["scenes"][k]
    o = sc.get("overlay")
    if o:
        a = ov.ease((tl - o.get("from", 0)) / 0.3) * (1 - ov.ease((tl - o.get("to", 99)) / 0.3))
        if o["type"] == "clock":
            img = ov.clock(img, o["text"], a)
        elif o["type"] == "phone":
            img = ov.phone(img, o["spec"], tl - o.get("from", 0), a)
    y = 0.13 if o and o["type"] == "phone" else 0.74  # keep captions off the phone
    for ln in sc.get("lines", []):
        if ln["start"] - 0.05 <= tl <= ln["start"] + ln["dur"] + 0.25:
            a = ov.ease((tl - ln["start"] + 0.05) / 0.15) * (1 - ov.ease((tl - ln["start"] - ln["dur"]) / 0.25))
            img = ov.caption(img, ln["text"], ln["who"], a, y_frac=y)
    return img


def compose(story, rendered, total, args, out):
    path = os.path.join(out, "video_only.mp4")
    ofps = args.out_fps
    n = int(math.ceil(total * ofps))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(ofps),
           "-i", "-", "-vf", "noise=alls=4:allf=t+u,vignette=PI/4.5,format=yuv420p", "-c:v", "libx264",
           "-preset", "medium", "-crf", "19", path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    cache, cache_prev = {}, {}
    thumb = None
    for i in range(n):
        t = i / ofps
        k = scene_at(story, t)
        sc = story["scenes"][k]
        tl = t - sc["start"]
        img = decorate(story, k, tl, base_frame(story, rendered, k, tl, args, cache))
        if k > 0 and tl < XFADE:
            pk = k - 1
            ps = story["scenes"][pk]
            pt = t - ps["start"]
            prev = decorate(story, pk, pt, base_frame(story, rendered, pk, min(pt, ps["dur"] - 1e-3), args, cache_prev))
            img = Image.blend(prev, img, ov.ease(tl / XFADE))
        rgb = img.convert("RGB")
        if thumb is None and k == story.get("thumbnail_scene", 1) and tl > 1.0:
            thumb = rgb.copy()
        p.stdin.write(rgb.tobytes())
        if i % (ofps * 5) == 0:
            print(f"  compose {100 * i // n:3d}%", flush=True)
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit("ffmpeg failed")
    return path, thumb


# ------------------------------------------------------------------ sound
def footsteps_for(sc):
    hits = []
    for a in sc.get("actors", []):
        for act in a.get("actions", []):
            if "walk_to" in act:
                t, end = act["t"] + 0.1, act["t"] + act.get("dur", 2.0)
                while t < end:
                    hits.append(t)
                    t += 0.36
    return hits


def sound(story, total, out):
    n = int(total * SR) + SR
    voice = np.zeros(n, np.float32)
    sfx = np.zeros(n, np.float32)
    for sc in story["scenes"]:
        s0 = sc["start"]
        for ln in sc.get("lines", []):
            snd.place(voice, s0 + ln["start"], ln["audio"], 1.0)
        for t in footsteps_for(sc):
            snd.place(sfx, s0 + t, snd.sfx_footstep(), 0.5)
        for e in sc.get("sfx", []):
            if e["name"] == "buzz":
                snd.place(sfx, s0 + e["t"], snd.sfx_blip(900), 0.35)
                snd.place(sfx, s0 + e["t"] + 0.12, snd.sfx_blip(900), 0.35)
            elif e["name"] == "sting":
                snd.place(sfx, s0 + e["t"], snd.sfx_swell(2.2, (98, 103.8, 146.8)), 0.6)
                snd.place(sfx, s0 + e["t"], snd.sfx_heartbeat(), 0.8)
            elif e["name"] == "boom":
                snd.place(sfx, s0 + e["t"], snd.sfx_boom(), 0.9)
        if "card" in sc:
            snd.place(sfx, max(0, s0 - 0.6), snd.sfx_riser(0.7), 0.25)
    # drone bed: low detuned sines + filtered noise, ducked under the voice
    tt = np.arange(n) / SR
    drone = (np.sin(2 * np.pi * 55 * tt) * 0.5 + np.sin(2 * np.pi * 55.4 * tt) * 0.4
             + np.sin(2 * np.pi * 82.4 * tt) * 0.2) * 0.12
    drone += snd.lp(np.random.default_rng(3).standard_normal(n), 300) * 0.02
    env = np.convolve(np.abs(voice), np.ones(4800) / 4800, mode="same")
    duck = 1 - 0.55 * np.clip(env / (env.max() + 1e-9) * 4, 0, 1)
    mix = voice + drone * duck + sfx
    mix = mix[: int(total * SR)]
    rms = np.sqrt(np.mean(voice[voice != 0] ** 2)) if np.any(voice) else 0.1
    mix = mix * (0.12 / (rms + 1e-9))  # voice ≈ -18 dBFS RMS
    mix = np.tanh(mix * 1.2) / 1.2
    path = os.path.join(out, "mix.wav")
    import soundfile as sf
    sf.write(path, mix, SR)
    return path


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--blender", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=None)
    ap.add_argument("--voices", default=None)
    ap.add_argument("--engine", default="CYCLES")
    ap.add_argument("--fps", type=int, default=12, help="3D animation rate (12 = on twos)")
    ap.add_argument("--out-fps", type=int, default=24)
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--samples", type=int, default=16)
    a = ap.parse_args()
    story = json.load(open(a.story))
    os.makedirs(a.out, exist_ok=True)
    vdir = os.environ.get("STUDIO_VOICES", os.path.join(HERE, "models"))
    voice = Voice(a.model or os.path.join(vdir, "kokoro-v1.0.onnx"), a.voices or os.path.join(vdir, "voices-v1.0.bin"),
                  os.path.join(a.out, "tts_cache"))
    print("1/5 voice…", flush=True)
    total = plan_timeline(story, voice)
    print(f"    runtime {total:.1f}s, {len(story['scenes'])} scenes", flush=True)
    print("2/5 render…", flush=True)
    rendered = render_scenes(story, a, a.out)
    print("3/5 compose…", flush=True)
    vid, thumb = compose(story, rendered, total, a, a.out)
    print("4/5 sound…", flush=True)
    wav = sound(story, total, a.out)
    print("5/5 mux…", flush=True)
    name = os.path.basename(os.path.dirname(os.path.abspath(a.story)))
    final = os.path.join(a.out, f"{name}.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", vid, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-ar", "48000", "-shortest", "-movflags", "+faststart", final], check=True)
    if thumb is not None:
        thumb.save(os.path.join(a.out, "thumbnail.jpg"), quality=90)
    print("done →", final)


if __name__ == "__main__":
    main()
