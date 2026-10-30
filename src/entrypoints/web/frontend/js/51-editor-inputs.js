// ============================================================================
// גל 3 של 102-ההצעות: שדות וקלט (items 19-28)
// ============================================================================

// item: בוררי-קבצים "📂" ליד כל שדה-נתיב (watermark/PiP/LUT/פס-קול), אותו חלון
// דפדוף בדיוק כמו בחירת התיקייה, במצב "בחירת קובץ" עם סינון לפי סוג.
const VE_AUDIO_VIDEO_EXTENSIONS = [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ...VE_VIDEO_EXTENSIONS];
const VE_BROWSE_KINDS = {
  image: {label: "תמונה", exts: [".png", ".jpg", ".jpeg", ".webp", ".bmp"]},
  video: {label: "וידאו", exts: VE_VIDEO_EXTENSIONS},
  lut: {label: "LUT", exts: [".cube", ".3dl"]},
  audio: {label: "אודיו/וידאו", exts: VE_AUDIO_VIDEO_EXTENSIONS},
};

function _veDirname(path) {
  const i = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return i > 0 ? path.slice(0, i) : "";
}

async function openVeFieldFileBrowser(fieldId) {
  const input = document.getElementById(fieldId);
  const kind = VE_BROWSE_KINDS[input.dataset.veBrowse] || null;
  state.browseTarget = "ve-field:" + fieldId;
  state.browseMode = "file";
  state.browseExtensions = kind ? kind.exts : null;
  const current = input.value.trim();
  await browseTo(current ? _veDirname(current) : (state.folder || ""));
  document.getElementById("modalBg").classList.add("show");
}

function _veSetFieldValue(input, value) {
  input.value = value;
  input.dispatchEvent(new Event("input", {bubbles: true}));
  input.dispatchEvent(new Event("change", {bubbles: true}));
}

// item: אימות נתיב חי - גבול אדום + "הקובץ לא נמצא" תוך כדי הקלדה (debounced),
// במקום לגלות את זה רק באמצע ריצה כ-"[WARNING] ... ממשיך בלי watermark".
const _vePathCheckTimers = {};

function _veScheduleVePathCheck(input) {
  clearTimeout(_vePathCheckTimers[input.id]);
  _vePathCheckTimers[input.id] = setTimeout(() => _veCheckPathField(input), 300);
}

async function _veCheckPathField(input) {
  const msg = document.querySelector(`.ve-field-msg[data-for="${input.id}"]`);
  const value = input.value.trim();
  input.classList.remove("ve-invalid", "ve-warn-input");
  if (msg) { msg.textContent = ""; msg.className = "ve-field-msg"; }
  if (!value) return;
  let info;
  try { info = await (await fetch("/api/path_info?path=" + encodeURIComponent(value))).json(); }
  catch (e) { return; }
  if (input.value.trim() !== value || !msg) return;  // הוקלד משהו אחר בינתיים
  const kind = VE_BROWSE_KINDS[input.dataset.veBrowse];
  if (!info.exists) { input.classList.add("ve-invalid"); msg.classList.add("bad"); msg.textContent = "⚠️ הקובץ לא נמצא"; }
  else if (info.is_dir) { input.classList.add("ve-invalid"); msg.classList.add("bad"); msg.textContent = "⚠️ זו תיקייה, לא קובץ"; }
  else if (kind && !kind.exts.includes(info.ext)) { input.classList.add("ve-warn-input"); msg.classList.add("warn"); msg.textContent = `⚠️ סוג לא צפוי (${info.ext || "בלי סיומת"})`; }
  else { msg.textContent = "✓ " + _formatFileSize(info.size || 0); }
}

