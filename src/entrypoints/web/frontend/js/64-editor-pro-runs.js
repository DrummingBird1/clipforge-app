// ============================================================================
// גל 14 - שגיאות עם פתרון בלחיצה, ותור רינדור מקצועי:
//  * כל קובץ שנכשל מקבל הסבר אנושי ("כרטיס המסך תפוס", "הדיסק מלא"...) וכפתורי
//    תיקון (נסה שוב בלי GPU / בלי מקבילות, הוצא מהתור, אפס שדה, בדוק הגדרות...).
//  * תור הרינדור (במסך העבודות): סדר, לראש התור, הוצאה, השהיה, "🌙 בלילה" (התור
//    ממתין עד 02:00), והמתנה אוטומטית כשהמחשב עסוק (משחק/סטרים/GPU בעומס).
// ============================================================================

// --- שגיאות ---
async function _veExplain(reason) {
  try {
    return await (await fetch("/api/video_editor/explain_error", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({reason})})).json();
  } catch (e) { return null; }
}

function _veFieldElementId(field) { return "ve" + field.split("_").map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(""); }

async function _veRerunFiles(names, mode) {
  if (_veLastManifest && _veLastManifest.input_dir && state.folder !== _veLastManifest.input_dir) {
    state.folder = _veLastManifest.input_dir;
    _veEl("folderInput").value = state.folder;
    updateRunEnabled();
    _onVeFolderChanged();
  }
  await refreshVeQueue();
  const wanted = new Set(names);
  let matched = 0;
  for (const item of _veQueueState) { item.selected = wanted.has(item.name); if (item.selected) matched++; }
  if (!matched) { alert("הקבצים לא נמצאו בתיקיית השורש (אולי הם בתת-תיקייה, או שהועברו)."); return; }
  _veQueueDirty = true;
  _renderVeQueue();
  if (mode === "cpu") {
    _veSetComposite("gpu", "off");
    const codec = _veEl("veCodec");
    if (codec.value !== "h264") _veSetFieldValue(codec, "h264");
  } else if (mode === "serial") {
    _veSetFieldValue(_veEl("veParallel"), "1");
  }
  _veShowResultsPanel(false);
  const note = mode === "cpu" ? " בלי GPU (H.264)" : mode === "serial" ? " בלי קידוד מקבילי" : "";
  if (await veConfirm(`להריץ שוב את ${matched} הקבצים${note}?`, {okLabel: "▶ הרץ"})) runScript();
}

async function _veRunFix(action, file) {
  const name = file && file.source;
  if (action.id === "retry") return _veRerunFiles([name], "");
  if (action.id === "retry_cpu") return _veRerunFiles([name], "cpu");
  if (action.id === "retry_serial") return _veRerunFiles([name], "serial");
  if (action.id === "skip") {
    await refreshVeQueue();
    const item = _veQueueState.find(f => f.name === name);
    if (item) { item.selected = false; _veQueueDirty = true; _renderVeQueue(); }
    _veShowResultsPanel(false);
    return;
  }
  if (action.id === "clear_field") {
    const id = _veFieldElementId(action.field);
    const el = _veEl(id);
    if (el) {
      const fallback = _veFieldDefaults && id in _veFieldDefaults ? _veFieldDefaults[id] : "";
      if (el.type === "checkbox") { el.checked = !!fallback; el.dispatchEvent(new Event("change", {bubbles: true})); }
      else _veSetFieldValue(el, fallback);
      if (typeof veScrollToField === "function") veScrollToField(action.field);
    }
    _veShowResultsPanel(false);
    return;
  }
  if (action.id === "validate") { _veShowResultsPanel(false); return runVeValidation(); }
  if (action.id === "open_folder") return openVeOutputFolder();
}

function _veExplanationBox(explanation, file) {
  const box = document.createElement("div");
  box.className = "ve-fix-box";
  const title = document.createElement("div");
  title.className = "ve-fix-title";
  title.textContent = "💡 " + explanation.title;
  const detail = document.createElement("div");
  detail.className = "ve-field-msg";
  detail.textContent = explanation.detail;
  const actions = document.createElement("div");
  actions.className = "ve-fix-actions";
  for (const action of explanation.actions || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = action.label;
    button.dataset.fix = action.id;
    button.onclick = () => _veRunFix(action, file);
    actions.appendChild(button);
  }
  box.append(title, detail, actions);
  if (explanation.raw) {
    const raw = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "פירוט טכני";
    const pre = document.createElement("pre");
    pre.textContent = explanation.raw;
    raw.append(summary, pre);
    box.appendChild(raw);
  }
  return box;
}

uiBus.on("ve:results-shown", (manifest) => {
  const rows = document.querySelectorAll("#veResultsList .ve-result-card");
  (manifest.files || []).forEach(async (file, index) => {
    if (file.status !== "error" && file.status !== "cancelled") return;
    const explanation = file.explanation || await _veExplain(file.reason);
    const row = rows[index];
    if (explanation && row) row.querySelector(".ve-result-main").appendChild(_veExplanationBox(explanation, file));
  });
});

