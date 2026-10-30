// ============================================================================
// גל 8 של 102-ההצעות: ריצה, אוטומציה ואינטגרציה (items 90-96)
// ============================================================================

// --- 93/90/94: פעולות סוף-ריצה, פרסום משורשר, "תמיד לבדוק" - העדפות לכל צופה ---
const VE_RUN_PREF_IDS = ["veFinishOpenFolder", "veFinishSound", "veFinishSleep", "vePublishAfter", "vePublishDryRun", "veAlwaysValidate"];
for (const id of VE_RUN_PREF_IDS) {
  const el = document.getElementById(id);
  el.checked = !!_veLoadPref("runPref:" + id, false);
  el.addEventListener("change", () => { _veSavePref("runPref:" + id, el.checked); _veUpdateRunsSummary(); _veRenderWarnings(_veEvaluateRules()); });
}

// לא חלק מ-_collectRunOptions בכוונה: אלה העדפות-ריצה של הצופה, לא הגדרות פרופיל -
// אחרת סימון "תמיד לבדוק" היה מסמן את הפרופיל כ"לא-שמור".
function _veRunExtras() {
  return {
    finish_actions: {open_folder: _veIsChecked("veFinishOpenFolder"), sound: _veIsChecked("veFinishSound"), sleep: _veIsChecked("veFinishSleep")},
    publish_after: _veIsChecked("vePublishAfter"), publish_dry_run: _veIsChecked("vePublishDryRun"),
  };
}

function _veUpdateRunsSummary() {
  const el = document.getElementById("veCatSummary-runs");
  if (!el) return;
  const parts = [];
  if (_veIsChecked("vePublishAfter")) parts.push("🚀 פרסום");
  if (_veIsChecked("veFinishSleep")) parts.push("💤 שינה");
  if (_veIsChecked("veAlwaysValidate")) parts.push("🧪 בדיקה");
  el.textContent = " · " + (parts.join(" · ") || (_veRunsCache.length ? `${_veRunsCache.length} ריצות אחרונות` : "אין ריצות עדיין"));
}

VE_RULES.push(
  {cats: ["runs"], field: "publish_after", when: () => _veIsChecked("vePublishAfter") && !_veIsChecked("vePublishDryRun"), msg: "פרסום אמיתי אחרי הריצה - הפלטים יועלו אוטומטית (סמן 'ריצת ניסיון' לבדיקה בלי העלאה).", level: "info"},
  {cats: ["runs"], field: "finish_actions", when: () => _veIsChecked("veFinishSleep"), msg: "המחשב ייכנס למצב שינה דקה אחרי ריצה מוצלחת (אפשר לבטל מהבאנר).", level: "info"},
);

// item 94: "תמיד לבדוק לפני ריצה"
const _runScriptBeforeWave8 = runScript;
runScript = async function () {
  const isEditor = (state.selectedId || "").endsWith("video_editor.py");
  if (isEditor && _veIsChecked("veAlwaysValidate") && state.folder) {
    appendLog("🧪 בודק את ההגדרות ואת שרשרת הפילטרים לפני הריצה...\n");
    let data = null;
    try {
      const res = await fetch("/api/video_editor/validate", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({..._collectRunOptions(), folder: state.folder})});
      data = await res.json();
    } catch (e) { data = null; }
    if (data && !data.valid) {
      const problems = [...Object.values(data.field_errors || {}), ...(data.general || [])].slice(0, 8).join("\n• ");
      if (!(await veConfirm("⚠️ הבדיקה מצאה בעיות:\n• " + problems + "\n\nלהריץ בכל זאת?", {danger: true, okLabel: "הרץ בכל זאת"}))) return;
    }
  }
  await _runScriptBeforeWave8();
  if (isEditor && state.running) {
    _veStartRunControl();
    if (_veLazyDone.has("runs")) setTimeout(loadVeRuns, 500);
  }
};

// --- item 93: שינה למחשב (באנר עם ביטול) + צליל בדפדפן ---
let _veSleepTimer = null;

