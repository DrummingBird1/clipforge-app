// 36-phone-screen.js - מסך "📱 בטלפון" (23.10.2026): מה שצריך מהטלפון, בכפתורים גדולים - מה רץ עכשיו (עם התקדמות),
// התור, קליפים שממתינים לאישור, והרצה חוזרת של ריצת סטודיו. נטען רק כשפותחים את המסך (LAZY_JS["phone"], lazy-html:phone);
// אחרי צימוד טלפון הוא המסך הראשון (/?screen=phone). הכול דרך routes קיימים: /api/render_queue, /api/stop|pause|resume,
// /api/render_queue/pause, /api/approvals, /api/video_editor/runs ו-rerun. מתרענן כל 5 שניות כשהמסך גלוי.
let _phoneTimer = null;
let _phoneProgress = null;
let _phoneRunning = false;

async function loadPhoneScreen() {
  if (!_phoneTimer) {
    _phoneTimer = setInterval(() => { if (_phoneVisible()) refreshPhoneScreen(); }, 5000);
    document.addEventListener("cf-progress", (e) => { _phoneProgress = e.detail; _renderPhoneProgress(); });
    document.addEventListener("cf-finished", () => { _phoneProgress = null; if (_phoneVisible()) refreshPhoneScreen(); });
  }
  await refreshPhoneScreen();
}

function _phoneVisible() {
  return !document.hidden && !document.querySelector('[data-tab-panel="phone"]').hidden;
}

async function _phoneGet(url) {
  try {
    const res = await fetch(url);
    return res.ok ? await res.json() : null;
  } catch (e) {
    return null;
  }
}

async function _phonePost(url, body) {
  const res = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "הפעולה נכשלה");
  return data;
}

function _phoneLine(text, className) {
  const line = document.createElement("div");
  if (className) line.className = className;
  line.textContent = text;
  return line;
}

function _phoneButton(label, onClick, danger) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = danger ? "phone-btn phone-danger" : "phone-btn";
  button.textContent = label;
  button.onclick = () => onClick(button);
  return button;
}

function _phoneName(folder) {
  return String(folder || "").split(/[\\/]/).filter(Boolean).pop() || folder || "";
}

async function refreshPhoneScreen() {
  const [queue, approvals, runs] = await Promise.all([_phoneGet("/api/render_queue"), _phoneGet("/api/approvals"), _phoneGet("/api/video_editor/runs")]);
  _renderPhoneNow(queue);
  _renderPhoneQueue(queue);
  _renderPhoneApprovals(approvals);
  _renderPhoneRuns(runs);
}

function _renderPhoneNow(queue) {
  const box = document.getElementById("phoneNow");
  const running = queue && queue.running;
  _phoneRunning = !!running;
  for (const id of ["phonePauseBtn", "phoneResumeBtn", "phoneStopBtn"]) document.getElementById(id).disabled = !running;
  if (!running) {
    _phoneProgress = null;
    box.replaceChildren(_phoneLine(queue ? "אין ריצה פעילה." : "אין חיבור לשרת.", "hint"));
    return;
  }
  const bar = document.createElement("progress");
  bar.id = "phoneProgress";
  bar.max = 100;
  const text = _phoneLine("", "hint");
  text.id = "phoneProgressText";
  const since = running.started_at ? "🕒 " + uiRelativeTime(new Date(running.started_at * 1000)) : "";
  box.replaceChildren(_phoneLine(running.script || "", "phone-title"), _phoneLine(since, "hint"), bar, text);
  _renderPhoneProgress();
}

function _renderPhoneProgress() {
  const bar = document.getElementById("phoneProgress");
  if (!bar) return;
  const pct = _phoneProgress && typeof _phoneProgress.pct === "number" ? _phoneProgress.pct : null;
  if (pct === null) bar.removeAttribute("value");
  else bar.value = pct;
  document.getElementById("phoneProgressText").textContent = pct === null ? "" : [`\u2066${Math.round(pct)}%\u2069`, _phoneProgress.eta].filter(Boolean).join(" · ");
}

function _renderPhoneQueue(queue) {
  const box = document.getElementById("phoneQueue");
  const paused = !!(queue && queue.paused);
  const button = document.getElementById("phoneQueueBtn");
  button.textContent = paused ? "▶️ הפעל את התור" : "⏸️ השהה את התור";
  button.dataset.paused = paused ? "1" : "";
  button.disabled = !queue;
  const items = ((queue && queue.pending) || []).map((item, i) => _phoneLine(`${i + 1}. ${item.label || _phoneName(item.folder)}`));
  if (paused) items.unshift(_phoneLine("⏸️ התור מושהה - משימה חדשה לא תתחיל עד שתפעיל אותו.", "hint"));
  if (!items.length) items.push(_phoneLine("התור ריק.", "hint"));
  box.replaceChildren(...items);
}