// שגיאה בתצוגה המקדימה / בקטע - אותו הסבר, בלי "נסה שוב על הקובץ"
async function _veExplainPreviewError() {
  const status = _veEl("vePreviewStatus");
  const box = _veEl("vePreviewFix");
  box.innerHTML = "";
  if (!status.classList.contains("bad")) return;
  const explanation = await _veExplain(status.textContent);
  if (!explanation || explanation.id === "unknown") return;
  explanation.actions = (explanation.actions || []).filter(a => ["clear_field", "validate", "retry_cpu"].includes(a.id));
  box.appendChild(_veExplanationBox(explanation, null));
}
for (const name of ["refreshVePreview", "refreshVePreviewClip"]) {
  const original = window[name];
  window[name] = async function (...args) {
    const result = await original(...args);
    _veExplainPreviewError();
    return result;
  };
}

// --- תור הרינדור ---
async function refreshVeRenderQueue() {
  let data;
  try { data = await (await fetch("/api/render_queue")).json(); } catch (e) { return; }
  const list = _veEl("veRenderQueueList");
  list.innerHTML = "";
  _veEl("veQueuePauseBtn").textContent = data.paused ? "▶ המשך את התור" : "⏸ השהה את התור";
  _veEl("veQueuePauseBtn").dataset.paused = data.paused ? "1" : "";
  _veEl("veRenderQueueStatus").textContent = (data.running ? `🎬 רץ: ${data.running.script || ""}` : "אין ריצה פעילה")
    + (data.pending.length ? ` · ${data.pending.length} ממתינות` : "")
    + (data.paused ? (data.resume_at ? ` · ⏸ מושהה עד ${data.resume_at.slice(11, 16)}` : " · ⏸ מושהה") : "");
  data.pending.forEach((task, index) => {
    const row = document.createElement("div");
    row.className = "ve-list-row ve-rq-row";
    const label = document.createElement("span");
    label.textContent = `${index + 1}. ${task.priority === "high" ? "⚡ " : ""}${task.label || "משימה"}` + (task.folder ? ` - ${String(task.folder).split(/[\\/]/).pop()}` : "");
    const actions = document.createElement("div");
    actions.className = "ve-list-row-actions";
    for (const [text, direction, title] of [["⤒", "top", "לראש התור"], ["↑", "up", "למעלה"], ["↓", "down", "למטה"]]) {
      const button = document.createElement("button");
      button.type = "button"; button.textContent = text; button.title = title; button.setAttribute("aria-label", title);
      button.onclick = async () => { await fetch("/api/render_queue/move", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: task.id, direction})}); refreshVeRenderQueue(); };
      actions.appendChild(button);
    }
    const remove = document.createElement("button");
    remove.type = "button"; remove.textContent = "✕"; remove.setAttribute("aria-label", "הוצא מהתור");
    remove.onclick = async () => { await fetch("/api/render_queue/remove", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: task.id})}); refreshVeRenderQueue(); };
    actions.appendChild(remove);
    row.append(label, actions);
    list.appendChild(row);
  });
  const settings = data.settings || {};
  _veEl("veWaitWhenBusy").checked = !!settings.wait_when_busy;
  if (document.activeElement !== _veEl("veBusyProcesses")) _veEl("veBusyProcesses").value = (settings.processes || []).join(", ");
  if (document.activeElement !== _veEl("veBusyGpu")) _veEl("veBusyGpu").value = settings.gpu_percent ?? "";
}

async function toggleVeQueuePause() {
  const paused = !_veEl("veQueuePauseBtn").dataset.paused;
  await fetch("/api/render_queue/pause", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({paused})});
  refreshVeRenderQueue();
}

async function saveVeQueueSettings() {
  const res = await fetch("/api/render_queue/settings", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
    wait_when_busy: _veEl("veWaitWhenBusy").checked, processes: _veEl("veBusyProcesses").value, gpu_percent: _veEl("veBusyGpu").value,
  })});
  const data = await res.json();
  _veEl("veBusyNow").textContent = data.busy_now ? `עכשיו: ${data.busy_now} - רינדור חדש ימתין` : "המחשב פנוי עכשיו";
}

// "🌙 הרץ בלילה" - הריצה נכנסת לתור, והתור ממתין עד 02:00
async function runVeTonight() {
  closeVeMenus();
  const at = ((await vePrompt("באיזו שעה להתחיל? (HH:MM)", {value: "02:00"})) || "").trim();
  if (!at) return;
  const res = await fetch("/api/render_queue/pause", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({paused: true, until: at})});
  const data = await res.json();
  if (!res.ok) { alert(data.error || "תזמון נכשל"); return; }
  await runScript();
  appendLog(`🌙 הריצה בתור - התור מושהה ויתחיל ב-${(data.resume_at || at).slice(-5)}\n`);
}

// "⚡ לראש התור" נשלח עם הריצה (לא הגדרת פרופיל)
const _collectRunOptionsBeforeW14 = _collectRunOptions;
_collectRunOptions = function () {
  const options = _collectRunOptionsBeforeW14();
  if (options && "trim_start" in options && _veEl("veRunPriority") && _veEl("veRunPriority").checked) options.priority = "high";
  return options;
};
const _veComparableOptionsJsonBeforeW14 = _veComparableOptionsJson;
_veComparableOptionsJson = function () {
  const box = _veEl("veRunPriority");
  const was = box && box.checked;
  if (box) box.checked = false;
  try { return _veComparableOptionsJsonBeforeW14(); } finally { if (box) box.checked = was; }
};

const _openVeJobsBeforeW14 = openVeJobs;
openVeJobs = async function (...args) {
  const result = await _openVeJobsBeforeW14(...args);
  refreshVeRenderQueue();
  return result;
};

function _veInitWave14() {
  if (typeof _veInitWave14Timeline === "function") _veInitWave14Timeline();
  _veEl("veRunPriority").checked = false;
}
