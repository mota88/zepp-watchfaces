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
import re
import shutil

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

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
PHOTO_DIM = 0                   # 0..255: darkening over every photo
# Photos brighter than this behind the data (mean, 0..1) get a softer exposure, so white
# text stays readable; dark photos are left alone. None = off.
PHOTO_MAX_MEAN = 0.40
PHOTO_CLARITY = 15              # local contrast ("clarity"), 0 = off
PHOTO_SHARPEN = 80              # unsharp-mask strength after shrinking to 466 px, 0 = off
PHOTO_SATURATION = 1.08         # 1.0 = unchanged
PHOTO_VIGNETTE = 0.45           # 0..1: darkening at the screen edge, behind the compass ring
# Photos are saved without transparency so the watch stores them as 16-bit colour
# (RGB565, smooth gradients) instead of a 256-colour palette (blotchy). Costs about
# 0.45 MB per photo on the watch instead of 0.22 MB.
PHOTO_16BIT = True
BEZEL_R = 206                   # compass bezel: radius of the N/E/S/W letter centres
RING_TRACK_ALPHA = 70           # 0..255: opacity of the ring gauges' track (in the ring's colour)
BATTERY_LOW = 20                # at or below this %, the battery shows in the warning colour

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ROOT = os.path.join(REPO, "meridian")   # the watch face project (app.json, watchface/, assets/)
FONT = os.path.join(HERE, "fonts", "barlow-condensed-latin-%d-normal.woff")
PHOTOS = os.path.join(REPO, "photos")
REVIEW_SHEET = os.path.join(PHOTOS, "review_sheet.jpg")   # not in git, like the photos
TODS = ("dawn", "day", "dusk", "night")
# Background photos: photos/<dawn|day|dusk|night>/ for any weather, and optionally
# photos/<time of day>/<weather>/ for photos that match the weather, one folder per main
# condition (MOODS). The face picks from the pool for the current time of day and today's
# weather, and changes photo every hour. Crop per photo lives in photos/crops.json (see
# photo_crop).
MOODS = ("clear", "clouds", "overcast", "rain", "storm", "snow", "sleet", "fog", "haze", "dust")
# Weather code (0..28) -> folder; codes not listed (sunny, clear night, unknown) use "clear".
# Storms are the codes with the dark storm tint (thunderstorms and heavy rainstorms).
WEATHER_MOOD = {0: "clouds", 26: "clouds", 4: "overcast",
                1: "rain", 5: "rain", 7: "rain", 10: "rain", 24: "rain", 27: "rain",
                15: "storm", 18: "storm", 20: "storm", 21: "storm",
                2: "snow", 6: "snow", 8: "snow", 9: "snow", 16: "snow",
                12: "sleet", 19: "sleet",
                13: "fog", 14: "haze", 11: "dust", 17: "dust", 22: "dust", 23: "dust"}
# Where to look when a folder has no photos (for this time of day, or for its twin: dawn
# and dusk share photos), in order; "any" is the time of day's own folder.
MOOD_FALLBACK = {
    "clear": ("any", "clouds"),
    "clouds": ("overcast", "any", "clear"),
    "overcast": ("clouds", "any", "fog", "rain"),
    "rain": ("storm", "any", "overcast", "clouds"),
    "storm": ("rain", "any", "overcast", "clouds"),
    "snow": ("sleet", "any", "overcast", "clouds"),
    "sleet": ("snow", "rain", "any", "overcast", "clouds"),
    "fog": ("haze", "any", "overcast", "clouds"),
    "haze": ("fog", "dust", "any", "clouds", "clear"),
    "dust": ("haze", "fog", "any", "clear"),
}
PHOTO_CROP_DEFAULT = {"x": 0.5, "y": 0.5, "zoom": 1.0, "ev": 0.0}
# Used to work out sunrise/sunset when the watch gives no sun times (Madrid).
HOME = {"lat": 40.4168, "lon": -3.7038}
FX_H = H                        # height of the weather animation layer (from the top)
# Review mode, to check photos on the watch: tap the time for the next photo (every photo
# in the pools, plus any other folder under photos/ except unused/), each shown with weather
# that matches its folder, whatever the real weather, with its name and the condition at
# the top. Off for normal use. Either way, a contact sheet of the same list is written to
# photos/review_sheet.jpg (not in git) to check photos without installing.
REVIEW = False
REVIEW_SKIP = ("unused",)
# Review: the conditions the photos of each folder take turns through (by day, at night).
# Photos straight in a time-of-day folder (any weather) take the conditions that would
# fall back to them.
REVIEW_WEATHER = {
    "clear": ([3], [28]),
    "clouds": ([0], [26]),
    "overcast": ([4], [4]),
    "rain": ([5, 10, 1], [27, 10, 7]),
    "storm": ([15, 21, 20], [15, 21, 20]),
    "snow": ([6, 9, 16], [6, 9, 16]),
    "sleet": ([12, 19], [12, 19]),
    "fog": ([13], [13]),
    "haze": ([14], [14]),
    "dust": ([11, 22, 17], [11, 22, 17]),
}
# ... and these are each shown at least once: sunny, clear night, cloudy, overcast, light and
# heavy rain, thunderstorm, light and heavy snow, sleet, fog, haze, sandstorm
REVIEW_MAIN = (3, 28, 0, 4, 5, 10, 15, 6, 9, 12, 13, 14, 11)
NIGHT_CODES = (26, 27, 28)

