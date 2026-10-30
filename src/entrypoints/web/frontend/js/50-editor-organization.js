// ============================================================================
// גל 2 של 102-ההצעות: ארגון וסידור עורך-העל (items 1-18)
// ============================================================================

const VE_PROFILE_ACTION_BUTTON_IDS = [
  "veDeleteProfileBtn", "veUpdateProfileBtn", "veRenameProfileBtn", "veStickyUpdateBtn",
  "veDuplicateProfileBtn", "veHistoryProfileBtn", "veExportProfileBtn", "veProfileMoreBtn",
];

// item: קיבוץ כפתורי הפרופיל - נקודה אחת שמציגה/מסתירה את כל כפתורי-הפעולה של
// פרופיל אישי (היו 6 עותקים כמעט-זהים של 7 שורות .hidden= פזורים בקוד).
function _setVeProfileButtonsVisible(visible) {
  for (const id of VE_PROFILE_ACTION_BUTTON_IDS) {
    const el = document.getElementById(id);
    if (el) el.hidden = !visible;
  }
  if (!visible) closeVeMenus();
}

// --- תפריטים נפתחים (⋯ עוד / 🧰 ניהול / 🗂️ תצוגה) ---
function toggleVeMenu(menuId, event) {
  if (event) event.stopPropagation();
  const menu = document.getElementById(menuId);
  const willOpen = menu.hidden;
  closeVeMenus();
  menu.hidden = !willOpen;
  const trigger = menu.parentElement.querySelector("button[aria-haspopup]");
  if (trigger) trigger.setAttribute("aria-expanded", String(willOpen));
  if (willOpen) {
    const first = menu.querySelector("button:not([hidden]), input");
    if (first) first.focus();
  }
}

function closeVeMenus() {
  for (const menu of document.querySelectorAll(".ve-menu")) menu.hidden = true;
  for (const trigger of document.querySelectorAll(".ve-menu-wrap > button[aria-haspopup]")) trigger.setAttribute("aria-expanded", "false");
}

document.addEventListener("click", (e) => {
  if (!e.target.closest(".ve-menu")) closeVeMenus();
  else if (e.target.closest(".ve-menu button")) closeVeMenus();  // פעולה נבחרה - סוגרים
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeVeMenus(); });

// --- העדפות תצוגה פר-דפדפן (localStorage - נוחות, לא הגדרת-רינדור) ---
function _veLoadPref(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch (e) { return fallback; }
}

function _veSavePref(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* פרטי/מוגבל - לא קריטי */ }
}

function _veCategoryEls() {
  return Array.from(document.querySelectorAll("#veCategories > details.ve-category[data-cat]"));
}

function _veCategoryByKey(key) {
  return document.querySelector(`#veCategories > details.ve-category[data-cat="${key}"]`);
}

// item: זכירת מצב פתוח/סגור לכל קטגוריה per-browser. נשמר רק על שינוי שהמשתמש
// יזם (לא כשהחיפוש פותח קטגוריות זמנית, ולא במצב טאבים שכופה פתיחה).
let _veOpenStateSuppressed = false;

function _veApplyCategoryOpenState() {
  const saved = _veLoadPref("veCatOpen", {});
  _veOpenStateSuppressed = true;
  for (const details of _veCategoryEls()) {
    if (typeof saved[details.dataset.cat] === "boolean") details.open = saved[details.dataset.cat];
  }
  setTimeout(() => { _veOpenStateSuppressed = false; }, 0);
}

document.getElementById("veCategories").addEventListener("toggle", (e) => {
  const details = e.target;
  if (!details.matches || !details.matches("details.ve-category[data-cat]")) return;
  if (_veOpenStateSuppressed || _veSearchActive() || _veCurrentLayout() === "tabs" || document.body.classList.contains("ve-sheets")) return;
  const saved = _veLoadPref("veCatOpen", {});
  saved[details.dataset.cat] = details.open;
  _veSavePref("veCatOpen", saved);
}, true);

function resetVeCategoryOpenState() {
  _veSavePref("veCatOpen", {});
  _veOpenStateSuppressed = true;
  for (const details of _veCategoryEls()) details.open = details.dataset.cat !== "queue";
  setTimeout(() => { _veOpenStateSuppressed = false; }, 0);
}

// item: גרירה לסידור-מחדש של הקטגוריות - הסדר נשמר per-browser ומוחל דרך CSS
// order (הקונטיינר הוא flex/grid), בלי להזיז אלמנטים ב-DOM בכלל. Alt+↑/↓ על
// כותרת ממוקדת עושה אותו דבר מהמקלדת (נגישות).
function _veCategoryOrder() {
  const domOrder = _veCategoryEls().map(d => d.dataset.cat);
  const saved = _veLoadPref("veCatOrder", []).filter(k => domOrder.includes(k));
  return [...saved, ...domOrder.filter(k => !saved.includes(k))];
}

function _veApplyCategoryOrder() {
  const order = _veCategoryOrder();
  for (const details of _veCategoryEls()) details.style.order = String(order.indexOf(details.dataset.cat));
  _veRenderCategoryTabs();
}

function _veMoveCategory(key, beforeKey) {
  const order = _veCategoryOrder().filter(k => k !== key);
  const index = beforeKey ? order.indexOf(beforeKey) : -1;
  if (index === -1) order.push(key); else order.splice(index, 0, key);
  _veSavePref("veCatOrder", order);
  _veApplyCategoryOrder();
}

function resetVeCategoryOrder() {
  _veSavePref("veCatOrder", []);
  _veApplyCategoryOrder();
}

