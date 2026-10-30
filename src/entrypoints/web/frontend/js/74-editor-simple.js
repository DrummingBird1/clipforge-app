// ============================================================================
// גל 30 - מודל עבודה פשוט ומילים ברורות:
//  * אינדיקטור שמירה אחד: הפרויקט נשמר לבד ("✓ נשמר"), ו"הסגנון שונה - עדכן / שמור כחדש"
//    מופיע רק כשבאמת יש מה לשמור (סגנון אישי נבחר וההגדרות שונות ממנו).
//  * מראות מוכנים עם תצוגה: כרטיס לכל מראה (טבעי, קולנועי, חי, שחור-לבן, וינטג', חמים) עם
//    הפריים הנוכחי בצבעים של המראה. לחיצה מחילה; הסליידרים נשארים לכוונון.
//  * "פשוט" = ארבעה צעדים: תיקייה, יעדים, מראה, הרצה. כל השאר ב"מתקדם".
// ============================================================================

// --- אינדיקטור שמירה ---
function _veRenderSaveState() {
  const box = _veEl("veSaveState");
  if (!box) return;
  const dirty = _veStyleDirty();
  const info = _veProjectSaveInfo || {state: "idle"};
  const text = _veEl("veSaveStateText");
  _veEl("veSaveStateUpdate").hidden = !dirty;
  _veEl("veSaveStateNew").hidden = !dirty;
  box.dataset.state = dirty ? "dirty" : info.state;
  if (dirty) {
    text.textContent = `● הסגנון "${_currentVeProfileName()}" שונה`;
    box.title = "השינויים עוד לא בסגנון השמור - הפרויקט עצמו נשמר אוטומטית";
  } else if (info.state === "saving") {
    text.textContent = "⏳ שומר...";
    box.title = "";
  } else if (info.state === "error") {
    text.textContent = "⚠️ לא נשמר";
    box.title = info.error || "";
  } else if (info.state === "saved") {
    text.textContent = "✓ נשמר";
    const at = info.at && !isNaN(info.at) ? " - " + info.at.toLocaleTimeString("he-IL", {hour: "2-digit", minute: "2-digit"}) : "";
    box.title = "הפרויקט (תיקייה, הגדרות, יעדים, עריכות קליפים ותור) נשמר אוטומטית" + at;
  } else {
    text.textContent = "";
    box.title = "";
  }
  box.hidden = !text.textContent;
}

// --- מראות מוכנים ---
// שדות הצבע שמראה קובע. LUT נשאר של המשתמש (מתקדם) - מראה לא נוגע בו.
const VE_LOOK_FIELDS = {
  eq_brightness: "veEqBrightness", eq_contrast: "veEqContrast", eq_saturation: "veEqSaturation", eq_gamma: "veEqGamma",
  grade_shadows: "veGradeShadows", grade_midtones: "veGradeMidtones", grade_highlights: "veGradeHighlights",
  curves_preset: "veCurvesPreset", curves_master: "veCurvesMaster", curves_red: "veCurvesRed", curves_green: "veCurvesGreen", curves_blue: "veCurvesBlue",
  vignette: "veVignette",
};
const VE_LOOKS = [
  {id: "natural", icon: "🌿", label: "טבעי", title: "בלי שינוי צבע", values: {}},
  {id: "cinematic", icon: "🎬", label: "קולנועי", title: "ניגודיות, צללים כחלחלים והדגשות חמות, וינייטה קלה",
    values: {eq_contrast: "1.15", eq_saturation: "0.85", grade_shadows: "-0.04,0,0.05", grade_highlights: "0.05,0.02,-0.04", vignette: "light"}},
  {id: "vivid", icon: "🌈", label: "צבעוני", title: "צבעים רוויים וניגודיות", values: {eq_brightness: "0.02", eq_contrast: "1.1", eq_saturation: "1.45"}},
  {id: "bw", icon: "⚫", label: "שחור-לבן", title: "בלי צבע, ניגודיות גבוהה", values: {eq_contrast: "1.2", eq_saturation: "0"}},
  {id: "vintage", icon: "📻", label: "וינטג'", title: "עקומת וינטג', צבעים דהויים ווינייטה", values: {eq_brightness: "0.03", eq_saturation: "0.8", curves_preset: "vintage", vignette: "medium"}},
  {id: "warm", icon: "☀️", label: "חמים", title: "גוון חם באמצע הטונים", values: {eq_saturation: "1.1", grade_midtones: "0.04,0.01,-0.04"}},
];

