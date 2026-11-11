"""Render preview images from the generated assets and layout, mirroring index.js."""
import math
import os
from PIL import Image, ImageDraw

KEYS = {"-": "minus", ".": "dot", ":": "colon", "/": "slash", "%": "pct", "°": "deg"}

SAMPLE = {
    "h": 10, "m": 9, "s": 36, "wd": 2, "day": 10, "month": 11,
    "heading": 42, "cond": 0, "temp": "14°", "wind": "15", "hum": "86%", "alt": "657",
    "steps": 8670, "goal": 10000, "hr": 86, "charge": 72,
    "rise": "07:54", "set": "18:02", "recovery": "18", "sleep": "82", "batt": 75,
    "vo2": "48", "hrv": "46",
}


class Face:
    def __init__(self, root, L):
        self.img = os.path.join(root, "assets", "default.r", "images")
        self.L = L
        self.im = Image.new("RGBA", (L["W"], L["W"]), (0, 0, 0, 255))

    def put(self, rel, x, y):
        src = Image.open(os.path.join(self.img, rel)).convert("RGBA")
        self.im.alpha_composite(src, (int(round(x)), int(round(y))))
        return src.size

    def run(self, set_name, text, box, align="l", units=None):
        g = self.L["g"][set_name]
        keys = [KEYS.get(c, c) for c in text] + (units or [])
        total = sum(g["w"][k] for k in keys)
        x = box["x"] + {"l": 0, "c": (box["w"] - total) / 2}[align] - g["pad"]
        for k in keys:
            self.put("%s/%s.png" % (set_name, k), round(x), box["y"])
            x += g["w"][k]

    def item(self, spec, icon, text, units=None, set_name="sm"):
        self.put("icon/%s.png" % icon, *spec["icon"])
        self.run(set_name, text, spec["box"], units=units)

    def arc(self, cx, cy, r, w, a0, a1, color):
        # like the watch's ARC: the stroke stays inside the box of radius r
        d = ImageDraw.Draw(self.im)
        d.arc([cx - r, cy - r, cx + r, cy + r], min(a0, a1), max(a0, a1), fill=color, width=w)


def hexrgb(v):
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255)


def date_row(f, L, s, key="date"):
    d = L[key]
    f.put("sm/wk%d.png" % (s["wd"] - 1), *d["wk"])
    dd = "%02d" % s["day"]
    f.put("sm/%s.png" % dd[0], *d["dd"])
    f.put("sm/%s.png" % dd[1], d["dd"][0] + L["g"]["sm"]["w"]["0"], d["dd"][1])
    f.put("sm/mo%d.png" % (s["month"] - 1), *d["mo"])