function _setupVeCategoryDragAndKeys() {
  for (const details of _veCategoryEls()) {
    const summary = details.querySelector(":scope > summary");
    summary.draggable = true;
    summary.title = "לחץ לפתיחה/סגירה · גרור לשינוי סדר הקטגוריות (או Alt+↑/↓)";
    summary.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/x-ve-category", details.dataset.cat);
      e.dataTransfer.effectAllowed = "move";
      details.classList.add("ve-cat-dragging");
    });
    summary.addEventListener("dragend", () => details.classList.remove("ve-cat-dragging"));
    details.addEventListener("dragover", (e) => {
      if (!e.dataTransfer.types.includes("text/x-ve-category")) return;
      e.preventDefault();
      details.classList.add("ve-cat-drag-over");
    });
    details.addEventListener("dragleave", () => details.classList.remove("ve-cat-drag-over"));
    details.addEventListener("drop", (e) => {
      const key = e.dataTransfer.getData("text/x-ve-category");
      details.classList.remove("ve-cat-drag-over");
      if (!key || key === details.dataset.cat) return;
      e.preventDefault();
      _veMoveCategory(key, details.dataset.cat);
    });
    summary.addEventListener("keydown", (e) => {
      if (!e.altKey || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
      e.preventDefault();
      const order = _veCategoryOrder();
      const i = order.indexOf(details.dataset.cat);
      const j = e.key === "ArrowUp" ? i - 1 : i + 1;
      if (j < 0 || j >= order.length) return;
      [order[i], order[j]] = [order[j], order[i]];
      _veSavePref("veCatOrder", order);
      _veApplyCategoryOrder();
      summary.focus();
    });
  }
}

// המפקח: אזור אחד בכל פעם בלשוניות (ברירת מחדל, גל 28), או כל האזורים ברשימה. גל 31: העורך תמיד
// בסטודיו, אז "שתי עמודות" (שהייתה רק מחוץ לו) ירדה.
function _veCurrentLayout() {
  return _veLoadPref("veLayout", "tabs") === "accordion" ? "accordion" : "tabs";
}

function setVeLayout(layout) {
  _veSavePref("veLayout", layout);
  _veApplyLayout();
}

function _veApplyLayout() {
  const layout = _veCurrentLayout();
  const container = document.getElementById("veCategories");
  container.classList.toggle("ve-layout-tabs", layout === "tabs");
  for (const radio of document.querySelectorAll('input[name="veLayout"]')) radio.checked = radio.value === layout;
  document.getElementById("veCatTabs").hidden = layout !== "tabs";
  if (layout === "tabs") {
    for (const details of _veCategoryEls()) details.open = true;
    _veActivateTab(_veLoadPref("veActiveTab", VE_DEFAULT_TAB));
  } else {
    _veApplyCategoryOpenState();
  }
  _veRenderCategoryTabs();
}

// גל 34: הלשוניות בסדר של זרימת העבודה (זמן, צבע, אפקטים, שכבות, שמע, פלט, ייצוא) - הראשונה היא ברירת המחדל
const VE_DEFAULT_TAB = "time";

function _veActivateTab(key) {
  const target = _veCategoryByKey(key) || _veCategoryEls()[0];
  for (const details of _veCategoryEls()) details.classList.toggle("ve-tab-active", details === target);
  if (target) { target.open = true; _veSavePref("veActiveTab", target.dataset.cat); }
  _veRenderCategoryTabs();
}

function _veRenderCategoryTabs() {
  const nav = document.getElementById("veCatTabs");
  if (!nav || nav.hidden) return;
  const active = _veLoadPref("veActiveTab", VE_DEFAULT_TAB);
  // גל 29: נבנית מחדש רק כשמשהו בה השתנה - בנייה בכל רענון רקע "בלעה" לחיצות על לשונית (נמצא ב-CI)
  const simple = _veEl("videoEditorOptions").classList.contains("ve-simple");
  const signature = JSON.stringify([active, simple, _veCategoryOrder().map(key => {
    const details = _veCategoryByKey(key);
    return details ? [key, details.querySelector(".ve-cat-warn").hidden, key === "queue" ? 0 : _veChangedFieldsInCategory(details).length] : null;
  })]);
  if (nav.dataset.signature === signature && nav.children.length) return;
  nav.dataset.signature = signature;
  nav.innerHTML = "";
  for (const key of _veCategoryOrder()) {
    const details = _veCategoryByKey(key);
    if (!details) continue;
    if (details.hasAttribute("data-adv") && _veEl("videoEditorOptions").classList.contains("ve-simple")) continue;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", String(key === active));
    btn.dataset.cat = key;
    btn.className = key === active ? "active" : "";
    const warn = !details.querySelector(".ve-cat-warn").hidden ? " ⚠️" : "";
    btn.textContent = details.querySelector(".ve-cat-title").textContent + warn;
    // גל 28: כמה הגדרות שונו באזור - נקודה עם מספר על הלשונית
    const changed = key === "queue" ? 0 : _veChangedFieldsInCategory(details).length;
    if (changed) {
      const badge = document.createElement("span");
      badge.className = "ve-tab-changed";
      badge.textContent = String(changed);
      btn.appendChild(badge);
    }
    btn.onclick = () => _veActivateTab(key);
    nav.appendChild(btn);
  }
}

// item: מצב צפוף (compact).
function setVeCompact(on) {
  _veSavePref("veCompact", !!on);
  document.getElementById("videoEditorOptions").classList.toggle("ve-compact", !!on);
  document.getElementById("veCompactToggle").checked = !!on;
}

// item: חשיפה מדורגת - שדה שאין לו שום השפעה בלי שדה-אב (מיקום/שקיפות/גודל
// watermark בלי קובץ watermark, צבעי כרומה-קי בלי כרומה-קי וכו') מוסתר עד
// שהאב מופעל. אותה רשימת-תלויות כמו VE_FAVORITE_DEPENDS_ON, מורחבת לכל
// זוג אב/ילד בפאנל. בזמן חיפוש (או עם "הצג תמיד שדות תלויים") רק מעומעם.
const _veHasText = (id) => !!(document.getElementById(id) && document.getElementById(id).value.trim());
const _veIsChecked = (id) => !!(document.getElementById(id) && document.getElementById(id).checked);
const VE_DEPENDENT_FIELDS = {
  veWatermarkPosition: () => _veHasText("veWatermarkPath"),
  veWatermarkOpacity: () => _veHasText("veWatermarkPath"),
  veWatermarkScale: () => _veHasText("veWatermarkPath"),
  veWmDragCoords: () => _veHasText("veWatermarkPath"),
  veRemoveWatermarkWidthFraction: () => _veHasText("veRemoveWatermarkPosition"),
  veRemoveWatermarkHeightFraction: () => _veHasText("veRemoveWatermarkPosition"),
  vePipPosition: () => _veHasText("vePipPath"),
  vePipScale: () => _veHasText("vePipPath"),
  vePipOpacity: () => _veHasText("vePipPath"),
  veTextFont: () => _veHasText("veText"),
  veSmartCrop: () => _veIsChecked("veVertical"),
  veSmartCropFace: () => _veIsChecked("veVertical") && _veIsChecked("veSmartCrop"),
  veChromakeyColor: () => _veIsChecked("veChromakey"),
  veChromakeySimilarity: () => _veIsChecked("veChromakey"),
  veChromakeyBlend: () => _veIsChecked("veChromakey"),
  veLoudnormTarget: () => _veIsChecked("veLoudnorm"),
  veCaptionsTranslate: () => _veIsChecked("veCaptions"),
  veCaptionFont: () => _veIsChecked("veCaptions"),
  veCaptionColor: () => _veIsChecked("veCaptions"),
  veMaxConcurrentNvenc: () => (parseInt(document.getElementById("veParallel").value || "1", 10) || 1) > 1,
};

