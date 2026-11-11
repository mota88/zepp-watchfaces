#!/usr/bin/env python3
"""
Asset generator for the "Meridian" Zepp OS watch face (v3: city + data).

Renders every PNG the face needs (backgrounds, weather overlays, digits, words,
icons, compass bezel) into meridian/assets/, writes meridian/watchface/layout.js so
positions live in one place, and renders preview images built from the same assets
and layout.

Usage (from the repository root):
    pip install pillow
    python3 tools/gen_assets.py

Backgrounds: photos from photos/<dawn|day|dusk|night>/ (any size); a generated city
skyline for each time of day that has no photos.

Font: Barlow Condensed (SIL Open Font License), bundled in tools/fonts/.
"""
import json
import math
import os
import shutil

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import city
import fx
import icons
import landscape

# ---------------------------------------------------------------- settings --
W = H = 466
CX = W // 2
PREVIEW = 314
BG_H = 466                      # background photo covers the whole screen
FADE = None                     # no fade to black (set e.g. (158, 246) for a top band)
PHOTO_DIM = 0                  # 0..255: darkening over photos so the data stays readable
BEZEL_R = 216                   # compass bezel: radius of the marker centres

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ROOT = os.path.join(REPO, "meridian")   # the watch face project (app.json, watchface/, assets/)
FONT = os.path.join(HERE, "fonts", "barlow-condensed-latin-%d-normal.woff")
PHOTOS = os.path.join(REPO, "photos")
TODS = ("dawn", "day", "dusk", "night")
MOODS = ("clear", "clouds", "rain", "snow", "fog")
# Background photos: photos/<dawn|day|dusk|night>/*.jpg. The face picks one from
# the pool for the current time of day and changes it every hour. Crop per photo
# (vertical focus 0..1, zoom) lives in photos/crops.json.
PHOTO_CROP_DEFAULT = (0.5, 1.0)
# Used to work out sunrise/sunset when the watch gives no sun times (Madrid).
HOME = {"lat": 40.4168, "lon": -3.7038}
FX_H = 200                      # height of the weather animation band
# Review mode: the face cycles through every photo (including photos/unused/),
# one per minute, with its name shown, so you can pick which ones to keep.
# Set to False for the final version.
REVIEW = True

COLORS = {
    "text": (255, 255, 255),
    "date": (232, 232, 232),
    "caption": (200, 200, 200),
    "unit": (170, 170, 170),
    "steps": (200, 240, 60),     # lime
    "heart": (255, 96, 92),      # coral
    "charge": (90, 200, 250),    # cyan
    "seconds": (255, 138, 128),  # pastel red
    "accent": (255, 138, 128),   # pastel red: weekday, seconds
    "weather": (255, 196, 84),
    "recovery": (110, 220, 150),
    "sleep": (170, 140, 255),
    "vo2": (255, 150, 90),
    "hrv": (110, 220, 150),
    "muted": (160, 160, 160),
    "bezel": (170, 170, 170),
    "north": (255, 80, 70),
    "aod": (255, 255, 255),
}

WEEKDAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]   # Zepp: 1 = Monday
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

# glyph keys -> characters (file names avoid punctuation)
PUNCT = {"minus": "-", "dot": ".", "colon": ":", "slash": "/", "pct": "%", "deg": "°"}
UNITS = {"kmh": "km/h", "m": "m", "h": "h", "ms": "ms"}

# digit sets: name -> (weight, size, colour, shadow, outline, extras)
SETS = {
    "time": (600, 108, COLORS["text"], True, False, False),
    "sec": (600, 44, COLORS["seconds"], True, False, False),
    "aod": (600, 108, COLORS["aod"], False, True, False),
    "num": (600, 34, COLORS["text"], True, False, True),     # heart rate, recovery, sleep
    "gn": (600, 24, COLORS["text"], True, False, True),      # numbers inside rings
    "sm": (600, 24, COLORS["text"], True, False, True),       # weather, date, small rows
    "xs": (600, 20, COLORS["text"], True, False, True),       # sun times, VO2max, HRV, battery
}


def font(weight, size):
    return ImageFont.truetype(FONT % weight, size)


