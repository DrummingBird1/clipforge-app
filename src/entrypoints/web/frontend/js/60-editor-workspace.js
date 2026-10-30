// ============================================================================
// גל 12 - מודל הנתונים v2: "מתכון" (לכל הקבצים) מול "עריכת קליפ" (לקובץ אחד),
// יעדים (ריצה = מתכון × יעדים), ערכות מותג מקושרות, ופרויקט לכל תיקייה עם
// שמירה אוטומטית. מקור-האמת של המודל בצד השרת: utils/editor_model.py.
// ============================================================================

let _veSchema = null;
async function _veLoadSchema() {
  if (_veSchema) return _veSchema;
  try { _veSchema = await (await fetch("/api/video_editor/schema")).json(); }
  catch (e) { _veSchema = {targets: {}, brand_fields: [], fields: {}}; }
  return _veSchema;
}

// --- יעדים ---
VE_GENERIC_FIELDS.targets = {id: "veTargets", kind: "json", label: "יעדים", onApply: () => _veRenderTargetChips()};
VE_GENERIC_FIELDS.brand_kit = {id: "veBrandKit", kind: "str", label: "מיתוג"};

function _veTargets() {
  try { const value = JSON.parse(_veEl("veTargets").value || "[]"); return Array.isArray(value) ? value : []; }
  catch (e) { return []; }
}

function _veSetTargets(list) {
  _veSetFieldValue(_veEl("veTargets"), JSON.stringify(list));
  _veRenderTargetChips();
}

// גל 58: הנפוצים בשורה אחת, השאר מאחורי "➕ עוד יעדים" (יעד שנבחר נשאר גלוי גם כשהם מקופלים)
const VE_MAIN_TARGETS = ["youtube", "shorts", "tiktok", "reels"];

function toggleVeMoreTargets() {
  _veSavePref("veMoreTargets", !_veLoadPref("veMoreTargets", false));
  _veRenderTargetChips();
}

// השבבים באזור "פלט" ובצעד 2 של המצב הפשוט (גל 30) - אותו מצב
async function _veRenderTargetChips() {
  const schema = await _veLoadSchema();
  const active = _veTargets();
  const more = _veLoadPref("veMoreTargets", false);
  const extra = Object.keys(schema.targets || {}).filter(id => !VE_MAIN_TARGETS.includes(id));
  for (const box of [_veEl("veTargetChips"), _veEl("veStepTargets")]) {
    box.innerHTML = "";
    for (const [id, target] of Object.entries(schema.targets || {})) {
      if (!more && !VE_MAIN_TARGETS.includes(id) && !active.includes(id)) continue;
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.target = id;
      button.textContent = `${target.icon} ${target.label}`;
      button.setAttribute("aria-pressed", String(active.includes(id)));
      button.onclick = () => {
        const current = _veTargets();
        _veSetTargets(current.includes(id) ? current.filter(x => x !== id) : [...current, id]);
      };
      box.appendChild(button);
    }
    const folded = extra.filter(id => !active.includes(id)).length;
    if (more || folded) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "ve-more-targets";
      toggle.textContent = more ? "➖ פחות יעדים" : `➕ עוד יעדים (${folded})`;
      toggle.setAttribute("aria-expanded", String(more));
      toggle.onclick = toggleVeMoreTargets;
      box.appendChild(toggle);
    }
  }
  _veSyncTargetsUi();
}

function _veSyncTargetsUi() {
  const active = _veTargets();
  const area = document.querySelector("#veCategories > details[data-cat=output]");
  if (area) area.classList.toggle("ve-targets-active", active.length > 0);
  const note = _veEl("veTargetsNote");
  note.hidden = !active.length;
  note.textContent = active.length
    ? `▶ ריצה לכל יעד (${active.length}) - הפורמט והאיכות לפי היעד, וכל יעד לתיקיית פלט משלו`
    : "";
  const schema = _veSchema;
  if (schema && active.length) {
    const firstWithZone = active.map(id => schema.targets[id]).find(t => t && t.safe_zone);
    const select = _veEl("veSafeZones");
    if (firstWithZone && select.value !== firstWithZone.safe_zone) { select.value = firstWithZone.safe_zone; applyVeSafeZones(); }
  }
  const previewTarget = _veEl("vePreviewTarget");
  if (previewTarget && schema) {
    const current = previewTarget.value;
    previewTarget.innerHTML = "";
    for (const id of active) {
      const option = document.createElement("option");
      option.value = id; option.textContent = `${schema.targets[id].icon} ${schema.targets[id].label}`;
      previewTarget.appendChild(option);
    }
    if (active.includes(current)) previewTarget.value = current;
    _veEl("vePreviewTargetWrap").hidden = !active.length;
  }
  _veSyncRunMode();
}

const _veSyncRunModeBeforeW12 = _veSyncRunMode;
_veSyncRunMode = function () {
  _veSyncRunModeBeforeW12();
  const count = _veTargets().length;
  const button = _veEl("veStickyRunBtn");
  if (count > 1 && button.textContent === VE_RUN_MODE_LABELS.normal) button.textContent = `▶ הרץ ל-${count} יעדים`;
};

// תצוגה מקדימה / בדיקה / הערכה לפי יעד מסוים (ברירת מחדל: הראשון)
const _vePreviewRequestBodyBeforeW12 = _vePreviewRequestBody;
_vePreviewRequestBody = function (extra) {
  const select = _veEl("vePreviewTarget");
  const target = select && !select.closest("[hidden]") ? select.value : "";
  return _vePreviewRequestBodyBeforeW12({...(extra || {}), preview_target: target || null});
};

