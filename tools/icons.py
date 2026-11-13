"""Small vector icons for Meridian, drawn at 4x and scaled down."""
import math
from PIL import Image, ImageDraw, ImageChops

K = 4
SUN = (255, 196, 84)
MOON = (226, 232, 246)
CLOUD = (214, 220, 230)
DARK_CLOUD = (150, 158, 172)
RAIN = (90, 200, 250)
RED = (255, 80, 70)


class Canvas:
    """Draw in a 0..1 unit square; colours composite as separate layers."""

    def __init__(self, size):
        self.size = size
        self.s = size * K
        self.im = Image.new("RGBA", (self.s, self.s), (0, 0, 0, 0))

    def layer(self):
        return Image.new("L", (self.s, self.s), 0)

    def p(self, x, y):
        return (x * self.s, y * self.s)

    def add(self, mask, color):
        lay = Image.new("RGBA", (self.s, self.s), color + (0,))
        lay.putalpha(mask)
        self.im.alpha_composite(lay)

    def cut(self, mask):
        a = self.im.getchannel("A")
        self.im.putalpha(ImageChops.subtract(a, mask))

    def done(self):
        return self.im.resize((self.size, self.size), Image.LANCZOS)


def _ell(d, c, x0, y0, x1, y1):
    d.ellipse([c.p(x0, y0), c.p(x1, y1)], fill=255)


def _line(d, c, pts, w):
    d.line([c.p(*p) for p in pts], fill=255, width=max(1, int(w * c.s)), joint="curve")
    for p in (pts[0], pts[-1]):
        r = w * c.s / 2
        x, y = c.p(*p)
        d.ellipse([x - r, y - r, x + r, y + r], fill=255)


def _cloud_mask(c, dx=0.0, dy=0.0, sc=1.0):
    m = c.layer()
    d = ImageDraw.Draw(m)
    f = lambda x0, y0, x1, y1: _ell(d, c, dx + x0 * sc, dy + y0 * sc, dx + x1 * sc, dy + y1 * sc)
    f(0.08, 0.42, 0.46, 0.80)
    f(0.26, 0.24, 0.70, 0.68)
    f(0.52, 0.40, 0.92, 0.80)
    d.rectangle([c.p(dx + 0.27 * sc, dy + 0.55 * sc), c.p(dx + 0.72 * sc, dy + 0.80 * sc)], fill=255)
    return m


def _sun(c, cx, cy, r, rays=True):
    m = c.layer()
    d = ImageDraw.Draw(m)
    _ell(d, c, cx - r, cy - r, cx + r, cy + r)
    if rays:
        for i in range(8):
            a = math.radians(i * 45)
            _line(d, c, [(cx + math.cos(a) * r * 1.45, cy + math.sin(a) * r * 1.45),
                         (cx + math.cos(a) * r * 1.95, cy + math.sin(a) * r * 1.95)], 0.07)
    c.add(m, SUN)


def _moon(c, cx, cy, r):
    m = c.layer()
    d = ImageDraw.Draw(m)
    _ell(d, c, cx - r, cy - r, cx + r, cy + r)
    cutm = c.layer()
    _ell(ImageDraw.Draw(cutm), c, cx - r + r * 0.7, cy - r - r * 0.35, cx + r + r * 0.7, cy + r - r * 0.35)
    c.add(ImageChops.subtract(m, cutm), MOON)


def _drops(c, kind, color):
    m = c.layer()
    d = ImageDraw.Draw(m)
    for x in (0.32, 0.52, 0.72):
        if kind == "rain":
            _line(d, c, [(x, 0.80), (x - 0.06, 0.96)], 0.07)
        else:
            _ell(d, c, x - 0.05, 0.84, x + 0.05, 0.94)
    c.add(m, color)