function _veLookDefaults() {
  const out = {};
  for (const [key, id] of Object.entries(VE_LOOK_FIELDS)) {
    const el = _veEl(id);
    out[key] = _veFieldDefaults && id in _veFieldDefaults ? String(_veFieldDefaults[id]) : (el.tagName === "SELECT" ? el.options[0].value : el.defaultValue);
  }
  return out;
}
const _veLookValues = (look) => ({..._veLookDefaults(), ...look.values});

function _veActiveLook() {
  const current = Object.fromEntries(Object.entries(VE_LOOK_FIELDS).map(([key, id]) => [key, _veEl(id).value]));
  return VE_LOOKS.find(look => {
    const values = _veLookValues(look);
    return Object.keys(VE_LOOK_FIELDS).every(key => _veSameFieldValue(current[key], values[key]));
  }) || null;
}

function applyVeLook(id) {
  const look = VE_LOOKS.find(item => item.id === id);
  if (!look || _veClipModeRefuses("המראה")) return;
  const values = _veLookValues(look);
  for (const [key, fieldId] of Object.entries(VE_LOOK_FIELDS)) {
    const el = _veEl(fieldId);
    if (String(el.value) !== String(values[key])) _veSetFieldValue(el, values[key]);
  }
  for (const range of Object.keys(VE_GRADE_RANGES)) _veRenderWheel(range);
  _veCurveCanvasDraw();
  _veSyncLookCards();
}

// פילטר CSS לכרטיס: בהירות/ניגודיות/רוויה כמו בנגן החי, וגלגלי צבע/עקומות דרך פילטר SVG לכל מראה
function _veLookFilter(look) {
  const v = _veLookValues(look);
  let filter = `brightness(${1 + (Number(v.eq_brightness) || 0)}) contrast(${Number(v.eq_contrast) || 1}) saturate(${Number(v.eq_saturation)})`;
  if (_veGradeActive(v)) filter += ` url(#veLookGrade-${look.id})`;
  return filter;
}

function _veEnsureLookFilters() {
  if (_veEl("veLookSvg")) return;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.id = "veLookSvg";
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("ve-svg-defs");
  for (const look of VE_LOOKS) {
    const values = _veLookValues(look);
    if (!_veGradeActive(values)) continue;
    const ns = "http://www.w3.org/2000/svg";
    const filter = document.createElementNS(ns, "filter");
    filter.id = `veLookGrade-${look.id}`;
    filter.setAttribute("color-interpolation-filters", "sRGB");
    const transfer = document.createElementNS(ns, "feComponentTransfer");
    _veGradeTables(values).forEach((table, i) => {
      const func = document.createElementNS(ns, ["feFuncR", "feFuncG", "feFuncB"][i]);
      func.setAttribute("type", "table");
      func.setAttribute("tableValues", table);
      transfer.appendChild(func);
    });
    filter.appendChild(transfer);
    svg.appendChild(filter);
  }
  document.body.appendChild(svg);
}

// הפריים לכרטיסים: הרגע הנוכחי בנגן החי (המקור, לפני צבע), אחרת תמונה ממוזערת של הקובץ, אחרת דוגמה
function _veLookFrameSource() {
  const video = _veEl("veLiveVideo");
  if (video && video.readyState >= 2 && video.videoWidth) {
    try {
      const canvas = document.createElement("canvas");
      canvas.width = 192;
      canvas.height = Math.max(1, Math.round(192 * video.videoHeight / video.videoWidth));
      canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
      return canvas.toDataURL("image/jpeg", 0.75);
    } catch (e) { /* מקור שלא אפשר לקרוא ממנו - נופלים לתמונה הממוזערת */ }
  }
  const file = _veEl("vePreviewFile").value;
  return state.folder && file ? "/api/video_editor/file_thumbnail?path=" + encodeURIComponent(_veFolderPath(file)) : "";
}

