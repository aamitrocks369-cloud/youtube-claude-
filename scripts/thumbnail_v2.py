#!/usr/bin/env python3
"""
Thumbnail generator v2: the layout that wins in this niche, in our own style.

  left  : huge two-colour command ("DO NOT" / "STEP OUT") + hand-drawn arrow
  right : two framed panels, NORMAL | WRONG, the second with the anomaly
          (red spiral eyes, too-wide grin)
  mascot: "you" wears a yellow lanyard + badge in every thumbnail

    python3 scripts/thumbnail_v2.py episodes/001-elevator/episode_v3.json out_dir
"""
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_episode_v2 as v2  # noqa: E402
import build_episode_v3 as v3  # noqa: E402

W, H = 1920, 1080
BLACK, WHITE, RED, YELLOW, AMBER = (8, 8, 8), (245, 245, 240), (230, 40, 36), (250, 200, 40), (255, 170, 60)
mont = v2.mont
thick = v3.thick
LANYARD = (250, 200, 40)


# ---------------------------------------------------------------------------
# characters
# ---------------------------------------------------------------------------


def mascot_head(d, cx, cy, r, expr="neutral", lanyard=True):
    """'You': white round head, dot eyes, yellow lanyard + badge."""
    # shoulders
    d.chord([cx - r * 1.5, cy + r * 0.85, cx + r * 1.5, cy + r * 3.4], 180, 360, fill=BLACK)
    d.chord([cx - r * 1.42, cy + r * 0.93, cx + r * 1.42, cy + r * 3.3], 180, 360, fill=WHITE)
    if lanyard:
        thick(d, [(cx - r * 0.55, cy + r * 1.0), (cx, cy + r * 1.75)], max(6, int(r * 0.12)), LANYARD)
        thick(d, [(cx + r * 0.55, cy + r * 1.0), (cx, cy + r * 1.75)], max(6, int(r * 0.12)), LANYARD)
        d.rounded_rectangle([cx - r * 0.3, cy + r * 1.7, cx + r * 0.3, cy + r * 2.15], radius=r * 0.06,
                            fill=WHITE, outline=BLACK, width=max(3, int(r * 0.05)))
        d.rectangle([cx - r * 0.3, cy + r * 1.7, cx + r * 0.3, cy + r * 1.82], fill=LANYARD)
    o = max(4, int(r * 0.07))
    d.ellipse([cx - r - o, cy - r - o, cx + r + o, cy + r + o], fill=BLACK)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
    er = r * (0.16 if expr == "wide" else 0.1)
    for sx in (-1, 1):
        ex, ey = cx + sx * r * 0.36, cy - r * 0.05
        d.ellipse([ex - er, ey - er, ex + er, ey + er], fill=BLACK)
    if expr == "wide":
        d.ellipse([cx - r * 0.12, cy + r * 0.38, cx + r * 0.12, cy + r * 0.62], fill=BLACK)
        # sweat
        sx, sy = cx + r * 0.85, cy - r * 0.55
        d.ellipse([sx - r * 0.09, sy, sx + r * 0.09, sy + r * 0.22], fill=(150, 200, 255))
        d.polygon([(sx - r * 0.08, sy + r * 0.06), (sx + r * 0.08, sy + r * 0.06), (sx, sy - r * 0.14)], fill=(150, 200, 255))
    else:
        d.line([(cx - r * 0.18, cy + r * 0.45), (cx + r * 0.18, cy + r * 0.45)], fill=BLACK, width=max(3, int(r * 0.06)))


def spiral_eye(d, cx, cy, r):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE, outline=BLACK, width=max(3, int(r * 0.12)))
    for k, col in enumerate([RED, WHITE, RED, WHITE, RED]):
        rr = r * (0.85 - k * 0.16)
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col)
    d.ellipse([cx - r * 0.12, cy - r * 0.12, cx + r * 0.12, cy + r * 0.12], fill=BLACK)
    # veins
    for a in range(0, 360, 45):
        ang = math.radians(a + 20)
        d.line([(cx + math.cos(ang) * r * 0.9, cy + math.sin(ang) * r * 0.9),
                (cx + math.cos(ang) * r * 0.7, cy + math.sin(ang) * r * 0.7)], fill=RED, width=max(1, int(r * 0.05)))


