// ============================================================================
// גל 33: המפקח מסודר - מסלול ניווט קבוע, חיפוש ו"רק מה ששיניתי" בתוך המפקח עצמו (לא
// בתפריט), שדות לא רלוונטיים מושבתים עם סיבה, אזהרות ליד השדה, כלים לכל קבוצה
// (איפוס / העתקה / הדבקה), שורת "מה זה עושה" לכל קבוצה, זכירת גלילה לכל לשונית,
// "?" שנפתח ליד כל שדה (עובד גם במגע) וקישור לסעיף המתאים בתיעוד.
// ============================================================================

// --- מסלול ניווט: תיקייה › קובץ › עריכת קליפ › לשונית ---
function _veActiveCategoryKey() {
  const container = _veEl("veCategories");
  if (container && container.classList.contains("ve-layout-tabs")) return _veLoadPref("veActiveTab", VE_DEFAULT_TAB);
  const focused = document.activeElement && document.activeElement.closest && document.activeElement.closest("#veCategories details.ve-category");
  return focused ? focused.dataset.cat : "";
}

function _veCrumb(icon, text, title, onclick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "ve-crumb";
  btn.textContent = `${icon} ${text}`;
  btn.title = title;
  btn.onclick = onclick;
  return btn;
}

function _veRenderCrumbs() {
  const nav = _veEl("veCrumbs");
  if (!nav) return;
  const items = [];
  const folder = String(state.folder || "").split(/[\\/]/).filter(Boolean).pop();
  items.push(_veCrumb("📁", folder || "בחר תיקייה", state.folder || "בחר תיקייה", () => openBrowser()));
  const select = _veEl("vePreviewFile");
  const file = _veTimeScope === "clip" ? _veClipScopeFile : (select && select.value);
  if (file) {
    items.push(_veCrumb("🎞️", file, "הצג את הקובץ בתור", () => {
      const row = [...document.querySelectorAll("#veQueueList .ve-queue-row")].find(r => r.dataset.name === file);
      if (row) { _veRevealElement(row); row.scrollIntoView({block: "nearest"}); }
    }));
  }
  if (_veTimeScope === "clip") {
    items.push(_veCrumb("✏️", "עריכת קליפ", "השינויים חלים רק על הקובץ הזה - לחץ לסיום", () => exitVeClipMode()));
  }
  const key = _veActiveCategoryKey();
  const details = key && _veCategoryByKey(key);
  if (details) {
    items.push(_veCrumb("", details.querySelector(".ve-cat-title").textContent.trim(), "לראש האזור", () => {
      details.scrollIntoView({block: "start"});
    }));
  }
  const signature = items.map(b => b.textContent).join("|");
  if (nav.dataset.signature === signature) return;
  nav.dataset.signature = signature;
  const parts = [];
  items.forEach((btn, i) => {
    if (i) {
      const sep = document.createElement("span");
      sep.className = "ve-crumb-sep";
      sep.setAttribute("aria-hidden", "true");
      sep.textContent = "›";
      parts.push(sep);
    }
    parts.push(btn);
  });
  nav.replaceChildren(...parts);
}

// --- "רק מה ששיניתי" בכלי המפקח (ליד החיפוש) ---
function _veChangedTotal() {
  return _veCategoryEls().filter(d => d.dataset.cat !== "queue").reduce((n, d) => n + _veChangedFieldsInCategory(d).length, 0);
}

function _veRenderChangedChip() {
  const chip = _veEl("veChangedChip");
  if (!chip) return;
  const on = _veLoadPref("veOnlyChanged", false);
  const total = _veChangedTotal();
  chip.textContent = `✎ רק מה ששיניתי (${total})`;
  chip.setAttribute("aria-pressed", String(!!on));
  chip.classList.toggle("ve-chip-on", !!on);
}

function toggleVeChangedChip() {
  setVeOnlyChanged(!_veLoadPref("veOnlyChanged", false));
  _veRenderChangedChip();
}

// --- שדות לא רלוונטיים: מעומעמים עם סיבה (לא מוסתרים ולא נעולים - לפעמים המתג שמפעיל אותם
// באותה שורה, ומותר למלא אותם מראש). שדות קודק כבר מוסתרים לפי הקודק (updateVeCodecDependentRows),
// ושדות "legacy" מוסתרים מאחורי הבקרים המשולבים - שניהם לא כאן.
const _veOff = (id) => { const el = _veEl(id); return !el || (el.type === "checkbox" ? !el.checked : !String(el.value).trim()); };

