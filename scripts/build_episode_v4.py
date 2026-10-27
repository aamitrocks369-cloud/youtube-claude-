#!/usr/bin/env python3
"""
v4: fixes the "editing and voiceover look bad" feedback on v3.

Voice
  - Piper "Ryan" (channel voice) or Kokoro; one synthesis per *sentence* so
    intonation flows; phrase boundaries inside a sentence are located by
    proportional duration and snapped to the nearest pause in the audio
  - light processing only (band-limit, gentle compression, small room)

Editing
  - consecutive beats in the same set are one continuous shot: the camera
    glides between framings instead of cutting
  - every other change is a short crossfade; hard glitch cuts only where the
    script flags them (no automatic glitches)
  - captions without boxes; the scene is framed to stay above the caption band
  - music pad + sound effects (rule-card thump, typing ticks, whoosh on scene
    changes) on top of the existing hiss/drone bed

Usage:
    python3 scripts/build_episode_v4.py episodes/001-elevator/episode_v3.json \
        --model voices/en-us-ryan-medium.onnx --out build/001v4 [--preview]
    (Kokoro instead: --engine kokoro --model voices/kokoro-v1.0.onnx
     --voices voices/voices-v1.0.bin --voice am_michael)
"""
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_episode as v1  # noqa: E402
import build_episode_v2 as v2  # noqa: E402
import build_episode_v3 as v3  # noqa: E402

W, H, FPS = v3.W, v3.H, v3.FPS
BLACK, WHITE = v3.BLACK, v3.WHITE
ease, fade = v3.ease, v3.fade
SETS = {"lobby", "elevator", "hallway", "office"}
XFADE = 0.2        # crossfade between shots
GLIDE = 0.7        # camera glide inside a continuous set shot
SR = 24000


# ----------------------------------------------------------------------------
# Voice
# ----------------------------------------------------------------------------


class Voice:
    """engine='piper' (default, the voice picked for the channel) or 'kokoro'."""

    def __init__(self, engine, model, voices, voice, speed, cache):
        self.engine, self.model = engine, model
        if engine == "kokoro":
            from kokoro_onnx import Kokoro
            self.k = Kokoro(model, voices)
        self.voice, self.speed, self.cache = voice, speed, cache
        os.makedirs(cache, exist_ok=True)

    def _piper(self, text, path_npy):
        wav = path_npy[:-4] + ".wav"
        wav24 = path_npy[:-4] + "_24k.wav"
        # same settings as the approved sample: Ryan medium, length scale 1.25, model defaults otherwise
        subprocess.run([sys.executable, "-m", "piper", "-m", self.model, "-c", self.model + ".json",
                        "--length-scale", str(self.speed), "-f", wav], input=text.encode(), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-ar", str(SR), "-ac", "1", wav24], check=True)
        _, a = v1.read_wav(wav24)
        os.remove(wav)
        os.remove(wav24)
        return a

    def say(self, text):
        key = hashlib.sha1(f"{self.engine}|{self.voice}|{self.speed}|{text}".encode()).hexdigest()[:16]
        path = os.path.join(self.cache, key + ".npy")
        if os.path.exists(path):
            return np.load(path)
        if self.engine == "piper":
            a = self._piper(text, path)
        else:
            lang = "en-gb" if self.voice.startswith("b") else "en-us"
            a, sr = self.k.create(text, voice=self.voice, speed=self.speed, lang=lang)
            assert sr == SR
        a = trim(np.asarray(a, dtype=np.float32))
        np.save(path, a)
        return a


def trim(x, thr=0.008):
    idx = np.where(np.abs(x) > thr)[0]
    if not len(idx):
        return x
    return x[max(0, idx[0] - int(0.03 * SR)): min(len(x), idx[-1] + int(0.15 * SR))]


def energy(x, hop=240):
    n = len(x) // hop
    return np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-9)


def split_points(sentence_audio, phrase_lens):
    """Boundaries between phrases inside one synthesized sentence."""
    total = len(sentence_audio) / SR
    if len(phrase_lens) == 1:
        return [0.0, total]
    s = sum(phrase_lens)
    cum = np.cumsum(phrase_lens)[:-1] / s * total
    e = energy(sentence_audio)
    hop = 240 / SR
    pts = [0.0]
    for c in cum:
        lo, hi = int(max(0, c - 0.3) / hop), int(min(total, c + 0.3) / hop)
        if hi > lo:
            j = lo + int(np.argmin(e[lo:hi]))
            pts.append(max(pts[-1] + 0.15, j * hop))
        else:
            pts.append(c)
    pts.append(total)
    return pts


