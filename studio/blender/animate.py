"""
Per-frame animation of characters and cameras.

Instead of relying on Blender's curve interpolation, each frame is computed
in Python (pose blends, walk cycle, blinks, breathing, head turns) and
written as a keyframe. That keeps the motion deterministic and easy to
describe in a shot file.

Actor spec (from the shot JSON):
    {"who": "ravi", "at": "bed_sit" | [x, y, z], "facing": 55,
     "pose": "sit+phone", "expr": "tired", "prop": "phone",
     "actions": [
        {"t": 1.0, "pose": "sit+sad"},                 # blend to a pose
        {"t": 1.2, "expr": "sad"},                     # change eyelids
        {"t": 0.5, "look": [yaw, pitch]},              # turn head (deg)
        {"t": 0.0, "walk_to": "door_spot", "dur": 2.5, "facing": 180},
        {"t": 2.0, "blink": true}
     ]}
"""
import math
import random

import character as ch

BLEND = 0.35  # seconds for a pose change
WALK_STEP = 0.36  # seconds per step


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def pose_rot(pose):
    rot = {}
    for p in pose.split("+"):
        rot.update(ch.POSES[p])
    return rot


def _resolve(at, anchors):
    if isinstance(at, str):
        return tuple(anchors[at])
    return tuple(at) + (0.0,) * (3 - len(at))


class ActorTrack:
    def __init__(self, spec, anchors, seed=0):
        self.spec = spec
        a = spec.get("actions", [])
        at = _resolve(spec["at"], anchors)
        self.base_xy = at[:2]
        self.seat = at[2] if "sit" in spec.get("pose", "stand") else 0.34
        self.floor_z = 0.0 if "sit" in spec.get("pose", "stand") else at[2]
        self.poses = [(0.0, spec.get("pose", "stand"))] + [(x["t"], x["pose"]) for x in a if "pose" in x]
        self.exprs = [(0.0, spec.get("expr", "open"))] + [(x["t"], x["expr"]) for x in a if "expr" in x]
        self.looks = [(0.0, (0.0, 0.0))] + [(x["t"], tuple(x["look"])) for x in a if "look" in x]
        self.facings = [(0.0, spec.get("facing", 0.0))] + [(x["t"], x["turn"]) for x in a if "turn" in x]
        self.walks = []
        pos = (*self.base_xy, self.floor_z)
        for x in sorted((x for x in a if "walk_to" in x), key=lambda x: x["t"]):
            dest = _resolve(x["walk_to"], anchors)
            self.walks.append((x["t"], x.get("dur", 2.0), pos, dest, x.get("facing")))
            pos = dest
        rng = random.Random(sum(map(ord, spec["who"])) * 7919 + seed)
        self.blinks, t = [], rng.uniform(0.6, 2.0)
        while t < 120:
            self.blinks.append(t)
            t += rng.uniform(2.2, 4.8)
        self.blinks += [x["t"] for x in a if x.get("blink")]
        self.phase = rng.uniform(0, 6.28)

    @staticmethod
    def _step(track, t):
        """Value of a step track at time t with a BLEND crossfade: (prev, cur, k)."""
        cur = track[0][1]
        prev, k = cur, 1.0
        for i, (ti, v) in enumerate(track):
            if t >= ti:
                prev = track[i - 1][1] if i else v
                cur = v
                k = ease((t - ti) / BLEND)
        return prev, cur, k

    def root(self, t):
        """(x, y, z, facing_deg, walking_amount, walk_phase)"""
        x, y = self.base_xy
        z = self.floor_z
        p0, p1, k = self._step(self.facings, t)
        facing = p0 + (p1 - p0) * k
        walking, phase = 0.0, 0.0
        for (t0, dur, a, b, f_end) in self.walks:
            if t < t0:
                break
            u = min(1.0, (t - t0) / dur)
            # constant speed with short ease at both ends
            g = ease(u) * 0.3 + u * 0.7
            x, y, z = (a[i] + (b[i] - a[i]) * g for i in range(3))
            dx, dy = b[0] - a[0], b[1] - a[1]
            if u < 1.0:
                walking = min(1.0, (t - t0) / 0.25, (t0 + dur - t) / 0.25)
                facing = math.degrees(math.atan2(dx, -dy))
                phase = (t - t0) / WALK_STEP
            elif f_end is not None:
                facing = f_end
        return x, y, z, facing, max(0.0, walking), phase

    def joints(self, t, walking, phase):
        p0, p1, k = self._step(self.poses, t)
        r0, r1 = pose_rot(p0), pose_rot(p1)
        rot = {}
        for name in ch.JOINTS:
            a = r0.get(name, (0, 0, 0))
            b = r1.get(name, (0, 0, 0))
            rot[name] = [a[i] + (b[i] - a[i]) * k for i in range(3)]
        sitting = "sit" in p1
        hips_z = (self.seat + ch.LIMB_R * 1.15) if sitting else ch.HIP_H
        if "sit" in p0 and not sitting:
            hips_z = self.seat + ch.LIMB_R * 1.15 + (ch.HIP_H - self.seat - ch.LIMB_R * 1.15) * k
        elif sitting and "sit" not in p0:
            hips_z = ch.HIP_H + (self.seat + ch.LIMB_R * 1.15 - ch.HIP_H) * k
        if walking > 0:
            s = math.sin(phase * math.pi)
            for name, amp in (("hipL", -24), ("hipR", 24), ("shoulderL", 18), ("shoulderR", -18)):
                rot[name][0] += amp * s * walking
            for name, sgn in (("kneeL", 1), ("kneeR", -1)):
                rot[name][0] += max(0.0, 32 * sgn * math.sin(phase * math.pi + 0.6)) * walking
            hips_z += 0.018 * abs(math.cos(phase * math.pi)) * walking
            rot["chest"][1] += 3 * s * walking
        # breathing and a little life in the head
        b = math.sin(t * 2 * math.pi / 3.6 + self.phase)
        rot["chest"][0] += 1.2 * b
        rot["neck"][0] += 0.8 * b
        l0, l1, kl = self._step(self.looks, t)
        yaw = l0[0] + (l1[0] - l0[0]) * kl
        pitch = l0[1] + (l1[1] - l0[1]) * kl
        rot["head"][2] += yaw + 2.0 * math.sin(t * 0.7 + self.phase)
        rot["head"][0] += pitch
        return rot, hips_z

    def lids(self, t):
        e0, e1, k = self._step(self.exprs, t)
        c0, tilt0 = ch.EXPRESSIONS[e0]
        c1, tilt1 = ch.EXPRESSIONS[e1]
        close = c0 + (c1 - c0) * k
        tilt = tilt0 + (tilt1 - tilt0) * k
        for bt in self.blinks:
            d = t - bt
            if 0 <= d < 0.16:
                b = 1 - abs(d - 0.08) / 0.08  # close and reopen
                close = close + (1 - close) * b
        return close, tilt


