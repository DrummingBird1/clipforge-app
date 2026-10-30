// ============================================================================
// גל 25: כלי צבע ושמע מקצועיים - שלושה גלגלי lift/gamma/gain, עקומות (ראשית + R/G/B),
// ושדות השמע (חיתוך נמוכים, EQ שלושה פסים, קומפרסור, הפחתת רעש). הבנייה ל-ffmpeg ב-
// utils/color_audio.py; כאן הממשק, הערכים בשדות הטקסט (הם מה שנשמר בפרופיל), והדמיה
// בנגן החי (פילטר SVG עם טבלת צבע לכל ערוץ - אותו חישוב של colorbalance ו-curves).
// ============================================================================

const VE_WAVE25_FIELDS = {
  grade_shadows: {id: "veGradeShadows", kind: "str", label: "גלגל צללים (Lift)"},
  grade_midtones: {id: "veGradeMidtones", kind: "str", label: "גלגל גוונים אמצעיים (Gamma)"},
  grade_highlights: {id: "veGradeHighlights", kind: "str", label: "גלגל הדגשות (Gain)"},
  curves_preset: {id: "veCurvesPreset", kind: "str", label: "עקומה מוכנה"},
  curves_master: {id: "veCurvesMaster", kind: "str", label: "עקומה ראשית"},
  curves_red: {id: "veCurvesRed", kind: "str", label: "עקומת אדום"},
  curves_green: {id: "veCurvesGreen", kind: "str", label: "עקומת ירוק"},
  curves_blue: {id: "veCurvesBlue", kind: "str", label: "עקומת כחול"},
  audio_highpass: {id: "veAudioHighpass", kind: "int", label: "חיתוך נמוכים"},
  audio_eq_low: {id: "veAudioEqLow", kind: "float", label: "EQ נמוכים"},
  audio_eq_mid: {id: "veAudioEqMid", kind: "float", label: "EQ אמצע"},
  audio_eq_mid_freq: {id: "veAudioEqMidFreq", kind: "int", label: "תדר EQ אמצע"},
  audio_eq_high: {id: "veAudioEqHigh", kind: "float", label: "EQ גבוהים"},
  audio_compressor: {id: "veAudioCompressor", kind: "str", label: "קומפרסור"},
  audio_denoise: {id: "veAudioDenoise", kind: "str", label: "הפחתת רעש בשמע"},
  audio_denoise_model: {id: "veAudioDenoiseModel", kind: "str", label: "מודל RNNoise"},
};
Object.assign(VE_GENERIC_FIELDS, VE_WAVE25_FIELDS);
for (const [key, meta] of Object.entries(VE_WAVE25_FIELDS)) VE_FAVORITABLE_FIELDS[key] = {id: meta.id, label: meta.label};

Object.assign(VE_DEPENDENT_FIELDS, {
  veAudioEqMidFreq: () => Math.abs(parseFloat(_veValue("veAudioEqMid")) || 0) >= 0.05,
  veAudioDenoiseModel: () => _veValue("veAudioDenoise") !== "off" && _veValue("veAudioDenoise") !== "",
});

const VE_GRADE_RANGES = {shadows: "veGradeShadows", midtones: "veGradeMidtones", highlights: "veGradeHighlights"};
const VE_GRADE_MAX = 0.3;  // קצה הגלגל = היסט של 0.3 בערוץ הדומיננטי (colorbalance: -1..1)

function _veParseTriplet(text) {
  const match = /^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/.exec(text || "");
  return match ? match.slice(1).map(v => Math.max(-1, Math.min(1, parseFloat(v)))) : [0, 0, 0];
}

function _veFormatTriplet(rgb) {
  if (rgb.every(v => Math.abs(v) < 0.0005)) return "";
  return rgb.map(v => (Math.round(v * 1000) / 1000).toString()).join(",");
}

