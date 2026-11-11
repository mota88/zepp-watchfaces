// Meridian v9: city + data watch face for the Amazfit Active 3 Premium (466 x 466).
//
// Background: a photo (or city skyline) that follows the time of day (dawn, day, dusk,
// night), with full-screen weather on top (tint, looping rain/snow/dust animation and
// lightning) that follows the watch's current weather, or today's forecast without it.
// Edge: a compass bezel whose N marker points north.
// Then weather + altitude, the date, HH:MM with seconds, ring gauges for steps and
// HybridCharge, heart rate, sunrise and sunset, recovery time, sleep score, battery.
//
// Values come from two places:
//   - JS sensors (@zos/sensor): drawn by this file as rows of IMG widgets.
//   - "System" data fields (TEXT_IMG / IMG_LEVEL / ARC_PROGRESS with a data_type),
//     drawn by the watch itself, used only where this firmware offers them.
// Taps use IMG_CLICK areas bound to a data type, which open the matching watch app.
// The bridge log ("[meridian] ...") lists what each field ended up using.
import * as uiNs from '@zos/ui'
import * as sensorNs from '@zos/sensor'
import * as routerNs from '@zos/router'
import { L } from './layout'

// Shows a diagnostics panel over the face after install (tap it to close).
// The watch does not always stream console.log to `zeus bridge`, so this is the
// reliable way to see which data fields and taps this firmware offers.
const DEBUG = false

const ui = uiNs.default || uiNs
const sensor = sensorNs.default || sensorNs
const router = routerNs.default || routerNs
const W = ui.widget
const DT = ui.data_type || {}
const G = L.g
const CX = L.W / 2

// ---- logging and fail-safe blocks ------------------------------------------------
const log = (msg) => console.log('[meridian] ' + msg)
const chunked = (label, text) => {
  text = String(text)
  for (let i = 0; i < text.length; i += 240) log(label + ' [' + i / 240 + ']: ' + text.slice(i, i + 240))
}
const keysOf = (o) => (o && typeof o === 'object' ? Object.keys(o).join(',') : String(o))
const json = (v) => safe(() => JSON.stringify(v)) || String(v)
const errors = []
const sources = []
function step(name, fn) {
  try {
    fn()
  } catch (e) {
    log(name + ' FAILED: ' + e)
    errors.push(name + ': ' + e)
  }
}
function safe(fn) {
  try {
    return fn()
  } catch (e) {
    return undefined
  }
}

// ---- display levels -------------------------------------------------------------
const SL = ui.show_level || {}
const NORMAL = SL.ONLY_NORMAL
const AOD = SL.ONAL_AOD !== undefined ? SL.ONAL_AOD : SL.ONLY_AOD
const BOTH = NORMAL !== undefined && AOD !== undefined ? NORMAL | AOD : undefined
const lvl = (opts, level) => {
  if (level !== undefined) opts.show_level = level
  return opts
}

// ---- image helpers ----------------------------------------------------------------
const img = (p) => 'images/' + p
function makeImg(x, y, src, level) {
  const w = ui.createWidget(W.IMG, lvl({ x: Math.round(x), y: Math.round(y), src: src }, level))
  if (!w) throw new Error('createWidget(IMG) returned ' + w)
  w._x = Math.round(x)
  w._y = Math.round(y)
  w._src = src
  return w
}
function setSrc(w, src) {
  if (w._src !== src) {
    w.setProperty(ui.prop.SRC, src)
    w._src = src
  }
}
function show(w, on) {
  if (w._vis !== on) {
    w.setProperty(ui.prop.VISIBLE, on)
    w._vis = on
  }
}
let moveMode = 'more'
function place(w, x, y, src) {
  x = Math.round(x)
  y = Math.round(y)
  src = src || w._src
  if (w._x === x && w._y === y && w._src === src) return
  if (moveMode === 'more') {
    try {
      w.setProperty(ui.prop.MORE, { x: x, y: y, src: src })
      w._x = x
      w._y = y
      w._src = src
      return
    } catch (e) {
      moveMode = 'single'
      log('prop.MORE on IMG failed (' + e + '), using prop.X/Y')
    }
  }
  w.setProperty(ui.prop.X, x)
  w.setProperty(ui.prop.Y, y)
  w._x = x
  w._y = y
  setSrc(w, src)
}

// ---- text runs: a string drawn as a row of glyph images ---------------------------
const CHAR_KEY = { '-': 'minus', '.': 'dot', ':': 'colon', '/': 'slash', '%': 'pct', '°': 'deg' }
const toKeys = (text) => String(text).split('').map((c) => CHAR_KEY[c] || c)
const measure = (set, keys) => keys.reduce((t, k) => t + G[set].w[k], 0)

function makeRun(set, max, y, level) {
  const cells = []
  for (let i = 0; i < max; i++) {
    const c = makeImg(0, y, img(set + '/0.png'), level)
    show(c, false)
    cells.push(c)
  }
  return {
    draw(keys, x) {
      let cx = x - G[set].pad
      for (let i = 0; i < max; i++) {
        if (i < keys.length) {
          place(cells[i], cx, y, img(set + '/' + keys[i] + '.png'))
          show(cells[i], true)
          cx += G[set].w[keys[i]]
        } else {
          show(cells[i], false)
        }
      }
    },
  }
}
// text centred in a box
function centredRun(set, box, max, level) {
  const run = makeRun(set, max, box.y, level)
  return (keys) => run.draw(keys, box.x + (box.w - measure(set, keys)) / 2)
}