// --- עריכת קליפ ---
// גל 30: מצב אחד לעריכת קליפ. בוחרים קליפ (✏️ בשורת התור או "✏️ רק הקליפ הזה" בנגן), מופיע
// באנר "עורך את clip_3 בלבד", והשדות מציגים את הערכים של הקליפ הזה: כל שינוי בזמן, בלוגו
// ובשכבות נשמר רק לו (סימון ✏️ ליד השדה, לחיצה עליו מחזירה לערך של כל הקבצים), ושאר
// ההגדרות נעולות - הן חלות על כל הקבצים. קודם היו לזה ארבעה מנגנונים: היקף זמן (מתכון/קליפ),
// דריסות ✏️ בשורת התור, בורר "קובץ" בכל שכבה ודריסה משותפת לשורות מסומנות.
let _veClipEdits = {};        // שם-קובץ -> רק הקבוצות שנדרסו (ערכי טקסט כמו בשדות) [+ reset_time]
let _veTimeScope = "recipe";  // "recipe" = כל הקבצים, "clip" = מצב עריכת קליפ (של _veClipScopeFile)
let _veRecipeTime = null;     // הערכים של כל הקבצים בשדות-לקליפ, בזמן שהשדות מציגים קליפ
let _veClipScopeFile = null;
let _veScopeLoading = false;
// מה אפשר לשנות לקליפ אחד - הרנדרר מקבל את זה כדריסה פר-קובץ. כל קבוצה נדרסת שלמה.
const VE_CLIP_GROUPS = {
  time: {label: "חיתוך וטווחים", fields: {trim_start: "veTrimStart", trim_duration: "veTrimDuration", remove_ranges: "veRemoveRanges"}},
  logo_file: {label: "קובץ הלוגו", fields: {watermark_path: "veWatermarkPath"}},
  logo_place: {label: "מיקום הלוגו", fields: {watermark_position: "veWatermarkPosition", watermark_x: "veWatermarkX", watermark_y: "veWatermarkY"}},
  logo_scale: {label: "גודל הלוגו", fields: {watermark_scale: "veWatermarkScale"}},
  logo_opacity: {label: "שקיפות הלוגו", fields: {watermark_opacity: "veWatermarkOpacity"}},
};
const VE_CLIP_TIME_FIELDS = VE_CLIP_GROUPS.time.fields;
const VE_CLIP_FIELD_GROUP = {};  // מזהה שדה -> קבוצה
for (const [group, spec] of Object.entries(VE_CLIP_GROUPS)) for (const id of Object.values(spec.fields)) VE_CLIP_FIELD_GROUP[id] = group;
// ערכי כל הקבצים בזמן מצב קליפ (אחרת null) - למועדפים האוטומטיים
function _veRecipeTimeValues() { return _veTimeScope === "clip" ? _veRecipeTime : null; }

const _veClipGroupKeys = (group) => Object.keys(VE_CLIP_GROUPS[group].fields);
const _veClipHasGroup = (edit, group) => !!edit && _veClipGroupKeys(group).some(key => key in edit);
function _veParseRangesText(text) {
  try { const value = JSON.parse(text || "[]"); return Array.isArray(value) ? value : []; } catch (e) { return []; }
}
const _veSameFieldValue = (a, b) => {
  const x = String(a ?? "").trim(), y = String(b ?? "").trim();
  return x === y || (x !== "" && y !== "" && !isNaN(x) && !isNaN(y) && Number(x) === Number(y));
};

function _veClipGroupEqual(group, a, b) {
  if (group === "time") {
    const norm = (v) => JSON.stringify([_veParseTimeText(v.trim_start) || 0, _veParseTimeText(v.trim_duration) || 0, _veCanonicalJson(_veParseRangesText(v.remove_ranges))]);
    return norm(a) === norm(b);
  }
  return _veClipGroupKeys(group).every(key => _veSameFieldValue(a[key], b[key]));
}

function _veClipTimeIsEmpty(values) {
  return !(_veParseTimeText(values.trim_start) || 0) && !String(values.trim_duration || "").trim() && !_veParseRangesText(values.remove_ranges).length;
}

function _veReadClipFields(groups) {
  const out = {};
  for (const group of groups || Object.keys(VE_CLIP_GROUPS)) for (const [key, id] of Object.entries(VE_CLIP_GROUPS[group].fields)) out[key] = _veEl(id).value;
  return out;
}

// כתיבה לשדות עם אירועים (התצוגות מתעדכנות) - בלי שזה ייחשב שינוי של הקליפ. מיקום הלוגו
// לפני x/y: בחירת מיקום מנקה את מרכז הגרירה.
function _veWriteClipFields(values) {
  _veScopeLoading = true;
  try {
    for (const spec of Object.values(VE_CLIP_GROUPS)) {
      for (const [key, id] of Object.entries(spec.fields)) {
        if (!(key in values) || _veEl(id).value === String(values[key] ?? "")) continue;
        _veSetFieldValue(_veEl(id), values[key] ?? "");
      }
    }
    if (typeof _veRenderRangesEditor === "function") _veRenderRangesEditor(true);
  } finally { _veScopeLoading = false; }
}

// בלי אירועים - רק כדי לאסוף את ההגדרות של כל הקבצים
function _veSetRawClipFields(values) {
  for (const spec of Object.values(VE_CLIP_GROUPS)) for (const [key, id] of Object.entries(spec.fields)) if (key in values) _veEl(id).value = values[key] ?? "";
}

function _veClipLayersFor(name) {
  return _veLayersValue().filter(layer => layer.clip === name);
}
function _veClipGroupsOf(name) {
  const edit = _veClipEdits[name];
  return Object.keys(VE_CLIP_GROUPS).filter(group => _veClipHasGroup(edit, group));
}
function _veClipChangeCount(name) {
  return _veClipGroupsOf(name).length + _veClipLayersFor(name).length;
}

// פרויקטים מלפני גל 30 שמרו תמיד את שלושת שדות הזמן לכל קליפ שנגעו בו, וריקים = "בלי עריכה"
function _veNormalizeClipEdits(edits) {
  const out = {};
  for (const [name, edit] of Object.entries(edits && typeof edits === "object" ? edits : {})) {
    if (!edit || typeof edit !== "object") continue;
    const copy = {...edit};
    if (_veClipHasGroup(copy, "time") && !copy.reset_time && _veClipTimeIsEmpty(copy)) for (const key of _veClipGroupKeys("time")) delete copy[key];
    if (!_veClipHasGroup(copy, "time")) delete copy.reset_time;
    if (Object.keys(copy).length) out[name] = copy;
  }
  return out;
}