COLORS = {
    # values are white; coral is the one text accent (weekday, seconds); the metric
    # colours below are only used for rings and icons
    "text": (255, 255, 255),
    "date": (255, 255, 255),
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
    "bezel": (215, 215, 215),
    "north": (255, 80, 70),
    "aod": (255, 255, 255),
    "warning": (255, 78, 66),    # low battery
}

# Weekday (Monday first) and month abbreviations per language, uppercase, as the face
# shows them. The face picks the watch's language (Zepp language codes in ZEPP_LANGS);
# languages missing here, or needing letters the bundled font lacks (e.g. Polish, Czech,
# Turkish, or non-Latin scripts), show English.
DATE_NAMES = {
    "en": ("MON TUE WED THU FRI SAT SUN", "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC"),
    "es": ("LUN MAR MIÉ JUE VIE SÁB DOM", "ENE FEB MAR ABR MAY JUN JUL AGO SEP OCT NOV DIC"),
    "ca": ("DL DT DC DJ DV DS DG", "GEN FEBR MARÇ ABR MAIG JUNY JUL AG SET OCT NOV DES"),
    "fr": ("LUN MAR MER JEU VEN SAM DIM", "JANV FÉVR MARS AVR MAI JUIN JUIL AOÛT SEPT OCT NOV DÉC"),
    "de": ("MO DI MI DO FR SA SO", "JAN FEB MÄR APR MAI JUN JUL AUG SEP OKT NOV DEZ"),
    "it": ("LUN MAR MER GIO VEN SAB DOM", "GEN FEB MAR APR MAG GIU LUG AGO SET OTT NOV DIC"),
    "pt": ("SEG TER QUA QUI SEX SÁB DOM", "JAN FEV MAR ABR MAI JUN JUL AGO SET OUT NOV DEZ"),
    "nl": ("MA DI WO DO VR ZA ZO", "JAN FEB MRT APR MEI JUN JUL AUG SEP OKT NOV DEC"),
    "sv": ("MÅN TIS ONS TORS FRE LÖR SÖN", "JAN FEB MARS APR MAJ JUNI JULI AUG SEP OKT NOV DEC"),
    "da": ("MAN TIRS ONS TORS FRE LØR SØN", "JAN FEB MAR APR MAJ JUN JUL AUG SEP OKT NOV DEC"),
    "nb": ("MAN TIR ONS TOR FRE LØR SØN", "JAN FEB MAR APR MAI JUN JUL AUG SEP OKT NOV DES"),
    "fi": ("MA TI KE TO PE LA SU", "TAMMI HELMI MAALIS HUHTI TOUKO KESÄ HEINÄ ELO SYYS LOKA MARRAS JOULU"),
    "ro": ("LUN MAR MIE JOI VIN SÂM DUM", "IAN FEB MAR APR MAI IUN IUL AUG SEPT OCT NOI DEC"),
    "hu": ("H K SZE CS P SZO V", "JAN FEBR MÁRC ÁPR MÁJ JÚN JÚL AUG SZEPT OKT NOV DEC"),
    "id": ("SEN SEL RAB KAM JUM SAB MIN", "JAN FEB MAR APR MEI JUN JUL AGU SEP OKT NOV DES"),
    "ms": ("ISN SEL RAB KHA JUM SAB AHD", "JAN FEB MAC APR MEI JUN JUL OGO SEP OKT NOV DIS"),
}
# Zepp OS language codes (getLanguage(), see the Zepp docs' language list) -> DATE_NAMES key
ZEPP_LANGS = {2: "en", 3: "es", 6: "fr", 7: "de", 8: "id", 10: "it", 15: "pt", 16: "nl", 20: "pt",
              21: "ro", 25: "ca", 26: "fi", 27: "nb", 28: "da", 29: "sv", 30: "hu", 31: "ms"}