// גל 28: id של שדה תלוי -> id של האב (מהסכמה, utils/editor_model.py DEPENDS_ON)
const VE_DEPENDENT_PARENTS = {};

// השדה עצמו - או העטיפה הקטנה שלו (label/span) כשהיא לא מכילה גם את האב
function _veDependentTarget(el, parent) {
  const wrap = el.closest("label, span");
  return wrap && !wrap.contains(parent) && !wrap.classList.contains("ve-row") ? wrap : el;
}

function setVeShowDependent(on) {
  _veSavePref("veShowDependent", !!on);
  document.getElementById("veShowDependentToggle").checked = !!on;
  _veUpdateDependentRows();
}

function _veUpdateDependentRows() {
  const dimInstead = _veLoadPref("veShowDependent", false) || _veSearchActive();
  for (const [id, isActive] of Object.entries(VE_DEPENDENT_FIELDS)) {
    const el = document.getElementById(id);
    if (!el) continue;
    const row = el.closest(".ve-row");
    if (!row || row.closest(".ve-favorite-row")) continue;
    const parent = VE_DEPENDENT_PARENTS[id] && document.getElementById(VE_DEPENDENT_PARENTS[id]);
    const target = parent && row.contains(parent) ? _veDependentTarget(el, parent) : row;
    const active = isActive();
    target.classList.toggle("ve-dep-hidden", !active && !dimInstead);
    target.classList.toggle("ve-dep-dim", !active && dimInstead);
  }
}

// item: חיפוש/סינון גלובלי על כל השדות - מסתיר שורות/תתי-קטגוריות/קטגוריות
// שאין בהן התאמה, פותח את אלה שיש, ומדגיש את השורות התואמות. לא נוגע במצב
// הפתוח/סגור השמור (מוחזר ברגע שמנקים את החיפוש).
function _veSearchActive() {
  const input = document.getElementById("veSearchInput");
  return !!(input && input.value.trim());
}

function _veRowSearchText(row) {
  const parts = [];
  for (const el of row.querySelectorAll("label, span, button")) {
    if (!el.closest("select")) parts.push(el.textContent);
  }
  for (const el of row.querySelectorAll("[title]")) parts.push(el.getAttribute("title"));
  for (const el of row.querySelectorAll("[placeholder]")) parts.push(el.getAttribute("placeholder"));
  for (const el of row.querySelectorAll("input, select")) {
    for (const [key, meta] of Object.entries(VE_FAVORITABLE_FIELDS)) {
      if (meta.id === el.id) { parts.push(key); if (_fieldHelpCache && _fieldHelpCache[key]) parts.push(_fieldHelpCache[key].term); }
    }
  }
  return parts.join(" ").toLowerCase();
}

function onVeSearchInput() {
  const query = document.getElementById("veSearchInput").value.trim().toLowerCase();
  const container = document.getElementById("veCategories");
  const searching = !!query;
  container.classList.toggle("ve-searching", searching);
  for (const el of container.querySelectorAll(".ve-search-hidden, .ve-search-match")) el.classList.remove("ve-search-hidden", "ve-search-match");
  if (!searching) {
    _veApplyLayout();
    _veUpdateDependentRows();
    return;
  }
  _veOpenStateSuppressed = true;
  for (const details of _veCategoryEls()) {
    const titleHit = details.querySelector(".ve-cat-title").textContent.toLowerCase().includes(query);
    let matches = 0;
    for (const row of details.querySelectorAll(".ve-category-body .ve-row")) {
      if (row.closest(".ve-favorite-row") && row !== row.closest(".ve-favorite-row")) continue;
      const hit = titleHit || _veRowSearchText(row).includes(query);
      row.classList.toggle("ve-search-hidden", !hit);
      if (hit && !titleHit) row.classList.add("ve-search-match");
      if (hit) matches++;
    }
    for (const sub of details.querySelectorAll(".ve-subcat")) {
      const subTitleHit = sub.querySelector(".ve-subcat-title").textContent.toLowerCase().includes(query);
      if (subTitleHit) { for (const row of sub.querySelectorAll(".ve-row")) { row.classList.remove("ve-search-hidden"); matches++; } }
      const visibleRows = sub.querySelectorAll(".ve-row:not(.ve-search-hidden)").length;
      sub.classList.toggle("ve-search-hidden", !visibleRows && !subTitleHit);
    }
    details.classList.toggle("ve-search-hidden", matches === 0 && !titleHit);
    if (matches || titleHit) details.open = true;
  }
  setTimeout(() => { _veOpenStateSuppressed = false; }, 0);
  _veUpdateDependentRows();
}

// item: איפוס קטגוריה בלחיצה אחת - כל השדות הרשומים (VE_FAVORITABLE_FIELDS) שיושבים
// בתוך הקטגוריה חוזרים לערך שה-HTML נטען איתו, אחרי אישור (item: אישור עקבי).
async function resetVeCategory(key) {
  const details = _veCategoryByKey(key);
  if (!details) return;
  const title = details.querySelector(".ve-cat-title").textContent;
  const changed = _veChangedFieldsInCategory(details);
  if (!changed.length) { alert(`אין מה לאפס - כל ההגדרות ב"${title}" כבר בברירת המחדל.`); return; }
  const labels = changed.map(k => VE_FAVORITABLE_FIELDS[k].label).join(", ");
  if (!(await veConfirm(`לאפס ${changed.length} הגדרות בקטגוריה "${title}"?\n(${labels})`, {danger: true, okLabel: "↺ אפס קטגוריה"}))) return;
  for (const fieldKey of changed) _resetSingleVeField(document.getElementById(VE_FAVORITABLE_FIELDS[fieldKey].id));
  if (key === "layers") clearWatermarkCustomPosition();
  _veRefreshAllDerivedUi();
}

