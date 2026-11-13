"""Weather effects (tints, looping animations, lightning, shooting stars) and the compass ring.

Animations are full-screen frames that the face cycles while the screen is on. Every
frame draws the same scene at a later moment, and the loop restarts without a visible
jump: particles move a whole number of tile periods per loop (rain, sleet, dust) or fade
in and out within it (snow, stars), slow drifts (clouds, fog) cross-fade between two
copies half a loop apart (each copy jumps back while it is invisible), and sun rays sway
back and forth. Particles are drawn at 3x and scaled down, so they are smooth, and fade
behind the central text (FOCUS) so the data stays readable.
"""
import math
import random
from PIL import Image, ImageChops, ImageDraw, ImageFilter

FRAMES = 8              # frames per loop (each costs ~0.22 MB per animation on the watch)
TICK_MS = 120           # time per frame; one loop lasts FRAMES * TICK_MS
SS = 3                  # supersampling for particles

# Zepp weather codes (0..28) -> (wash, animation). None = nothing.
WEATHER_FX = {
    0: ("cloudy", "clouds"), 1: ("rain", "rain_light"), 2: ("snow", "snow_light"), 3: (None, "sun"),
    4: ("overcast", "overcast"), 5: ("rain", "rain_light"), 6: ("snow", "snow_light"), 7: ("rain", "rain_heavy"),
    8: ("snow", "snow_heavy"), 9: ("snow", "snow_heavy"), 10: ("rain", "rain_heavy"), 11: ("dust", "dust"),
    12: ("rain", "sleet"), 13: ("fog", "fog"), 14: ("haze", "haze"), 15: ("storm", "rain_heavy"),
    16: ("snow", "snow_heavy"), 17: ("dust", "dust"), 18: ("storm", "rain_heavy"), 19: ("rain", "sleet"),
    20: ("storm", "rain_heavy"), 21: ("storm", "rain_heavy"), 22: ("dust", "dust"), 23: ("dust", "dust"),
    24: ("rain", "rain_heavy"), 25: (None, None), 26: ("cloudy", "clouds"), 27: ("rain", "rain_light"),
    28: (None, "stars"),
}
WEATHER_NAMES = ("Cloudy", "Showers", "Snow showers", "Sunny", "Overcast", "Light rain", "Light snow",
                 "Moderate rain", "Moderate snow", "Heavy snow", "Heavy rain", "Sandstorm", "Rain and snow",
                 "Fog", "Haze", "Thunderstorm", "Snowstorm", "Floating dust", "Very heavy rainstorm",
                 "Rain and hail", "Thunderstorm and hail", "Heavy rainstorm", "Dust", "Heavy sandstorm",
                 "Rainstorm", "Unknown", "Cloudy night", "Showers night", "Clear night")
# Every few seconds the face shows two "flash" images, one tick each: lightning (bright,
# then fading) in thunderstorms (their icon shows a bolt), a shooting star on clear nights.
FLASH_CODES = (15, 20)
METEOR_CODES = (28,)
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
ANIMS = ("rain_light", "rain_heavy", "sleet", "snow_light", "snow_heavy", "dust", "clouds", "overcast",
         "fog", "haze", "sun", "stars")
# Animations that need fewer distinct frames than FRAMES (saves space on the watch):
# "half" repeats after half a loop (drifts, star twinkle), "swing" plays forward then back.
REPEAT = {"clouds": "half", "overcast": "half", "fog": "half", "haze": "half", "stars": "half", "sun": "swing"}
# Particles fade behind the central text: ellipse centre x, y, radii (px at 466) and the
# strength left at its middle, per animation (1 = no fade).
FOCUS = (233, 248, 175, 150)
FOCUS_KEEP = {"clouds": 0.6, "overcast": 0.7, "fog": 0.7, "haze": 0.8, "sun": 0.55}
FOCUS_KEEP_DEFAULT = 0.35

RAIN = (205, 218, 236)
WIND = math.tan(math.radians(9))    # rain slant: horizontal px per px of fall