# glyph keys -> characters (file names avoid punctuation)
PUNCT = {"minus": "-", "dot": ".", "colon": ":", "slash": "/", "pct": "%", "deg": "°"}
UNITS = {"kmh": "km/h", "m": "m", "h": "h", "ms": "ms", "k": "k"}

# digit sets: name -> (weight, size, colour, shadow, outline, extras)
SETS = {
    "time": (600, 108, COLORS["text"], True, False, False),
    "sec": (600, 44, COLORS["seconds"], True, False, False),
    "aod": (600, 108, COLORS["aod"], False, True, False),
    "num": (600, 38, COLORS["text"], True, False, True),     # heart rate, recovery, sleep
    "gn": (600, 28, COLORS["text"], True, False, True),      # numbers inside rings
    "sm": (600, 26, COLORS["text"], True, False, True),      # weather, date, sun, VO2max, HRV, battery
    "bw": (600, 26, COLORS["warning"], True, False, True),   # the battery when low (same metrics as sm)
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
        im = im.convert("RGBA")       # with alpha: 8-bit palette + alpha on the watch
    im.save(path, optimize=True)


def vignette_mask(w, h, strength, start=0.72):
    """Darkening (L mask) that starts at `start` of the radius and reaches `strength`
    at the edge of the round screen: under the compass ring, not over the data."""
    g = Image.radial_gradient("L").resize((w, h), Image.BICUBIC)   # 0 centre .. ~180 at the edge
    lut = []
    for v in range(256):
        t = min(1.0, max(0.0, (v / 180.3 - start) / (1 - start)))
        lut.append(int(round(255 * strength * t * t * (3 - 2 * t))))
    return g.point(lut)


def save_photo(im, path, grade=True):
    """Opaque background: local contrast, sharpening, colour and vignette, saved without
    alpha so the watch keeps it 16-bit. grade=False: vignette only (generated skylines)."""
    rgb = im.convert("RGB")
    if grade and PHOTO_CLARITY:
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=18, percent=PHOTO_CLARITY, threshold=0))
    if grade and PHOTO_SHARPEN:
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=0.8, percent=PHOTO_SHARPEN, threshold=1))
    if grade and PHOTO_SATURATION != 1.0:
        rgb = ImageEnhance.Color(rgb).enhance(PHOTO_SATURATION)
    if PHOTO_VIGNETTE:
        rgb = Image.composite(Image.new("RGB", rgb.size, (0, 0, 0)), rgb, vignette_mask(*rgb.size, PHOTO_VIGNETTE))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # no alpha channel -> Zeus converts it to RGB565 instead of a 256-colour palette
    (rgb if PHOTO_16BIT else rgb.convert("RGBA")).save(path, optimize=True)


def photo_crop(v):
    """A photos/crops.json entry -> {"x", "y", "zoom", "ev"}. Accepted forms:
    [y, zoom] (vertical focus only), [x, y, zoom], or {"x": .., "y": .., "zoom": .., "ev": ..}
    with any subset of keys. x, y: focus point, 0 = left/top .. 1 = right/bottom;
    zoom >= 1; ev: exposure change in stops, on top of the automatic one."""
    c = dict(PHOTO_CROP_DEFAULT)
    if isinstance(v, dict):
        c.update({k: float(v[k]) for k in c if k in v})
    elif isinstance(v, (list, tuple)) and len(v) == 2:
        c["y"], c["zoom"] = map(float, v)
    elif isinstance(v, (list, tuple)) and len(v) >= 3:
        c["x"], c["y"], c["zoom"] = map(float, v[:3])
    return c


def load_photo(path, crop):
    return city.from_photo(path, W, BG_H, FADE, crop["x"], crop["y"], crop["zoom"], PHOTO_DIM,
                           PHOTO_MAX_MEAN, crop["ev"])


def short_name(name):
    """A photo's name for the review label: Unsplash downloads lose their photo id."""
    return re.sub(r"-[A-Za-z0-9_-]{11}-unsplash$", "", name)


