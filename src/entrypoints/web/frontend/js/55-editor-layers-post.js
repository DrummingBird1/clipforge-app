// ============================================================================
// גל 7ב של 102-ההצעות: שכבות, קישוטים, הייליטס ועיבוד-אחרי (items 79-89)
// ============================================================================

const VE_WAVE7B_FIELDS = {
  caption_max_chars: {id: "veCaptionMaxChars", kind: "int", label: "אורך שורה בכתוביות"},
  timestamp_overlay: {id: "veTimestampOverlay", kind: "str", label: "חותמת-זמן"},
  progress_bar: {id: "veProgressBar", kind: "bool", label: "סרגל התקדמות"},
  progress_bar_color: {id: "veProgressBarColor", kind: "str", label: "צבע הסרגל"},
  progress_bar_position: {id: "veProgressBarPosition", kind: "str", label: "מיקום הסרגל"},
  progress_bar_height: {id: "veProgressBarHeight", kind: "int", label: "עובי הסרגל"},
  frame_thickness: {id: "veFrameThickness", kind: "int", label: "עובי מסגרת"},
  frame_color: {id: "veFrameColor", kind: "str", label: "צבע מסגרת"},
  vignette: {id: "veVignette", kind: "str", label: "וינייטה"},
  ken_burns: {id: "veKenBurns", kind: "float", label: "Ken Burns"},
  watermark_move_seconds: {id: "veWatermarkMoveSeconds", kind: "float", label: "watermark נודד"},
  pip_audio: {id: "vePipAudio", kind: "bool", label: "שמע מה-PiP"},
  pip_duck: {id: "vePipDuck", kind: "bool", label: "הנמכה בזמן דיבור"},
  intro_path: {id: "veIntroPath", kind: "str", label: "קליפ פתיחה"},
  outro_path: {id: "veOutroPath", kind: "str", label: "קליפ סיום"},
  boomerang: {id: "veBoomerang", kind: "bool", label: "בומרנג"},
  loop_count: {id: "veLoopCount", kind: "int", label: "מספר חזרות"},
  meta_title: {id: "veMetaTitle", kind: "str", label: "כותרת (מטא-דאטה)"},
  meta_comment: {id: "veMetaComment", kind: "str", label: "הערה (מטא-דאטה)"},
  chapters: {id: "veChapters", kind: "str", label: "פרקים"},
  export_gif: {id: "veExportGif", kind: "str", label: "ייצוא GIF/WebP"},
  gif_width: {id: "veGifWidth", kind: "int", label: "רוחב GIF"},
  gif_fps: {id: "veGifFps", kind: "int", label: "קצב GIF"},
  export_audio: {id: "veExportAudio", kind: "str", label: "ייצוא אודיו בלבד"},
};
Object.assign(VE_GENERIC_FIELDS, VE_WAVE7B_FIELDS);
for (const [key, meta] of Object.entries(VE_WAVE7B_FIELDS)) {
  VE_FAVORITABLE_FIELDS[key] = {id: meta.id, label: meta.label};
}
// שכבות: ערך מובנה (json) - בלי מועדפים/איפוס-לשדה (אין לו שורת-קלט בודדת)
VE_GENERIC_FIELDS.layers = {id: "veLayers", kind: "json", label: "שכבות מתוזמנות", onApply: () => _veRenderLayersEditor(true)};

Object.assign(VE_DEPENDENT_FIELDS, {
  veProgressBarColor: () => _veIsChecked("veProgressBar"),
  veWatermarkMoveSeconds: () => _veHasText("veWatermarkPath"),
  vePipAudio: () => _veHasText("vePipPath"),
  vePipDuck: () => _veHasText("vePipPath") && _veIsChecked("vePipAudio"),
  veGifWidth: () => !!_veValue("veExportGif"),
});