// מה שנשלח לשרת: ערכים מספריים, רק מה שנדרס (שכבות-קליפ נשלחות עם השכבות עצמן - layer.clip)
function _veCompactClipEdits() {
  const out = {};
  for (const [name, edit] of Object.entries(_veClipEdits)) {
    const compact = {};
    if (_veClipHasGroup(edit, "time")) {
      const duration = _veParseTimeText(edit.trim_duration);
      Object.assign(compact, {trim_start: _veParseTimeText(edit.trim_start) || 0, trim_duration: duration && duration > 0 ? duration : null,
        remove_ranges: _veParseRangesText(edit.remove_ranges)});
      if (edit.reset_time) compact.reset_time = true;
    }
    if (_veClipHasGroup(edit, "logo_file")) {
      if (String(edit.watermark_path || "").trim()) compact.watermark_path = String(edit.watermark_path).trim();
      else compact.watermark_opacity = 0;  // "בלי לוגו בקליפ הזה" כשלכל הקבצים יש לוגו
    }
    if (_veClipHasGroup(edit, "logo_place")) {
      compact.watermark_position = edit.watermark_position;
      if (String(edit.watermark_x ?? "") !== "" && String(edit.watermark_y ?? "") !== "") {
        compact.watermark_x = parseFloat(edit.watermark_x);
        compact.watermark_y = parseFloat(edit.watermark_y);
      }
    }
    if (_veClipHasGroup(edit, "logo_scale")) compact.watermark_scale = (parseFloat(edit.watermark_scale) || 15) / 100;
    if (_veClipHasGroup(edit, "logo_opacity") && !("watermark_opacity" in compact)) {
      const opacity = parseFloat(edit.watermark_opacity);
      compact.watermark_opacity = Number.isFinite(opacity) ? opacity : 1;
    }
    if (Object.keys(compact).length) out[name] = compact;
  }
  return out;
}

function enterVeClipMode(file) {
  file = file || _veEl("vePreviewFile").value;
  if (!file) { uiToast("בחר קודם תיקייה וקובץ בתצוגה המקדימה", "warn"); return; }
  if (_veTimeScope !== "clip") {
    _veRecipeTime = _veReadClipFields();
    _veTimeScope = "clip";
  }
  _veClipScopeFile = file;
  const select = _veEl("vePreviewFile");
  if (![...select.options].some(option => option.value === file)) _vePopulatePreviewFiles();  // התור נטען, הבורר עוד לא
  if (select.value !== file && [...select.options].some(option => option.value === file)) {
    select.value = file;
    select.dispatchEvent(new Event("change", {bubbles: true}));
  }
  _veShowClipValues(file);
  _veSyncClipScopeUi();
  _veScheduleTrimReference();
}

function exitVeClipMode() {
  if (_veTimeScope !== "clip") return;
  const recipe = _veRecipeTime || {};
  _veTimeScope = "recipe";
  _veClipScopeFile = null;
  _veRecipeTime = null;
  _veWriteClipFields(recipe);
  _veSyncClipScopeUi();
  _veScheduleTrimReference();
}

function toggleVeClipMode() {
  if (_veTimeScope === "clip") exitVeClipMode(); else enterVeClipMode();
}

// גל 12 (תאימות): היקף הזמן הישן = מצב הקליפ
function setVeTimeScope(scope) {
  if (scope === "clip") enterVeClipMode(); else exitVeClipMode();
}

// השדות מציגים את הקליפ: הערך שלו בקבוצות שנדרסו, ושל כל הקבצים בשאר
function _veShowClipValues(file) {
  const edit = _veClipEdits[file] || {};
  const values = {...(_veRecipeTime || {})};
  for (const group of _veClipGroupsOf(file)) for (const key of _veClipGroupKeys(group)) values[key] = edit[key] ?? "";
  _veWriteClipFields(values);
}

function _veRecordClipGroup(group) {
  const file = _veClipScopeFile;
  const values = _veReadClipFields([group]);
  const edit = {...(_veClipEdits[file] || {})};
  if (_veClipGroupEqual(group, values, _veRecipeTime || {})) {
    for (const key of _veClipGroupKeys(group)) delete edit[key];
    if (group === "time") delete edit.reset_time;
  } else {
    Object.assign(edit, values);
    if (group === "time") { if (_veClipTimeIsEmpty(values)) edit.reset_time = true; else delete edit.reset_time; }
  }
  if (Object.keys(edit).length) _veClipEdits[file] = edit; else delete _veClipEdits[file];
  _veSyncClipScopeUi();
  _veScheduleProjectSave();
}

// הבועה (לא capture): ה-onchange של השדה רץ קודם - בחירת מיקום לוגו מנקה את x/y לפני שנקרא
document.addEventListener("input", (e) => _veOnClipFieldEdited(e));
document.addEventListener("change", (e) => _veOnClipFieldEdited(e));
function _veOnClipFieldEdited(e) {
  if (_veTimeScope !== "clip" || _veScopeLoading || !e.target || !e.target.id) return;
  const group = VE_CLIP_FIELD_GROUP[e.target.id];
  if (group) _veRecordClipGroup(group);
}

function revertVeClipGroup(group) {
  if (_veTimeScope !== "clip" || !VE_CLIP_GROUPS[group]) return;
  const file = _veClipScopeFile;
  const edit = {...(_veClipEdits[file] || {})};
  for (const key of _veClipGroupKeys(group)) delete edit[key];
  if (group === "time") delete edit.reset_time;
  if (Object.keys(edit).length) _veClipEdits[file] = edit; else delete _veClipEdits[file];
  _veWriteClipFields(Object.fromEntries(_veClipGroupKeys(group).map(key => [key, (_veRecipeTime || {})[key] ?? ""])));
  _veSyncClipScopeUi();
  _veScheduleProjectSave();
}

