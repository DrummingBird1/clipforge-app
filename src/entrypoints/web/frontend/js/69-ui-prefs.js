// ==========================================================================
// גל 21 - העדפות תצוגה: ערכת נושא (אוטומטי לפי המערכת / כהה / בהירה / ניגודיות
// גבוהה), צבע הדגשה ושפת ממשק (עברית / English). הכל per-viewer (localStorage),
// כמו ערכת הנושא הקודמת - כל דפדפן/מכשיר בוחר לעצמו.
//
// אנגלית: המקור נשאר עברית ב-HTML/JS. המילון (/api/ui_strings/en, מפתח = הטקסט
// בלי אימוג'י מוביל) מוחל על צמתי הטקסט ועל title/placeholder/aria-label, ו-
// MutationObserver מתרגם גם כל מה ש-JS כותב אחר כך. המקור נשמר לכל צומת, כך
// שחזרה לעברית משחזרת בדיוק (רק אם האפליקציה לא כתבה שם משהו חדש בינתיים).
// ==========================================================================

const UI_THEMES = ["auto", "dark", "light", "contrast"];
const UI_ACCENTS = ["cyan", "emerald", "violet", "amber", "rose"];
const _uiMedia = query => (window.matchMedia ? window.matchMedia(query) : null);
const _uiSystemLight = _uiMedia("(prefers-color-scheme: light)");
const _uiSystemContrast = _uiMedia("(prefers-contrast: more)");

function _uiPrefGet(key, fallback) {
  try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; }
}

function _uiPrefSet(key, value) {
  try { localStorage.setItem(key, value); } catch (e) { /* private mode - לא קריטי */ }
}

function _uiResolveTheme(pref) {
  if (pref !== "auto") return pref;
  if (_uiSystemContrast && _uiSystemContrast.matches) return "contrast";
  return _uiSystemLight && _uiSystemLight.matches ? "light" : "dark";
}

function setUiTheme(pref) {
  if (!UI_THEMES.includes(pref)) pref = "dark";
  _uiPrefSet("web_app_theme", pref);
  document.documentElement.dataset.themePref = pref;
  applyTheme(_uiResolveTheme(pref));
  _uiSyncPrefsMenu();
}

function _uiOnSystemThemeChange() {
  if (document.documentElement.dataset.themePref === "auto") applyTheme(_uiResolveTheme("auto"));
}
for (const media of [_uiSystemLight, _uiSystemContrast]) {
  if (media && media.addEventListener) media.addEventListener("change", _uiOnSystemThemeChange);
}

function setUiAccent(name) {
  if (!UI_ACCENTS.includes(name)) name = "cyan";
  _uiPrefSet("uiAccent", name);
  const root = document.documentElement;
  root.dataset.accent = name;
  // בחירה מפורשת כאן גוברת על צבע ה-GUI השולחני שמוחל חי (_applyAccentLive)
  root.style.removeProperty("--brand");
  root.style.removeProperty("--brand-strong");
  _uiSyncPrefsMenu();
}

const _applyAccentLiveBeforePrefs = _applyAccentLive;
_applyAccentLive = function () {
  if (document.documentElement.dataset.accent) return;
  _applyAccentLiveBeforePrefs();
};

// --- תפריט ההעדפות (כפתור ערכת הנושא בסרגל העליון) ---
function _uiSyncPrefsMenu() {
  const root = document.documentElement;
  const current = {
    "data-theme-opt": root.dataset.themePref || "dark",
    "data-accent-opt": root.dataset.accent || "cyan",
    "data-lang-opt": _uiLang,
  };
  for (const [attr, value] of Object.entries(current)) {
    for (const btn of document.querySelectorAll(`#uiPrefsMenu [${attr}]`)) {
      btn.setAttribute("aria-checked", String(btn.getAttribute(attr) === value));
    }
  }
}

function toggleUiPrefsMenu(open) {
  const menu = document.getElementById("uiPrefsMenu");
  const btn = document.getElementById("themeToggle");
  const show = open === undefined ? menu.hidden : !!open;
  menu.hidden = !show;
  btn.setAttribute("aria-expanded", String(show));
  if (show) {
    // מתחת לכפתור עצמו - במובייל שורת הכפתורים נשברת לשורה שנייה
    menu.style.setProperty("--prefs-top", `${Math.round(btn.getBoundingClientRect().bottom + 6)}px`);
    _uiSyncPrefsMenu();
    (menu.querySelector('[aria-checked="true"]') || menu.querySelector("button")).focus();
  }
}