def render(root, L, tod="dusk", pick=0, s=SAMPLE, frame=1, bg=None, flash=0):
    """The face with sample data. bg: background image (or path under images/) instead
    of the photo pool; flash: 1 or 2 adds that step of the flash (lightning, shooting star)."""
    f = Face(root, L)
    if bg is None:
        p = L["bgpool"][tod]
        mood = "any" if "any" in p else sorted(p)[0]
        f.put("bg/%s_%s_%d.png" % (tod, mood, pick % p[mood]), 0, 0)
    elif isinstance(bg, str):
        f.put(bg, 0, 0)
    else:
        f.im.alpha_composite(bg.convert("RGBA"))
    # weather wash + one animation frame for the sample condition
    f.put(L["fx"]["wash"][s["cond"]], 0, 0)
    f.put(L["fx"]["frames"][frame % len(L["fx"]["frames"])][s["cond"]], 0, 0)
    if flash:
        f.put(L["fx"]["flash"][flash - 1][s["cond"]], 0, 0)

    # compass: ring of ticks rotated so N points north, upright letters around it,
    # fixed index mark at the top
    W = L["W"]
    ring = Image.open(os.path.join(f.img, "bezel/ring.png")).convert("RGBA")
    ring = ring.rotate(s["heading"], resample=Image.BICUBIC)
    f.im.alpha_composite(ring)
    b = L["bezel"]
    for i, (k, size) in enumerate(b["letters"]):
        a = math.radians(i * 90 - s["heading"])
        f.put("bezel/%s.png" % k, W / 2 + b["r"] * math.sin(a) - size / 2, W / 2 - b["r"] * math.cos(a) - size / 2)
    f.put("bezel/lubber.png", W / 2 - 8, 0)

    w = L["weather"]
    f.item(w["cond"], "weather/%d" % s["cond"], s["temp"])
    f.item(w["wind"], "wind", s["wind"], ["u_kmh"])
    f.item(w["hum"], "drop", s["hum"])
    f.item(w["alt"], "alt", s["alt"], ["u_m"])

    date_row(f, L, s)
    # next sun event: sunset during the day, sunrise otherwise
    hm = lambda v: int(v[:2]) * 60 + int(v[3:])
    sunset = hm(s["rise"]) <= s["h"] * 60 + s["m"] < hm(s["set"])
    f.item(L["sun"], "sunset" if sunset else "sunrise", s["set"] if sunset else s["rise"])

    t = L["time"]
    digits = "%02d%02d" % (s["h"], s["m"])
    for i in range(4):
        f.put("time/%s.png" % digits[i], t["x"][i], t["y"])
    f.put("time/colon.png", t["colon"], t["y"])
    ss = "%02d" % s["s"]
    for i in range(2):
        f.put("sec/%s.png" % ss[i], t["sec"]["x"][i], t["sec"]["y"])

    gc = L["gauge_colors"]
    st = s["steps"]
    steps = (str(st), None) if st < 10000 else ("%.1f" % (math.floor(st / 100 + 0.5) / 10), ["u_k"])
    for k, frac, (val, units) in (("steps", min(1, st / s["goal"]), steps), ("charge", s["charge"] / 100, (str(s["charge"]), None))):
        gg = L["gauges"][k]
        f.put("icon/track_%s.png" % k, *gg["track"])
        f.arc(gg["cx"], gg["cy"], gg["r"], gg["w"], -90, -90 + 360 * frac, hexrgb(gc[k]))
        f.put("icon/%s.png" % k, *gg["icon"])
        f.run("gn", val, gg["box"], "c", units)
    h = L["heart"]
    f.put("icon/heart.png", *h["icon"])
    f.run("num", str(s["hr"]), h["box"], "c")

    for k, val, units in (("recovery", s["recovery"], ["u_h"]), ("sleep", s["sleep"], [])):
        h = L["health"][k]
        g = L["g"]["num"]
        keys = [KEYS.get(ch, ch) for ch in val] + units
        total = h["icon_w"] + 5 + sum(g["w"][q] for q in keys)
        x = h["cx"] - total / 2
        f.put("icon/%s.png" % k, round(x), h["icon_y"])
        f.run("num", val, {"x": round(x + h["icon_w"] + 5), "y": h["y"], "w": 0}, units=units)

    for k, val, units in (("vo2", s["vo2"], []), ("hrv", s["hrv"], ["u_ms"])):
        fz = L["fitness"][k]
        f.put("icon/%s.png" % k, *fz["icon"])
        f.run("sm", val, fz["box"], units=units)

    bt = L["batt"]
    g = L["g"]["sm"]
    text = str(s["batt"]) + "%"
    keys = [KEYS.get(ch, ch) for ch in text]
    total = bt["icon_w"] + 3 + sum(g["w"][k] for k in keys)
    x = bt["cx"] - total / 2
    f.put("icon/batt.png", round(x), bt["icon_y"])
    f.run("sm", text, {"x": round(x + bt["icon_w"] + 3), "y": bt["y"], "w": 0})
    return finish(f.im)


def render_aod(root, L, s=SAMPLE):
    f = Face(root, L)
    a = L["aod"]
    digits = "%02d%02d" % (s["h"], s["m"])
    for i in range(4):
        f.put("aod/%s.png" % digits[i], a["x"][i], a["y"])
    f.put("aod/colon.png", a["colon"], a["y"])
    date_row(f, L, s, "date_aod")
    return finish(f.im)