// item: <input type="color"> לצבעי כתוביות/טקסט/כרומה-קי - דגימה ויזואלית
// צמודה לשדה הטקסט הקיים (שנשאר מקור-האמת, כי כרומה-קי צריך 0xRRGGBB ולא #).
function _veNormalizeColor(text) {
  const match = String(text || "").trim().match(/^(?:#|0x)?([0-9a-f]{6})$/i);
  return match ? "#" + match[1].toLowerCase() : null;
}

function _veSyncColorSwatch(input) {
  const swatch = input.parentElement.querySelector(`.ve-color-swatch[data-for="${input.id}"]`);
  const normalized = _veNormalizeColor(input.value);
  if (swatch && normalized) swatch.value = normalized;
  input.classList.toggle("ve-invalid", !!input.value.trim() && !normalized);
}

// item: בורר גופנים מהגופנים המותקנים (/api/system_fonts), עם תצוגה חיה "Aa אב".
let _veFontsLoaded = false;
async function _veLoadSystemFonts() {
  if (_veFontsLoaded) return;
  _veFontsLoaded = true;
  try {
    const {fonts} = await (await fetch("/api/system_fonts")).json();
    const list = document.getElementById("veSystemFontsList");
    list.innerHTML = "";
    for (const font of fonts) {
      const option = document.createElement("option");
      option.value = font;
      list.appendChild(option);
    }
  } catch (e) { _veFontsLoaded = false; }
}

function _veSyncFontPreview(input) {
  const preview = input.parentElement.querySelector(`.ve-font-preview[data-for="${input.id}"]`);
  if (preview) preview.style.fontFamily = `"${input.value.replace(/"/g, "")}", sans-serif`;
}

// item: קלט mm:ss לשדות שניות - "90", "1:30", "01:02:03", "1:30.5" - כולם תקינים.
function _veParseTime(text) {
  const raw = String(text ?? "").trim();
  if (!raw) return NaN;
  const match = raw.match(/^(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)$/);
  if (match) return (match[1] ? parseInt(match[1], 10) * 3600 : 0) + parseInt(match[2], 10) * 60 + parseFloat(match[3]);
  if (!/^\d+(?:\.\d+)?$/.test(raw)) return NaN;
  return parseFloat(raw);
}

function _veFormatTime(seconds) {
  if (!Number.isFinite(seconds)) return "";
  const tenths = Math.round(Math.max(0, seconds) * 10);  // עיגול לפני הפירוק - 59.96 -> 1:00, לא 0:59.10
  const h = Math.floor(tenths / 36000), m = Math.floor((tenths % 36000) / 600), rest = tenths % 600;
  const sText = String(Math.floor(rest / 10)).padStart(2, "0") + (rest % 10 ? "." + (rest % 10) : "");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sText}` : `${m}:${sText}`;
}

function _veTimeValue(id, blankValue) {
  const el = document.getElementById(id);
  if (!el || !String(el.value).trim()) return blankValue;
  const seconds = _veParseTime(el.value);
  return Number.isFinite(seconds) ? seconds : blankValue;
}

function _veSyncTimeHint(input) {
  const hint = input.parentElement.querySelector(`.ve-time-hint[data-for="${input.id}"]`);
  const raw = input.value.trim();
  const seconds = _veParseTime(raw);
  input.classList.toggle("ve-invalid", !!raw && !Number.isFinite(seconds));
  if (!hint) return;
  if (!raw || !Number.isFinite(seconds)) { hint.textContent = raw ? "⚠️ זמן לא תקין" : ""; return; }
  hint.textContent = raw.includes(":") ? `= ${Math.round(seconds * 10) / 10} שנ'` : (seconds >= 60 ? `= ${_veFormatTime(seconds)}` : "");
}

// item: עורך ויזואלי לחיתוך-טווחים - שורות התחלה/סוף עם ➕/✖ במקום [[10,15],[40,42]].
// veRemoveRanges (JSON) נשאר מקור-האמת (פרופילים/מועדפים/ה-CLI קוראים אותו) -
// העורך הוא רק תצוגה עליו. שורה לא-תקינה (סוף<=התחלה) מסומנת ולא נשלחת.
let _veRangesDraft = [];
let _veRangesLastWritten = null;

function _veRangesFromJson(raw) {
  if (!String(raw || "").trim()) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    return parsed.map(r => Array.isArray(r) && r.length === 2 ? {start: String(r[0]), end: String(r[1])} : null).filter(Boolean);
  } catch (e) { return null; }
}

