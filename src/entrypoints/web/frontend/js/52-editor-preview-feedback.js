// ============================================================================
// גל 4 של 102-ההצעות: תצוגה מקדימה ומשוב (items 40-50)
// ============================================================================

Object.assign(VE_GENERIC_FIELDS, {
  silence_threshold_db: {id: "veSilenceThresholdDb", kind: "float", label: "סף שקט (dB)"},
  silence_min_duration: {id: "veSilenceMinDuration", kind: "float", label: "אורך שקט מינימלי"},
  remove_watermark_region: {id: "veRemoveWatermarkRegion", kind: "str", label: "אזור מחיקה מותאם"},
  include_subfolders: {id: "veIncludeSubfolders", kind: "bool", label: "כולל תתי-תיקיות"},
});
for (const key of ["silence_threshold_db", "silence_min_duration", "remove_watermark_region", "include_subfolders"]) {
  VE_FAVORITABLE_FIELDS[key] = {id: VE_GENERIC_FIELDS[key].id, label: VE_GENERIC_FIELDS[key].label};
}
Object.assign(VE_DEPENDENT_FIELDS, {
  veSilenceThresholdDb: () => _veIsChecked("veTrimSilence") || _veIsChecked("veRemoveMidSilence"),
  veSilenceMinDuration: () => _veIsChecked("veTrimSilence") || _veIsChecked("veRemoveMidSilence"),
});
VE_EMPTY_SUMMARY_TEXT.preview = "פריים מהפלט, בדיקת הגדרות, הערכת גודל וציר-זמן";

function _veFolderPath(name) {
  return state.folder ? state.folder.replace(/[\\/]+$/, "") + "/" + name : name;
}

// --- בחירת הקובץ לתצוגה המקדימה (מהתור, או מהתיקייה אם התור לא נטען) ---
async function _vePopulatePreviewFiles() {
  const select = document.getElementById("vePreviewFile");
  if (!select) return;
  const previous = select.value;
  let names = _veQueueState.length ? _veQueueState.filter(f => f.selected).map(f => f.name) : [];
  if (!names.length && state.folder) {
    try {
      const data = await (await fetch("/api/browse?path=" + encodeURIComponent(state.folder))).json();
      names = (data.files || []).map(f => f.name).filter(n => VE_VIDEO_EXTENSIONS.some(ext => n.toLowerCase().endsWith(ext)));
    } catch (e) { names = []; }
  }
  select.innerHTML = "";
  for (const name of names) {
    const option = document.createElement("option");
    option.value = name; option.textContent = name;
    select.appendChild(option);
  }
  if (names.includes(previous)) select.value = previous;
  uiBus.emit("ve:preview-files", names);
}

function _vePreviewRequestBody(extra) {
  return JSON.stringify({
    ..._collectRunOptions(), folder: state.folder,
    file: document.getElementById("vePreviewFile").value || null, ...(extra || {}),
  });
}

// item 40+41: תצוגה מקדימה מלאה + לפני/אחרי.
let _vePreviewInFlight = false;
let _vePreviewQueued = false;

