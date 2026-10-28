"""
2D layers drawn on top of the 3D frames: captions (Devanagari, one colour per
speaker), clock stamps, phone screens with chat bubbles, and black theme
cards. All text goes through Raqm so Hindi conjuncts shape correctly.
"""
import os
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "assets", "fonts")
W, H = 1080, 1920

SPEAKER_COLOURS = {
    "narrator": (245, 245, 240),
    "ravi": (255, 120, 100),
    "meera": (255, 170, 200),
    "papa": (150, 200, 255),
    "maa": (255, 205, 110),
    "sharma": (170, 230, 170),
}


EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u2190-\u21FF\u2300-\u23FF]")


def clean(text):
    """Drop emoji and symbols the Devanagari fonts cannot draw."""
    return re.sub(r"\s{2,}", " ", EMOJI.sub("", text)).strip()


def font(kind="sans", size=56, bold=True):
    name = {
        ("sans", True): "NotoSansDevanagari-Bold.ttf",
        ("sans", False): "NotoSansDevanagari-Regular.ttf",
        ("serif", True): "NotoSerifDevanagari-Bold.ttf",
        ("serif", False): "NotoSerifDevanagari-Regular.ttf",
    }[(kind, bold)]
    return ImageFont.truetype(os.path.join(FONTS, name), size, layout_engine=ImageFont.Layout.RAQM)


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def wrap(d, text, f, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if d.textlength(test, font=f) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def caption(img, text, who, alpha, y_frac=0.74):
    """Speaker-coloured caption with a soft dark outline. The narrator is a
    serif in white; characters are a bold sans in their colour."""
    if alpha <= 0:
        return img
    narr = who == "narrator"
    f = font("serif" if narr else "sans", 58 if narr else 62, bold=not narr or True)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lines = wrap(d, clean(text), f, W * 0.82)
    lh = int(f.size * 1.45)
    y = int(H * y_frac) - lh * len(lines) // 2
    col = SPEAKER_COLOURS.get(who, (255, 255, 255))
    a = int(255 * alpha)
    for k, line in enumerate(lines):
        tw = d.textlength(line, font=f)
        x = (W - tw) / 2
        d.text((x, y + k * lh), line, font=f, fill=(*col, a), stroke_width=7, stroke_fill=(0, 0, 0, int(a * 0.85)))
    if not narr:
        # speaker tag above the caption
        tag = font("sans", 34, bold=True)
        name = who.upper()
        d.text(((W - d.textlength(name, font=tag)) / 2, y - 52), name, font=tag, fill=(*col, int(a * 0.8)),
               stroke_width=4, stroke_fill=(0, 0, 0, int(a * 0.7)))
    return Image.alpha_composite(img.convert("RGBA"), layer)


def clock(img, text, alpha, corner="top"):
    """Big thin clock stamp ("2:14 AM"), the Last Soul time ladder."""
    if alpha <= 0:
        return img
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    hm, _, ampm = text.partition(" ")
    f1 = font("sans", 150, bold=False)
    f2 = font("sans", 60, bold=False)
    w1 = d.textlength(hm, font=f1)
    w2 = d.textlength(ampm, font=f2)
    x = (W - w1 - w2 - 16) / 2
    y = 230 if corner == "top" else H // 2 - 100
    a = int(235 * alpha)
    d.text((x, y), hm, font=f1, fill=(235, 238, 245, a), stroke_width=3, stroke_fill=(0, 0, 0, a // 3))
    d.text((x + w1 + 16, y + 70), ampm, font=f2, fill=(235, 238, 245, a))
    return Image.alpha_composite(img.convert("RGBA"), layer)


def card(img, text, sub, alpha):
    """Black theme card: serif text centred, optional small line under it."""
    base = Image.new("RGBA", img.size, (4, 4, 6, 255))
    d = ImageDraw.Draw(base)
    f = font("serif", 84, bold=False)
    lines = wrap(d, clean(text), f, W * 0.8)
    lh = int(f.size * 1.5)
    y = H // 2 - lh * len(lines) // 2 - (30 if sub else 0)
    for k, line in enumerate(lines):
        d.text(((W - d.textlength(line, font=f)) / 2, y + k * lh), line, font=f, fill=(238, 236, 230))
    if sub:
        fs = font("serif", 40, bold=False)
        sub = clean(sub)
        d.text(((W - d.textlength(sub, font=fs)) / 2, y + lh * len(lines) + 30), sub, font=fs, fill=(170, 168, 160))
    return Image.blend(img.convert("RGBA"), base, alpha)


def _rounded(d, box, r, fill, outline=None, width=0):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


def phone(img, spec, t, alpha):
    """POV phone held up in front of the scene with a chat thread.
    spec: {"title": "माँ", "messages": [{"t": 0.4, "from": "them"|"me"|"group", "who": "…", "text": "…"}],
           "time": "2:16"}"""
    if alpha <= 0:
        return img
    base = img.convert("RGBA").filter(ImageFilter.GaussianBlur(10))
    dim = Image.new("RGBA", img.size, (0, 0, 0, int(120 * alpha)))
    base = Image.alpha_composite(base, dim)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    pw, ph = 700, 1300
    rise = int((1 - ease(alpha)) * 300)
    x0, y0 = (W - pw) // 2, (H - ph) // 2 + 60 + rise
    _rounded(d, (x0 - 18, y0 - 18, x0 + pw + 18, y0 + ph + 18), 90, (12, 12, 14, 255))
    _rounded(d, (x0, y0, x0 + pw, y0 + ph), 74, (236, 238, 242, 255))
    # status bar + header
    fs = font("sans", 30, bold=True)
    d.text((x0 + 60, y0 + 28), spec.get("time", "2:16"), font=fs, fill=(20, 20, 20, 255))
    _rounded(d, (x0 + pw - 120, y0 + 34, x0 + pw - 60, y0 + 58), 8, None, (20, 20, 20, 255), 3)
    d.rectangle((x0, y0 + 90, x0 + pw, y0 + 200), fill=(250, 250, 252, 255))
    d.ellipse((x0 + 40, y0 + 112, x0 + 106, y0 + 178), fill=(150, 160, 175, 255))
    d.text((x0 + 126, y0 + 118), clean(spec.get("title", "")), font=font("sans", 40, bold=True), fill=(20, 20, 25, 255))
    if spec.get("subtitle"):
        d.text((x0 + 126, y0 + 160), spec["subtitle"], font=font("sans", 24, bold=False), fill=(110, 110, 120, 255))
    # bubbles, bottom-up so the newest sits lowest
    fm = font("sans", 36, bold=False)
    fw = font("sans", 24, bold=True)
    shown = [m for m in spec.get("messages", []) if t >= m.get("t", 0)]
    y = y0 + 230
    for m in shown:
        mine = m.get("from") == "me"
        lines = wrap(d, clean(m["text"]), fm, pw * 0.62)
        bh = len(lines) * 50 + 34 + (30 if m.get("who") else 0)
        bw = max(d.textlength(line, font=fm) for line in lines) + 48
        if m.get("who"):
            bw = max(bw, d.textlength(m["who"], font=fw) + 48)
        bx = x0 + pw - 40 - bw if mine else x0 + 40
        pop = ease((t - m.get("t", 0)) / 0.18)
        fill = (60, 125, 245, int(255 * pop)) if mine else (255, 255, 255, int(255 * pop))
        _rounded(d, (bx, y, bx + bw, y + bh), 26, fill)
        ty = y + 16
        if m.get("who"):
            d.text((bx + 24, ty), m["who"], font=fw, fill=(30, 140, 90, int(255 * pop)))
            ty += 30
        for k, line in enumerate(lines):
            d.text((bx + 24, ty + k * 50), line, font=fm,
                   fill=(255, 255, 255, int(255 * pop)) if mine else (25, 25, 30, int(255 * pop)))
        y += bh + 22
    # hand silhouettes holding the phone
    hand = (8, 8, 10, 255)
    d.ellipse((x0 - 90, y0 + ph - 420, x0 + 90, y0 + ph + 60), fill=hand)
    d.ellipse((x0 + pw - 90, y0 + ph - 420, x0 + pw + 90, y0 + ph + 60), fill=hand)
    d.ellipse((x0 + pw - 120, y0 + ph - 520, x0 + pw + 20, y0 + ph - 380), fill=hand)
    out = Image.alpha_composite(base, layer)
    return Image.blend(img.convert("RGBA"), out, min(1.0, alpha * 1.4))