function _veRangesWrite() {
  const valid = [];
  for (const row of _veRangesDraft) {
    const start = _veParseTime(row.start), end = _veParseTime(row.end);
    row.bad = !(Number.isFinite(start) && Number.isFinite(end) && end > start && start >= 0);
    if (!row.bad) valid.push([Math.round(start * 1000) / 1000, Math.round(end * 1000) / 1000]);
  }
  const input = document.getElementById("veRemoveRanges");
  const next = valid.length ? JSON.stringify(valid) : "";
  _veRangesLastWritten = next;
  if (input.value !== next) _veSetFieldValue(input, next);
}

function _veRenderRangesEditor(forceReload) {
  const input = document.getElementById("veRemoveRanges");
  const box = document.getElementById("veRangesEditor");
  if (!input.hidden) { box.hidden = true; return; }
  box.hidden = false;
  if (forceReload || input.value !== _veRangesLastWritten) {
    const parsed = _veRangesFromJson(input.value);
    _veRangesDraft = parsed === null ? [] : parsed.map(r => ({start: _veFormatTime(parseFloat(r.start)), end: _veFormatTime(parseFloat(r.end))}));
    _veRangesLastWritten = input.value;
    if (parsed === null) box.dataset.jsonError = "1"; else delete box.dataset.jsonError;
  }
  box.innerHTML = "";
  if (box.dataset.jsonError) {
    const err = document.createElement("div");
    err.className = "ve-field-msg bad";
    err.textContent = "⚠️ ה-JSON הקיים לא תקין - עבור ל-{ } JSON כדי לתקן אותו";
    box.appendChild(err);
  }
  _veRangesDraft.forEach((row, index) => {
    const line = document.createElement("div");
    line.className = "ve-range-row" + (row.bad ? " bad" : "");
    const startInput = document.createElement("input");
    startInput.type = "text"; startInput.value = row.start; startInput.placeholder = "התחלה"; startInput.setAttribute("aria-label", `התחלת טווח ${index + 1}`);
    const endInput = document.createElement("input");
    endInput.type = "text"; endInput.value = row.end; endInput.placeholder = "סוף"; endInput.setAttribute("aria-label", `סוף טווח ${index + 1}`);
    const length = document.createElement("span");
    const s = _veParseTime(row.start), e = _veParseTime(row.end);
    length.className = "ve-field-msg" + (row.bad ? " bad" : "");
    length.textContent = row.bad ? "⚠️ סוף חייב להיות אחרי ההתחלה" : `(${Math.round((e - s) * 10) / 10} שנ' יוסרו)`;
    const remove = document.createElement("button");
    remove.type = "button"; remove.textContent = "✖"; remove.title = "הסר טווח";
    remove.onclick = () => { _veRangesDraft.splice(index, 1); _veRangesWrite(); _veRenderRangesEditor(); };
    for (const [el, key] of [[startInput, "start"], [endInput, "end"]]) {
      el.addEventListener("change", () => { row[key] = el.value; _veRangesWrite(); _veRenderRangesEditor(); });
    }
    line.append(`#${index + 1}`, startInput, "→", endInput, length, remove);
    box.appendChild(line);
  });
  const add = document.createElement("button");
  add.type = "button";
  add.textContent = "➕ הוסף טווח להסרה";
  add.onclick = () => {
    const last = _veRangesDraft.length ? _veParseTime(_veRangesDraft[_veRangesDraft.length - 1].end) : 0;
    const start = Number.isFinite(last) ? last + 5 : 0;
    _veRangesDraft.push({start: _veFormatTime(start), end: _veFormatTime(start + 5)});
    _veRangesWrite();
    _veRenderRangesEditor();
  };
  box.appendChild(add);
}

function toggleVeRangesJson() {
  const input = document.getElementById("veRemoveRanges");
  input.hidden = !input.hidden;
  document.getElementById("veRemoveRangesJsonToggle").textContent = input.hidden ? "{ } JSON" : "☰ עורך ויזואלי";
  _veRenderRangesEditor(true);
}