def build_timeline(ep, voice):
    t = 0.0
    pieces, beats, segs = [], [], []
    for si, seg in enumerate(ep["segments"]):
        t += seg.get("pre_pause", 1.2)
        seg_start = t
        group = []
        bl = seg["beats"]
        for bi, bt in enumerate(bl):
            group.append(bt)
            txt = bt["text"].rstrip()
            end_sentence = txt.endswith((".", "?", "!")) or bi == len(bl) - 1
            if not end_sentence:
                continue
            sentence = " ".join(g["text"].strip() for g in group)
            audio = voice.say(sentence)
            lens = [len(voice.say(g["text"])) / SR for g in group] if len(group) > 1 else [1.0]
            pts = split_points(audio, lens)
            pieces.append((t, audio))
            for gi, g in enumerate(group):
                beats.append({"seg": si, "start": t + pts[gi], "end": t + pts[gi + 1], **g})
            t += len(audio) / SR
            last = bi == len(bl) - 1
            t += 0.0 if last else (1.1 if txt.endswith("...") else 0.75)
            group = []
        t += seg.get("post_pause", 0.0)
        segs.append({"id": seg["id"], "scene": seg["id"], "rule": seg.get("rule"), "start": seg_start, "end": t,
                     "silence_before": seg.get("silence_before", False), "rule_name": seg.get("rule_name", "")})
    for i in range(len(segs) - 1):
        segs[i]["end"] = segs[i + 1]["start"]
    total = t + 1.0
    segs[-1]["end"] = total
    track = np.zeros(int(total * SR) + SR, dtype=np.float32)
    for st, x in pieces:
        a = int(st * SR)
        track[a:a + len(x)] += x
    return track, beats, segs, total


def voice_fx(in_wav, out_wav, room=False):
    af = ("highpass=f=80,"
          "acompressor=threshold=-20dB:ratio=2:attack=10:release=200:makeup=2dB"
          + (",aecho=0.8:0.5:28|46:0.18|0.12" if room else ""))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", in_wav, "-af", af, "-ar", str(SR), out_wav], check=True)


# ----------------------------------------------------------------------------
# Music + SFX
# ----------------------------------------------------------------------------


def lowpass(x, a):
    from scipy.signal import lfilter
    return lfilter([a], [1, a - 1], x).astype(np.float32)


def music_pad(total, segs):
    """Slow minor pad: Am - F - Dm - E, 8 s per chord, soft and filtered."""
    n = int(total * SR) + SR
    t = np.arange(n) / SR
    chords = [[220.0, 261.6, 329.6], [174.6, 220.0, 261.6], [146.8, 174.6, 220.0], [164.8, 207.7, 246.9]]
    out = np.zeros(n, dtype=np.float32)
    seglen = 8.0
    for ci in range(int(total / seglen) + 2):
        ch = chords[ci % 4]
        a, b = int(ci * seglen * SR), int(min(n, (ci + 1) * seglen * SR + SR))
        if a >= n:
            break
        tt = t[a:b]
        env = np.minimum(1, (tt - ci * seglen) / 2.0) * np.minimum(1, ((ci + 1) * seglen + 1 - tt) / 2.0)
        env = np.clip(env, 0, 1)
        for f in ch:
            for det in (-0.6, 0.6):
                out[a:b] += (np.sin(2 * np.pi * (f / 2 + det) * tt) * 0.5
                             + np.sin(2 * np.pi * (f + det) * tt) * 0.25).astype(np.float32) * env
    out = lowpass(out, 0.04)
    out /= np.max(np.abs(out)) + 1e-9
    # duck under rule 7 silence and end
    for s in segs:
        if s["silence_before"]:
            a = int((s["start"] - 2.4) * SR)
            b = int((s["start"] + 4.0) * SR)
            out[a:b] *= np.linspace(1, 0, b - a) ** 0.3 if False else 0.0
    fadeout = int(3 * SR)
    out[-fadeout:] *= np.linspace(1, 0, fadeout)
    return out * 0.06