async function revertVeClipEdits() {
  if (_veTimeScope !== "clip") return;
  const file = _veClipScopeFile;
  const layerCount = _veClipLayersFor(file).length;
  if (layerCount && !await veConfirm(`להחזיר את "${file}" להיות כמו כל הקבצים?\n${layerCount} שכבות שהוספת רק לו יימחקו.`, {okLabel: "↩ כמו כל הקבצים"})) return;
  delete _veClipEdits[file];
  if (layerCount) {
    _veWriteLayers(_veLayersValue().filter(layer => layer.clip !== file));
    _veRenderLayersEditor(true);
  }
  _veShowClipValues(file);
  _veSyncClipScopeUi();
  _veScheduleProjectSave();
}

// השינויים של הקליפ הופכים להגדרות של כל הקבצים (קבצים עם עריכה משלהם שומרים אותה)
async function promoteVeClipEdits() {
  if (_veTimeScope !== "clip") return;
  const file = _veClipScopeFile;
  const count = _veClipChangeCount(file);
  if (!count) return;
  if (!await veConfirm(`להחיל את ${count} השינויים של "${file}" על כל הקבצים?\nקבצים שיש להם עריכה משלהם שומרים אותה.`, {okLabel: "📋 החל על כל הקבצים"})) return;
  const edit = _veClipEdits[file] || {};
  for (const group of _veClipGroupsOf(file)) for (const key of _veClipGroupKeys(group)) _veRecipeTime[key] = edit[key] ?? "";
  delete _veClipEdits[file];
  const layers = _veLayersValue();
  if (layers.some(layer => layer.clip === file)) {
    for (const layer of layers) if (layer.clip === file) delete layer.clip;
    _veWriteLayers(layers);
    _veRenderLayersEditor(true);
  }
  _veSyncClipScopeUi();
  _veRefreshAllDerivedUi();
  updateUnsavedIndicator();
  _veScheduleProjectSave();
}

// גל 30: במצב קליפ - הכל נעול חוץ ממה שאפשר לשנות לקליפ אחד (זמן, לוגו ושכבות של הקליפ)
const VE_CLIP_LOCK_SELECTOR = "#veCategories .ve-row, #veCategories .ve-wheels, #veCategories .ve-curves, #veCategories .ve-cat-reset, #veCategories [data-clip-lock]";
function _veClipRowAllowed(el) {
  if (el.matches("[data-clip-lock], .ve-cat-reset, .ve-wheels, .ve-curves")) return false;
  if (el.hasAttribute("data-clip-ok") || el.closest("#veLayersRows, #veLayersList, #veRangesEditor")) return true;
  return [...el.querySelectorAll("input, select, textarea")].some(input => VE_CLIP_FIELD_GROUP[input.id]);
}

function _veApplyClipLocks() {
  const on = _veTimeScope === "clip";
  for (const el of document.querySelectorAll(".ve-clip-locked")) { el.classList.remove("ve-clip-locked"); el.inert = false; }
  if (!on) return;
  for (const el of document.querySelectorAll(VE_CLIP_LOCK_SELECTOR)) {
    if (_veClipRowAllowed(el)) continue;
    el.classList.add("ve-clip-locked");
    el.inert = true;
  }
  for (const row of document.querySelectorAll("#veLayersRows .ve-layer-row, #veLayersList .ve-ll-row")) {
    const layer = row.dataset.kind === "layer" || row.classList.contains("ve-layer-row") ? _veLayersValue()[parseInt(row.dataset.index, 10)] : null;
    const allowed = row.dataset.kind === "logo" || (layer && layer.clip === _veClipScopeFile);
    if (allowed) continue;
    row.classList.add("ve-clip-locked");
    row.inert = true;
  }
}

// שכבה שחלה על כל הקבצים לא זזה ולא משתנה בזמן עריכת קליפ
function _veClipModeLocksLayer(layer) {
  return _veTimeScope === "clip" && !!layer && layer.clip !== _veClipScopeFile;
}
// שכבה חדשה במצב קליפ שייכת לקליפ
function _veClipLayerTag() {
  return _veTimeScope === "clip" && _veClipScopeFile ? {clip: _veClipScopeFile} : {};
}
// פעולה שחלה על כל הקבצים (PiP, פס-קול, פתיח/סיום) - לא במצב קליפ
function _veClipModeRefuses(what) {
  if (_veTimeScope !== "clip") return false;
  uiToast(`${what} - חל על כל הקבצים, סיים קודם את עריכת הקליפ`, "warn");
  return true;
}

// ✏️ ליד שדה שנדרס לקליפ - לחיצה מחזירה אותו לערך של כל הקבצים
function _veMarkClipRows() {
  for (const mark of document.querySelectorAll(".ve-clip-mark")) mark.remove();
  for (const row of document.querySelectorAll(".ve-row-clip-override")) row.classList.remove("ve-row-clip-override");
  if (_veTimeScope !== "clip") return;
  for (const group of _veClipGroupsOf(_veClipScopeFile)) {
    const hosts = new Set();
    for (const id of Object.values(VE_CLIP_GROUPS[group].fields)) {
      const el = _veEl(id);
      const host = el && (el.type === "hidden" || el.hidden ? null : el.closest(".ve-row"));
      if (host) hosts.add(host);
    }
    if (group === "time") hosts.add(document.querySelector("[data-subcat=cuts] > .ve-subcat-title"));
    if (group === "logo_place") hosts.add(_veEl("veWatermarkPosition").closest(".ve-row"));
    for (const host of hosts) {
      if (!host) continue;
      host.classList.add("ve-row-clip-override");
      if (host.querySelector(":scope > .ve-clip-mark")) continue;
      const mark = document.createElement("button");
      mark.type = "button";
      mark.className = "ve-clip-mark";
      mark.textContent = "✏️";
      mark.title = `${VE_CLIP_GROUPS[group].label} - רק ל-${_veClipScopeFile}. לחיצה מחזירה לערך של כל הקבצים`;
      mark.setAttribute("aria-label", `${VE_CLIP_GROUPS[group].label} - החזר לערך של כל הקבצים`);
      mark.onclick = (e) => { e.preventDefault(); e.stopPropagation(); revertVeClipGroup(group); };
      host.appendChild(mark);
    }
  }
}