def order(kind, frames=None):
    """Distinct frame shown in each of the face's frame slots."""
    frames = frames or FRAMES
    mode = REPEAT.get(kind)
    if mode == "half":
        return [k % (frames // 2) for k in range(frames)]
    if mode == "swing":
        return [k if k <= frames // 2 else frames - k for k in range(frames)]
    return list(range(frames))


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


def flash(w, h, strength=1.0):
    """Lightning: the sky lights up from above (shown for a moment by the face)."""
    cx, cy, rad = w * 0.62, -h * 0.25, h * 1.5
    m = Image.new("L", (w // 2, h // 2), 0)
    px = m.load()
    for y in range(h // 2):
        for x in range(w // 2):
            d = math.hypot(2 * x - cx, 2 * y - cy) / rad
            px[x, y] = int(140 * strength * max(0.0, 1 - d) ** 1.6)
    im = Image.new("RGBA", (w, h), (226, 232, 255, 0))
    im.putalpha(m.resize((w, h), Image.BICUBIC))
    return im


def meteor(w, h, part):
    """Shooting star in the upper-left sky, in two steps (part 0, then 1) shown one tick each."""
    x0, y0, x1, y1 = w * 0.44, h * 0.07, w * 0.13, h * 0.29         # path start and end
    head, tail, peak = ((0.42, 0.20, 200), (0.80, 0.38, 255))[part]  # along the path, tail length, brightness
    hx, hy = x0 + (x1 - x0) * head, y0 + (y1 - y0) * head
    tx, ty = hx - (x1 - x0) * tail, hy - (y1 - y0) * tail
    m = Image.new("L", (w * SS, h * SS), 0)
    d = ImageDraw.Draw(m)
    n = 24
    for i in range(n):                          # tail fades towards its end
        a, b = i / n, (i + 1) / n
        d.line([((tx + (hx - tx) * a) * SS, (ty + (hy - ty) * a) * SS),
                ((tx + (hx - tx) * b) * SS, (ty + (hy - ty) * b) * SS)],
               fill=int(peak * b ** 1.8), width=int((0.8 + 1.0 * b) * SS))
    r = 1.6 * SS
    d.ellipse([hx * SS - r, hy * SS - r, hx * SS + r, hy * SS + r], fill=peak)
    m = m.resize((w, h), Image.BOX)
    glow = m.filter(ImageFilter.GaussianBlur(3)).point(lambda v: min(255, v * 2))
    im = Image.new("RGBA", (w, h), (232, 240, 255, 0))
    im.putalpha(ImageChops.lighter(m, glow.point(lambda v: v // 2)))
    return im


def _focus_mask(w, h, keep):
    """Alpha multiplier: `keep` behind the central text, rising to 1 towards the edges."""
    cx, cy, rx, ry = FOCUS
    s = w / 466.0
    m = Image.new("L", (w // 2, h // 2))
    px = m.load()
    for y in range(h // 2):
        for x in range(w // 2):
            d = math.hypot((2 * x - cx * s) / (rx * s), (2 * y - cy * s) / (ry * s))
            t = min(1.0, max(0.0, (d - 0.55) / 0.45))
            px[x, y] = int(255 * (keep + (1 - keep) * t * t * (3 - 2 * t)))
    return m.resize((w, h), Image.BICUBIC)


def _with_focus(frames, kind):
    keep = FOCUS_KEEP.get(kind, FOCUS_KEEP_DEFAULT)
    if keep >= 1:
        return frames
    w, h = frames[0].size
    mask = _focus_mask(w, h, keep)
    for f in frames:
        f.putalpha(ImageChops.multiply(f.getchannel("A"), mask))
    return frames


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


def _ramp(w, h, top_full, bottom_zero):
    """Vertical alpha profile: 255 above `top_full`, fading to 0 at `bottom_zero` (fractions
    of h). Swap the two to fade the other way."""
    r = Image.new("L", (1, h))
    for y in range(h):
        t = (y / h - top_full) / (bottom_zero - top_full)
        t = min(1.0, max(0.0, t))
        r.putpixel((0, y), int(255 * (1 - t * t * (3 - 2 * t))))
    return r.resize((w, h))


def _drift_frames(rng, w, h, color, travel, density, ramp, stretch, frames, fade):
    """A soft texture drifting sideways by `travel` px per loop (negative: to the left).
    Two copies half a loop apart cross-fade, each jumping back while it is invisible, so
    the drift never visibly restarts; the result repeats after half a loop."""
    lo, hi, peak = density
    # made taller, then squeezed to h: features come out wide and flat, like cloud banks
    n = _fractal(rng, w, int(h * stretch)).resize((w, h), Image.BICUBIC)

    def curve(v):
        t = min(1.0, max(0.0, (v / 255 - lo) / (hi - lo)))
        return int(peak * t * t * (3 - 2 * t))
    tex = ImageChops.multiply(n.point(curve), _ramp(w, h, *ramp)).filter(ImageFilter.GaussianBlur(2))
    out = []
    for k in range(frames // 2):
        t = k / frames
        a = ImageChops.offset(tex, int(round(travel * t)), 0)
        b = ImageChops.offset(tex, int(round(travel * (t + 0.5))), 0)
        im = Image.new("RGBA", (w, h), color + (0,))
        im.putalpha(Image.blend(b, a, 2 * t))          # copy a fades in as b fades out
        out.append(_bottom_fade(im, fade) if fade else im)
    return out


def _stars_frames(rng, w, h, frames, fade):
    """Clear night: small stars in the upper sky, most of them twinkling (repeats every
    half loop)."""
    half = frames // 2
    stars = []
    for _ in range(70):
        stars.append((rng.uniform(0, w), h * 0.55 * rng.random() ** 1.2, rng.choice((0.55, 0.7, 0.85, 1.0, 1.3)),
                      rng.uniform(90, 235), rng.random() < 0.65, rng.random()))
    out = []
    for k in range(half):
        m = Image.new("L", (w * SS, h * SS), 0)
        d = ImageDraw.Draw(m)
        for x, y, r, a, twinkle, ph in stars:
            v = a * (0.3 + 0.7 * (0.5 + 0.5 * math.cos(2 * math.pi * (k / half + ph)))) if twinkle else a
            rr = r * SS
            d.ellipse([x * SS - rr, y * SS - rr, x * SS + rr, y * SS + rr], fill=int(v))
        m = m.resize((w, h), Image.BOX)
        glow = m.filter(ImageFilter.GaussianBlur(1.6)).point(lambda v: min(255, v * 2))
        im = Image.new("RGBA", (w, h), (236, 242, 255, 0))
        im.putalpha(ImageChops.lighter(m, glow))
        out.append(_bottom_fade(im, fade) if fade else im)
    return out


def _sun_frames(rng, w, h, frames, fade):
    """Clear day: soft light rays from beyond the top-right edge that sway a little and
    breathe; played forward then back (frames // 2 + 1 distinct frames)."""
    half = frames // 2
    sx, sy = w * 0.86, -h * 0.10                       # the sun, just off screen
    rays = [(rng.uniform(98, 146), rng.uniform(1.2, 2.8), rng.uniform(0.55, 1.0), rng.random()) for _ in range(9)]
    hw, hh = w // 2, h // 2                            # rays are soft: draw at half size
    fall = Image.new("L", (hw, hh))                    # rays fade with distance from the sun
    px = fall.load()
    for y in range(hh):
        for x in range(hw):
            d = math.hypot(2 * x - sx, 2 * y - sy) / (1.25 * h)
            px[x, y] = int(255 * max(0.0, 1 - d) ** 1.4)
    glow = Image.new("L", (hw, hh), 0)
    gd = ImageDraw.Draw(glow)
    for i in range(30, 0, -1):
        rr = 0.42 * h / 2 * i / 30
        gd.ellipse([sx / 2 - rr, sy / 2 - rr, sx / 2 + rr, sy / 2 + rr], fill=int(120 * (1 - i / 30) ** 1.5))
    out = []
    for j in range(half + 1):
        s = j / half                                   # 0 .. 1 over the forward half of the swing
        sway = 2.0 * (1 - math.cos(math.pi * s)) / 2
        m = Image.new("L", (hw, hh), 0)
        d = ImageDraw.Draw(m)
        for ang, width, power, ph in rays:
            v = 105 * power * (0.72 + 0.28 * math.cos(math.pi * s + 2 * math.pi * ph))
            pts = [(sx / 2, sy / 2)]
            for side in (-1, 1):
                a = math.radians(ang + sway + side * width)
                pts.append((sx / 2 + math.cos(a) * h, sy / 2 + math.sin(a) * h))
            d.polygon(pts, fill=int(v))
        m = ImageChops.multiply(m.filter(ImageFilter.GaussianBlur(5)), fall)
        m = ImageChops.lighter(m, glow.filter(ImageFilter.GaussianBlur(6)))
        im = Image.new("RGBA", (w, h), (255, 238, 200, 0))
        im.putalpha(m.resize((w, h), Image.BICUBIC))
        out.append(_bottom_fade(im, fade) if fade else im)
    return out


def anim_frames(kind, w, h, fade=None, frames=None):
    """The distinct frames of an animation; order(kind) says which one each frame slot
    shows (FRAMES slots by default)."""
    frames = frames or FRAMES
    rng = random.Random(sum(map(ord, kind)))
    if kind == "rain_light":
        out = _fall(w, h, _rain(rng, w, h, [(110, (9, 14), (45, 80), 1.0, 1),
                                            (40, (18, 26), (80, 120), 1.2, 1),
                                            (10, (34, 48), (95, 135), 1.5, 2)]), frames, fade)
    elif kind == "rain_heavy":
        out = _fall(w, h, _rain(rng, w, h, [(240, (10, 16), (45, 85), 1.0, 1),
                                            (110, (20, 30), (75, 120), 1.2, 1),
                                            (34, (40, 60), (100, 150), 1.6, 2)]), frames, fade)
    elif kind == "sleet":
        layers = _rain(rng, w, h, [(90, (9, 14), (45, 80), 1.0, 1), (30, (18, 26), (80, 120), 1.2, 1)])
        ice = _Layer((246, 250, 255), halo=0.3)
        for _ in range(70):     # ice pellets: short bright dashes, falling with the rain
            ice.items.append((rng.uniform(0, w), rng.uniform(0, h), rng.uniform(3, 6), rng.uniform(170, 245),
                              max(1, int(round(2.2 * SS))), 1))
        out = _fall(w, h, layers + [ice], frames, fade)
    elif kind == "snow_light":
        out = _snow_frames(rng, w, h, [(90, (0.7, 1.2), (120, 200), 26, 0),
                                       (45, (1.4, 2.2), (170, 235), 46, 0),
                                       (10, (2.6, 3.6), (130, 200), 80, 1.1)], frames, fade)
    elif kind == "snow_heavy":
        out = _snow_frames(rng, w, h, [(280, (0.7, 1.3), (120, 200), 32, 0),
                                       (130, (1.5, 2.4), (170, 240), 56, 0),
                                       (32, (2.8, 4.0), (130, 210), 96, 1.1)], frames, fade)
    elif kind == "dust":
        out = _dust_frames(rng, w, h, frames, fade)
    elif kind == "clouds":          # a grey veil of cloud drifting right across the upper sky
        out = _drift_frames(rng, w, h, (150, 156, 168), 16, (0.28, 0.72, 120), (0.25, 0.70), 1.6, frames, fade)
    elif kind == "overcast":        # a thick, darker cloud deck over most of the sky, drifting slowly
        out = _drift_frames(rng, w, h, (112, 118, 130), 16, (0.10, 0.60, 150), (0.40, 0.85), 2.2, frames, fade)
    elif kind == "fog":             # banks of fog drifting left along the bottom
        out = _drift_frames(rng, w, h, (214, 218, 226), -16, (0.30, 0.85, 120), (0.78, 0.40), 2.6, frames, fade)
    elif kind == "haze":            # a thin warm veil over everything, drifting left
        out = _drift_frames(rng, w, h, (226, 206, 172), -16, (0.05, 0.95, 85), (0.0, 1.6), 3.0, frames, fade)
    elif kind == "sun":
        out = _sun_frames(rng, w, h, frames, fade)
    elif kind == "stars":
        out = _stars_frames(rng, w, h, frames, fade)
    else:
        raise ValueError("unknown animation " + kind)
    return _with_focus(out, kind)


# ---------------------------------------------------------------- compass ring --
def compass_ring(size, north=(255, 80, 70), fg=(235, 235, 235), dim=(140, 140, 140)):
    """Full-screen ring of ticks: every 5 degrees, longer every 30, red at north.
    The watch rotates this image; the N/E/S/W letters are separate images that the face
    keeps upright while moving them around the edge."""
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
        ln = (13 if deg == 0 else 11 if major else 6) * S
        col = (north if deg == 0 else fg if major else dim) + (255,)
        d.line([c + r_out * math.cos(a), c + r_out * math.sin(a),
                c + (r_out - ln) * math.cos(a), c + (r_out - ln) * math.sin(a)],
               fill=col, width=int((3.0 if deg == 0 else 2.4 if major else 1.4) * S))
    return im.resize((size, size), Image.LANCZOS)


def lubber(color=(255, 255, 255)):
    """Fixed index mark at 12 o'clock: the heading is read where it points."""
    S = 4
    im = Image.new("RGBA", (16 * S, 12 * S), color + (0,))
    ImageDraw.Draw(im).polygon([(0, 0), (16 * S, 0), (8 * S, 12 * S)], fill=color + (255,))
    return im.resize((16, 12), Image.LANCZOS)
