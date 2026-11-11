"""Weather effects (looping animation frames and tint washes) and the compass ring."""
import math
import random
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FRAMES = 4

# Zepp weather codes (0..28) -> (wash, animation). None = nothing.
WEATHER_FX = {
    0: ("cloudy", None), 1: ("rain", "rain_light"), 2: ("snow", "snow_light"), 3: (None, None),
    4: ("overcast", None), 5: ("rain", "rain_light"), 6: ("snow", "snow_light"), 7: ("rain", "rain_heavy"),
    8: ("snow", "snow_heavy"), 9: ("snow", "snow_heavy"), 10: ("rain", "rain_heavy"), 11: ("dust", "dust"),
    12: ("rain", "sleet"), 13: ("fog", "fog"), 14: ("haze", "fog"), 15: ("storm", "storm"),
    16: ("snow", "snow_heavy"), 17: ("dust", "dust"), 18: ("storm", "storm"), 19: ("rain", "sleet"),
    20: ("storm", "storm"), 21: ("storm", "storm"), 22: ("dust", "dust"), 23: ("dust", "dust"),
    24: ("rain", "rain_heavy"), 25: (None, None), 26: ("cloudy", None), 27: ("rain", "rain_light"),
    28: (None, None),
}
"""
WASHES = {  # colour, alpha
    "cloudy": ((120, 126, 138), 60), "overcast": ((92, 98, 110), 105), "rain": ((70, 80, 96), 115),
    "storm": ((40, 44, 60), 140), "snow": ((196, 204, 214), 70), "fog": ((200, 206, 214), 110),
    "haze": ((210, 196, 170), 70), "dust": ((196, 150, 90), 95),
}
"""
WASHES = {  # colour, alpha
    "cloudy": ((120, 126, 138), 0), "overcast": ((92, 98, 110), 0), "rain": ((70, 80, 96), 0),
    "storm": ((40, 44, 60), 0), "snow": ((196, 204, 214), 0), "fog": ((200, 206, 214), 0),
    "haze": ((210, 196, 170), 0), "dust": ((196, 150, 90), 0),
}
ANIMS = ("rain_light", "rain_heavy", "storm", "snow_light", "snow_heavy", "sleet", "fog", "dust")


def _bottom_fade(im, fade):
    w, h = im.size
    ramp = Image.new("L", (1, h))
    for y in range(h):
        t = 0 if y <= fade[0] else 1 if y >= fade[1] else (y - fade[0]) / (fade[1] - fade[0])
        ramp.putpixel((0, y), int(255 * (1 - t)))
    im.putalpha(ImageChops.multiply(im.getchannel("A"), ramp.resize((w, h))))
    return im


def wash(kind, w, h, fade):
    col, a = WASHES[kind]
    return _bottom_fade(Image.new("RGBA", (w, h), col + (a,)), fade)


def _rain_layer(rng, w, h, count, length, alpha, width=1, color=(205, 220, 238)):
    im = Image.new("RGBA", (w, h), color + (0,))
    d = ImageDraw.Draw(im)
    for _ in range(count):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        ln = rng.uniform(*length)
        for dy in (0, -h):            # draw twice so the pattern wraps vertically
            d.line([(x, y + dy), (x + ln * 0.18, y + dy + ln)], fill=color + (rng.randint(*alpha),), width=width)
    return im


def _snow_layer(rng, w, h, count, rmax, alpha):
    im = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    for _ in range(count):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.uniform(0.7, rmax)
        a = rng.randint(*alpha)
        for dy in (0, -h, h):
            d.ellipse([x - r, y + dy - r, x + r, y + dy + r], fill=(255, 255, 255, a))
    return im


def _mist_layer(rng, w, h, color, count, alpha):
    im = Image.new("RGBA", (w, h), color + (0,))
    d = ImageDraw.Draw(im)
    for _ in range(count):
        x, y = rng.uniform(0, w), rng.uniform(h * 0.25, h * 0.9)
        rw, rh = rng.uniform(60, 160), rng.uniform(8, 20)
        a = rng.randint(*alpha)
        for dx in (0, -w, w):          # wrap horizontally
            d.ellipse([x + dx - rw, y - rh, x + dx + rw, y + rh], fill=color + (a,))
    return im.filter(ImageFilter.GaussianBlur(10))


def _roll(im, dx, dy):
    return ImageChops.offset(im, int(dx), int(dy))