// ---- system data fields (the watch draws the value) -------------------------------
function dataType(names) {
  for (let i = 0; i < names.length; i++) if (DT[names[i]] !== undefined) return { name: names[i], id: DT[names[i]] }
  return null
}
function sysField(label, names, box, set, opts) {
  const t = dataType(names)
  if (W.TEXT_IMG === undefined || !t) return null
  try {
    const digits = []
    for (let i = 0; i < 10; i++) digits.push(img(set + '/' + i + '.png'))
    const o = {
      x: box.x - G[set].pad, y: box.y, w: box.w + 2 * G[set].pad, h: box.h,
      type: t.id,
      font_array: digits,
      h_space: -2 * G[set].pad,
      align_h: opts.center ? ui.align.CENTER_H : ui.align.LEFT,
      invalid_image: img(set + '/none.png'),
      negative_image: img(set + '/minus.png'),
      dot_image: img(set + '/' + (opts.dot || 'dot') + '.png'),
    }
    if (opts.unit) {
      o.unit_en = img(set + '/' + opts.unit + '.png')
      o.unit_sc = o.unit_en
      o.unit_tc = o.unit_en
    }
    const w = ui.createWidget(W.TEXT_IMG, lvl(o, NORMAL))
    if (!w) return null
    sources.push(label + '=sys:' + t.name)
    return w
  } catch (e) {
    log(label + ' TEXT_IMG failed: ' + e)
    return null
  }
}

// ---- taps --------------------------------------------------------------------------------
// Created last so they sit on top. First choice: IMG_CLICK bound to a data type (the
// watch opens the matching app). Otherwise: a transparent BUTTON that launches a system app.
const taps = []
const tapSpecs = []
function tapApp(name, names, appKey, url, fn) {
  tapSpecs.push([name, names, appKey, url, fn])
}
// Open a system app. Some apps (Compass) only open properly by their screen name,
// which is how older watch faces do it; others by the system app id.
function openApp(appKey, url) {
  // the face's own compass reading would keep the sensor busy: release it first
  if (appKey === 'SYSTEM_APP_COMPASS') compassStop()
  if (url && typeof hmApp !== 'undefined' && hmApp && typeof hmApp.startApp === 'function') {
    hmApp.startApp({ url: url, native: true })
    return
  }
  const o = { appId: router[appKey], native: true }
  if (url) o.url = url
  router.launchApp(o)
}
function createTaps() {
  tapSpecs.forEach((t) => {
    const name = t[0]
    const r = L.taps[name] || (name.indexOf('ring') === 0 ? L.ring_taps[+name.slice(4)] : null)
    if (!r) return
    const src = img('tap/' + name + '.png')
    if (t[4] && W.BUTTON !== undefined) {
      const ok = safe(() => ui.createWidget(W.BUTTON, lvl({ x: r[0], y: r[1], w: r[2], h: r[3], normal_src: src, press_src: src, click_func: t[4] }, NORMAL)))
      return taps.push(name + (ok ? ':button:fn' : ':button-failed'))
    }
    const dt = t[1] ? dataType(t[1]) : null
    if (dt && W.IMG_CLICK !== undefined) {
      const ok = safe(() => ui.createWidget(W.IMG_CLICK, lvl({ x: r[0], y: r[1], w: r[2], h: r[3], src: src, type: dt.id }, NORMAL)))
      if (ok) return taps.push(name + ':click:' + dt.name)
    }
    const app = t[2] ? router[t[2]] : undefined
    if (app !== undefined && W.BUTTON !== undefined) {
      const ok = safe(() =>
        ui.createWidget(W.BUTTON, lvl({
          x: r[0], y: r[1], w: r[2], h: r[3], normal_src: src, press_src: src,
          click_func: () => {
            try {
              openApp(t[2], t[3])
            } catch (e) {
              log('launch ' + t[2] + ' failed: ' + e)
            }
          },
        }, NORMAL))
      )
      return taps.push(name + (ok ? ':button:' + t[2].replace('SYSTEM_APP_', '') + (t[3] ? '/' + t[3] : '') : ':button-failed'))
    }
    taps.push(name + ':none')
  })
}

// ---- weather helpers ------------------------------------------------------------------
const st = { forecast: null, tide: null }
const S = {}
const draw = {}
const listeners = []