function _veShowSleepBanner(seconds) {
  let banner = document.getElementById("veSleepBanner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "veSleepBanner"; banner.className = "ve-sleep-banner"; banner.setAttribute("role", "alert");
    banner.innerHTML = '<span id="veSleepBannerText" style="flex:1"></span><button type="button" class="btn-stop" onclick="cancelVeSleep()">בטל שינה</button>';
    document.body.appendChild(banner);
  }
  let remaining = seconds;
  const tick = () => { document.getElementById("veSleepBannerText").textContent = `💤 הריצה הסתיימה - המחשב ייכנס למצב שינה בעוד ${remaining} שניות.`; };
  banner.hidden = false;
  tick();
  clearInterval(_veSleepTimer);
  _veSleepTimer = setInterval(() => { remaining -= 1; if (remaining <= 0) { clearInterval(_veSleepTimer); banner.hidden = true; } else tick(); }, 1000);
}

async function cancelVeSleep() {
  clearInterval(_veSleepTimer);
  const banner = document.getElementById("veSleepBanner");
  if (banner) banner.hidden = true;
  await fetch("/api/video_editor/cancel_sleep", {method: "POST"});
  appendLog("💤 מצב השינה בוטל.\n");
}

function _vePlayChime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [660, 880].forEach((freq, i) => {
      const osc = ctx.createOscillator(), gain = ctx.createGain();
      osc.frequency.value = freq; osc.connect(gain); gain.connect(ctx.destination);
      const t = ctx.currentTime + i * 0.18;
      gain.gain.setValueAtTime(0.0001, t); gain.gain.exponentialRampToValueAtTime(0.25, t + 0.02); gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.35);
      osc.start(t); osc.stop(t + 0.4);
    });
  } catch (e) { /* אין WebAudio - לא קריטי */ }
}

function _veOnRunFinished(msg) {
  _veStopRunControl();
  if (msg.finish_sound) _vePlayChime();
  if (msg.sleep_seconds) _veShowSleepBanner(msg.sleep_seconds);
  if (msg.publish_started) appendLog("🚀 הפרסום (Shorts) שורשר ורץ עכשיו על הפלטים של הריצה הזו.\n");
  if (msg.editor_run_id && _veLazyDone.has("runs")) loadVeRuns();
}

// --- items 95/96: שליטה בקבצים תוך ריצה ---
let _veRunControlPoll = null;
let _veRunControlState = {active: false, pause: [], cancel: [], priority: []};

function toggleVeRunControl(force) {
  const panel = document.getElementById("veRunControl");
  const show = force === undefined ? panel.hidden : force;
  panel.hidden = !show;
  document.getElementById("veRunControlBtn").setAttribute("aria-expanded", String(show));
  if (show) _refreshVeRunControl();
}

function _veStartRunControl() {
  document.getElementById("veRunControlBtn").hidden = false;
  clearInterval(_veRunControlPoll);
  _veRunControlPoll = setInterval(() => { if (!document.getElementById("veRunControl").hidden) _refreshVeRunControl(); }, 2000);
}

function _veStopRunControl() {
  clearInterval(_veRunControlPoll);
  _veRunControlPoll = null;
  document.getElementById("veRunControlBtn").hidden = true;
  toggleVeRunControl(false);
}

async function _refreshVeRunControl() {
  try { _veRunControlState = await (await fetch("/api/video_editor/run_control")).json(); }
  catch (e) { return; }
  _renderVeRunControl();
}

async function veRunControlAction(action, file) {
  const res = await fetch("/api/video_editor/run_control", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({action, file})});
  const data = await res.json();
  if (!res.ok) { alert(data.error || "הפעולה נכשלה"); return; }
  _veRunControlState = data;
  _renderVeRunControl();
}

function _veRcButton(label, title, onclick) {
  const btn = document.createElement("button");
  btn.type = "button"; btn.textContent = label; btn.title = title; btn.setAttribute("aria-label", title);
  btn.onclick = onclick;
  return btn;
}

