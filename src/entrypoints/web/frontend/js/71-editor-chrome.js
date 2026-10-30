// ============================================================================
// גל 27: לנקות את המסך - הפס העליון בשורה אחת (התיקייה כשבב קצר עם תיקיות אחרונות),
// פס סטטוס אחד בתחתית (אזהרות בכפתור), איפוס שדה רק בשדה ששונה (ריחוף / קליק ימני),
// הנגן מציג פריים ברגע שנטענת תיקייה, בורר אחד לסוג התצוגה, וחיפוש/סינון בתור.
// ============================================================================

// --- שבב התיקייה ---
function _veFolderShortName(path) {
  const parts = String(path || "").split(/[\\/]+/).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : "";
}

function _veRenderFolderChip() {
  const name = _veFolderShortName(state.folder);
  const chip = _veEl("veFolderChip");
  _veEl("veFolderChipName").textContent = name || "בחר תיקייה";
  chip.classList.toggle("ve-folder-empty", !name);
  _veEl("veFolderMenuPath").textContent = state.folder || "";
  _veEl("veFolderMenuPath").hidden = !state.folder;
}

function toggleVeFolderMenu(event) {
  toggleVeMenu("veFolderMenu", event);
  if (!_veEl("veFolderMenu").hidden) _veLoadRecentFolders();
}

async function _veLoadRecentFolders() {
  const box = _veEl("veRecentFolders");
  let projects = [];
  try {
    projects = await fetch("/api/editor_projects").then(r => r.json()).then(d => d.projects || []);
  } catch (e) { projects = []; }
  const recent = projects.filter(p => p.folder && p.folder !== state.folder).slice(0, 6);
  if (!recent.length) {
    const empty = document.createElement("div");
    empty.className = "ve-field-msg";
    empty.textContent = "עוד אין תיקיות אחרות";
    box.replaceChildren(empty);
    return;
  }
  box.replaceChildren(...recent.map(project => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("role", "menuitem");
    btn.textContent = "📁 " + (project.name || _veFolderShortName(project.folder));
    btn.title = project.folder;
    btn.dataset.folder = project.folder;
    btn.disabled = project.folder_exists === false;
    btn.onclick = () => { closeVeMenus(); openVeJob(project.folder); };
    return btn;
  }));
}

// --- אזהרות: כפתור בפס הסטטוס שפותח את הרשימה ---
function toggleVeWarnings(force) {
  const toggle = _veEl("veWarningsToggle");
  const open = typeof force === "boolean" ? force : toggle.getAttribute("aria-expanded") !== "true";
  toggle.setAttribute("aria-expanded", String(open));
  _veEl("veWarningsBox").hidden = !open || !_veEl("veWarningsBox").children.length;
}

// נסגרת כמו התפריטים; Escape סוגר רק אותה
document.addEventListener("click", (e) => { if (!e.target.closest("#veWarningsBox, #veWarningsToggle")) toggleVeWarnings(false); });
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || _veEl("veWarningsToggle").getAttribute("aria-expanded") !== "true") return;
  e.stopImmediatePropagation();
  toggleVeWarnings(false);
}, true);

// --- איפוס שדה: קליק ימני על שדה ששונה ---
function _veRowMenu() {
  let menu = _veEl("veRowMenu");
  if (menu) return menu;
  menu = document.createElement("div");
  menu.id = "veRowMenu";
  menu.className = "ve-menu ve-row-menu";
  menu.setAttribute("role", "menu");
  menu.hidden = true;
  document.body.appendChild(menu);
  return menu;
}

