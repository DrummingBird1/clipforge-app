// ============================================================================
// גל 17 - מעטפת האפליקציה: ניווט (rail), מסך הבית, פיד הפעילות, מגירת הלוג,
// ניווט מרכזי ב-Ctrl+K, והודעות קופצות במקום alert() חוסם.
// ============================================================================

// --- ניווט ---
function _uiScriptsLayout() { return document.querySelector('.layout[data-tab-panel="scripts"]'); }
function _uiEditorScript() { return (state.scripts || []).find(s => s.id.endsWith("video_editor.py")); }

function openStudio() {
  switchTab("scripts");
  const editor = _uiEditorScript();
  if (!editor) return;
  if (state.selectedId !== editor.id) selectScript(editor.id);
  if (!document.body.classList.contains("ve-focus")) setVeFocus(true);
}

// כפתור "סקריפטים" בסרגל. בתוך הסטודיו (שגם הוא על מסך הסקריפטים, עם סקריפט ה-editor נבחר) switchTab('scripts') לא משנה כלום
// חוץ מסגירת הסרגל הפתוח (☰) - לכן נראה שהכפתור "רק סוגר את התפריט". כאן הכפתור מחזיר לרשימת הסקריפטים (goHome).
function openScripts() {
  const layout = _uiScriptsLayout();
  if (layout && !layout.hidden && document.body.classList.contains("ve-focus")) { goHome(); return; }
  switchTab("scripts");
}

function openStudioJobs() {
  openStudio();
  if (typeof openVeJobs === "function" && _veEl("veJobsView").hidden) openVeJobs();
}

function openProject(folder) {
  openStudio();
  if (typeof openVeJob === "function") openVeJob(folder);
}

// 23.10.2026: "נפתחו לאחרונה" (uiRecent) - כל תיקייה שנפתחה בסטודיו, מכל מקום; גם ב-Ctrl+K
uiRecent.register("project", {icon: "📁", open: openProject});
uiBus.on("ve:folder-changed", (folder) => {
  if (folder) uiRecent.remember("project", folder, folder.split(/[\\/]/).filter(Boolean).pop());
});

// פרקים של עורך הגרפים - נרשמים כשבוחרים אותם (42-dataviz-screen.js); כאן רק הפתיחה, כדי שיופיעו עוד לפני שהמסך נטען
let dvzOpenRequest = "";
uiRecent.register("dataviz", {icon: "📊", open: (name) => { dvzOpenRequest = name; switchTab("dataviz"); }});

function toggleRecentMenu(open) {
  uiLoadLazy("frame").then(() => toggleRecentPanel(open)).catch((e) => uiToast(e.message, "warn"));
}

// מסך הבית = לשונית הסקריפטים בלי סקריפט נבחר (העדפת המסך המלא לא משתנה)
function goHome() {
  switchTab("scripts");
  if (state.selectedId) {
    state.selectedId = null;
    for (const id of ["storyCutterOptions", "videoEditorOptions", "superManagerOptions", "superStreamerOptions", "rocketShortsOptions", "wmPreviewBox"]) {
      const el = document.getElementById(id);
      if (el) el.hidden = true;
    }
    document.getElementById("selName").textContent = "בחר סקריפט מהרשימה";
    document.getElementById("selDesc").textContent = "";
    renderScripts();
    updateRunEnabled();
    if (typeof _veApplyFocus === "function") _veApplyFocus();
  }
  _uiSyncShell();
}