// item: סליידר ל-trim מקושר למשך הקובץ הראשון בתור - התחלה/סוף בגרירה, כותב
// ל-veTrimStart/veTrimDuration (סוף = משך הקובץ -> "עד הסוף", בלי אורך מפורש).
let _veTrimRef = null;
let _veTrimRefTimer = null;

function _veScheduleTrimReference() {
  clearTimeout(_veTrimRefTimer);
  _veTrimRefTimer = setTimeout(_veLoadTrimReference, 400);
}

async function _veFirstQueueFilePath() {
  if (!state.folder) return null;
  if (_veTimeScope === "clip" && _veClipScopeFile) return state.folder.replace(/[\\/]+$/, "") + "/" + _veClipScopeFile;  // גל 30: עריכת קליפ
  const selected = _veQueueState.find(f => f.selected);
  if (selected) return state.folder.replace(/[\\/]+$/, "") + "/" + selected.name;
  try {
    const data = await (await fetch("/api/browse?path=" + encodeURIComponent(state.folder))).json();
    const first = (data.files || []).find(f => VE_VIDEO_EXTENSIONS.some(ext => f.name.toLowerCase().endsWith(ext)));
    return first ? data.path.replace(/[\\/]+$/, "") + "/" + first.name : null;
  } catch (e) { return null; }
}

async function _veLoadTrimReference() {
  _vePopulatePreviewFiles();  // item 40: אותו רגע (תיקייה/תור השתנו) מעדכן גם את בורר קובץ-התצוגה-המקדימה
  const path = await _veFirstQueueFilePath();
  _veTrimRef = null;
  if (path) {
    try {
      const res = await fetch("/api/video_editor/probe?path=" + encodeURIComponent(path));
      const info = await res.json();
      if (res.ok && info.duration) _veTrimRef = {name: path.split(/[\\/]/).pop(), path, duration: info.duration, info};
    } catch (e) { /* בלי סליידר */ }
  }
  _veRenderTrimSlider();
}

function _veRenderTrimSlider() {
  const box = document.getElementById("veTrimSliderBox");
  if (!box) return;
  if (!_veTrimRef) { box.hidden = true; box.innerHTML = ""; return; }
  const duration = _veTrimRef.duration;
  const start = Math.min(duration, _veTimeValue("veTrimStart", 0));
  const length = _veTimeValue("veTrimDuration", null);
  const end = length === null ? duration : Math.min(duration, start + length);
  box.hidden = false;
  box.innerHTML = "";
  const title = document.createElement("div");
  title.textContent = _veTimeScope === "clip" ? `🎚️ ${_veTrimRef.name} (${_veFormatTime(duration)})` : `🎚️ לפי הקובץ הראשון בתור: ${_veTrimRef.name} (${_veFormatTime(duration)})`;
  box.appendChild(title);
  const makeSlider = (labelText, value, onInput) => {
    const label = document.createElement("label");
    label.append(labelText);
    const range = document.createElement("input");
    range.type = "range"; range.min = "0"; range.max = String(duration); range.step = "0.1"; range.value = String(value);
    range.setAttribute("aria-label", labelText);
    const out = document.createElement("span");
    out.textContent = _veFormatTime(value);
    range.addEventListener("input", () => { out.textContent = _veFormatTime(parseFloat(range.value)); onInput(parseFloat(range.value)); });
    label.append(range, out);
    box.appendChild(label);
    return range;
  };
  let startRange, endRange;
  const apply = () => {
    let s = parseFloat(startRange.value), e = parseFloat(endRange.value);
    if (e <= s) { e = Math.min(duration, s + 0.1); endRange.value = String(e); }
    document.getElementById("veTrimStart").value = s > 0 ? String(Math.round(s * 10) / 10) : "0";
    document.getElementById("veTrimDuration").value = e >= duration - 0.05 ? "" : String(Math.round((e - s) * 10) / 10);
    for (const id of ["veTrimStart", "veTrimDuration"]) {
      const el = document.getElementById(id);
      el.dispatchEvent(new Event("input", {bubbles: true}));
      _veSyncTimeHint(el);
    }
  };
  startRange = makeSlider("התחלה", start, apply);
  endRange = makeSlider("סוף", end, apply);
  endRange.addEventListener("change", () => document.getElementById("veTrimDuration").dispatchEvent(new Event("change", {bubbles: true})));
}