document.addEventListener("click", event => {
  const menu = document.getElementById("uiPrefsMenu");
  if (!menu || menu.hidden || event.target.closest("#uiPrefsMenu, #themeToggle")) return;
  toggleUiPrefsMenu(false);
});

document.addEventListener("keydown", event => {
  const menu = document.getElementById("uiPrefsMenu");
  if (!menu || menu.hidden) return;
  if (event.key === "Escape") {
    event.stopPropagation();
    toggleUiPrefsMenu(false);
    document.getElementById("themeToggle").focus();
    return;
  }
  // חיצים בתוך קבוצת radio - כמו radiogroup רגיל
  const group = event.target.closest('#uiPrefsMenu [role="radiogroup"]');
  if (!group || !["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
  const items = [...group.querySelectorAll('[role="radio"]')];
  const forward = event.key === "ArrowDown" || event.key === (getComputedStyle(group).direction === "rtl" ? "ArrowLeft" : "ArrowRight");
  const next = items[(items.indexOf(event.target) + (forward ? 1 : items.length - 1)) % items.length];
  event.preventDefault();
  next.focus();
  next.click();
}, true);

// --- שפת ממשק ---
let _uiLang = "he";
let _uiDict = null;
let _uiI18nObserver = null;
const _uiTranslatedText = new Map();   // צומת טקסט -> {orig, out}
const _uiTranslatedAttrs = new Map();  // אלמנט -> {attr: {orig, out}}
const _UI_I18N_ATTRS = ["title", "placeholder", "aria-label"];
const _UI_I18N_SKIP = "script, style, textarea, pre, code, .console, [data-no-i18n]";
const _UI_HEBREW = /[\u0590-\u05FF]/;
const _UI_LEAD = /^[\s\u00B7\p{Extended_Pictographic}\u2190-\u21FF\u2300-\u23FF\u25A0-\u25FF\u2600-\u27BF\u27F0-\u27FF\u2B00-\u2BFF\uFE0F\u200D]*/u;
const _UI_TRAIL = /[\s\p{Extended_Pictographic}\u2190-\u21FF\u2300-\u23FF\u25A0-\u25FF\u2600-\u27BF\u27F0-\u27FF\u2B00-\u2BFF\uFE0F\u200D]*$/u;
const _UI_SPLITTERS = [/(\s*\n\s*)/, /( · )/, /( - )/, /( \/ )/, /(\s*\p{Extended_Pictographic}[\uFE0F\u200D\p{Extended_Pictographic}]*\s*)/u];

async function _uiLoadDict(lang) {
  const data = await (await fetch(`/api/ui_strings/${lang}`)).json();
  data._patterns = (data.patterns || []).map(([source, replacement]) => [new RegExp(source, "g"), replacement]);
  return data;
}

function uiTranslate(text) {
  if (!_uiDict || !text || !_UI_HEBREW.test(text)) return null;
  const lead = text.match(_UI_LEAD)[0];
  const trail = text.slice(lead.length).match(_UI_TRAIL)[0];
  const core = text.slice(lead.length, text.length - trail.length);
  const out = _uiTranslateCore(core);
  return out === null ? null : lead + out + trail;
}

function _uiTranslateCore(core) {
  if (!core) return null;
  const hit = _uiDict.exact[core];
  if (hit !== undefined) return hit;
  // תוויות שהועתקו בלי הנקודתיים (aria-label שנבנה מ-<label>)
  const withColon = _uiDict.exact[core + ":"];
  if (withColon !== undefined) return withColon.replace(/:\s*$/, "");
  const split = _uiTranslateParts(core);
  if (split !== null) return split;
  let out = core;
  for (const [pattern, replacement] of _uiDict._patterns) out = out.replace(pattern, replacement);
  if (out === core) return null;
  // תבנית שהשאירה עברית בתוך חלק שנלכד (למשל " · עוד 2 בתור" בסוף הודעה) - מתרגמים גם אותו
  if (_UI_HEBREW.test(out)) return _uiTranslateParts(out) ?? out;
  return out;
}

// טקסט מורכב: שורות, " · ", " - ", " / " או אימוג'י באמצע - כל חלק בנפרד
function _uiTranslateParts(text) {
  for (const splitter of _UI_SPLITTERS) {
    const parts = text.split(splitter);
    if (parts.length < 3) continue;
    const done = parts.map((part, i) => (i % 2 || !_UI_HEBREW.test(part) ? part : uiTranslate(part)));
    if (done.every(part => part !== null)) return done.join("");
  }
  return null;
}

function _uiSkipped(el) {
  return !el || !!el.closest(_UI_I18N_SKIP);
}

function _uiTranslateTextNode(node) {
  if (_uiSkipped(node.parentElement)) return;
  const text = node.nodeValue;
  const out = uiTranslate(text);
  if (out === null || out === text) return;
  _uiTranslatedText.set(node, {orig: text, out});
  node.nodeValue = out;
}

function _uiTranslateAttrs(el) {
  // התוכן של textarea/לוג לא מתורגם, אבל ה-placeholder/aria-label שלהם כן
  if (_uiSkipped(el.parentElement) || el.hasAttribute("data-no-i18n")) return;
  for (const attr of _UI_I18N_ATTRS) {
    const value = el.getAttribute(attr);
    const out = value && uiTranslate(value);
    if (!out || out === value) continue;
    if (!_uiTranslatedAttrs.has(el)) _uiTranslatedAttrs.set(el, {});
    _uiTranslatedAttrs.get(el)[attr] = {orig: value, out};
    el.setAttribute(attr, out);
  }
}

// טקסט שהאייקונים (span.ei) פיצלו לכמה צמתים - מתורגם כיחידה אחת כשהמילון מכיר אותו שלם
const _uiTranslatedMixed = new Map();  // אלמנט -> {nodes, out}

function _uiTranslateMixed(el) {
  if (el.childNodes.length < 2 || _uiTranslatedMixed.has(el) || _uiSkipped(el)) return false;
  let hasText = false;
  for (const child of el.childNodes) {
    if (child.nodeType === Node.TEXT_NODE) { hasText = hasText || _UI_HEBREW.test(child.nodeValue); continue; }
    if (!(child.nodeType === Node.ELEMENT_NODE && child.classList.contains("ei"))) return false;
  }
  if (!hasText) return false;
  const text = el.textContent;
  const out = uiTranslate(text);
  if (out === null || _UI_HEBREW.test(out)) return false;
  _uiTranslatedMixed.set(el, {nodes: [...el.childNodes], out});
  el.textContent = out;  // האייקונים נעטפים מחדש (06-ui-core.js)
  return true;
}

function _uiTranslateTree(root) {
  if (root.nodeType === Node.TEXT_NODE) { _uiTranslateTextNode(root); return; }
  if (root.nodeType !== Node.ELEMENT_NODE) return;
  _uiTranslateAttrs(root);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
    acceptNode: node => {
      if (node.nodeType !== Node.ELEMENT_NODE || !node.matches(_UI_I18N_SKIP)) return NodeFilter.FILTER_ACCEPT;
      _uiTranslateAttrs(node);
      return NodeFilter.FILTER_REJECT;
    },
  });
  const mixed = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (node.nodeType === Node.TEXT_NODE) {
      if (_UI_HEBREW.test(node.nodeValue) && uiTranslate(node.nodeValue) === null) mixed.push(node.parentElement);
      else _uiTranslateTextNode(node);
    } else _uiTranslateAttrs(node);
  }
  for (const el of new Set(mixed)) if (!_uiTranslateMixed(el)) for (const child of el.childNodes) if (child.nodeType === Node.TEXT_NODE) _uiTranslateTextNode(child);
}

