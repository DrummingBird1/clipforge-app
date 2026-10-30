// ============================================================================
// גל 13 - פריסת סטודיו ומסך "עבודות":
//  * הסטודיו: העורך תופס את כל החלון (בלי רשימת הסקריפטים וההיסטוריה). ברוחב
//    רחב זו פריסה מקצועית בשלוש עמודות - קבצים | נגן + ציר-זמן | מפקח (ההגדרות).
//    גל 31: העורך נפתח תמיד בסטודיו - הפריסה השנייה (בתוך עמוד הסקריפטים) הוסרה.
//  * מפקח: לחיצה על ידית (לוגו/PiP/שכבה) בנגן פותחת ומדגישה רק את ההגדרות שלה.
//  * 📋 עבודות: מסך בית - כל התיקיות שעבדת עליהן (פרויקטים), סטטוס הריצה האחרונה,
//    ותור הרינדור הנוכחי. "פתח" טוען את התיקייה עם הפרויקט שלה.
// ============================================================================

function _veFocusOn() { return document.body.classList.contains("ve-focus"); }

// גל 31: העורך תמיד בסטודיו - "כבוי" = סגירת העורך (חזרה למסך הבית)
function setVeFocus(on) {
  if (!on) { closeVeEditor(); return; }
  _veApplyFocus();
  _veEl("videoEditorOptions").scrollTop = 0;
  uiLoadLazy("studio_more").catch(() => {});   // 89-studio-more.js; נכשל - בלי התוספות, וננסה שוב בפתיחה הבאה
}

// כפתור ☰ בסרגל הסטודיו: מציג/מסתיר את סרגל הניווט הראשי בלי לצאת מהסטודיו
function toggleStudioNav() {
  if (!_veFocusOn()) return;
  document.body.classList.toggle("ve-nav-open");
  _veApplyFocus();
}

function closeVeEditor() {
  if (typeof goHome === "function") goHome();
  _veApplyFocus();
}

function _veApplyFocus() {
  // מצב מיקוד (בלי סרגל ניווט) רק כשהסטודיו גלוי *ובמסך הסקריפטים* - מעבר למסך אחר (פלטה, קיצור) חייב להחזיר את הניווט,
  // אחרת המשתמש נשאר במסך אחר בלי שום דרך לחזור (באג: "הסטודיו סוגר את התפריט ואי אפשר לפתוח אותו")
  const layout = document.querySelector('.layout[data-tab-panel="scripts"]');
  const on = !_veEl("videoEditorOptions").hidden && !!layout && !layout.hidden;
  document.body.classList.toggle("ve-focus", on);
  if (!on) document.body.classList.remove("ve-nav-open");
  const navBtn = document.getElementById("veNavBtn");
  if (navBtn) navBtn.setAttribute("aria-expanded", document.body.classList.contains("ve-nav-open") ? "true" : "false");
  _veApplyLayout();
  _veScheduleLiveRebuild();
}

// ה-DOM של העורך קיים תמיד; מסך מלא רק כשהעורך הוא הסקריפט הנבחר
const _selectScriptBeforeW13 = selectScript;
selectScript = function (...args) {
  const result = _selectScriptBeforeW13(...args);
  _veApplyFocus();
  return result;
};

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && _veFocusOn() && !document.querySelector(".modal-bg.show") && !_veIsTyping()) {
    if (!_veEl("veJobsView").hidden) { closeVeJobs(); return; }
  }
});