def finish(im):
    w = im.size[0]
    mask = Image.new("L", (w * 4, w * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, w * 4 - 1, w * 4 - 1], fill=255)
    mask = mask.resize((w, w), Image.LANCZOS)
    out = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def render_sheet(root, L, path, info=None, cols=8, cell=233):
    """Contact sheet: every photo of L["review"] under the face, numbered like the watch's
    review mode, to choose and crop photos without installing. Shows your photos, so it
    is written next to them (photos/ is not in git)."""
    from PIL import ImageFont
    rv = L["review"]
    lab = 32
    rows = (len(rv) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cell + 8) + 8, rows * (cell + lab + 8) + 8), (24, 26, 34))
    d = ImageDraw.Draw(sheet)
    f1, f2 = ImageFont.load_default(13), ImageFont.load_default(11)
    for i, (bg, name) in enumerate(rv):
        im = render(root, L, bg=bg, s=dict(SAMPLE, cond=3)).resize((cell, cell), Image.LANCZOS)
        x, y = 8 + (i % cols) * (cell + 8), 8 + (i // cols) * (cell + lab + 8)
        sheet.paste(im, (x, y + lab), im)
        d.text((x, y + 1), "%d  %s" % (i + 1, name), font=f1, fill=(235, 235, 235))
        meta = (info or {}).get(bg)
        if meta:
            d.text((x, y + 17), "brightness %.2f   exposure %+.1f EV" % (meta["mean"], meta["ev"]),
                   font=f2, fill=(150, 150, 150))
    sheet.save(path, quality=88)


def render_weather_gif(root, L, path, tick, loops=2, cell=200):
    """Animated weather preview over the generated skylines (never over your photos, which
    may not be published). Lightning and shooting stars appear once, as on the watch (every
    few seconds)."""
    import city
    W = L["W"]
    panels = [("night", 15), ("night", 28), ("day", 3),       # thunderstorm, clear night, sunny
              ("day", 0), ("day", 8), ("dawn", 13)]           # cloudy, snow, fog
    bgs = {t: city.base(t, W, W, (W, W)) for t, _ in panels}
    n = len(L["fx"]["frames"])
    flash_at = {n + 2: 1, n + 3: 2}                          # the two flash steps, second loop
    cols = 3
    frames = []
    for k in range(n * loops):
        im = Image.new("RGB", (cols * (cell + 4) + 4, 2 * (cell + 4) + 4), (24, 26, 34))
        for i, (tod, code) in enumerate(panels):
            face = render(root, L, frame=k % n, s=dict(SAMPLE, cond=code), bg=bgs[tod], flash=flash_at.get(k, 0))
            face = face.resize((cell, cell), Image.LANCZOS)
            im.paste(face, (4 + (i % cols) * (cell + 4), 4 + (i // cols) * (cell + 4)), face)
        frames.append(im)
    # one palette for all frames (from a plain and a flash frame), no dithering: the parts
    # that don't change compress far better
    first = min(flash_at)
    mosaic = Image.new("RGB", (frames[0].width, frames[0].height * 2))
    mosaic.paste(frames[0], (0, 0))
    mosaic.paste(frames[first % len(frames)], (0, frames[0].height))
    pal = mosaic.quantize(256, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    q[0].save(path, save_all=True, append_images=q[1:], duration=tick, loop=0, optimize=True)


def render_all(root, L):
    out = os.path.join(root, "preview")
    os.makedirs(out, exist_ok=True)
    main = render(root, L, "dusk", 1, dict(SAMPLE, cond=3))
    main.save(os.path.join(out, "normal.png"))
    main.resize((314, 314), Image.LANCZOS).save(os.path.join(root, "assets", "default.r", "icon.png"))
    aod = render_aod(root, L)
    aod.save(os.path.join(out, "aod.png"))
    lit = sum(1 for p in aod.convert("L").getdata() if p > 40) / (aod.size[0] ** 2)
    print("AOD lit-pixel ratio: %.1f%% (Zepp limit: 10%%)" % (lit * 100))

    combos = [("dawn", 0, 3), ("day", 0, 4), ("dusk", 1, 3), ("night", 0, 28),
              ("day", 1, 7), ("dusk", 0, 15), ("night", 2, 8), ("dawn", 1, 13)]
    cell = 466
    sheet = Image.new("RGBA", (cell * 4 + 50, cell * 2 + 30), (24, 26, 34, 255))
    for i, (tod, pick, cond) in enumerate(combos):
        im = render(root, L, tod, pick, dict(SAMPLE, cond=cond))
        sheet.alpha_composite(im, (10 + (i % 4) * (cell + 10), 10 + (i // 4) * (cell + 10)))
    sheet.save(os.path.join(out, "variants.png"))
    render_weather_gif(root, L, os.path.join(out, "weather.gif"), L["fx"].get("tick", 120))