function _renderPhoneApprovals(rows) {
  const box = document.getElementById("phoneApprovals");
  if (!rows) {
    box.replaceChildren(_phoneLine("הטעינה נכשלה", "hint"));
    return;
  }
  if (!rows.length) {
    box.replaceChildren(_phoneLine("אין קליפים שממתינים לאישור.", "hint"));
    return;
  }
  box.replaceChildren(...rows.map((row) => {
    const card = document.createElement("div");
    card.className = "phone-approval";
    const video = document.createElement("video");
    Object.assign(video, {controls: true, preload: "none", playsInline: true});
    video.poster = "/api/clips/thumbnail?path=" + encodeURIComponent(row.path);
    video.src = "/api/clips/stream?path=" + encodeURIComponent(row.path);
    const actions = document.createElement("div");
    actions.className = "phone-actions";
    actions.append(_phoneButton("✅ אשר", () => phoneDecide(row.id, true, card)), _phoneButton("❌ דחה", () => phoneDecide(row.id, false, card), true));
    card.append(video, _phoneLine(row.game ? `${row.game} · ${row.name}` : row.name, "phone-title"), actions);
    return card;
  }));
}

function _renderPhoneRuns(data) {
  const box = document.getElementById("phoneRuns");
  const runs = ((data && data.runs) || []).filter((run) => run.status !== "running").slice(0, 5);
  if (!runs.length) {
    box.replaceChildren(_phoneLine(data ? "עוד אין ריצות של הסטודיו." : "הטעינה נכשלה", "hint"));
    return;
  }
  box.replaceChildren(...runs.map((run) => {
    const row = document.createElement("div");
    row.className = "phone-run";
    const icon = run.status === "success" ? "✅" : "❌";
    const info = document.createElement("div");
    info.append(_phoneLine(`${icon} ${_phoneName(run.folder)}`, "phone-title"),
      _phoneLine([run.profile_name, uiRelativeTime(run.started_at)].filter(Boolean).join(" · "), "hint"));
    const again = _phoneButton("🔁 הרץ שוב", () => phoneRerun(run));
    again.disabled = _phoneRunning;
    row.append(info, again);
    return row;
  }));
}

async function phoneRunAction(action) {
  try {
    await _phonePost(action === "pause" ? "/api/pause" : "/api/resume");
    uiToast(action === "pause" ? "⏸️ הריצה מושהית" : "▶️ הריצה ממשיכה", "ok");
  } catch (e) {
    uiToast(e.message, "warn");
  }
}

async function phoneStopRun() {
  if (!(await veConfirm("לעצור את הריצה? מה שכבר רונדר נשאר.", {danger: true, okLabel: "🛑 עצור"}))) return;
  try {
    await _phonePost("/api/stop");
    uiToast("🛑 הריצה נעצרה", "ok");
  } catch (e) {
    uiToast(e.message, "warn");
  }
  refreshPhoneScreen();
}

async function phoneToggleQueue() {
  const button = document.getElementById("phoneQueueBtn");
  try {
    await _phonePost("/api/render_queue/pause", {paused: !button.dataset.paused});
  } catch (e) {
    uiToast(e.message, "warn");
  }
  refreshPhoneScreen();
}

async function phoneDecide(id, approved, card) {
  for (const button of card.querySelectorAll("button")) button.disabled = true;
  try {
    await _phonePost(`/api/approvals/${encodeURIComponent(id)}/decide`, {approved});
    uiToast(approved ? "✅ אושר" : "❌ נדחה", "ok");
    card.remove();
    if (!document.querySelector("#phoneApprovals .phone-approval")) refreshPhoneScreen();
  } catch (e) {
    uiToast(e.message, "warn");
    for (const button of card.querySelectorAll("button")) button.disabled = false;
  }
}

async function phoneRerun(run) {
  if (!(await veConfirm(`להריץ שוב את ${_phoneName(run.folder)}?`, {okLabel: "🔁 הרץ שוב"}))) return;
  try {
    await _phonePost(`/api/video_editor/runs/${encodeURIComponent(run.id)}/rerun`);
    uiToast("🔁 הריצה התחילה", "ok");
  } catch (e) {
    uiToast(e.message, "warn");
  }
  refreshPhoneScreen();
}