async function refreshVePreview() {
  const status = document.getElementById("vePreviewStatus");
  if (!state.folder) { status.textContent = "⚠️ בחר תיקיית קלט קודם."; return; }
  if (_vePreviewInFlight) { _vePreviewQueued = true; return; }
  _vePreviewInFlight = true;
  status.className = "ve-field-msg";
  status.textContent = "⏳ מרנדר פריים עם ההגדרות הנוכחיות...";
  try {
    const res = await fetch("/api/video_editor/preview_frame", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: _vePreviewRequestBody({time: document.getElementById("vePreviewTime").value}),
    });
    const data = await res.json();
    if (!res.ok) {
      status.className = "ve-field-msg bad";
      status.textContent = "⚠️ " + (data.error || "התצוגה המקדימה נכשלה") + (data.detail ? "\n" + data.detail : "");
      return;
    }
    const wrap = document.getElementById("vePreviewStageWrap");
    const before = document.getElementById("vePreviewBefore");
    const after = document.getElementById("vePreviewAfter");
    after.src = data.after_url;
    before.src = data.before_url || data.after_url;
    wrap.hidden = false;
    applyVePreviewSplit();
    const notes = document.getElementById("vePreviewNotes");
    notes.innerHTML = "";
    for (const note of data.notes || []) {
      const li = document.createElement("li");
      li.textContent = note;
      notes.appendChild(li);
    }
    status.textContent = `✓ ${data.file} · ${_veFormatTime(data.time)} בפלט (מתוך ${_veFormatTime(data.output_seconds)}) · ${data.output_width}×${data.output_height}`;
  } catch (e) {
    status.className = "ve-field-msg bad";
    status.textContent = "⚠️ שגיאת רשת בתצוגה המקדימה";
  } finally {
    _vePreviewInFlight = false;
    if (_vePreviewQueued) { _vePreviewQueued = false; refreshVePreview(); }
  }
}

function applyVePreviewSplit() {
  const value = document.getElementById("vePreviewSplit").value;
  document.getElementById("vePreviewStage").style.setProperty("--ve-split", value + "%");
}

let _veAutoPreviewTimer = null;
function _veScheduleAutoPreview(e) {
  if (!document.getElementById("vePreviewAuto").checked) return;
  if (e && e.target && (e.target.closest("[data-cat=preview]") || e.target.closest("#veLogTail"))) return;
  clearTimeout(_veAutoPreviewTimer);
  _veAutoPreviewTimer = setTimeout(refreshVePreview, 1200);
}
document.getElementById("veCategories").addEventListener("change", _veScheduleAutoPreview);

// item 44: בדיקת הגדרות עם שגיאה ליד השדה.
function _veClearValidationMessages() {
  for (const el of document.querySelectorAll("#veCategories .ve-validate-msg")) el.remove();
}

async function runVeValidation() {
  const box = document.getElementById("veValidationBox");
  box.hidden = false;
  box.innerHTML = '<div>⏳ בודק הגדרות ושרשרת פילטרים מול ffmpeg...</div>';
  _veClearValidationMessages();
  // התוצאה חוזרת גם למי שחיכה לה ("תמיד לבדוק לפני ריצה"), אבל רק הבדיקה האחרונה מצוירת
  const request = uiLatest("ve:validate");
  let data;
  try {
    const res = await fetch("/api/video_editor/validate", {method: "POST", headers: {"Content-Type": "application/json"}, body: _vePreviewRequestBody()});
    data = await res.json();
  } catch (e) {
    if (request.current()) box.innerHTML = '<div class="bad">⚠️ שגיאת רשת בבדיקה</div>';
    return data;
  }
  if (!request.current()) return data;
  _veClearValidationMessages();
  box.innerHTML = "";
  const head = document.createElement("div");
  const hardErrors = Object.values(data.field_errors).filter(m => !m.startsWith("⚠️")).length;
  head.className = data.valid ? "ok" : "bad";
  head.textContent = data.valid
    ? `✅ ההגדרות תקינות${data.ffmpeg_checked ? " - גם שרשרת הפילטרים עברה בדיקה מול ffmpeg" : ""}`
    : `❌ נמצאו ${hardErrors + data.general.length} בעיות`;
  box.appendChild(head);
  let first = null;
  for (const [key, message] of Object.entries(data.field_errors)) {
    const meta = VE_FAVORITABLE_FIELDS[key];
    const el = meta && document.getElementById(meta.id);
    const line = document.createElement("div");
    line.textContent = `• ${meta ? meta.label : key}: ${message}`;
    line.style.cursor = meta ? "pointer" : "";
    if (meta) line.onclick = () => veScrollToField(key);
    box.appendChild(line);
    if (el) {
      const row = el.closest(".ve-row");
      const msg = document.createElement("div");
      msg.className = "ve-validate-msg" + (message.startsWith("⚠️") ? " warn" : "");
      msg.textContent = message;
      (row || el).after(msg);
      _veRevealElement(el);
      if (!first) first = el;
    }
  }
  for (const message of data.general) {
    const line = document.createElement("div");
    line.textContent = "• " + message;
    box.appendChild(line);
  }
  return data;
}