const _veLayersOf = (o) => Array.isArray(o.layers) ? o.layers : [];
VE_RULES.push(
  {cats: ["layers", "audio"], field: "pip_audio", when: o => o.pip_audio && !!(o.pip_path || "").trim() && !o.keep_audio, msg: 'שמע מה-PiP דורש "שמירת אודיו".'},
  {cats: ["export", "audio"], field: "export_audio", when: o => !!o.export_audio && !_veHasAudioOut(o), msg: 'ייצוא אודיו בלבד בלי "שמירת אודיו" - לפלט לא יהיה פס-קול לייצא.'},
  {cats: ["export"], field: "boomerang", when: o => o.boomerang, msg: "בומרנג פועל רק על פלט של עד 60 שניות (reverse מחזיק את כל הקליפ בזיכרון).", level: "info"},
  {cats: ["export"], field: "chapters", when: o => !!(o.chapters || "").trim() && ((o.loop_count || 1) > 1 || o.boomerang), msg: "הפרקים מתייחסים לפלט הסופי כולו - עם חזרות/בומרנג הם יסמנו רק את המעבר הראשון.", level: "info"},
  {cats: ["layers", "resources"], field: "progress_bar", when: o => (_veLayersOf(o).length || o.progress_bar || (o.frame_thickness || 0) > 0 || !!o.timestamp_overlay || (o.watermark_move_seconds || 0) > 0 || (o.ken_burns || 0) > 0 || (o.vignette && o.vignette !== "none")) && _veHwFull(o), msg: "שכבות/קישוטים עם פייפליין GPU מלא - מצב היברידי: פענוח והקטנה על ה-GPU, השכבות מצוירות ב-CPU על פריים בגודל הפלט.", level: "info"},
  {cats: ["trim", "export"], field: "remove_ranges", when: o => !!(o.remove_ranges || "").trim() && _veLayersOf(o).some(l => l.end !== null && l.end !== undefined), msg: "זמני השכבות מתייחסים לפלט אחרי החיתוך (לא לקובץ המקור).", level: "info"},
);

const _veBuildSummaryChipsBeforeWave7b = _veBuildSummaryChips;
_veBuildSummaryChips = function (o) {
  const chips = _veBuildSummaryChipsBeforeWave7b(o);
  const extra = [];
  const layers = _veLayersOf(o);
  if (layers.length) extra.push(`📚 ${layers.length} שכבות`);
  if (o.timestamp_overlay) extra.push("🕒 חותמת-זמן");
  if (o.progress_bar) extra.push("▬ סרגל התקדמות");
  if ((o.frame_thickness || 0) > 0) extra.push("🖼️ מסגרת");
  if (o.vignette && o.vignette !== "none") extra.push("🌘 וינייטה");
  if ((o.ken_burns || 0) > 0) extra.push(`🔍 Ken Burns ${Math.round(o.ken_burns * 100)}%`);
  if ((o.watermark_move_seconds || 0) > 0 && (o.watermark_path || "").trim()) extra.push("🔄 watermark נודד");
  if (o.pip_audio && (o.pip_path || "").trim()) extra.push(o.pip_duck ? "🎙️ PiP + ducking" : "🎙️ שמע PiP");
  if ((o.intro_path || "").trim() || (o.outro_path || "").trim()) extra.push("🎬 intro/outro");
  if (o.boomerang) extra.push("🔁 בומרנג");
  if ((o.loop_count || 1) > 1) extra.push(`🔂 x${o.loop_count}`);
  if ((o.meta_title || "").trim() || (o.meta_comment || "").trim()) extra.push("🏷️ מטא-דאטה");
  const chapterCount = (o.chapters || "").split("\n").filter(l => /^\s*(\d{1,2}:)?\d{1,2}:\d{2}/.test(l)).length;
  if (chapterCount) extra.push(`📑 ${chapterCount} פרקים`);
  if (o.export_gif) extra.push(o.export_gif === "both" ? "GIF + WebP" : o.export_gif.toUpperCase());
  if (o.export_audio) extra.push(`🎵 ${o.export_audio.toUpperCase()}`);
  const countIndex = chips.findIndex(c => c.startsWith("📁 "));
  chips.splice(countIndex >= 0 ? countIndex : chips.length, 0, ...extra);
  return chips;
};