function _uiSyncShell() {
  const layout = _uiScriptsLayout();
  const hasSelection = !!state.selectedId;
  layout.classList.toggle("has-selection", hasSelection);
  const scriptsActive = !layout.hidden;
  const editorSelected = hasSelection && state.selectedId.endsWith("video_editor.py");
  document.querySelector(".nav-rail .rail-studio").classList.toggle("rail-active", scriptsActive && editorSelected);
  document.querySelector('.nav-rail .tab-btn[data-tab="scripts"]').classList.toggle("active", scriptsActive && !editorSelected);
  const drawer = document.getElementById("consoleDrawer");
  if (!hasSelection) drawer.classList.add("collapsed");
  else drawer.classList.toggle("collapsed", (editorSelected || !state.running) && _uiLoadConsolePref(editorSelected));   // 24.10: בסטודיו - לפי ההעדפה
  _uiSyncConsoleToggle();
  document.body.classList.remove("ve-nav-open", "dvz-nav-open");   // בחירת יעד בסרגל הפתוח (או כל מעבר) סוגרת אותו
  // גל 56: עורך הגרפים באותה מסגרת כמו הסטודיו - מסך מלא, ו-☰ בסרגל העליון שלו מחזיר את סרגל הניווט
  const dataviz = document.querySelector('[data-tab-panel="dataviz"]');
  document.body.classList.toggle("dvz-focus", !!dataviz && !dataviz.hidden);
  const dvzNav = document.getElementById("dvzNavBtn");
  if (dvzNav) dvzNav.setAttribute("aria-expanded", "false");
  if (typeof _veApplyFocus === "function") _veApplyFocus();
  if (scriptsActive && !hasSelection) _uiRenderHome();
}

function dvzToggleNav() {
  const open = document.body.classList.toggle("dvz-nav-open");
  document.getElementById("dvzNavBtn").setAttribute("aria-expanded", open ? "true" : "false");
}

const _switchTabBeforeShell = switchTab;
switchTab = function (...args) {
  const result = _switchTabBeforeShell(...args);
  _uiSyncShell();
  return result;
};

const _selectScriptBeforeShell = selectScript;
selectScript = function (...args) {
  const result = _selectScriptBeforeShell(...args);
  _uiSyncShell();
  return result;
};

// --- מסך הבית ---
let _uiHomeFetchedAt = 0;
let _uiLastHistoryRows = [];

function _uiEmpty(icon, title, text) {
  const box = document.createElement("div");
  box.className = "empty-state";
  const ico = document.createElement("div");
  ico.textContent = icon;
  const t = document.createElement("div");
  t.className = "empty-state-title";
  t.textContent = title;
  const p = document.createElement("div");
  p.textContent = text;
  box.append(ico, t, p);
  return box;
}

async function _uiRenderHome(force) {
  _uiRenderHomeRuns();
  if (!force && Date.now() - _uiHomeFetchedAt < 4000) return;
  _uiHomeFetchedAt = Date.now();
  const box = document.getElementById("homeProjects");
  let projects = [];
  try {
    projects = await fetch("/api/editor_projects").then(r => r.json()).then(d => d.projects || []);
  } catch (e) {
    box.replaceChildren(_uiEmpty("⚠️", "טעינת הפרויקטים נכשלה", "נסה לרענן את הדף."));
    return;
  }
  _uiPaletteProjects = projects;
  if (!projects.length) {
    box.replaceChildren(_uiEmpty("📁", "עוד אין פרויקטים", "בחר תיקייה בסטודיו - כל מה שתעשה בה נשמר אוטומטית כפרויקט."));
    return;
  }
  box.replaceChildren(...projects.slice(0, 5).map(project => {
    const row = document.createElement("div");
    row.className = "home-project";
    const main = document.createElement("div");
    main.className = "home-project-main";
    const name = document.createElement("div");
    name.className = "home-project-name";
    name.textContent = "📁 " + (project.name || project.folder);
    const meta = document.createElement("div");
    meta.className = "home-project-meta";
    meta.textContent = project.folder;
    meta.title = project.folder;
    main.append(name, meta);
    const when = document.createElement("span");
    when.className = "feed-time";
    when.textContent = uiRelativeTime(project.updated_at);
    const open = document.createElement("button");
    open.type = "button";
    open.className = "btn-sm";
    open.textContent = "📂 פתח";
    open.disabled = !project.folder_exists;
    open.onclick = () => openProject(project.folder);
    row.append(main, when, open);
    return row;
  }));
}

function _uiRenderHomeRuns() {
  const box = document.getElementById("homeRuns");
  if (!box) return;
  if (!_uiLastHistoryRows.length) {
    box.replaceChildren(_uiEmpty("🕘", "עוד לא בוצעו ריצות", "ריצה ראשונה תופיע כאן עם סיכום התוצאה."));
    return;
  }
  box.replaceChildren(..._uiLastHistoryRows.slice(0, 5).map(_uiFeedItem));
}

