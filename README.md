# Zepp watch faces

Zepp OS watch faces for the Amazfit Active 3 Premium (466 x 466).

```
meridian/    Meridian watch face (Zeus project: app.json, watchface/, assets/)
tools/       shared generator, weather effects, icons, preview renderer, fonts
photos/      background photos (not in git) and crops.json
```

Run the tools from the repository root, and `zeus` from the face's folder (`meridian/`).

Not in git (see `.gitignore`):

- `meridian/assets/default.r/images/`: generated. After cloning, run `python3 tools/gen_assets.py`
  (needs `pip install pillow`) before building the face.
- `photos/`: only `crops.json` is tracked (see
  [Background photos and weather](#background-photos-and-weather)).
- `dist/`, `*.zab`, `*.zpk`: `zeus build` output.

## Meridian v6

City + data face.

- Background: your photos (or a generated city skyline) for the time of day (dawn, day,
  dusk, night) and today's weather, with full-screen animated weather on top that follows
  the watch's current weather: rain, sleet, snow, blowing dust, sun rays, drifting clouds,
  overcast, fog and haze, stars with the odd shooting star, lightning in thunderstorms.
- Compass bezel: the ring turns so N points north, with N/E/S/W kept upright (only while
  the screen is on).
- Weather (condition, temperature, wind, humidity) and altitude, the date with the next
  sunrise or sunset, HH:MM with seconds.
- Ring gauges for steps (16.3k above 9,999) and HybridCharge, heart rate, recovery time,
  sleep score, VO2max, HRV, battery. Values are white, coral is the only text accent, and
  the metric colours are kept to the rings and icons (no text captions).
- Taps: weather, altitude, steps, HybridCharge, heart rate, sun times, sleep and battery open the matching watch app (IMG_CLICK areas, if the firmware offers them).
  The time opens the Timer (or Alarms). HRV opens HybridCharge, as there is no HRV screen to
  open and HRV is one of HybridCharge's inputs (it replaced Readiness on current firmware).
- Always-on: outlined time and the date on black (about 2% of pixels lit; Zepp's limit is 10%).

`meridian/preview/normal.png`, `variants.png`, `aod.png` and `weather.gif` are rendered from
the real assets (the GIF over the generated skylines, never over your photos).

### Where each value comes from

The face logs a `sources:` line in `zeus bridge`:

- `js` values come from `@zos/sensor` and are drawn by index.js.
- `sys:NAME` values are drawn by the watch itself (TEXT_IMG / IMG_LEVEL with a data type),
  used only if the firmware offers that data type.
- `none` means "--" on screen: no source found on this firmware.

Without system data types, temperature falls back to today's low/high from the forecast,
and wind, humidity, UV and HybridCharge show "--".

### Files

```
meridian/app.json                 project config
meridian/watchface/index.js       the face
meridian/watchface/layout.js      positions and glyph widths (generated)
meridian/assets/default.r/        images (generated, not in git); icon.png is the store preview
meridian/preview/                 preview images (generated)
tools/gen_assets.py               generates images, layout.js and previews
tools/city.py                     city skylines and photo crops
tools/landscape.py                landscapes and weather layers
tools/fx.py                       weather animations, tints and lightning, compass ring
tools/icons.py                    icons
tools/preview.py                  preview renderer (mirrors index.js), photo review sheet
tools/fonts/                      Barlow Condensed (SIL Open Font License, licence included)
photos/crops.json                 crop per photo
photos/review_sheet.jpg           every photo under the face (generated, not in git)
```

### Restyle

Edit `COLORS`, `SETS` or the layout section in `tools/gen_assets.py` (or the palettes in
`tools/landscape.py`), then run `python3 tools/gen_assets.py` (needs `pip install pillow`).
Photo processing is set by the `PHOTO_*` settings there (see below).

### Install / test

From `meridian/`: `zeus bridge`, then `connect` and `install`; the `[meridian]` lines show what loaded.

### Background photos and weather

Put photos in `photos/dawn/`, `day/`, `dusk/` and `night/` (any number, any size), and
photos that match a kind of weather in a subfolder, e.g. `photos/night/rain/`. There is one
subfolder per main condition, and the watch's 29 weather codes map onto them
(`WEATHER_MOOD` in `tools/gen_assets.py`):

| Folder | Weather codes |
|---|---|
| `clear` | sunny, clear night, unknown |
| `clouds` | cloudy, cloudy night |
| `overcast` | overcast |
| `rain` | showers, light, moderate and heavy rain, rainstorm |
| `storm` | thunderstorms (with or without hail), heavy and very heavy rainstorms |
| `snow` | snow showers, light, moderate and heavy snow, snowstorm |
| `sleet` | rain and snow, rain and hail |
| `fog` | fog |
| `haze` | haze |
| `dust` | sandstorms, dust, floating dust |

The photo follows the watch's current weather, like the weather effects and icon. A photo
layer bound to the weather code holds a photo for each of the 29 codes, rebuilt when the time
of day or the date changes. Each code gets a photo from its weather's folder, or else from the
first of its fallbacks that has photos (`MOOD_FALLBACK`: e.g. storm → rain, sleet → snow → rain,
dust → haze → fog, then the time of day's own folder, then grey skies). At dawn and dusk
it takes from either folder, as they look alike. If nothing matches, it uses whatever
that time of day has. Empty folders are fine. Photos in `photos/unused/` are left out.

The photos of each folder come in a fixed shuffled order, and every day each weather moves
one step along it, so the photo changes daily (when the folder has 2 or more). Weathers that
share a folder start at different steps, e.g. light and heavy rain, so a change of weather
brings a different photo. On watches without a current-weather data type, the photo follows
today's forecast instead.
Dawn/day/dusk/night come from sunrise and sunset (from the watch, or calculated for `HOME` in
`tools/gen_assets.py` when the watch gives none).

Crop per photo goes in `photos/crops.json`, keyed by the path under `photos/`
(unlisted photos are centred):

```
"night/shanghai.jpg": {"x": 0.35, "y": 0.5, "zoom": 1.15, "ev": -0.3}
"night/rain/shibuya_rain.jpg": {"y": 0.4}
"day/dunes.jpg": [0.4, 1.0]          (older form: vertical focus, zoom)
```

`x`, `y`: the point to keep in the middle (0 = left/top, 1 = right/bottom); `zoom` >= 1;
`ev`: exposure change in stops, on top of the automatic one. Any key can be left out.

How photos are prepared (all in `tools/gen_assets.py` and `tools/city.py`):

- Saved without transparency, so the watch keeps them 16-bit (RGB565, 0.45 MB each).
  Images with transparency become a 256-colour palette on the watch, which is what made
  skies blotchy and night photos speckled. Overlays (weather, digits, icons) need
  transparency and stay 8-bit; they have few colours, so that's fine.
- Resized in linear light, so small lights and stars keep their brightness.
- Photos brighter than `PHOTO_MAX_MEAN` behind the data are darkened softly so white text
  stays readable (the review sheet shows the brightness and the exposure applied).
- Then local contrast (`PHOTO_CLARITY`), sharpening (`PHOTO_SHARPEN`), colour
  (`PHOTO_SATURATION`) and a darker edge behind the compass ring (`PHOTO_VIGNETTE`).

The photos are not in git: they are large, and even free-licence sites (e.g. Unsplash) don't
allow redistributing them as a collection. Without photos, the generator uses the generated
city skylines.

`photos/review_sheet.jpg` shows every photo under the face with weather that matches its
folder, to check photos and crops without installing; the generator rewrites it each run.
Every photo adds 0.45 MB to the package.

Review mode (`REVIEW` in `tools/gen_assets.py`, off by default) shows the same list on the
watch: tap the time to step through every photo in the pools (plus any other folder under
`photos/`, except `photos/unused/`), each with that weather whatever the real weather, and
the folder, photo name and condition at the top. The photos of a folder take turns through
its conditions (`REVIEW_WEATHER`), and every main condition is shown at least once
(`REVIEW_MAIN`).

Weather is drawn on top of the photo, following the watch's current weather code (29 codes):
a tint (cloudy, overcast, rain, storm, snow, haze; textured for fog and dust) and a
full-screen looping animation: light/heavy rain, sleet, light/heavy snow, blowing dust,
sun rays (sunny), stars (clear night), drifting clouds (cloudy), a cloud deck (overcast),
fog banks (fog) and a warm veil (haze).
Every few seconds thunderstorms add a lightning flash and clear nights a shooting star.
Particles fade behind the central text (`FOCUS` in `tools/fx.py`) and stay strong at the edges.
Loops are seamless (8 frames, `FRAMES` and `TICK_MS` in `tools/fx.py`; about 20 MB on the
watch in total). The mapping is `WEATHER_FX` in `tools/fx.py`. Re-run
`python3 tools/gen_assets.py` after changes.