function readWeather() {
  if (!S.weather) return
  const r = safe(() => S.weather.getForecastWeather())
  if (!r) return
  st.forecast = r.forecastData && r.forecastData.count > 0 ? r.forecastData.data[0] : null
  st.tide = r.tideData && r.tideData.count > 0 ? r.tideData.data : null
}
const hm = (o) => (o && typeof o.hour === 'number' ? o.hour * 60 + o.minute : null)
function sunTimes() {
  const t0 = st.tide && st.tide[0]
  const sr = hm(t0 && t0.sunrise)
  const ss = hm(t0 && t0.sunset)
  if (sr !== null && ss !== null) return { sr: sr, ss: ss, known: true, src: 'forecast' }
  const a = safe(astroSun)
  if (a) return a
  return { sr: 450, ss: 1110, known: false, src: 'none' }
}
// Sunrise/sunset from the date and a home location (NOAA approximation), in local minutes.
let astroCache = null
function astroSun() {
  const t = S.time
  const y = t.getFullYear()
  const mo = t.getMonth()
  const d = t.getDate()
  const key = y * 10000 + mo * 100 + d
  if (astroCache && astroCache.key === key) return astroCache.v
  // local offset from UTC, in minutes, from the watch's own clock
  const utcMin = Math.floor(t.getTime() / 60000) % 1440
  let tz = (t.getHours() * 60 + t.getMinutes() - utcMin) % 1440
  if (tz > 720) tz -= 1440
  if (tz < -720) tz += 1440
  const days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
  const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0
  const n = days[mo - 1] + d + (leap && mo > 2 ? 1 : 0)
  const rad = Math.PI / 180
  const g = ((2 * Math.PI) / 365) * (n - 1)
  const eq = 229.18 * (0.000075 + 0.001868 * Math.cos(g) - 0.032077 * Math.sin(g) - 0.014615 * Math.cos(2 * g) - 0.040849 * Math.sin(2 * g))
  const decl = 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g) - 0.006758 * Math.cos(2 * g) + 0.000907 * Math.sin(2 * g) - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g)
  const lat = L.home.lat * rad
  const cosH = Math.cos(90.833 * rad) / (Math.cos(lat) * Math.cos(decl)) - Math.tan(lat) * Math.tan(decl)
  if (cosH > 1 || cosH < -1) return null
  const ha = Math.acos(cosH) / rad
  const wrap = (m) => ((Math.round(m) % 1440) + 1440) % 1440
  const v = { sr: wrap(720 - 4 * (L.home.lon + ha) - eq + tz), ss: wrap(720 - 4 * (L.home.lon - ha) - eq + tz), known: true, src: 'calculated' }
  astroCache = { key: key, v: v }
  return v
}
const nowMin = () => S.time.getHours() * 60 + S.time.getMinutes()
// Today's forecast as a weather code, for the fallbacks without the watch's current
// weather: 25 (unknown) without data, and at night the night version of the day codes
// (moon and stars rather than sun).
const NIGHT_CODE = { 0: 26, 1: 27, 3: 28 }
function forecastCode() {
  const f = st.forecast
  if (!(f && f.index >= 0 && f.index <= 28)) return 25
  return st.tod === 'night' && NIGHT_CODE[f.index] !== undefined ? NIGHT_CODE[f.index] : f.index
}
const pad2 = (n) => (n < 10 ? '0' : '') + n
const fmtHM = (m) => pad2(Math.floor(m / 60)) + ':' + pad2(m % 60)

function listen(obj, onName, offName, cb) {
  if (obj && typeof obj[onName] === 'function') {
    obj[onName](cb)
    listeners.push([obj, offName, cb])
  }
}
function newSensor(name) {
  try {
    return new sensor[name]()
  } catch (e) {
    log(name + ' sensor unavailable: ' + e)
    return null
  }
}

// ---- compass and seconds only run while the screen is on ---------------------------
let compassOn = false
const cmp = { events: 0, last: undefined }
function onCompass() {
  cmp.events++
  if (draw.bezel) safe(draw.bezel)
}
function compassStart() {
  if (!S.compass || compassOn) return
  step('compass start', () => {
    // normal rate (it only runs while the screen is on): smoother than the low rate
    if (typeof S.compass.setFreqMode === 'function' && sensor.FREQ_MODE_NORMAL !== undefined) S.compass.setFreqMode(sensor.FREQ_MODE_NORMAL)
    S.compass.onChange(onCompass)
    S.compass.start()
    compassOn = true
  })
}
function compassStop() {
  if (!S.compass || !compassOn) return
  safe(() => S.compass.offChange(onCompass))
  safe(() => S.compass.stop())
  compassOn = false
}
let secTimer = null
function secondsStart() {
  if (secTimer !== null || !draw.secs) return
  secTimer = safe(() => setInterval(() => safe(draw.secs), 1000))
  if (secTimer === undefined) secTimer = null
}
function secondsStop() {
  if (secTimer !== null) safe(() => clearInterval(secTimer))
  secTimer = null
}
// weather animation: cycles the frame layers while the screen is on and, every few
// seconds, shows the two flash layers one tick each (lightning and its afterglow in a
// thunderstorm, a shooting star on a clear night; transparent in other weather)
let fxTimer = null
const fx = { frames: [], i: 0, flashes: [], flashStep: 0, flashWait: 0 }
const fxTicks = (ms) => Math.max(1, Math.round(ms / (L.fx.tick || 140)))
function fxTick() {
  const prev = fx.frames[fx.i]
  fx.i = (fx.i + 1) % fx.frames.length
  safe(() => show(fx.frames[fx.i], true))
  safe(() => show(prev, false))
  if (!fx.flashes.length) return
  if (fx.flashStep <= fx.flashes.length) {
    // step k shows flash k (and hides the one before); one step past the end hides the last
    const k = fx.flashStep++
    if (k < fx.flashes.length) safe(() => show(fx.flashes[k], true))
    if (k > 0) safe(() => show(fx.flashes[k - 1], false))
  } else if (--fx.flashWait <= 0) {
    fx.flashStep = 0
    fx.flashWait = fxTicks(5000 + Math.random() * 8000)
  }
}
function fxStart() {
  if (fxTimer !== null || fx.frames.length < 2) return
  fx.flashStep = fx.flashes.length + 1
  fx.flashWait = fxTicks(1500 + Math.random() * 3000)
  fxTimer = safe(() => setInterval(fxTick, L.fx.tick || 140))
  if (fxTimer === undefined) fxTimer = null
}
function fxStop() {
  if (fxTimer !== null) safe(() => clearInterval(fxTimer))
  fxTimer = null
  fx.flashes.forEach((f) => safe(() => show(f, false)))
}
function wake() {
  readWeather()
  refreshAll()
  compassStart()
  secondsStart()
  fxStart()
}
function sleepMode() {
  compassStop()
  secondsStop()
  fxStop()
}

function refreshAll() {
  Object.keys(draw).forEach((k) => {
    try {
      draw[k]()
    } catch (e) {
      log('refresh ' + k + ' FAILED: ' + e)
    }
  })
}