// --- פיד הפעילות: סיכום אנושי במקום "files_created: 24 | errors: 0 | ..." ---
const _UI_RESULT_PARTS = [
  ["files_created", n => `${n} נוצרו`], ["clips_created", n => `${n} קליפים`], ["videos_found", n => `${n} סרטונים`],
  ["files_scanned", n => `${n} נסרקו`], ["duplicate_groups", n => `${n} קבוצות כפילויות`], ["groups_processed", n => `${n} קבוצות`],
  ["files_moved", n => `${n} הועברו`], ["junk_files", n => `${n} קבצי זבל`], ["uploaded", n => `${n} הועלו`],
  ["published", n => `${n} פורסמו`], ["downloaded", n => `${n} הורדו`], ["skipped", n => `${n} דולגו`],
];
const _UI_RESULT_BAD = [["errors", n => `${n} שגיאות`], ["failed", n => `${n} נכשלו`], ["invalid", n => `${n} לא תקינים`]];

function _uiScriptLabel(scriptFile) {
  const s = (state.scripts || []).find(x => x.id.split("/").pop() === scriptFile);
  return s ? s.name : scriptFile;
}

function _uiResultSummary(row) {
  const result = row.result && typeof row.result === "object" ? row.result : {};
  const parts = [];
  for (const [key, fmt] of _UI_RESULT_PARTS) {
    const value = result[key];
    if (typeof value === "number" && value > 0 && parts.length < 3) parts.push({text: fmt(value)});
  }
  for (const [key, fmt] of _UI_RESULT_BAD) {
    const value = result[key];
    if (typeof value === "number" && value > 0) parts.push({text: fmt(value), bad: true});
  }
  const seconds = row.duration ?? result.elapsed_seconds;
  if (seconds) parts.push({text: "⏱️ " + uiFormatDuration(seconds)});
  if (!parts.length && row.summary) parts.push({text: row.summary.length > 60 ? row.summary.slice(0, 60) + "…" : row.summary});
  return parts;
}

function _uiFeedItem(row) {
  const ok = row.status === "success";
  const running = row.status === "running";
  const item = document.createElement("div");
  item.className = "hist-row feed-item";
  item.dataset.status = ok ? "ok" : (running ? "running" : "bad");
  const status = document.createElement("span");
  status.className = "feed-status";
  status.textContent = running ? "⏳" : (ok ? "✅" : "❌");
  const main = document.createElement("div");
  main.style.minWidth = "0";
  const title = document.createElement("div");
  title.className = "feed-title";
  title.textContent = _uiScriptLabel(row.script);
  title.title = row.script;
  const sub = document.createElement("div");
  sub.className = "feed-sub";
  _uiResultSummary(row).forEach((part, index) => {
    if (index) sub.append(" · ");
    const span = document.createElement("span");
    if (part.bad) span.className = "bad";
    span.textContent = part.text;
    sub.append(span);
  });
  main.append(title, sub);
  const time = document.createElement("time");
  time.className = "feed-time";
  time.textContent = uiRelativeTime(row.started_at);
  time.title = String(row.started_at || "").replace("T", " ");
  item.append(status, main, time);
  if (row.summary) {
    const details = document.createElement("div");
    details.className = "feed-details";
    details.textContent = row.summary.split(" | ").join("\n");
    item.append(details);
    item.onclick = () => item.classList.toggle("open");
    item.title = "לחיצה מציגה את כל הפרטים";
  }
  return item;
}

_renderHistoryRows = function (rows, emptyMessage) {
  const container = document.getElementById("historyList");
  if (!document.getElementById("historySearch").value.trim()) _uiLastHistoryRows = rows;
  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "hist-row feed-empty";
    empty.textContent = emptyMessage;
    container.replaceChildren(empty);
  } else {
    container.replaceChildren(...rows.map(_uiFeedItem));
  }
  if (!_uiScriptsLayout().classList.contains("has-selection")) _uiRenderHomeRuns();
};

