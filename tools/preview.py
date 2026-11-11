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
        d = ImageDraw.Draw(self.im)
        d.arc([cx - r - w / 2, cy - r - w / 2, cx + r + w / 2, cy + r + w / 2], min(a0, a1), max(a0, a1), fill=color, width=w)


def hexrgb(v):
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255)


def date_row(f, L, s):
    d = L["date"]
    f.put("sm/wk%d.png" % (s["wd"] - 1), *d["wk"])
    dd = "%02d" % s["day"]
    f.put("sm/%s.png" % dd[0], *d["dd"])
    f.put("sm/%s.png" % dd[1], d["dd"][0] + L["g"]["sm"]["w"]["0"], d["dd"][1])
    f.put("sm/mo%d.png" % (s["month"] - 1), *d["mo"])


def render(root, L, tod="dusk", pick=0, s=SAMPLE, frame=1):
    f = Face(root, L)
    f.put("bg/%s_%d.png" % (tod, pick % L["bgpool"][tod]), 0, 0)
    # weather wash + one animation frame for the sample condition
    f.put(L["fx"]["wash"][s["cond"]], 0, 0)
    f.put(L["fx"]["frames"][frame][s["cond"]], 0, 0)

    # compass ring rotated so N points north, fixed index mark at the top
    ring = Image.open(os.path.join(f.img, "bezel/ring.png")).convert("RGBA")
    ring = ring.rotate(s["heading"], resample=Image.BICUBIC)
    f.im.alpha_composite(ring)
    f.put("bezel/lubber.png", L["W"] / 2 - 8, 0)

    w = L["weather"]
    f.item(w["cond"], "weather/%d" % s["cond"], s["temp"])
    f.item(w["wind"], "wind", s["wind"], ["u_kmh"])
    f.item(w["hum"], "drop", s["hum"])
    f.item(w["alt"], "alt", s["alt"], ["u_m"])

    date_row(f, L, s)
    f.item(L["sun"]["rise"], "sunrise", s["rise"], set_name="xs")
    f.item(L["sun"]["set"], "sunset", s["set"], set_name="xs")

    t = L["time"]
    digits = "%02d%02d" % (s["h"], s["m"])
    for i in range(4):
        f.put("time/%s.png" % digits[i], t["x"][i], t["y"])
    f.put("time/colon.png", t["colon"], t["y"])
    ss = "%02d" % s["s"]
    for i in range(2):
        f.put("sec/%s.png" % ss[i], t["sec"]["x"][i], t["sec"]["y"])

    gc = L["gauge_colors"]
    for k, frac, val in (("steps", min(1, s["steps"] / s["goal"]), s["steps"]), ("charge", s["charge"] / 100, s["charge"])):
        gg = L["gauges"][k]
        f.arc(gg["cx"], gg["cy"], gg["r"], gg["w"], -90, 270, hexrgb(gc["track"]))
        f.arc(gg["cx"], gg["cy"], gg["r"], gg["w"], -90, -90 + 360 * frac, hexrgb(gc[k]))
        f.put("icon/%s.png" % k, *gg["icon"])
        f.run("gn", str(val), gg["box"], "c")
        f.put("cap/%s.png" % k, *gg["cap"])
    h = L["heart"]
    f.put("icon/heart.png", *h["icon"])
    f.run("num", str(s["hr"]), h["box"], "c")
    f.put("cap/heart.png", *h["cap"])

    for k, val, units in (("recovery", s["recovery"], ["u_h"]), ("sleep", s["sleep"], [])):
        h = L["health"][k]
        g = L["g"]["num"]
        keys = [KEYS.get(ch, ch) for ch in val] + units
        total = h["icon_w"] + 5 + sum(g["w"][q] for q in keys)
        x = h["cx"] - total / 2
        f.put("icon/%s.png" % k, round(x), h["icon_y"])
        f.run("num", val, {"x": round(x + h["icon_w"] + 5), "y": h["y"], "w": 0}, units=units)
        f.put("cap/%s.png" % k, *h["cap"])

    for k, val, units in (("vo2", s["vo2"], []), ("hrv", s["hrv"], ["u_ms"])):
        fz = L["fitness"][k]
        g = L["g"]["xs"]
        keys = [KEYS.get(ch, ch) for ch in val] + units
        total = fz["cap_w"] + 4 + sum(g["w"][q] for q in keys)
        x = fz["cx"] - total / 2
        f.put("cap/%s.png" % k, round(x), fz["cap_y"])
        f.run("xs", val, {"x": round(x + fz["cap_w"] + 4), "y": fz["y"], "w": 0}, units=units)

    bt = L["batt"]
    g = L["g"]["xs"]
    text = str(s["batt"]) + "%"
    keys = [KEYS.get(ch, ch) for ch in text]
    total = bt["icon_w"] + 3 + sum(g["w"][k] for k in keys)
    x = bt["cx"] - total / 2
    f.put("icon/batt.png", round(x), bt["icon_y"])
    f.run("xs", text, {"x": round(x + bt["icon_w"] + 3), "y": bt["y"], "w": 0})
    return finish(f.im)


def render_aod(root, L, s=SAMPLE):
    f = Face(root, L)
    a = L["aod"]
    digits = "%02d%02d" % (s["h"], s["m"])
    for i in range(4):
        f.put("aod/%s.png" % digits[i], a["x"][i], a["y"])
    f.put("aod/colon.png", a["colon"], a["y"])
    date_row(f, L, s)
    return finish(f.im)


def finish(im):
    w = im.size[0]
    mask = Image.new("L", (w * 4, w * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, w * 4 - 1, w * 4 - 1], fill=255)
    mask = mask.resize((w, w), Image.LANCZOS)
    out = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


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