// גל 28: ההסבר המלא מהמקראה (מקור-אמת אחד עם הדסקטופ) - ה-title הקצר רק כגיבוי
function _veRowHelpText(row, fallback) {
  const input = row.querySelector("input[id], select[id], textarea[id]");
  const key = input && Object.keys(VE_FAVORITABLE_FIELDS).find(k => VE_FAVORITABLE_FIELDS[k].id === input.id);
  const help = key && _fieldHelpCache && _fieldHelpCache[key];
  return help && help.tooltip && help.tooltip.length > (fallback || "").length ? help.tooltip : fallback;
}

// item: ⓘ בלחיצה במקום tooltip-הובר בלבד - במובייל/מגע אין הובר בכלל.
function _veToggleInfo(row, btn, text) {
  const next = row.nextElementSibling;
  if (next && next.classList.contains("ve-info-box")) {
    next.remove();
    btn.setAttribute("aria-expanded", "false");
    return;
  }
  for (const open of document.querySelectorAll("#veCategories .ve-info-box")) open.remove();
  for (const other of document.querySelectorAll("#veCategories .ve-info-btn[aria-expanded=true]")) other.setAttribute("aria-expanded", "false");
  const box = document.createElement("div");
  box.className = "ve-info-box";
  box.setAttribute("role", "note");
  box.textContent = text;
  row.after(box);
  btn.setAttribute("aria-expanded", "true");
}

// item: סליידרים עם ערך מספרי לעריכה - לכל סליידר מצורף שדה מספר מסונכרן בשני
// הכיוונים (במקום תווית-ערך לקריאה בלבד). סליידר "percent" (שבר 0-1) מוצג באחוזים.
function _veSyncRangeNumber(range) {
  const number = range.parentElement.querySelector(`.ve-range-number[data-for="${range.id}"]`);
  if (!number || document.activeElement === number) return;
  const value = parseFloat(range.value);
  number.value = range.dataset.veValueFormat === "percent" ? String(Math.round(value * 100)) : String(value);
}