def weather(index, size):
    c = Canvas(size)
    kind = {3: "sun", 28: "moon", 0: "cloud", 4: "cloud", 25: "cloud", 26: "mooncloud",
            1: "rain", 5: "rain", 7: "rain", 10: "rain", 18: "rain", 21: "rain", 24: "rain", 27: "rain",
            2: "snow", 6: "snow", 8: "snow", 9: "snow", 16: "snow",
            12: "sleet", 19: "sleet", 15: "storm", 20: "storm",
            13: "fog", 14: "fog", 11: "dust", 17: "dust", 22: "dust", 23: "dust"}.get(index, "cloud")
    if kind == "sun":
        _sun(c, 0.5, 0.5, 0.2)
    elif kind == "moon":
        _moon(c, 0.5, 0.5, 0.3)
    elif kind in ("cloud", "mooncloud"):
        if kind == "mooncloud":
            _moon(c, 0.66, 0.30, 0.2)
        else:
            _sun(c, 0.66, 0.32, 0.13)
        cm = _cloud_mask(c, 0.0, 0.08, 0.95)
        c.cut(cm)
        c.add(cm, CLOUD if index != 4 else DARK_CLOUD)
    elif kind in ("rain", "snow", "sleet", "storm"):
        c.add(_cloud_mask(c, 0.0, -0.12, 1.0), DARK_CLOUD if kind != "snow" else CLOUD)
        if kind == "storm":
            m = c.layer()
            ImageDraw.Draw(m).polygon([c.p(0.52, 0.60), c.p(0.38, 0.82), c.p(0.50, 0.82), c.p(0.44, 0.98),
                                       c.p(0.64, 0.74), c.p(0.52, 0.74), c.p(0.58, 0.60)], fill=255)
            c.add(m, SUN)
        elif kind == "sleet":
            _drops(c, "rain", RAIN)
            _drops(c, "snow", (255, 255, 255))
        else:
            _drops(c, kind, RAIN if kind == "rain" else (255, 255, 255))
    else:  # fog / dust: horizontal bars
        m = c.layer()
        d = ImageDraw.Draw(m)
        for i, (a, b) in enumerate(((0.14, 0.86), (0.24, 0.76), (0.10, 0.70), (0.30, 0.90))):
            _line(d, c, [(a, 0.25 + i * 0.17), (b, 0.25 + i * 0.17)], 0.08)
        c.add(m, CLOUD if kind == "fog" else (214, 180, 120))
    return c.done()


def heart(size, color):
    c = Canvas(size)
    m = c.layer()
    d = ImageDraw.Draw(m)
    _ell(d, c, 0.06, 0.14, 0.52, 0.58)
    _ell(d, c, 0.48, 0.14, 0.94, 0.58)
    d.polygon([c.p(0.08, 0.44), c.p(0.92, 0.44), c.p(0.5, 0.90)], fill=255)
    c.add(m, color)
    return c.done()


def steps(size, color):
    c = Canvas(size)
    m = c.layer()
    d = ImageDraw.Draw(m)
    for dx, dy in ((0.0, 0.1), (0.42, -0.06)):
        _ell(d, c, 0.12 + dx, 0.18 + dy, 0.42 + dx, 0.64 + dy)
        _ell(d, c, 0.16 + dx, 0.70 + dy, 0.38 + dx, 0.90 + dy)
    c.add(m, color)
    return c.done()


def bolt(size, color):
    c = Canvas(size)
    m = c.layer()
    ImageDraw.Draw(m).polygon([c.p(0.60, 0.04), c.p(0.18, 0.56), c.p(0.46, 0.56), c.p(0.38, 0.96),
                               c.p(0.82, 0.42), c.p(0.54, 0.42)], fill=255)
    c.add(m, color)
    return c.done()


def charge(size, color):
    """Ring with a bolt: Amazfit-style energy score."""
    c = Canvas(size)
    m = c.layer()
    d = ImageDraw.Draw(m)
    d.arc([c.p(0.06, 0.06), c.p(0.94, 0.94)], 125, 415, fill=255, width=int(0.1 * c.s))
    d.polygon([c.p(0.56, 0.20), c.p(0.30, 0.54), c.p(0.48, 0.54), c.p(0.42, 0.80),
               c.p(0.70, 0.44), c.p(0.52, 0.44)], fill=255)
    c.add(m, color)
    return c.done()