// item 46: הערכת גודל פלט + משך לכל קובץ.
let _veEstimateTotals = null;

async function runVeEstimate() {
  const box = document.getElementById("veEstimateBox");
  box.hidden = false;
  if (!state.folder) { box.textContent = "⚠️ בחר תיקיית קלט קודם."; return; }
  box.textContent = "⏳ מחשב...";
  const options = _collectRunOptions();
  const body = {...options, folder: state.folder, only_files: _veQueueSelectedFiles()};
  const request = uiLatest("ve:estimate");
  let res, data;
  try {
    res = await fetch("/api/video_editor/estimate", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body), signal: request.signal});
    data = await res.json();
  } catch (e) {
    if (!uiIsAbort(e)) box.textContent = "⚠️ ההערכה נכשלה";
    return;
  }
  if (!request.current()) return;
  if (!res.ok) { box.textContent = "⚠️ " + (data.error || "ההערכה נכשלה"); return; }
  _veEstimateTotals = {seconds: data.total_output_seconds, mb: data.total_output_mb};
  const table = document.createElement("table");
  table.innerHTML = "<thead><tr><th>קובץ</th><th>מקור</th><th>פלט</th><th>גודל משוער</th></tr></thead>";
  const tbody = document.createElement("tbody");
  for (const row of data.files) {
    const tr = document.createElement("tr");
    for (const text of [row.file, _veFormatTime(row.source_seconds), (row.exact ? "" : "≤ ") + _veFormatTime(row.output_seconds), `≈ ${_veFormatMb(row.output_mb)}`]) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  const foot = document.createElement("tfoot");
  const footRow = document.createElement("tr");
  for (const text of [`סה"כ (${data.files.length} קבצים${data.truncated ? ", 300 ראשונים" : ""})`, "", _veFormatTime(data.total_output_seconds), `≈ ${_veFormatMb(data.total_output_mb)}`]) {
    const td = document.createElement("td");
    td.textContent = text;
    footRow.appendChild(td);
  }
  foot.appendChild(footRow);
  table.appendChild(foot);
  box.innerHTML = "";
  box.appendChild(table);
  const hint = document.createElement("div");
  hint.className = "ve-field-msg";
  hint.textContent = "הערכה לפי קודק/רזולוציה/איכות - תוכן עם הרבה תנועה/רעש יוצא גדול יותר. \"≤\" = משך לפני הסרת שקט אוטומטית.";
  box.appendChild(hint);
  _veRefreshAllDerivedUi();
}

function _veFormatMb(mb) {
  return mb >= 1024 ? (mb / 1024).toFixed(2) + " GB" : Math.round(mb * 10) / 10 + " MB";
}

// item 42+43: ציר-זמן עם תמונות ממוזערות + גל-קול עם קו סף-השקט.
let _veTimeline = null;   // {path, duration}
let _veTimelineCursor = null;
let _veWaveformData = null;