function _renderVeRunControl() {
  const st = _veRunControlState;
  const activeBox = document.getElementById("veRunControlActive");
  const pendingBox = document.getElementById("veRunControlPending");
  activeBox.innerHTML = ""; pendingBox.innerHTML = "";
  if (!st.active) { activeBox.textContent = "אין ריצה פעילה."; return; }
  // שם הקובץ מתוך תווית ההתקדמות ("clip.mp4 (pass 2/2)" -> "clip.mp4")
  const running = [...new Set(Object.entries(_veFileProgress).filter(([, pct]) => pct < 100).map(([label]) => label.replace(/\s+\(pass \d\/\d\)$/, "")))];
  const paused = new Set(st.pause), cancelled = new Set(st.cancel);
  const title = document.createElement("div");
  title.className = "ve-field-msg"; title.textContent = running.length ? "פעילים עכשיו:" : "ממתין לקובץ הבא...";
  activeBox.appendChild(title);
  for (const name of running) {
    const row = document.createElement("div");
    row.className = "ve-rc-row" + (paused.has(name) ? " paused" : "") + (cancelled.has(name) ? " cancelled" : "");
    const label = document.createElement("span");
    label.className = "ve-rc-name"; label.textContent = `${name} · ${_veFileProgress[name] ?? 0}%`; label.title = name;
    row.appendChild(label);
    if (!cancelled.has(name)) {
      row.appendChild(paused.has(name)
        ? _veRcButton("▶ המשך", `המשך את ${name}`, () => veRunControlAction("resume", name))
        : _veRcButton("⏸ השהה", `השהה את ${name} (שאר הקבצים ממשיכים)`, () => veRunControlAction("pause", name)));
      row.appendChild(_veRcButton("✖ בטל", `בטל את ${name} בלבד`, async () => { if (await veConfirm(`לבטל את הקידוד של "${name}"? הפלט החלקי יימחק, שאר הקבצים ממשיכים.`, {danger: true})) veRunControlAction("cancel", name); }));
    }
    activeBox.appendChild(row);
  }
  const queued = (_veQueueState.length ? _veQueueState.filter(f => f.selected).map(f => f.name) : []).filter(n => !running.includes(n) && !cancelled.has(n) && !(n in _veFileProgress));
  if (!queued.length) return;
  const priority = st.priority || [];
  queued.sort((a, b) => {
    const ia = priority.indexOf(a), ib = priority.indexOf(b);
    return (ia < 0 ? 1e9 : ia) - (ib < 0 ? 1e9 : ib);
  });
  const qTitle = document.createElement("div");
  qTitle.className = "ve-field-msg"; qTitle.textContent = "ממתינים (לפי הסדר שבו יתחילו):";
  pendingBox.appendChild(qTitle);
  for (const name of queued.slice(0, 50)) {
    const row = document.createElement("div");
    row.className = "ve-rc-row" + (paused.has(name) ? " paused" : "");
    const label = document.createElement("span");
    label.className = "ve-rc-name"; label.textContent = (priority.includes(name) ? "⬆ " : "") + name;
    row.appendChild(label);
    row.appendChild(_veRcButton("⬆ הבא בתור", `${name} יתחיל ברגע שיתפנה מקום`, () => veRunControlAction("prioritize", name)));
    row.appendChild(paused.has(name)
      ? _veRcButton("▶", `בטל השהיה של ${name}`, () => veRunControlAction("resume", name))
      : _veRcButton("⏸", `אל תתחיל את ${name} עד שאמשיך`, () => veRunControlAction("pause", name)));
    row.appendChild(_veRcButton("✖ דלג", `דלג על ${name}`, () => veRunControlAction("cancel", name)));
    pendingBox.appendChild(row);
  }
}

// --- item 92: ריצות אחרונות ---
let _veRunsCache = [];

async function loadVeRuns() {
  try { _veRunsCache = (await (await fetch("/api/video_editor/runs")).json()).runs || []; }
  catch (e) { _veRunsCache = []; }
  _renderVeRuns();
  _veUpdateRunsSummary();
}

function _veRunStatusIcon(run) {
  return {running: "⏳", success: "✅", failed: "❌"}[run.status] || "•";
}