def wind(size, color):
    c = Canvas(size)
    m = c.layer()
    d = ImageDraw.Draw(m)
    _line(d, c, [(0.06, 0.36), (0.66, 0.36)], 0.09)
    _line(d, c, [(0.06, 0.58), (0.86, 0.58)], 0.09)
    _line(d, c, [(0.06, 0.80), (0.50, 0.80)], 0.09)
    d.arc([c.p(0.54, 0.12), c.p(0.86, 0.40)], 190, 100, fill=255, width=int(0.09 * c.s))
    c.add(m, color)
    return c.done()


def drop(size, color):
    c = Canvas(size)
    m = c.layer()
    d = ImageDraw.Draw(m)
    _ell(d, c, 0.2, 0.36, 0.8, 0.96)
    d.polygon([c.p(0.5, 0.02), c.p(0.22, 0.58), c.p(0.78, 0.58)], fill=255)
    c.add(m, color)
    return c.done()


def uv(size, color):
    c = Canvas(size)
    m = c.layer()
    d = ImageDraw.Draw(m)
    _ell(d, c, 0.3, 0.3, 0.7, 0.7)
    for i in range(8):
        a = math.radians(i * 45)
        _line(d, c, [(0.5 + math.cos(a) * 0.3, 0.5 + math.sin(a) * 0.3),
                     (0.5 + math.cos(a) * 0.44, 0.5 + math.sin(a) * 0.44)], 0.08)
    c.add(m, color)
    return c.done()


def mountain(size, color):
    c = Canvas(size)
    m = c.layer()
    ImageDraw.Draw(m).polygon([c.p(0.02, 0.86), c.p(0.38, 0.18), c.p(0.60, 0.56), c.p(0.72, 0.40),
                               c.p(0.98, 0.86)], fill=255)
    c.add(m, color)
    return c.done()


def _sunline(size, color, up):
    c = Canvas(size)
    m = c.layer()
    d = ImageDraw.Draw(m)
    d.pieslice([c.p(0.24, 0.44), c.p(0.76, 0.96)], 180, 360, fill=255)
    for a in (180, 225, 270, 315, 360):
        t = math.radians(a)
        _line(d, c, [(0.5 + math.cos(t) * 0.34, 0.70 + math.sin(t) * 0.34),
                     (0.5 + math.cos(t) * 0.46, 0.70 + math.sin(t) * 0.46)], 0.07)
    _line(d, c, [(0.04, 0.78), (0.96, 0.78)], 0.07)
    cut = c.layer()
    ImageDraw.Draw(cut).rectangle([c.p(0, 0.74), c.p(1, 1)], fill=255)
    m = ImageChops.subtract(m, cut)
    _line(ImageDraw.Draw(m), c, [(0.04, 0.84), (0.96, 0.84)], 0.07)
    arrow = c.layer()
    ad = ImageDraw.Draw(arrow)
    if up:
        ad.polygon([c.p(0.5, 0.0), c.p(0.36, 0.16), c.p(0.64, 0.16)], fill=255)
    else:
        ad.polygon([c.p(0.5, 0.18), c.p(0.36, 0.02), c.p(0.64, 0.02)], fill=255)
    c.add(m, color)
    c.add(arrow, color)
    return c.done()


def sunrise(size, color):
    return _sunline(size, color, True)


def sunset(size, color):
    return _sunline(size, color, False)


def compass(size, angle):
    """Ring with a needle; red tip points `angle` degrees clockwise from up."""
    c = Canvas(size)
    ring = c.layer()
    ImageDraw.Draw(ring).ellipse([c.p(0.04, 0.04), c.p(0.96, 0.96)], outline=255, width=int(0.07 * c.s))
    c.add(ring, (150, 150, 150))
    a = math.radians(angle)

    def rot(x, y):
        x, y = x - 0.5, y - 0.5
        return c.p(0.5 + x * math.cos(a) - y * math.sin(a), 0.5 + x * math.sin(a) + y * math.cos(a))

    n = c.layer()
    ImageDraw.Draw(n).polygon([rot(0.5, 0.14), rot(0.62, 0.5), rot(0.38, 0.5)], fill=255)
    s = c.layer()
    ImageDraw.Draw(s).polygon([rot(0.5, 0.86), rot(0.62, 0.5), rot(0.38, 0.5)], fill=255)
    c.add(n, RED)
    c.add(s, (220, 220, 220))
    return c.done()


