"""
Procedural score + sound effects for the Bureau files (v5).

Everything is synthesized with numpy/scipy so the pipeline stays offline and
royalty-free. All functions work at SR (24 kHz) and return float32 arrays.
"""
import math

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 24000
RNG = np.random.default_rng(1729)


# ----------------------------------------------------------------------------
# building blocks
# ----------------------------------------------------------------------------


def t_axis(dur):
    return np.arange(int(dur * SR)) / SR


def bp(x, lo, hi, order=2):
    sos = butter(order, [lo, hi], btype="band", fs=SR, output="sos")
    return sosfilt(sos, x).astype(np.float32)


def lp(x, f, order=2):
    sos = butter(order, f, btype="low", fs=SR, output="sos")
    return sosfilt(sos, x).astype(np.float32)


def hp(x, f, order=2):
    sos = butter(order, f, btype="high", fs=SR, output="sos")
    return sosfilt(sos, x).astype(np.float32)


def noise(dur):
    return RNG.standard_normal(int(dur * SR)).astype(np.float32)


def env_ad(n, attack, decay_tau):
    t = np.arange(n) / SR
    a = np.minimum(1.0, t / max(attack, 1e-4))
    return (a * np.exp(-np.maximum(0, t - attack) / decay_tau)).astype(np.float32)


def tone(f, dur, decay=0.3, attack=0.004, partials=((1, 1.0),), sweep=0.0):
    t = t_axis(dur)
    out = np.zeros_like(t, dtype=np.float32)
    for mult, amp in partials:
        ph = 2 * np.pi * f * mult * (t + 0.5 * sweep * t * t)
        out += (amp * np.sin(ph)).astype(np.float32)
    return out * env_ad(len(t), attack, decay)


def reverb(x, wet=0.25, size=1.6):
    n = int(size * SR)
    ir = noise(size) * np.exp(-np.arange(n) / SR / (size / 4.5)).astype(np.float32)
    ir = lp(ir, 5000)
    ir /= np.sqrt((ir ** 2).sum()) + 1e-9
    w = fftconvolve(x, ir)[: len(x)].astype(np.float32)
    return x * (1 - wet) + w * wet * 1.4


def place(buf, at, x, gain=1.0):
    a = int(at * SR)
    if a < 0:
        x = x[-a:]
        a = 0
    if a >= len(buf) or len(x) == 0:
        return
    m = min(len(x), len(buf) - a)
    buf[a:a + m] += x[:m] * gain


# ----------------------------------------------------------------------------
# sound effects
# ----------------------------------------------------------------------------


def sfx_footstep():
    x = bp(noise(0.09), 120, 1800) * env_ad(int(0.09 * SR), 0.002, 0.018)
    thud = tone(85, 0.09, 0.025)
    return (x * 0.5 + thud * 0.6).astype(np.float32)


def sfx_ding():
    p = ((1, 1.0), (2.0, 0.35), (3.01, 0.15))
    hi = tone(1318.5, 1.6, 0.6, partials=p)
    lo = np.pad(tone(1046.5, 1.4, 0.6, partials=p), (int(0.18 * SR), 0))
    lo = np.pad(lo, (0, max(0, len(hi) - len(lo))))[: len(hi)]
    return (hi + 0.8 * lo) * 0.35


def sfx_door_slide(dur=1.6):
    x = bp(noise(dur), 200, 900)
    t = t_axis(dur)
    e = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.5
    hum = np.sin(2 * np.pi * 70 * t) * 0.3
    return ((x * 0.25 + hum * 0.4) * e).astype(np.float32)


def sfx_blip(f=1800):
    return tone(f, 0.08, 0.02, partials=((1, 1.0), (3, 0.2))) * 0.35


def sfx_click():
    x = hp(noise(0.03), 2000) * env_ad(int(0.03 * SR), 0.0005, 0.004)
    return (x * 0.9 + tone(2400, 0.03, 0.006) * 0.3).astype(np.float32)