def key_actor(j, track, frame, fps):
    t = (frame - 1) / fps
    x, y, z, facing, walking, phase = track.root(t)
    root = j["root"]
    root.location = (x, y, z)
    root.rotation_euler = (0, 0, math.radians(facing))
    root.keyframe_insert("location", frame=frame)
    root.keyframe_insert("rotation_euler", frame=frame)
    rot, hips_z = track.joints(t, walking, phase)
    for name in ch.JOINTS:
        e = j[name]
        e.rotation_euler = tuple(math.radians(v) for v in rot[name])
        e.keyframe_insert("rotation_euler", frame=frame)
    j["hips"].location.z = hips_z
    j["hips"].keyframe_insert("location", frame=frame)
    ch.apply_lids(j, *track.lids(t), frame=frame)


def key_camera(cam, target, spec, anchors, actors, frame, fps, duration):
    """Camera spec: {"pos": [x,y,z], "look": [x,y,z] | actor name, "lens": 45,
    "move": "push" | "pull" | "drift" | "rise" | "static", "amount": 0.15,
    "to": [x,y,z] (optional end position), "shake": 0.004}"""
    t = (frame - 1) / fps
    u = ease(t / max(duration, 1e-3)) * 0.4 + (t / max(duration, 1e-3)) * 0.6
    p0 = list(spec["pos"])
    look = spec.get("look", [0, 0, 0.8])
    if isinstance(look, str):
        if look in actors:
            j, track = actors[look]
            x, y, z, *_ = track.root(t)
            seat = "sit" in track._step(track.poses, t)[1]
            look = [x, y, z + (0.85 if seat else 1.05)]
        else:
            ax = anchors[look]
            look = [ax[0], ax[1], ax[2] + 0.9]
    if "to" in spec:
        p1 = list(spec["to"])
    else:
        amt = spec.get("amount", 0.12)
        d = [look[i] - p0[i] for i in range(3)]
        n = math.sqrt(sum(v * v for v in d)) or 1
        d = [v / n for v in d]
        side = [d[1], -d[0], 0]
        move = spec.get("move", "push")
        if move == "push":
            p1 = [p0[i] + d[i] * amt * n for i in range(3)]
        elif move == "pull":
            p1 = [p0[i] - d[i] * amt * n for i in range(3)]
        elif move == "drift":
            p1 = [p0[i] + side[i] * amt * n for i in range(3)]
        elif move == "rise":
            p1 = [p0[0], p0[1], p0[2] + amt * n]
        else:
            p1 = p0
    pos = [p0[i] + (p1[i] - p0[i]) * u for i in range(3)]
    sh = spec.get("shake", 0.004)
    pos[0] += sh * math.sin(t * 1.3) + sh * 0.5 * math.sin(t * 3.1)
    pos[2] += sh * math.sin(t * 1.7 + 1.0)
    cam.location = pos
    target.location = look
    cam.keyframe_insert("location", frame=frame)
    target.keyframe_insert("location", frame=frame)
