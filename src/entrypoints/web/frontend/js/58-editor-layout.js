// ============================================================================
// גל 10 - סידור מחדש של עורך-העל: שדה אחד לכל רעיון (composites), פשוט/מתקדם,
// "רק מה ששיניתי", כרטיסי שכבות, דיאלוגי פרופילים/תמלול. ה-composites הם *תצוגה*
// מעל השדות הקיימים (שיושבים מוסתרים ב-#veLegacyFields): פרופילים, דגלי ה-CLI,
// החוקים וההערכות לא השתנו בכלל - רק איך עורכים אותם.
// ============================================================================

// מפתחות הקטגוריות הישנים -> האזורים החדשים (חוקים/קישורים עמוקים ישנים ממשיכים לעבוד)
// גל 28: "אפקטים וניקוי" הוא אזור משלו (ייצוב/אינטרפולציה = motion שייכים אליו)
const VE_CAT_ALIASES = {format: "output", trim: "time", color: "look", motion: "effects", audio: "sound", captions: "sound", resources: "perf"};
for (const rule of VE_RULES) rule.cats = [...new Set(rule.cats.map(c => VE_CAT_ALIASES[c] || c))];

const _veScrollToCategoryBeforeWave10 = veScrollToCategory;
veScrollToCategory = function (catKey) { return _veScrollToCategoryBeforeWave10(VE_CAT_ALIASES[catKey] || catKey); };

// שדות תלויים שחולקים עכשיו שורה עם השדה-האב (הסתרת השורה הייתה מסתירה גם את האב)
for (const id of ["vePipDuck", "veLoudnormTarget", "veGifWidth", "veMaxConcurrentNvenc"]) delete VE_DEPENDENT_FIELDS[id];

const _veEl = (id) => document.getElementById(id);
const _veSetLegacy = (id, value) => {
  const el = _veEl(id);
  if (!el) return;
  if (el.type === "checkbox") el.checked = !!value; else el.value = value;
};
let _veCompositeWriting = false;

function _veWriteLegacy(changes) {
  _veCompositeWriting = true;
  try {
    for (const [id, value] of Object.entries(changes)) _veSetLegacy(id, value);
    for (const id of Object.keys(changes)) {
      const el = _veEl(id);
      if (!el) continue;
      el.dispatchEvent(new Event("input", {bubbles: true}));
      el.dispatchEvent(new Event("change", {bubbles: true}));
    }
  } finally { _veCompositeWriting = false; }
  _veRefreshAllDerivedUi();
}

const VE_QUALITY_LEVELS = {
  h264: {best: 17, default: 20, balanced: 23, small: 27},
  hevc: {best: 16, default: 19, balanced: 23, small: 27},
  av1: {best: 21, default: 24, balanced: 28, small: 32},
};
const _vePortrait = (format) => format === "9:16" || format === "4:5"
  || (format === "custom" && (parseInt(_veValue("veCustomHeight"), 10) || 0) > (parseInt(_veValue("veCustomWidth"), 10) || 0));