def sfx(total, plan):
    n = int(total * SR) + SR
    out = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(5)

    def add(at, x):
        a = int(at * SR)
        if 0 <= a < n:
            out[a:a + len(x)] += x[: n - a]

    tt = np.arange(int(0.35 * SR)) / SR
    thump = (np.sin(2 * np.pi * 52 * tt) * np.exp(-tt * 9)).astype(np.float32) * 0.5
    tick_t = np.arange(int(0.025 * SR)) / SR
    tick = (rng.standard_normal(len(tick_t)) * np.exp(-tick_t * 260)).astype(np.float32) * 0.12
    wl = int(0.45 * SR)
    whoosh = lowpass(rng.standard_normal(wl).astype(np.float32), 0.08)
    whoosh *= np.sin(np.linspace(0, np.pi, wl)) ** 2 * 0.18
    for i, sh in enumerate(plan.shots):
        if sh["beat"] == "rule_card":
            add(sh["start"] + 0.2, thump)
            name = sh["rule_name"]
            for c in range(len(name)):
                add(sh["start"] + 0.5 + 0.8 * c / max(1, len(name)), tick)
        elif i > 0 and not sh["continuous"] and not sh["glitch"]:
            add(sh["start"] - 0.2, whoosh)
    return out


# ----------------------------------------------------------------------------
# Plan + rendering
# ----------------------------------------------------------------------------


class Plan:
    def __init__(self, ep, beats, segs, total):
        self.ep, self.segs, self.total = ep, segs, total
        lead = 0.1
        self.shots = []
        for k, b in enumerate(beats):
            start = max(0.0, b["start"] - lead)
            end = beats[k + 1]["start"] - lead if k + 1 < len(beats) else total
            seg = ep["segments"][b["seg"]]
            prev = self.shots[-1] if self.shots else None
            continuous = bool(prev and b["beat"] in SETS and prev["beat"] == b["beat"]
                              and prev["seg"] == b["seg"] and not b.get("glitch"))
            self.shots.append({"start": start, "end": max(start + 0.4, end), "voice_start": b["start"],
                               "voice_end": b["end"], "text": b["text"], "beat": b["beat"], "seg": b["seg"],
                               "args": b.get("args", {}), "glitch": b.get("glitch", False),
                               "continuous": continuous, "rule": seg.get("rule"),
                               "rule_name": seg.get("rule_name", "")})
        self.blackouts = [(s["start"] - 2.4, s["start"] - 0.1) for s in segs if s["silence_before"]]


PLAN = None


def init_worker(plan):
    global PLAN
    PLAN = plan


def cam_of(sh, tl):
    dur = sh["end"] - sh["start"]
    cx, cy, z = sh["args"].get("cam", [960, 540, 1.0])
    return cx, cy, z * (1.0 + 0.05 * ease(tl / max(dur, 0.5)))


def scene_layer(sh, tl, cam):
    layer = Image.new("RGB", (W, H), BLACK)
    ld = ImageDraw.Draw(layer)
    ctx = {"rule": sh["rule"], "rule_name": sh["rule_name"]}
    v3.BEATS[sh["beat"]](ld, layer, tl, sh["end"] - sh["start"], sh["args"], ctx)
    cx, cy, z = cam
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
        layer.paste(small, (int(W / 2 - W * fit / 2), 46))
    layer = v3.add_glow(layer)
    if sh["args"].get("red"):
        layer = v2.red_takeover(layer)
    return layer


def draw_caption(d, text, k):
    f = v3.mont(700, 44)
    text = text.upper()
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if v3.spaced_width(d, trial, f, 2) <= 1300:
            cur = trial
        else:
            lines.append(cur)
            cur = w_
    lines.append(cur)
    y = 975 - 54 * len(lines)
    for ln in lines:
        # soft dark edge instead of a box, so text survives over any art
        for ox, oy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)):
            v3.spaced_text(d, (W / 2 + ox, y + oy), ln, f, BLACK, 2, anchor="m")
        v3.spaced_text(d, (W / 2, y), ln, f, fade(WHITE, k), 2, anchor="m")
        y += 54