// --- item 79/80: עורך שכבות מתוזמנות ---
const VE_LAYER_KIND_ICONS = {text: "🔤", image: "🖼️", timer: "⏱️", timestamp: "🕒", video: "🎞️"};
// גל 26: שכבת וידאו (B-roll) - איך הקליפ ממלא את הפריים, ומה קורה לשמע שלו
const VE_BROLL_FITS = {fill: "מסך מלא", fit: "מותאם (שוליים)", pip: "חלון (PiP)"};
const VE_BROLL_AUDIO = {mute: "בלי השמע שלו", mix: "מעורבב עם הראשי", replace: "במקום השמע הראשי"};
const VE_LAYER_POSITIONS = {"top-left": "⬆️⬅️", "top-center": "⬆️", "top-right": "⬆️➡️", "center": "⏺️", "bottom-left": "⬇️⬅️", "bottom-center": "⬇️", "bottom-right": "⬇️➡️"};
const VE_LAYER_ANIMATIONS = {none: "בלי הנפשה", fade: "fade", typewriter: "מכונת-כתיבה", slide: "החלקה"};
let _veLayersLastWritten = null;
let _veLayerIdCounter = 0;

function _veLayersValue() {
  try { const parsed = JSON.parse(document.getElementById("veLayers").value || "[]"); return Array.isArray(parsed) ? parsed : []; }
  catch (e) { return []; }
}

function _veWriteLayers(layers) {
  const input = document.getElementById("veLayers");
  input.value = JSON.stringify(layers);
  _veLayersLastWritten = input.value;
  input.dispatchEvent(new Event("change", {bubbles: true}));
}

function addVeLayer(kind) {
  const layers = _veLayersValue();
  const base = {type: kind, start: 0, end: null, position: kind === "timestamp" ? "bottom-right" : "bottom-center", opacity: 1};
  if (kind === "image") Object.assign(base, {path: "", scale: 0.2, position: "top-left"});
  else if (kind === "video") Object.assign(base, {path: "", source_in: 0, fit: "fill", scale: 0.35, position: "top-right", audio: "mute", volume: 1});
  else Object.assign(base, {text: kind === "text" ? "" : "", font_size: kind === "text" ? 48 : 36, color: "#FFFFFF", box: kind !== "text", animation: kind === "text" ? "fade" : "none"});
  if (kind === "timer") Object.assign(base, {timer_mode: "countdown", timer_seconds: null, position: "top-right"});
  Object.assign(base, _veClipLayerTag());  // גל 30: במצב עריכת קליפ - שכבה של הקליפ בלבד
  layers.push(base);
  _veWriteLayers(layers);
  _veRenderLayersEditor(true);
  const rows = document.querySelectorAll("#veLayersRows .ve-layer-row");
  const last = rows[rows.length - 1];
  const focusable = last && last.querySelector(".ve-layer-content");
  if (focusable) focusable.focus();
}

function _veLayerSelect(options, value, title) {
  const select = document.createElement("select");
  select.title = title;
  select.setAttribute("aria-label", title);
  for (const [v, label] of Object.entries(options)) {
    const option = document.createElement("option");
    option.value = v; option.textContent = label;
    select.appendChild(option);
  }
  select.value = value;
  return select;
}

function _veLayerInput(type, value, className, title, attrs) {
  const input = document.createElement("input");
  input.type = type; input.className = className || ""; input.title = title || "";
  input.value = value === null || value === undefined ? "" : value;
  for (const [k, v] of Object.entries(attrs || {})) input.setAttribute(k, v);
  return input;
}