document.getElementById("veCategories").addEventListener("click", (e) => {
  const btn = e.target.closest(".ve-cat-reset");
  if (!btn) return;
  e.preventDefault();
  e.stopPropagation();
  resetVeCategory(btn.dataset.catReset);
});

function _veFieldChanged(el) {
  if (!el || !_veFieldDefaults || !(el.id in _veFieldDefaults)) return false;
  return el.type === "checkbox" ? el.checked !== _veFieldDefaults[el.id] : String(el.value) !== String(_veFieldDefaults[el.id]);
}

function _veChangedFieldsInCategory(details) {
  const keys = [];
  for (const [key, meta] of Object.entries(VE_FAVORITABLE_FIELDS)) {
    const el = document.getElementById(meta.id);
    if (el && details.contains(el) && !el.closest(".ve-favorite-row") && _veFieldChanged(el)) keys.push(key);
  }
  return keys;
}

// item: תקציר-מצב לקטגוריה + Empty-state - "N הגדרות שונו מברירת המחדל" (מול
// _veFieldDefaults, לא ספירה גולמית של checkbox-ים/שדות-מלאים כמו קודם), או
// כלום כשאין (גל 27). התור מנהל את התקציר של עצמו (_renderVeQueue).
const VE_EMPTY_SUMMARY_TEXT = {favorites: "אין מועדפים עדיין", profiles: "לא נבחר סגנון"};

function updateCategorySummaries() {
  for (const details of _veCategoryEls()) {
    const key = details.dataset.cat;
    const el = details.querySelector(".ve-cat-summary");
    if (!el || key === "queue") continue;
    let text = "";
    if (key === "favorites") {
      const count = _favoriteFieldKeys().length;
      text = count ? `${count} מועדפים` : "";
    } else if (key === "profiles") {
      const personal = _currentVeProfileName();
      const raw = document.getElementById("vePreset").value;
      text = personal ? `פעיל: ${personal}` : (raw ? `מובנה: ${raw}` : "");
    } else {
      const count = _veChangedFieldsInCategory(details).length;
      text = count === 1 ? "הגדרה אחת שונתה" : (count ? `${count} הגדרות שונו` : "");
    }
    // גל 27: בלי "שום דבר לא מופעל כאן" בכל כותרת - כותרת ריקה היא כבר הסימן
    const shown = text || VE_EMPTY_SUMMARY_TEXT[key] || "";
    el.textContent = shown ? " · " + shown : "";
    el.classList.toggle("ve-empty", !text);
    details.classList.toggle("ve-cat-changed", !!text && key !== "favorites" && key !== "profiles");
  }
}

// item: ⚠️ בכותרת קטגוריה + אזהרות live על שילובים בעייתיים - טבלת-חוקים אחת
// שמשקפת בדיוק את ה-"[INFO] ... מתעלם" שהסקריפט עצמו היה מדפיס רק באמצע ריצה
// (video_editor.py) - כאן זה נראה *לפני* שמריצים. field = לאן קליק על האזהרה
// קופץ; level "info" לא מדליק ⚠️ בכותרת (מידע, לא בעיה).
const _veHwFull = (o) => o.hwaccel && o.codec !== "h264";
const _veHasExplicitTrim = (o) => (o.trim_start || 0) > 0 || o.trim_duration !== null && o.trim_duration !== undefined;
const _veHasAudioOut = (o) => o.keep_audio || !!(o.replace_audio_path || "").trim();
// יש שמע במקור (לפי ה-probe של התור) - קודם סרטון עם מוזיקה יצא בשקט בלי שמע (הרצה מקצה לקצה, 16.10)
const _veQueueHasAudio = () => (_veQueueState || []).some(f => f.selected && (_veQueueMeta[state.folder + "|" + f.name] || {}).has_audio);
// מראה של _ANY_CROP_VARIANT בסקריפט (video_editor.py) - האם איזשהו פלט נחתך בכלל.
const _veAnyCropVariant = (o) => o.vertical || o.dual_output || ["9:16", "1:1", "4:5"].includes(o.aspect)
  || (o.aspect === "custom" && (o.custom_height || 0) >= (o.custom_width || 0)) || o.fit === "crop";