def recovery(size, color):
    """Circular arrow around a plus: recovery time."""
    c = Canvas(size)
    m = c.layer()
    d = ImageDraw.Draw(m)
    d.arc([c.p(0.10, 0.10), c.p(0.90, 0.90)], 300, 230, fill=255, width=int(0.10 * c.s))
    d.polygon([c.p(0.14, 0.12), c.p(0.40, 0.18), c.p(0.20, 0.40)], fill=255)
    _line(d, c, [(0.5, 0.36), (0.5, 0.64)], 0.1)
    _line(d, c, [(0.36, 0.5), (0.64, 0.5)], 0.1)
    c.add(m, color)
    return c.done()


def sleep(size, color):
    """Crescent moon with a small star."""
    c = Canvas(size)
    m = c.layer()
    d = ImageDraw.Draw(m)
    _ell(d, c, 0.08, 0.14, 0.82, 0.88)
    cut = c.layer()
    _ell(ImageDraw.Draw(cut), c, 0.30, 0.02, 1.02, 0.74)
    m = ImageChops.subtract(m, cut)
    ImageDraw.Draw(m).polygon([c.p(0.80, 0.06), c.p(0.85, 0.20), c.p(0.98, 0.24), c.p(0.85, 0.28),
                               c.p(0.80, 0.42), c.p(0.75, 0.28), c.p(0.62, 0.24), c.p(0.75, 0.20)], fill=255)
    c.add(m, color)
    return c.done()


def lungs(size, color):
    """Two lung lobes and the windpipe: VO2max."""
    c = Canvas(size)
    m = c.layer()
    d = ImageDraw.Draw(m)
    for x0, x1 in ((0.06, 0.45), (0.55, 0.94)):
        _ell(d, c, x0, 0.30, x1, 0.96)
        d.rectangle([c.p(x0 + 0.07, 0.62), c.p(x1 - 0.07, 0.96)], fill=255)
    cut = c.layer()
    _ell(ImageDraw.Draw(cut), c, 0.38, 0.40, 0.62, 1.10)          # gap between the lobes
    m = ImageChops.subtract(m, cut)
    d = ImageDraw.Draw(m)
    _line(d, c, [(0.5, 0.04), (0.5, 0.50)], 0.1)
    _line(d, c, [(0.5, 0.44), (0.34, 0.58)], 0.08)
    _line(d, c, [(0.5, 0.44), (0.66, 0.58)], 0.08)
    c.add(m, color)
    return c.done()


def hrv(size, color):
    """Heart with a pulse line cut through it: heart rate variability."""
    c = Canvas(size)
    m = c.layer()
    d = ImageDraw.Draw(m)
    _ell(d, c, 0.06, 0.10, 0.52, 0.56)
    _ell(d, c, 0.48, 0.10, 0.94, 0.56)
    d.polygon([c.p(0.08, 0.42), c.p(0.92, 0.42), c.p(0.5, 0.92)], fill=255)
    pulse = c.layer()
    _line(ImageDraw.Draw(pulse), c, [(0.0, 0.48), (0.30, 0.48), (0.40, 0.30), (0.54, 0.68),
                                    (0.64, 0.48), (1.0, 0.48)], 0.09)
    c.add(ImageChops.subtract(m, pulse), color)
    return c.done()