function _uiPruneTranslated() {
  // צמתים שהוסרו מהדף (פיד, לוג, רשימות שנבנות מחדש) לא צריכים שחזור
  if (_uiTranslatedText.size < 4000) return;
  for (const node of _uiTranslatedText.keys()) if (!node.isConnected) _uiTranslatedText.delete(node);
  for (const el of _uiTranslatedAttrs.keys()) if (!el.isConnected) _uiTranslatedAttrs.delete(el);
  for (const el of _uiTranslatedMixed.keys()) if (!el.isConnected) _uiTranslatedMixed.delete(el);
}

function _uiOnMutations(records) {
  for (const record of records) {
    if (record.type === "childList") {
      record.addedNodes.forEach(_uiTranslateTree);
      // רק אלמנטים קטנים (תווית/כפתור) - לא textContent של רשימה שלמה בכל שינוי
      if (record.target.nodeType === Node.ELEMENT_NODE && record.target.childNodes.length <= 12) _uiTranslateMixed(record.target);
    }
    else if (record.type === "characterData") _uiTranslateTextNode(record.target);
    else if (record.type === "attributes") _uiTranslateAttrs(record.target);
  }
  _uiPruneTranslated();
}

function _uiRevertTranslations() {
  for (const [node, {orig, out}] of _uiTranslatedText) if (node.nodeValue === out) node.nodeValue = orig;
  for (const [el, attrs] of _uiTranslatedAttrs) {
    for (const [attr, {orig, out}] of Object.entries(attrs)) if (el.getAttribute(attr) === out) el.setAttribute(attr, orig);
  }
  for (const [el, {nodes, out}] of _uiTranslatedMixed) if (el.textContent === out) el.replaceChildren(...nodes);
  _uiTranslatedText.clear();
  _uiTranslatedAttrs.clear();
  _uiTranslatedMixed.clear();
}