const VE_RELEVANCE = [
  {ids: ["veMaxConcurrentNvenc"], when: () => (parseInt((_veEl("veParallel") || {}).value, 10) || 1) <= 1, reason: "רלוונטי רק כשמקודדים כמה קבצים במקביל"},
  {ids: ["vePipPosition", "vePipScale", "vePipOpacity", "vePipAudio", "vePipDuck"], when: () => _veOff("vePipPath"), reason: "רלוונטי רק כשיש קובץ PiP"},
  {ids: ["veWatermarkOpacity", "veWatermarkScale", "veWatermarkPosition"], when: () => _veOff("veWatermarkPath"), reason: "רלוונטי רק כשיש לוגו"},
  {ids: ["veLoudnormTarget"], when: () => _veOff("veLoudnorm"), reason: "רלוונטי רק כשנרמול העוצמה פעיל"},
];

// הבקר עצמו, או התווית שעוטפת אותו (תיבת סימון בתוך label)
function _veRelevanceTarget(el) {
  const wrap = el.parentElement;
  return wrap && wrap.tagName === "LABEL" && wrap.querySelectorAll("input, select, textarea").length === 1 ? wrap : el;
}

function _veApplyRelevance() {
  const reasons = new Map();   // שורה -> סיבות (כמה בקרים בשורה יכולים להיות לא רלוונטיים מאותה סיבה)
  for (const rule of VE_RELEVANCE) {
    let off = false;
    try { off = !!rule.when(); } catch (e) { off = false; }
    for (const id of rule.ids) {
      const el = _veEl(id);
      const row = el && el.closest(".ve-row");
      if (!row || row.closest(".ve-favorite-row, #veLegacyFields")) continue;
      _veRelevanceTarget(el).classList.toggle("ve-ctl-irrelevant", off);
      if (!reasons.has(row)) reasons.set(row, new Set());
      if (off) reasons.get(row).add(rule.reason);
    }
  }
  for (const [row, set] of reasons) {
    let note = row.querySelector(":scope > .ve-rel-note");
    if (!set.size) { if (note) note.remove(); continue; }
    if (!note) {
      note = document.createElement("div");
      note.className = "ve-rel-note";
      row.appendChild(note);
    }
    note.textContent = "💤 " + [...set].join(" · ");
  }
}

// שדות תלויים (מהסכמה) כשמוצגים מעומעמים - עם הסיבה, לא רק עמעום
function _veDependentReason(id) {
  const parentId = VE_DEPENDENT_PARENTS[id];
  const parent = parentId && _veEl(parentId);
  if (!parent) return "";
  const row = parent.closest(".ve-row");
  const label = ((row && row.querySelector("label")) || {}).textContent || "";
  const name = label.replace(/[:：]\s*$/, "").trim();
  return parent.type === "checkbox" ? `פעיל רק כש"${name}" מסומן` : `פעיל רק כש"${name}" מלא`;
}

function _veApplyDependentReasons() {
  for (const id of Object.keys(VE_DEPENDENT_FIELDS)) {
    const el = _veEl(id);
    const row = el && el.closest(".ve-row");
    if (!row) continue;
    const dim = row.classList.contains("ve-dep-dim");
    let note = row.querySelector(":scope > .ve-dep-note");
    if (!dim) { if (note) note.remove(); continue; }
    if (!note) {
      note = document.createElement("div");
      note.className = "ve-dep-note";
      row.appendChild(note);
    }
    note.textContent = "↳ " + _veDependentReason(id);
  }
}

// --- אזהרות ליד השדה עצמו ---
let _veInlineWarnSignature = "";

function _veRenderInlineWarnings() {
  const rules = _veEvaluateRules();
  const signature = rules.map(r => `${r.field}|${r.level}|${r.msg}`).join("\n");
  if (signature === _veInlineWarnSignature) return;   // רץ על כל שינוי - בלי לגעת ב-DOM כשאין חדש
  _veInlineWarnSignature = signature;
  for (const old of document.querySelectorAll("#veCategories .ve-inline-warn")) old.remove();
  for (const rule of rules) {
    const meta = rule.field && VE_FAVORITABLE_FIELDS[rule.field];
    const el = meta && _veEl(meta.id);
    const row = el && el.closest(".ve-row");
    if (!row || row.closest(".ve-favorite-row")) continue;
    const note = document.createElement("div");
    note.className = "ve-inline-warn " + (rule.level === "info" ? "info" : "warn");
    note.setAttribute("role", "note");
    note.textContent = (rule.level === "info" ? "ℹ️ " : "⚠️ ") + rule.msg;
    row.appendChild(note);
  }
}