# ---------------------------------------------------------------- glyphs ----
def shadowed(mask, color, shadow):
    """Coloured glyph from an L mask, with an optional soft dark shadow."""
    out = Image.new("RGBA", mask.size, color + (0,))
    if shadow:
        sh = mask.filter(ImageFilter.GaussianBlur(2.5)).point(lambda v: int(v * 0.75))
        sh = ImageChops.offset(sh, 0, 1)
        out = Image.new("RGBA", mask.size, (0, 0, 0, 0))
        out.putalpha(sh)
    fg = Image.new("RGBA", mask.size, color + (0,))
    fg.putalpha(mask)
    out.alpha_composite(fg)
    return out


def text_mask(fnt, text, w, h, x, baseline, track=0, outline=False):
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    for ch in text:
        d.text((x, baseline), ch, font=fnt, fill=255, anchor="ls")
        x += fnt.getlength(ch) + track
    if outline:
        inner = m.filter(ImageFilter.MinFilter(5))
        m = ImageChops.subtract(m, inner)
    return m


class GlyphSet:
    def __init__(self, name, weight, size, color, shadow, outline):
        self.name, self.color, self.shadow, self.outline = name, color, shadow, outline
        self.f = font(weight, size)
        self.fu = font(500, int(size * 0.62))   # units
        self.pad = 4 if shadow or outline else 2
        tops, bots = [], []
        for ch in "0123456789-/°%:":
            l, t, r, b = self.f.getbbox(ch, anchor="ls")
            tops.append(t)
            bots.append(b)
        self.top, self.bot = min(tops), max(bots)
        self.h = int(self.bot - self.top) + 2 * self.pad
        self.baseline = self.pad - self.top
        cap_top = self.f.getbbox("0", anchor="ls")[1]
        self.vc = int(round(self.baseline + cap_top / 2))   # visual centre of digits
        self.digit_w = int(math.ceil(max(self.f.getlength(c) for c in "0123456789"))) + 2 * self.pad
        self.widths = {}
        self.images = {}

    def glyph(self, key, text, width=None, fnt=None, color=None, track=0):
        fnt = fnt or self.f
        tw = sum(fnt.getlength(c) for c in text) + track * (len(text) - 1)
        w = width or int(math.ceil(tw)) + 2 * self.pad
        x = (w - tw) / 2
        m = text_mask(fnt, text, w, self.h, x, self.baseline, track, self.outline)
        self.images[key] = shadowed(m, color or self.color, self.shadow)
        self.widths[key] = w

    def build(self, extras=True):
        for d in "0123456789":
            self.glyph(d, d, self.digit_w)
        if not extras:
            self.glyph("colon", ":")
            return
        for k, c in PUNCT.items():
            self.glyph(k, c)
        self.glyph("none", "--", color=COLORS["muted"])
        for k, t in UNITS.items():
            self.glyph("u_" + k, t, fnt=self.fu, color=COLORS["unit"])

    def word(self, key, text, color, width=None, align="c", track=1):
        fnt = self.f
        tw = sum(fnt.getlength(c) for c in text) + track * (len(text) - 1)
        w = width or int(math.ceil(tw)) + 2 * self.pad
        x = {"c": (w - tw) / 2, "l": self.pad, "r": w - self.pad - tw}[align]
        m = text_mask(fnt, text, w, self.h, x, self.baseline, track, self.outline)
        self.images[key] = shadowed(m, color, self.shadow)
        self.widths[key] = w

    def save(self, outdir):
        for k, im in self.images.items():
            save(im, os.path.join(outdir, k + ".png"))

    def meta(self):
        # "w" holds advances: each image carries `pad` px of transparent margin
        # (room for the shadow) on both sides, so neighbours overlap by 2 * pad
        return {"h": self.h, "vc": self.vc, "pad": self.pad,
                "w": {k: v - 2 * self.pad for k, v in self.widths.items()}}


def caption(text, color=None, size=13, track=1.6, shadow=True):
    f = font(500, size)
    tw = sum(f.getlength(c) for c in text) + track * (len(text) - 1)
    l, t, r, b = f.getbbox("A", anchor="ls")
    w, h = int(math.ceil(tw)) + 4, int(b - t) + 6
    m = text_mask(f, text, w, h, 2, 3 - t, track)
    return shadowed(m, color or COLORS["caption"], shadow)


def halo(im):
    """Soft dark shadow under an icon so it reads on top of photos."""
    a = im.getchannel("A").filter(ImageFilter.GaussianBlur(1.6)).point(lambda v: int(v * 0.8))
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.putalpha(a)
    out.alpha_composite(im)
    return out


