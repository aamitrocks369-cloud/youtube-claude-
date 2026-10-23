#!/usr/bin/env python3
"""Render high-quality astrology YouTube thumbnails (1920x1080 + 1280x720).

Everything is drawn procedurally with Pillow + numpy: cosmic nebula background,
a shaded banded Jupiter, a zodiac ring, metallic gold text, badges and a 12-sign
strip.  Rendered at 2x and downsampled for clean anti-aliasing.

    python3 thumbnails/make_horoscope_thumbnail.py --variant all \
        --out thumbnails/weekly-horoscope-oct25-31
"""
import argparse
import math
import os

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")
SYMBOL_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

S = 2                      # supersample factor
W, H = 1920 * S, 1080 * S  # render size

SIGNS = "♈♉♊♋♌♍♎♏♐♑♒♓"
SIGN_NAMES = ["ARIES", "TAURUS", "GEMINI", "CANCER", "LEO", "VIRGO",
              "LIBRA", "SCORPIO", "SAGITTARIUS", "CAPRICORN", "AQUARIUS", "PISCES"]
LEO = 4
JUPITER_GLYPH = "♃"

GOLD_STOPS = [(0.00, (255, 248, 205)), (0.30, (255, 214, 92)), (0.52, (255, 236, 150)),
              (0.62, (232, 160, 32)), (0.85, (190, 110, 14)), (1.00, (255, 206, 90))]
WHITE_STOPS = [(0.0, (255, 255, 255)), (0.55, (240, 243, 255)), (1.0, (196, 206, 232))]
RED_STOPS = [(0.0, (255, 84, 84)), (0.5, (214, 20, 40)), (1.0, (140, 0, 24))]


# ----------------------------------------------------------------------------- utils
def font(name, size, weight=None):
    f = ImageFont.truetype(os.path.join(FONT_DIR, name), int(size))
    if weight:
        f.set_variation_by_name(weight)
    return f


def sym_font(size):
    return ImageFont.truetype(SYMBOL_FONT, int(size))


def lerp(a, b, t):
    return a + (b - a) * t


def gradient_strip(stops, n):
    """n x 3 float array interpolated over multi-stop gradient."""
    out = np.zeros((n, 3), np.float32)
    ts = np.linspace(0, 1, n)
    for i, t in enumerate(ts):
        for (t0, c0), (t1, c1) in zip(stops[:-1], stops[1:]):
            if t0 <= t <= t1:
                u = 0 if t1 == t0 else (t - t0) / (t1 - t0)
                out[i] = [lerp(c0[k], c1[k], u) for k in range(3)]
                break
    return out


def vgradient_image(w, h, stops):
    strip = gradient_strip(stops, h)
    arr = np.repeat(strip[:, None, :], w, axis=1)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def fbm(h, w, octaves=5, base=3, seed=0, persistence=0.55):
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        n = base * (2 ** o) + 1
        g = rng.random((n, n)).astype(np.float32)
        up = Image.fromarray(g, "F").resize((w, h), Image.BICUBIC)
        acc += amp * np.asarray(up)
        total += amp
        amp *= persistence
    acc /= total
    return np.clip(acc, 0, 1)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def paste(dst, src, xy):
    dst.alpha_composite(src, (int(xy[0]), int(xy[1])))


def glow_layer(mask, color, radius, strength=1.0):
    """RGBA layer of `color` blurred by mask."""
    g = mask.filter(ImageFilter.GaussianBlur(radius))
    if strength != 1.0:
        g = g.point(lambda v: min(255, int(v * strength)))
    layer = Image.new("RGBA", mask.size, color + (0,))
    layer.putalpha(g)
    return layer


# ----------------------------------------------------------------------------- text
def text_mask(size, xy, text, fnt, stroke=0, anchor="la"):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).text(xy, text, font=fnt, fill=255, stroke_width=stroke,
                           stroke_fill=255, anchor=anchor)
    return m