// --- מפקח: ידית בנגן -> ההגדרות של אותו פריט בלבד ---
function _veRevealInspectorFor(kind, index) {
  // גל 29: האובייקט נבחר גם בנגן, בציר-הזמן וברשימת השכבות (סרגל צף ליד הידית)
  _veSelected = {kind, index: kind === "layer" ? index : undefined};
  setTimeout(_veSyncSelection, 0);
  let target = null;
  if (kind === "logo") target = document.querySelector('.ve-layer-card[data-card="logo"]');
  else if (kind === "pip") target = document.querySelector('.ve-layer-card[data-card="pip"]');
  else if (kind === "layer") target = document.querySelectorAll("#veLayersRows .ve-layer-row")[index];
  if (!target) return;
  const area = target.closest("details.ve-category");
  if (area && !area.open) area.open = true;
  if (typeof _veRevealElement === "function") _veRevealElement(target);
  target.scrollIntoView({behavior: "smooth", block: "nearest"});
  for (const el of document.querySelectorAll(".ve-inspect-focus")) el.classList.remove("ve-inspect-focus");
  target.classList.add("ve-inspect-focus");
  setTimeout(() => target.classList.remove("ve-inspect-focus"), 2500);
}

// ציור-מחדש של הידיות (רענון נגזר אחרי כל שינוי) לא קורה באמצע גרירה - אחרת הידית
// שנגררת מוחלפת באחרת והגרירה "נופלת". מה שהתבקש בזמן הגרירה מצויר מיד אחריה.
let _veHandleDragActive = false;
let _veHandleRenderPending = false;
const _veRenderDragHandlesBeforeW13 = _veRenderDragHandles;
_veRenderDragHandles = function (...args) {
  if (_veHandleDragActive) { _veHandleRenderPending = true; return; }
  return _veRenderDragHandlesBeforeW13(...args);
};

const _veAttachHandleDragBeforeW13 = _veAttachHandleDrag;
_veAttachHandleDrag = function (handle) {
  _veAttachHandleDragBeforeW13(handle);
  handle.addEventListener("pointerdown", () => { _veHandleDragActive = true; });
  const release = () => {
    _veHandleDragActive = false;
    if (_veHandleRenderPending) { _veHandleRenderPending = false; setTimeout(() => _veRenderDragHandles(), 0); }
  };
  handle.addEventListener("pointerup", release);
  handle.addEventListener("pointercancel", release);
  handle.addEventListener("dblclick", () => _veRevealInspectorFor(handle.dataset.kind, parseInt(handle.dataset.index || "0", 10)));
  handle.addEventListener("pointerup", () => {
    // לחיצה (בלי גרירה) = בחירה -> המפקח מציג את הפריט
    if (!handle._movedSinceDown) _veRevealInspectorFor(handle.dataset.kind, parseInt(handle.dataset.index || "0", 10));
  });
  handle.addEventListener("pointerdown", () => { handle._movedSinceDown = false; });
  handle.addEventListener("pointermove", (e) => { if (e.buttons) handle._movedSinceDown = true; });
};

// --- 📋 עבודות ---
async function openVeJobs() {
  _veEl("veJobsView").hidden = false;
  _veEl("videoEditorOptions").classList.add("ve-jobs-open");
  _veEl("veJobsBtn").setAttribute("aria-pressed", "true");
  await refreshVeJobs();
}

function closeVeJobs() {
  _veEl("veJobsView").hidden = true;
  _veEl("videoEditorOptions").classList.remove("ve-jobs-open");
  _veEl("veJobsBtn").setAttribute("aria-pressed", "false");
}

function toggleVeJobs() { if (_veEl("veJobsView").hidden) openVeJobs(); else closeVeJobs(); }

function _veJobStatusBadge(run) {
  if (!run) return {text: "טרם הורץ", cls: ""};
  if (run.status === "running") return {text: "⏳ רץ", cls: "running"};
  if (run.status === "success" || run.status === "done" || run.success) {
    const created = run.files_created ?? (run.summary && run.summary.files_created);
    return {text: "✅ הושלם" + (created !== undefined ? ` (${created})` : ""), cls: "ok"};
  }
  return {text: "❌ נכשל", cls: "bad"};
}