// --- כלים לכל קבוצה: איפוס, העתקה והדבקה (גם בין פרויקטים) ---
const VE_GROUP_CLIPBOARD = "veGroupClipboard";

function _veFieldValue(el) {
  return el.type === "checkbox" ? el.checked : el.value;
}

function _veApplyFieldValue(el, value) {
  if (el.type !== "checkbox") { _veSetFieldValue(el, value); return; }
  el.checked = !!value;
  el.dispatchEvent(new Event("input", {bubbles: true}));
  el.dispatchEvent(new Event("change", {bubbles: true}));
}

function resetVeSubcat(sub) {
  const fields = _veSubcatFields(sub).filter(([, , el]) => _veFieldChanged(el));
  for (const [, , el] of fields) _veApplyFieldValue(el, _veFieldDefaults[el.id]);
  uiToast(fields.length ? `↺ ${fields.length} הגדרות חזרו לברירת המחדל` : "הכל כבר בברירת המחדל", fields.length ? "ok" : "");
}

function copyVeSubcat(sub) {
  const values = {};
  for (const [key, , el] of _veSubcatFields(sub)) values[key] = _veFieldValue(el);
  _veSavePref(VE_GROUP_CLIPBOARD, {group: sub.dataset.subcat, title: sub.querySelector(".ve-subcat-title").firstChild.textContent.trim(), values});
  uiToast(`📋 הועתקו ${Object.keys(values).length} הגדרות - אפשר להדביק גם בפרויקט אחר`, "ok");
  _veRefreshGroupTools();
}

function pasteVeSubcat(sub) {
  const clip = _veLoadPref(VE_GROUP_CLIPBOARD, null);
  if (!clip || clip.group !== sub.dataset.subcat) { uiToast("אין העתקה של הקבוצה הזו", "warn"); return; }
  let applied = 0;
  for (const [key, meta, el] of _veSubcatFields(sub)) {
    if (!(key in clip.values) || !meta) continue;
    _veApplyFieldValue(el, clip.values[key]);
    applied++;
  }
  uiToast(`📥 הודבקו ${applied} הגדרות`, "ok");
}

function _veRefreshGroupTools() {
  const clip = _veLoadPref(VE_GROUP_CLIPBOARD, null);
  for (const btn of document.querySelectorAll("#veCategories .ve-group-paste")) {
    btn.disabled = !clip || clip.group !== btn.closest(".ve-subcat").dataset.subcat;
  }
}

function _veGroupButton(icon, title, onclick, cls) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "ve-group-tool" + (cls ? " " + cls : "");
  btn.textContent = icon;
  btn.title = title;
  btn.setAttribute("aria-label", title);
  btn.onclick = (e) => { e.stopPropagation(); onclick(); };
  // הכותרת מקפלת ב-Enter/רווח ועושה preventDefault - בלי זה הכפתור לא נלחץ מהמקלדת
  btn.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") e.stopPropagation(); });
  return btn;
}