const VE_RULES = [
  {cats: ["captions", "audio"], field: "captions", when: o => o.captions && !o.keep_audio, msg: 'כתוביות אוטומטיות דורשות "שמירת אודיו" - בלעדיה לא ייווצרו כתוביות.'},
  {cats: ["captions"], field: "captions_translate", when: o => o.captions_translate && !o.captions, msg: "תרגום כתוביות פעיל בלי כתוביות אוטומטיות - לא ישפיע."},
  {cats: ["audio"], field: "keep_audio", when: o => !_veHasAudioOut(o) && !o.concat_mode && _veQueueHasAudio(), msg: 'בסרטונים שבתור יש שמע (מוזיקה, קול) ו"שמירת אודיו" כבויה - הפלט ייצא בלי שמע.'},
  {cats: ["audio"], field: "loudnorm", when: o => o.loudnorm && !_veHasAudioOut(o), msg: 'נרמול עוצמת קול בלי "שמירת אודיו" - אין אודיו לנרמל.'},
  {cats: ["audio"], field: "noise_gate", when: o => o.noise_gate && !_veHasAudioOut(o), msg: 'שער רעש בלי "שמירת אודיו" - לא ישפיע.'},
  {cats: ["audio"], field: "remove_mid_silence", when: o => o.remove_mid_silence && !_veHasAudioOut(o), msg: 'הסרת שקט באמצע דורשת "שמירת אודיו" (אין ממה לזהות שקט).'},
  {cats: ["audio", "trim"], field: "remove_mid_silence", when: o => o.remove_mid_silence && (_veHasExplicitTrim(o) || o.trim_silence), msg: "הסרת שקט באמצע מתעלמת כשיש חיתוך מפורש או חיתוך-שקט-בקצוות."},
  {cats: ["trim"], field: "trim_silence", when: o => o.trim_silence && _veHasExplicitTrim(o), msg: "חיתוך שקט אוטומטי מתעלם כשיש התחלת/אורך חיתוך מפורשים."},
  {cats: ["trim"], field: "remove_ranges", when: o => !!(o.remove_ranges || "").trim() && (_veHasExplicitTrim(o) || o.trim_silence), msg: "חיתוך כמה טווחים מתעלם כשיש חיתוך מפורש או חיתוך-שקט-בקצוות."},
  {cats: ["resources", "export"], field: "hwaccel", when: o => o.hwaccel && o.codec === "h264", msg: 'פייפליין GPU מלא דורש קידוד HEVC/AV1 - עם H.264 הוא מתעלם (אפשר "פענוח מואץ-GPU" במקום).'},
  {cats: ["resources"], field: "hwaccel_decode", when: o => o.hwaccel_decode && _veHwFull(o), msg: "פענוח מואץ מיותר - הפייפליין המלא כבר כולל אותו.", level: "info"},
  {cats: ["layers", "resources"], field: "pip_path", when: o => !!(o.pip_path || "").trim() && _veHwFull(o), msg: "PiP לא נתמך עם פייפליין GPU מלא - יתעלם."},
  {cats: ["format", "resources"], field: "blur_background", when: o => o.blur_background && _veHwFull(o), msg: "רקע מטושטש לא נתמך עם פייפליין GPU מלא - יתעלם."},
  {cats: ["effects", "resources"], field: "chromakey", when: o => o.chromakey && _veHwFull(o), msg: "כרומה-קי לא נתמך עם פייפליין GPU מלא - יתעלם."},
  {cats: ["effects", "format"], field: "chromakey", when: o => o.chromakey && o.blur_background && !_veHwFull(o), msg: "כרומה-קי מתעלם יחד עם רקע מטושטש (שני אופנים סותרים לבניית הרקע)."},
  {cats: ["effects", "resources"], field: "denoise", when: o => (o.denoise || o.sharpen) && _veHwFull(o), msg: "הפחתת רעש/חידוד מתעלמים עם פייפליין GPU מלא."},
  {cats: ["motion", "resources"], field: "stabilize", when: o => (o.stabilize || o.smooth_fps) && _veHwFull(o), msg: "ייצוב/אינטרפולציה חלקה מתעלמים עם פייפליין GPU מלא."},
  {cats: ["format"], field: "smart_crop", when: o => o.smart_crop && !_veAnyCropVariant(o), msg: "קרופ חכם רלוונטי רק כשהפלט נחתך (אנכי/ריבוע/4:5/fit חיתוך) - יתעלם."},
  {cats: ["format"], field: "smart_crop", when: o => o.smart_crop && o.vertical && o.blur_background, msg: "קרופ חכם מתעלם עם רקע מטושטש (הפריים לא נחתך בכלל)."},
  {cats: ["export"], field: "nvenc_cq", when: o => o.nvenc_cq !== null && o.nvenc_cq !== undefined && !!o.target_size_mb && o.codec !== "h264", msg: "איכות NVENC (CQ) מתעלמת כשיש יעד גודל קובץ."},
  {cats: ["resources"], field: "max_concurrent_nvenc", when: o => o.max_concurrent_nvenc !== null && o.max_concurrent_nvenc !== undefined && (o.parallel || 1) <= 1, msg: "מגבלת NVENC מקבילי רלוונטית רק עם קידוד מקבילי מעל 1.", level: "info"},
  {cats: ["export"], field: "number_videos", when: o => o.number_videos && !!(o.output_template || "").trim() && !o.output_template.includes("{number}"), msg: "המספור לא יופיע בשם הקובץ - הוסף {number} לתבנית השם."},
  {cats: ["export"], field: "no_suffix", when: o => o.no_suffix && (!!(o.output_template || "").trim() || o.number_videos), msg: '"בלי סיומת" מתעלם כשיש תבנית שם או מספור.', level: "info"},
  {cats: ["queue"], field: "concat_mode", when: o => o.concat_mode, msg: "מצב איחוד קטעים: watermark/חיתוך/LUT/כתוביות לא חלים - רק פורמט, קידוד, מיכל, FPS ואודיו.", level: "info"},
  {cats: ["resources"], field: "preview_only", when: o => o.preview_only, msg: "תצוגה מקדימה בלבד - שום סרטון לא ירונדר, רק תמונת contact-sheet.", level: "info"},
  {cats: ["resources"], field: "validate_only", when: o => o.validate_only && !o.preview_only, msg: "בדיקה בלבד - שום סרטון לא ירונדר.", level: "info"},
];

function _veEvaluateRules(opts) {
  const o = opts || _collectRunOptions();
  return VE_RULES.filter(rule => { try { return !!rule.when(o); } catch (e) { return false; } });
}

function _veRenderWarnings(active) {
  const box = document.getElementById("veWarningsBox");
  box.innerHTML = "";
  for (const rule of active) {
    const row = document.createElement("div");
    row.className = "ve-warning " + (rule.level === "info" ? "info" : "warn");
    row.textContent = (rule.level === "info" ? "ℹ️ " : "⚠️ ") + rule.msg;
    row.title = "לחץ כדי לקפוץ להגדרה";
    row.onclick = () => veScrollToField(rule.field);
    box.appendChild(row);
  }
  // גל 27: האזהרות בכפתור בפס הסטטוס התחתון ("⚠️ 2"), והרשימה נפתחת ממנו
  const toggle = document.getElementById("veWarningsToggle");
  const warnCount = active.filter(rule => rule.level !== "info").length;
  toggle.hidden = !active.length;
  toggle.textContent = warnCount ? `⚠️ ${warnCount}` : `ℹ️ ${active.length}`;
  toggle.classList.toggle("ve-has-warn", warnCount > 0);
  if (!active.length) toggle.setAttribute("aria-expanded", "false");
  box.hidden = !active.length || toggle.getAttribute("aria-expanded") !== "true";
  const warnByCat = {};
  for (const rule of active) {
    if (rule.level === "info") continue;
    for (const cat of rule.cats) (warnByCat[cat] = warnByCat[cat] || []).push(rule.msg);
  }
  for (const details of _veCategoryEls()) {
    const warnEl = details.querySelector(".ve-cat-warn");
    const messages = warnByCat[details.dataset.cat] || [];
    warnEl.hidden = !messages.length;
    warnEl.title = messages.join("\n");
  }
}