function _veLayerRowEl(layer, index, total) {
  const row = document.createElement("div");
  row.className = "ve-layer-row";
  row.dataset.index = String(index);
  row.dataset.type = layer.type;
  const kind = document.createElement("span");
  kind.className = "ve-layer-kind"; kind.textContent = VE_LAYER_KIND_ICONS[layer.type] || "?";
  kind.title = {text: "טקסט", image: "תמונה/מדבקה", timer: "טיימר", timestamp: "חותמת-זמן", video: "וידאו (B-roll)"}[layer.type] || "";
  row.appendChild(kind);
  const inputs = {};
  if (layer.type === "text") {
    inputs.text = _veLayerInput("text", layer.text, "ve-layer-content", "הטקסט של השכבה", {placeholder: "טקסט...", "aria-label": "טקסט השכבה"});
    row.appendChild(inputs.text);
  } else if (layer.type === "image") {
    const id = `veLayerPath_${++_veLayerIdCounter}`;
    inputs.path = _veLayerInput("text", layer.path, "ve-layer-content", "נתיב התמונה (PNG עם שקיפות מומלץ)", {id, "data-ve-browse": "image", placeholder: "C:\\...\\sticker.png", "aria-label": "נתיב תמונה"});
    const browse = document.createElement("button");
    browse.type = "button"; browse.textContent = "📂"; browse.title = "בחר תמונה...";
    browse.onclick = () => openVeFieldFileBrowser(id);
    row.append(inputs.path, browse);
    inputs.scale = _veLayerInput("number", Math.round((layer.scale || 0.2) * 100), "", "רוחב התמונה כאחוז מרוחב הפריים", {min: "2", max: "100", step: "1", style: "width:55px", "aria-label": "גודל (%)"});
    row.append(inputs.scale);
  } else if (layer.type === "video") {
    const id = `veLayerPath_${++_veLayerIdCounter}`;
    inputs.path = _veLayerInput("text", layer.path, "ve-layer-content", "קליפ ה-B-roll (וידאו) שמוכנס בטווח הזמן", {id, "data-ve-browse": "video", placeholder: "C:\\...\\broll.mp4", "aria-label": "נתיב קליפ B-roll"});
    const browse = document.createElement("button");
    browse.type = "button"; browse.textContent = "📂"; browse.title = "בחר קליפ...";
    browse.onclick = () => openVeFieldFileBrowser(id);
    row.append(inputs.path, browse);
    inputs.source_in = _veLayerInput("text", _veFormatTime(layer.source_in || 0), "ve-layer-time", "מאיזו נקודה בקליפ להתחיל (שניות/mm:ss)", {"aria-label": "התחלה בקליפ"});
    inputs.fit = _veLayerSelect(VE_BROLL_FITS, layer.fit || "fill", "איך הקליפ ממלא את הפריים");
    inputs.scale = _veLayerInput("number", Math.round((layer.scale || 0.35) * 100), "u-width-60px", "רוחב החלון כאחוז מרוחב הפריים (רק בחלון/PiP)", {min: "5", max: "100", step: "1", "aria-label": "גודל החלון (%)"});
    inputs.audio = _veLayerSelect(VE_BROLL_AUDIO, layer.audio || "mute", "מה קורה לשמע של הקליפ");
    const inLabel = document.createElement("span");
    inLabel.className = "ve-field-msg";
    inLabel.textContent = "בקליפ מ-";
    row.append(inLabel, inputs.source_in, inputs.fit, inputs.scale, inputs.audio);
  } else if (layer.type === "timer") {
    inputs.timer_mode = _veLayerSelect({countdown: "ספירה לאחור", elapsed: "זמן שעבר"}, layer.timer_mode || "countdown", "סוג הטיימר");
    inputs.timer_seconds = _veLayerInput("text", layer.timer_seconds || "", "ve-layer-time", "ספירה לאחור מ- (שניות או mm:ss) - ריק = עד סוף השכבה", {placeholder: "מ- (אוטו')", "aria-label": "ספירה מ-"});
    row.append(inputs.timer_mode, inputs.timer_seconds);
  }
  inputs.position = _veLayerSelect(VE_LAYER_POSITIONS, layer.position || "bottom-center", "מיקום");
  inputs.start = _veLayerInput("text", _veFormatTime(layer.start || 0), "ve-layer-time", "מתחיל ב- (שניות/mm:ss, בזמן הפלט)", {"aria-label": "התחלה"});
  inputs.end = _veLayerInput("text", layer.end === null || layer.end === undefined ? "" : _veFormatTime(layer.end), "ve-layer-time", "מסתיים ב- (ריק = עד הסוף)", {placeholder: "סוף", "aria-label": "סיום"});
  row.append(inputs.position, inputs.start, inputs.end);
  if (layer.type !== "image" && layer.type !== "video") {
    if (layer.type !== "timestamp") {
      inputs.animation = _veLayerSelect(VE_LAYER_ANIMATIONS, layer.animation || "none", "הנפשה");
      row.append(inputs.animation);
    }
    inputs.font_size = _veLayerInput("number", layer.font_size || 48, "", "גודל גופן", {min: "8", max: "300", step: "1", style: "width:55px", "aria-label": "גודל גופן"});
    inputs.color = _veLayerInput("color", (layer.color || "#FFFFFF").toLowerCase(), "", "צבע", {"aria-label": "צבע"});
    const boxLabel = document.createElement("label");
    boxLabel.title = "רקע כהה מאחורי הטקסט";
    inputs.box = _veLayerInput("checkbox", "", "", "", {"aria-label": "רקע"});
    inputs.box.checked = !!layer.box;
    boxLabel.append(inputs.box, document.createTextNode(" רקע"));
    row.append(inputs.font_size, inputs.color, boxLabel);
  }
  inputs.opacity = _veLayerInput("range", layer.opacity === undefined ? 1 : layer.opacity, "", "שקיפות", {min: "0", max: "1", step: "0.05", style: "width:70px", "aria-label": "שקיפות"});
  row.append(inputs.opacity);
  const actions = [["↑", "הזז למטה בערימה (מתחת)", -1, index === 0], ["↓", "הזז למעלה בערימה (מעל)", 1, index === total - 1]];
  for (const [text, title, delta, disabled] of actions) {
    const btn = document.createElement("button");
    btn.type = "button"; btn.textContent = text; btn.title = title; btn.disabled = disabled;
    btn.onclick = () => _veMoveLayer(index, delta);
    row.appendChild(btn);
  }
  const remove = document.createElement("button");
  remove.type = "button"; remove.textContent = "✕"; remove.title = "מחק שכבה"; remove.className = "ve-layer-remove";
  remove.onclick = () => { const layers = _veLayersValue(); layers.splice(index, 1); _veWriteLayers(layers); _veRenderLayersEditor(true); };
  row.appendChild(remove);
  // גל 23: כל שדה מזוהה ב-data-field - לא לפי title/aria-label, שמתורגמים בממשק האנגלי
  for (const [field, el] of Object.entries(inputs)) el.dataset.field = field;
  for (const el of Object.values(inputs)) {
    el.addEventListener("input", () => _veSyncLayersFromRows());
    el.addEventListener("change", () => _veSyncLayersFromRows());
  }
  return row;
}