async function loadVeTimeline() {
  const name = document.getElementById("vePreviewFile").value;
  const box = document.getElementById("veTimelineBox");
  const status = document.getElementById("veTimelineStatus");
  box.hidden = false;
  if (!state.folder || !name) { status.textContent = "⚠️ בחר תיקייה עם קובץ וידאו קודם."; return; }
  const path = _veFolderPath(name);
  status.className = "ve-field-msg";
  status.textContent = "⏳ טוען ציר-זמן...";
  // מעבר מהיר בין קבצים: רק ציר-הזמן (וגל-הקול) של הקובץ האחרון שנבחר מצויר
  const request = uiLatest("ve:timeline");
  let res, data;
  try {
    res = await fetch("/api/video_editor/timeline?count=16&path=" + encodeURIComponent(path), {signal: request.signal});
    data = await res.json();
  } catch (e) {
    if (!uiIsAbort(e)) status.textContent = "⚠️ טעינת ציר-הזמן נכשלה";
    return;
  }
  if (!request.current()) return;
  if (!res.ok) { status.textContent = "⚠️ " + (data.error || "טעינת ציר-הזמן נכשלה"); return; }
  _veTimeline = {path, duration: data.duration};
  document.getElementById("veTimelineImg").src = data.url;
  box.hidden = false;
  status.textContent = `🎞️ ${name} · ${_veFormatTime(data.duration)}`;
  _veRenderTimelineOverlays();
  _veWaveformData = null;
  drawVeWaveform();
  try {
    const wave = await (await fetch("/api/waveform?path=" + encodeURIComponent(path), {signal: request.signal})).json();
    if (!request.current()) return;
    if (!wave.error) { _veWaveformData = wave; drawVeWaveform(); }
    else document.getElementById("veWaveformStatus").textContent = "אין פס קול לקובץ הזה (או שלא ניתן לפענח אותו).";
  } catch (e) { /* בלי גל-קול */ }
}

function _veRenderTimelineOverlays() {
  const layer = document.getElementById("veTimelineOverlays");
  if (!_veTimeline || !layer) return;
  if (_veRangeDrag) { _veRangeDrag.renderPending = true; return; }  // גל 29: לא מחליפים טווח שנגרר עכשיו
  const d = _veTimeline.duration;
  const pct = (t) => `${Math.max(0, Math.min(100, t / d * 100))}%`;
  layer.innerHTML = "";
  const start = _veTimeValue("veTrimStart", 0);
  const length = _veTimeValue("veTrimDuration", null);
  const end = length === null ? d : Math.min(d, start + length);
  const addBlock = (cls, from, to) => {
    if (to <= from) return null;
    const el = document.createElement("div");
    el.className = cls;
    el.style.left = pct(from);
    el.style.width = `calc(${pct(to)} - ${pct(from)})`;
    layer.appendChild(el);
    return el;
  };
  addBlock("ve-tl-dim", 0, start);
  addBlock("ve-tl-dim", end, d);
  const ranges = _veRangesFromJson(document.getElementById("veRemoveRanges").value) || [];
  // גל 29: טווח להסרה נגרר (הזזה), הקצוות שלו משנים אורך, ולחיצה כפולה מוחקת אותו
  ranges.forEach((r, index) => {
    const el = addBlock("ve-tl-range", parseFloat(r.start), parseFloat(r.end));
    if (!el) return;
    el.dataset.index = String(index);
    el.title = "טווח להסרה - גרירה מזיזה, הקצוות משנים אורך, לחיצה כפולה מוחקת";
    for (const edge of ["start", "end"]) {
      const grip = document.createElement("span");
      grip.className = "ve-tl-edge";
      grip.dataset.edge = edge;
      el.appendChild(grip);
    }
  });
  const cursor = document.getElementById("veTimelineCursor");
  cursor.hidden = _veTimelineCursor === null;
  if (_veTimelineCursor !== null) cursor.style.left = pct(_veTimelineCursor);
}

document.getElementById("veTimeline").addEventListener("click", (e) => {
  if (!_veTimeline) return;
  const rect = e.currentTarget.getBoundingClientRect();
  _veTimelineCursor = Math.round(Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)) * _veTimeline.duration * 10) / 10;
  document.getElementById("veTimelineCursorText").textContent = `📍 ${_veFormatTime(_veTimelineCursor)} במקור`;
  _veRenderTimelineOverlays();
});