// כל composite: legacy = השדות שהוא עורך; read() -> ערך UI; write(v) -> שינויים ב-legacy
const VE_COMPOSITES = {
  format: {
    legacy: ["veVertical", "veAspect", "veDualOutput"],
    read: () => _veIsChecked("veDualOutput") ? "dual" : (_veValue("veAspect") || (_veIsChecked("veVertical") ? "9:16" : "16:9")),
    write: (v) => v === "dual" ? {veDualOutput: true, veAspect: "", veVertical: false}
      : (v === "16:9" || v === "9:16") ? {veDualOutput: false, veAspect: "", veVertical: v === "9:16"}
      : {veDualOutput: false, veAspect: v, veVertical: _vePortrait(v)},
  },
  fill: {
    legacy: ["veSmartCrop", "veSmartCropFace", "veBlurBackground", "veFit"],
    read: () => _veIsChecked("veBlurBackground") ? "blur" : _veIsChecked("veSmartCrop") ? (_veIsChecked("veSmartCropFace") ? "face" : "smart")
      : _veValue("veFit") === "pad" ? "pad" : _veValue("veFit") === "crop" ? "center" : "auto",
    write: (v) => ({
      veBlurBackground: v === "blur", veSmartCrop: v === "smart" || v === "face", veSmartCropFace: v === "face",
      veFit: v === "pad" ? "pad" : v === "center" ? "crop" : "auto",
    }),
  },
  resolution: {
    legacy: ["vePreserveResolution", "veResolution"],
    read: () => _veIsChecked("vePreserveResolution") ? "source" : (_veValue("veResolution") || "auto"),
    write: (v) => v === "source" ? {vePreserveResolution: true, veResolution: "auto"} : {vePreserveResolution: false, veResolution: v},
  },
  silence: {
    legacy: ["veTrimSilence", "veRemoveMidSilence"],
    read: () => _veIsChecked("veRemoveMidSilence") ? "all" : _veIsChecked("veTrimSilence") ? "edges" : "off",
    write: (v) => ({veTrimSilence: v === "edges", veRemoveMidSilence: v === "all"}),
  },
  speed: {
    legacy: [],
    read: () => (_veParseTimeText(_veValue("veTargetSeconds")) || 0) > 0 ? "timelapse"
      : Math.abs((parseFloat(_veValue("veSpeed")) || 1) - 1) > 0.001 ? "speed" : "normal",
    write: (v) => v === "normal" ? {veSpeed: "1", veTargetSeconds: "0"}
      : v === "speed" ? {veTargetSeconds: "0", veSpeed: Math.abs((parseFloat(_veValue("veSpeed")) || 1) - 1) > 0.001 ? _veValue("veSpeed") : "1.5"}
      : {veSpeed: "1", veTargetSeconds: (_veParseTimeText(_veValue("veTargetSeconds")) || 0) > 0 ? _veValue("veTargetSeconds") : "60"},
  },
  denoise: {
    legacy: ["veDenoise", "veDenoiseLevel"],
    read: () => _veIsChecked("veDenoise") ? (_veValue("veDenoiseLevel") || "medium") : "off",
    write: (v) => v === "off" ? {veDenoise: false} : {veDenoise: true, veDenoiseLevel: v},
  },
  sharpen: {
    legacy: ["veSharpen", "veSharpenLevel"],
    read: () => _veIsChecked("veSharpen") ? (_veValue("veSharpenLevel") || "medium") : "off",
    write: (v) => v === "off" ? {veSharpen: false} : {veSharpen: true, veSharpenLevel: v},
  },
  audio: {
    legacy: ["veKeepAudio"],
    read: () => _veHasText("veReplaceAudioPath") ? "file" : _veIsChecked("veKeepAudio") ? "original" : "none",
    write: (v) => v === "none" ? {veKeepAudio: false, veReplaceAudioPath: ""} : v === "original" ? {veKeepAudio: true, veReplaceAudioPath: ""} : {veKeepAudio: true},
  },
  quality: {
    legacy: [],
    read: () => {
      if (_veHasText("veTargetSizeMb") && parseFloat(_veValue("veTargetSizeMb")) > 0) return "size";
      const codec = _veValue("veCodec") || "h264";
      const raw = codec === "h264" ? _veValue("veCrf") : _veValue("veNvencCq");
      if (raw === "") return "default";
      const level = Object.entries(VE_QUALITY_LEVELS[codec] || {}).find(([, n]) => n === parseInt(raw, 10));
      return level ? level[0] : "manual";
    },
    write: (v) => {
      const codec = _veValue("veCodec") || "h264";
      if (v === "size" || v === "manual") return v === "size" ? {veCrf: "", veNvencCq: ""} : {veTargetSizeMb: ""};
      const number = v === "default" ? "" : String(VE_QUALITY_LEVELS[codec][v]);
      return codec === "h264" ? {veCrf: number, veNvencCq: "", veTargetSizeMb: ""} : {veNvencCq: number, veCrf: "", veTargetSizeMb: ""};
    },
  },
  gpu: {
    legacy: ["veHwaccel", "veHwaccelDecode"],
    read: () => _veIsChecked("veHwaccel") ? "full" : _veIsChecked("veHwaccelDecode") ? "decode" : "off",
    write: (v) => ({veHwaccel: v === "full", veHwaccelDecode: v === "decode"}),
  },
};
const VE_COMPOSITE_CONTROL = {
  fill: "veFillMode", resolution: "veResolutionMode", silence: "veSilenceMode", speed: "veSpeedMode", denoise: "veDenoiseMode",
  sharpen: "veSharpenMode", audio: "veAudioSource", quality: "veQualityMode", gpu: "veGpuMode",
};
// איפה כל composite יושב (לתקצירי-אזור, איפוס-אזור, קפיצה לשדה מתוך אזהרה)
const VE_COMPOSITE_ROW = {
  format: "format", fill: "fill", resolution: "resolution", silence: "silence", speed: "speed", denoise: "cleanup",
  sharpen: "cleanup", audio: "audio", quality: "quality", gpu: "gpu",
};
const _veCompositeRowEl = (name) => document.querySelector(`#veCategories .ve-composite-row[data-composite="${VE_COMPOSITE_ROW[name]}"]`);
// ערך UI שנבחר אבל עוד לא "מתבטא" ב-legacy (למשל "מקובץ אחר" בלי נתיב עדיין) - נשמר עד טעינה חיצונית
const _veCompositePending = {};

