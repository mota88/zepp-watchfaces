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
  the watch's current weather: rain, sleet, snow, blowing dust, sun rays, drifting clouds
  and fog, stars with the odd shooting star, lightning in thunderstorms.
- Compass bezel: the ring turns so N points north, with N/E/S/W kept upright (only while
  the screen is on).
- Weather (condition, temperature, wind, humidity) and altitude, the date with the next
  sunrise or sunset, HH:MM with seconds.
- Ring gauges for steps (16.3k above 9,999) and HybridCharge, heart rate, recovery time,
  sleep score, VO2max, HRV, battery. Values are white, coral is the only text accent, and
  the metric colours are kept to the rings and icons (no text captions).
- Taps: weather, altitude, steps, HybridCharge, heart rate, sun times, sleep and battery open the matching watch app (IMG_CLICK areas, if the firmware offers them).
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
photos/review_sheet.jpg           every photo under the face (generated in review mode, not in git)
```

### Restyle

Edit `COLORS`, `SETS` or the layout section in `tools/gen_assets.py` (or the palettes in
`tools/landscape.py`), then run `python3 tools/gen_assets.py` (needs `pip install pillow`).
Photo processing is set by the `PHOTO_*` settings there (see below).

### Install / test

From `meridian/`: `zeus bridge`, then `connect` and `install`; the `[meridian]` lines show what loaded.

### Background photos and weather

Put photos in `photos/dawn/`, `day/`, `dusk/` and `night/` (any number, any size), and
photos that match a kind of weather in a subfolder: `photos/night/rain/`, `photos/day/snow/`
(`clear`, `clouds`, `rain`, `snow`, `fog`). The face picks from the pool for the current time
of day and today's forecast, and switches every hour: a photo for that weather, else one
from the time of day's own folder (any weather), else one for that weather from the other
twilight (dawn and dusk look alike), else whatever that time of day has.
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

Review mode (`REVIEW` in `tools/gen_assets.py`) adds the photos from any other folder
(e.g. `photos/review/`, `photos/unused/`): tap the time to step through them, with each
photo's name shown at the top. It also writes `photos/review_sheet.jpg`: every photo under the
face, numbered as on the watch, to choose and crop photos without installing. Every photo
adds 0.45 MB to the package, so review large sets on the sheet and only a shortlist on the watch.

Weather is drawn on top of the photo, following the watch's current weather code (29 codes):
a tint (cloudy, overcast, rain, storm, snow, haze; textured for fog and dust) and a
full-screen looping animation: light/heavy rain, sleet, light/heavy snow, blowing dust,
sun rays (sunny), stars (clear night), drifting clouds (cloudy, overcast) and fog (fog, haze).
Every few seconds thunderstorms add a lightning flash and clear nights a shooting star.
Particles fade behind the central text (`FOCUS` in `tools/fx.py`) and stay strong at the edges.
Loops are seamless (8 frames, `FRAMES` and `TICK_MS` in `tools/fx.py`; about 17 MB on the
watch in total). The mapping is `WEATHER_FX` in `tools/fx.py`. Re-run
`python3 tools/gen_assets.py` after changes.