function veTimelineAction(kind) {
  if (_veTimelineCursor === null) { alert("לחץ קודם על ציר-הזמן כדי לבחור נקודה."); return; }
  const t = _veTimelineCursor;
  if (kind === "start") {
    const oldEnd = (() => { const len = _veTimeValue("veTrimDuration", null); return len === null ? null : _veTimeValue("veTrimStart", 0) + len; })();
    _veSetFieldValue(document.getElementById("veTrimStart"), String(t));
    if (oldEnd !== null) _veSetFieldValue(document.getElementById("veTrimDuration"), oldEnd > t ? String(Math.round((oldEnd - t) * 10) / 10) : "");
  } else if (kind === "end") {
    const start = _veTimeValue("veTrimStart", 0);
    if (t <= start) { alert("הסוף חייב להיות אחרי התחלת החיתוך."); return; }
    _veSetFieldValue(document.getElementById("veTrimDuration"), String(Math.round((t - start) * 10) / 10));
  } else if (kind === "range") {
    const input = document.getElementById("veRemoveRanges");
    const ranges = JSON.parse(input.value || "[]");
    ranges.push([t, Math.min(_veTimeline.duration, Math.round((t + 5) * 10) / 10)]);
    ranges.sort((a, b) => a[0] - b[0]);
    _veSetFieldValue(input, JSON.stringify(ranges));
    _veRenderRangesEditor(true);
  } else if (kind === "preview") {
    const start = _veTimeValue("veTrimStart", 0);
    document.getElementById("vePreviewTime").value = String(Math.max(0, Math.round((t - start) * 10) / 10));
    refreshVePreview();
  }
  _veRenderTimelineOverlays();
}

function drawVeWaveform() {
  const canvas = document.getElementById("veWaveformCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!_veWaveformData) return;
  const midY = canvas.height / 2;
  const fullScale = _veWaveformData.full_scale || _veWaveformData.max_peak || 1;
  const peaks = _veWaveformData.peaks;
  const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#4ade80";
  ctx.strokeStyle = accent;
  ctx.lineWidth = 1;
  const step = peaks.length / canvas.width;
  for (let x = 0; x < canvas.width; x++) {
    const peak = peaks[Math.min(peaks.length - 1, Math.floor(x * step))] || 0;
    const h = Math.min(1, peak / fullScale) * (midY - 3);
    ctx.beginPath(); ctx.moveTo(x, midY - h); ctx.lineTo(x, midY + h); ctx.stroke();
  }
  const db = parseFloat(document.getElementById("veSilenceThresholdDb").value || "-30");
  const threshold = Math.pow(10, db / 20) * (midY - 3);
  ctx.strokeStyle = "#f59e0b";
  ctx.setLineDash([5, 4]);
  for (const y of [midY - threshold, midY + threshold]) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke(); }
  ctx.setLineDash([]);
  document.getElementById("veWaveformStatus").textContent = `הקו הכתום = סף השקט (${db}dB) - מה שבתוך הרצועה נחשב שקט.`;
}

// item 50: בחירת אזור מחיקת-watermark בגרירת מלבן על פריים המקור.
let _veRegionDraft = null;   // [x, y, w, h] fractions
let _veRegionDrag = null;

function _veRegionText(region) {
  return region ? region.map(v => Math.round(v * 1000) / 10 + "%").join(", ") : "";
}

function _veSyncRegionField() {
  const raw = document.getElementById("veRemoveWatermarkRegion").value.trim();
  const parts = raw ? raw.split(",").map(Number) : null;
  const valid = parts && parts.length === 4 && parts.every(Number.isFinite);
  document.getElementById("veRemoveWatermarkRegionText").textContent = valid ? `x,y,רוחב,גובה = ${_veRegionText(parts)}` : "לא סומן (משתמש בפינה+גודל למעלה)";
  document.getElementById("veRegionClearBtn").hidden = !valid;
}

async function openVeRegionDialog() {
  const name = document.getElementById("vePreviewFile").value || (await (async () => { await _vePopulatePreviewFiles(); return document.getElementById("vePreviewFile").value; })());
  if (!state.folder || !name) { alert("בחר תיקיית קלט עם קובץ וידאו קודם."); return; }
  const raw = document.getElementById("veRemoveWatermarkRegion").value.trim();
  const parts = raw ? raw.split(",").map(Number) : null;
  _veRegionDraft = parts && parts.length === 4 && parts.every(Number.isFinite) ? parts : null;
  document.getElementById("veRegionModalBg").classList.add("show");
  await loadVeRegionFrame();
}