// גלגל: זווית (בכיוון השעון מלמעלה, אדום למעלה - כמו ה-conic-gradient) + עוצמה 0..1 + בהירות.
// כיוון הצבע לזווית h: (cos h, cos(h-120), cos(h-240)) - ההיפוך המדויק דרך atan2(√3(g-b), 2r-g-b).
function _veWheelToRgb(hueDeg, strength, luma) {
  const h = hueDeg * Math.PI / 180, amp = strength * VE_GRADE_MAX;
  return [0, 120, 240].map(offset => amp * Math.cos(h - offset * Math.PI / 180) + luma);
}

function _veRgbToWheel(rgb) {
  const [r, g, b] = rgb;
  const luma = (r + g + b) / 3;
  const x = 2 * r - g - b, y = Math.sqrt(3) * (g - b);
  const amp = Math.hypot(x, y) / 3;
  const hue = ((Math.atan2(y, x) * 180 / Math.PI) + 360) % 360;
  return {hue, strength: Math.min(1, amp / VE_GRADE_MAX), luma};
}

function _veWheelState(range) {
  return _veRgbToWheel(_veParseTriplet(_veEl(VE_GRADE_RANGES[range]).value));
}

function _veSetWheel(range, hue, strength, luma) {
  const input = _veEl(VE_GRADE_RANGES[range]);
  const next = _veFormatTriplet(_veWheelToRgb(hue, Math.max(0, Math.min(1, strength)), luma));
  if (input.value === next) return;
  input.value = next;
  input.dispatchEvent(new Event("input", {bubbles: true}));
  input.dispatchEvent(new Event("change", {bubbles: true}));
}

function _veRenderWheel(range) {
  const wheel = document.querySelector(`.ve-wheel[data-grade="${range}"]`);
  if (!wheel) return;
  const {hue, strength, luma} = _veWheelState(range);
  const puck = wheel.querySelector(".ve-wheel-puck");
  const h = hue * Math.PI / 180;
  puck.style.left = `${50 + 50 * strength * Math.sin(h)}%`;
  puck.style.top = `${50 - 50 * strength * Math.cos(h)}%`;
  const slider = wheel.parentElement.querySelector(".ve-wheel-luma");
  if (slider && document.activeElement !== slider) slider.value = String(Math.round(luma * 1000) / 1000);
  wheel.classList.toggle("is-set", strength > 0.001 || Math.abs(luma) > 0.0005);
}

function _veWheelPointer(range, event) {
  const disc = document.querySelector(`.ve-wheel[data-grade="${range}"] .ve-wheel-disc`);
  const rect = disc.getBoundingClientRect();
  const dx = (event.clientX - rect.left - rect.width / 2) / (rect.width / 2);
  const dy = (event.clientY - rect.top - rect.height / 2) / (rect.height / 2);
  const strength = Math.min(1, Math.hypot(dx, dy));
  const hue = ((Math.atan2(dx, -dy) * 180 / Math.PI) + 360) % 360;
  // Shift = עדין (חצי מהמרחק), כמו גרירת תוויות מספריות בסטודיו
  _veSetWheel(range, hue, event.shiftKey ? strength / 2 : strength, _veWheelState(range).luma);
}