function _veOpenRowMenu(row, x, y) {
  const reset = row.querySelector(".ve-field-reset");
  if (!reset) return false;
  const menu = _veRowMenu();
  const btn = document.createElement("button");
  btn.type = "button";
  btn.setAttribute("role", "menuitem");
  btn.textContent = "↺ אפס לברירת המחדל";
  btn.onclick = () => { closeVeMenus(); reset.click(); };
  menu.replaceChildren(btn);
  closeVeMenus();
  menu.style.setProperty("--ve-ctx-x", Math.min(x, window.innerWidth - 230) + "px");
  menu.style.setProperty("--ve-ctx-y", Math.min(y, window.innerHeight - 60) + "px");
  menu.hidden = false;
  btn.focus();
  return true;
}

function _veOnRowContextMenu(e) {
  const row = e.target.closest("#veCategories .ve-row.ve-row-changed");
  if (!row) return;
  let x = e.clientX, y = e.clientY;
  if (!x && !y) {  // מקלדת (Shift+F10 / מקש התפריט) - ליד השדה עצמו
    const rect = row.getBoundingClientRect();
    x = rect.left + 20; y = rect.bottom;
  }
  if (_veOpenRowMenu(row, x, y)) e.preventDefault();
}

// --- הנגן מציג פריים ברגע שנטענת תיקייה (נגן חי, עצור על הפריים הראשון) ---
function _veAutoFrame(names) {
  if (!names || !names.length || !state.folder) return;
  if (_veLoadPref("veAutoFrame", true) === false) return;
  if (_veEl("videoEditorOptions").hidden || !_veEl("vePreviewStageWrap").hidden || _veInClipMode()) return;
  startVeLivePreview();
}

// --- בורר סוג התצוגה (חי / פריים / קטע) משקף את מה שמוצג בפועל ---
function _veSyncPreviewModeButtons() {
  const stageShown = !_veEl("vePreviewStageWrap").hidden;
  const live = stageShown && _veInLiveMode();
  const clip = stageShown && _veInClipMode();
  const frame = stageShown && !live && !clip && !!_veEl("vePreviewAfter").getAttribute("src");
  _veEl("veLiveBtn").setAttribute("aria-pressed", String(live));
  _veEl("veFrameBtn").setAttribute("aria-pressed", String(frame));
  _veEl("vePreviewClipBtn").setAttribute("aria-pressed", String(clip));
}

// --- תור: חיפוש לפי שם + סינון מתקפל ---
function _veQueueMatchesSearch(item) {
  const query = (_veEl("veQueueSearch").value || "").trim().toLowerCase();
  return !query || item.name.toLowerCase().includes(query);
}

function applyVeQueueSearch() {
  const query = (_veEl("veQueueSearch").value || "").trim().toLowerCase();
  for (const row of document.querySelectorAll("#veQueueList .ve-queue-row")) {
    row.hidden = !!query && !(row.dataset.name || "").toLowerCase().includes(query);
  }
}

function toggleVeQueueFilters(force) {
  const box = _veEl("veQueueFilters");
  const open = typeof force === "boolean" ? force : box.hidden;
  box.hidden = !open;
  _veEl("veQueueFilterBtn").setAttribute("aria-expanded", String(open));
}

function _veInitWave27() {
  _veRenderFolderChip();
  uiBus.on("ve:folder-changed", _veRenderFolderChip);
  uiBus.on("ve:preview-files", _veAutoFrame);
  _veEl("veCategories").addEventListener("contextmenu", _veOnRowContextMenu);
  const sync = () => _veSyncPreviewModeButtons();
  const observer = new MutationObserver(sync);
  observer.observe(_veEl("vePreviewStage"), {attributes: true, attributeFilter: ["class"]});
  observer.observe(_veEl("vePreviewStageWrap"), {attributes: true, attributeFilter: ["hidden"]});
  observer.observe(_veEl("vePreviewAfter"), {attributes: true, attributeFilter: ["src"]});
  sync();
  // מסננים שכבר מולאו (למשל אחרי ריענון) - הפאנל נשאר פתוח כדי שיראו אותם
  if (_veEl("veQueueFilterSince").value || _veEl("veQueueFilterMinSeconds").value || _veEl("veQueueFilterNotCreated").checked) toggleVeQueueFilters(true);
}