function _veSyncClipScopeUi() {
  const clip = _veTimeScope === "clip";
  _veEl("videoEditorOptions").classList.toggle("ve-clip-mode", clip);
  _veEl("veClipBanner").hidden = !clip;
  _veEl("veClipModeBtn").setAttribute("aria-pressed", String(clip));
  if (clip) {
    const count = _veClipChangeCount(_veClipScopeFile);
    _veEl("veClipBannerName").textContent = _veClipScopeFile;
    _veEl("veClipBannerCount").textContent = count ? ` · ${count} שינויים` : " · עוד בלי שינויים";
    _veEl("veClipRevertBtn").disabled = !count;
    _veEl("veClipPromoteBtn").disabled = !count;
  }
  _veMarkClipRows();
  _veApplyClipLocks();
  _veDecorateQueueClipBadges();
  if (typeof _veRenderDragHandles === "function" && !_veEl("vePreviewStageWrap").hidden) _veRenderDragHandles();
}

// שכבה נוספה/נמחקה/עברה בין "כל הקבצים" לקליפ - הספירה בבאנר ובתור והנעילות מתעדכנות
_veEl("veLayers").addEventListener("change", () => _veSyncClipScopeUi());

_veEl("vePreviewFile").addEventListener("change", () => {
  const file = _veEl("vePreviewFile").value;
  if (_veTimeScope === "clip" && file && file !== _veClipScopeFile) enterVeClipMode(file);
  else _veSyncClipScopeUi();
});

const _collectRunOptionsBeforeW12 = _collectRunOptions;
_collectRunOptions = function () {
  let options;
  if (_veTimeScope === "clip" && _veRecipeTime) {
    // השדות מציגים את הקליפ - אוספים את ההגדרות של כל הקבצים
    const shown = _veReadClipFields();
    _veSetRawClipFields(_veRecipeTime);
    try { options = _collectRunOptionsBeforeW12(); } finally { _veSetRawClipFields(shown); }
  } else {
    options = _collectRunOptionsBeforeW12();
  }
  if (!options || !("trim_start" in options)) return options;
  const edits = _veCompactClipEdits();
  if (Object.keys(edits).length) options.clip_edits = edits;
  return options;
};

// עריכות-קליפ שייכות לפרויקט, לא לסגנון - לא מסמנות אותו כ"שונה"
const _veComparableOptionsJsonBeforeW12 = _veComparableOptionsJson;
_veComparableOptionsJson = function () {
  const saved = _veClipEdits;
  _veClipEdits = {};
  try { return _veComparableOptionsJsonBeforeW12(); } finally { _veClipEdits = saved; }
};

// ✏️ N בשורות התור לקבצים עם עריכה משלהם
function _veDecorateQueueClipBadges() {
  for (const row of document.querySelectorAll("#veQueueList .ve-queue-row")) {
    const item = (_veQueueState || [])[parseInt(row.dataset.index, 10)];
    const count = item ? _veClipChangeCount(item.name) : 0;
    let badge = row.querySelector(".ve-clip-badge");
    if (count && !badge) {
      badge = document.createElement("span");
      badge.className = "ve-clip-badge";
      row.querySelector(".ve-queue-main").after(badge);
    } else if (!count && badge) badge.remove();
    if (badge) {
      badge.textContent = `✏️ ${count}`;
      badge.title = `לקובץ הזה ${count} שינויים משלו (זמן, לוגו או שכבות)`;
    }
    const active = _veTimeScope === "clip" && item && item.name === _veClipScopeFile;
    row.classList.toggle("ve-queue-clip-active", !!active);
    const editBtn = row.querySelector(".ve-queue-clip-btn");
    if (editBtn) editBtn.setAttribute("aria-pressed", String(!!active));
  }
}
const _renderVeQueueBeforeW12 = _renderVeQueue;
let _veQueueSavedSignature = "";
_renderVeQueue = function (...args) {
  const result = _renderVeQueueBeforeW12(...args);
  _veDecorateQueueClipBadges();
  // רק שינוי אמיתי בסדר/בבחירה נשמר בפרויקט (לא כל עדכון מטא-דאטה של שורה)
  const signature = (_veQueueState || []).map(f => (f.selected ? "+" : "-") + f.name).join("|");
  if (signature !== _veQueueSavedSignature) { _veQueueSavedSignature = signature; _veScheduleProjectSave(); }
  return result;
};

// שכבה של קליפ אחד: בשורת השכבה "📋 כל הקבצים" / שם קובץ (במצב קליפ שכבה חדשה שייכת לקליפ)
const _veLayerRowElBeforeW12 = _veLayerRowEl;
_veLayerRowEl = function (layer, index, total) {
  const row = _veLayerRowElBeforeW12(layer, index, total);
  const names = (_veQueueState || []).map(f => f.name);
  if (layer.clip && !names.includes(layer.clip)) names.unshift(layer.clip);
  const options = {"": "📋 כל הקבצים"};
  for (const name of names) options[name] = "🎬 " + name;
  const select = _veLayerSelect(options, layer.clip || "", "על אילו קבצים");
  select.classList.add("ve-layer-clip");
  select.addEventListener("change", () => {
    const layers = _veLayersValue();
    if (!layers[index]) return;
    if (select.value) layers[index].clip = select.value; else delete layers[index].clip;
    _veWriteLayers(layers);
    _veSyncClipScopeUi();
  });
  const position = row.querySelector("select[data-field=position]");
  (position || row.lastChild).after(select);
  if (_veClipModeLocksLayer(layer)) { row.classList.add("ve-clip-locked"); row.inert = true; }
  return row;
};
const _veLayerFromRowBeforeW12 = _veLayerFromRow;
_veLayerFromRow = function (row, previous) {
  const layer = _veLayerFromRowBeforeW12(row, previous);
  const select = row.querySelector("select.ve-layer-clip");
  if (select) { if (select.value) layer.clip = select.value; else delete layer.clip; }
  return layer;
};

// --- ערכות מותג ---
let _veBrandKits = {};

