"""Weather effects (tints, looping animations, lightning) and the compass ring.

Animations are full-screen frames that the face cycles while the screen is on. Every
frame draws the same particles at a later moment, and each particle either moves a
whole number of tile periods per loop (rain, sleet, dust) or fades in and out within
the loop (snow), so the loop restarts without a visible jump. Particles are drawn at
3x and scaled down, so streaks and flakes are smooth.
"""
import math
import random
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FRAMES = 8              # frames per loop (each costs ~0.22 MB per animation on the watch)
TICK_MS = 120           # time per frame; one loop lasts FRAMES * TICK_MS
SS = 3                  # supersampling for particles

# Zepp weather codes (0..28) -> (wash, animation). None = nothing.
WEATHER_FX = {
    0: ("cloudy", None), 1: ("rain", "rain_light"), 2: ("snow", "snow_light"), 3: (None, None),
    4: ("overcast", None), 5: ("rain", "rain_light"), 6: ("snow", "snow_light"), 7: ("rain", "rain_heavy"),
    8: ("snow", "snow_heavy"), 9: ("snow", "snow_heavy"), 10: ("rain", "rain_heavy"), 11: ("dust", "dust"),
    12: ("rain", "sleet"), 13: ("fog", None), 14: ("haze", None), 15: ("storm", "rain_heavy"),
    16: ("snow", "snow_heavy"), 17: ("dust", "dust"), 18: ("storm", "rain_heavy"), 19: ("rain", "sleet"),
    20: ("storm", "rain_heavy"), 21: ("storm", "rain_heavy"), 22: ("dust", "dust"), 23: ("dust", "dust"),
    24: ("rain", "rain_heavy"), 25: (None, None), 26: ("cloudy", None), 27: ("rain", "rain_light"),
    28: (None, None),
}
# Thunderstorm codes (their icon shows a bolt): the face adds an occasional lightning flash.
FLASH_CODES = (15, 20)
# Tints over the photo: colour, mean alpha (0 = no tint; kept light so the photo stays
# clear) and how it spreads from top to bottom ("sky": heavier at the top, like a
# clouded sky; "low": heavier at the bottom, like fog lying in a valley).
WASHES = {
    "cloudy": ((120, 126, 138), 25, "sky"), "overcast": ((92, 98, 110), 45, "sky"),
    "rain": ((70, 80, 96), 45, "sky"), "storm": ((40, 44, 60), 70, "sky"),
    "snow": ((196, 204, 214), 35, "even"), "fog": ((200, 206, 214), 60, "low"),
    "haze": ((210, 196, 170), 35, "even"), "dust": ((196, 150, 90), 45, "low"),
}
PROFILES = {"sky": (1.5, 0.5), "even": (1.15, 0.85), "low": (0.6, 1.4)}  # alpha factor at top, bottom
TEXTURED = ("fog", "dust")          # washes with drifting-cloud texture instead of a flat tint
ANIMS = ("rain_light", "rain_heavy", "sleet", "snow_light", "snow_heavy", "dust")

RAIN = (205, 218, 236)
WIND = math.tan(math.radians(9))    # rain slant: horizontal px per px of fall


def _bottom_fade(im, fade):
    w, h = im.size
    ramp = Image.new("L", (1, h))
    for y in range(h):
        t = 0 if y <= fade[0] else 1 if y >= fade[1] else (y - fade[0]) / (fade[1] - fade[0])
        ramp.putpixel((0, y), int(255 * (1 - t)))
    im.putalpha(ImageChops.multiply(im.getchannel("A"), ramp.resize((w, h))))
    return im


def _noise(rng, w, h, cells):
    """Smooth value noise (0..255) that wraps around horizontally."""
    gw, gh = cells, max(2, round(cells * h / w))
    g = Image.new("L", (gw, gh))
    g.putdata([rng.randint(0, 255) for _ in range(gw * gh)])
    strip = Image.new("L", (gw * 3, gh))
    for i in range(3):
        strip.paste(g, (i * gw, 0))
    return strip.resize((w * 3, h), Image.BICUBIC).crop((w, 0, 2 * w, h))


def _fractal(rng, w, h, octaves=((3, 1.0), (6, 0.55), (12, 0.3), (24, 0.15))):
    acc, total = None, 0.0
    for cells, amp in octaves:
        n = _noise(rng, w, h, cells)
        total += amp
        acc = n if acc is None else Image.blend(acc, n, amp / total)
    # stretch to the full range so thresholds behave the same for every seed
    lo, hi = acc.getextrema()
    return acc.point(lambda v: int(255 * (v - lo) / max(1, hi - lo)))