def grin_head(d, cx, cy, r, tint=WHITE):
    """The anomaly: same head, red spiral eyes, grin far too wide."""
    d.chord([cx - r * 1.5, cy + r * 0.85, cx + r * 1.5, cy + r * 3.4], 180, 360, fill=BLACK)
    d.chord([cx - r * 1.42, cy + r * 0.93, cx + r * 1.42, cy + r * 3.3], 180, 360, fill=tint)
    o = max(4, int(r * 0.07))
    d.ellipse([cx - r - o, cy - r - o, cx + r + o, cy + r + o], fill=BLACK)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tint)
    for sx in (-1, 1):
        spiral_eye(d, cx + sx * r * 0.38, cy - r * 0.18, r * 0.27)
    # grin: wide black crescent with teeth
    box = [cx - r * 0.78, cy - r * 0.15, cx + r * 0.78, cy + r * 0.82]
    d.chord(box, 10, 170, fill=BLACK)
    inner = [cx - r * 0.66, cy - r * 0.05, cx + r * 0.66, cy + r * 0.68]
    d.chord(inner, 15, 165, fill=WHITE)
    for k in range(-5, 6):
        x = cx + k * r * 0.11
        d.line([(x, cy + r * 0.15), (x, cy + r * 0.62)], fill=BLACK, width=max(2, int(r * 0.035)))
    d.line([(cx - r * 0.66, cy + r * 0.36), (cx + r * 0.66, cy + r * 0.36)], fill=BLACK, width=max(2, int(r * 0.04)))
    # cheek lines
    for sx in (-1, 1):
        d.arc([cx + sx * r * 0.7 - r * 0.15, cy + r * 0.05, cx + sx * r * 0.7 + r * 0.15, cy + r * 0.45],
              270 if sx > 0 else 90, 90 if sx > 0 else 270, fill=BLACK, width=max(2, int(r * 0.04)))


# ---------------------------------------------------------------------------
# panel scenes (drawn into a panel-sized image)
# ---------------------------------------------------------------------------


def scene(kind, w, h, label=None):
    img = Image.new("RGB", (w, h), (18, 18, 22))
    d = ImageDraw.Draw(img)
    cx = w / 2
    if kind in ("elevator_normal", "elevator_wrong"):
        # doors + display
        d.rectangle([w * 0.12, h * 0.22, w * 0.88, h], outline=WHITE, width=10)
        wrong = kind == "elevator_wrong"
        if wrong:
            d.rectangle([w * 0.14, h * 0.24, w * 0.86, h], fill=(4, 4, 4))
            grin_head(d, cx, h * 0.55, w * 0.2)
        else:
            d.rectangle([w * 0.14, h * 0.24, w * 0.5 - 3, h], fill=(196, 196, 190))
            d.rectangle([w * 0.5 + 3, h * 0.24, w * 0.86, h], fill=(196, 196, 190))
            mascot_head(d, cx, h * 0.62, w * 0.17, "neutral")
        d.rounded_rectangle([cx - w * 0.17, h * 0.04, cx + w * 0.17, h * 0.17], radius=10, outline=WHITE, width=6)
        f = mont(800, int(h * 0.1))
        txt = "13" if wrong else "12"
        d.text((cx - d.textlength(txt, font=f) / 2, h * 0.045), txt, font=f, fill=RED if wrong else AMBER)
    elif kind in ("badge_normal", "badge_wrong"):
        d.rounded_rectangle([w * 0.1, h * 0.12, w * 0.9, h * 0.92], radius=30, fill=WHITE)
        d.rectangle([w * 0.1, h * 0.2, w * 0.9, h * 0.32], fill=(40, 40, 40))
        v2.spaced_text(d, (w * 0.16, h * 0.225), "OAB · STAFF", mont(800, int(h * 0.06)), WHITE, 6)
        d.line([(cx - w * 0.1, 0), (cx - w * 0.04, h * 0.13)], fill=LANYARD, width=12)
        d.line([(cx + w * 0.1, 0), (cx + w * 0.04, h * 0.13)], fill=LANYARD, width=12)
        d.rectangle([w * 0.18, h * 0.38, w * 0.82, h * 0.86], fill=(225, 225, 220), outline=BLACK, width=6)
        if kind == "badge_wrong":
            grin_head(d, cx, h * 0.58, w * 0.19)
        else:
            mascot_head(d, cx, h * 0.58, w * 0.17, "neutral", lanyard=False)
        d.rectangle([w * 0.18, h * 0.86, w * 0.82, h * 0.92], fill=WHITE)
    elif kind in ("door_normal", "door_wrong"):
        d.rectangle([0, h * 0.9, w, h * 0.92], fill=WHITE)
        d.rectangle([w * 0.25, h * 0.15, w * 0.75, h * 0.9], outline=WHITE, width=10)
        if kind == "door_wrong":
            d.rectangle([w * 0.27, h * 0.17, w * 0.73, h * 0.9], fill=(2, 2, 2))
            d.rectangle([w * 0.27, h * 0.17, w * 0.38, h * 0.9], fill=(40, 40, 38))
            grin_head(d, w * 0.56, h * 0.42, w * 0.13)
        else:
            d.rectangle([w * 0.27, h * 0.17, w * 0.73, h * 0.9], fill=WHITE)
            d.rectangle([w * 0.33, h * 0.24, w * 0.67, h * 0.5], outline=BLACK, width=6)
            d.rectangle([w * 0.33, h * 0.56, w * 0.67, h * 0.84], outline=BLACK, width=6)
            d.ellipse([w * 0.62, h * 0.52, w * 0.66, h * 0.55], fill=BLACK)
        d.rounded_rectangle([w * 0.8, h * 0.45, w * 0.88, h * 0.6], radius=6, fill=WHITE)
        d.ellipse([w * 0.825, h * 0.47, w * 0.855, h * 0.5], fill=(90, 220, 120))
    if label:
        f = mont(800, int(h * 0.075))
        tw = d.textlength(label, font=f)
        d.rectangle([w / 2 - tw / 2 - 16, h - h * 0.12, w / 2 + tw / 2 + 16, h - h * 0.02], fill=BLACK)
        d.text((w / 2 - tw / 2, h - h * 0.115), label, font=f, fill=YELLOW)
    return img