// item: כרטיס-תקציר קריא בראש הפאנל - "אנכי · קרופ חכם · HEVC · watermark
// ימין-תחתון · 3 קבצים", נבנה מההגדרות עצמן, לצד "⌨️ פקודה" הטכני.
function _veSelectText(id) {
  const el = document.getElementById(id);
  return el && el.selectedIndex >= 0 ? el.options[el.selectedIndex].textContent.replace(/^[^\p{L}\p{N}]+/u, "").trim() : "";
}

function _veBuildSummaryChips(o) {
  const chips = [];
  if (o.concat_mode) chips.push(`🔗 איחוד ${(o.concat_files || []).length} קטעים`);
  // עם יעדים - הצורה של היעד
  const targets = (o.targets || []).map(id => _veSchema && _veSchema.targets[id]).filter(Boolean);
  const shape = targets.length === 1 ? targets[0].fields : o;
  if (targets.length > 1) chips.push(`🎯 ${targets.length} יעדים`);
  else chips.push(shape.aspect === "1:1" ? "⬛ 1:1" : shape.vertical ? "📱 אנכי 9:16" : "🖥️ אופקי 16:9");
  if (o.preserve_resolution) chips.push("רזולוציית מקור");
  if (o.vertical && o.smart_crop && !o.blur_background) chips.push(o.smart_crop_face ? "🎯 קרופ לפי פנים" : "🎯 קרופ חכם");
  if (o.blur_background) chips.push("🌫️ רקע מטושטש");
  const codecLabel = {h264: "H.264", hevc: "HEVC", av1: "AV1"}[o.codec] || o.codec;
  chips.push(`🎬 ${codecLabel}${o.container === "mkv" ? " · MKV" : ""}`);
  if (_veHwFull(o)) chips.push("🚀 GPU מלא"); else if (o.hwaccel_decode) chips.push("⚡ NVDEC");
  if (o.target_size_mb) chips.push(`🎯 ${o.target_size_mb}MB`);
  if ((o.watermark_path || "").trim()) chips.push("🖼️ watermark " + (o.watermark_x !== null && o.watermark_x !== undefined ? "מיקום מותאם" : _veSelectText("veWatermarkPosition")));
  if ((o.remove_watermark_region || "").trim()) chips.push("🧽 מחיקת לוגו (אזור מותאם)");
  else if (o.remove_watermark_position) chips.push("🧽 מחיקת לוגו ישן");
  if (o.include_subfolders === false) chips.push("📁 בלי תתי-תיקיות");
  if ((o.pip_path || "").trim()) chips.push("📺 PiP");
  if ((o.text || "").trim()) chips.push(`🔤 "${o.text.trim().slice(0, 18)}"`);
  if (_veHasExplicitTrim(o)) chips.push("✂️ חיתוך");
  if (o.trim_silence) chips.push("🔇 חיתוך שקט");
  if ((o.remove_ranges || "").trim()) chips.push("✂️ טווחים");
  if ((o.target_seconds || 0) > 0) chips.push(`⏩ טיימלאפס ${o.target_seconds}s`);
  if ((o.fade_in_seconds || 0) > 0 || (o.fade_out_seconds || 0) > 0) chips.push("🌓 fade");
  if ((o.lut_path || "").trim()) chips.push("🎨 LUT");
  if (o.auto_levels) chips.push("בהירות אוטומטית");
  if (o.denoise) chips.push("הפחתת רעש");
  if (o.sharpen) chips.push("חידוד");
  if (o.chromakey) chips.push("🟩 כרומה-קי");
  if ((o.fps || "").trim()) chips.push(`🎞️ ${o.fps}fps`);
  if (o.stabilize) chips.push("ייצוב");
  if ((o.replace_audio_path || "").trim()) chips.push("🎵 פס קול חלופי");
  else chips.push(o.keep_audio ? (o.loudnorm ? "🔊 אודיו מנורמל" : "🔊 אודיו") : "🔇 בלי אודיו");
  if (o.captions && o.keep_audio) chips.push(o.captions_translate ? "💬 כתוביות (EN)" : "💬 כתוביות");
  if (o.number_videos) chips.push(`#️⃣ ${o.number_prefix || "Clip"} #N`);
  if ((o.parallel || 1) > 1) chips.push(`×${o.parallel} במקביל`);
  if (o.force) chips.push("🔁 רנדר מחדש");
  if (o.preview_only) chips.push("🖼️ תצוגה מקדימה בלבד");
  else if (o.validate_only) chips.push("🧪 בדיקה בלבד");
  // מספר הקבצים מוצג פעם אחת - בשבב #veFileCount שבפס הסטטוס (גל 27)
  return chips;
}

function _veRenderSummaryCard(opts) {
  const o = opts || _collectRunOptions();
  const box = document.getElementById("veSummaryText");
  box.innerHTML = "";
  const chips = _veBuildSummaryChips(o);
  box.title = chips.join(" · ");  // בפס הסטטוס הצר - הרשימה המלאה בריחוף
  for (const chip of chips) {
    const span = document.createElement("span");
    span.className = "ve-summary-chip";
    span.textContent = chip;
    box.appendChild(span);
  }
}

// item: מספר קבצים בתור בפס הצף - לפי התור אם נערך, אחרת ספירת קבצי הווידאו
// בתיקיית השורש (תתי-תיקיות מוצגות בנפרד - הן תמיד מעובדות במלואן).
let _veFolderCounts = null;

function _veFileCountText() {
  if (document.getElementById("veConcatMode").checked && _veQueueState.length) {
    return `📁 ${_veConcatFiles().length} קטעים לאיחוד`;
  }
  if (_veQueueDirty && _veQueueState.length) {
    return `📁 ${_veQueueState.filter(f => f.selected).length}/${_veQueueState.length} קבצים`;
  }
  if (!_veFolderCounts) return "";
  const sub = _veFolderCounts.folders ? ` (+${_veFolderCounts.folders} תתי-תיקיות)` : "";
  return `📁 ${_veFolderCounts.files} קבצים${sub}`;
}

async function _veRefreshFolderCounts() {
  _veFolderCounts = null;
  if (!state.folder) { _veRenderFileCount(); return; }
  try {
    const res = await fetch("/api/browse?path=" + encodeURIComponent(state.folder));
    const data = await res.json();
    if (!data.error) {
      _veFolderCounts = {
        files: (data.files || []).filter(f => VE_VIDEO_EXTENSIONS.some(ext => f.name.toLowerCase().endsWith(ext))).length,
        folders: (data.folders || []).length,
      };
    }
  } catch (e) { /* תיקייה לא נגישה - פשוט בלי ספירה */ }
  _veRenderFileCount();
}