def wash(kind, w, h, fade=None):
    col, a, prof = WASHES[kind]
    top, bot = PROFILES[prof]
    ramp = Image.new("L", (1, h))
    for y in range(h):
        ramp.putpixel((0, y), max(0, min(255, int(round(a * (top + (bot - top) * y / (h - 1)))))))
    alpha = ramp.resize((w, h))
    if kind in TEXTURED:
        # patchy cloud: 0.35x..1.65x the ramp, so the mean strength stays about the same
        n = _fractal(random.Random(sum(map(ord, kind))), w, h).filter(ImageFilter.GaussianBlur(3))
        mult = n.point(lambda v: int(round(255 * (0.35 + 1.3 * (v / 255) ** 1.6) / 1.65)))
        tex = ImageChops.multiply(alpha, mult).point(lambda v: min(255, int(round(v * 1.65))))
        k = a / max(1.0, sum(tex.getdata()) / (w * h))      # keep the mean strength at `a`
        alpha = tex.point(lambda v: min(255, int(round(v * k))))
    im = Image.new("RGBA", (w, h), col + (0,))
    im.putalpha(alpha)
    return _bottom_fade(im, fade) if fade else im


def flash(w, h):
    """Lightning: the sky lights up from above (shown for a moment by the face)."""
    cx, cy, rad = w * 0.62, -h * 0.25, h * 1.5
    m = Image.new("L", (w // 2, h // 2), 0)
    px = m.load()
    for y in range(h // 2):
        for x in range(w // 2):
            d = math.hypot(2 * x - cx, 2 * y - cy) / rad
            px[x, y] = int(140 * max(0.0, 1 - d) ** 1.6)
    im = Image.new("RGBA", (w, h), (226, 232, 255, 0))
    im.putalpha(m.resize((w, h), Image.BICUBIC))
    return im


# ---------------------------------------------------------------- particles --
class _Layer:
    """One depth layer of particles, rendered as an alpha mask (colour is per layer).
    `halo`: strength of a faint dark rim, so light particles still show on bright skies."""

    def __init__(self, color, blur=0.0, halo=0.0):
        self.color, self.blur, self.halo, self.items = color, blur, halo, []


def _streak(d, x, y, ln, a, width, dx, dy):
    """Tapered streak ending (bright head) at x, y; tail points back along -dx, -dy."""
    pts = [(x - dx * ln * (1 - i / 4), y - dy * ln * (1 - i / 4)) for i in range(5)]
    for i in range(4):
        d.line([pts[i], pts[i + 1]], fill=int(a * (0.2 + 0.8 * (i + 1) / 4)), width=width)


def _render(layers, w, h, k, place, fade):
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for lay in layers:
        m = Image.new("L", (w * SS, h * SS), 0)
        d = ImageDraw.Draw(m)
        for it in lay.items:
            place(d, it, k)
        m = m.resize((w, h), Image.BOX)         # area average: clean anti-aliasing, no ringing
        if lay.blur:
            m = m.filter(ImageFilter.GaussianBlur(lay.blur))
        if lay.halo:
            sh = m.filter(ImageFilter.GaussianBlur(1.4)).point(lambda v: int(v * lay.halo))
            dark = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            dark.putalpha(sh)
            out.alpha_composite(dark)
        im = Image.new("RGBA", (w, h), lay.color + (0,))
        im.putalpha(m)
        out.alpha_composite(im)
    return _bottom_fade(out, fade) if fade else out


def _fall(w, h, layers, frames, fade):
    """Streaks falling along a slanted lattice: each moves n * (WIND * h, h) per loop."""
    S = WIND * h
    ux, uy = WIND / math.hypot(WIND, 1), 1 / math.hypot(WIND, 1)

    def place(d, it, k):
        x0, y0, ln, a, width, n = it
        t = n * k / frames
        x, y = x0 + S * t, y0 + h * t
        j = math.floor(y / h)
        x, y = (x - j * S) % w, y - j * h
        for jy in (0, 1):                       # the copy one period down shows the tail that wraps
            for ix in (-1, 0, 1):
                px, py = x + ix * w + jy * S, y + jy * h
                if -ln < px < w + ln and py - ln * uy < h:
                    _streak(d, px * SS, py * SS, ln * SS, a, width, ux, uy)
    return [_render(layers, w, h, k, place, fade) for k in range(frames)]


def _rain(rng, w, h, spec, halo=0.22):
    """spec: per layer (count, length range, alpha range, width px, periods per loop)."""
    layers = []
    for count, length, alpha, width, n in spec:
        lay = _Layer(RAIN, halo=halo)
        for _ in range(count):
            lay.items.append((rng.uniform(0, w), rng.uniform(0, h), rng.uniform(*length),
                              rng.uniform(*alpha), max(1, int(round(width * SS))), n))
        layers.append(lay)
    return layers


def _snow_frames(rng, w, h, spec, frames, fade):
    """Flakes drift down while fading in and out within one loop (no tiling, no jump).
    spec: per layer (count, radius range, alpha range, fall px per loop, blur)."""
    layers = []
    for count, radius, alpha, fall, blur in spec:
        lay = _Layer((255, 255, 255), blur, halo=0.35)
        for _ in range(count):
            lay.items.append((rng.uniform(0, w), rng.uniform(0, h), rng.uniform(*radius), rng.uniform(*alpha),
                              fall * rng.uniform(0.75, 1.25), rng.uniform(-0.25, 0.4) * fall,
                              rng.uniform(1.5, 4.0), rng.random(), rng.random()))
        layers.append(lay)

    def env(p):                                  # fade in over the first 30%, out over the last 30%
        e = min(1.0, p / 0.3, (1 - p) / 0.3)
        return e * e * (3 - 2 * e)

    def place(d, it, k):
        x0, y0, r, a, fall, drift, sway, phase, sph = it
        p = (k / frames + phase) % 1.0
        x = (x0 + drift * p + sway * math.sin(2 * math.pi * (p + sph))) % w
        y = (y0 + fall * p) % h
        v = int(a * env(p))
        if v <= 0:
            return
        for ox in (-w, 0, w):
            for oy in (-h, 0, h):
                px, py = x + ox, y + oy
                if -r < px < w + r and -r < py < h + r:
                    d.ellipse([(px - r) * SS, (py - r) * SS, (px + r) * SS, (py + r) * SS], fill=v)
    return [_render(layers, w, h, k, place, fade) for k in range(frames)]


def _dust_frames(rng, w, h, frames, fade):
    """Sand blown sideways: short horizontal streaks, one or two widths of the screen per loop."""
    layers = []
    for count, length, alpha, width, n, col in ((300, (3, 7), (60, 120), 1.0, 1, (226, 196, 150)),
                                                (70, (8, 16), (90, 160), 1.4, 2, (236, 210, 170))):
        lay = _Layer(col, halo=0.2)
        for _ in range(count):
            lay.items.append((rng.uniform(0, w), rng.uniform(0, h), rng.uniform(*length), rng.uniform(*alpha),
                              max(1, int(round(width * SS))), n, rng.uniform(-0.05, 0.12)))
        layers.append(lay)

    def place(d, it, k):
        x0, y0, ln, a, width, n, slope = it
        x = (x0 + w * n * k / frames) % w
        y = y0
        for ix in (-1, 0, 1):
            px = x + ix * w
            if -ln < px < w + ln:
                _streak(d, px * SS, y * SS, ln * SS, a, width, 1 / math.hypot(1, slope), slope / math.hypot(1, slope))
    return [_render(layers, w, h, k, place, fade) for k in range(frames)]


def anim_frames(kind, w, h, fade=None, frames=None):
    """`frames` images (FRAMES by default) that loop seamlessly."""
    frames = frames or FRAMES
    rng = random.Random(sum(map(ord, kind)))
    if kind == "rain_light":
        return _fall(w, h, _rain(rng, w, h, [(110, (9, 14), (45, 80), 1.0, 1),
                                             (40, (18, 26), (80, 120), 1.2, 1),
                                             (10, (34, 48), (95, 135), 1.5, 2)]), frames, fade)
    if kind == "rain_heavy":
        return _fall(w, h, _rain(rng, w, h, [(240, (10, 16), (45, 85), 1.0, 1),
                                             (110, (20, 30), (75, 120), 1.2, 1),
                                             (34, (40, 60), (100, 150), 1.6, 2)]), frames, fade)
    if kind == "sleet":
        layers = _rain(rng, w, h, [(90, (9, 14), (45, 80), 1.0, 1), (30, (18, 26), (80, 120), 1.2, 1)])
        ice = _Layer((246, 250, 255), halo=0.3)
        for _ in range(70):     # ice pellets: short bright dashes, falling with the rain
            ice.items.append((rng.uniform(0, w), rng.uniform(0, h), rng.uniform(3, 6), rng.uniform(170, 245),
                              max(1, int(round(2.2 * SS))), 1))
        return _fall(w, h, layers + [ice], frames, fade)
    if kind == "snow_light":
        return _snow_frames(rng, w, h, [(90, (0.7, 1.2), (120, 200), 26, 0),
                                        (45, (1.4, 2.2), (170, 235), 46, 0),
                                        (10, (2.6, 3.6), (130, 200), 80, 1.1)], frames, fade)
    if kind == "snow_heavy":
        return _snow_frames(rng, w, h, [(280, (0.7, 1.3), (120, 200), 32, 0),
                                        (130, (1.5, 2.4), (170, 240), 56, 0),
                                        (32, (2.8, 4.0), (130, 210), 96, 1.1)], frames, fade)
    if kind == "dust":
        return _dust_frames(rng, w, h, frames, fade)
    raise ValueError("unknown animation " + kind)


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