function _veLayerFromRow(row, previous) {
  const get = (selector) => row.querySelector(selector);
  const layer = {...previous};
  const text = get("input.ve-layer-content:not([data-ve-browse])");
  if (row.dataset.type === "text" && text) layer.text = text.value;
  if (row.dataset.type === "image") {
    layer.path = get("input[data-ve-browse]").value.trim();
    const scale = parseFloat(get("input[type=number]").value);
    layer.scale = Number.isFinite(scale) ? Math.max(0.02, Math.min(1, scale / 100)) : 0.2;
  }
  if (row.dataset.type === "video") {
    layer.path = get("input[data-ve-browse]").value.trim();
    const scale = parseFloat(get("input[data-field=scale]").value);
    layer.scale = Number.isFinite(scale) ? Math.max(0.05, Math.min(1, scale / 100)) : 0.35;
  }
  for (const [field, key] of [["position", "position"], ["animation", "animation"], ["timer_mode", "timer_mode"], ["fit", "fit"], ["audio", "audio"]]) {
    const select = row.querySelector(`select[data-field=${field}]`);
    if (select) layer[key] = select.value;
  }
  const timeValue = (el) => el.value.trim() === "" ? null : _veParseTimeText(el.value);
  for (const el of row.querySelectorAll("input.ve-layer-time")) {
    const value = timeValue(el);
    el.classList.toggle("ve-invalid", el.value.trim() !== "" && value === null);
    if (el.dataset.field === "start") layer.start = value === null ? 0 : value;
    else if (el.dataset.field === "end") layer.end = value;
    else if (el.dataset.field === "timer_seconds") layer.timer_seconds = value;
    else if (el.dataset.field === "source_in") layer.source_in = value === null ? 0 : value;
  }
  const fontSize = row.querySelector("input[data-field=font_size]");
  if (fontSize) layer.font_size = parseInt(fontSize.value, 10) || 48;
  const color = row.querySelector("input[type=color]");
  if (color) layer.color = color.value.toUpperCase();
  const box = row.querySelector("input[data-field=box]");
  if (box) layer.box = box.checked;
  layer.opacity = parseFloat(row.querySelector("input[type=range]").value);
  return layer;
}