def sun_arrow(size, color, up):
    """Half sun on the horizon with an arrow above (up = sunrise)."""
    c = Canvas(size)
    m = c.layer()
    d = ImageDraw.Draw(m)
    d.pieslice([c.p(0.22, 0.52), c.p(0.78, 1.08)], 180, 360, fill=255)
    _line(d, c, [(0.04, 0.86), (0.96, 0.86)], 0.08)
    cut = c.layer()
    ImageDraw.Draw(cut).rectangle([c.p(0, 0.90), c.p(1, 1)], fill=255)
    m = ImageChops.subtract(m, cut)
    d = ImageDraw.Draw(m)
    if up:
        _line(d, c, [(0.5, 0.16), (0.5, 0.44)], 0.10)
        d.polygon([c.p(0.5, -0.02), c.p(0.24, 0.26), c.p(0.76, 0.26)], fill=255)
    else:
        _line(d, c, [(0.5, 0.0), (0.5, 0.26)], 0.10)
        d.polygon([c.p(0.5, 0.48), c.p(0.24, 0.20), c.p(0.76, 0.20)], fill=255)
    c.add(m, color)
    return c.done()


def dot(size, color):
    c = Canvas(size)
    m = c.layer()
    _ell(ImageDraw.Draw(m), c, 0.2, 0.2, 0.8, 0.8)
    c.add(m, color)
    return c.done()


def ring(radius, width, color, alpha):
    """See-through track of a ring gauge: centre line at `radius`, `width` px thick."""
    size = int(math.ceil(2 * radius + width)) + 2
    s = size * K
    m = Image.new("L", (s, s), 0)
    c, r_out, r_in = s / 2, (radius + width / 2) * K, (radius - width / 2) * K
    d = ImageDraw.Draw(m)
    d.ellipse([c - r_out, c - r_out, c + r_out, c + r_out], fill=alpha)
    d.ellipse([c - r_in, c - r_in, c + r_in, c + r_in], fill=0)
    im = Image.new("RGBA", (s, s), color + (0,))
    im.putalpha(m)
    return im.resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------- status icons --
def bluetooth_off(size, color):
    """Bluetooth rune with a small cross at its lower right: the phone is disconnected."""
    c = Canvas(size)
    m = c.layer()
    d = ImageDraw.Draw(m)
    w = 0.09
    # upper left -> lower right point -> bottom of the spine -> top -> upper right point -> lower left
    pts = [(0.14, 0.30), (0.52, 0.64), (0.33, 0.86), (0.33, 0.14), (0.52, 0.36), (0.14, 0.70)]
    for a, b in zip(pts, pts[1:]):
        _line(d, c, [a, b], w)
    for a, b in (((0.68, 0.62), (0.94, 0.88)), ((0.94, 0.62), (0.68, 0.88))):
        _line(d, c, [a, b], w * 1.1)
    c.add(m, color)
    return c.done()


def dnd(size, color):
    """Plain crescent moon: Do Not Disturb (the sleep icon has a star and another colour)."""
    c = Canvas(size)
    m = c.layer()
    _ell(ImageDraw.Draw(m), c, 0.10, 0.10, 0.86, 0.86)
    cut = c.layer()
    _ell(ImageDraw.Draw(cut), c, 0.34, -0.02, 1.06, 0.70)
    c.add(ImageChops.subtract(m, cut), color)
    return c.done()


def lock(size, color):
    """Padlock: the screen is locked."""
    c = Canvas(size)
    m = c.layer()
    d = ImageDraw.Draw(m)
    d.arc([c.p(0.28, 0.08), c.p(0.72, 0.62)], 180, 360, fill=255, width=int(0.10 * c.s))
    d.line([c.p(0.28, 0.35), c.p(0.28, 0.50)], fill=255, width=int(0.10 * c.s))
    d.line([c.p(0.72, 0.35), c.p(0.72, 0.50)], fill=255, width=int(0.10 * c.s))
    d.rounded_rectangle([c.p(0.16, 0.44), c.p(0.84, 0.94)], radius=int(0.10 * c.s), fill=255)
    hole = c.layer()
    hd = ImageDraw.Draw(hole)
    _ell(hd, c, 0.43, 0.56, 0.57, 0.70)
    hd.rectangle([c.p(0.47, 0.62), c.p(0.53, 0.80)], fill=255)
    c.add(ImageChops.subtract(m, hole), color)
    return c.done()