function showDebug() {
  const c = S.compass
  const cinfo = c
    ? json({ on: compassOn, events: cmp.events, status: safe(() => c.getStatus()), angle: safe(() => c.getDirectionAngle()), dir: safe(() => c.getDirection()) })
    : 'no sensor'
  const cands = ['COMPASS', 'DIRECTION', 'HEADING', 'ALARM_CLOCK', 'ALARM', 'WEATHER_CURRENT', 'BIO_CHARGE']
    .map((k) => k + (DT[k] !== undefined ? '+' : '-')).join(' ')
  const lvlInfo = fx.wash ? json(safe(() => fx.wash.getProperty(ui.prop.MORE, {}))) : 'js'
  const text = [
    'MERIDIAN v7 (tap to close)',
    'compass: ' + cinfo,
    'types: ' + cands,
    'weather layer: ' + (lvlInfo || 'n/a').slice(0, 160),
    'frames: ' + fx.frames.length + ' timer: ' + (fxTimer !== null),
    'time of day: ' + st.tod + '  sun: ' + json(sunTimes()),
    'errors: ' + (errors.length ? errors.join(' | ') : 'none'),
  ].join('\n')
  const bg = ui.createWidget(W.FILL_RECT, lvl({ x: 0, y: 0, w: L.W, h: L.W, color: 0x000000 }, NORMAL))
  const t = ui.createWidget(W.TEXT, lvl({
    x: 56, y: 70, w: L.W - 112, h: L.W - 130, text: text, color: 0xffffff, text_size: 16,
    align_h: ui.align ? ui.align.LEFT : undefined,
    text_style: ui.text_style ? ui.text_style.WRAP : undefined,
  }, NORMAL))
  let btn = null
  const close = () => [bg, t, btn].forEach((w) => w && safe(() => w.setProperty(ui.prop.VISIBLE, false)))
  if (W.BUTTON !== undefined) {
    btn = ui.createWidget(W.BUTTON, lvl({
      x: 0, y: 0, w: L.W, h: L.W, normal_src: img('tap/debug.png'), press_src: img('tap/debug.png'), click_func: close,
    }, NORMAL))
  }
}