function _veSyncLayersFromRows() {
  const previous = _veLayersValue();
  const rows = document.querySelectorAll("#veLayersRows .ve-layer-row");
  const layers = [...rows].map((row, i) => _veLayerFromRow(row, previous[i] || {type: row.dataset.type}));
  _veWriteLayers(layers);
}

function _veMoveLayer(index, delta) {
  const layers = _veLayersValue();
  const target = index + delta;
  if (target < 0 || target >= layers.length) return;
  [layers[index], layers[target]] = [layers[target], layers[index]];
  _veWriteLayers(layers);
  _veRenderLayersEditor(true);
}

function _veRenderLayersEditor(forceReload) {
  const input = document.getElementById("veLayers");
  const box = document.getElementById("veLayersRows");
  if (!input || !box) return;
  if (!forceReload && input.value === _veLayersLastWritten) return;
  _veLayersLastWritten = input.value;
  const layers = _veLayersValue();
  box.innerHTML = "";
  layers.forEach((layer, i) => box.appendChild(_veLayerRowEl(layer, i, layers.length)));
  // גל 31: בלי שכבות - המצב הריק ברשימת השכבות (מעל) מסביר מה עושים
}
// איפוס-לשדה/איפוס-קטגוריה/החלת פרופיל כותבים לשדה הנסתר - העורך נבנה מחדש מהערך
document.getElementById("veLayers").addEventListener("change", () => _veRenderLayersEditor(false));

// --- item 85: זהה הייליטס ---
async function detectVeHighlights() {
  const status = document.getElementById("veHighlightStatus");
  if (!state.folder) { status.textContent = "בחר תיקייה קודם."; return; }
  const file = (document.getElementById("vePreviewFile") || {}).value || null;
  status.textContent = "🔎 מנתח את פס-הקול...";
  const body = {
    folder: state.folder, file,
    threshold_db: parseFloat(_veValue("veHighlightThreshold")) || 18,
    before: parseFloat(_veValue("veHighlightBefore")), after: parseFloat(_veValue("veHighlightAfter")),
  };
  let data;
  try {
    const res = await fetch("/api/video_editor/detect_highlights", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    data = await res.json();
    if (!res.ok) { status.textContent = "⚠️ " + (data.error || "הזיהוי נכשל"); return; }
  } catch (e) { status.textContent = "⚠️ הזיהוי נכשל"; return; }
  if (!data.peaks.length) { status.textContent = `לא נמצאו שיאים ב-${data.file} - נסה סף נמוך יותר.`; return; }
  const input = document.getElementById("veRemoveRanges");
  input.value = JSON.stringify(data.remove_ranges);
  input.dispatchEvent(new Event("input", {bubbles: true}));
  input.dispatchEvent(new Event("change", {bubbles: true}));
  _veRenderRangesEditor(true);
  status.textContent = `✅ ${data.peaks.length} שיאים ב-${data.file} - נשארים ${_veFormatTime(data.kept_seconds)} מתוך ${_veFormatTime(data.duration)}.`;
  // גל 10ב: 🔥 על ציר-הזמן בכל שיא שנמצא
  _veHighlightMarkers = {file: data.file, peaks: data.peaks};
  _veRenderTimelineOverlays();
}

_veRenderLayersEditor(true);