async function refreshVeJobs() {
  const list = _veEl("veJobsList");
  uiSkeleton(list, 3, "card");
  let projects = [], runs = [], queue = {pending: 0};
  try {
    [projects, runs, queue] = await Promise.all([
      fetch("/api/editor_projects").then(r => r.json()).then(d => d.projects || []),
      fetch("/api/video_editor/runs").then(r => r.json()).then(d => Array.isArray(d) ? d : (d.runs || [])).catch(() => []),
      fetch("/api/queue_status").then(r => r.json()).catch(() => ({pending: 0})),
    ]);
  } catch (e) { list.innerHTML = '<div class="ve-field-msg bad">⚠️ טעינת הפרויקטים נכשלה</div>'; return; }
  const running = runs.find(r => r.status === "running");
  _veEl("veJobsQueue").textContent = running
    ? `🎬 רץ עכשיו: ${running.folder ? running.folder.split(/[\\/]/).pop() : ""}${queue.pending ? ` · ${queue.pending} ממתינות בתור` : ""}`
    : (queue.pending ? `🎬 ${queue.pending} ממתינות בתור` : "🎬 אין ריצה פעילה");
  list.innerHTML = "";
  if (!projects.length) {
    list.innerHTML = '<div class="ve-jobs-empty">עוד אין פרויקטים. בחר תיקייה - כל מה שתעשה בה נשמר אוטומטית כפרויקט.</div>';
    return;
  }
  const schema = await _veLoadSchema();
  for (const project of projects) {
    const lastRun = runs.find(r => r.folder && project.folder && r.folder.toLowerCase() === project.folder.toLowerCase());
    const badge = _veJobStatusBadge(lastRun);
    const card = document.createElement("div");
    card.className = "ve-job-card" + (project.folder === state.folder ? " ve-job-current" : "") + (project.folder_exists ? "" : " ve-job-missing");
    card.dataset.folder = project.folder;
    const title = document.createElement("div");
    title.className = "ve-job-title";
    title.textContent = "📁 " + (project.name || project.folder);
    const meta = document.createElement("div");
    meta.className = "ve-job-meta";
    const bits = [project.folder];
    if (project.profile_name) bits.push("🗂️ " + project.profile_name);
    if (project.brand_kit) bits.push("🎨 " + project.brand_kit);
    if (project.clip_edit_count) bits.push(`✂️ ${project.clip_edit_count} קליפים עם עריכה`);
    if (project.updated_at) bits.push("עודכן " + _veFormatProjectTime(project.updated_at));
    meta.textContent = bits.join(" · ");
    const chips = document.createElement("div");
    chips.className = "ve-chips";
    for (const id of project.targets || []) {
      const t = schema.targets[id];
      if (!t) continue;
      const chip = document.createElement("span");
      chip.className = "ve-chip";
      chip.textContent = `${t.icon} ${t.label}`;
      chips.appendChild(chip);
    }
    const status = document.createElement("span");
    status.className = "ve-job-status " + badge.cls;
    status.textContent = badge.text;
    const actions = document.createElement("div");
    actions.className = "ve-job-actions";
    const open = document.createElement("button");
    open.type = "button"; open.textContent = "📂 פתח"; open.disabled = !project.folder_exists;
    open.onclick = () => openVeJob(project.folder);
    const remove = document.createElement("button");
    remove.type = "button"; remove.textContent = "🗑️"; remove.title = "מחק את הפרויקט השמור (הקבצים עצמם לא נמחקים)";
    remove.setAttribute("aria-label", "מחק פרויקט");
    remove.onclick = async () => {
      if (!await veConfirm(`למחוק את הפרויקט השמור של "${project.name}"? (עריכות הקליפים והיעדים שלו - לא הסרטונים)`, {okLabel: "🗑️ מחק", danger: true})) return;
      await fetch("/api/editor_projects?folder=" + encodeURIComponent(project.folder), {method: "DELETE"});
      refreshVeJobs();
    };
    actions.append(open, remove);
    card.append(title, status, meta, chips, actions);
    list.appendChild(card);
  }
}

function openVeJob(folder) {
  const input = document.getElementById("folderInput");
  input.value = folder;
  input.dispatchEvent(new Event("change", {bubbles: true}));
  closeVeJobs();
}

function newVeJob() {
  closeVeJobs();
  openBrowser();
}

function _veInitWave13() {
  _veApplyFocus();
}
