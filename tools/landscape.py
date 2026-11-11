"""Procedural mountain landscapes for Meridian's top band.

Four times of day (dawn, day, dusk, night) as base images, plus weather
overlays (clouds, rain, snow, fog) drawn on top by the watch face. Everything is
generated, so there are no third-party photos to license.
"""
import math
import random
from PIL import Image, ImageDraw, ImageFilter

SS = 2  # supersampling

# sky top, sky horizon, sun/moon colour, three mountain layers (far -> near)
PALETTES = {
    "dawn": {
        "sky": [(28, 36, 74), (122, 92, 140), (246, 160, 120)],
        "orb": (255, 214, 160), "orb_y": 0.80, "orb_r": 15, "glow": (255, 170, 120),
        "layers": [(132, 104, 150), (84, 66, 110), (44, 36, 66)],
    },
    "day": {
        "sky": [(34, 110, 190), (88, 160, 220), (178, 214, 236)],
        "orb": (255, 246, 214), "orb_y": 0.46, "orb_r": 14, "glow": (255, 250, 230),
        "layers": [(120, 156, 182), (76, 110, 120), (40, 62, 58)],
    },
    "dusk": {
        "sky": [(40, 30, 72), (170, 72, 92), (250, 150, 70)],
        "orb": (255, 200, 110), "orb_y": 0.86, "orb_r": 17, "glow": (255, 130, 70),
        "layers": [(150, 70, 90), (92, 42, 72), (44, 22, 44)],
    },
    "night": {
        "sky": [(4, 8, 22), (12, 22, 50), (30, 44, 80)],
        "orb": (232, 236, 246), "orb_y": 0.44, "orb_r": 11, "glow": (120, 140, 190),
        "layers": [(34, 46, 76), (22, 30, 52), (10, 14, 28)],
    },
}


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def ridge(rng, w, base, rough, n=9):
    """Midpoint-displacement ridge line, returns y per x."""
    pts = [base + rng.uniform(-rough, rough), base + rng.uniform(-rough, rough)]
    disp = rough
    for _ in range(n):
        nxt = []
        for i in range(len(pts) - 1):
            nxt.append(pts[i])
            nxt.append((pts[i] + pts[i + 1]) / 2 + rng.uniform(-disp, disp))
        nxt.append(pts[-1])
        pts = nxt
        disp *= 0.55
    out = []
    for x in range(w):
        f = x / (w - 1) * (len(pts) - 1)
        i = min(int(f), len(pts) - 2)
        out.append(pts[i] + (pts[i + 1] - pts[i]) * (f - i))
    return out


def fade_to_black(im, start, end):
    """Darken rows from `start` to `end` (in px) down to pure black, keep alpha."""
    w, h = im.size
    mask = Image.new("L", (1, h), 0)
    for y in range(h):
        if y <= start:
            v = 0
        elif y >= end:
            v = 255
        else:
            t = (y - start) / (end - start)
            v = int(255 * (t * t * (3 - 2 * t)))
        mask.putpixel((0, y), v)
    mask = mask.resize((w, h))
    black = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    return Image.composite(black, im, mask)


def base(name, w, h, fade):
    p = PALETTES[name]
    W, H = w * SS, h * SS
    im = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(im)
    horizon = int(H * 0.82)
    top, mid, low = p["sky"]
    for y in range(H):
        t = min(1.0, y / horizon)
        c = lerp(top, mid, t / 0.6) if t < 0.6 else lerp(mid, low, (t - 0.6) / 0.4)
        d.line([(0, y), (W, y)], fill=c + (255,))

    rng = random.Random(7)
    if name == "night":
        for _ in range(140):
            x, y = rng.uniform(0, W), rng.uniform(0, H * 0.62)
            r = rng.choice([0.6, 0.8, 1.0, 1.4]) * SS
            a = rng.randint(90, 255)
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, a))

    # sun / moon with glow
    ox, oy, r = int(W * 0.81), int(H * p["orb_y"]), p["orb_r"] * SS
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for k in range(10, 0, -1):
        rr = r * (1 + k * 0.55)
        gd.ellipse([ox - rr, oy - rr, ox + rr, oy + rr], fill=p["glow"] + (int(14 + 4 * (10 - k)),))
    glow = glow.filter(ImageFilter.GaussianBlur(8 * SS))
    im.alpha_composite(glow)
    d = ImageDraw.Draw(im)
    d.ellipse([ox - r, oy - r, ox + r, oy + r], fill=p["orb"] + (255,))
    if name == "night":  # crescent
        d.ellipse([ox - r + 6 * SS, oy - r - 3 * SS, ox + r + 6 * SS, oy + r - 3 * SS], fill=lerp(top, mid, 0.4) + (255,))

    # mountain layers
    rng = random.Random(11)
    # (base height, roughness, peaks as (x fraction, height px, width px))
    specs = [(0.66, 30, [(0.22, 62, 70), (0.58, 40, 60)]),
             (0.76, 26, [(0.40, 34, 80), (0.88, 46, 60)]),
             (0.88, 14, [(0.12, 20, 90), (0.70, 14, 110)])]
    for (bf, rough, peaks), col in zip(specs, p["layers"]):
        ys = ridge(rng, W, H * bf, rough * SS)
        for px, ph, pw in peaks:
            for x in range(W):
                dx = (x - px * W) / (pw * SS)
                ys[x] -= ph * SS * max(0.0, 1 - abs(dx)) ** 1.6
        poly = [(0, H)] + [(x, ys[x]) for x in range(W)] + [(W - 1, H)]
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).polygon(poly, fill=col + (255,))
        im.alpha_composite(layer)

    im = im.resize((w, h), Image.LANCZOS)
    return fade_to_black(im, fade[0], fade[1])