WatchFace({
  build() {
    log('build start (v9)')
    chunked('ui.widget', keysOf(W))
    chunked('ui.data_type', keysOf(ui.data_type))

    S.time = newSensor('Time')
    S.step = newSensor('Step')
    S.hr = newSensor('HeartRate')
    S.batt = newSensor('Battery')
    S.baro = newSensor('Barometer')
    S.weather = newSensor('Weather')
    S.compass = newSensor('Compass')
    S.sleep = newSensor('Sleep')
    S.workout = newSensor('Workout')
    readWeather()
    chunked('forecast', json(safe(() => S.weather.getForecastWeather())))

    // -- background photo (pool per time of day and weather) + weather wash and animation ---
    step('background', () => {
      ui.createWidget(W.FILL_RECT, lvl({ x: 0, y: 0, w: L.W, h: L.W, color: 0x000000 }, BOTH))
      const bgPath = (tod, mood, i) => 'bg/' + tod + '_' + mood + '_' + i + '.png'
      const bg = makeImg(0, 0, img(bgPath('day', Object.keys(L.bgpool.day)[0], 0)), NORMAL)
      st.reviewIdx = 0
      let reviewLabel = null
      if (L.review) {
        ui.createWidget(W.FILL_RECT, lvl({ x: 93, y: 18, w: L.W - 186, h: 24, radius: 12, color: 0x000000 }, NORMAL))
        reviewLabel = ui.createWidget(W.TEXT, lvl({ x: 93, y: 19, w: L.W - 186, h: 22, text: '', color: 0xffffff, text_size: 15,
          align_h: ui.align ? ui.align.CENTER_H : undefined }, NORMAL))
      }
      // Photo for the time of day and today's weather: one that matches the weather,
      // else one for any weather, else a matching one from the other twilight (dawn and
      // dusk look alike), else whatever this time of day has.
      const pickBg = (tod) => {
        const code = st.forecast && st.forecast.index >= 0 && st.forecast.index <= 28 ? st.forecast.index : 3
        const mood = L.moods[code]
        const twin = tod === 'dawn' ? 'dusk' : tod === 'dusk' ? 'dawn' : null
        const p = L.bgpool[tod]
        let t = tod
        let m = p[mood] ? mood : p.any ? 'any' : null
        if (!m && twin && L.bgpool[twin][mood]) {
          t = twin
          m = mood
        }
        if (!m) m = Object.keys(p)[0]
        // a different photo from the pool every hour (stable within the hour)
        const seed = S.time.getDate() * 31 + S.time.getHours() * 7 + S.time.getMonth()
        return bgPath(t, m, ((seed * 2654435761) % 4294967296) % L.bgpool[t][m])
      }
      draw.sky = () => {
        const t = nowMin()
        const sun = sunTimes()
        let tod = 'day'
        if (Math.abs(t - sun.sr) <= 45) tod = 'dawn'
        else if (Math.abs(t - sun.ss) <= 45) tod = 'dusk'
        else if (t < sun.sr || t > sun.ss) tod = 'night'
        st.tod = tod
        if (L.review) {
          // review mode: tap the time for the next photo; its name is shown at the top
          const i = st.reviewIdx % L.review.length
          setSrc(bg, img(L.review[i][0]))
          if (reviewLabel) safe(() => reviewLabel.setProperty(ui.prop.TEXT, (i + 1) + '/' + L.review.length + '  ' + L.review[i][1]))
          return
        }
        setSrc(bg, img(pickBg(tod)))
      }
      draw.sky()

      // Weather layers follow the watch's own current weather (IMG_LEVEL bound to the
      // weather code) so they need no JS weather access. Fallback: today's forecast.
      const t = dataType(['WEATHER_CURRENT', 'WEATHER'])
      const paths = (arr) => arr.map((p) => img(p))
      let sys = false
      if (W.IMG_LEVEL !== undefined && t) {
        const mk = (arr, h) => safe(() => ui.createWidget(W.IMG_LEVEL, lvl({ x: 0, y: 0, w: L.W, h: h, image_array: paths(arr), image_length: arr.length, type: t.id }, NORMAL)))
        const wash = mk(L.fx.wash, L.bg_h)
        const frames = L.fx.frames.map((arr) => mk(arr, L.fx_h))
        const flashes = L.fx.flash.map((arr) => mk(arr, L.bg_h))
        fx.wash = wash
        const made = [wash].concat(flashes, frames)
        if (made.every((w) => w)) {
          sys = true
          fx.frames = frames
          fx.flashes = flashes
          frames.forEach((f, k) => k > 0 && show(f, false))
          flashes.forEach((f) => show(f, false))
          sources.push('weatherfx=sys:' + t.name)
        } else made.forEach((w) => w && safe(() => show(w, false)))
      }
      if (!sys) {
        const wash = makeImg(0, 0, img('fx/wash_none.png'), NORMAL)
        const frames = L.fx.frames.map(() => makeImg(0, 0, img('fx/none.png'), NORMAL))
        const flashes = L.fx.flash.map(() => makeImg(0, 0, img('fx/wash_none.png'), NORMAL))
        fx.frames = frames
        fx.flashes = flashes
        frames.forEach((f, k) => k > 0 && show(f, false))
        flashes.forEach((f) => show(f, false))
        draw.fx = () => {
          const code = forecastCode()
          setSrc(wash, img(L.fx.wash[code]))
          flashes.forEach((f, k) => setSrc(f, img(L.fx.flash[k][code])))
          frames.forEach((f, k) => setSrc(f, img(L.fx.frames[k][code])))
        }
        draw.fx()
        sources.push('weatherfx=' + (st.forecast ? 'js:forecast' : 'none'))
      }
    })

    // -- compass: a ring that turns so N points north, read at the fixed top mark --------
    step('bezel', () => {
      const b = L.bezel
      let mode = 'ring'
      const ring = ui.createWidget(W.IMG, lvl({ x: 0, y: 0, w: L.W, h: L.W, src: img('bezel/ring_off.png'), center_x: CX, center_y: CX, angle: 0 }, NORMAL))
      ring._src = img('bezel/ring_off.png')
      const mark = makeImg(CX - 8, 0, img('bezel/lubber.png'), NORMAL)
      const rotate = (deg) => {
        try {
          ring.setProperty(ui.prop.ANGLE, deg)
        } catch (e) {
          ring.setProperty(ui.prop.MORE, { x: 0, y: 0, w: L.W, h: L.W, src: img('bezel/ring.png'), center_x: CX, center_y: CX, angle: deg })
        }
      }
      // upright N/E/S/W letters, moved around the edge (the ring image only has ticks)
      const letters = b.letters.map((m) => {
        const w = makeImg(CX - m[1] / 2, CX - b.r - m[1] / 2, img('bezel/' + m[0] + '.png'), NORMAL)
        w._size = m[1]
        show(w, false)
        return w
      })
      // fallback if the ring can't rotate: dots between the letters stand in for its ticks
      let dots = null
      const fallback = () => {
        mode = 'markers'
        safe(() => show(ring, false))
        dots = [0, 1, 2, 3].map(() => {
          const w = makeImg(CX - b.dot / 2, CX - b.r - b.dot / 2, img('bezel/dot.png'), NORMAL)
          w._size = b.dot
          return w
        })
      }
      const around = (ws, offset, a) =>
        ws.forEach((m, i) => {
          const r = ((offset + i * 90 - a) * Math.PI) / 180
          place(m, CX + b.r * Math.sin(r) - m._size / 2, CX - b.r * Math.cos(r) - m._size / 2)
        })
      let last = null
      draw.bezel = () => {
        const a = S.compass ? safe(() => S.compass.getDirectionAngle()) : undefined
        const ok = typeof a === 'number' && isFinite(a)
        cmp.last = a
        show(mark, ok)
        letters.forEach((m) => show(m, ok))
        if (mode === 'ring') {
          // no heading yet (e.g. not calibrated): grey ring, not turned, no letters
          if (!ok) {
            setSrc(ring, img('bezel/ring_off.png'))
            safe(() => rotate(0))
          } else setSrc(ring, img('bezel/ring.png'))
        } else dots.forEach((m) => show(m, ok))
        if (!ok) {
          last = null
          return
        }
        if (last !== null && Math.abs(((a - last + 540) % 360) - 180) < 1) return
        last = a
        if (mode === 'ring') {
          try {
            rotate(-a)
          } catch (e) {
            log('ring rotation failed: ' + e)
            fallback()
          }
        }
        around(letters, 0, a)
        if (dots) around(dots, 45, a)
      }
      draw.bezel()
      sources.push('compass=' + (S.compass ? 'js:' + mode : 'none'))
      // tapping the ring (any edge) opens the Compass app, e.g. to calibrate
      for (let i = 0; i < L.ring_taps.length; i++) tapApp('ring' + i, ['COMPASS'], 'SYSTEM_APP_COMPASS')
    })

    // -- weather + altitude ----------------------------------------------------------------
    step('weather', () => {
      const w = L.weather
      let condJs = true
      let cond = null
      const t = dataType(['WEATHER_CURRENT', 'WEATHER'])
      if (W.IMG_LEVEL !== undefined && t) {
        const arr = []
        for (let i = 0; i < 29; i++) arr.push(img('icon/weather/' + i + '.png'))
        cond = safe(() => ui.createWidget(W.IMG_LEVEL, lvl({ x: w.cond.icon[0], y: w.cond.icon[1], image_array: arr, image_length: 29, type: t.id }, NORMAL)))
        if (cond) {
          condJs = false
          sources.push('condition=sys:' + t.name)
        }
      }
      if (condJs) {
        cond = makeImg(w.cond.icon[0], w.cond.icon[1], img('icon/weather/25.png'), NORMAL)
        sources.push('condition=js')
      }
      const tempRun = sysField('temp', ['WEATHER_CURRENT'], w.cond.box, 'sm', { unit: 'deg' }) ? null : makeRun('sm', 7, w.cond.box.y, NORMAL)
      if (tempRun) sources.push('temp=js:low/high')

      makeImg(w.wind.icon[0], w.wind.icon[1], img('icon/wind.png'), NORMAL)
      if (!sysField('wind', ['WIND', 'WIND_SPEED'], w.wind.box, 'sm', { unit: 'u_kmh' })) {
        makeImg(w.wind.box.x - G.sm.pad, w.wind.box.y, img('sm/none.png'), NORMAL)
        sources.push('wind=none')
      }
      makeImg(w.hum.icon[0], w.hum.icon[1], img('icon/drop.png'), NORMAL)
      if (!sysField('humidity', ['HUMIDITY'], w.hum.box, 'sm', { unit: 'pct' })) {
        makeImg(w.hum.box.x - G.sm.pad, w.hum.box.y, img('sm/none.png'), NORMAL)
        sources.push('humidity=none')
      }
      makeImg(w.alt.icon[0], w.alt.icon[1], img('icon/alt.png'), NORMAL)
      const altRun = makeRun('sm', 7, w.alt.box.y, NORMAL)
      let altSys = null
      draw.alt = () => {
        const v = S.baro ? safe(() => S.baro.getAltitude()) : undefined
        if (typeof v === 'number' && isFinite(v)) altRun.draw(toKeys(Math.round(v)).concat(['u_m']), w.alt.box.x)
        else if (!altSys) altRun.draw(['none'], w.alt.box.x)
      }
      const firstAlt = S.baro ? safe(() => S.baro.getAltitude()) : undefined
      if (typeof firstAlt === 'number' && isFinite(firstAlt)) sources.push('altitude=js')
      else {
        altSys = sysField('altitude', ['ALTIMETER', 'ALTITUDE'], w.alt.box, 'sm', { unit: 'u_m' })
        if (!altSys) sources.push('altitude=none')
      }
      draw.alt()

      draw.weather = () => {
        const f = st.forecast
        if (condJs) setSrc(cond, img('icon/weather/' + forecastCode() + '.png'))
        if (tempRun) {
          if (f && typeof f.low === 'number' && typeof f.high === 'number') tempRun.draw(toKeys(f.low + '/' + f.high + '°'), w.cond.box.x)
          else tempRun.draw(['none'], w.cond.box.x)
        }
      }
      draw.weather()
      tapApp('weather', ['WEATHER_CURRENT', 'WEATHER'], 'SYSTEM_APP_WEATHER')
      tapApp('altitude', ['ALTIMETER', 'ALTITUDE'], 'SYSTEM_APP_ALTIMETER')
    })

    // -- date (always-on: its own copy, centred, as the sun event isn't shown there) -----------
    step('date', () => {
      const row = (d, level) => ({
        wk: makeImg(d.wk[0], d.wk[1], img('sm/wk0.png'), level),
        d1: makeImg(d.dd[0], d.dd[1], img('sm/0.png'), level),
        d2: makeImg(d.dd[0] + G.sm.w['0'], d.dd[1], img('sm/0.png'), level),
        mo: makeImg(d.mo[0], d.mo[1], img('sm/mo0.png'), level),
      })
      const rows = AOD !== undefined ? [row(L.date, NORMAL), row(L.date_aod, AOD)] : [row(L.date, BOTH)]
      draw.date = () => {
        const dd = pad2(S.time.getDate())
        rows.forEach((r) => {
          setSrc(r.wk, img('sm/wk' + ((S.time.getDay() + 6) % 7) + '.png'))
          setSrc(r.d1, img('sm/' + dd[0] + '.png'))
          setSrc(r.d2, img('sm/' + dd[1] + '.png'))
          setSrc(r.mo, img('sm/mo' + (((S.time.getMonth() - 1) % 12 + 12) % 12) + '.png'))
        })
      }
      draw.date()
    })

    // -- time: HH:MM + seconds; always-on HH:MM -----------------------------------------------
    step('time', () => {
      const t = L.time
      const rows = [{ folder: 'time', cells: t.x.map((x) => makeImg(x, t.y, img('time/0.png'), NORMAL)) }]
      makeImg(t.colon, t.y, img('time/colon.png'), NORMAL)
      if (AOD !== undefined) {
        const a = L.aod
        rows.push({ folder: 'aod', cells: a.x.map((x) => makeImg(x, a.y, img('aod/0.png'), AOD)) })
        makeImg(a.colon, a.y, img('aod/colon.png'), AOD)
      }
      draw.time = () => {
        let h = S.time.getHours()
        const fh = safe(() => S.time.getFormatHour())
        if (typeof fh === 'number' && fh >= 0) h = fh
        const text = pad2(h) + pad2(S.time.getMinutes())
        rows.forEach((r) => {
          for (let i = 0; i < 4; i++) setSrc(r.cells[i], img(r.folder + '/' + text[i] + '.png'))
        })
      }
      draw.time()
      const s1 = makeImg(t.sec.x[0], t.sec.y, img('sec/0.png'), NORMAL)
      const s2 = makeImg(t.sec.x[1], t.sec.y, img('sec/0.png'), NORMAL)
      let lastMin = -1
      draw.secs = () => {
        const s = pad2(S.time.getSeconds())
        setSrc(s1, img('sec/' + s[0] + '.png'))
        setSrc(s2, img('sec/' + s[1] + '.png'))
        const m = S.time.getMinutes()
        if (m !== lastMin) {
          lastMin = m
          draw.time()
        }
      }
      draw.secs()
      if (L.review) {
        // review mode: tap the time to show the next photo
        tapApp('time', null, null, null, () => {
          st.reviewIdx++
          if (draw.sky) safe(draw.sky)
        })
      } else tapApp('time', ['ALARM_CLOCK', 'ALARM'], 'SYSTEM_APP_ALARM') // tap the time: open Alarms
    })

    // -- ring gauges: steps (JS) and HybridCharge (system) ----------------------------------------
    const gaugeFill = {}
    step('gauges', () => {
      const gc = L.gauge_colors
      ;['steps', 'charge'].forEach((k) => {
        const g = L.gauges[k]
        const box = { x: g.cx - g.r, y: g.cy - g.r, w: 2 * g.r, h: 2 * g.r }
        const arc = (end, color) => lvl({ x: box.x, y: box.y, w: box.w, h: box.h, line_width: g.w, color: color, start_angle: -90, end_angle: end }, NORMAL)
        makeImg(g.track[0], g.track[1], img('icon/track_' + k + '.png'), NORMAL)
        makeImg(g.icon[0], g.icon[1], img('icon/' + k + '.png'), NORMAL)
        if (k === 'steps') {
          const fill = ui.createWidget(W.ARC, arc(-89, gc.steps))
          gaugeFill.steps = (frac) => {
            frac = Math.max(0, Math.min(1, frac))
            if (frac < 0.005) return show(fill, false)
            fill.setProperty(ui.prop.MORE, arc(-90 + 360 * frac, gc.steps))
            show(fill, true)
          }
        }
      })

      const s = L.gauges.steps
      const stepsDraw = centredRun('gn', s.box, 6, NORMAL)
      // up to 9999 in full, then 16.3k (one decimal), then 123k
      const stepsKeys = (n) =>
        n < 10000 ? toKeys(n) : toKeys(n < 99950 ? (Math.round(n / 100) / 10).toFixed(1) : Math.round(n / 1000)).concat(['u_k'])
      draw.steps = () => {
        const cur = S.step.getCurrent()
        stepsDraw(typeof cur === 'number' && cur >= 0 ? stepsKeys(Math.round(cur)) : ['none'])
        const goal = S.step.getTarget()
        if (gaugeFill.steps) gaugeFill.steps(cur / (goal > 0 ? goal : 10000))
      }
      draw.steps()
      sources.push('steps=js')
      tapApp('steps', ['STEP'], null)

      const c = L.gauges.charge
      const chargeNames = ['HYBRID_CHARGE', 'HYBRIDCHARGE', 'BIO_CHARGE', 'BIOCHARGE', 'BODY_BATTERY', 'READINESS']
      if (!sysField('hybridcharge', chargeNames, c.box, 'gn', { center: true })) {
        centredRun('gn', c.box, 2, NORMAL)(['none'])
        sources.push('hybridcharge=none')
      }
      // ring fill bound to the same data type, if the watch offers ARC_PROGRESS
      const ct = dataType(chargeNames)
      if (ct && W.ARC_PROGRESS !== undefined) {
        const ok = safe(() => ui.createWidget(W.ARC_PROGRESS, lvl({ center_x: c.cx, center_y: c.cy, radius: c.r - c.w / 2, start_angle: -90, end_angle: 270, line_width: c.w, color: gc.charge, type: ct.id }, NORMAL)))
        sources.push('hybridring=' + (ok ? 'sys' : 'failed'))
      }
      tapApp('charge', chargeNames, 'SYSTEM_APP_READINESS')
    })

    // -- heart rate --------------------------------------------------------------------------
    step('heart', () => {
      const h = L.heart
      makeImg(h.icon[0], h.icon[1], img('icon/heart.png'), NORMAL)
      const hrDraw = centredRun('num', h.box, 3, NORMAL)
      draw.hr = () => {
        let v = typeof S.hr.getLast === 'function' ? S.hr.getLast() : 0
        if (!(v > 0)) v = S.hr.getCurrent()
        hrDraw(v > 0 ? toKeys(v) : ['none'])
      }
      draw.hr()
      sources.push('heart=js')
      tapApp('heart', ['HEART'], 'SYSTEM_APP_HR')
    })

    // -- next sun event: sunrise until it's up, then sunset until it's down ------------------------
    step('sun', () => {
      const s = L.sun
      const icon = makeImg(s.icon[0], s.icon[1], img('icon/sunrise.png'), NORMAL)
      // the watch's own times if it offers both (one shown at a time), otherwise ours
      const riseSys = sysField('sunrise', ['SUN_RISE', 'SUNRISE'], s.box, 'sm', { dot: 'colon' })
      const setSys = riseSys ? sysField('sunset', ['SUN_SET', 'SUNSET'], s.box, 'sm', { dot: 'colon' }) : null
      const sys = !!(riseSys && setSys)
      if (riseSys && !sys) show(riseSys, false)
      const run = sys ? null : makeRun('sm', 5, s.box.y, NORMAL)
      draw.sun = () => {
        const t = sunTimes()
        const now = nowMin()
        const sunset = t.known && now >= t.sr && now < t.ss
        setSrc(icon, img(sunset ? 'icon/sunset.png' : 'icon/sunrise.png'))
        if (sys) {
          show(riseSys, !sunset)
          show(setSys, sunset)
        } else run.draw(t.known ? toKeys(fmtHM(sunset ? t.ss : t.sr)) : ['none'], s.box.x)
      }
      draw.sun()
      sources.push('sun=' + (sys ? 'sys' : sunTimes().src))
      tapApp('sun', ['SUN_CURRENT', 'SUN_RISE', 'SUN_SET'], 'SYSTEM_APP_SUN_AND_MOON')
    })

    // -- recovery time and sleep score (larger), VO2max and HRV ------------------------------------
    step('health', () => {
      const group = (spec, icon, set, max) => {
        const ic = makeImg(spec.cx, spec.icon_y, img('icon/' + icon + '.png'), NORMAL)
        const run = makeRun(set, max, spec.y, NORMAL)
        return (keys) => {
          const total = spec.icon_w + 5 + measure(set, keys)
          const x = spec.cx - total / 2
          place(ic, x, spec.icon_y)
          run.draw(keys, x + spec.icon_w + 5)
        }
      }
      const h = L.health
      const recDraw = group(h.recovery, 'recovery', 'num', 5)
      const sleepDraw = group(h.sleep, 'sleep', 'num', 3)

      const f = L.fitness
      makeImg(f.vo2.icon[0], f.vo2.icon[1], img('icon/vo2.png'), NORMAL)
      makeImg(f.hrv.icon[0], f.hrv.icon[1], img('icon/hrv.png'), NORMAL)
      const vo2Run = makeRun('sm', 3, f.vo2.box.y, NORMAL)
      if (!sysField('hrv', ['HRV', 'HEART_RATE_VARIABILITY'], f.hrv.box, 'sm', { unit: 'u_ms' })) {
        makeImg(f.hrv.box.x - G.sm.pad, f.hrv.box.y, img('sm/none.png'), NORMAL)
        sources.push('hrv=none')
      }

      draw.health = () => {
        const w = S.workout ? safe(() => S.workout.getStatus()) : undefined
        const rec = w && typeof w.fullRecoveryTime === 'number' && w.fullRecoveryTime >= 0 ? w.fullRecoveryTime : null
        recDraw(rec !== null ? toKeys(Math.round(rec)).concat(['u_h']) : ['none'])
        const vo2 = w && typeof w.vo2Max === 'number' && w.vo2Max > 0 ? w.vo2Max : null
        vo2Run.draw(vo2 !== null ? toKeys(Math.round(vo2)) : ['none'], f.vo2.box.x)
        const sl = S.sleep ? safe(() => S.sleep.getInfo()) : undefined
        const score = sl && typeof sl.score === 'number' && sl.score > 0 ? sl.score : null
        sleepDraw(score !== null ? toKeys(score) : ['none'])
      }
      draw.health()
      log('workout status: ' + json(S.workout ? safe(() => S.workout.getStatus()) : null))
      log('sleep info: ' + json(S.sleep ? safe(() => S.sleep.getInfo()) : null))
      tapApp('recovery', ['RECOVERY_TIME', 'RECOVERY', 'TRAINING_LOAD'], 'SYSTEM_APP_SPORT_STATUS')
      tapApp('sleep', ['SLEEP'], 'SYSTEM_APP_SLEEP')
      tapApp('vo2', ['VO2MAX', 'VO2_MAX'], 'SYSTEM_APP_SPORT_STATUS')
      // No system app id for an HRV screen: the HRV data-type tap and Readiness do
      // nothing on this watch. Stress is the closest HRV-based screen that opens.
      tapApp('hrv', null, 'SYSTEM_APP_PRESSURE')
    })

    // -- battery ------------------------------------------------------------------------------------
    step('battery', () => {
      const b = L.batt
      const icon = makeImg(b.cx, b.icon_y, img('icon/batt.png'), NORMAL)
      const run = makeRun('sm', 4, b.y, NORMAL)
      draw.batt = () => {
        const v = S.batt.getCurrent()
        const keys = typeof v === 'number' && v >= 0 ? toKeys(v + '%') : ['none']
        const total = b.icon_w + 3 + measure('sm', keys)
        const x = b.cx - total / 2
        place(icon, x, b.icon_y)
        run.draw(keys, x + b.icon_w + 3)
      }
      draw.batt()
      tapApp('battery', ['BATTERY'], null)
    })

    // -- keep it current ---------------------------------------------------------------------------
    step('listeners', () => {
      let minutes = 0
      listen(S.time, 'onPerMinute', 'offPerMinute', () => {
        minutes++
        if (minutes % 30 === 0) {
          readWeather()
          if (S.sleep) safe(() => S.sleep.updateInfo())
        }
        ;['time', 'sky', 'fx', 'weather', 'alt', 'sun', 'date', 'health'].forEach((k) => draw[k] && safe(draw[k]))
      })
      listen(S.step, 'onChange', 'offChange', () => draw.steps && safe(draw.steps))
      listen(S.hr, 'onLastChange', 'offLastChange', () => draw.hr && safe(draw.hr))
      listen(S.batt, 'onChange', 'offChange', () => draw.batt && safe(draw.batt))
      if (W.WIDGET_DELEGATE !== undefined) {
        ui.createWidget(W.WIDGET_DELEGATE, { resume_call: wake, pause_call: sleepMode })
      }
      compassStart()
      secondsStart()
      fxStart()
    })

    step('taps', createTaps)
    log('sources: ' + sources.join(' '))
    log('taps: ' + taps.join(' '))
    if (errors.length) {
      safe(() =>
        ui.createWidget(W.TEXT, {
          x: 50, y: 300, w: 366, h: 120, text: errors.join('\n'), color: 0xff5050, text_size: 18,
          align_h: ui.align ? ui.align.CENTER_H : undefined,
          text_style: ui.text_style ? ui.text_style.WRAP : undefined,
        })
      )
    }
    if (DEBUG) step('debug panel', showDebug)
    log('build done, ' + errors.length + ' error(s)')
  },

  onResume() {
    wake()
  },

  onPause() {
    sleepMode()
  },

  onDestroy() {
    sleepMode()
    listeners.forEach((l) => safe(() => l[0][l[1]](l[2])))
  },
})