def save(im, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if im.mode != "RGBA":
        im = im.convert("RGBA")       # Zeus treats PNGs without alpha as JPEG
    im.save(path, optimize=True)


# ---------------------------------------------------------------- main ------
def bezel_letter(text, size, color, disc=None):
    s = size * 4
    im = Image.new("RGBA", (s, s), (color if not disc else disc) + (0,))
    d = ImageDraw.Draw(im)
    if disc:
        d.ellipse([0, 0, s - 1, s - 1], fill=disc + (255,))
    f = font(700, int(s * (0.62 if disc else 0.82)))
    m = Image.new("L", (s, s), 0)
    ImageDraw.Draw(m).text((s / 2, s / 2 + s * 0.02), text, font=f, fill=255, anchor="mm")
    lay = Image.new("RGBA", (s, s), (255, 255, 255, 0) if disc else color + (0,))
    lay.putalpha(m)
    if disc:
        im.alpha_composite(lay)
    else:
        im = lay
    return im.resize((size, size), Image.LANCZOS)


def main():
    img_dir = os.path.join(ROOT, "assets", "default.r", "images")
    if os.path.isdir(img_dir):
        shutil.rmtree(img_dir)
    rel = lambda p: os.path.join(img_dir, p)

    # -- backgrounds: a photo pool per time of day ----------------------------------
    crops = {}
    cp = os.path.join(PHOTOS, "crops.json")
    if os.path.exists(cp):
        crops = {k: v for k, v in json.load(open(cp)).items() if not k.startswith("_")}
    pool = {}
    review = []
    for t in TODS:
        folder = os.path.join(PHOTOS, t)
        files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png"))) if os.path.isdir(folder) else []
        if not files:
            save(city.base(t, W, BG_H, FADE or (BG_H, BG_H)), rel("bg/%s_0.png" % t))
            pool[t] = 1
            continue
        for i, f in enumerate(files):
            focus, zoom = crops.get(t + "/" + f, PHOTO_CROP_DEFAULT)
            save(city.from_photo(os.path.join(folder, f), W, BG_H, FADE, focus, zoom, PHOTO_DIM), rel("bg/%s_%d.png" % (t, i)))
            review.append(["bg/%s_%d.png" % (t, i), "%s/%s" % (t, f.rsplit(".", 1)[0])])
        pool[t] = len(files)
    if REVIEW:
        # every other photo under photos/ (any folder, e.g. review/ or unused/)
        extra = []
        for dirpath, _, names in os.walk(PHOTOS):
            relp = os.path.relpath(dirpath, PHOTOS)
            if relp.split(os.sep)[0] in TODS:
                continue
            for f in names:
                if f.lower().endswith((".jpg", ".jpeg", ".png")):
                    extra.append(os.path.join(relp, f) if relp != "." else f)
        for i, rp in enumerate(sorted(extra)):
            focus, zoom = crops.get(rp.replace(os.sep, "/"), PHOTO_CROP_DEFAULT)
            save(city.from_photo(os.path.join(PHOTOS, rp), W, BG_H, FADE, focus, zoom, PHOTO_DIM), rel("bg/review_%d.png" % i))
            review.append(["bg/review_%d.png" % i, rp.replace(os.sep, "/").rsplit(".", 1)[0]])

    # -- weather: tint washes and looping animations, chosen by weather code ----------
    fx_fade = (FX_H - 50, FX_H)
    # every image in one IMG_LEVEL array must have the same size, so "nothing" is a
    # transparent image as large as the layer it stands in for
    save(Image.new("RGBA", (W, BG_H), (0, 0, 0, 0)), rel("fx/wash_none.png"))
    save(Image.new("RGBA", (W, FX_H), (0, 0, 0, 0)), rel("fx/none.png"))
    for k in fx.WASHES:
        save(fx.wash(k, W, BG_H, FADE or (BG_H, BG_H + 1)), rel("fx/wash_%s.png" % k))
    for k in fx.ANIMS:
        for n, im in enumerate(fx.anim_frames(k, W, FX_H, fx_fade)):
            save(im, rel("fx/%s_%d.png" % (k, n)))
    fx_wash = []
    fx_frames = [[] for _ in range(fx.FRAMES)]
    for code in range(29):
        wsh, an = fx.WEATHER_FX[code]
        fx_wash.append("fx/wash_%s.png" % wsh if wsh else "fx/wash_none.png")
        for n in range(fx.FRAMES):
            fx_frames[n].append("fx/%s_%d.png" % (an, n) if an else "fx/none.png")

    # -- glyph sets -------------------------------------------------------------------
    sets = {}
    for name, (wt, size, col, sh, ol, extras) in SETS.items():
        g = GlyphSet(name, wt, size, col, sh, ol)
        g.build(extras=extras)
        sets[name] = g
    sm = sets["sm"]
    wk_w = max(int(math.ceil(sm.f.getlength(w) + 2 * (len(w) - 1))) for w in WEEKDAYS) + 2 * sm.pad
    mo_w = max(int(math.ceil(sm.f.getlength(m) + 2 * (len(m) - 1))) for m in MONTHS) + 2 * sm.pad
    for i, w in enumerate(WEEKDAYS):
        sm.word("wk%d" % i, w, COLORS["accent"], wk_w, "r", 2)
    for i, m in enumerate(MONTHS):
        sm.word("mo%d" % i, m, COLORS["date"], mo_w, "l", 2)
    for name, g in sets.items():
        g.save(rel(name))

    # -- icons ---------------------------------------------------------------------------
    for i in range(29):
        save(halo(icons.weather(i, 24)), rel("icon/weather/%d.png" % i))
    icon_specs = {
        "steps": (icons.steps, 18, COLORS["steps"]),
        "heart": (icons.heart, 22, COLORS["heart"]),
        "charge": (icons.bolt, 18, COLORS["charge"]),
        "wind": (icons.wind, 18, COLORS["muted"]),
        "drop": (icons.drop, 16, COLORS["charge"]),
        "alt": (icons.mountain, 18, COLORS["muted"]),
        "sunrise": (lambda s, c: icons.sun_arrow(s, c, True), 18, COLORS["weather"]),
        "sunset": (lambda s, c: icons.sun_arrow(s, c, False), 18, (255, 130, 70)),
        "recovery": (icons.recovery, 24, COLORS["recovery"]),
        "sleep": (icons.sleep, 24, COLORS["sleep"]),
        "batt": (icons.bolt, 13, COLORS["steps"]),
    }
    isize = {"weather": (24, 24)}
    for k, (fn, s, col) in icon_specs.items():
        im = halo(fn(s, col))
        save(im, rel("icon/%s.png" % k))
        isize[k] = im.size
    # compass bezel markers
    bez = {"N": bezel_letter("N", 24, (255, 255, 255), COLORS["north"])}
    for k in ("E", "S", "W"):
        bez[k] = bezel_letter(k, 18, COLORS["bezel"])
    bez["dot"] = icons.dot(8, COLORS["bezel"])
    for k, im in bez.items():
        save(im, rel("bezel/%s.png" % k))
    # rotating compass ring and the fixed index mark
    save(fx.compass_ring(W, FONT), rel("bezel/ring.png"))
    # shown while the compass has no heading yet (not calibrated): all grey, not rotated
    grey = (110, 110, 110)
    save(fx.compass_ring(W, FONT, north=grey, fg=grey, dim=(80, 80, 80)), rel("bezel/ring_off.png"))
    save(fx.lubber(), rel("bezel/lubber.png"))
    # transparent image for tap areas
    save(Image.new("RGBA", (8, 8), (0, 0, 0, 0)), rel("click.png"))

    caps = {"steps": "STEPS", "heart": "BPM", "charge": "HYBRIDCHARGE", "recovery": "RECOVERY",
            "sleep": "SLEEP", "vo2": "VO2MAX", "hrv": "HRV"}
    csize = {}
    for k, t in caps.items():
        im = caption(t, color={"vo2": COLORS["vo2"], "hrv": COLORS["hrv"]}.get(k), size=14 if k in ("vo2", "hrv") else 13)
        save(im, rel("cap/%s.png" % k))
        csize[k] = im.size

    # -- layout ----------------------------------------------------------------------------
    g = {n: s.meta() for n, s in sets.items()}
    L = {"W": W, "bg_h": BG_H, "fx_h": FX_H, "g": g, "bgpool": pool, "home": HOME,
         "review": review if REVIEW and review else None,   # no photos (fresh clone): normal mode
         "fx": {"wash": fx_wash, "frames": fx_frames}}

    def row(cy, set_name):
        return int(round(cy - g[set_name]["vc"]))

    def item(x, cy, icon, box_w, set_name="sm", gap=4):
        """[icon][left-aligned text box] starting at x."""
        iw, ih = isize[icon]
        return {"icon": [int(x), int(cy - ih // 2)],
                "box": {"x": int(x + iw + gap), "y": row(cy, set_name), "w": box_w, "h": g[set_name]["h"]}}

    def centred_row(cy, parts, gap=14):
        """parts: (key, icon, box_w); returns dict of items centred as a group."""
        total = sum(isize[ic][0] + 4 + bw for _, ic, bw in parts) + gap * (len(parts) - 1)
        x = CX - total / 2
        out = {}
        for key, ic, bw in parts:
            out[key] = item(x, cy, ic, bw)
            x += isize[ic][0] + 4 + bw + gap
        return out

    # bezel
    L["bezel"] = {"r": BEZEL_R, "marks": [["N", 24], ["dot", 8], ["E", 18], ["dot", 8],
                                          ["S", 18], ["dot", 8], ["W", 18], ["dot", 8]]}

    # weather: two rows
    L["weather"] = centred_row(58, [("cond", "weather", 44), ("wind", "wind", 64)])
    L["weather"].update(centred_row(86, [("hum", "drop", 42), ("alt", "alt", 58)]))

    # date row: [sunrise ↑ 07:54]  TUE 10 NOV  [sunset ↓ 18:02]
    dy = 114
    dd_w = 2 * g["sm"]["w"]["0"] + 2 * g["sm"]["pad"]
    gap = 6 - 2 * sm.pad
    date_w = (wk_w - 2 * sm.pad) + 6 + 2 * g["sm"]["w"]["0"] + 6 + (mo_w - 2 * sm.pad)
    # visible width of a typical date ("TUE 10 NOV")
    vis = sm.f.getlength("TUE") + 4 + 6 + 2 * g["sm"]["w"]["0"] + 6 + sm.f.getlength("NOV") + 4
    sun_box = int(math.ceil(4 * g["xs"]["w"]["0"] + g["xs"]["w"]["colon"]))
    sun_w = isize["sunrise"][0] + 3 + sun_box
    total = sun_w + 12 + vis + 12 + sun_w
    x0 = CX - total / 2
    # weekday box is right-aligned, so its visible text ends at the box's right edge
    wk_x = x0 + sun_w + 12 + (sm.f.getlength("TUE") + 4) - wk_w + sm.pad
    dd_x = wk_x + wk_w + gap
    mo_x = dd_x + dd_w + gap
    L["date"] = {"wk": [int(wk_x), row(dy, "sm")], "dd": [int(dd_x), row(dy, "sm")], "mo": [int(mo_x), row(dy, "sm")]}
    L["sun"] = {"rise": item(x0, dy, "sunrise", sun_box, "xs", gap=3),
                "set": item(x0 + total - sun_w, dy, "sunset", sun_box, "xs", gap=3)}

    # time HH:MM + seconds (baseline-aligned, smaller, accent colour)
    tg, sg = g["time"], g["sec"]
    tw_d, tw_c = tg["w"]["0"] + 2, tg["w"]["colon"] + 6
    sw_d = sg["w"]["0"] + 1
    total = 4 * tw_d + tw_c + 6 + 2 * sw_d
    tx = CX - total // 2 - tg["pad"]
    ty = int(round(172 - tg["vc"]))
    t_base = ty + sets["time"].baseline
    sx = tx + 4 * tw_d + tw_c + 6 + tg["pad"] - sg["pad"]
    L["time"] = {"x": [tx, tx + tw_d, tx + 2 * tw_d + tw_c, tx + 3 * tw_d + tw_c],
                 "colon": tx + 2 * tw_d + 3, "y": ty,
                 "sec": {"x": [sx, sx + sw_d], "y": int(t_base - sets["sec"].baseline)}}
    # always-on: HH:MM centred, no seconds
    total_a = 4 * tw_d + tw_c
    ax = CX - total_a // 2 - tg["pad"]
    L["aod"] = {"x": [ax, ax + tw_d, ax + 2 * tw_d + tw_c, ax + 3 * tw_d + tw_c], "colon": ax + 2 * tw_d + 3, "y": ty}

    # stats: ring gauges (steps, HybridCharge) and heart rate in the middle
    gy = 268
    L["gauges"] = {}
    for k, cx in (("steps", CX - 104), ("charge", CX + 104)):
        iw, ih = isize[k]
        cw, ch = csize[k]
        L["gauges"][k] = {"cx": cx, "cy": gy, "r": 38, "w": 5,
                          "icon": [cx - iw // 2, gy - 14 - ih // 2],
                          "box": {"x": cx - 32, "y": row(gy + 8, "gn"), "w": 64, "h": g["gn"]["h"]},
                          "cap": [cx - cw // 2, gy + 50 - ch // 2]}
    iw, ih = isize["heart"]
    cw, ch = csize["heart"]
    L["heart"] = {"icon": [CX - iw // 2, gy - 22 - ih // 2],
                  "box": {"x": CX - 40, "y": row(gy + 6, "num"), "w": 80, "h": g["num"]["h"]},
                  "cap": [CX - cw // 2, gy + 50 - ch // 2]}
    L["gauge_colors"] = {"track": 0x262626, "steps": 0xC8F03C, "charge": 0x5AC8FA}

    # sunrise / sunset, recovery / sleep, battery
    # recovery and sleep: larger, with captions and big tap areas
    L["health"] = {}
    for k, cx in (("recovery", CX - 62), ("sleep", CX + 62)):
        iw, ih = isize[k]
        cw, ch = csize[k]
        L["health"][k] = {"cx": cx, "icon_w": iw, "icon_y": 350 - ih // 2, "y": row(350, "num"),
                          "cap": [cx - cw // 2, 375 - ch // 2], "tap": [cx - 56, 330, 112, 54]}
    # VO2max and HRV: small, label + value
    L["fitness"] = {}
    for k, cx in (("vo2", CX - 56), ("hrv", CX + 56)):
        cw, ch = csize[k]
        L["fitness"][k] = {"cx": cx, "cap_w": cw, "cap_y": 400 - ch // 2, "y": row(400, "xs"),
                           "box": {"x": cx - 4, "y": row(400, "xs"), "w": 50, "h": g["xs"]["h"]}}
    L["batt"] = {"y": row(426, "xs"), "icon_y": 426 - isize["batt"][1] // 2, "icon_w": isize["batt"][0], "cx": CX}

    # tap areas (transparent images sized to each area)
    tw_all = L["time"]["sec"]["x"][1] + g["sec"]["w"]["0"] + 2 * g["sec"]["pad"] - L["time"]["x"][0]
    w_a, w_b = L["weather"]["cond"], L["weather"]["alt"]
    hl = L["health"]
    taps = {
        "time": [L["time"]["x"][0], L["time"]["y"] + 8, tw_all, g["time"]["h"] - 16],
        "weather": [CX - 110, 42, 220, 30],
        "altitude": [CX, 74, 100, 26],
        "sun": [CX - 150, 100, 300, 28],
        "steps": [L["gauges"]["steps"]["cx"] - 46, 222, 92, 104],
        "heart": [CX - 40, 222, 80, 104],
        "charge": [L["gauges"]["charge"]["cx"] - 46, 222, 92, 104],
        "recovery": hl["recovery"]["tap"],
        "sleep": hl["sleep"]["tap"],
        "vo2": [CX - 112, 388, 110, 26],
        "hrv": [CX + 2, 388, 110, 26],
        "battery": [CX - 40, 414, 80, 24],
    }
    L["taps"] = {k: [int(v) for v in r] for k, r in taps.items()}
    save(Image.new("RGBA", (W, H), (0, 0, 0, 0)), rel("tap/debug.png"))
    # tap areas on the compass ring (top, bottom, left, right edges): open Compass
    L["ring_taps"] = [[CX - 90, 0, 180, 40], [CX - 70, H - 30, 140, 30], [0, CX - 90, 34, 180], [W - 34, CX - 90, 34, 180]]
    for i, (x, y, w, h) in enumerate(L["ring_taps"]):
        save(Image.new("RGBA", (w, h), (0, 0, 0, 0)), rel("tap/ring%d.png" % i))
    for k, (x, y, w, h) in L["taps"].items():
        save(Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0)), rel("tap/%s.png" % k))

    with open(os.path.join(ROOT, "watchface", "layout.js"), "w") as fh:
        fh.write("// Generated by tools/gen_assets.py: edit there, not here.\n")
        fh.write("export const L = " + json.dumps(L, separators=(",", ":")) + "\n")

    import preview
    preview.render_all(ROOT, L)
    print("assets, layout.js and previews written")


if __name__ == "__main__":
    main()