def sfx_boom():
    t = t_axis(1.6)
    f = 70 * np.exp(-t * 1.2) + 32
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.2)
    rumble = lp(noise(1.6), 140) * np.exp(-t * 2.5) * 0.6
    return ((x + rumble) * 0.7).astype(np.float32)


def sfx_riser(dur=1.3):
    t = t_axis(dur)
    x = bp(noise(dur), 300, 4000) * (t / dur) ** 2.2
    f = 200 + 900 * (t / dur) ** 2
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * (t / dur) ** 3 * 0.25
    return ((x * 0.35 + s) * 0.6).astype(np.float32)


def sfx_whoosh(dur=0.42):
    t = t_axis(dur)
    x = noise(dur)
    lo = bp(x, 300, 1200)
    hi = bp(x, 1200, 5000)
    m = np.clip(t / dur, 0, 1)
    out = lo * (1 - m) + hi * m
    return (out * np.sin(np.pi * m) ** 2 * 0.45).astype(np.float32)


def sfx_beep_ok():
    return np.concatenate([tone(1760, 0.09, 0.05), np.zeros(int(0.03 * SR), np.float32), tone(2349, 0.12, 0.06)]) * 0.35


def sfx_buzz_no():
    t = t_axis(0.35)
    sq = np.sign(np.sin(2 * np.pi * 180 * t)) * np.exp(-t * 3)
    return (lp(sq.astype(np.float32), 2500) * 0.18).astype(np.float32)


def sfx_warble(dur=1.2):
    t = t_axis(dur)
    f = 900 + 380 * np.sin(2 * np.pi * 7.3 * t) + 120 * np.sin(2 * np.pi * 0.9 * t)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / dur)
    return (x * 0.16).astype(np.float32)


def sfx_scratch(dur=0.9):
    t = t_axis(dur)
    x = bp(noise(dur), 2500, 7000)
    mod = 0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 9 * t + np.sin(2 * np.pi * 2.1 * t)))
    return (x * mod * 0.12).astype(np.float32)


def sfx_thud():
    return (tone(90, 0.25, 0.06) + lp(noise(0.25), 400) * env_ad(int(0.25 * SR), 0.002, 0.04) * 0.6) * 0.6


def sfx_tick():
    return (hp(noise(0.02), 3000) * env_ad(int(0.02 * SR), 0.0005, 0.003) * 0.35).astype(np.float32)


def sfx_shutter():
    a = sfx_click()
    b = np.pad(sfx_click() * 0.7, (int(0.07 * SR), 0))
    n = max(len(a), len(b))
    return (np.pad(a, (0, n - len(a))) + np.pad(b, (0, n - len(b)))) * 0.9


def sfx_heartbeat():
    one = tone(55, 0.18, 0.05, partials=((1, 1.0), (2, 0.3)))
    two = np.pad(one * 0.7, (int(0.22 * SR), 0))
    n = len(two)
    return (np.pad(one, (0, n - len(one))) + two) * 0.55


def sfx_glitch(dur=0.18):
    t = t_axis(dur)
    x = noise(dur)
    gate = (np.sin(2 * np.pi * 47 * t) > 0).astype(np.float32)
    beep = np.sin(2 * np.pi * np.where(t < dur / 2, 1400, 700) * t)
    crushed = np.round(x * 4) / 4
    return ((crushed * gate * 0.25 + beep * 0.12) * np.sin(np.pi * t / dur) ** 0.3).astype(np.float32)


def sfx_tape_stop(dur=1.4):
    t = t_axis(dur)
    f = 220 * (1 - t / dur) ** 2 + 20
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.5 * np.sin(2 * np.pi * np.cumsum(f * 1.5) / SR)
    return (lp(x.astype(np.float32), 1500) * (1 - t / dur) * 0.35).astype(np.float32)