function closeVeRegionDialog() { document.getElementById("veRegionModalBg").classList.remove("show"); }

async function loadVeRegionFrame() {
  const name = document.getElementById("vePreviewFile").value;
  const info = document.getElementById("veRegionInfo");
  info.textContent = "⏳ טוען פריים...";
  const t = document.getElementById("veRegionTime").value;
  const res = await fetch(`/api/video_editor/source_frame?path=${encodeURIComponent(_veFolderPath(name))}&t=${encodeURIComponent(t)}`);
  const data = await res.json();
  if (!res.ok) { info.textContent = "⚠️ " + (data.error || "טעינה נכשלה"); return; }
  const img = document.getElementById("veRegionImg");
  img.onload = () => { _veDrawRegionRect(); info.textContent = `${name} · ${data.width}×${data.height} · ${_veFormatTime(data.time)}`; };
  img.src = data.url;
}

function _veDrawRegionRect() {
  const rect = document.getElementById("veRegionRect");
  if (!_veRegionDraft) { rect.hidden = true; return; }
  const [x, y, w, h] = _veRegionDraft;
  Object.assign(rect.style, {left: x * 100 + "%", top: y * 100 + "%", width: w * 100 + "%", height: h * 100 + "%"});
  rect.hidden = false;
}

function _veRegionPoint(e) {
  const box = document.getElementById("veRegionImg").getBoundingClientRect();
  return [Math.max(0, Math.min(1, (e.clientX - box.left) / box.width)), Math.max(0, Math.min(1, (e.clientY - box.top) / box.height))];
}

document.getElementById("veRegionStage").addEventListener("mousedown", (e) => {
  e.preventDefault();
  _veRegionDrag = _veRegionPoint(e);
  _veRegionDraft = [..._veRegionDrag, 0, 0];
  _veDrawRegionRect();
});
document.addEventListener("mousemove", (e) => {
  if (!_veRegionDrag) return;
  const [x2, y2] = _veRegionPoint(e);
  const [x1, y1] = _veRegionDrag;
  _veRegionDraft = [Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1)];
  _veDrawRegionRect();
});
document.addEventListener("mouseup", () => { _veRegionDrag = null; });

function saveVeRegion() {
  if (!_veRegionDraft || _veRegionDraft[2] < 0.005 || _veRegionDraft[3] < 0.005) { alert("גרור מלבן על אזור הלוגו קודם."); return; }
  _veSetFieldValue(document.getElementById("veRemoveWatermarkRegion"), _veRegionDraft.map(v => (Math.round(v * 10000) / 10000).toString()).join(","));
  _veSyncRegionField();
  closeVeRegionDialog();
}

function clearVeRegion() {
  _veSetFieldValue(document.getElementById("veRemoveWatermarkRegion"), "");
  _veRegionDraft = null;
  _veSyncRegionField();
}

// item 48: פאנל תוצאות בסוף ריצה.
let _veLastManifest = null;
const VE_STATUS_ICONS = {created: "✅", skipped: "⏭️", error: "❌", valid: "🧪✅", invalid: "🧪❌"};

async function openVeResults(manifestPath) {
  const res = await fetch("/api/video_editor/run_manifest?path=" + encodeURIComponent(manifestPath));
  if (!res.ok) return;
  _veShowResults(await res.json());
}

async function openVeLatestResults() {
  const res = await fetch("/api/video_editor/latest_manifest" + (state.folder ? "?folder=" + encodeURIComponent(state.folder) : ""));
  if (!res.ok) { alert("אין עדיין תוצאות ריצה" + (state.folder ? " לתיקייה הזו." : ".")); return; }
  _veShowResults(await res.json());
}