def _clouds(w, h, rng, color, alpha, count, y_range, blur, scale=1.0):
    W, H = w * SS, h * SS
    # transparent pixels carry the cloud colour, so blurring leaves no dark fringe
    layer = Image.new("RGBA", (W, H), color + (0,))
    d = ImageDraw.Draw(layer)
    for _ in range(count):
        cx = rng.uniform(-0.05, 1.05) * W
        cy = rng.uniform(*y_range) * H
        cw = rng.uniform(60, 130) * SS * scale
        for _ in range(9):
            bx = cx + rng.uniform(-cw / 2, cw / 2)
            by = cy + rng.uniform(-cw / 14, cw / 18)
            br = rng.uniform(cw / 9, cw / 5)
            d.ellipse([bx - br, by - br * 0.5, bx + br, by + br * 0.5], fill=color + (alpha,))
    return layer.filter(ImageFilter.GaussianBlur(blur * SS)).resize((w, h), Image.LANCZOS)


def overlay(kind, w, h, fade):
    rng = random.Random({"clouds": 3, "rain": 5, "snow": 9, "fog": 13}[kind])
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if kind in ("rain", "snow"):
        # overcast wash so the sky reads as grey whatever the time of day
        wash = Image.new("RGBA", (w, h), (70, 76, 86, 120 if kind == "rain" else 90))
        im.alpha_composite(wash)
    if kind in ("rain", "snow"):
        # heavy cloud bank over the sun/moon position (0.81 W, ~0.45 H)
        bank = Image.new("RGBA", (w, h), (96, 102, 114, 0))
        bd = ImageDraw.Draw(bank)
        for dx, dy, r in ((0, 0, 34), (-30, 8, 26), (30, 6, 28), (0, -16, 24)):
            x, y = w * 0.81 + dx, h * 0.45 + dy
            bd.ellipse([x - r * 1.4, y - r, x + r * 1.4, y + r], fill=(96, 102, 114, 235))
        im.alpha_composite(bank.filter(ImageFilter.GaussianBlur(6)))
    if kind == "clouds":
        im.alpha_composite(_clouds(w, h, rng, (214, 220, 230), 110, 10, (0.10, 0.55), 6))
        im.alpha_composite(_clouds(w, h, rng, (244, 246, 250), 150, 7, (0.15, 0.45), 4))
    elif kind == "rain":
        im.alpha_composite(_clouds(w, h, rng, (104, 110, 122), 190, 16, (0.0, 0.45), 7, 1.4))
        d = ImageDraw.Draw(im)
        for _ in range(170):
            x, y = rng.uniform(-20, w), rng.uniform(h * 0.2, h * 0.95)
            ln = rng.uniform(8, 15)
            d.line([(x, y), (x + ln * 0.3, y + ln)], fill=(200, 214, 230, rng.randint(70, 140)), width=1)
    elif kind == "snow":
        im.alpha_composite(_clouds(w, h, rng, (190, 196, 206), 170, 16, (0.0, 0.42), 7, 1.4))
        d = ImageDraw.Draw(im)
        for _ in range(150):
            x, y = rng.uniform(0, w), rng.uniform(h * 0.15, h * 0.95)
            r = rng.choice([0.8, 1.1, 1.5])
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rng.randint(150, 235)))
    elif kind == "fog":
        fog = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        fd = ImageDraw.Draw(fog)
        for i in range(7):
            y = h * (0.40 + i * 0.07)
            fd.rectangle([0, y, w, y + h * 0.05], fill=(210, 214, 222, 70 + i * 8))
        fog = fog.filter(ImageFilter.GaussianBlur(7))
        im.alpha_composite(Image.new("RGBA", (w, h), (150, 156, 166, 70)))
        im.alpha_composite(fog)
    # keep the lower part transparent so the black data area stays black
    a = im.getchannel("A")
    ramp = Image.new("L", (1, h))
    for y in range(h):
        t = 0 if y <= fade[0] else 1 if y >= fade[1] else (y - fade[0]) / (fade[1] - fade[0])
        ramp.putpixel((0, y), int(255 * (1 - t)))
    ramp = ramp.resize((w, h))
    from PIL import ImageChops
    im.putalpha(ImageChops.multiply(a, ramp))
    return im