function _veRenderComposite(name) {
  const value = _veCompositePending[name] || VE_COMPOSITES[name].read();
  if (name === "format") {
    for (const btn of document.querySelectorAll("#veFormatChips button[data-format]")) btn.setAttribute("aria-checked", String(btn.dataset.format === value));
    _veEl("veCustomSizeRow").hidden = value !== "custom";
    _veEl("veDualLegacyRow").hidden = value !== "dual";
  } else {
    const control = _veEl(VE_COMPOSITE_CONTROL[name]);
    if (control) control.value = value;
  }
  if (name === "fill") _veEl("vePadColorRow").hidden = value !== "pad";
  if (name === "silence") _veEl("veSilenceTuneRow").hidden = value === "off";
  if (name === "speed") { _veEl("veSpeedSliderWrap").hidden = value !== "speed"; _veEl("veTargetSecondsWrap").hidden = value !== "timelapse"; }
  if (name === "audio") { _veEl("veReplaceAudioRow").hidden = value !== "file"; _veEl("veAudioTrackWrap").hidden = value !== "original"; }
  if (name === "quality") { _veEl("veTargetSizeWrap").hidden = value !== "size"; _veEl("veQualityManualWrap").hidden = value !== "manual"; }
}

function _veSyncComposites(clearPending) {
  if (clearPending) for (const key of Object.keys(_veCompositePending)) delete _veCompositePending[key];
  for (const name of Object.keys(VE_COMPOSITES)) _veRenderComposite(name);
  _veSyncRunMode();
  _veSyncLayerCards();
  _veSyncMiscVisibility();
  _veRenderRemovalText();
}

function _veSetComposite(name, value) {
  const changes = VE_COMPOSITES[name].write(value);
  _veCompositePending[name] = value;
  _veWriteLegacy(changes);
  // ערך שכבר מתבטא ב-legacy לא צריך "המתנה"
  if (VE_COMPOSITES[name].read() === value) delete _veCompositePending[name];
  _veRenderComposite(name);
}

