# Zepp watch faces

Zepp OS watch faces for the Amazfit Active 3 Premium (466 x 466).

```
meridian/    Meridian watch face (Zeus project: app.json, watchface/, assets/)
tools/       shared generator, weather effects, icons, preview renderer, fonts
photos/      background photos (not in git), crops.json, sources.json
```

Run the tools from the repository root, and `zeus` from the face's folder (`meridian/`).

Not in git (see `.gitignore`):

- `meridian/assets/default.r/images/`: generated. After cloning, run `python3 tools/gen_assets.py`
  (needs `pip install pillow`) before building the face.
- `photos/`: only `crops.json` and `sources.json` are tracked (see
  [Background photos and weather](#background-photos-and-weather)).
- `dist/`, `*.zab`, `*.zpk`: `zeus build` output.

## Meridian v6

City + data face.

- Top: a generated city skyline that follows the time of day (dawn, day, dusk, night),
  with a weather layer (clouds, rain, snow, fog) chosen from today's forecast.
  Use your own photos instead by putting dawn/day/dusk/night .jpg files in photos/.
- Compass bezel: the red N marker points north (only while the screen is on).
- Weather (condition, temperature, wind, humidity) and altitude, full date, HH:MM with seconds.
- Ring gauges for steps and HybridCharge, heart rate, sunrise and sunset, recovery time,
  sleep score, battery.
- Taps: weather, altitude, steps, HybridCharge, heart rate, sun times, sleep and battery open the matching watch app (IMG_CLICK areas, if the firmware offers them).
- Always-on: outlined time and the date on black (about 2% of pixels lit; Zepp's limit is 10%).

`meridian/preview/normal.png`, `variants.png` and `aod.png` are rendered from the real assets.

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
tools/fx.py                       weather animations and tints, compass ring
tools/icons.py                    icons
tools/preview.py                  preview renderer (mirrors index.js)
tools/fonts/                      Barlow Condensed (SIL Open Font License, licence included)
photos/crops.json                 crop per photo
photos/sources.json               where each photo came from
```

### Restyle

Edit `COLORS`, `SETS` or the layout section in `tools/gen_assets.py` (or the palettes in
`tools/landscape.py`), then run `python3 tools/gen_assets.py` (needs `pip install pillow`).

### Install / test

From `meridian/`: `zeus bridge`, then `connect` and `install`; the `[meridian]` lines show what loaded.

### Background photos and weather

Put photos in `photos/dawn/`, `day/`, `dusk/` and `night/` (any number, any size).
The face shows one from the pool for the current time of day and switches every hour.
Crop per photo (vertical focus 0..1, zoom) goes in `photos/crops.json`.
Dawn/day/dusk/night come from sunrise and sunset (from the watch, or calculated for `HOME` in
`tools/gen_assets.py` when the watch gives none).

The photos are not in git: they are large, and even free-licence sites (e.g. Unsplash) don't
allow redistributing them as a collection. `photos/sources.json` records where each one came
from (page, author, licence and, when known, the original download link): add an entry for
every new photo. Without photos, the generator uses the generated city skylines.

Review mode (`REVIEW` in `tools/gen_assets.py`) adds the photos from any other folder
(e.g. `photos/review/`, `photos/unused/`): tap the time to step through them, with each
photo's name shown at the top.

Weather is drawn on top of the photo, following the watch's current weather code (29 codes):
a tint (cloudy, overcast, rain, storm, snow, fog, haze, dust) and a looping animation
(light/heavy rain, storm with lightning, light/heavy snow, sleet, drifting fog or dust).
The mapping is `WEATHER_FX` in `tools/fx.py`. Re-run `python3 tools/gen_assets.py` after changes.