// --- שורת "מה זה עושה" לכל קבוצה ---
const VE_SUBCAT_HELP = {
  "cuts": "קטעים שיוצאים מהסרטון - טווחים שסימנת, או קטעים שקטים שזוהו.",
  "bookends": "מה שמסביב לסרטון: מעבר בין קטעים, פתיח וסיום, וחזרות.",
  "color": "תיקון בסיסי של התמונה - מראה מוכן, בהירות, ניגודיות, רוויה ו-LUT.",
  "grade": "תיקון צבע מתקדם לכל טווח (צללים, אמצע, הדגשות) ועקומות.",
  "cleanup": "הפחתת רעש, חידוד וייצוב - לפני הצבע.",
  "effects": "אפקטים על כל התמונה: וינייטה, Ken Burns, מהירות ושינויים מיוחדים.",
  "chromakey": "מחליף רקע בצבע אחיד (מסך ירוק) בצבע אחר.",
  "watermark": "הלוגו שלך מעל הסרטון: קובץ, מקום, גודל ושקיפות.",
  "pip": "וידאו שני בחלון קטן (מצלמת פנים, פרשנות) עם השמע שלו.",
  "decor": "סרגל שמראה כמה מהסרטון עבר.",
  "frame": "מסגרת צבעונית סביב התמונה.",
  "removal": "מכסה לוגו או סימן מים שכבר צרוב במקור.",
  "audio-fx": "עיבוד השמע: חיתוך נמוכים, EQ, קומפרסור והפחתת רעש.",
  "captions": "כתוביות אוטומטיות מתמלול: שפה, עיצוב, מיקום וייצוא לקובץ.",
  "file": "הקובץ שנוצר: קודק, מיכל ואיכות.",
  "naming": "איך ייקראו הקבצים שנוצרים, ומספור רץ.",
  "extra-outputs": "קבצים נוספים מאותה ריצה: GIF, WebP, שמע בלבד, תמונה ממוזערת.",
  "metadata": "תגיות ופרקים בתוך קובץ הווידאו.",
  "timed-layers": "שכבות עם זמן התחלה וסוף: טקסט, תמונה, טיימר ו-B-roll.",
};

function _veSetupGroupTools() {
  for (const sub of document.querySelectorAll("#veCategories .ve-subcat[data-subcat]")) {
    const title = sub.querySelector(":scope > .ve-subcat-title");
    if (!title || sub.dataset.veGroupTools) continue;
    sub.dataset.veGroupTools = "1";
    const help = VE_SUBCAT_HELP[sub.dataset.subcat];
    if (help) {
      const desc = document.createElement("p");
      desc.className = "ve-subcat-desc";
      desc.textContent = help;
      title.after(desc);
    }
    if (!_veSubcatFields(sub).length) continue;
    const tools = document.createElement("span");
    tools.className = "ve-group-tools";
    tools.append(
      _veGroupButton("↺", "החזר את הקבוצה לברירת המחדל", () => resetVeSubcat(sub)),
      _veGroupButton("📋", "העתק את הגדרות הקבוצה (אפשר להדביק גם בפרויקט אחר)", () => copyVeSubcat(sub)),
      _veGroupButton("📥", "הדבק את ההגדרות שהועתקו לקבוצה הזו", () => pasteVeSubcat(sub), "ve-group-paste"),
    );
    title.appendChild(tools);
  }
  _veRefreshGroupTools();
}

// --- זכירת גלילה לכל לשונית ---
function _veInspectorScroller() {
  return document.querySelector("#videoEditorOptions .ve-main");
}

function _veSetupTabScrollMemory() {
  const nav = _veEl("veCatTabs");
  if (!nav || nav.dataset.veScrollMemory) return;
  nav.dataset.veScrollMemory = "1";
  nav.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-cat]");
    const scroller = _veInspectorScroller();
    if (!btn || !scroller) return;
    const saved = _veLoadPref("veTabScroll", {});
    saved[_veLoadPref("veActiveTab", VE_DEFAULT_TAB)] = scroller.scrollTop;
    _veSavePref("veTabScroll", saved);
    requestAnimationFrame(() => { scroller.scrollTop = _veLoadPref("veTabScroll", {})[btn.dataset.cat] || 0; });
  }, true);
}

// --- "?" ליד כל שדה: ההסבר נפתח בתוך הדף, עם קישור לסעיף בתיעוד ---
function _veFieldKeyForRow(row) {
  for (const [key, meta] of Object.entries(VE_FAVORITABLE_FIELDS)) {
    if (row.contains(_veEl(meta.id))) return key;
  }
  return "";
}

function _veToggleRowHelp(row, label, btn) {
  let box = row.querySelector(":scope > .ve-help-inline");
  if (box) {
    box.remove();
    btn.setAttribute("aria-expanded", "false");
    return;
  }
  box = document.createElement("div");
  box.className = "ve-help-inline";
  const text = document.createElement("span");
  text.textContent = label.title;
  box.appendChild(text);
  const key = _veFieldKeyForRow(row);
  if (key) {
    const docs = document.createElement("button");
    docs.type = "button";
    docs.className = "ve-help-docs";
    docs.textContent = "📖 בתיעוד";
    docs.onclick = () => openVeFieldDocs(key, label.textContent.trim());
    box.appendChild(docs);
  }
  row.appendChild(box);
  btn.setAttribute("aria-expanded", "true");
}