function _veSetupWheels() {
  for (const range of Object.keys(VE_GRADE_RANGES)) {
    const wheel = document.querySelector(`.ve-wheel[data-grade="${range}"]`);
    if (!wheel || wheel.dataset.ready) continue;
    wheel.dataset.ready = "1";
    const disc = wheel.querySelector(".ve-wheel-disc");
    disc.addEventListener("pointerdown", (e) => {
      disc.setPointerCapture(e.pointerId);
      _veWheelPointer(range, e);
      const move = (ev) => _veWheelPointer(range, ev);
      const up = () => { disc.removeEventListener("pointermove", move); disc.removeEventListener("pointerup", up); };
      disc.addEventListener("pointermove", move);
      disc.addEventListener("pointerup", up);
    });
    disc.addEventListener("dblclick", () => { const {luma} = _veWheelState(range); _veSetWheel(range, 0, 0, luma); });
    // מקלדת: חיצים מזיזים את הנקודה (Shift = צעד גדול), Delete מאפס
    disc.addEventListener("keydown", (e) => {
      const step = e.shiftKey ? 0.1 : 0.02;
      const {hue, strength, luma} = _veWheelState(range);
      const h = hue * Math.PI / 180;
      let x = strength * Math.sin(h), y = -strength * Math.cos(h);
      if (e.key === "ArrowLeft") x -= step; else if (e.key === "ArrowRight") x += step;
      else if (e.key === "ArrowUp") y -= step; else if (e.key === "ArrowDown") y += step;
      else if (e.key === "Delete" || e.key === "Backspace") { _veSetWheel(range, 0, 0, luma); e.preventDefault(); return; }
      else return;
      e.preventDefault();
      _veSetWheel(range, ((Math.atan2(x, -y) * 180 / Math.PI) + 360) % 360, Math.min(1, Math.hypot(x, y)), luma);
    });
    const luma = wheel.parentElement.querySelector(".ve-wheel-luma");
    luma.addEventListener("input", () => { const {hue, strength} = _veWheelState(range); _veSetWheel(range, hue, strength, parseFloat(luma.value) || 0); });
    wheel.parentElement.querySelector(".ve-wheel-reset").addEventListener("click", () => _veSetWheel(range, 0, 0, 0));
    _veEl(VE_GRADE_RANGES[range]).addEventListener("input", () => _veRenderWheel(range));
    _veRenderWheel(range);
  }
}

// --- עקומות ---

const VE_CURVE_FIELDS = {master: "veCurvesMaster", red: "veCurvesRed", green: "veCurvesGreen", blue: "veCurvesBlue"};
const VE_CURVE_COLORS = {master: "--color-text", red: "--hue-rose", green: "--hue-emerald", blue: "--hue-blue"};
// אותן נקודות כמו ה-presets של ffmpeg (vf_curves.c) - להדמיה בנגן ולציור בעורך
const VE_CURVE_PRESETS = {
  lighter: {master: "0/0 0.4/0.5 1/1"},
  darker: {master: "0/0 0.5/0.4 1/1"},
  increase_contrast: {master: "0/0 0.149/0.066 0.831/0.905 0.905/0.98 1/1"},
  linear_contrast: {master: "0/0 0.305/0.286 0.694/0.713 1/1"},
  medium_contrast: {master: "0/0 0.286/0.219 0.639/0.643 1/1"},
  strong_contrast: {master: "0/0 0.301/0.196 0.592/0.6 0.686/0.737 1/1"},
  vintage: {red: "0/0.11 0.42/0.51 1/0.95", green: "0/0 0.50/0.48 1/1", blue: "0/0.22 0.49/0.44 1/0.8"},
  cross_process: {red: "0/0 0.25/0.156 0.501/0.501 0.686/0.745 1/1", green: "0/0 0.25/0.188 0.38/0.501 0.745/0.815 1/0.815",
                  blue: "0/0 0.231/0.094 0.709/0.874 1/1"},
  color_negative: {red: "0.129/1 0.466/0.498 0.725/0", green: "0.109/1 0.301/0.498 0.517/0", blue: "0.098/1 0.235/0.498 0.423/0"},
};
let _veCurveChannel = "master";

function _veParseCurve(text) {
  const points = [];
  for (const token of String(text || "").trim().split(/\s+/)) {
    const match = /^(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)$/.exec(token);
    if (!match) continue;
    const x = Math.min(1, parseFloat(match[1])), y = Math.min(1, parseFloat(match[2]));
    if (!points.length || x > points[points.length - 1][0]) points.push([x, y]);
  }
  return points.length >= 2 ? points : null;
}

function _veFormatCurve(points) {
  const identity = points.length === 2 && points[0][0] === 0 && points[0][1] === 0 && points[1][0] === 1 && points[1][1] === 1;
  if (identity) return "";
  const r = v => (Math.round(v * 1000) / 1000).toString();
  return points.map(([x, y]) => `${r(x)}/${r(y)}`).join(" ");
}