async function loadVeBrandKits() {
  try { _veBrandKits = (await (await fetch("/api/brand_kits")).json()).kits || {}; } catch (e) { _veBrandKits = {}; }
  _veRenderBrandKitSelect();
}

function _veRenderBrandKitSelect(forceValue) {
  const select = _veEl("veBrandKit");
  const current = forceValue !== undefined ? forceValue : select.value;
  select.innerHTML = '<option value="">— בלי מיתוג —</option>';
  const names = Object.keys(_veBrandKits).sort((a, b) => a.localeCompare(b, "he"));
  if (current && !names.includes(current)) names.push(current);
  for (const name of names) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = _veBrandKits[name] ? "🏷️ " + name : `⚠️ ${name} (לא נמצאה)`;  // גל 34: האיקון של מיתוג
    select.appendChild(option);
  }
  select.value = current || "";
  _veSyncBrandUi();
}

function _veBrandFieldNames() { return (_veSchema && _veSchema.brand_fields) || []; }

function _veCurrentBrandValues() {
  const options = _collectRunOptions();
  return Object.fromEntries(_veBrandFieldNames().filter(key => key in options).map(key => [key, options[key]]));
}

function _veBrandDiffCount(kitName) {
  const kit = _veBrandKits[kitName];
  if (!kit) return 0;
  const current = _veCurrentBrandValues();
  return Object.entries(kit.fields || {}).filter(([key, value]) => JSON.stringify(current[key] ?? null) !== JSON.stringify(value ?? null)).length;
}

function _veSyncBrandUi() {
  const name = _veEl("veBrandKit").value;
  const kit = _veBrandKits[name];
  _veEl("veBrandUpdateBtn").hidden = !kit;
  _veEl("veBrandDeleteBtn").hidden = !kit;
  const status = _veEl("veBrandStatus");
  if (!name) status.textContent = "";
  else if (!kit) status.textContent = "⚠️ המיתוג לא קיים - הסגנון ירוץ עם השדות שלו";
  else {
    const diff = _veBrandDiffCount(name);
    status.textContent = diff ? `🔗 מקושר · ✏️ ${diff} שדות שונים מהמיתוג (בריצה המיתוג גובר)` : "🔗 מקושר - עדכון המיתוג יחול על כל סגנון שמשתמש בו";
  }
  const templates = (kit && kit.templates) || [];
  _veEl("veBrandTemplatesRow").hidden = !kit;
  const templateSelect = _veEl("veBrandTemplate");
  templateSelect.innerHTML = "";
  for (const [i, tpl] of templates.entries()) {
    const option = document.createElement("option");
    option.value = String(i); option.textContent = tpl.name;
    templateSelect.appendChild(option);
  }
  templateSelect.disabled = !templates.length;
}

async function onVeBrandKitSelected() {
  const name = _veEl("veBrandKit").value;
  const kit = _veBrandKits[name];
  if (kit) {
    const fields = {..._collectRunOptions(), ...(kit.fields || {}), brand_kit: name};
    _applyVideoEditorFields(fields);
  }
  _veSetFieldValue(_veEl("veBrandKit"), name);
  _veSyncBrandUi();
}

async function _veSaveKit(name, fields, templates) {
  const res = await fetch("/api/brand_kits", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name, fields, templates})});
  const data = await res.json();
  if (!res.ok) { _veEl("veBrandStatus").textContent = "⚠️ " + (data.error || "השמירה נכשלה"); return false; }
  await loadVeBrandKits();
  return true;
}

async function saveVeBrandKitFromCurrent() {
  const name = ((await vePrompt("שם למיתוג (לוגו, עיצוב כתוביות, צבעים ו-intro/outro מההגדרות הנוכחיות):")) || "").trim();
  if (!name) return;
  if (await _veSaveKit(name, _veCurrentBrandValues(), [])) {
    _veRenderBrandKitSelect(name);
    _veSetFieldValue(_veEl("veBrandKit"), name);
    _veSyncBrandUi();
  }
}

async function updateVeBrandKitFromCurrent() {
  const name = _veEl("veBrandKit").value;
  const kit = _veBrandKits[name];
  if (!kit) return;
  if (!await veConfirm(`לעדכן את המיתוג "${name}" לפי ההגדרות הנוכחיות? כל סגנון שמקושר אליו יקבל את השינוי.`, {okLabel: "🔄 עדכן מיתוג"})) return;
  await _veSaveKit(name, _veCurrentBrandValues(), kit.templates || []);
}

async function deleteVeBrandKit() {
  const name = _veEl("veBrandKit").value;
  if (!_veBrandKits[name] || !await veConfirm(`למחוק את המיתוג "${name}"? סגנונות שמקושרים אליו ימשיכו עם השדות שלהם.`, {okLabel: "🗑️ מחק", danger: true})) return;
  await fetch("/api/brand_kits/" + encodeURIComponent(name), {method: "DELETE"});
  await loadVeBrandKits();
}

function addVeLayerFromTemplate() {
  const kit = _veBrandKits[_veEl("veBrandKit").value];
  const tpl = kit && (kit.templates || [])[parseInt(_veEl("veBrandTemplate").value, 10)];
  if (!tpl) return;
  const layers = _veLayersValue();
  layers.push(JSON.parse(JSON.stringify(tpl.layer)));
  _veWriteLayers(layers);
  _veRenderLayersEditor(true);
}

async function saveVeLastLayerAsTemplate() {
  const name = _veEl("veBrandKit").value;
  const kit = _veBrandKits[name];
  const layers = _veLayersValue();
  if (!kit || !layers.length) { _veEl("veBrandStatus").textContent = "⚠️ צריך מיתוג מקושר ולפחות שכבה אחת."; return; }
  const title = ((await vePrompt("שם לשכבה המוכנה (למשל: כותרת תחתונה):")) || "").trim();
  if (!title) return;
  const layer = {...layers[layers.length - 1]};
  delete layer.clip;
  await _veSaveKit(name, kit.fields || {}, [...(kit.templates || []), {name: title, layer}]);
}