// שמות הסקריפטים נטענים אחרי ההיסטוריה - מרנדרים שוב את הפיד עם השמות הידידותיים
const _loadScriptsBeforeShell = loadScripts;
loadScripts = async function (...args) {
  const result = await _loadScriptsBeforeShell(...args);
  if (_uiLastHistoryRows.length && !document.getElementById("historySearch").value.trim()) _renderHistoryRows(_uiLastHistoryRows, "");
  return result;
};

// --- מגירת הלוג ---
// גל 57: בסטודיו הלוג מקופל כברירת מחדל - שורה אחת עם מצב הריצה האחרונה, ותיבה ריקה לא תופסת את תחתית המסך.
// נפתח לבד כשריצה מתחילה או נכשלת, ופתיחה ידנית נזכרת (מפתח נפרד מהסקריפטים האחרים)
function _uiLoadConsolePref(studio) {
  try {
    return studio ? localStorage.getItem("uiStudioConsoleOpen") !== "1" : localStorage.getItem("uiConsoleCollapsed") === "1";
  } catch (e) { return !!studio; }
}

function _uiEditorIsSelected() { return !!state.selectedId && state.selectedId.endsWith("video_editor.py"); }

function _uiSyncConsoleToggle() {
  const collapsed = document.getElementById("consoleDrawer").classList.contains("collapsed");
  document.getElementById("consoleToggle").setAttribute("aria-expanded", String(!collapsed));
}

function toggleConsoleDrawer(force) {
  const drawer = document.getElementById("consoleDrawer");
  const collapsed = force === undefined ? !drawer.classList.contains("collapsed") : !!force;
  drawer.classList.toggle("collapsed", collapsed);
  _uiSyncConsoleToggle();
  if (_uiScriptsLayout().classList.contains("has-selection")) {
    try {
      if (_uiEditorIsSelected()) localStorage.setItem("uiStudioConsoleOpen", collapsed ? "0" : "1");
      else localStorage.setItem("uiConsoleCollapsed", collapsed ? "1" : "0");
    } catch (e) { /* לא קריטי */ }
  }
  if (typeof _veScheduleLiveRebuild === "function") _veScheduleLiveRebuild();   // גל 57: הנגן בסטודיו גדל/קטן עם המקום שהתפנה
}

// גל 60: ריצה של כלי אחד נראית מהשני - שבב בסרגל העליון של הסטודיו ושל עורך הגרפים (התור והריצה משותפים).
// כל כלי מסמן את עצמו כשהוא מתחיל ריצה; ריצה שהתחילה במקום אחר (תזמון, בוט) מוצגת כ"ריצה"
let _uiRun = {owner: "", label: "", pct: 0, active: false};

function uiMarkRunOwner(owner, label) {
  _uiRun = {owner, label, pct: 0, active: true};
  _uiSyncRunChips();
}

function uiGoToRunOwner() {
  if (_uiRun.owner === "dataviz") switchTab("dataviz");
  else if (_uiRun.owner === "studio") openStudio();
  else switchTab("scripts");
}

function _uiSyncRunChips() {
  for (const [id, mine] of [["veOtherRunChip", "studio"], ["dvzOtherRunChip", "dataviz"]]) {
    const chip = document.getElementById(id);
    if (!chip) continue;
    chip.hidden = !_uiRun.active || _uiRun.owner === mine;
    const label = document.createElement("span");
    label.textContent = _uiRun.label;
    chip.replaceChildren(label, document.createTextNode(` ${_uiRun.pct}%`));
  }
}

document.addEventListener("cf-progress", (e) => {
  if (!_uiRun.active) _uiRun = {owner: "", label: "▶ ריצה", pct: 0, active: true};
  _uiRun.pct = Math.round(Number(e.detail.pct) || 0);
  _uiSyncRunChips();
});
document.addEventListener("cf-finished", () => { _uiRun.active = false; _uiSyncRunChips(); });