async function setUiLanguage(lang) {
  lang = lang === "en" ? "en" : "he";
  if (lang === _uiLang && (lang === "he" || _uiI18nObserver)) { _uiSyncPrefsMenu(); return; }
  const root = document.documentElement;
  if (lang === "en") {
    try { _uiDict = _uiDict || await _uiLoadDict("en"); }
    catch (e) { uiToast("Loading the English UI failed", "bad"); return; }
    _uiLang = "en";
    _uiPrefSet("uiLang", "en");
    // תוויות העורך מקבלות קודם את המונחים המקצועיים (item 100) - הם שומרים את
    // המקור העברי שלהם, והמילון משלים את כל השאר
    const veToggle = document.getElementById("veEnglishToggle");
    if (veToggle && !veToggle.checked) {
      _uiPrefSet("uiVeEnglishBefore", "0");
      await setVeEnglish(true);
    }
    root.lang = "en";
    root.dir = "ltr";
    _uiTranslateTree(document.body);
    _uiI18nObserver = new MutationObserver(_uiOnMutations);
    _uiI18nObserver.observe(document.body, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: _UI_I18N_ATTRS});
  } else {
    _uiLang = "he";
    _uiPrefSet("uiLang", "he");
    if (_uiI18nObserver) { _uiI18nObserver.disconnect(); _uiI18nObserver = null; }
    _uiRevertTranslations();
    root.lang = "he";
    root.dir = "rtl";
    if (_uiPrefGet("uiVeEnglishBefore", "") === "0") {
      _uiPrefSet("uiVeEnglishBefore", "");
      await setVeEnglish(false);
    }
  }
  _uiSyncPrefsMenu();
}

// --- Ctrl+K: ערכות נושא, הדגשה ושפה ---
uiPaletteProviders.push(() => {
  const extra = [
    {section: "🛠️ מערכת", label: "🎨 ערכת נושא: אוטומטי/כהה/בהירה/ניגודיות גבוהה", run: () => toggleUiPrefsMenu(true)},
    {section: "🛠️ מערכת", label: "🌐 שפת הממשק: עברית/English", run: () => setUiLanguage(_uiLang === "en" ? "he" : "en")},
  ];
  return extra;
});

// ערכת הנושא והצבע מוחלים מיד (לפני init) כדי שלא יהבהב צבע אחר
setUiTheme(_uiPrefGet("web_app_theme", "dark"));
if (_uiPrefGet("uiAccent", "")) setUiAccent(_uiPrefGet("uiAccent", "cyan"));

function _uiLangReady() { document.documentElement.classList.add("ui-lang-ready"); }

function _uiInitPrefs() {
  const saved = _uiPrefGet("uiLang", "");
  if (saved) { if (saved === "en") setUiLanguage("en").finally(_uiLangReady); else { _uiSyncPrefsMenu(); _uiLangReady(); } return; }
  // 30.10.2026: בדפדפן עוד אין בחירה - השפה של ההתקנה (אנגלית בחדשה, עברית נשמרת בקיימת - utils/shared/ui_language.py)
  _uiSyncPrefsMenu();
  fetch("/api/settings/style").then(r => r.json()).then(s => s.language === "he" ? _uiPrefSet("uiLang", "he") : setUiLanguage("en"))
    .catch(() => setUiLanguage("en")).finally(_uiLangReady);
}