function _veRenderFileCount() {
  const el = document.getElementById("veFileCount");
  const text = _veFileCountText();
  el.hidden = !text;
  el.textContent = text;
}

// item: כפתור "▶ הרץ" בפס הצף - משקף את מצב כפתורי ההרצה/עצירה הראשיים דרך
// MutationObserver על disabled, כך שכל מסלול קוד שמשנה אותם (הרצה/סיום/WS/
// בחירת סקריפט) מתעדכן כאן אוטומטית, בלי לגעת בכל אחד מהם בנפרד.
function _veMirrorRunButtons() {
  const pairs = [["runBtn", "veStickyRunBtn"], ["stopBtn", "veStickyStopBtn"]];
  for (const [sourceId, mirrorId] of pairs) {
    const source = document.getElementById(sourceId);
    const mirror = document.getElementById(mirrorId);
    mirror.disabled = source.disabled;
    new MutationObserver(() => { mirror.disabled = source.disabled; }).observe(source, {attributes: true, attributeFilter: ["disabled"]});
  }
}

// רענון כל ה-UI הנגזר (תקצירים/אזהרות/כרטיס/תלויות) - debounced (item:
// debounce לחישובים על כל הקלדה), לא על כל תו בנפרד.
function _veRefreshAllDerivedUi() {
  uiBus.emit("ve:derived-refresh");
  uiDebounce("ve:derived-ui", () => {
    if (document.getElementById("videoEditorOptions").hidden) return;
    const opts = _collectRunOptions();
    _veUpdateDependentRows();
    _veRenderWarnings(_veEvaluateRules(opts));
    _veRenderSummaryCard(opts);
    _veRenderFileCount();
    updateCategorySummaries();
    _veRenderCategoryTabs();
    if (typeof _veRenderTimelineOverlays === "function" && _veTimelineOverlaysChanged(opts)) _veRenderTimelineOverlays();
  }, 150);
}

// 25.10.2026: הרענון התקופתי (כל 1.5 שניות) בנה מחדש את טווחי ההסרה ואת פסי השכבות בציר הזמן גם כשלא השתנה בהם
// כלום - לחיצה או גרירה שהתחילה על פס שהוחלף באותו רגע הלכה לאיבוד. מציירים רק כשמשהו שהציר מציג השתנה
// (קריאה ישירה ל-_veRenderTimelineOverlays - לחיצה על הציר, שינוי שכבות - מציירת תמיד, כמו קודם)
let _veOverlaysKey = null;
let _veOverlaysTimeline = null;
function _veTimelineOverlaysChanged(opts) {
  const markers = typeof _veHighlightMarkers !== "undefined" && _veHighlightMarkers ? [_veHighlightMarkers.file, _veHighlightMarkers.peaks] : null;
  const cursor = typeof _veTimelineCursor !== "undefined" ? _veTimelineCursor : null;
  const preview = document.getElementById("vePreviewFile");
  const key = JSON.stringify([opts, cursor, markers, preview ? preview.value : ""]);
  const timeline = typeof _veTimeline !== "undefined" ? _veTimeline : null;
  if (key === _veOverlaysKey && timeline === _veOverlaysTimeline) return false;
  _veOverlaysKey = key;
  _veOverlaysTimeline = timeline;
  return true;
}

// דרך השם (לא הפניה לפונקציה) - כך שגם עטיפות מגלים מאוחרים (סימון שורות ששונו,
// כרטיסי שכבות, שמירת פרויקט אוטומטית) רצות על כל שינוי של המשתמש.
document.getElementById("videoEditorOptions").addEventListener("input", () => _veRefreshAllDerivedUi());
document.getElementById("videoEditorOptions").addEventListener("change", () => _veRefreshAllDerivedUi());

// item: קיצורי מקלדת - Ctrl+S (עדכן/שמור פרופיל), Ctrl+Enter (הרץ), "/" (חיפוש),
// "?" (רשימת הקיצורים). "/" ו-"?" לא נחטפים כשמקלידים בתוך שדה טקסט.
function _veIsTyping() {
  const active = document.activeElement;
  return !!active && (active.tagName === "TEXTAREA" || active.tagName === "SELECT" || (active.tagName === "INPUT" && !["checkbox", "radio", "range", "button"].includes(active.type)) || active.isContentEditable);
}

document.addEventListener("keydown", (e) => {
  if (!_veIsActive()) return;
  const key = e.key.toLowerCase();
  if ((e.ctrlKey || e.metaKey) && key === "s") {
    e.preventDefault();
    if (_isPersonalProfileSelected()) updateVideoEditorProfile(); else saveVideoEditorProfile();
  } else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    if (document.getElementById("veRunSheetBg").classList.contains("show")) confirmVeRunSheet(); else requestVeRun();
  } else if (e.key === "/" && !_veIsTyping() && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    // גל 33: החיפוש יושב בתוך המפקח - פס מקופל נפתח קודם
    if (document.getElementById("videoEditorOptions").classList.contains("ve-inspector-rail")) setVePanelRail("inspector", false);
    const search = document.getElementById("veSearchInput");
    search.focus(); search.select();
  } else if (e.key === "?" && !_veIsTyping()) {
    e.preventDefault();
    openVeShortcutsDialog();
  }
});

function openVeShortcutsDialog() {
  _veRenderShortcuts();  // גל 31: נבנית מרשימה אחת (VE_SHORTCUTS)
  document.getElementById("veShortcutsModalBg").classList.add("show");
}
function closeVeShortcutsDialog() { document.getElementById("veShortcutsModalBg").classList.remove("show"); }