// מחבר את כל שיפורי-הקלט לשדות (פעם אחת בטעינה): 📂, אימות-נתיב, צבע, גופן,
// רמז-זמן, ℹ️, שדה-מספר לסליידר, סליידר-חיתוך ועורך-טווחים.
function _veEnhanceInputs() {
  const root = document.getElementById("veCategories");
  for (const input of root.querySelectorAll("input[data-ve-browse]")) {
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "ve-browse-btn"; btn.textContent = "📂";
    btn.title = `בחר קובץ ${VE_BROWSE_KINDS[input.dataset.veBrowse].label}...`;
    btn.setAttribute("aria-label", btn.title);
    btn.onclick = () => openVeFieldFileBrowser(input.id);
    const msg = document.createElement("span");
    msg.className = "ve-field-msg"; msg.dataset.for = input.id; msg.setAttribute("aria-live", "polite");
    input.after(btn, msg);
    input.addEventListener("input", () => _veScheduleVePathCheck(input));
    input.addEventListener("change", () => _veScheduleVePathCheck(input));
  }
  for (const input of root.querySelectorAll("input[data-ve-color]")) {
    const swatch = document.createElement("input");
    swatch.type = "color"; swatch.className = "ve-color-swatch"; swatch.dataset.for = input.id;
    swatch.setAttribute("aria-label", "בחירת צבע");
    swatch.addEventListener("input", () => {
      const hex = swatch.value.slice(1).toUpperCase();
      _veSetFieldValue(input, input.dataset.veColor === "0x" ? "0x" + hex : "#" + hex);
    });
    input.after(swatch);
    input.addEventListener("input", () => _veSyncColorSwatch(input));
    _veSyncColorSwatch(input);
  }
  for (const input of root.querySelectorAll("input[data-ve-font]")) {
    const preview = document.createElement("span");
    preview.className = "ve-font-preview"; preview.dataset.for = input.id; preview.textContent = "Aa אב";
    input.after(preview);
    input.addEventListener("input", () => _veSyncFontPreview(input));
    input.addEventListener("focus", _veLoadSystemFonts, {once: true});
    _veSyncFontPreview(input);
  }
  for (const input of root.querySelectorAll("input.ve-time")) {
    const hint = document.createElement("span");
    hint.className = "ve-time-hint"; hint.dataset.for = input.id;
    input.after(hint);
    input.addEventListener("input", () => { _veSyncTimeHint(input); if (input.id.startsWith("veTrim")) _veRenderTrimSlider(); });
  }
  for (const range of root.querySelectorAll('input[type="range"]')) {
    if (!range.id || range.closest(".ve-trim-slider")) continue;
    const number = document.createElement("input");
    number.type = "number"; number.className = "ve-range-number"; number.dataset.for = range.id;
    const percent = range.dataset.veValueFormat === "percent";
    number.min = String(percent ? parseFloat(range.min) * 100 : range.min);
    number.max = String(percent ? parseFloat(range.max) * 100 : range.max);
    number.step = String(percent ? Math.max(1, parseFloat(range.step) * 100) : range.step);
    number.setAttribute("aria-label", "ערך מספרי");
    number.addEventListener("change", () => {
      let value = parseFloat(number.value);
      if (!Number.isFinite(value)) { _veSyncRangeNumber(range); return; }
      if (percent) value /= 100;
      range.value = String(Math.max(parseFloat(range.min), Math.min(parseFloat(range.max), value)));
      range.dispatchEvent(new Event("input", {bubbles: true}));
      range.dispatchEvent(new Event("change", {bubbles: true}));
      _veSyncRangeNumber(range);
    });
    range.after(number);
    range.addEventListener("input", () => _veSyncRangeNumber(range));
    _veSyncRangeNumber(range);
  }
  for (const row of root.querySelectorAll(".ve-category-body .ve-row")) {
    if (row.closest("#veFavoritesBox") || row.querySelector(".ve-info-btn")) continue;
    const titled = row.querySelector("label[title]");
    if (!titled) continue;
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "ve-info-btn"; btn.textContent = "ⓘ";
    btn.setAttribute("aria-label", "הסבר על ההגדרה");
    btn.setAttribute("aria-expanded", "false");
    btn.onclick = () => _veToggleInfo(row, btn, _veRowHelpText(row, titled.getAttribute("title")));
    titled.after(btn);
  }
  const trimDurationRow = document.getElementById("veTrimDuration").closest(".ve-row");
  const slider = document.createElement("div");
  slider.id = "veTrimSliderBox"; slider.className = "ve-trim-slider"; slider.hidden = true;
  trimDurationRow.after(slider);
  _veRenderRangesEditor(true);
}

// אחרי טעינת פרופיל/undo/איפוס - הערכים השתנו בלי אירועי input, מסנכרנים הכל.
function _veSyncEnhancedInputs() {
  const root = document.getElementById("veCategories");
  for (const input of root.querySelectorAll("input[data-ve-color]")) _veSyncColorSwatch(input);
  for (const input of root.querySelectorAll("input[data-ve-font]")) _veSyncFontPreview(input);
  for (const input of root.querySelectorAll("input.ve-time")) _veSyncTimeHint(input);
  for (const input of root.querySelectorAll("input[data-ve-browse]")) _veScheduleVePathCheck(input);
  for (const range of root.querySelectorAll('input[type="range"]')) _veSyncRangeNumber(range);
  _veRenderRangesEditor();
  _veRenderTrimSlider();
  if (typeof _veSyncRegionField === "function") _veSyncRegionField();
}

// item: בורר גופנים - רשימת הגופנים נטענת פעם אחת, רק כשעורך-העל נפתח בפועל.
document.body.insertAdjacentHTML("beforeend", '<datalist id="veSystemFontsList"></datalist>');