function _veRenderLookCards() {
  _veEnsureLookFilters();
  for (const box of document.querySelectorAll(".ve-look-cards")) {
    if (box.childElementCount) continue;
    for (const look of VE_LOOKS) {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "ve-look-card";
      card.dataset.look = look.id;
      card.title = look.title;
      card.setAttribute("aria-pressed", "false");
      const thumb = document.createElement("span");
      thumb.className = "ve-look-thumb";
      thumb.dataset.vignette = _veLookValues(look).vignette;
      const img = document.createElement("img");
      img.alt = "";
      img.hidden = true;
      thumb.appendChild(img);
      thumb.style.filter = _veLookFilter(look);
      const name = document.createElement("span");
      name.className = "ve-look-name";
      name.textContent = `${look.icon} ${look.label}`;
      card.append(thumb, name);
      card.onclick = () => applyVeLook(look.id);
      box.appendChild(card);
    }
  }
  _veRefreshLookThumbs();
  _veSyncLookCards();
}

function _veRefreshLookThumbs() {
  const src = _veLookFrameSource();
  for (const img of document.querySelectorAll(".ve-look-thumb img")) {
    if (!src) { img.hidden = true; img.removeAttribute("src"); continue; }
    if (img.getAttribute("src") !== src) img.src = src;
    img.hidden = false;
  }
}

function _veSyncLookCards() {
  const active = _veActiveLook();
  for (const card of document.querySelectorAll(".ve-look-card")) card.setAttribute("aria-pressed", String(!!active && card.dataset.look === active.id));
  for (const note of document.querySelectorAll(".ve-look-custom")) note.hidden = !!active;
}

// --- "פשוט" = ארבעה צעדים ---
function _veRenderSteps() {
  const steps = _veEl("veSteps");
  if (!steps) return;
  const folder = state.folder || "";
  const name = folder ? folder.replace(/[\\/]+$/, "").split(/[\\/]/).pop() : "";
  const count = _veFileCountText().replace(/^📁\s*/, "");
  _veEl("veStepFolderText").textContent = folder ? `${name}${count ? " - " + count : ""}` : "עוד לא נבחרה תיקייה";
  _veEl("veStepFolderText").title = folder;
  _veEl("veStepFolderBtn").textContent = folder ? "📂 החלף תיקייה..." : "📂 בחר תיקייה...";
  const targets = _veTargets();
  const look = _veActiveLook();
  steps.querySelector("[data-step=folder]").classList.toggle("ve-step-done", !!folder);
  steps.querySelector("[data-step=targets]").classList.toggle("ve-step-done", targets.length > 0);
  steps.querySelector("[data-step=look]").classList.toggle("ve-step-done", !!look && look.id !== "natural");
  _veEl("veStepTargetsNote").textContent = targets.length
    ? `כל סרטון ייצא ל-${targets.length} יעדים, כל אחד בפורמט ובתיקייה משלו`
    : "בלי יעד - סרטון אחד בפורמט שבהגדרות";
  const files = _veQueueDirty && _veQueueState.length ? _veQueueState.filter(f => f.selected).length : (_veFolderCounts ? _veFolderCounts.files : 0);
  const outputs = files * Math.max(1, targets.length);
  const sum = targets.length > 1 ? `${files} קבצים × ${targets.length} יעדים = ${outputs} סרטונים` : `${files} קבצים = ${outputs} סרטונים`;
  _veEl("veStepRunText").textContent = !folder ? "בחר תיקייה כדי להתחיל" : outputs ? sum : "אין קבצי וידאו בתיקייה";
  _veEl("veStepRunBtn").disabled = _veEl("veStickyRunBtn").disabled || !folder;
  _veEl("veStepRunBtn").textContent = _veEl("veStickyRunBtn").textContent;
}

uiBus.on("ve:derived-refresh", () => {
  _veSyncLookCards();
  if (_veEl("videoEditorOptions").classList.contains("ve-simple")) _veRenderSteps();
});

function _veInitWave30() {
  _veRenderLookCards();
  _veRenderSaveState();
  _veRenderSteps();
  _veEl("vePreviewFile").addEventListener("change", () => setTimeout(_veRefreshLookThumbs, 0));
  const video = _veEl("veLiveVideo");
  for (const type of ["pause", "seeked", "loadeddata"]) video.addEventListener(type, () => uiDebounce("ve:look-thumbs", _veRefreshLookThumbs, 250));
  new MutationObserver(() => _veRenderSteps()).observe(_veEl("veStickyRunBtn"), {attributes: true, attributeFilter: ["disabled"], childList: true, characterData: true, subtree: true});
  uiBus.on("ve:folder-changed", () => setTimeout(() => { _veRenderSteps(); _veRefreshLookThumbs(); }, 0));
}