// item: לוח פקודות Ctrl+K - בעורך-העל הלוח כולל גם פעולות, קטגוריות, שדות
// ופרופילים (לא רק סקריפטים), עם ניווט מקלדת ↑/↓/Enter.
function _vePaletteEntries() {
  const entries = [];
  const add = (section, label, run) => entries.push({section, label, run});
  if (_veIsActive()) {
    add("⚡ פעולות", "▶ הרץ עכשיו", requestVeRun);
    add("⚡ פעולות", "💾 שמור כסגנון חדש", saveVideoEditorProfile);
    if (_isPersonalProfileSelected()) add("⚡ פעולות", "🔄 עדכן את הסגנון הנבחר", updateVideoEditorProfile);
    add("⚡ פעולות", "⌨️ הצג את הפקודה שתישלח", openCommandPreviewDialog);
    add("⚡ פעולות", "📖 מקראה", openGlossaryDialog);
    add("⚡ פעולות", "🔍 חפש הגדרה", () => document.getElementById("veSearchInput").focus());
    add("⚡ פעולות", "📋 רענן את תור העיבוד", () => { veScrollToCategory("queue"); refreshVeQueue(); });
    add("⚡ פעולות", "↺ אפס הכל לברירת מחדל", resetVideoEditorToDefaults);
    add("⚡ פעולות", "⏬ הרחב/כווץ את כל הקטגוריות", toggleAllVeCategories);
    add("⚡ פעולות", "🛟 שחזר סגנונות מגיבוי", openProfileBackupsDialog);
    add("⚡ פעולות", "🗑️ סל מחזור לסגנונות", openProfileTrashDialog);
    add("⚡ פעולות", "🔍 השווה סגנונות", openCompareProfilesDialog);
    add("⚡ פעולות", "🗂️ הגדרות בלשוניות", () => setVeLayout("tabs"));
    add("⚡ פעולות", "☰ כל ההגדרות ברשימה", () => setVeLayout("accordion"));
    add("⚡ פעולות", "⌨️ קיצורי מקלדת", openVeShortcutsDialog);
    for (const details of _veCategoryEls()) {
      add("📂 קטגוריות", details.querySelector(".ve-cat-title").textContent, () => veScrollToCategory(details.dataset.cat));
    }
    for (const name of Object.keys(state.videoEditorProfiles || {})) {
      add("🗂️ סגנונות", name, () => { document.getElementById("vePreset").value = "profile:" + name; applyVideoEditorPreset(); });
    }
    for (const [key, meta] of Object.entries(VE_FAVORITABLE_FIELDS)) {
      add("⚙️ הגדרות", meta.label, () => veScrollToField(key));
    }
  }
  // גל 22: מסכים/מערכת/ערכות נושא וכו' מגיעים מספקים רשומים (uiPaletteProviders), לפני הסקריפטים
  for (const provider of uiPaletteProviders) entries.push(...provider());
  for (const s of state.scripts) add("🎮 סקריפטים", s.name, () => selectScript(s.id));
  return entries;
}

let _vePaletteVisible = [];

function _renderPaletteList(query) {
  const q = (query || "").toLowerCase().trim();
  const list = document.getElementById("paletteList");
  list.innerHTML = "";
  // גל 31: פקודות שמבצעות ("קודק hevc", "הוסף לוגו") בראש הרשימה
  const commands = _veIsActive() ? _vePaletteCommands(query) : [];
  _vePaletteVisible = [...commands, ..._vePaletteEntries().filter(entry => !q || entry.label.toLowerCase().includes(q) || entry.section.toLowerCase().includes(q))].slice(0, 80);
  let lastSection = null;
  _vePaletteVisible.forEach((entry, index) => {
    if (entry.section !== lastSection) {
      const header = document.createElement("div");
      header.className = "ve-palette-section";
      header.textContent = entry.section;
      list.appendChild(header);
      lastSection = entry.section;
    }
    const row = document.createElement("div");
    row.textContent = entry.label;
    row.dataset.paletteIndex = String(index);
    if (index === 0) row.classList.add("ve-palette-active");
    row.onclick = () => { closeCommandPalette(); entry.run(); };
    list.appendChild(row);
  });
}

document.getElementById("paletteInput").addEventListener("keydown", (e) => {
  const rows = Array.from(document.querySelectorAll("#paletteList div[data-palette-index]"));
  if (!rows.length) return;
  let index = rows.findIndex(r => r.classList.contains("ve-palette-active"));
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    index = e.key === "ArrowDown" ? Math.min(rows.length - 1, index + 1) : Math.max(0, index - 1);
    rows.forEach(r => r.classList.remove("ve-palette-active"));
    rows[index].classList.add("ve-palette-active");
    rows[index].scrollIntoView({block: "nearest"});
  } else if (e.key === "Enter") {
    e.preventDefault();
    (rows[Math.max(0, index)]).click();
  }
});

// קפיצה לקטגוריה/שדה שמכבדת טאבים/חיפוש/חשיפה-מדורגת: מבטלת חיפוש שמסתיר את
// היעד, עוברת לטאב שלו, ופותחת את הקטגוריה.
function _veRevealElement(el) {
  if (!el) return null;
  // גל 30: במצב פשוט אזורי ההגדרות מוסתרים (ארבעה צעדים) - קפיצה לשדה עוברת למתקדם
  // גל 34: וגם ב"רגיל" - כששדה היעד הוא מההגדרות הנדירות
  const root = document.getElementById("videoEditorOptions");
  if (el.closest("#veCategories") && (root.classList.contains("ve-simple") || (root.classList.contains("ve-regular") && el.closest(".ve-rare")))) setVeMode("advanced");
  if (_veSearchActive() && el.closest(".ve-search-hidden")) {
    document.getElementById("veSearchInput").value = "";
    onVeSearchInput();
  }
  const details = el.closest("details.ve-category");
  if (details) {
    if (_veCurrentLayout() === "tabs") _veActivateTab(details.dataset.cat);
    details.open = true;
  }
  const depRow = el.closest(".ve-dep-hidden");
  if (depRow) { depRow.classList.remove("ve-dep-hidden"); depRow.classList.add("ve-dep-dim"); }
  const collapsed = el.closest(".ve-subcat.ve-subcat-collapsed");
  if (collapsed && collapsed !== el) _veSetSubcatOpen(collapsed, true);
  return details;
}

function _veInitOrganization() {
  setVeCompact(_veLoadPref("veCompact", false));
  document.getElementById("veShowDependentToggle").checked = _veLoadPref("veShowDependent", false);
  _setupVeCategoryDragAndKeys();
  _veApplyCategoryOrder();
  _veApplyLayout();
  _veMirrorRunButtons();
  _veUpdateDependentRows();
  // גל 31: שינוי גובה הפאנל בגרירת הפינה היה של הפריסה בתוך עמוד הסקריפטים. בסטודיו הלחיצה בפס
  // התחתון הסירה את הגובה המרבי, הפס זז בין הלחיצה לשחרור - והלחיצה (למשל על ⚠️) הלכה לאיבוד.
}