// --- פרויקט: שמירה אוטומטית ושחזור לכל תיקייה ---
let _veProjectTimer = null;
let _veProjectLoadedFor = null;
let _veProjectSaveInfo = {state: "idle"};  // גל 30: לאינדיקטור השמירה - idle / saving / saved / error
let _veProjectSuppress = false;
let _veProjectPendingSince = 0;
// הגדרות הפרויקט כשהן שונות מהטופס ועוד לא הוחלט ("החל" או "השאר את הנוכחיות"): השמירה האוטומטית שומרת אותן
// כמו שהן. קודם עצם הפתיחה של פרויקט דרסה תוך שניות את ההגדרות שלו בהגדרות שבטופס (הרצה מקצה לקצה, 16.10)
let _veProjectPendingRecipe = null;
// עריכה של המשתמש (אירוע אמיתי, לא שדה שהקוד מילא) שעוד לא נשמרה באף פרויקט. בלעדיה פתיחת פרויקט מחילה את ההגדרות
// שלו מיד - קודם כל פתיחה דרשה "החל"; איתה (למשל סגנון שנבחר לפני שנבחרה תיקייה) השורה שואלת, כמו קודם
let _veFormEditSeq = 0;
let _veFormSyncedSeq = 0;
for (const type of ["input", "change", "click"]) {
  document.getElementById("videoEditorOptions").addEventListener(type, (e) => {
    if (!e.isTrusted || e.target.type === "search" || e.target.id === "folderInput") return;
    if (type !== "click" || e.target.closest("[data-target], [data-look]")) _veFormEditSeq++;   // שבבי יעדים ומראה - לחיצה, לא change
  });
}

function _veProjectPayload() {
  const options = _collectRunOptions();
  const recipe = {...options};
  for (const key of ["clip_edits", "only_files", "concat_files", "ve_profile_name", "queue_files"]) delete recipe[key];
  const pending = _veProjectPendingRecipe;
  return {
    folder: state.folder, recipe: pending ? pending.recipe : recipe,
    profile_name: pending ? pending.profile_name : (_currentVeProfileName() || null), targets: _veTargets(),
    clip_edits: _veClipEdits, brand_kit: _veEl("veBrandKit").value || "",
    queue: (_veQueueState || []).length ? {files: _veQueueState.map(f => ({name: f.name, selected: !!f.selected}))} : null,
  };
}

function _veScheduleProjectSave() {
  if (_veProjectSuppress || !state || !state.folder || _veProjectLoadedFor !== state.folder) return;
  if (_veEl("videoEditorOptions").hidden) return;
  // debounce עם המתנה מקסימלית: שינויים רצופים (למשל התור שמתעדכן בזמן ה-probe) לא דוחים את השמירה לנצח
  const now = Date.now();
  if (!_veProjectPendingSince) _veProjectPendingSince = now;
  clearTimeout(_veProjectTimer);
  _veProjectTimer = setTimeout(() => _veSaveProjectNow(), now - _veProjectPendingSince >= 4000 ? 0 : 1500);
}

async function _veSaveProjectNow() {
  clearTimeout(_veProjectTimer);
  _veProjectPendingSince = 0;
  if (!state.folder || _veProjectLoadedFor !== state.folder) return;
  _veProjectSaveInfo = {..._veProjectSaveInfo, state: "saving"};
  _veRenderSaveState();
  const editSeq = _veFormEditSeq, savesForm = !_veProjectPendingRecipe;
  try {
    const res = await fetch("/api/editor_projects", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(_veProjectPayload())});
    const data = await res.json();
    _veProjectSaveInfo = res.ok ? {state: "saved", at: new Date()} : {state: "error", error: data.error || "שמירת הפרויקט נכשלה"};
    if (res.ok && savesForm) _veFormSyncedSeq = Math.max(_veFormSyncedSeq, editSeq);
  } catch (e) {
    _veProjectSaveInfo = {state: "error", error: "שגיאת רשת - ננסה שוב בשינוי הבא"};
  }
  _veRenderSaveState();
}

// רענון או סגירה בתוך ההמתנה של השמירה האוטומטית: השינוי האחרון נשלח מיד (keepalive ממשיך גם אחרי שהדף נסגר).
// קודם שינוי שנעשה פחות מ-1.5 שנ' לפני רענון אבד (הרצה מקצה לקצה, 16.10)
window.addEventListener("pagehide", () => {
  if (!_veProjectPendingSince || !state.folder || _veProjectLoadedFor !== state.folder) return;
  clearTimeout(_veProjectTimer);
  _veProjectPendingSince = 0;
  fetch("/api/editor_projects", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(_veProjectPayload()), keepalive: true});
});