function _renderVeRuns() {
  const box = document.getElementById("veRunsList");
  if (!box) return;
  box.innerHTML = "";
  if (!_veRunsCache.length) {
    box.appendChild(_veEmptyState("🕘", "עוד אין ריצות", "אחרי הרצה היא מופיעה כאן - עם התוצאות, הרצה חוזרת וטעינת ההגדרות שלה"));
    return;
  }
  for (const run of _veRunsCache) {
    const row = document.createElement("div");
    row.className = "ve-run-row"; row.dataset.runId = run.id;
    const main = document.createElement("div");
    main.className = "ve-run-main";
    const folderName = (run.folder || "").split(/[\\/]/).filter(Boolean).pop() || run.folder;
    main.textContent = `${_veRunStatusIcon(run)} ${folderName}${run.profile_name ? " · " + run.profile_name : ""}`;
    main.title = run.folder;
    const meta = document.createElement("div");
    meta.className = "ve-run-meta";
    const counts = run.status === "running" ? "רץ עכשיו" : `${run.files_created ?? 0} נוצרו${run.errors ? ` · ${run.errors} נכשלו` : ""}${run.cancelled ? ` · ${run.cancelled} בוטלו` : ""}`;
    meta.textContent = `${(run.started_at || "").replace("T", " ")} · ${counts}${run.duration_seconds ? " · " + _veFormatTime(run.duration_seconds) : ""}`;
    main.appendChild(meta);
    row.appendChild(main);
    row.appendChild(_veRcButton("📂 טען", "טען את ההגדרות והתיקייה של הריצה הזו לפאנל", () => loadVeRunSettings(run.id)));
    row.appendChild(_veRcButton("▶ הרץ שוב", "הרץ שוב עם אותן הגדרות בדיוק על אותה תיקייה", () => rerunVeRun(run.id)));
    if (run.manifest_path) row.appendChild(_veRcButton("📋", "תוצאות הריצה", () => openVeResults(run.manifest_path)));
    row.appendChild(_veRcButton("✕", "הסר מההיסטוריה", async () => {
      if (!(await veConfirm("להסיר את הריצה מההיסטוריה? (הפלטים עצמם לא נמחקים)"))) return;
      await fetch(`/api/video_editor/runs/${encodeURIComponent(run.id)}`, {method: "DELETE"});
      loadVeRuns();
    }));
    _veDecorateRunRow(row, run, main);  // גל 36: שם ותגיות, סימון להשוואה
    box.appendChild(row);
  }
  _veSyncCompareButton();
}

function loadVeRunSettings(runId) {
  const run = _veRunsCache.find(r => r.id === runId);
  if (!run) return;
  _applyVideoEditorFields(run.settings || {});
  if (run.folder && run.folder !== state.folder) {
    state.folder = run.folder;
    document.getElementById("folderInput").value = run.folder;
    updateRunEnabled();
    _onVeFolderChanged();
  }
  appendLog(`📂 נטענו ההגדרות של הריצה מ-${(run.started_at || "").replace("T", " ")}.\n`);
}

async function rerunVeRun(runId) {
  if (state.running) { alert("כבר יש ריצה פעילה."); return; }
  const res = await fetch(`/api/video_editor/runs/${encodeURIComponent(runId)}/rerun`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(_veRunExtras())});
  const data = await res.json();
  if (!res.ok || data.error) { alert(data.error || "ההרצה נכשלה"); return; }
  state.running = true;
  state.veLastRunScript = "video/video_editor.py";
  _veFileProgress = {};
  document.getElementById("console").textContent = "";
  document.getElementById("runBtn").disabled = true;
  document.getElementById("stopBtn").disabled = false;
  document.getElementById("pauseBtn").disabled = false;
  appendLog("▶ מריץ שוב ריצה מההיסטוריה...\n");
  _veStartRunControl();
  loadVeRuns();
}

// --- item 91: תזמון ריצה מהעורך ---
function _veSyncScheduleFields() {
  const type = _veValue("veScheduleType");
  document.getElementById("veScheduleWeekday").hidden = type !== "weekly";
  document.getElementById("veScheduleTime").hidden = type === "interval_hours";
  document.getElementById("veScheduleHours").hidden = type !== "interval_hours";
}

function openVeScheduleDialog() {
  if (!state.folder) { alert("בחר תיקיית קלט קודם - המשימה המתוזמנת תרוץ עליה."); return; }
  document.getElementById("veScheduleFolder").textContent = `📁 ${state.folder}`;
  document.getElementById("veScheduleStatus").textContent = "";
  const profile = _currentVeProfileName();
  if (profile && !_veValue("veScheduleLabel")) document.getElementById("veScheduleLabel").value = profile;
  _veSyncScheduleFields();
  document.getElementById("veScheduleModalBg").classList.add("show");
}

async function saveVeSchedule() {
  const body = {
    folder: state.folder, options: _collectRunOptions(), schedule_type: _veValue("veScheduleType"),
    time_str: _veValue("veScheduleTime") || "03:00", weekday: _veValue("veScheduleWeekday"),
    interval_hours: parseInt(_veValue("veScheduleHours"), 10) || 24, label: _veValue("veScheduleLabel"),
  };
  const res = await fetch("/api/video_editor/schedule", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const data = await res.json();
  const status = document.getElementById("veScheduleStatus");
  if (!res.ok) { status.textContent = "⚠️ " + (data.error || "התזמון נכשל"); return; }
  status.textContent = "✅ נוסף לטאב המתזמן - ירוץ עם ההגדרות האלה בדיוק.";
  setTimeout(() => document.getElementById("veScheduleModalBg").classList.remove("show"), 900);
}