def sfx_swell(dur=2.5, freqs=(110, 116.5, 164.8)):
    t = t_axis(dur)
    x = sum(np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 2.01 * t) for f in freqs)
    e = np.minimum(1, t / (dur * 0.7)) * np.minimum(1, (dur - t) / 0.4)
    return (lp(x.astype(np.float32), 900) * e * 0.12).astype(np.float32)


def sfx_murmur(dur=1.2):
    """Muffled, unintelligible voice through a wall."""
    t = t_axis(dur)
    f0 = 140 + 30 * np.sin(2 * np.pi * 3.1 * t)
    src = np.sign(np.sin(2 * np.pi * np.cumsum(f0) / SR)).astype(np.float32)
    syll = (0.5 + 0.5 * np.sin(2 * np.pi * 4.2 * t)) ** 2
    return (lp(bp(src, 250, 1100), 700) * syll * np.sin(np.pi * t / dur) * 0.25).astype(np.float32)


def sfx_rustle(dur=0.5):
    x = bp(noise(dur), 1500, 6000) * (0.4 + 0.6 * np.abs(np.sin(2 * np.pi * 6 * t_axis(dur))))
    return (x * env_ad(len(x), 0.05, 0.2) * 0.12).astype(np.float32)


def sfx_hum(dur):
    t = t_axis(dur)
    x = np.sin(2 * np.pi * 120 * t) * 0.6 + np.sin(2 * np.pi * 240 * t) * 0.3 + hp(noise(dur), 4000) * 0.15
    e = np.minimum(1, t / 0.2) * np.minimum(1, (dur - t) / 0.2)
    return (x * e * 0.07).astype(np.float32)


def sfx_pop():
    return tone(620, 0.07, 0.03, sweep=-2000) * 0.25


# ----------------------------------------------------------------------------
# score
# ----------------------------------------------------------------------------

BELL_NOTES = [440.0, 523.25, 587.33, 659.25, 783.99, 880.0]  # A minor pentatonic


def bell(f):
    p = ((1, 1.0), (2.76, 0.35), (5.4, 0.12), (8.9, 0.05))
    return tone(f, 3.2, 0.9, attack=0.002, partials=p) * 0.22


def intensity_curve(total, segs):
    n = int(total * SR) + SR
    curve = np.zeros(n, dtype=np.float32)
    for s in segs:
        r = s.get("rule")
        level = 0.35 if not r else 0.4 + 0.08 * r
        if s["id"] == "outro":
            level = 0.3
        a, b = int(s["start"] * SR), int(s["end"] * SR)
        curve[a:b] = level
    k = int(1.5 * SR)
    return np.convolve(curve, np.ones(k) / k, mode="same").astype(np.float32)