async function _veLoadProjectForFolder(folder) {
  _veProjectLoadedFor = null;
  _veProjectPendingRecipe = null;
  _veEl("veProjectBanner").hidden = true;
  if (!folder) return;
  const queueMark = veFlow.queueMark();
  let project = null;
  try { project = (await (await fetch("/api/editor_projects/by_folder?folder=" + encodeURIComponent(folder))).json()).project; }
  catch (e) { project = null; }
  if (state.folder !== folder) return;  // המשתמש כבר עבר לתיקייה אחרת
  _veProjectSuppress = true;
  let autoApply = false;
  try {
    if (project) {
      _veClipEdits = _veNormalizeClipEdits(project.clip_edits);
      if (Array.isArray(project.targets) && JSON.stringify(project.targets) !== JSON.stringify(_veTargets())) _veSetTargets(project.targets);
      const differs = project.recipe && _veCanonicalJson(_veRecipeOnly(project.recipe)) !== _veCanonicalJson(_veRecipeOnly(_veProjectPayload().recipe));
      autoApply = !!differs && _veFormEditSeq === _veFormSyncedSeq;   // אין בטופס עבודה שלא נשמרה - ההגדרות של הפרויקט
      const ask = differs && !autoApply;
      const restored = `📂 שוחזרו עריכות הקליפים והיעדים מהפרויקט של התיקייה הזו (נשמר ${_veFormatProjectTime(project.updated_at)}).`;
      _veEl("veProjectBannerText").textContent = restored + (ask ? " ההגדרות שהיו בפרויקט שונות מהנוכחיות - הן נשמרות בו עד שתבחר." : "");
      _veEl("veProjectApplyRecipeBtn").hidden = !ask;
      _veProjectPendingRecipe = ask ? {recipe: project.recipe, profile_name: project.profile_name || null} : null;
      // גל 58: שורה ברוחב מלא רק כשיש מה להחליט (ההגדרות בפרויקט שונות); אחרת הודעה קופצת שנעלמת לבד
      _veEl("veProjectBanner").hidden = !ask;
      if (!ask) uiToast(autoApply ? "📁 הפרויקט נפתח עם ההגדרות שלו" : restored, "ok");
      _veEl("veProjectBanner").dataset.recipe = JSON.stringify(project.recipe || {});
      _veEl("veProjectBanner").dataset.profile = project.profile_name || "";
    } else {
      _veClipEdits = {};
      // סרטון מעורך הגרפים (dataviz_studio/, utils/dataviz_handoff.py) - יש בו מוזיקה, ו"שמירת אודיו" כבויה כברירת מחדל
      if (/[\\/](dataviz_studio|studio_handoff)[\\/]/i.test(folder) && !_veEl("veKeepAudio").checked) {
        _veEl("veKeepAudio").checked = true;
        _veEl("veKeepAudio").dispatchEvent(new Event("change", {bubbles: true}));
        uiToast('🎵 "שמירת אודיו" הופעלה - בסרטון מעורך הגרפים יש מוזיקה', "ok");
      }
    }
    _veProjectSaveInfo = project ? {state: "saved", at: new Date(project.updated_at)} : {state: "idle"};
    _veRenderSaveState();
    _veSyncClipScopeUi();
  } finally {
    _veProjectSuppress = false;
    _veProjectLoadedFor = folder;
  }
  if (autoApply) applyVeProjectRecipe();
  else if (project && !_veProjectPendingRecipe) _veFormSyncedSeq = _veFormEditSeq;   // הטופס כמו הפרויקט
  // תור שנבחר בינתיים (פרופיל עם תור שמור, או סידור ידני) גובר - לא דורסים אותו
  // בסדר של הפרויקט או ברשימת ברירת-המחדל של התיקייה (veFlow, 07-ui-flow.js)
  if (veFlow.queueChosenSince(queueMark, _veQueueDirty)) return;
  if (project && project.queue && Array.isArray(project.queue.files) && project.queue.files.length) veFlow.requestQueueRestore(project.queue.files, "project");
  // חלונית הקבצים קבועה על המסך - התור נטען מיד (עם הסדר השמור בפרויקט, אם יש)
  if (!_veEl("videoEditorOptions").hidden) refreshVeQueue();
}

function _veRecipeOnly(recipe) {
  const out = {...(recipe || {})};
  for (const key of ["batch_overrides", "favorite_fields", "folder", "queue_files", "only_files", "clip_edits"]) delete out[key];
  return out;
}

function _veFormatProjectTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  return isNaN(date) ? iso : date.toLocaleString("he-IL", {day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit"});
}

function applyVeProjectRecipe() {
  const banner = _veEl("veProjectBanner");
  let recipe = {};
  try { recipe = JSON.parse(banner.dataset.recipe || "{}"); } catch (e) { recipe = {}; }
  _veProjectPendingRecipe = null;
  _veFormSyncedSeq = _veFormEditSeq;
  _applyVideoEditorFields(recipe);
  banner.hidden = true;
  _veScheduleProjectSave();
}

// ✕ בשורה: ממשיכים עם ההגדרות שבטופס - מעכשיו הפרויקט נשמר איתן
function keepVeCurrentSettings() {
  _veProjectPendingRecipe = null;
  _veEl("veProjectBanner").hidden = true;
  _veScheduleProjectSave();
}

async function exportVeProject() {
  if (!state.folder) return;
  await _veSaveProjectNow();
  const res = await fetch("/api/editor_projects/export?folder=" + encodeURIComponent(state.folder));
  const data = await res.json();
  if (!res.ok) { alert(data.error || "הייצוא נכשל"); return; }
  const blob = new Blob([JSON.stringify(data, null, 2)], {type: "application/json"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = (data.project && data.project.name ? data.project.name : "project") + ".clipforge.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 2000);
}

async function _veImportProjectFileChosen(event) {
  const file = event.target.files && event.target.files[0];
  event.target.value = "";
  if (!file || !state.folder) { if (!state.folder) alert("בחר קודם את התיקייה שהפרויקט יחול עליה."); return; }
  let data;
  try { data = JSON.parse(await file.text()); } catch (e) { alert("הקובץ לא JSON תקין."); return; }
  const res = await fetch("/api/editor_projects/import", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({data, folder: state.folder})});
  const result = await res.json();
  if (!res.ok) { alert(result.error || "הייבוא נכשל"); return; }
  await _veLoadProjectForFolder(state.folder);
  if (result.project && result.project.recipe) { _veEl("veProjectBanner").dataset.recipe = JSON.stringify(result.project.recipe); applyVeProjectRecipe(); }
}

uiBus.on("ve:folder-changed", (folder) => {
  if (_veTimeScope === "clip") setVeTimeScope("recipe");
  _veLoadProjectForFolder(folder);
});

// כל שינוי בעורך (אותו מסלול כמו רענון ה-UI הנגזר) -> שמירה אוטומטית של הפרויקט
uiBus.on("ve:derived-refresh", () => {
  _veScheduleProjectSave();
  if (_veEl("veBrandKit").value) _veSyncBrandUi();
});

uiBus.on("ve:fields-applied", (fields) => {
  _veRenderBrandKitSelect((fields || {}).brand_kit || "");
  _veRenderTargetChips();
});

function _veInitWave12() {
  _veLoadSchema().then(() => { _veRenderTargetChips(); _veSyncBrandUi(); });
  loadVeBrandKits();
  _veSyncClipScopeUi();
  if (state && state.folder) _veLoadProjectForFolder(state.folder);
}
