"""Procedural city skylines for Meridian's top band (dawn, day, dusk, night), and photo crops.

Generated, so there are no photos to license. To use your own photos instead,
put them in photos/<dawn|day|dusk|night>/ (see gen_assets.py).
"""
import math
import random
from PIL import Image, ImageDraw, ImageFilter, ImageMath, ImageStat

from landscape import PALETTES, fade_to_black, lerp

SS = 2
GAMMA = 2.2         # photos are resized in linear light (gamma-decoded), then re-encoded

CITY = {
    # far / mid / near building colours, window colour, share of lit windows, beacons
    "dawn": {"b": [(118, 96, 140), (70, 56, 96), (30, 24, 44)], "win": (255, 200, 140), "lit": 0.18, "beacon": True},
    "day": {"b": [(150, 178, 200), (96, 120, 140), (44, 58, 70)], "win": (200, 226, 244), "lit": 0.30, "beacon": False},
    "dusk": {"b": [(150, 78, 100), (84, 40, 68), (26, 14, 30)], "win": (255, 196, 110), "lit": 0.45, "beacon": True},
    "night": {"b": [(30, 40, 70), (18, 24, 46), (8, 10, 22)], "win": (255, 204, 120), "lit": 0.40, "beacon": True},
}


def _sky(name, W, H):
    p = PALETTES[name]
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
        for _ in range(90):
            x, y = rng.uniform(0, W), rng.uniform(0, H * 0.45)
            r = rng.choice([0.6, 0.8, 1.0]) * SS
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rng.randint(80, 220)))
    ox, oy, r = int(W * 0.75), int(H * p["orb_y"] * 0.8), p["orb_r"] * SS
    glow = Image.new("RGBA", (W, H), p["glow"] + (0,))
    gd = ImageDraw.Draw(glow)
    for k in range(10, 0, -1):
        rr = r * (1 + k * 0.55)
        gd.ellipse([ox - rr, oy - rr, ox + rr, oy + rr], fill=p["glow"] + (int(14 + 4 * (10 - k)),))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(8 * SS)))
    d = ImageDraw.Draw(im)
    d.ellipse([ox - r, oy - r, ox + r, oy + r], fill=p["orb"] + (255,))
    if name == "night":
        d.ellipse([ox - r + 6 * SS, oy - r - 3 * SS, ox + r + 6 * SS, oy + r - 3 * SS], fill=lerp(top, mid, 0.3) + (255,))
    return im


def _skyline(d, rng, W, H, base_y, hmin, hmax, wmin, wmax, color, win, lit, beacon, windows):
    x = -rng.uniform(0, wmax)
    while x < W:
        bw = rng.uniform(wmin, wmax) * SS
        bh = rng.uniform(hmin, hmax) * SS
        if rng.random() < 0.12:
            bh *= 1.45                                  # occasional tower
        top = base_y - bh
        d.rectangle([x, top, x + bw, H], fill=color + (255,))
        kind = rng.random()
        if kind < 0.25:                                 # stepped top
            d.rectangle([x + bw * 0.2, top - bh * 0.12, x + bw * 0.8, top], fill=color + (255,))
            top -= bh * 0.12
        elif kind < 0.40:                               # spire
            d.rectangle([x + bw * 0.46, top - bh * 0.28, x + bw * 0.54, top], fill=color + (255,))
            if beacon:
                r = 1.4 * SS
                cx, cy = x + bw * 0.5, top - bh * 0.28
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 70, 60, 255))
            top -= bh * 0.28
        if windows:
            wx0 = x + 3 * SS
            while wx0 < x + bw - 4 * SS:
                wy = base_y - bh + 6 * SS
                while wy < H - 2 * SS:
                    if rng.random() < lit:
                        a = rng.randint(120, 255)
                        d.rectangle([wx0, wy, wx0 + 2 * SS, wy + 2.5 * SS], fill=win + (a,))
                    wy += 6 * SS
                wx0 += 5 * SS
        x += bw + rng.uniform(0, 3) * SS