def fancy_text(canvas, xy, text, fnt, stops=GOLD_STOPS, stroke=0, stroke_color=(30, 16, 0),
               shadow=(0, 0), shadow_blur=0, shadow_alpha=170, glow=None, glow_radius=0,
               glow_strength=1.0, anchor="la", fill=None):
    """Draw text with gradient fill, optional stroke, drop shadow and glow."""
    size = canvas.size
    fill_mask = text_mask(size, xy, text, fnt, 0, anchor)
    bbox = fill_mask.getbbox()
    if bbox is None:
        return None
    stroke_mask = text_mask(size, xy, text, fnt, stroke, anchor) if stroke else fill_mask

    if glow:
        canvas.alpha_composite(glow_layer(stroke_mask, glow, glow_radius, glow_strength))
    if shadow != (0, 0) or shadow_blur:
        sh = ImageChops.offset(stroke_mask, shadow[0], shadow[1])
        if shadow_blur:
            sh = sh.filter(ImageFilter.GaussianBlur(shadow_blur))
        sh = sh.point(lambda v: v * shadow_alpha // 255)
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        layer.putalpha(sh)
        canvas.alpha_composite(layer)
    if stroke:
        layer = Image.new("RGBA", size, stroke_color + (0,))
        layer.putalpha(stroke_mask)
        canvas.alpha_composite(layer)
    if fill is not None:
        layer = Image.new("RGBA", size, fill + (0,))
    else:
        x0, y0, x1, y1 = bbox
        grad = vgradient_image(x1 - x0, y1 - y0, stops)
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        layer.paste(grad, (x0, y0))
    layer.putalpha(fill_mask)
    canvas.alpha_composite(layer)
    return bbox


def tracked_width(text, fnt, tracking):
    return sum(fnt.getlength(c) for c in text) + tracking * (len(text) - 1)


def tracked_text(draw, xy, text, fnt, fill, tracking, anchor_mid=False):
    x, y = xy
    if anchor_mid:
        x -= tracked_width(text, fnt, tracking) / 2
    for c in text:
        draw.text((x, y), c, font=fnt, fill=fill, anchor="ls")
        x += fnt.getlength(c) + tracking


def pill(text, fnt, pad_x, pad_y, fill, text_fill, outline=None, outline_w=0, tracking=0,
         radius=None, rotate=0, shadow=True):
    tw = tracked_width(text, fnt, tracking)
    asc, desc = fnt.getmetrics()
    th = asc + desc
    w, h = int(tw + 2 * pad_x), int(th + 2 * pad_y)
    m = 60
    img = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = h // 2 if radius is None else radius
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([m + 6, m + 12, m + w + 6, m + h + 12], r, fill=(0, 0, 0, 150))
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14)))
    d.rounded_rectangle([m, m, m + w, m + h], r, fill=fill, outline=outline, width=outline_w)
    tracked_text(d, (m + pad_x, m + pad_y + asc), text, fnt, text_fill, tracking)
    if rotate:
        img = img.rotate(rotate, resample=Image.BICUBIC, expand=True)
    return img