// spline קובי טבעי - כמו ffmpeg curves (interp=natural), קבוע מחוץ לנקודות הקצה
function _veSpline(points) {
  const n = points.length, xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const clamp = v => Math.max(0, Math.min(1, v));
  if (n === 2) return x => clamp(x <= xs[0] ? ys[0] : x >= xs[1] ? ys[1] : ys[0] + (x - xs[0]) / (xs[1] - xs[0]) * (ys[1] - ys[0]));
  const h = [], alpha = [], l = [1], mu = [0], z = [0], b = [], c = new Array(n).fill(0), d = [];
  for (let i = 0; i < n - 1; i++) h[i] = xs[i + 1] - xs[i];
  for (let i = 1; i < n - 1; i++) {
    alpha[i] = 3 / h[i] * (ys[i + 1] - ys[i]) - 3 / h[i - 1] * (ys[i] - ys[i - 1]);
    l[i] = 2 * (xs[i + 1] - xs[i - 1]) - h[i - 1] * mu[i - 1];
    mu[i] = h[i] / l[i];
    z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / l[i];
  }
  for (let j = n - 2; j >= 0; j--) {
    c[j] = (j === 0 ? 0 : z[j] - mu[j] * c[j + 1]);
    b[j] = (ys[j + 1] - ys[j]) / h[j] - h[j] * (c[j + 1] + 2 * c[j]) / 3;
    d[j] = (c[j + 1] - c[j]) / (3 * h[j]);
  }
  return x => {
    if (x <= xs[0]) return clamp(ys[0]);
    if (x >= xs[n - 1]) return clamp(ys[n - 1]);
    let j = 0;
    while (j < n - 2 && x > xs[j + 1]) j++;
    const t = x - xs[j];
    return clamp(ys[j] + b[j] * t + c[j] * t * t + d[j] * t * t * t);
  };
}

// העקומה שחלה בפועל על ערוץ: נקודות מותאמות גוברות על ה-preset (כמו ב-ffmpeg)
// values (אופציונלי, גל 30): ערכי שדות של מראה מוכן במקום השדות שעל המסך
function _veCurvePointsFor(channel, values) {
  const custom = _veParseCurve(values ? values["curves_" + channel] : _veEl(VE_CURVE_FIELDS[channel]).value);
  if (custom) return custom;
  const preset = VE_CURVE_PRESETS[values ? values.curves_preset : _veValue("veCurvesPreset")];
  return (preset && _veParseCurve(preset[channel])) || [[0, 0], [1, 1]];
}