function _veSetupInlineHelp() {
  for (const label of document.querySelectorAll("#veCategories .ve-row > label[title]")) {
    const row = label.parentElement;
    if (row.dataset.veHelp || !label.title.trim()) continue;
    row.dataset.veHelp = "1";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ve-help-toggle";
    btn.textContent = "?";
    btn.setAttribute("aria-label", "הסבר על ההגדרה");
    btn.setAttribute("aria-expanded", "false");
    btn.onclick = (e) => { e.preventDefault(); _veToggleRowHelp(row, label, btn); };
    label.after(btn);
  }
}

// גל 37: סכימת השדות האחת (GET /api/video_editor/field_schema) - הדגל האמיתי לכל שדה, וההסבר
let _veFieldSchema = null;
async function _veLoadFieldSchema() {
  if (_veFieldSchema) return _veFieldSchema;
  try { _veFieldSchema = (await (await fetch("/api/video_editor/field_schema")).json()).fields || {}; }
  catch (e) { _veFieldSchema = {}; }
  return _veFieldSchema;
}

// שדה שהתווית שלו בלי tooltip מקבל את ההסבר מהסכימה (וכך גם "?" ליד השדה)
function _veApplySchemaHelp(schema) {
  for (const [key, meta] of Object.entries(VE_FAVORITABLE_FIELDS)) {
    const help = (schema[key] || {}).help;
    const el = help && _veEl(meta.id);
    const row = el && el.closest("#veCategories .ve-row");
    const label = row && row.querySelector(":scope > label:not([title])");
    if (label && !label.querySelector("input, select, textarea")) label.title = help;
  }
  _veSetupInlineHelp();
}

async function openVeFieldDocs(key, term) {
  const meta = (await _veLoadFieldSchema())[key] || {};
  const flags = meta.flags && meta.flags.length ? meta.flags : ["--" + key.replace(/_/g, "-")];
  const params = new URLSearchParams({doc: "video_editor", q: [...flags, "--" + key, key, term].join("|")});
  const body = _veEl("veDocsBody");
  _veEl("veDocsTitle").textContent = "📖 " + term;
  body.textContent = "⏳";
  _veEl("veDocsModalBg").classList.add("show");
  try {
    const res = await fetch("/api/docs/section?" + params.toString());
    const data = await res.json();
    if (!res.ok || !data.text) { body.textContent = "אין עדיין סעיף בתיעוד להגדרה הזו."; return; }
    _veEl("veDocsTitle").textContent = "📖 " + data.title;
    body.textContent = data.text;
  } catch (e) {
    body.textContent = "התיעוד לא נטען.";
  }
}

function closeVeDocs() {
  _veEl("veDocsModalBg").classList.remove("show");
}

function _veRefreshInspectorTools() {
  _veRenderCrumbs();
  _veRenderChangedChip();
  _veApplyRelevance();
  _veApplyDependentReasons();
  _veRenderInlineWarnings();
}

function _veInitWave33() {
  _veLoadFieldSchema().then(_veApplySchemaHelp);
  _veSetupGroupTools();
  _veSetupInlineHelp();
  _veSetupTabScrollMemory();
  _veRefreshInspectorTools();
  // נשלח על כל הקלדה - מרעננים אחרי הרענון הנגזר (150ms), כשהשדות התלויים כבר מעודכנים
  const refreshSoon = () => uiDebounce("ve:inspector-tools", _veRefreshInspectorTools, 160);
  uiBus.on("ve:derived-refresh", refreshSoon);
  uiBus.on("ve:fields-applied", refreshSoon);
  uiBus.on("ve:folder-changed", () => setTimeout(_veRenderCrumbs, 0));
  const nav = _veEl("veCatTabs");
  if (nav) nav.addEventListener("click", () => setTimeout(_veRenderCrumbs, 0));
  const select = _veEl("vePreviewFile");
  if (select) select.addEventListener("change", _veRenderCrumbs);
  const cats = _veEl("veCategories");
  if (cats) cats.addEventListener("focusin", () => { if (!cats.classList.contains("ve-layout-tabs")) _veRenderCrumbs(); });
}