def score(total, segs, voice_env):
    n = int(total * SR) + SR
    t = np.arange(n) / SR
    inten = intensity_curve(total, segs)[:n]
    out = np.zeros(n, dtype=np.float32)

    # drone: A1 + E2, harmonics breathing slowly
    for f0, amp in ((55.0, 1.0), (82.41, 0.55)):
        for h in range(1, 7):
            w = (1.0 / h) * (0.55 + 0.45 * np.sin(2 * np.pi * (0.021 * h) * t + h))
            out += (amp * w * np.sin(2 * np.pi * f0 * h * t + h)).astype(np.float32)
    out = lp(out, 700) * (0.35 + 0.65 * inten)
    out *= 0.08

    # bells only in the gaps between narration, denser as intensity rises
    bells = np.zeros(n, dtype=np.float32)
    at = 2.0
    while at < total - 3:
        i = int(at * SR)
        quiet = voice_env[i:i + int(0.6 * SR)].mean() < 0.15 if i < len(voice_env) else True
        if quiet:
            place(bells, at, bell(BELL_NOTES[int(RNG.integers(0, len(BELL_NOTES)))]))
            at += float(RNG.uniform(3.0, 5.5)) * (1.4 - inten[i])
        else:
            at += 0.4
    out += reverb(bells, wet=0.45, size=2.4) * 0.9

    # heartbeat pulse from rule 4 onward
    pulse = np.zeros(n, dtype=np.float32)
    hb = sfx_heartbeat()
    for s in segs:
        if s.get("rule") and s["rule"] >= 4:
            bpm = 58 + 4 * (s["rule"] - 4)
            k = s["start"] + 0.5
            while k < s["end"] - 0.5:
                place(pulse, k, hb, 0.35 + 0.08 * (s["rule"] - 4))
                k += 60.0 / bpm
    out += pulse

    # rule 7: hard silence before, then a dissonant swell
    for s in segs:
        if s["silence_before"]:
            a, b = int((s["start"] - 2.4) * SR), int(s["start"] * SR)
            out[a:b] = 0.0
            place(out, s["start"] + 0.2, sfx_swell(6.0, (110, 116.5, 155.6, 164.8)), 1.0)

    # duck under narration (6–8 dB)
    duck = 1.0 - 0.6 * np.clip(voice_env[:n] if len(voice_env) >= n else np.pad(voice_env, (0, n - len(voice_env))), 0, 1)
    out *= duck
    fade = int(3 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out


def voice_envelope(narr):
    a = np.abs(narr)
    win = int(0.05 * SR)
    e = np.convolve(a, np.ones(win) / win, mode="same")
    e = e / (np.percentile(e, 99) + 1e-9)
    # slow release so music does not pump between words
    rel = int(0.35 * SR)
    e = np.maximum.accumulate(e[::-1].reshape(-1)[::-1]) if False else e
    k = np.ones(rel) / rel
    return np.clip(np.convolve(e, k, mode="same") * 1.6, 0, 1).astype(np.float32)


# ----------------------------------------------------------------------------
# timeline-driven sound effects
# ----------------------------------------------------------------------------


def effects(total, plan):
    n = int(total * SR) + SR
    fx = np.zeros(n, dtype=np.float32)
    step = sfx_footstep()

    def steps(t0, dur, period, gain=0.5):
        k = t0
        while k < t0 + dur:
            place(fx, k, step, gain * float(RNG.uniform(0.8, 1.1)))
            k += period

    for i, sh in enumerate(plan.shots):
        s, a, b = sh["start"], sh["args"], sh["beat"]
        dur = sh["end"] - s
        tr = sh.get("transition")
        # transitions
        if tr == "dip":
            place(fx, s - 1.25, sfx_riser(1.3), 0.8)
            place(fx, s + 0.05, sfx_boom(), 0.9)
        elif tr == "whip":
            place(fx, s - 0.12, sfx_whoosh(0.42), 0.9)
        if sh["glitch"]:
            place(fx, s, sfx_glitch(), 0.9)
        # actors
        you = a.get("you")
        if you == "walk_in":
            steps(s + 0.05, 1.55, math.pi / 9.5)
        elif you == "run":
            steps(s, dur, math.pi / 15, 0.6)
        elif you in ("step_back",):
            place(fx, s + 0.15, step, 0.6)
        if a.get("stranger") == "exit":
            steps(s + 0.4, 2.2, math.pi / 8, 0.35)
        # per beat
        if b == "rule_card":
            name = sh["rule_name"]
            for c in range(len(name)):
                place(fx, s + 0.5 + 0.8 * c / max(1, len(name)), sfx_tick(), 0.9)
        elif b == "elevator":
            doors = a.get("doors")
            if doors in ("open", "opening"):
                place(fx, s + (0.0 if doors == "open" else 0.2), sfx_ding(), 0.8)
                place(fx, s + (0.05 if doors == "open" else 0.3), sfx_door_slide(1.2 if doors == "open" else 2.0), 0.9)
            elif doors in ("closing", "closing_slow"):
                place(fx, s + 0.2, sfx_door_slide(1.6), 0.8)
            if a.get("moving"):
                place(fx, s, sfx_hum(dur), 1.0)
            if a.get("beyond") == "voice":
                place(fx, s + 0.3, sfx_murmur(min(1.6, dur)), 0.9)
        elif b == "display_close":
            every = a.get("every", 1.0)
            for j in range(len(a.get("seq", []))):
                place(fx, s + j * every, sfx_blip(1500 if j == 0 else 1900), 0.8)
        elif b == "button":
            mode = a.get("mode")
            if mode == "press":
                place(fx, s + min(1.4, dur * 0.5), sfx_click(), 1.0)
                place(fx, s + min(1.4, dur * 0.5), sfx_boom(), 0.35)
            elif mode == "wire":
                place(fx, s + 0.3, sfx_hum(min(2.0, dur)), 1.0)
        elif b == "badge_reader":
            light = a.get("light")
            if light == "green" or (a.get("tap") and light == "green"):
                place(fx, s + 0.8, sfx_beep_ok(), 0.9)
            elif light == "red":
                place(fx, s + (0.8 if a.get("tap") else 0.2), sfx_buzz_no(), 0.9)
            elif light == "third":
                place(fx, s + 0.3, sfx_warble(min(1.6, dur)), 1.0)
        elif b == "card_write":
            place(fx, s + (0.7 if a.get("rewrite") else 0.1), sfx_scratch(0.9), 1.0)
            if a.get("rewrite"):
                place(fx, s + 0.2, sfx_scratch(0.4), 0.8)
        elif b == "wallet":
            place(fx, s + 0.9, sfx_rustle(0.4), 1.0)
            place(fx, s + 2.0, sfx_thud(), 0.7)
        elif b in ("stat",):
            if not a.get("hold"):
                for j in range(12):
                    place(fx, s + j * 0.08, sfx_tick(), 0.8)
        elif b == "evidence":
            if not a.get("zoom"):
                place(fx, s, sfx_shutter(), 0.9)
            place(fx, s, sfx_hum(min(2.5, dur)), 0.6)
        elif b == "officer":
            place(fx, s + 0.3, sfx_rustle(0.5), 0.8)
        elif b == "face":
            if a.get("expr") in ("worried", "wide") or a.get("sweat"):
                hb = sfx_heartbeat()
                k = s + 0.1
                while k < s + dur - 0.3:
                    place(fx, k, hb, 0.7)
                    k += 0.85
        elif b == "eye":
            place(fx, s, sfx_swell(2.0, (98, 103.8, 146.8)), 1.2)
        elif b == "counter":
            if not a.get("silent"):
                k = s
                while k < s + dur:
                    place(fx, k, sfx_tick(), 0.9)
                    k += 1 / 1.4
        elif b == "counter_loop":
            for j in range(4):
                place(fx, s + j * 0.55, sfx_blip(1200 + 200 * j), 0.7)
        elif b in ("number_row", "seven_rules", "people_row"):
            for j in range(9):
                place(fx, s + 0.1 + j * 0.07, sfx_pop(), 0.6)
        elif b == "building_floors":
            for j in range(13):
                place(fx, s + j * 0.09, tone(220 * 2 ** (j / 12), 0.12, 0.05) * 0.18, 1.0)
            steps(s + 1.2, dur - 1.2, math.pi / 15, 0.4)
        elif b == "org_chart":
            steps(s + 1.3, 1.3, math.pi / 9.5, 0.45)
            place(fx, s + 2.7, sfx_thud(), 0.6)
        elif b == "rules_shuffled":
            place(fx, s + 0.3, sfx_whoosh(0.5), 0.6)
        elif b == "voice_bubble":
            place(fx, s + 0.2, sfx_murmur(min(1.8, dur)), 1.0)
        elif b == "hallway" and a.get("door_appear"):
            place(fx, s, sfx_swell(1.6, (73.4, 77.8)), 1.4)
        elif b == "hallway" and a.get("door_opening"):
            place(fx, s + 0.6, sfx_door_slide(1.4), 0.6)
        elif b == "end_card" and not a.get("sub"):
            place(fx, s, sfx_tape_stop(), 1.0)
    return reverb(fx, wet=0.18, size=1.0)