function _veCurveCanvasDraw() {
  const canvas = _veEl("veCurvesCanvas");
  if (!canvas || !canvas.getContext || !canvas.clientWidth) return;  // מוסתר - יצויר כשיוצג (ResizeObserver)
  const {ctx, width, height} = _uiPrepCanvas(canvas);
  const pad = 6, w = width - pad * 2, hh = height - pad * 2;
  const X = x => pad + x * w, Y = y => pad + (1 - y) * hh;
  _uiGridLines(ctx, width, height, 4);
  ctx.strokeStyle = _uiCssVar("--color-border");
  ctx.setLineDash([3, 3]);
  ctx.beginPath(); ctx.moveTo(X(0), Y(0)); ctx.lineTo(X(1), Y(1)); ctx.stroke();
  ctx.setLineDash([]);
  for (const channel of ["red", "green", "blue", "master"]) {
    const active = channel === _veCurveChannel;
    const fn = _veSpline(_veCurvePointsFor(channel));
    ctx.beginPath();
    ctx.strokeStyle = _uiCssVar(VE_CURVE_COLORS[channel], "#999");
    ctx.globalAlpha = active ? 1 : 0.25;
    ctx.lineWidth = active ? 2 : 1;
    for (let i = 0; i <= 64; i++) { const x = i / 64; if (i) ctx.lineTo(X(x), Y(fn(x))); else ctx.moveTo(X(x), Y(fn(x))); }
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
  for (const [x, y] of _veCurvePointsFor(_veCurveChannel)) {
    ctx.beginPath();
    ctx.fillStyle = _uiCssVar(VE_CURVE_COLORS[_veCurveChannel], "#fff");
    ctx.arc(X(x), Y(y), 4, 0, Math.PI * 2);
    ctx.fill();
  }
}

function _veWriteCurve(channel, points) {
  const input = _veEl(VE_CURVE_FIELDS[channel]);
  const next = _veFormatCurve(points);
  if (input.value !== next) {
    input.value = next;
    input.dispatchEvent(new Event("input", {bubbles: true}));
    input.dispatchEvent(new Event("change", {bubbles: true}));
  }
  _veCurveCanvasDraw();
}

function setVeCurveChannel(channel) {
  _veCurveChannel = channel;
  for (const button of document.querySelectorAll("#veCurvesChannels button")) {
    button.setAttribute("aria-pressed", String(button.dataset.channel === channel));
  }
  for (const [name, id] of Object.entries(VE_CURVE_FIELDS)) _veEl(id).closest(".ve-curve-field").hidden = name !== channel;
  _veCurveCanvasDraw();
}

function resetVeCurveChannel() { _veWriteCurve(_veCurveChannel, [[0, 0], [1, 1]]); }

function _veSetupCurves() {
  const canvas = _veEl("veCurvesCanvas");
  if (!canvas || canvas.dataset.ready) return;
  canvas.dataset.ready = "1";
  const toPoint = (e) => {
    const rect = canvas.getBoundingClientRect(), pad = 6;
    const x = (e.clientX - rect.left - pad) / (rect.width - pad * 2), y = 1 - (e.clientY - rect.top - pad) / (rect.height - pad * 2);
    return [Math.max(0, Math.min(1, x)), Math.max(0, Math.min(1, y))];
  };
  canvas.addEventListener("pointerdown", (e) => {
    const points = _veCurvePointsFor(_veCurveChannel).map(p => [...p]);
    const [px, py] = toPoint(e);
    const rect = canvas.getBoundingClientRect();
    const near = 10 / rect.width;
    let index = points.findIndex(([x, y]) => Math.abs(x - px) < near && Math.abs(y - py) < near * 1.5);
    if (index < 0) {
      if (points.length >= 16) return;
      index = points.findIndex(([x]) => x > px);
      if (index <= 0) return;  // לא מחוץ לנקודות הקצה
      points.splice(index, 0, [px, py]);
    }
    canvas.setPointerCapture(e.pointerId);
    const drag = (ev) => {
      const [x, y] = toPoint(ev);
      const last = points.length - 1;
      const minX = index === 0 ? 0 : points[index - 1][0] + 0.01, maxX = index === last ? 1 : points[index + 1][0] - 0.01;
      points[index] = [index === 0 || index === last ? points[index][0] : Math.max(minX, Math.min(maxX, x)), y];
      _veWriteCurve(_veCurveChannel, points);
    };
    drag(e);
    const up = () => { canvas.removeEventListener("pointermove", drag); canvas.removeEventListener("pointerup", up); };
    canvas.addEventListener("pointermove", drag);
    canvas.addEventListener("pointerup", up);
  });
  // לחיצה כפולה על נקודה פנימית מוחקת אותה
  canvas.addEventListener("dblclick", (e) => {
    const points = _veCurvePointsFor(_veCurveChannel).map(p => [...p]);
    const [px, py] = toPoint(e);
    const near = 10 / canvas.getBoundingClientRect().width;
    const index = points.findIndex(([x, y], i) => i > 0 && i < points.length - 1 && Math.abs(x - px) < near && Math.abs(y - py) < near * 1.5);
    if (index > 0) { points.splice(index, 1); _veWriteCurve(_veCurveChannel, points); }
  });
  for (const id of [...Object.values(VE_CURVE_FIELDS), "veCurvesPreset"]) _veEl(id).addEventListener("input", _veCurveCanvasDraw);
  _veEl("veCurvesPreset").addEventListener("change", _veCurveCanvasDraw);
  if (typeof ResizeObserver === "function") new ResizeObserver(() => _veCurveCanvasDraw()).observe(canvas);
  setVeCurveChannel("master");
}

// --- הדמיה בנגן החי: טבלת צבע לכל ערוץ (colorbalance ואז עקומות ערוץ ואז ראשית) ---

function _veColorbalance(v, s, m, h) {
  const clip = t => Math.max(0, Math.min(1, t));
  const a = 4, b = 0.333, scale = 0.7, l = v;  // בהירות הפיקסל ≈ ערך הערוץ (קירוב לתצוגה)
  const shadows = s * clip((b - l) * a + 0.5) * scale;
  const mids = m * clip((l - b) * a + 0.5) * clip((1 - l - b) * a + 0.5) * scale;
  const highs = h * clip((l + b - 1) * a + 0.5) * scale;
  return clip(v + shadows + mids + highs);
}

function _veGradeActive(opts) {
  return ["grade_shadows", "grade_midtones", "grade_highlights", "curves_master", "curves_red", "curves_green", "curves_blue"]
    .some(key => String(opts[key] || "").trim()) || (opts.curves_preset && opts.curves_preset !== "none");
}

function _veGradeTables(lookValues) {
  const balance = Object.entries(VE_GRADE_RANGES).map(([range, id]) => _veParseTriplet(lookValues ? lookValues["grade_" + range] : _veEl(id).value));
  const master = _veSpline(_veCurvePointsFor("master", lookValues));
  return ["red", "green", "blue"].map((channel, c) => {
    const curve = _veSpline(_veCurvePointsFor(channel, lookValues));
    const values = [];
    for (let i = 0; i <= 32; i++) {
      const x = i / 32;
      values.push(master(curve(_veColorbalance(x, balance[0][c], balance[1][c], balance[2][c]))).toFixed(4));
    }
    return values.join(" ");
  });
}

function _veLiveGradeFilter(opts) {
  if (!_veGradeActive(opts)) return "";
  let svg = document.getElementById("veLiveGradeSvg");
  if (!svg) {
    svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.id = "veLiveGradeSvg";
    svg.setAttribute("aria-hidden", "true");
    svg.classList.add("ve-svg-defs");
    svg.innerHTML = '<filter id="veLiveGrade" color-interpolation-filters="sRGB"><feComponentTransfer>'
      + '<feFuncR type="table"/><feFuncG type="table"/><feFuncB type="table"/></feComponentTransfer></filter>';
    document.body.appendChild(svg);
  }
  const [r, g, b] = _veGradeTables();
  svg.querySelector("feFuncR").setAttribute("tableValues", r);
  svg.querySelector("feFuncG").setAttribute("tableValues", g);
  svg.querySelector("feFuncB").setAttribute("tableValues", b);
  return " url(#veLiveGrade)";
}

// --- כללים (אזהרות ליד השדה) ---

const _veAudioFxActive = (o) => (Number(o.audio_highpass) || 0) > 0 || ["audio_eq_low", "audio_eq_mid", "audio_eq_high"].some(k => Math.abs(Number(o[k]) || 0) >= 0.05)
  || (o.audio_compressor && o.audio_compressor !== "off") || (o.audio_denoise && o.audio_denoise !== "off");
VE_RULES.push(
  {cats: ["audio"], field: "audio_compressor", when: o => _veAudioFxActive(o) && !_veHasAudioOut(o), msg: 'EQ, קומפרסור והפחתת רעש בשמע פועלים רק עם "שמירת אודיו".'},
  {cats: ["color"], field: "curves_preset", when: o => _veGradeActive(o) && _veHwFull(o), msg: "גלגלי צבע ועקומות עם פייפליין GPU מלא - הסינון יעבור ל-CPU (הפענוח נשאר מואץ).", level: "info"},
  {cats: ["audio"], field: "audio_denoise_model", when: o => (o.audio_denoise_model || "").trim() && !/\.rnnn$/i.test(o.audio_denoise_model.trim()), msg: "מודל RNNoise הוא קובץ .rnnn - אחר ייכשל ברינדור.", level: "info"},
);

uiBus.on("ve:fields-applied", () => {
  for (const range of Object.keys(VE_GRADE_RANGES)) _veRenderWheel(range);
  _veCurveCanvasDraw();
});

function _veSetupGrade() {
  _veSetupWheels();
  _veSetupCurves();
}