def framed(img, border=12, color=WHITE, tilt=0):
    w, h = img.size
    out = Image.new("RGBA", (w + border * 2, h + border * 2), color + (255,))
    out.paste(img, (border, border))
    if tilt:
        out = out.rotate(tilt, resample=Image.BICUBIC, expand=True)
    return out


def arrow(d, pts, width=22, color=WHITE):
    # smooth curve through control points (quadratic bezier), arrowhead at end
    (x0, y0), (x1, y1), (x2, y2) = pts
    curve = []
    for i in range(41):
        t = i / 40
        x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * x1 + t * t * x2
        y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * y1 + t * t * y2
        curve.append((x, y))
    thick(d, curve, width + 12, BLACK)
    thick(d, curve, width, color)
    ex, ey = curve[-1]
    px, py = curve[-6]
    ang = math.atan2(ey - py, ex - px)
    L = width * 3.2
    for s in (-1, 1):
        a = ang + math.pi + s * 0.55
        thick(d, [(ex, ey), (ex + math.cos(a) * L, ey + math.sin(a) * L)], width + 12, BLACK)
    for s in (-1, 1):
        a = ang + math.pi + s * 0.55
        thick(d, [(ex, ey), (ex + math.cos(a) * L, ey + math.sin(a) * L)], width, color)


def fit_text(d, text, maxw, size):
    f = mont(800, size)
    while d.textlength(text, font=f) > maxw and size > 40:
        size -= 6
        f = mont(800, size)
    return f


def make(spec, path):
    bg = spec.get("bg", "red")
    img = Image.new("RGB", (W, H), RED if bg == "red" else BLACK)
    d = ImageDraw.Draw(img)
    if bg == "red":
        d.rectangle([W * 0.47, 0, W, H], fill=BLACK)
    # text block
    l1, l2 = spec["command"]
    size = min(fit_text(d, l1, W * 0.42, 240).size, fit_text(d, l2, W * 0.42, 240).size)
    f1 = f2 = mont(800, size)
    c1 = WHITE
    c2 = BLACK if bg == "red" else RED
    for ox, oy in ((-6, 0), (6, 0), (0, -6), (0, 6), (5, 5)):
        if bg != "red":
            d.text((60 + ox, 90 + oy), l1, font=f1, fill=BLACK)
    d.text((60, 90), l1, font=f1, fill=c1)
    d.text((60, 90 + int(size * 1.08)), l2, font=f2, fill=c2)
    arrow(d, [(260, 620), (420, 980), (900, 760)], width=24, color=WHITE)
    # panels
    pw, ph = 480, 740
    a = framed(scene(spec["left"], pw, ph, spec.get("left_label")), tilt=3)
    b = framed(scene(spec["right"], pw, ph, spec.get("right_label")), color=RED, tilt=-3)
    img.paste(a, (900, 170), a)
    img.paste(b, (W - b.width - 30, 140), b)
    d = ImageDraw.Draw(img)
    v2.spaced_text(d, (W - 50, 40), spec.get("file", ""), mont(700, 40), (200, 200, 200), 8, anchor="r")
    img = img.convert("RGB")
    img.resize((1280, 720), Image.LANCZOS).save(path, quality=93)


EPISODE_SPECS = {
    "001": [
        {"command": ["DO NOT", "STEP OUT"], "left": "elevator_normal", "right": "elevator_wrong",
         "left_label": "FLOOR 12", "right_label": "FLOOR 13", "file": "FILE 001", "bg": "red"},
        {"command": ["FLOOR 13?", "STAY INSIDE"], "left": "elevator_normal", "right": "elevator_wrong",
         "right_label": "IT'S SMILING", "file": "FILE 001", "bg": "black"},
    ],
    "002": [
        {"command": ["DO NOT", "GO IN"], "left": "door_normal", "right": "door_wrong",
         "left_label": "MONDAY", "right_label": "TUESDAY", "file": "FILE 002", "bg": "red"},
        {"command": ["CHECK YOUR", "BADGE"], "left": "badge_normal", "right": "badge_wrong",
         "left_label": "YESTERDAY", "right_label": "TODAY", "file": "FILE 002", "bg": "black"},
    ],
}


if __name__ == "__main__":
    ep = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for i, spec in enumerate(ep.get("thumbnails") or EPISODE_SPECS[ep["file_number"]]):
        p = os.path.join(out, f"thumb_{ep['file_number']}_{'AB'[i]}.jpg")
        make(spec, p)
        print(p)