document.getElementById("veFormatChips").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-format]");
  if (btn) _veSetComposite("format", btn.dataset.format);
});
for (const [name, id] of Object.entries(VE_COMPOSITE_CONTROL)) {
  _veEl(id).addEventListener("change", () => _veSetComposite(name, _veEl(id).value));
}
// שינוי קודק: רמת איכות מוכנה עוברת למספר המתאים לקודק החדש
_veEl("veCodec").addEventListener("change", () => {
  const level = _veEl("veQualityMode").value;
  if (["best", "balanced", "small"].includes(level)) _veSetComposite("quality", level);
  else _veRenderComposite("quality");
});
// שדה legacy שהשתנה מבחוץ (איפוס/Undo/טעינת פרופיל/איפוס-אזור) -> ה-composite מתעדכן
document.getElementById("videoEditorOptions").addEventListener("change", (e) => {
  if (_veCompositeWriting) return;
  if (e.target.closest && (e.target.closest("#veLegacyFields") || ["veTargetSeconds", "veSpeed", "veReplaceAudioPath", "veTargetSizeMb", "veCrf", "veNvencCq", "veCustomWidth", "veCustomHeight"].includes(e.target.id))) {
    _veSyncComposites(false);
  }
}, true);

function _veSyncMiscVisibility() {
  _veEl("veLoudnormTarget").hidden = !_veIsChecked("veLoudnorm");
  _veEl("veGifOptionsWrap").hidden = !_veValue("veExportGif");
  _veEl("veMaxConcurrentNvenc").hidden = (parseInt(_veValue("veParallel"), 10) || 1) <= 1;
}
for (const id of ["veLoudnorm", "veExportGif", "veParallel"]) _veEl(id).addEventListener("change", _veSyncMiscVisibility);
_veEl("veParallel").addEventListener("input", _veSyncMiscVisibility);

// --- מצב ריצה (בתפריט של ▶) ---
const VE_RUN_MODE_LABELS = {normal: "▶ הרץ", force: "🔁 רנדר מחדש", validate: "🧪 בדוק", contact: "🖼️ contact-sheet"};
function _veSyncRunMode() {
  const mode = _veIsChecked("veValidateOnly") ? "validate" : _veIsChecked("vePreviewOnly") ? "contact" : _veIsChecked("veForce") ? "force" : "normal";
  for (const radio of document.querySelectorAll('input[name="veRunMode"]')) radio.checked = radio.value === mode;
  _veEl("veStickyRunBtn").textContent = VE_RUN_MODE_LABELS[mode];
}
for (const radio of document.querySelectorAll('input[name="veRunMode"]')) {
  radio.addEventListener("change", () => {
    _veWriteLegacy({veForce: radio.value === "force", veValidateOnly: radio.value === "validate", vePreviewOnly: radio.value === "contact"});
    _veSyncRunMode();
  });
}

// --- פשוט / מתקדם ---
// גל 34: שלוש רמות - פשוט (ארבעה צעדים), רגיל (בלי ההגדרות הטכניות הנדירות, VE_RARE_FIELDS), מומחה ("advanced" - הכל)
const VE_MODES = ["simple", "regular", "advanced"];
function _veCurrentMode() { const mode = _veLoadPref("veMode", "simple"); return VE_MODES.includes(mode) ? mode : "simple"; }
function setVeMode(mode) {
  if (mode === "simple" && typeof exitVeClipMode === "function") exitVeClipMode();  // גל 30: עריכת קליפ לא קיימת בצעדים
  _veSavePref("veMode", VE_MODES.includes(mode) ? mode : "simple");
  _veApplyMode();
}
function _veApplyMode() {
  const mode = _veCurrentMode();
  _veEl("videoEditorOptions").classList.toggle("ve-simple", mode === "simple");
  _veEl("videoEditorOptions").classList.toggle("ve-regular", mode === "regular");
  _veEl("veModeSimpleBtn").setAttribute("aria-pressed", String(mode === "simple"));
  _veEl("veModeRegularBtn").setAttribute("aria-pressed", String(mode === "regular"));
  _veEl("veModeAdvancedBtn").setAttribute("aria-pressed", String(mode === "advanced"));
  _veRenderCategoryTabs();
  _veUpdateAdvancedHint();
  uiBus.emit("ve:mode-changed", mode);
}

// --- מה שונה מברירת המחדל: שורות, composites, רמז "הגדרות מתקדמות פעילות" ---
const VE_COMPOSITE_LEGACY_IDS = new Set(Object.values(VE_COMPOSITES).flatMap(c => c.legacy));
function _veCompositeChanged(name) { return VE_COMPOSITES[name].legacy.some(id => _veFieldChanged(_veEl(id))); }