def bg_options(pool, tod, mood):
    """The (time of day, folder) pairs the face picks a photo from for this weather, as in
    index.js: the folder or the first of its fallbacks with photos, for this time of day or
    its twin (dawn and dusk share photos), else whatever this time of day has."""
    twin = {"dawn": "dusk", "dusk": "dawn"}.get(tod)
    for m in (mood,) + MOOD_FALLBACK[mood]:
        opts = [(t, m) for t in (tod, twin) if t and pool.get(t, {}).get(m)]
        if opts:
            return opts
    return [(tod, next(iter(pool[tod])))]


def review_weather(entries, pool):
    """Review list [bg, folder, "name - condition", weather code] from [bg, folder, name,
    time of day, mood]: photos of a folder take turns through its REVIEW_WEATHER conditions
    (photos for any weather through those of the folders that fall back to them), then one
    more entry for each of REVIEW_MAIN not shown yet, on a photo the face would pick for it."""
    turn, out = {}, []
    for bg, folder, name, tod, mood in entries:
        night = tod == "night"
        if mood in REVIEW_WEATHER:
            codes = REVIEW_WEATHER[mood][night]
        else:
            uses = [m for m in MOODS if (tod, mood) in bg_options(pool, tod, m)] or list(MOODS)
            codes = [c for m in uses for c in REVIEW_WEATHER[m][night]]
        k = turn.get((tod, mood), 0)
        turn[(tod, mood)] = k + 1
        out.append([bg, folder, name, codes[k % len(codes)]])
    for code in REVIEW_MAIN:
        if not entries or any(e[3] == code for e in out):
            continue
        mood = WEATHER_MOOD.get(code, "clear")
        pick = None
        for tod in ("night",) if code in NIGHT_CODES else ("day", "dusk", "dawn", "night"):
            opts = bg_options(pool, tod, mood)
            pick = next((e for e in entries if (e[3], e[4]) in opts), None)
            if pick:
                break
        pick = pick or entries[0]
        out.append([pick[0], pick[1], pick[2], code])
    return [[bg, folder, "%s - %s" % (name, fx.WEATHER_NAMES[code]), code] for bg, folder, name, code in out]


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

    # -- backgrounds: a photo pool per time of day and weather ---------------------------
    crops = {}
    cp = os.path.join(PHOTOS, "crops.json")
    if os.path.exists(cp):
        crops = {k: v for k, v in json.load(open(cp)).items() if not k.startswith("_")}
    pool = {}                   # time of day -> {"any" or mood: number of photos}
    review = []
    photo_info = {}             # bg image -> {"mean", "ev"}: shown on the review sheet

    def add_photo(src, key, out):
        im, info = load_photo(src, photo_crop(crops.get(key)))
        save_photo(im, rel(out))
        photo_info[out] = info

    def photos_in(folder):
        if not os.path.isdir(folder):
            return []
        return sorted(f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png")))

    for t in TODS:
        folder = os.path.join(PHOTOS, t)
        groups = [("any", "", photos_in(folder))] + [(m, m + "/", photos_in(os.path.join(folder, m))) for m in MOODS]
        groups = [gr for gr in groups if gr[2]]
        if not groups:
            save_photo(city.base(t, W, BG_H, FADE or (BG_H, BG_H)), rel("bg/%s_any_0.png" % t), grade=False)
            pool[t] = {"any": 1}
            continue
        pool[t] = {}
        for mood, sub, files in groups:
            for i, f in enumerate(files):
                out = "bg/%s_%s_%d.png" % (t, mood, i)
                add_photo(os.path.join(folder, sub + f), t + "/" + sub + f, out)
                review.append([out, t + ("/" + mood if sub else ""), short_name(f.rsplit(".", 1)[0]), t, mood])
            pool[t][mood] = len(files)
    if REVIEW:
        # every other photo under photos/ (any folder except the ones skipped)
        extra = []
        for dirpath, _, names in os.walk(PHOTOS):
            relp = os.path.relpath(dirpath, PHOTOS)
            if relp.split(os.sep)[0] in TODS + REVIEW_SKIP:
                continue
            for f in names:
                p = os.path.join(dirpath, f)
                if f.lower().endswith((".jpg", ".jpeg", ".png")) and p != REVIEW_SHEET:
                    extra.append(os.path.join(relp, f) if relp != "." else f)
        for i, rp in enumerate(sorted(extra)):
            add_photo(os.path.join(PHOTOS, rp), rp.replace(os.sep, "/"), "bg/review_%d.png" % i)
            folder, name = os.path.split(rp.replace(os.sep, "/").rsplit(".", 1)[0])
            review.append(["bg/review_%d.png" % i, folder or ".", short_name(name), "day", "any"])
    review = review_weather(review, pool)      # also for the contact sheet when REVIEW is off

    # -- weather: tints, looping animations and flashes, chosen by weather code ----------
    fx_fade = (FX_H - 50, FX_H) if FX_H < H else None
    # every image in one IMG_LEVEL array must have the same size, so "nothing" is a
    # transparent image as large as the layer it stands in for
    save(Image.new("RGBA", (W, BG_H), (0, 0, 0, 0)), rel("fx/wash_none.png"))
    save(Image.new("RGBA", (W, FX_H), (0, 0, 0, 0)), rel("fx/none.png"))
    for k in fx.WASHES:
        save(fx.wash(k, W, BG_H, FADE), rel("fx/wash_%s.png" % k))
    # two flash images, shown one tick each: lightning then its afterglow, or a shooting star
    save(fx.flash(W, BG_H), rel("fx/flash_0.png"))
    save(fx.flash(W, BG_H, 0.5), rel("fx/flash_1.png"))
    for n in range(2):
        save(fx.meteor(W, BG_H, n), rel("fx/meteor_%d.png" % n))
    for k in fx.ANIMS:
        for n, im in enumerate(fx.anim_frames(k, W, FX_H, fx_fade)):
            save(im, rel("fx/%s_%d.png" % (k, n)))
    fx_wash, fx_flash = [], [[], []]
    fx_frames = [[] for _ in range(fx.FRAMES)]
    for code in range(29):
        wsh, an = fx.WEATHER_FX[code]
        fx_wash.append("fx/wash_%s.png" % wsh if wsh else "fx/wash_none.png")
        for n in range(2):
            fx_flash[n].append("fx/flash_%d.png" % n if code in fx.FLASH_CODES else
                               "fx/meteor_%d.png" % n if code in fx.METEOR_CODES else "fx/wash_none.png")
        slots = fx.order(an) if an else None
        for n in range(fx.FRAMES):
            fx_frames[n].append("fx/%s_%d.png" % (an, slots[n]) if an else "fx/none.png")

    # -- glyph sets -------------------------------------------------------------------
    sets = {}
    for name, (wt, size, col, sh, ol, extras) in SETS.items():
        g = GlyphSet(name, wt, size, col, sh, ol)
        g.build(extras=extras)
        sets[name] = g
    sm = sets["sm"]
    # weekday and month names for each language the font can draw: weekdays in boxes as
    # wide as the language's widest one, right-aligned against the day; months left-aligned
    notdef = sm.f.getmask("\u4e00")                      # what a letter the font lacks looks like
    lacks = lambda ch: (sm.f.getmask(ch).size, bytes(sm.f.getmask(ch))) == (notdef.size, bytes(notdef))
    word_w = lambda t: int(math.ceil(sm.f.getlength(t) + 2 * (len(t) - 1))) + 2 * sm.pad
    date_langs = {}
    for lang, (wks, mos) in DATE_NAMES.items():
        wks, mos = wks.split(), mos.split()
        assert len(wks) == 7 and len(mos) == 12, lang
        missing = sorted({ch for t in wks + mos for ch in t if lacks(ch)})
        if missing:
            print("date names: %s left out, the font lacks %s (English instead)" % (lang, "".join(missing)))
            continue
        wk_w, mo_w = max(map(word_w, wks)), max(map(word_w, mos))
        for i, w in enumerate(wks):
            sm.word("wk_%s_%d" % (lang, i), w, COLORS["accent"], wk_w, "r", 2)
        for i, m in enumerate(mos):
            sm.word("mo_%s_%d" % (lang, i), m, COLORS["date"], mo_w, "l", 2)
        date_langs[lang] = (wk_w, mo_w)
    # 12-hour clock: AM / PM, in the accent colour like the seconds
    for k in ("am", "pm"):
        sm.word(k, k.upper(), COLORS["seconds"], None, "l", 1)
    for name, g in sets.items():
        g.save(rel(name))

    # -- icons ---------------------------------------------------------------------------
    for i in range(29):
        save(halo(icons.weather(i, 26)), rel("icon/weather/%d.png" % i))
    icon_specs = {
        "steps": (icons.steps, 20, COLORS["steps"]),
        "heart": (icons.heart, 24, COLORS["heart"]),
        "charge": (icons.bolt, 20, COLORS["charge"]),
        "wind": (icons.wind, 20, COLORS["muted"]),
        "drop": (icons.drop, 18, COLORS["charge"]),
        "alt": (icons.mountain, 20, COLORS["muted"]),
        "sunrise": (lambda s, c: icons.sun_arrow(s, c, True), 20, COLORS["weather"]),
        "sunset": (lambda s, c: icons.sun_arrow(s, c, False), 20, (255, 130, 70)),
        "recovery": (icons.recovery, 26, COLORS["recovery"]),
        "sleep": (icons.sleep, 26, COLORS["sleep"]),
        "vo2": (icons.lungs, 22, COLORS["vo2"]),
        "hrv": (icons.hrv, 22, COLORS["hrv"]),
        "batt": (icons.bolt, 16, COLORS["steps"]),
        "batt_low": (icons.bolt, 16, COLORS["warning"]),
        # system status, shown by the watch only while on (left of the hours)
        "st_bt": (icons.bluetooth_off, 18, COLORS["warning"]),
        "st_dnd": (icons.dnd, 18, COLORS["bezel"]),
        "st_lock": (icons.lock, 18, COLORS["bezel"]),
    }
    isize = {"weather": (26, 26)}
    for k, (fn, s, col) in icon_specs.items():
        im = halo(fn(s, col))
        save(im, rel("icon/%s.png" % k))
        isize[k] = im.size
    # compass bezel: upright letters that the face moves around the edge, and dots that
    # stand in for the ring's ticks if the watch can't rotate it
    bez = {"N": bezel_letter("N", 34, COLORS["north"])}
    for k in ("E", "S", "W"):
        bez[k] = bezel_letter(k, 28, COLORS["bezel"])
    bez = {k: halo(im) for k, im in bez.items()}
    bez["dot"] = icons.dot(8, COLORS["bezel"])
    for k, im in bez.items():
        save(im, rel("bezel/%s.png" % k))
    # rotating compass ring (ticks only) and the fixed index mark
    save(fx.compass_ring(W), rel("bezel/ring.png"))
    # shown while the compass has no heading yet (not calibrated): all grey, not rotated
    grey = (110, 110, 110)
    save(fx.compass_ring(W, north=grey, fg=grey, dim=(80, 80, 80)), rel("bezel/ring_off.png"))
    save(fx.lubber(), rel("bezel/lubber.png"))
    # transparent image for tap areas
    save(Image.new("RGBA", (8, 8), (0, 0, 0, 0)), rel("click.png"))

    # -- layout ----------------------------------------------------------------------------
    g = {n: s.meta() for n, s in sets.items()}
    L = {"W": W, "bg_h": BG_H, "fx_h": FX_H, "g": g, "bgpool": pool, "home": HOME,
         "moods": [WEATHER_MOOD.get(code, "clear") for code in range(29)],
         "mood_chain": {m: [m] + list(MOOD_FALLBACK[m]) for m in MOODS},
         "review": review if REVIEW and review else None,   # no photos (fresh clone): normal mode
         "fx": {"wash": fx_wash, "frames": fx_frames, "flash": fx_flash, "tick": fx.TICK_MS}}

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

    key_of = {v: k for k, v in PUNCT.items()}

    def text_w(set_name, text, units=()):
        """Width of a value as the face draws it (sum of glyph advances)."""
        adv = g[set_name]["w"]
        return int(math.ceil(sum(adv[key_of.get(ch, ch)] for ch in text) + sum(adv[u] for u in units)))

    # bezel: the ring image only has ticks; upright N/E/S/W letters sit at radius r
    L["bezel"] = {"r": BEZEL_R, "letters": [[k, bez[k].size[0]] for k in ("N", "E", "S", "W")],
                  "dot": bez["dot"].size[0]}

    # weather: two rows (box widths fit the longest usual value)
    L["weather"] = centred_row(60, [("cond", "weather", text_w("sm", "-12°")),
                                    ("wind", "wind", text_w("sm", "12", ["u_kmh"]))])
    L["weather"].update(centred_row(90, [("hum", "drop", text_w("sm", "100%")),
                                         ("alt", "alt", text_w("sm", "1234", ["u_m"]))]))

    # date row: WED 11 NOV, then the next sun event (sunrise or sunset) with its icon. Laid
    # out per language, centred for its widest names, so the sun event never overlaps a month.
    # Always-on shows the date without the sun event: the same row, centred on its own.
    dy = 120
    dd_w = 2 * g["sm"]["w"]["0"] + 2 * g["sm"]["pad"]
    gap = 6                                      # px between weekday, day and month
    sun_box = text_w("sm", "18:00")
    L["dates"] = {}
    for lang, (wk_w, mo_w) in date_langs.items():
        date_vis = (wk_w - 2 * sm.pad) + gap + 2 * g["sm"]["w"]["0"] + gap + (mo_w - 2 * sm.pad)
        x0 = CX - (date_vis + 18 + isize["sunrise"][0] + 3 + sun_box) / 2
        wk_x = x0 - sm.pad                       # the box is right-aligned: the widest name starts at x0
        dd_x = wk_x + wk_w - 2 * sm.pad + gap    # images carry `pad` px of margin on each side
        mo_x = dd_x + dd_w - 2 * sm.pad + gap
        date = {"wk": [int(round(wk_x)), row(dy, "sm")], "dd": [int(round(dd_x)), row(dy, "sm")],
                "mo": [int(round(mo_x)), row(dy, "sm")]}
        shift = (CX - date_vis / 2) - x0
        L["dates"][lang] = {"wk": ["wk_%s_%d" % (lang, i) for i in range(7)],
                            "mo": ["mo_%s_%d" % (lang, i) for i in range(12)],
                            "date": date, "aod": {k: [int(round(v[0] + shift)), v[1]] for k, v in date.items()},
                            "sun": item(x0 + date_vis + 18, dy, "sunrise", sun_box, "sm", gap=3)}
    L["langs"] = {str(code): lang for code, lang in ZEPP_LANGS.items() if lang in L["dates"]}

    # time HH:MM + seconds (baseline-aligned, smaller, accent colour)
    tg, sg = g["time"], g["sec"]
    tw_d, tw_c = tg["w"]["0"] + 2, tg["w"]["colon"] + 6
    sw_d = sg["w"]["0"] + 1
    total = 4 * tw_d + tw_c + 6 + 2 * sw_d
    tx = CX - total // 2 - tg["pad"]
    ty = int(round(176 - tg["vc"]))
    t_base = ty + sets["time"].baseline
    sx = tx + 4 * tw_d + tw_c + 6 + tg["pad"] - sg["pad"]
    L["time"] = {"x": [tx, tx + tw_d, tx + 2 * tw_d + tw_c, tx + 3 * tw_d + tw_c],
                 "colon": tx + 2 * tw_d + 3, "y": ty,
                 "sec": {"x": [sx, sx + sw_d], "y": int(t_base - sets["sec"].baseline)}}
    # always-on: HH:MM centred, no seconds
    total_a = 4 * tw_d + tw_c
    ax = CX - total_a // 2 - tg["pad"]
    L["aod"] = {"x": [ax, ax + tw_d, ax + 2 * tw_d + tw_c, ax + 3 * tw_d + tw_c], "colon": ax + 2 * tw_d + 3, "y": ty}
    # 12-hour clock: AM/PM top-aligned with the digits, above the seconds (always-on: where
    # the seconds would be). A one-digit hour drops its leading zero and the row moves left
    # by half a digit, so the time stays centred.
    cap_top = lambda s, ch: sets[s].baseline + sets[s].f.getbbox(ch, anchor="ls")[1]
    ampm_y = int(round(ty + cap_top("time", "0") - cap_top("sm", "A")))
    for key, x0 in (("time", tx), ("aod", ax)):
        L[key]["ampm"] = [int(round(x0 + 4 * tw_d + tw_c + 6 + tg["pad"] - sm.pad)), ampm_y]
        L[key]["shift"] = -int(round(tw_d / 2))
    # always-on has no seconds, so AM/PM widens the row: the row moves left to stay centred
    ampm_w = max(g["sm"]["w"]["am"], g["sm"]["w"]["pm"])
    L["aod"]["ampm_shift"] = -int(round((6 + ampm_w) / 2))
    # status icons (Bluetooth lost, Do Not Disturb, screen lock): a column left of the hours,
    # mirroring the seconds on the right; each shows only while that status is on
    sw = isize["st_bt"][0]
    st_x = tx + tg["pad"] - 6 - sw
    st_h = 3 * sw + 2 * 6
    st_y0 = int(round(176 - st_h / 2))
    L["status"] = [[k, int(st_x), st_y0 + i * (sw + 6)] for i, k in enumerate(("bt", "dnd", "lock"))]

    # stats: ring gauges (steps, HybridCharge) and heart rate in the middle; no captions,
    # the icons and ring colours say what each one is
    gy, gr, gwid = 270, 44, 6
    L["gauges"] = {}
    for k, cx in (("steps", CX - 106), ("charge", CX + 106)):
        iw, ih = isize[k]
        # see-through track in the metric's own colour; the watch draws the fill on top.
        # The watch strokes arcs inside their box (radius gr), so the track does too.
        track = icons.ring(gr - gwid / 2, gwid, COLORS[k], RING_TRACK_ALPHA)
        save(track, rel("icon/track_%s.png" % k))
        L["gauges"][k] = {"cx": cx, "cy": gy, "r": gr, "w": gwid,
                          "track": [cx - track.size[0] // 2, gy - track.size[1] // 2],
                          "icon": [cx - iw // 2, gy - 15 - ih // 2],
                          "box": {"x": cx - 34, "y": row(gy + 10, "gn"), "w": 68, "h": g["gn"]["h"]}}
    iw, ih = isize["heart"]
    L["heart"] = {"icon": [CX - iw // 2, gy - 20 - ih // 2],
                  "box": {"x": CX - 44, "y": row(gy + 12, "num"), "w": 88, "h": g["num"]["h"]}}
    L["gauge_colors"] = {"steps": 0xC8F03C, "charge": 0x5AC8FA}

    # recovery and sleep: icon + large value, centred on their column
    hy = 348
    L["health"] = {}
    for k, cx in (("recovery", CX - 66), ("sleep", CX + 66)):
        iw, ih = isize[k]
        L["health"][k] = {"cx": cx, "icon_w": iw, "icon_y": hy - ih // 2, "y": row(hy, "num"),
                          "tap": [cx - 60, hy - 22, 120, 44]}
    # VO2max, battery and HRV in one row, the battery in the middle: the bottom centre stays
    # free for the watch's own indicators (offline voice prompt), as Zepp's guidelines ask.
    # VO2max and HRV keep fixed boxes (the watch may draw HRV itself); the battery is centred.
    fy = 386
    side = 46                                    # VO2max ends / HRV starts this far from the centre
    L["fitness"] = {}
    for k, sample in (("vo2", "48"), ("hrv", "96")):
        iw, ih = isize[k]
        units = ["u_ms"] if k == "hrv" else []
        x = CX - side - (iw + 5 + text_w("sm", sample, units)) if k == "vo2" else CX + side
        L["fitness"][k] = {"icon": [int(round(x)), fy - ih // 2],
                           "box": {"x": int(round(x + iw + 5)), "y": row(fy, "sm"),
                                   "w": text_w("sm", "100", units) + 4, "h": g["sm"]["h"]}}
    L["batt"] = {"y": row(fy, "sm"), "icon_y": fy - isize["batt"][1] // 2, "icon_w": isize["batt"][0], "cx": CX,
                 "low": BATTERY_LOW}

    # tap areas (transparent images sized to each area)
    tw_all = L["time"]["sec"]["x"][1] + g["sec"]["w"]["0"] + 2 * g["sec"]["pad"] - L["time"]["x"][0]
    hl = L["health"]
    taps = {
        "time": [L["time"]["x"][0], L["time"]["y"] + 8, tw_all, g["time"]["h"] - 16],
        "weather": [CX - 120, 44, 240, 32],
        "altitude": [CX, 76, 120, 28],
        "sun": [CX - 130, 104, 260, 26],
        "steps": [L["gauges"]["steps"]["cx"] - 48, gy - 48, 96, 96],
        "heart": [CX - 44, gy - 48, 88, 96],
        "charge": [L["gauges"]["charge"]["cx"] - 48, gy - 48, 96, 96],
        "recovery": hl["recovery"]["tap"],
        "sleep": hl["sleep"]["tap"],
        "vo2": [CX - side - 66, fy - 16, 66, 26],
        "battery": [CX - side, fy - 16, 2 * side, 26],
        "hrv": [CX + side, fy - 16, 80, 26],
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
    if review:
        preview.render_sheet(ROOT, L, REVIEW_SHEET, review, photo_info)
        print("review sheet: %s" % os.path.relpath(REVIEW_SHEET, REPO))
    print("assets, layout.js and previews written")


if __name__ == "__main__":
    main()