def base(name, w, h, fade):
    W, H = w * SS, h * SS
    c = CITY[name]
    im = _sky(name, W, H)
    rng = random.Random(21)
    specs = [  # base y, height range, width range, windows
        (H * 0.78, 60, 140, 16, 32, False),
        (H * 0.86, 50, 110, 20, 40, True),
        (H * 0.96, 36, 80, 24, 48, True),
    ]
    for (by, hmin, hmax, wmin, wmax, win), col in zip(specs, c["b"]):
        layer = Image.new("RGBA", (W, H), col + (0,))
        _skyline(ImageDraw.Draw(layer), rng, W, H, by, hmin, hmax, wmin, wmax, col, c["win"],
                 c["lit"] * (0.6 if not win else 1), c["beacon"], win)
        im.alpha_composite(layer)
    im = im.resize((w, h), Image.LANCZOS)
    return fade_to_black(im, fade[0], fade[1])


def _linear(ch):
    return ImageMath.lambda_eval(lambda a: (a["float"](a["c"]) / 255.0) ** GAMMA, c=ch)


def _encode(lin, k=1.0):
    return ImageMath.lambda_eval(
        lambda a: a["convert"](a["max"](a["min"](a["f"] * k, 1.0), 0.0) ** (1 / GAMMA) * 255.0 + 0.5, "L"), f=lin)


def data_mean(im):
    """Mean brightness (0..1) of the area behind the data: the disc inside the bezel."""
    w, h = im.size
    m = Image.new("L", (w, h), 0)
    r = 0.43 * w
    ImageDraw.Draw(m).ellipse([w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r], fill=255)
    return ImageStat.Stat(im.convert("L"), m).mean[0] / 255


def from_photo(path, w, h, fade=None, x=0.5, y=0.5, zoom=1.0, dim=0, max_mean=None, ev=0.0):
    """Cover-crop a photo around a focus point (x, y: 0 = left/top .. 1 = right/bottom)
    with `zoom` (>= 1). Resizing happens in linear light, so small lights and stars keep
    their brightness. Photos brighter than `max_mean` behind the data (see data_mean) are
    darkened softly (exposure in linear light, colours kept) so white text stays readable;
    `ev` adds a manual exposure change in stops. Returns (RGB image, info)."""
    im = Image.open(path)
    scale = max(w / im.width, h / im.height) * max(1.0, zoom)
    # JPEG: decode at a reduced size that still keeps 2x the pixels needed (much faster)
    im.draft("RGB", (int(im.width * scale * 2) + 1, int(im.height * scale * 2) + 1))
    im = im.convert("RGB")
    scale = max(w / im.width, h / im.height) * max(1.0, zoom)
    sw, sh = im.width * scale, im.height * scale
    x0 = max(0.0, min(x * sw - w / 2, sw - w))
    y0 = max(0.0, min(y * sh - h / 2, sh - h))
    box = (x0 / scale, y0 / scale, min(im.width, (x0 + w) / scale), min(im.height, (y0 + h) / scale))
    lin = [_linear(c).resize((w, h), Image.LANCZOS, box=box) for c in im.split()]
    out = Image.merge("RGB", [_encode(c) for c in lin])
    mean = data_mean(out)
    k = 2.0 ** ev
    if max_mean and mean > max_mean:
        # keep a third of the excess, so bright photos still look brighter than dark ones
        target = max_mean + (mean - max_mean) / 3
        k *= max(0.35, (target / mean) ** GAMMA)
    if k != 1.0:
        out = Image.merge("RGB", [_encode(c, k) for c in lin])
    if dim:
        out = Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), out, Image.new("L", (w, h), dim))
    if fade:
        out = fade_to_black(out.convert("RGBA"), fade[0], fade[1]).convert("RGB")
    return out, {"mean": mean, "ev": math.log2(k)}