def gradient_bar(text, fnt, pad_x, pad_y, stops, text_fill, tracking=0, skew=0.0, rotate=0):
    """Rectangular (optionally skewed) bar filled with a vertical gradient."""
    tw = tracked_width(text, fnt, tracking)
    asc, desc = fnt.getmetrics()
    th = asc + desc
    w, h = int(tw + 2 * pad_x + abs(skew) * th), int(th + 2 * pad_y)
    m = 60
    img = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    grad = vgradient_image(w, h, stops)
    mask = Image.new("L", (w, h), 0)
    dx = int(skew * h)
    ImageDraw.Draw(mask).polygon([(dx, 0), (w, 0), (w - dx, h), (0, h)], fill=255)
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sh.paste((0, 0, 0, 160), (m + 8, m + 14), mask)
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))
    img.paste(grad, (m, m), mask)
    d = ImageDraw.Draw(img)
    tracked_text(d, (m + pad_x + max(dx, 0) // 2, m + pad_y + asc), text, fnt, text_fill, tracking)
    if rotate:
        img = img.rotate(rotate, resample=Image.BICUBIC, expand=True)
    return img


# ----------------------------------------------------------------------------- scenery
def cosmic_background(seed=1, base=(6, 8, 28), nebula_a=(92, 34, 150), nebula_b=(255, 150, 50),
                      hot=(1540 * S, 540 * S), hot_color=(255, 170, 60), hot_radius=900 * S,
                      hot_strength=0.55, nebula_strength=0.9):
    h, w = H, W
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.zeros((h, w, 3), np.float32)
    img[:] = base

    # vertical / diagonal lift
    diag = (xx / w * 0.6 + yy / h * 0.4)
    img += diag[..., None] * np.array([10, 4, 30], np.float32)

    # nebula (two tints)
    n1 = fbm(h // 4, w // 4, octaves=6, base=3, seed=seed)
    n1 = np.asarray(Image.fromarray(n1, "F").resize((w, h), Image.BICUBIC))
    n2 = fbm(h // 4, w // 4, octaves=5, base=2, seed=seed + 7)
    n2 = np.asarray(Image.fromarray(n2, "F").resize((w, h), Image.BICUBIC))
    a = smoothstep(0.42, 0.85, n1) * nebula_strength
    b = smoothstep(0.55, 0.95, n2) * nebula_strength * 0.75
    img += a[..., None] * np.array(nebula_a, np.float32) * 0.8
    img += b[..., None] * np.array(nebula_b, np.float32) * 0.35

    # hot glow near the hero
    d = np.sqrt((xx - hot[0]) ** 2 + (yy - hot[1]) ** 2)
    g = np.clip(1 - d / hot_radius, 0, 1) ** 2.2 * hot_strength
    img += g[..., None] * np.array(hot_color, np.float32)

    # vignette
    cx, cy = w / 2, h / 2
    v = np.sqrt(((xx - cx) / (w / 2)) ** 2 + ((yy - cy) / (h / 2)) ** 2)
    img *= (1 - 0.45 * smoothstep(0.55, 1.25, v))[..., None]

    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    return add_stars(im, seed)


def add_stars(im, seed=1, count=900):
    rng = np.random.default_rng(seed + 100)
    w, h = im.size
    small = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(small)
    for _ in range(count):
        x, y = rng.random() * w, rng.random() * h
        r = rng.random() ** 3 * 3.5 * S + 0.6 * S
        v = int(120 + rng.random() * 135)
        d.ellipse([x - r, y - r, x + r, y + r], fill=v)
    small = small.filter(ImageFilter.GaussianBlur(0.8 * S))
    layer = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    layer.putalpha(small)
    im.alpha_composite(layer)
    # a few bright stars with 4-point flares
    big = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(big)
    for _ in range(28):
        x, y = rng.random() * w, rng.random() * h
        ln = (18 + rng.random() * 40) * S
        d.line([x - ln, y, x + ln, y], fill=255, width=int(1.2 * S))
        d.line([x, y - ln * 0.7, x, y + ln * 0.7], fill=255, width=int(1.2 * S))
        r = 2.6 * S
        d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    big = big.filter(ImageFilter.GaussianBlur(1.1 * S))
    layer = Image.new("RGBA", (w, h), (255, 246, 220, 0))
    layer.putalpha(big.point(lambda v: int(v * 0.85)))
    im.alpha_composite(layer)
    return im


def jupiter(radius, seed=3, light=(-0.42, -0.38, 0.82)):
    """Return RGBA image of a banded gas giant of given radius (in render px)."""
    n = int(radius * 2)
    pad = 2
    size = n + 2 * pad
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    x = (xx - size / 2 + 0.5) / radius
    y = (yy - size / 2 + 0.5) / radius
    r2 = x * x + y * y
    inside = r2 < 1.0
    z = np.sqrt(np.clip(1 - r2, 0, 1))
    lat = np.arcsin(np.clip(y, -1, 1))            # -pi/2..pi/2
    lon = np.arctan2(x, np.maximum(z, 1e-4))       # -pi/2..pi/2 visible

    # banded texture in (lat, lon) space with domain warp
    th, tw = 1024, 1024

    def stretched(octaves, base, sd, stretch=6):
        n = fbm(th, max(tw // stretch, 8), octaves=octaves, base=base, seed=sd)
        return np.asarray(Image.fromarray(n, "F").resize((tw, th), Image.BICUBIC))

    warp = stretched(6, 5, seed) - 0.5
    streak = stretched(5, 3, seed + 1, stretch=4)
    # texture coordinates
    ti = np.clip(((lat / math.pi + 0.5) * (th - 1)).astype(int), 0, th - 1)
    tj = np.clip(((lon / math.pi + 0.5) * (tw - 1)).astype(int), 0, tw - 1)
    wv = warp[ti, tj]
    eddies = stretched(5, 16, seed + 3, stretch=3) - 0.5
    t = (lat / math.pi + 0.5) + 0.035 * wv + 0.012 * (streak[ti, tj] - 0.5) + 0.010 * eddies[ti, tj]

    stops = [(0.00, (150, 110, 80)), (0.08, (215, 190, 150)), (0.14, (176, 118, 70)),
             (0.20, (236, 220, 190)), (0.26, (196, 140, 86)), (0.32, (244, 230, 204)),
             (0.38, (170, 100, 56)), (0.43, (232, 206, 164)), (0.48, (210, 150, 96)),
             (0.52, (240, 226, 198)), (0.58, (182, 112, 64)), (0.63, (236, 216, 180)),
             (0.68, (204, 148, 94)), (0.74, (246, 232, 206)), (0.80, (178, 118, 72)),
             (0.87, (220, 196, 156)), (0.93, (160, 112, 76)), (1.00, (140, 100, 72))]
    cmap = gradient_strip(stops, 1024)
    idx = np.clip((t * 1023).astype(int), 0, 1023)
    col = cmap[idx]
    # fine streaks
    fine = stretched(5, 14, seed + 2, stretch=10)
    col *= (0.84 + 0.30 * fine[ti, tj])[..., None]
    # polar darkening
    polar = smoothstep(0.55, 1.0, np.abs(np.sin(lat)))
    col *= (1 - 0.28 * polar)[..., None]
    # boost band contrast
    mean = col.mean(axis=2, keepdims=True)
    col = np.clip(mean + (col - mean) * 1.3, 0, 255)
    col = np.clip(128 + (col - 128) * 1.08, 0, 255)

    # Great Red Spot
    sx, sy = -0.30, 0.30                     # lon, lat (radians-ish)
    dsp = ((lon - sx) / 0.26) ** 2 + ((lat - sy) / 0.11) ** 2
    spot = np.clip(np.exp(-dsp ** 1.5 * 1.1) * 1.15, 0, 1)
    ring = np.exp(-((np.sqrt(dsp) - 1.25) ** 2) * 9) * 0.6
    col = col * (1 - spot[..., None]) + np.array([190, 72, 40], np.float32) * spot[..., None]
    col = col * (1 - ring[..., None]) + np.array([240, 214, 180], np.float32) * ring[..., None]

    # shading
    L = np.array(light, np.float32)
    L /= np.linalg.norm(L)
    ndl = np.clip(x * L[0] + y * L[1] + z * L[2], 0, 1)
    shade = 0.30 + 0.80 * ndl ** 0.75
    limb = 0.72 + 0.28 * z ** 0.5
    spec = np.clip(ndl, 0, 1) ** 40 * 0.25
    col = col * (shade * limb)[..., None] + 255 * spec[..., None]
    # warm rim on lit side, cool shadow
    col[..., 2] *= 0.92
    rgb = np.clip(col, 0, 255).astype(np.uint8)

    edge = smoothstep(1.0, 0.985, r2)
    alpha = (edge * 255).astype(np.uint8)
    out = np.dstack([rgb, alpha])
    img = Image.fromarray(out, "RGBA")
    rgb_img = img.convert("RGB").filter(ImageFilter.UnsharpMask(radius=2.5 * S, percent=110, threshold=1))
    rgb_img.putalpha(img.getchannel("A"))
    return rgb_img


def radial_glow(radius, inner, color, strength=1.0, power=2.0):
    size = int(radius * 2)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    d = np.sqrt((xx - size / 2) ** 2 + (yy - size / 2) ** 2)
    a = np.clip(1 - (d - inner) / (radius - inner), 0, 1) ** power * strength
    a[d < inner] = strength
    arr = np.zeros((size, size, 4), np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = color
    arr[..., 3] = np.clip(a * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def zodiac_ring(canvas, center, radius, glyph_size, highlight=LEO, start_deg=-150,
                ring_color=(255, 200, 90), dim=(255, 220, 150)):
    cx, cy = center
    d = ImageDraw.Draw(canvas)
    # rings
    for rr, wd, al in [(radius, 3 * S, 210), (radius - 26 * S, 1 * S, 110), (radius + 26 * S, 1 * S, 110)]:
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=ring_color + (al,), width=int(wd))
    # ticks
    for k in range(72):
        a = math.radians(k * 5)
        r0 = radius - (14 * S if k % 6 == 0 else 7 * S)
        d.line([cx + r0 * math.cos(a), cy + r0 * math.sin(a),
                cx + radius * math.cos(a), cy + radius * math.sin(a)],
               fill=ring_color + (170,), width=int(1.5 * S))
    sf = sym_font(glyph_size)
    for i, g in enumerate(SIGNS):
        a = math.radians(start_deg + i * 30)
        gx, gy = cx + radius * math.cos(a), cy + radius * math.sin(a)
        cr = glyph_size * 0.78
        if i == highlight:
            continue
        d.ellipse([gx - cr, gy - cr, gx + cr, gy + cr], fill=(10, 8, 30, 235),
                  outline=ring_color + (255,), width=int(2.5 * S))
        d.text((gx, gy), g, font=sf, fill=dim + (255,), anchor="mm")
    # highlighted sign
    a = math.radians(start_deg + highlight * 30)
    gx, gy = cx + radius * math.cos(a), cy + radius * math.sin(a)
    cr = glyph_size * 1.15
    m = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(m).ellipse([gx - cr, gy - cr, gx + cr, gy + cr], fill=255)
    canvas.alpha_composite(glow_layer(m, (255, 190, 60), 40 * S, 1.0))
    canvas.alpha_composite(glow_layer(m, (255, 230, 150), 12 * S, 1.0))
    d = ImageDraw.Draw(canvas)
    d.ellipse([gx - cr, gy - cr, gx + cr, gy + cr], fill=(255, 212, 96, 255),
              outline=(255, 250, 220, 255), width=int(4 * S))
    d.text((gx, gy), SIGNS[highlight], font=sym_font(glyph_size * 1.5), fill=(40, 16, 0, 255), anchor="mm")
    return gx, gy


def sign_strip(canvas, x0, y, spacing, radius, highlight=LEO, names=False, name_font=None):
    d = ImageDraw.Draw(canvas)
    sf = sym_font(radius * 1.3)
    for i, g in enumerate(SIGNS):
        cx = x0 + i * spacing
        if i == highlight:
            m = Image.new("L", canvas.size, 0)
            ImageDraw.Draw(m).ellipse([cx - radius * 1.2, y - radius * 1.2, cx + radius * 1.2, y + radius * 1.2], fill=255)
            canvas.alpha_composite(glow_layer(m, (255, 190, 60), 22 * S))
            d = ImageDraw.Draw(canvas)
            rr = radius * 1.2
            d.ellipse([cx - rr, y - rr, cx + rr, y + rr], fill=(255, 212, 96, 255),
                      outline=(255, 250, 220, 255), width=int(3 * S))
            d.text((cx, y), g, font=sym_font(radius * 1.7), fill=(40, 16, 0, 255), anchor="mm")
        else:
            d.ellipse([cx - radius, y - radius, cx + radius, y + radius], fill=(12, 10, 36, 220),
                      outline=(255, 200, 90, 255), width=int(2.5 * S))
            d.text((cx, y), g, font=sf, fill=(255, 226, 160, 255), anchor="mm")
        if names and name_font:
            d.text((cx, y + radius * 1.55), SIGN_NAMES[i], font=name_font,
                   fill=(255, 226, 160, 255) if i != highlight else (255, 240, 200, 255), anchor="ma")


def sun_lion_emblem(canvas, center, radius, rays=24, color_outer=(255, 150, 20), glyph=True):
    """Stylised sun/mane disc for Leo (ruled by the Sun) with the Leo glyph inside."""
    cx, cy = center
    size = canvas.size
    rays_mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(rays_mask)
    for k in range(rays):
        a = math.radians(k * 360 / rays - 90)
        long = radius * (1.62 if k % 2 == 0 else 1.32)
        half = math.radians(360 / rays * 0.42)
        pts = [(cx + radius * 0.92 * math.cos(a - half), cy + radius * 0.92 * math.sin(a - half)),
               (cx + long * math.cos(a), cy + long * math.sin(a)),
               (cx + radius * 0.92 * math.cos(a + half), cy + radius * 0.92 * math.sin(a + half))]
        d.polygon(pts, fill=255)
    canvas.alpha_composite(glow_layer(rays_mask, (255, 140, 30), 60 * S, 1.0))
    canvas.alpha_composite(glow_layer(rays_mask, (255, 200, 80), 18 * S, 1.0))
    # rays: gradient gold
    bbox = rays_mask.getbbox()
    grad = vgradient_image(bbox[2] - bbox[0], bbox[3] - bbox[1],
                           [(0, (255, 232, 140)), (0.5, (255, 170, 40)), (1, (200, 90, 10))])
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.paste(grad, (bbox[0], bbox[1]))
    layer.putalpha(rays_mask)
    canvas.alpha_composite(layer)
    # disc
    disc = radial_glow(radius * 1.02, radius * 0.0, (255, 220, 120), 1.0, 0.0)
    d = ImageDraw.Draw(canvas)
    # outer ring and inner disc with gradient
    rr = radius
    disc_mask = Image.new("L", size, 0)
    ImageDraw.Draw(disc_mask).ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=255)
    grad = vgradient_image(int(2 * rr), int(2 * rr),
                           [(0, (255, 240, 170)), (0.45, (255, 196, 70)), (1, (224, 120, 20))])
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.paste(grad, (int(cx - rr), int(cy - rr)))
    layer.putalpha(disc_mask)
    canvas.alpha_composite(layer)
    d = ImageDraw.Draw(canvas)
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(120, 50, 0, 255), width=int(6 * S))
    r2 = rr * 0.86
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], outline=(255, 250, 215, 200), width=int(3 * S))
    if glyph:
        fancy_text(canvas, (cx, cy + rr * 0.02), SIGNS[LEO], sym_font(rr * 1.45),
                   stops=[(0, (70, 24, 0)), (1, (40, 10, 0))], shadow=(0, 6 * S), shadow_blur=8 * S,
                   shadow_alpha=120, anchor="mm")


def finish(canvas, out_base):
    rgb = canvas.convert("RGB")
    full = rgb.resize((1920, 1080), Image.LANCZOS)
    full = full.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    full.save(out_base + ".png", optimize=True)
    small = full.resize((1280, 720), Image.LANCZOS)
    small.save(out_base + ".jpg", quality=93, subsampling=0, optimize=True)
    print("wrote", out_base + ".png", out_base + ".jpg")


# ----------------------------------------------------------------------------- variants
def variant_a(out):
    """Cosmic Jupiter on the zodiac ring, text column on the left."""
    canvas = cosmic_background(seed=11)
    jc = (1500 * S, 540 * S)
    jr = 300 * S

    # outer glows behind the planet
    paste(canvas, radial_glow(jr * 2.4, jr * 0.9, (255, 150, 40), 0.75, 2.4), (jc[0] - jr * 2.4, jc[1] - jr * 2.4))
    paste(canvas, radial_glow(jr * 1.35, jr * 0.98, (255, 220, 140), 0.9, 1.4), (jc[0] - jr * 1.35, jc[1] - jr * 1.35))
    lx, ly = zodiac_ring(canvas, jc, 410 * S, 40 * S, start_deg=90)
    jup = jupiter(jr, seed=5)
    paste(canvas, jup, (jc[0] - jr - 2, jc[1] - jr - 2))

    # label under planet
    tag = gradient_bar("BIG TRANSIT", font("BebasNeue-Regular.ttf", 64 * S), 30 * S, 8 * S, RED_STOPS,
                       (255, 255, 255, 255), tracking=4 * S, skew=0.18, rotate=-4)
    paste(canvas, tag, (jc[0] - tag.width / 2 + 10 * S, jc[1] + jr + 4 * S))

    # ---- left column
    pad = 72 * S
    date = pill("25 – 31 OCTOBER", font("Montserratwght.ttf", 40 * S, b"ExtraBold"), 34 * S, 14 * S,
                (10, 8, 34, 235), (255, 214, 110, 255), outline=(255, 200, 90, 255), outline_w=int(3 * S),
                tracking=5 * S)
    paste(canvas, date, (pad - 60, 48 * S - 60))

    fancy_text(canvas, (pad, 150 * S), "WEEKLY HOROSCOPE", font("BebasNeue-Regular.ttf", 112 * S),
               stops=WHITE_STOPS, stroke=int(6 * S), stroke_color=(14, 6, 40), shadow=(0, 10 * S),
               shadow_blur=14 * S, shadow_alpha=200)

    fancy_text(canvas, (pad - 6 * S, 262 * S), "JUPITER", font("Cinzelwght.ttf", 196 * S, b"Black"),
               stroke=int(9 * S), stroke_color=(42, 18, 0), shadow=(0, 14 * S), shadow_blur=18 * S,
               shadow_alpha=220, glow=(255, 160, 40), glow_radius=50 * S, glow_strength=0.9)
    fancy_text(canvas, (pad - 6 * S, 474 * S), "IN LEO", font("Cinzelwght.ttf", 196 * S, b"Black"),
               stroke=int(9 * S), stroke_color=(42, 18, 0), shadow=(0, 14 * S), shadow_blur=18 * S,
               shadow_alpha=220, glow=(255, 160, 40), glow_radius=50 * S, glow_strength=0.9)
    # Leo glyph next to "IN LEO"
    leo_x = pad + font("Cinzelwght.ttf", 196 * S, b"Black").getlength("IN LEO") + 36 * S
    fancy_text(canvas, (leo_x, 474 * S + 118 * S), SIGNS[LEO], sym_font(190 * S),
               stroke=int(8 * S), stroke_color=(42, 18, 0), shadow=(0, 10 * S), shadow_blur=14 * S,
               glow=(255, 160, 40), glow_radius=40 * S, anchor="lm")

    bar = gradient_bar("ALL 12 SIGNS", font("Montserratwght.ttf", 72 * S, b"Black"), 40 * S, 12 * S,
                       GOLD_STOPS, (30, 14, 0, 255), tracking=3 * S, skew=0.2)
    paste(canvas, bar, (pad - 60 - 4 * S, 720 * S - 60))

    sign_strip(canvas, pad + 40 * S, 930 * S, 78 * S, 30 * S)

    finish(canvas, out)


def variant_b(out):
    """Golden Leo sun-emblem with Jupiter arriving, warm palette, huge headline."""
    canvas = cosmic_background(seed=23, base=(22, 6, 30), nebula_a=(140, 30, 90), nebula_b=(255, 120, 40),
                               hot=(1420 * S, 560 * S), hot_color=(255, 120, 30), hot_radius=1000 * S,
                               hot_strength=0.5)
    ec = (1430 * S, 560 * S)
    er = 230 * S
    paste(canvas, radial_glow(er * 2.8, er * 1.2, (255, 120, 20), 0.6, 2.2), (ec[0] - er * 2.8, ec[1] - er * 2.8))
    sun_lion_emblem(canvas, ec, er)

    # Jupiter sweeping in from the top-left along an orbit arc
    jr = 118 * S
    jc = (985 * S, 215 * S)
    d = ImageDraw.Draw(canvas)
    # curved trail from Jupiter into the sun, with a glowing arrow head
    dx, dy = ec[0] - jc[0], ec[1] - jc[1]
    dl = math.hypot(dx, dy)
    ux, uy = dx / dl, dy / dl
    p0 = (jc[0] + ux * jr * 1.25, jc[1] + uy * jr * 1.25)
    p2 = (ec[0] - ux * er * 1.22, ec[1] - uy * er * 1.22)
    mid = ((p0[0] + p2[0]) / 2, (p0[1] + p2[1]) / 2)
    p1 = (mid[0] + uy * 70 * S, mid[1] - ux * 70 * S)
    pts = []
    for i in range(41):
        u = i / 40
        pts.append(((1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * p1[0] + u * u * p2[0],
                    (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * p1[1] + u * u * p2[1]))
    trail = Image.new("L", canvas.size, 0)
    td = ImageDraw.Draw(trail)
    for (xa, ya), (xb, yb), i in zip(pts[:-1], pts[1:], range(40)):
        td.line([xa, ya, xb, yb], fill=int(90 + 165 * i / 40), width=int(6 * S + 8 * S * i / 40))
    ang = math.atan2(p2[1] - pts[-3][1], p2[0] - pts[-3][0])
    tip = (p2[0] + 34 * S * math.cos(ang), p2[1] + 34 * S * math.sin(ang))
    tri = [tip,
           (p2[0] + 28 * S * math.cos(ang + 2.2), p2[1] + 28 * S * math.sin(ang + 2.2)),
           (p2[0] + 28 * S * math.cos(ang - 2.2), p2[1] + 28 * S * math.sin(ang - 2.2))]
    td.polygon(tri, fill=255)
    canvas.alpha_composite(glow_layer(trail, (255, 190, 90), 18 * S, 1.0))
    canvas.alpha_composite(glow_layer(trail, (255, 245, 215), 2 * S, 1.0))
    paste(canvas, radial_glow(jr * 2.0, jr * 0.95, (255, 200, 120), 0.8, 1.8), (jc[0] - jr * 2, jc[1] - jr * 2))
    paste(canvas, jupiter(jr, seed=9, light=(0.35, 0.45, 0.82)), (jc[0] - jr - 2, jc[1] - jr - 2))
    lab = font("Montserratwght.ttf", 44 * S, b"ExtraBold")
    lw = lab.getlength("JUPITER") + 58 * S
    fancy_text(canvas, (jc[0] - lw / 2, jc[1] - jr - 30 * S), JUPITER_GLYPH, sym_font(50 * S),
               stops=GOLD_STOPS, stroke=int(5 * S), stroke_color=(30, 8, 20), anchor="lm")
    fancy_text(canvas, (jc[0] - lw / 2 + 58 * S, jc[1] - jr - 30 * S), "JUPITER", lab,
               stops=WHITE_STOPS, stroke=int(5 * S), stroke_color=(30, 8, 20), anchor="lm")

    # ---- left column
    pad = 72 * S
    date = pill("25 – 31 OCTOBER", font("Montserratwght.ttf", 40 * S, b"ExtraBold"), 34 * S, 14 * S,
                (255, 214, 110, 255), (40, 16, 0, 255), tracking=5 * S)
    paste(canvas, date, (pad - 60, 50 * S - 60))

    big = font("Anton-Regular.ttf", 236 * S)
    fancy_text(canvas, (pad - 8 * S, 128 * S), "WEEKLY", big, stops=WHITE_STOPS, stroke=int(10 * S),
               stroke_color=(30, 6, 30), shadow=(0, 16 * S), shadow_blur=20 * S, shadow_alpha=220)
    fancy_text(canvas, (pad - 8 * S, 356 * S), "HOROSCOPE", big, stops=WHITE_STOPS, stroke=int(10 * S),
               stroke_color=(30, 6, 30), shadow=(0, 16 * S), shadow_blur=20 * S, shadow_alpha=220)

    bar = gradient_bar("ALL 12 SIGNS", font("Montserratwght.ttf", 70 * S, b"Black"), 40 * S, 12 * S,
                       GOLD_STOPS, (30, 14, 0, 255), tracking=3 * S, skew=0.2, rotate=-2)
    paste(canvas, bar, (pad - 60, 640 * S - 60))

    fancy_text(canvas, (pad, 1022 * S), "JUPITER ENTERS LEO", font("Cinzelwght.ttf", 118 * S, b"Black"),
               stroke=int(8 * S), stroke_color=(42, 18, 0), shadow=(0, 12 * S), shadow_blur=16 * S,
               shadow_alpha=220, glow=(255, 150, 30), glow_radius=40 * S, glow_strength=0.9, anchor="ls")
    tag = gradient_bar("BIG TRANSIT", font("BebasNeue-Regular.ttf", 58 * S), 26 * S, 6 * S, RED_STOPS,
                       (255, 255, 255, 255), tracking=4 * S, skew=0.18, rotate=-6)
    paste(canvas, tag, (pad + 480 * S, 782 * S))

    finish(canvas, out)


def variant_c(out):
    """All-12-signs showcase: glyph rows top and bottom, Jupiter + Leo hero in the middle."""
    canvas = cosmic_background(seed=37, base=(5, 10, 34), nebula_a=(60, 40, 170), nebula_b=(255, 160, 60),
                               hot=(1560 * S, 600 * S), hot_strength=0.5)
    jc = (1560 * S, 600 * S)
    jr = 330 * S
    paste(canvas, radial_glow(jr * 2.2, jr * 0.9, (255, 150, 40), 0.7, 2.4), (jc[0] - jr * 2.2, jc[1] - jr * 2.2))
    paste(canvas, radial_glow(jr * 1.3, jr * 0.98, (255, 220, 140), 0.9, 1.4), (jc[0] - jr * 1.3, jc[1] - jr * 1.3))
    paste(canvas, jupiter(jr, seed=17), (jc[0] - jr - 2, jc[1] - jr - 2))

    # big Leo medallion overlapping the planet's lower-left
    mc = (jc[0] - jr * 0.78, jc[1] + jr * 0.62)
    mr = 118 * S
    m = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(m).ellipse([mc[0] - mr, mc[1] - mr, mc[0] + mr, mc[1] + mr], fill=255)
    canvas.alpha_composite(glow_layer(m, (255, 180, 50), 50 * S))
    d = ImageDraw.Draw(canvas)
    grad = vgradient_image(int(2 * mr), int(2 * mr), [(0, (255, 240, 170)), (0.5, (255, 196, 70)), (1, (224, 120, 20))])
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(grad, (int(mc[0] - mr), int(mc[1] - mr)))
    layer.putalpha(m)
    canvas.alpha_composite(layer)
    d = ImageDraw.Draw(canvas)
    d.ellipse([mc[0] - mr, mc[1] - mr, mc[0] + mr, mc[1] + mr], outline=(255, 250, 215, 255), width=int(6 * S))
    d.ellipse([mc[0] - mr * 0.88, mc[1] - mr * 0.88, mc[0] + mr * 0.88, mc[1] + mr * 0.88], outline=(120, 50, 0, 200), width=int(3 * S))
    d.text((mc[0], mc[1] + 4 * S), SIGNS[LEO], font=sym_font(mr * 1.5), fill=(50, 18, 0, 255), anchor="mm")

    # sign rows
    nf = font("Montserratwght.ttf", 17 * S, b"Bold")
    row = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sign_strip(row, 150 * S, 78 * S, 148 * S, 34 * S, highlight=LEO, names=True, name_font=nf)
    canvas.alpha_composite(row)

    # headline block
    pad = 72 * S
    date = pill("25 – 31 OCTOBER", font("Montserratwght.ttf", 40 * S, b"ExtraBold"), 34 * S, 14 * S,
                (10, 8, 34, 235), (255, 214, 110, 255), outline=(255, 200, 90, 255), outline_w=int(3 * S),
                tracking=5 * S)
    paste(canvas, date, (pad - 60, 190 * S - 60))
    big = font("Anton-Regular.ttf", 200 * S)
    fancy_text(canvas, (pad - 8 * S, 268 * S), "WEEKLY", big, stops=WHITE_STOPS, stroke=int(9 * S),
               stroke_color=(14, 6, 40), shadow=(0, 14 * S), shadow_blur=18 * S, shadow_alpha=220)
    fancy_text(canvas, (pad - 8 * S, 458 * S), "HOROSCOPE", big, stops=WHITE_STOPS, stroke=int(9 * S),
               stroke_color=(14, 6, 40), shadow=(0, 14 * S), shadow_blur=18 * S, shadow_alpha=220)
    bar = gradient_bar("ALL 12 SIGNS", font("Montserratwght.ttf", 66 * S, b"Black"), 36 * S, 12 * S,
                       GOLD_STOPS, (30, 14, 0, 255), tracking=3 * S, skew=0.2)
    paste(canvas, bar, (pad - 60, 700 * S - 60))
    tag = gradient_bar("BIG TRANSIT", font("BebasNeue-Regular.ttf", 56 * S), 26 * S, 6 * S, RED_STOPS,
                       (255, 255, 255, 255), tracking=4 * S, skew=0.18, rotate=-5)
    paste(canvas, tag, (pad + 610 * S, 676 * S))
    fancy_text(canvas, (pad, 930 * S), "JUPITER IN LEO", font("Cinzelwght.ttf", 124 * S, b"Black"),
               stroke=int(8 * S), stroke_color=(42, 18, 0), shadow=(0, 12 * S), shadow_blur=16 * S,
               shadow_alpha=220, glow=(255, 150, 30), glow_radius=40 * S, glow_strength=0.9, anchor="ls")
    finish(canvas, out)


VARIANTS = {"a": variant_a, "b": variant_b, "c": variant_c}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="all", help="a, b, c or all")
    ap.add_argument("--out", default=os.path.join(HERE, "weekly-horoscope-oct25-31"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    keys = VARIANTS if args.variant == "all" else [args.variant]
    for k in keys:
        VARIANTS[k](os.path.join(args.out, f"thumbnail_{k}"))


if __name__ == "__main__":
    main()