function _veMarkChangedRows() {
  const changedComposites = new Set(Object.keys(VE_COMPOSITES).filter(_veCompositeChanged));
  for (const row of document.querySelectorAll("#veCategories .ve-row")) {
    let changed = [...row.querySelectorAll("input, select, textarea")].some(el => _veFieldChanged(el));
    const composite = row.dataset.composite;
    if (composite) changed = changed || Object.keys(VE_COMPOSITE_ROW).some(n => VE_COMPOSITE_ROW[n] === composite && changedComposites.has(n));
    row.classList.toggle("ve-row-changed", changed);
  }
  for (const card of document.querySelectorAll("#veCategories .ve-layer-card")) {
    if (!card.hidden && card.querySelector(".ve-row-changed")) card.querySelector(".ve-row")?.classList.add("ve-row-changed");
  }
}

function _veUpdateAdvancedHint() {
  const hint = _veEl("veAdvancedHint");
  if (_veCurrentMode() !== "simple") { hint.hidden = true; return; }
  const count = [...document.querySelectorAll("#veCategories [data-adv] .ve-row-changed, #veCategories .ve-row-changed[data-adv]")].length;
  hint.hidden = !count;
  hint.textContent = `⚙️ ${count} הגדרות מתקדמות פעילות - הצג`;
}

function setVeOnlyChanged(on) {
  _veSavePref("veOnlyChanged", !!on);
  _veEl("videoEditorOptions").classList.toggle("ve-only-changed", !!on);
  _veMarkChangedRows();
}

// תקצירי-אזור ואיפוס-אזור סופרים גם שדות legacy שה-composite שלהם יושב באזור
const _veChangedFieldsInCategoryBeforeWave10 = _veChangedFieldsInCategory;
_veChangedFieldsInCategory = function (details) {
  const keys = _veChangedFieldsInCategoryBeforeWave10(details);
  for (const [name, composite] of Object.entries(VE_COMPOSITES)) {
    const row = _veCompositeRowEl(name);
    if (!row || !details.contains(row)) continue;
    for (const id of composite.legacy) {
      const key = Object.keys(VE_FAVORITABLE_FIELDS).find(k => VE_FAVORITABLE_FIELDS[k].id === id);
      if (key && !keys.includes(key) && _veFieldChanged(_veEl(id))) keys.push(key);
    }
  }
  return keys;
};

// קפיצה לשדה (מאזהרה/מקראה/פלטה): שדה legacy -> השורה של ה-composite שלו
const _veScrollToFieldBeforeWave10 = veScrollToField;
veScrollToField = function (fieldKey) {
  const meta = VE_FAVORITABLE_FIELDS[fieldKey];
  const el = meta && _veEl(meta.id);
  if (!el || !el.closest("#veLegacyFields")) return _veScrollToFieldBeforeWave10(fieldKey);
  const name = Object.keys(VE_COMPOSITES).find(n => VE_COMPOSITES[n].legacy.includes(meta.id));
  const row = name ? _veCompositeRowEl(name) : (meta.id.startsWith("veRemoveWatermark") ? document.querySelector('[data-composite="removal"]') : null);
  if (!row) return;
  if ((_veCurrentMode() === "simple" && row.closest("[data-adv]")) || (_veCurrentMode() === "regular" && row.closest(".ve-rare"))) setVeMode("advanced");
  _veRevealElement(row);
  row.scrollIntoView({behavior: "smooth", block: "center"});
  row.classList.remove("ve-flash-highlight"); void row.offsetWidth; row.classList.add("ve-flash-highlight");
};