const _runScriptBeforeShell = runScript;
runScript = async function (...args) {
  const result = await _runScriptBeforeShell(...args);
  if (state.running) {
    const script = (state.scripts || []).find(s => s.id === state.selectedId);
    uiMarkRunOwner(_uiEditorIsSelected() ? "studio" : "scripts", _uiEditorIsSelected() ? "🎬 סטודיו" : "▶ " + (script ? script.name : "ריצה"));
    if (!_uiEditorIsSelected()) document.getElementById("consoleDrawer").classList.remove("collapsed");
    _uiSyncConsoleToggle();
    document.getElementById("consoleMeta").textContent = "⏳ רץ...";
  }
  return result;
};

const _appendLogBatchBeforeShell = appendLogBatch;
appendLogBatch = function (lines) {
  _appendLogBatchBeforeShell(lines);
  const meta = document.getElementById("consoleMeta");
  if (!state.running && lines.some(l => /הסתיים בהצלחה|נכשל\./.test(l.line || ""))) {
    const ok = lines.some(l => /הסתיים בהצלחה/.test(l.line || ""));
    meta.textContent = ok ? "✅ הריצה האחרונה הסתיימה" : "❌ הריצה האחרונה נכשלה";
    if (!ok) {   // גל 57: כישלון פותח את הלוג גם אם היה מקופל - בלי לשמור את זה כהעדפה
      document.getElementById("consoleDrawer").classList.remove("collapsed");
      _uiSyncConsoleToggle();
    }
  }
};

// --- Ctrl+K כניווט מרכזי: מסכים, פרויקטים ופעולות מערכת (לפני רשימת הסקריפטים) ---
let _uiPaletteProjects = [];

uiPaletteProviders.push(() => {
  const extra = [];
  const add = (section, label, run) => extra.push({section, label, run});
  add("🧭 מסכים", "🏠 מסך הבית", goHome);
  add("🧭 מסכים", "🎬 סטודיו (עורך-העל במסך מלא)", openStudio);
  add("🧭 מסכים", "📁 פרויקטים", openStudioJobs);
  for (const btn of document.querySelectorAll(".nav-rail .tab-btn[data-tab]")) {
    const label = btn.textContent.trim();
    add("🧭 מסכים", label, () => switchTab(btn.dataset.tab));
  }
  for (const item of uiRecent.list().slice(0, 8)) add("🕘 נפתחו לאחרונה", `${item.icon} ${item.label}`, () => uiRecent.open(item));
  for (const project of _uiPaletteProjects.slice(0, 12)) {
    add("📁 פרויקטים", "📁 " + (project.name || project.folder), () => openProject(project.folder));
  }
  add("🛠️ מערכת", "🌓 החלף ערכת נושא (כהה/בהירה)", toggleTheme);
  add("🛠️ מערכת", "📊 סטטיסטיקות", openStats);
  add("🛠️ מערכת", "🩺 אבחון תקינות", openDiagnostics);
  add("🛠️ מערכת", "⚙️ הגדרות: ייצוא/ייבוא וגיבויים", openSettingsModal);
  add("🛠️ מערכת", "🔔 התראות דפדפן: הפעל/כבה", toggleNotifications);
  return extra;
});

const _openCommandPaletteBeforeShell = openCommandPalette;
openCommandPalette = function (...args) {
  const result = _openCommandPaletteBeforeShell(...args);
  if (Date.now() - _uiHomeFetchedAt > 15000) {
    fetch("/api/editor_projects").then(r => r.json()).then(d => {
      _uiPaletteProjects = d.projects || [];
      if (document.getElementById("paletteModalBg").classList.contains("show")) _renderPaletteList(document.getElementById("paletteInput").value);
    }).catch(() => {});
  }
  return result;
};

// --- alert() -> הודעה קופצת (לא חוסמת). confirm/prompt: veConfirm/vePrompt בתוך הדף (גל 22). ---
window._uiNativeAlert = window.alert.bind(window);
window.alert = function (message) {
  const text = String(message ?? "");
  const tone = /^(❌|שגיאה|Error)|נכשל/.test(text) ? "bad" : (/^⚠/.test(text) ? "warn" : (/^(✅|↩️|💾)/.test(text) ? "ok" : ""));
  uiToast(text, tone);
};

function _uiInitShell() {
  _uiSyncShell();
}