def anim_frames(kind, w, h, fade):
    """FRAMES images that loop seamlessly."""
    rng = random.Random(sum(map(ord, kind)))
    frames = []
    if kind in ("rain_light", "rain_heavy", "storm", "sleet"):
        dense = kind != "rain_light"
        far = _rain_layer(rng, w, h, 140 if dense else 70, (8, 12), (50, 90))
        near = _rain_layer(rng, w, h, 90 if dense else 40, (14, 22), (90, 160), width=1)
        snow = _snow_layer(rng, w, h, 50, 1.8, (150, 230)) if kind == "sleet" else None
        for k in range(FRAMES):
            f = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            f.alpha_composite(_roll(far, 0, k * h / FRAMES / 2))
            f.alpha_composite(_roll(near, 0, k * h / FRAMES))
            if snow:
                f.alpha_composite(_roll(snow, 0, k * h / FRAMES / 4))
            if kind == "storm" and k == 0:
                f.alpha_composite(Image.new("RGBA", (w, h), (230, 236, 255, 55)))
            frames.append(f)
    elif kind in ("snow_light", "snow_heavy"):
        heavy = kind == "snow_heavy"
        far = _snow_layer(rng, w, h, 140 if heavy else 70, 1.3, (120, 200))
        near = _snow_layer(rng, w, h, 70 if heavy else 35, 2.4, (170, 250))
        for k in range(FRAMES):
            f = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            f.alpha_composite(_roll(far, k * 2, k * h / FRAMES / 4))
            f.alpha_composite(_roll(near, -k * 3, k * h / FRAMES / 2))
            frames.append(f)
    else:  # fog / dust drift sideways
        color = (214, 218, 226) if kind == "fog" else (214, 170, 110)
        mist = _mist_layer(rng, w, h, color, 26, (40, 90))
        for k in range(FRAMES):
            frames.append(_roll(mist, k * w / FRAMES / 4, 0).copy())
    return [_bottom_fade(f, fade) for f in frames]


# ---------------------------------------------------------------- compass ring --
def compass_ring(size, font_path, north=(255, 80, 70), fg=(235, 235, 235), dim=(140, 140, 140)):
    """Full-screen ring: ticks every 5 degrees, numbers every 30, N/E/S/W letters.
    The watch rotates this image so N points north."""
    S = 3
    W = size * S
    c = W / 2
    im = Image.new("RGBA", (W, W), fg + (0,))
    d = ImageDraw.Draw(im)
    r_out = (size / 2 - 1) * S
    # connecting circle
    rc = (size / 2 - 14) * S
    d.ellipse([c - rc, c - rc, c + rc, c + rc], outline=dim + (150,), width=int(1.2 * S))
    for deg in range(0, 360, 5):
        a = math.radians(deg - 90)
        major = deg % 30 == 0
        ln = (11 if major else 6) * S
        col = (north if deg == 0 else fg if major else dim) + (255,)
        d.line([c + r_out * math.cos(a), c + r_out * math.sin(a),
                c + (r_out - ln) * math.cos(a), c + (r_out - ln) * math.sin(a)],
               fill=col, width=int((2.4 if major else 1.4) * S))
    labels = {0: ("N", 30, north), 90: ("E", 26, fg), 180: ("S", 26, fg), 270: ("W", 26, fg)}
    for deg in range(0, 360, 30):
        if deg in labels:
            text, fs, col = labels[deg]
            weight = 700
        else:
            text, fs, col = str(deg), 15, dim
            weight = 600
        f = ImageFont.truetype(font_path % weight, int(fs * S))
        tile = Image.new("RGBA", (int(fs * 2.6 * S), int(fs * 1.6 * S)), col + (0,))
        m = Image.new("L", tile.size, 0)
        ImageDraw.Draw(m).text((tile.width / 2, tile.height / 2), text, font=f, fill=255, anchor="mm")
        tile.putalpha(m)
        tile = tile.rotate(-deg, resample=Image.BICUBIC, expand=True)
        rr = (size / 2 - (30 if deg in labels else 27)) * S
        a = math.radians(deg - 90)
        x, y = c + rr * math.cos(a), c + rr * math.sin(a)
        im.alpha_composite(tile, (int(x - tile.width / 2), int(y - tile.height / 2)))
    return im.resize((size, size), Image.LANCZOS)


def lubber(color=(255, 255, 255)):
    """Fixed index mark at 12 o'clock: the heading is read where it points."""
    S = 4
    im = Image.new("RGBA", (16 * S, 12 * S), color + (0,))
    ImageDraw.Draw(im).polygon([(0, 0), (16 * S, 0), (8 * S, 12 * S)], fill=color + (255,))
    return im.resize((16, 12), Image.LANCZOS)