// ↺ לשורת composite: מאפס את כל השדות שהיא עורכת (גם המוסתרים)
function _veSetupCompositeResetButtons() {
  for (const row of document.querySelectorAll("#veCategories .ve-composite-row")) {
    if (row.querySelector(".ve-composite-reset")) continue;
    const names = Object.keys(VE_COMPOSITE_ROW).filter(n => VE_COMPOSITE_ROW[n] === row.dataset.composite);
    if (!names.length) continue;
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "ve-field-reset ve-composite-reset"; btn.textContent = "↺";
    btn.title = "אפס לברירת המחדל"; btn.setAttribute("aria-label", "אפס לברירת המחדל");
    btn.onclick = () => {
      const changes = {};
      for (const n of names) for (const id of VE_COMPOSITES[n].legacy) if (_veFieldDefaults && id in _veFieldDefaults) changes[id] = _veFieldDefaults[id];
      for (const el of row.querySelectorAll("input, select, textarea")) if (_veFieldDefaults && el.id in _veFieldDefaults) changes[el.id] = _veFieldDefaults[el.id];
      for (const n of names) delete _veCompositePending[n];
      _veWriteLegacy(changes);
      _veSyncComposites(false);
    };
    row.appendChild(btn);
  }
}

// --- כרטיסי שכבות (לוגו / PiP / סרגל / מסגרת / מחיקת לוגו ישן) ---
const VE_LAYER_CARDS = {
  logo: {active: () => _veHasText("veWatermarkPath"), focus: "veWatermarkPath", fields: ["veWatermarkPath", "veWatermarkPosition", "veWatermarkPositionVertical", "veWatermarkMoveSeconds", "veWatermarkOpacity", "veWatermarkScale"]},
  pip: {active: () => _veHasText("vePipPath"), focus: "vePipPath", fields: ["vePipPath", "vePipPosition", "vePipScale", "vePipOpacity", "vePipAudio", "vePipDuck", "vePipX", "vePipY"]},
  progress: {active: () => _veIsChecked("veProgressBar"), focus: "veProgressBarColor", fields: ["veProgressBar", "veProgressBarColor", "veProgressBarPosition", "veProgressBarHeight"], onAdd: {veProgressBar: true}},
  frame: {active: () => (parseInt(_veValue("veFrameThickness"), 10) || 0) > 0, focus: "veFrameThickness", fields: ["veFrameThickness", "veFrameColor"], onAdd: {veFrameThickness: "8"}},
  removal: {active: () => _veHasText("veRemoveWatermarkRegion") || _veHasText("veRemoveWatermarkPosition"), focus: "veRemovalCorner", fields: ["veRemoveWatermarkRegion", "veRemoveWatermarkPosition", "veRemoveWatermarkWidthFraction", "veRemoveWatermarkHeightFraction"]},
};
const _veCardsOpened = new Set();

function _veSyncLayerCards() {
  for (const [kind, card] of Object.entries(VE_LAYER_CARDS)) {
    const el = document.querySelector(`.ve-layer-card[data-card="${kind}"]`);
    if (el) el.hidden = !(card.active() || _veCardsOpened.has(kind));
  }
}

function addVeLayerCard(kind) {
  const card = VE_LAYER_CARDS[kind];
  _veCardsOpened.add(kind);
  if (card.onAdd && !card.active()) _veWriteLegacy(card.onAdd);
  _veSyncLayerCards();
  const el = document.querySelector(`.ve-layer-card[data-card="${kind}"]`);
  _veRevealElement(el);
  el.scrollIntoView({behavior: "smooth", block: "center"});
  const focus = _veEl(card.focus);
  if (focus) focus.focus();
}

function removeVeLayerCard(kind) {
  const changes = {};
  for (const id of VE_LAYER_CARDS[kind].fields) if (_veFieldDefaults && id in _veFieldDefaults) changes[id] = _veFieldDefaults[id]; else if (_veEl(id) && _veEl(id).type === "hidden") changes[id] = "";
  _veCardsOpened.delete(kind);
  _veWriteLegacy(changes);
  if (kind === "logo" && typeof clearWatermarkCustomPosition === "function") clearWatermarkCustomPosition();
  if (kind === "removal" && typeof _veSyncRegionField === "function") _veSyncRegionField();
  _veSyncLayerCards();
}