function _veShowResults(manifest) {
  _veLastManifest = manifest;
  const counts = manifest.counts || {};
  const parts = [];
  if (counts.files_created) parts.push(`✅ ${counts.files_created} נוצרו`);
  if (counts.skipped) parts.push(`⏭️ ${counts.skipped} דולגו`);
  if (counts.errors) parts.push(`❌ ${counts.errors} נכשלו`);
  if (counts.valid || counts.invalid) parts.push(`🧪 ${counts.valid || 0} תקינים / ${counts.invalid || 0} לא-תקינים`);
  const elapsed = manifest.elapsed_seconds ? ` · ${_veFormatTime(manifest.elapsed_seconds)} סה"כ` : "";
  document.getElementById("veResultsSummary").textContent = (parts.join(" · ") || "אין קבצים בריצה הזו") + elapsed;
  // גל 31: כרטיס לכל קובץ (נגן, מול המקור, תיקייה) - בתוך הסטודיו, לא בדיאלוג
  document.getElementById("veResultsList").replaceChildren(...(manifest.files || []).map(file => _veResultCard(manifest, file)));
  const failed = (manifest.files || []).filter(f => f.status === "error" || f.status === "invalid");
  const rerun = document.getElementById("veResultsRerunFailedBtn");
  rerun.disabled = !failed.length || manifest.mode === "concat";
  rerun.classList.toggle("ve-primary", !rerun.disabled);  // גל 31: כשיש נכשלים - זו הפעולה הראשית
  rerun.textContent = failed.length ? `🔁 הרץ שוב רק את ${failed.length} הנכשלים` : "🔁 הרץ שוב רק את הנכשלים";
  _veShowResultsPanel(true);
  uiBus.emit("ve:results-shown", manifest);
}

async function _veOpenFolder(path) {
  const res = await fetch("/api/open_folder", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({path})});
  if (!res.ok) alert((await res.json()).error || "פתיחת התיקייה נכשלה");
}

function openVeOutputFolder() {
  if (_veLastManifest) _veOpenFolder(_veLastManifest.output_dir || "");
}

function openVePlayer(path) {
  const player = document.getElementById("vePlayer");
  document.getElementById("vePlayerTitle").textContent = "▶ " + path.split(/[\\/]/).pop();
  player.src = "/api/video_editor/stream?path=" + encodeURIComponent(path);
  document.getElementById("vePlayerModalBg").classList.add("show");
  player.play().catch(() => {});
}

function closeVePlayer() {
  const player = document.getElementById("vePlayer");
  player.pause();
  player.removeAttribute("src");
  player.load();
  document.getElementById("vePlayerModalBg").classList.remove("show");
}

// "הרץ שוב רק את הנכשלים" - התור מסונן לנכשלים בלבד (רק קבצי תיקיית-השורש;
// קבצים בתתי-תיקיות לא ניתנים לסינון בתור, ראו --only-files) ומורץ מיד.
async function rerunVeFailedFiles() {
  if (!_veLastManifest) return;
  const failed = new Set((_veLastManifest.files || []).filter(f => f.status === "error" || f.status === "invalid").map(f => f.source));
  if (_veLastManifest.input_dir && state.folder !== _veLastManifest.input_dir) {
    state.folder = _veLastManifest.input_dir;
    document.getElementById("folderInput").value = state.folder;
    updateRunEnabled();
    _onVeFolderChanged();
  }
  await refreshVeQueue();
  let matched = 0;
  for (const item of _veQueueState) { item.selected = failed.has(item.name); if (item.selected) matched++; }
  if (!matched) { alert("הקבצים שנכשלו לא נמצאו בתיקיית השורש (אולי הם בתת-תיקייה, או שהועברו)."); return; }
  _veQueueDirty = true;
  _renderVeQueue();
  _veShowResultsPanel(false);
  if (await veConfirm(`להריץ שוב את ${matched} הקבצים שנכשלו, עם ההגדרות הנוכחיות?`, {okLabel: "▶ הרץ"})) runScript();
}

