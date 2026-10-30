// ============================================================================
// גל 9 של 102-ההצעות: איכות, נגישות ובדיקות (items 97-102)
// ============================================================================

// --- item 98: aria לכל שדה/סליידר + תפקידי דיאלוג ---
function _veAccessibleName(el) {
  if (el.getAttribute("aria-label") || el.getAttribute("aria-labelledby") || el.closest("label")) return true;
  return !!(el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`));
}

function _veApplyAria(root) {
  const scope = root || document.getElementById("videoEditorOptions");
  for (const el of scope.querySelectorAll("input:not([type=hidden]), select, textarea")) {
    if (_veAccessibleName(el)) continue;
    const row = el.closest(".ve-row");
    const label = row && row.querySelector("label");
    let text = (label ? label.textContent : "").replace(/[:↳]/g, "").replace(/\s+/g, " ").trim();
    const siblings = row ? row.querySelectorAll("input:not([type=hidden]):not([type=color]), select, textarea").length : 1;
    if (siblings > 1 && (el.placeholder || el.type === "color")) text = `${text} - ${el.type === "color" ? "בורר צבע" : el.placeholder}`;
    if (!text) text = el.placeholder || el.title || el.id;
    if (text) el.setAttribute("aria-label", text);
  }
  for (const sub of scope.querySelectorAll(".ve-subcat")) {
    const title = sub.querySelector(".ve-subcat-title");
    sub.setAttribute("role", "group");
    if (!title) continue;
    // שם הקבוצה בלבד - בלי תוויות הכפתורים שיושבים בכותרת (טען/התאם/⟳...)
    const name = title.cloneNode(true);
    name.querySelectorAll("button, select, input, .ve-field-msg").forEach(node => node.remove());
    sub.setAttribute("aria-label", name.textContent.replace(/\s+/g, " ").trim());
  }
  _veUpdateRangeAria(scope);
}

function _veUpdateRangeAria(scope) {
  for (const range of (scope || document).querySelectorAll("input[type=range]")) {
    const text = _veFormatRangeValue(range);
    if (text) range.setAttribute("aria-valuetext", text);
  }
}

const _veRefreshRangeLabelsBeforeWave9 = _veRefreshRangeLabels;
_veRefreshRangeLabels = function () {
  _veRefreshRangeLabelsBeforeWave9();
  _veUpdateRangeAria(document.getElementById("videoEditorOptions"));
};

function _veApplyDialogRoles() {
  let n = 0;
  for (const modal of document.querySelectorAll(".modal-bg > .modal")) {
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    const title = modal.querySelector("h3");
    if (title) {
      if (!title.id) title.id = `veDialogTitle${++n}`;
      modal.setAttribute("aria-labelledby", title.id);
    }
  }
}

// --- item 99: bottom-sheet לקטגוריות במובייל ---
const _veSheetQuery = window.matchMedia("(max-width: 700px)");
// מצב פתוח/סגור של ה-HTML עצמו - כדי שחזרה ממובייל למחשב תחזיר את ברירת-המחדל
const _veDefaultCategoryOpen = Object.fromEntries(_veCategoryEls().map(d => [d.dataset.cat, d.hasAttribute("open")]));

function _veSheetModeActive() {
  return _veSheetQuery.matches && _veCurrentLayout() !== "tabs";
}

function _veApplySheetMode() {
  const active = _veSheetModeActive();
  const wasActive = document.body.classList.contains("ve-sheets");
  document.body.classList.toggle("ve-sheets", active);
  if (active && !wasActive) {
    // נכנסים למצב גיליונות: הכל סגור, קטגוריה נפתחת בנגיעה (בלי לדרוס את המצב השמור של המחשב)
    _veOpenStateSuppressed = true;
    for (const details of _veCategoryEls()) details.open = false;
    setTimeout(() => { _veOpenStateSuppressed = false; }, 0);
  } else if (!active && wasActive) {
    _veOpenStateSuppressed = true;
    for (const details of _veCategoryEls()) details.open = !!_veDefaultCategoryOpen[details.dataset.cat];
    setTimeout(() => { _veOpenStateSuppressed = false; }, 0);
    _veApplyCategoryOpenState();
  }
  _veSyncSheetBackdrop();
}

function _veSyncSheetBackdrop() {
  const anyOpen = document.body.classList.contains("ve-sheets") && _veCategoryEls().some(d => d.open);
  document.getElementById("veSheetBackdrop").classList.toggle("show", anyOpen);
}

function closeVeSheets() {
  _veOpenStateSuppressed = true;
  for (const details of _veCategoryEls()) details.open = false;
  setTimeout(() => { _veOpenStateSuppressed = false; }, 0);
  _veSyncSheetBackdrop();
}

(function _veSetupSheets() {
  const backdrop = document.createElement("div");
  backdrop.id = "veSheetBackdrop"; backdrop.className = "ve-sheet-backdrop";
  backdrop.onclick = closeVeSheets;
  document.body.appendChild(backdrop);
  for (const details of _veCategoryEls()) {
    const body = details.querySelector(":scope > .ve-category-body");
    if (!body || body.querySelector(":scope > .ve-sheet-close")) continue;
    const close = document.createElement("button");
    close.type = "button"; close.className = "ve-sheet-close";
    close.textContent = "▾ " + (details.querySelector(".ve-cat-title") || {}).textContent;
    close.setAttribute("aria-label", "סגור את הקטגוריה");
    close.onclick = () => { details.open = false; _veSyncSheetBackdrop(); };
    body.prepend(close);
  }
  document.getElementById("veCategories").addEventListener("toggle", (e) => {
    const details = e.target;
    if (!details.matches || !details.matches("details.ve-category[data-cat]") || !document.body.classList.contains("ve-sheets")) return;
    if (details.open && !_veSearchActive()) {
      for (const other of _veCategoryEls()) if (other !== details && other.open) other.open = false;
    }
    _veSyncSheetBackdrop();
  }, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && document.body.classList.contains("ve-sheets")) closeVeSheets(); });
  _veSheetQuery.addEventListener("change", _veApplySheetMode);
})();

// שורות מועדפים נבנות מחדש דינמית (שכפולי שדות) - מקבלות aria מיד אחרי כל בנייה
const _rebuildFavoritesBoxBeforeWave9 = rebuildFavoritesBox;
rebuildFavoritesBox = function () {
  _rebuildFavoritesBoxBeforeWave9.apply(this, arguments);
  const box = document.getElementById("veFavoritesBox");
  if (box) _veApplyAria(box);
};

const _veApplyLayoutBeforeWave9 = _veApplyLayout;
_veApplyLayout = function () {
  _veApplyLayoutBeforeWave9();
  if (typeof _veApplySheetMode === "function") _veApplySheetMode();
};

// --- item 100: מתג אנגלית לתוויות ולהסברים ---
let _veEnglishData = null;

async function setVeEnglish(on) {
  _veSavePref("veEnglish", !!on);
  document.getElementById("veEnglishToggle").checked = !!on;
  if (on && !_veEnglishData) {
    try { _veEnglishData = await (await fetch("/api/video_editor/field_help_en")).json(); }
    catch (e) { return; }
  }
  _veApplyLanguage(!!on);
}

function _veLabelTextNodes(label) {
  return [...label.childNodes].filter(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
}

function _veApplyLanguage(english) {
  const panel = document.getElementById("videoEditorOptions");
  panel.lang = english ? "en" : "he";
  const done = new Set();
  const fields = (_veEnglishData && _veEnglishData.fields) || {};
  for (const [key, meta] of Object.entries(VE_FAVORITABLE_FIELDS)) {
    const el = document.getElementById(meta.id);
    if (!el || el.closest(".ve-favorite-row")) continue;
    const label = el.closest("label") || (el.closest(".ve-row") && el.closest(".ve-row").querySelector("label"));
    if (!label || done.has(label)) continue;
    done.add(label);
    const nodes = _veLabelTextNodes(label);
    if (!nodes.length) continue;
    if (label.dataset.veHe === undefined) label.dataset.veHe = JSON.stringify({texts: nodes.map(n => n.textContent), title: label.title});
    const original = JSON.parse(label.dataset.veHe);
    if (english && fields[key]) {
      const first = original.texts[0];
      const lead = first.match(/^\s*(↳\s*)?/)[0];
      const colon = /:\s*$/.test(original.texts[original.texts.length - 1]) ? ":" : "";
      nodes.forEach((node, i) => { node.textContent = i === 0 ? `${lead}${el.closest("label") === label ? " " : ""}${fields[key].term}${colon}` : ""; });
      label.title = fields[key].tooltip;
      label.dir = "ltr";  // נקודתיים/סוגריים במקום הנכון בטקסט אנגלי בתוך עמוד RTL
    } else if (!english) {
      nodes.forEach((node, i) => { if (original.texts[i] !== undefined) node.textContent = original.texts[i]; });
      label.title = original.title;
      label.removeAttribute("dir");
    }
  }
  const categories = (_veEnglishData && _veEnglishData.categories) || {};
  for (const details of _veCategoryEls()) {
    const title = details.querySelector(".ve-cat-title");
    if (!title) continue;
    if (title.dataset.veHe === undefined) title.dataset.veHe = title.textContent;
    title.textContent = english && categories[details.dataset.cat] ? categories[details.dataset.cat] : title.dataset.veHe;
    const sheetClose = details.querySelector(":scope > .ve-category-body > .ve-sheet-close");
    if (sheetClose) sheetClose.textContent = "▾ " + title.textContent;
  }
}

// --- item 101: lazy-render - תוכן כבד של קטגוריה נבנה רק כשהיא נפתחת לראשונה ---
const VE_LAZY_CATEGORY_INIT = {runs: () => loadVeRuns()};
const _veLazyDone = new Set();

function _veRunLazyInit(details) {
  const key = details.dataset.cat;
  if (!details.open || _veLazyDone.has(key) || !VE_LAZY_CATEGORY_INIT[key]) return;
  _veLazyDone.add(key);
  VE_LAZY_CATEGORY_INIT[key]();
}

document.getElementById("veCategories").addEventListener("toggle", (e) => {
  if (e.target.matches && e.target.matches("details.ve-category[data-cat]")) _veRunLazyInit(e.target);
}, true);