// --- מחיקת לוגו ישן: פינה מהירה -> אזור (x,y,רוחב,גובה כשברים), במקום פינה+אחוזים נפרדים ---
function _veCornerRegion(corner, w, h) {
  const x = corner.endsWith("left") ? 0 : corner.endsWith("right") ? 1 - w : (1 - w) / 2;
  const y = corner.startsWith("top") ? 0 : corner.startsWith("bottom") ? 1 - h : (1 - h) / 2;
  return [x, y, w, h].map(v => Math.round(v * 1000) / 1000).join(",");
}

_veEl("veRemovalCorner").addEventListener("change", () => {
  const corner = _veEl("veRemovalCorner").value;
  if (!corner) return;
  _veWriteLegacy({veRemoveWatermarkRegion: _veCornerRegion(corner, 0.2, 0.12), veRemoveWatermarkPosition: ""});
  _veEl("veRemovalCorner").value = "";
  _veSyncRegionField();
});

function _veRenderRemovalText() {
  if (typeof _veSyncRegionField === "function") _veSyncRegionField();
  const text = _veEl("veRemoveWatermarkRegionText");
  if (!_veHasText("veRemoveWatermarkRegion")) text.textContent = "לא סומן - בחר פינה מהירה או סמן על פריים";
}

// --- מיגרציה בטעינה: טקסט קבוע / חותמת-זמן / פינת-מחיקה ישנה -> המבנה החדש ---
const VE_TEXT_POSITION_TO_LAYER = {bottom: "bottom-center", top: "top-center", center: "center"};
function _veMigrateLegacyFields(fields) {
  const out = {...fields};
  const layers = Array.isArray(out.layers) ? [...out.layers] : [];
  if (typeof out.text === "string" && out.text.trim()) {
    layers.unshift({type: "text", text: out.text, start: 0, end: null, position: VE_TEXT_POSITION_TO_LAYER[out.text_position] || "bottom-center",
      opacity: 1, font: out.text_font || "Arial", font_size: parseInt(out.text_font_size, 10) || 24, color: out.text_color || "#FFFFFF", box: false, animation: "none"});
    out.text = "";
  }
  if (out.timestamp_overlay) {
    layers.push({type: "timestamp", start: 0, end: null, position: out.timestamp_overlay, opacity: 1, font: "Arial", font_size: 36, color: "#FFFFFF", box: true, animation: "none"});
    out.timestamp_overlay = "";
  }
  if (layers.length !== (Array.isArray(fields.layers) ? fields.layers.length : 0)) out.layers = layers;
  if (out.remove_watermark_position && !out.remove_watermark_region) {
    const w = parseFloat(out.remove_watermark_width_fraction) || 0.2, h = parseFloat(out.remove_watermark_height_fraction) || 0.12;
    out.remove_watermark_region = _veCornerRegion(out.remove_watermark_position, w, h);
    out.remove_watermark_position = "";
  }
  return out;
}

const _applyVideoEditorFieldsBeforeWave10 = _applyVideoEditorFields;
_applyVideoEditorFields = function (fields) {
  const result = _applyVideoEditorFieldsBeforeWave10(_veMigrateLegacyFields(fields || {}));
  _veCardsOpened.clear();
  _veSyncComposites(true);
  _veRefreshAllDerivedUi();
  return result;
};

const _resetVideoEditorToDefaultsBeforeWave10 = resetVideoEditorToDefaults;
resetVideoEditorToDefaults = async function () {
  const result = await _resetVideoEditorToDefaultsBeforeWave10();
  _veCardsOpened.clear();
  _veSyncComposites(true);
  return result;
};