def render_frame(i, fps, scale):
    plan = PLAN
    t = i / fps
    out = Image.new("RGB", (W, H), BLACK)
    if t >= plan.shots[0]["start"] and not any(a <= t < b for a, b in plan.blackouts):
        k = max(j for j, s in enumerate(plan.shots) if s["start"] <= t) if t >= plan.shots[0]["start"] else 0
        sh = plan.shots[k]
        tl = t - sh["start"]
        cam = cam_of(sh, tl)
        prev = plan.shots[k - 1] if k > 0 else None
        if sh["continuous"] and prev and tl < GLIDE:
            pc = cam_of(prev, prev["end"] - prev["start"])
            g = ease(tl / GLIDE)
            cam = tuple(pc[j] + (cam[j] - pc[j]) * g for j in range(3))
        layer = scene_layer(sh, tl, cam)
        in_blackout_tail = prev is not None and any(abs(sh["start"] - b) < 0.3 for _, b in plan.blackouts)
        if prev and not sh["glitch"] and tl < XFADE and not in_blackout_tail:
            pt = prev["end"] - prev["start"] + tl
            prev_layer = scene_layer(prev, pt, cam_of(prev, pt) if not sh["continuous"] else cam)
            layer = Image.blend(prev_layer, layer, ease(tl / XFADE))
        out = layer
        d = ImageDraw.Draw(out)
        v2.draw_hud(d, plan.ep, t, sh["rule"])
        if sh["beat"] != "end_card" and sh["voice_start"] - 0.05 <= t <= sh["voice_end"] + 0.25:
            draw_caption(d, sh["text"], ease((t - sh["voice_start"] + 0.05) / 0.12))
        if sh["glitch"] and tl < 0.15:
            out = v2.glitch(out, i)
    if scale != 1.0:
        out = out.resize((int(W * scale), int(H * scale)), Image.BILINEAR)
    return out.tobytes()


def _render(a):
    return render_frame(*a)


def render_video(plan, path, fps, scale, workers):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode_json")
    ap.add_argument("--engine", choices=["piper", "kokoro"], default="piper")
    ap.add_argument("--model", required=True, help="piper .onnx or kokoro .onnx")
    ap.add_argument("--voices", default=None, help="kokoro voices .bin")
    ap.add_argument("--voice", default="am_michael", help="kokoro voice name")
    ap.add_argument("--speed", type=float, default=None,
                    help="piper length scale (default 1.25) or kokoro speed (default 0.9)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    args = ap.parse_args()
    ep = json.load(open(args.episode_json))
    os.makedirs(args.out, exist_ok=True)

    speed = args.speed if args.speed is not None else (1.25 if args.engine == "piper" else 0.9)
    print(f"1/5 narration ({args.engine}, per sentence)…", flush=True)
    voice = Voice(args.engine, args.model, args.voices, args.voice, speed, os.path.join(args.out, "tts_cache"))
    narr, beats, segs, total = build_timeline(ep, voice)
    print(f"    {len(beats)} beats, runtime {total:.1f}s ({int(total // 60)}:{int(total % 60):02d})", flush=True)
    json.dump({"total": total, "beats": beats, "segments": segs}, open(os.path.join(args.out, "timeline.json"), "w"), indent=1)
    plan = Plan(ep, beats, segs, total)

    print("2/5 voice processing…", flush=True)
    raw, fx = os.path.join(args.out, "narr_raw.wav"), os.path.join(args.out, "narr_fx.wav")
    v1.write_wav(raw, SR, narr)
    voice_fx(raw, fx)
    _, nf = v1.read_wav(fx)
    nf = nf[: len(narr)] if len(nf) >= len(narr) else np.pad(nf, (0, len(narr) - len(nf)))

    print("3/5 bed, music, sfx, master…", flush=True)
    bed = v1.design_bed(SR, total, segs)
    pad = music_pad(total, segs)
    fxs = sfx(total, plan)
    n = min(len(bed), len(nf), len(pad), len(fxs))
    mix = nf[:n] + bed[:n] * 0.55 + pad[:n] + fxs[:n]
    rng = np.random.default_rng(11)
    for sh in plan.shots:
        if sh["glitch"]:
            a, L = int(sh["start"] * SR), int(0.15 * SR)
            if 0 <= a < n - L:
                mix[a:a + L] += rng.standard_normal(L).astype(np.float32) * 0.035
    mix = v3.master(mix, SR)
    master = os.path.join(args.out, "master.wav")
    v1.write_wav(master, SR, mix)
    if args.audio_only:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", master, "-b:a", "192k",
                        os.path.join(args.out, "master.mp3")], check=True)
        print("audio only → master.mp3")
        return

    print("4/5 frames…", flush=True)
    fps = 12 if args.preview else FPS
    scale = 0.5 if args.preview else 1.0
    vid = os.path.join(args.out, "video_only.mp4")
    render_video(plan, vid, fps, scale, args.workers)

    print("5/5 mux…", flush=True)
    final = os.path.join(args.out, f"file{ep['file_number']}_v4{'_preview' if args.preview else ''}.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", vid, "-i", master, "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", final], check=True)
    os.remove(vid)
    v3.render_thumbnail(ep, os.path.join(args.out, "thumbnail_v4.jpg"))
    print("done →", final)


if __name__ == "__main__":
    main()