// item 49: זנב-לוג מסונן לעורך בתוך הפאנל.
const VE_LOG_TAIL_MAX = 400;
let _veLogTailLines = [];

function _veLogLineKind(line) {
  if (/\[(ERROR|INVALID)\]|נכשל|❌|Traceback|Error/i.test(line)) return "err";
  if (/\[WARNING\]|⚠️/.test(line)) return "warn";
  if (/\[(APPROVED|SUCCESS|VALID|REPORT)\]|✅/.test(line)) return "ok";
  if (/\[(INFO|SKIP)\]/.test(line)) return "info";
  return "other";
}

function _veRecordLogTail(lines) {
  for (const {line} of lines) {
    const text = String(line || "").replace(/\s+$/, "");
    if (!text) continue;
    _veLogTailLines.push({text, kind: _veLogLineKind(text)});
  }
  if (_veLogTailLines.length > VE_LOG_TAIL_MAX) _veLogTailLines = _veLogTailLines.slice(-VE_LOG_TAIL_MAX);
  if (document.getElementById("veLogTail").open) renderVeLogTail();
  const problems = _veLogTailLines.filter(l => l.kind === "err" || l.kind === "warn").length;
  document.getElementById("veLogTailCount").textContent = _veLogTailLines.length ? `(${_veLogTailLines.length} שורות${problems ? `, ${problems} אזהרות/שגיאות` : ""})` : "";
}

function renderVeLogTail() {
  const filter = document.getElementById("veLogTailFilter").value;
  const box = document.getElementById("veLogTailBox");
  const lines = _veLogTailLines.filter(l => filter === "all" || (filter === "errors" ? (l.kind === "err" || l.kind === "warn") : l.kind !== "other"));
  box.innerHTML = "";
  for (const l of lines.slice(-200)) {
    const span = document.createElement("div");
    span.className = l.kind;
    span.textContent = l.text;
    box.appendChild(span);
  }
  box.scrollTop = box.scrollHeight;
}

function clearVeLogTail() {
  _veLogTailLines = [];
  renderVeLogTail();
  document.getElementById("veLogTailCount").textContent = "";
}

document.getElementById("veLogTail").addEventListener("toggle", () => { if (document.getElementById("veLogTail").open) renderVeLogTail(); });

// item 47: התקדמות פר-קובץ (שם + %) בפס הצף - בריצה מקבילית כמה קבצים יחד.
let _veFileProgress = {};

function _veUpdateFileProgress(files, overallPct, eta) {
  for (const [name, pct] of Object.entries(files || {})) {
    _veFileProgress[name] = pct;
    if (pct >= 100) setTimeout(() => { if (_veFileProgress[name] >= 100) { delete _veFileProgress[name]; _veRenderStickyProgress(overallPct, eta); } }, 2500);
  }
  _veRenderStickyProgress(overallPct, eta);
}

function _veRenderStickyProgress(overallPct, eta) {
  const el = document.getElementById("veStickyProgress");
  if (!el || document.getElementById("videoEditorOptions").hidden) return;
  const active = Object.entries(_veFileProgress).filter(([, pct]) => pct < 100);
  const filesText = active.slice(0, 3).map(([name, pct]) => `${name.length > 26 ? name.slice(0, 24) + "…" : name} ${pct}%`).join(" · ");
  el.hidden = false;
  el.textContent = `⏳ ${overallPct}%` + (eta && overallPct < 100 ? ` · ${eta}` : "") + (filesText ? ` · ${filesText}` : "") + (active.length > 3 ? ` · +${active.length - 3}` : "");
  el.title = active.map(([name, pct]) => `${name}: ${pct}%`).join("\n");
}

function _veInitPreviewFeedback() {
  _veSyncRegionField();
  _vePopulatePreviewFiles();
  // גל 5: תור העיבוד
  _setupVeQueueDropZone();
  document.getElementById("veSaveQueueWithProfile").checked = !!_veLoadPref("veSaveQueueWithProfile", false);
}