// --- פס עליון: שמירה, דיאלוג פרופילים, דיאלוג תמלול ---
function veSaveOrUpdateProfile() {
  if (_isPersonalProfileSelected()) updateVideoEditorProfile(); else veSaveAsNewProfile();
}
function veSaveAsNewProfile() {
  _veEl("veProfileName").value = "";
  saveVideoEditorProfile();
}
function openVeProfileManager() {
  _veEl("veProfileModalBg").classList.add("show");
  const name = _currentVeProfileName();
  if (name && typeof _loadAndShowProfileMeta === "function") _loadAndShowProfileMeta(name);
}
function closeVeProfileManager() { _veEl("veProfileModalBg").classList.remove("show"); }
function openVeTranscriptDialog() {
  _veSyncTranscriptFiles();
  if (!_veEl("veTranscriptFile").options.length) _vePopulatePreviewFiles();
  _veEl("veTranscriptModalBg").classList.add("show");
}
function closeVeTranscriptDialog() { _veEl("veTranscriptModalBg").classList.remove("show"); }
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  for (const id of ["veProfileModalBg", "veTranscriptModalBg"]) {
    const bg = _veEl(id);
    if (bg.classList.contains("show") && !_veEl("veConfirmModalBg").classList.contains("show")) bg.classList.remove("show");
  }
});

// --- הרחבות לחלקים קיימים ---
// מגירת הריצות: טעינה עצלה כמו קודם (היא כבר לא בתוך #veCategories)
_veEl("veRunsDrawer").addEventListener("toggle", () => _veRunLazyInit(_veEl("veRunsDrawer")));

// טאבים: אזור "מתקדם" לא מוצג כטאב במצב פשוט
const _veRenderCategoryTabsBeforeWave10 = _veRenderCategoryTabs;
_veRenderCategoryTabs = function () {
  _veRenderCategoryTabsBeforeWave10();
  if (_veCurrentMode() !== "simple") return;
  const nav = _veEl("veCatTabs");
  const hidden = _veCategoryEls().filter(d => d.hasAttribute("data-adv")).map(d => d.querySelector(".ve-cat-title").textContent);
  for (const btn of nav.querySelectorAll("button")) if (hidden.some(t => btn.textContent.startsWith(t))) btn.hidden = true;
};

// רענון UI נגזר: גם שורות-ששונו, רמז-מתקדם
uiBus.on("ve:derived-refresh", () => {
  // כרטיס שכבה נחשף גם כשהשדה שלו מולא מבחוץ (פרופיל/Ctrl+K/גרירה), לא רק מ"➕ הוסף"
  uiDebounce("ve:derived-cards", () => { _veSyncLayerCards(); _veMarkChangedRows(); _veUpdateAdvancedHint(); _veRenderDragHandles(); }, 180);
});

// מונחי English לשורות ה-composite (אין להן שדה-מקראה אחד)
const VE_COMPOSITE_LABELS_EN = {format: "Format:", fill: "Fill the frame:", resolution: "Resolution:", silence: "Remove silence:", speed: "Speed:",
  cleanup: "Noise / sharpen:", audio: "Audio:", quality: "Quality:", gpu: "GPU:", removal: "Area:"};
const _veApplyLanguageBeforeWave10 = _veApplyLanguage;
_veApplyLanguage = function (english) {
  _veApplyLanguageBeforeWave10(english);
  for (const row of document.querySelectorAll("#veCategories .ve-composite-row")) {
    const label = row.querySelector(":scope > label");
    if (!label) continue;
    if (label.dataset.veHeText === undefined) label.dataset.veHeText = label.textContent;
    label.textContent = english && VE_COMPOSITE_LABELS_EN[row.dataset.composite] ? VE_COMPOSITE_LABELS_EN[row.dataset.composite] : label.dataset.veHeText;
    label.dir = english ? "ltr" : "";
  }
  const categories = (_veEnglishData && _veEnglishData.categories) || {};
  for (const details of document.querySelectorAll("#videoEditorOptions details.ve-side-panel, #veRunsDrawer")) {
    const title = details.querySelector(".ve-cat-title");
    if (title.dataset.veHe === undefined) title.dataset.veHe = title.textContent;
    title.textContent = english && categories[details.dataset.cat] ? categories[details.dataset.cat] : title.dataset.veHe;
  }
};

function _veInitWave10() {
  _veApplyMode();
  setVeOnlyChanged(_veLoadPref("veOnlyChanged", false));
  _veSetupCompositeResetButtons();
  _veSyncComposites(true);
  _veMarkChangedRows();
  _veInitWave10b();
}

