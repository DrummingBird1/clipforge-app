// ============================================================================
// גל 36: שכבות, ריצות ויצוא - קבוצות שכבות (הסתרה ונעילה לקבוצה), המיתוג כשורה נעולה
// בראש השכבות, יישור ופיזור + קווי עזר בנגן, שכבות מוכנות מובנות עם תצוגה, מרכז ריצות
// אחד (תור, היסטוריה ותוצאות), שמות ותגיות לריצות והשוואה בין שתיים, תזמון מהגיליון
// שלפני הריצה, "פתח את הפרויקט" מהתוצאות, תבניות יצוא שמורות, ויחידות + גרירה לשדות.
// ============================================================================

// --- קבוצות שכבות ---
async function setVeLayerGroup(index) {
  const layers = _veLayersValue();
  if (!layers[index]) return;
  const groups = [...new Set(layers.map(l => l.group).filter(Boolean))];
  const name = await vePrompt("קבוצה לשכבה (ריק = בלי קבוצה):", {value: layers[index].group || "", placeholder: groups.join(", ")});
  if (name === null || name === undefined) return;
  _veEditLayers((list) => {
    if (!list[index]) return false;
    const clean = String(name).trim().slice(0, 30);
    if (clean) list[index].group = clean; else delete list[index].group;
  });
}

function toggleVeGroupFlag(group, flag) {
  _veEditLayers((layers) => {
    const members = layers.filter(l => l.group === group);
    if (!members.length) return false;
    const on = !members.every(l => l[flag]);
    for (const layer of members) { if (on) layer[flag] = true; else delete layer[flag]; }
  });
}

function ungroupVe(group) {
  _veEditLayers((layers) => {
    const members = layers.filter(l => l.group === group);
    if (!members.length) return false;
    for (const layer of members) delete layer.group;
  });
}

function _veGroupHeader(group, layers) {
  const members = layers.filter(l => l.group === group);
  const row = document.createElement("div");
  row.className = "ve-ll-group";
  row.dataset.group = group;
  const name = document.createElement("span");
  name.className = "ve-ll-group-name";
  name.textContent = `📂 ${group} (${members.length})`;
  const tool = (text, label, pressed, action) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ve-ll-tool";
    b.textContent = text;
    b.title = label;
    b.setAttribute("aria-label", label);
    if (pressed !== null) b.setAttribute("aria-pressed", String(pressed));
    b.onclick = (e) => { e.stopPropagation(); action(); };
    return b;
  };
  const hidden = members.every(l => l.hidden), locked = members.every(l => l.locked);
  row.append(name,
    tool(hidden ? "🙈" : "👁", hidden ? "הצג את כל הקבוצה" : "הסתר את כל הקבוצה", !hidden, () => toggleVeGroupFlag(group, "hidden")),
    tool(locked ? "🔒" : "🔓", locked ? "שחרר את כל הקבוצה" : "נעל את כל הקבוצה", locked, () => toggleVeGroupFlag(group, "locked")),
    tool("✕", "פרק את הקבוצה (השכבות נשארות)", null, () => ungroupVe(group)));
  return row;
}

// נקרא מ-_veRenderLayersList (73-editor-surface.js): כותרת לפני כל רצף של שכבות מאותה קבוצה
function _veWithGroupHeaders(rows, layers) {
  const out = [];
  let previous = null;
  for (const row of rows) {
    const layer = layers[parseInt(row.dataset.index, 10)];
    const group = layer && layer.group;
    if (group && group !== previous) out.push(_veGroupHeader(group, layers));
    if (group) row.classList.add("ve-ll-in-group");
    previous = group || null;
    out.push(row);
  }
  return out;
}

// --- המיתוג כשורה נעולה בראש השכבות ---
function _veBrandRow() {
  const name = _veEl("veBrandKit") && _veEl("veBrandKit").value;
  if (!name) return null;
  const row = document.createElement("div");
  row.className = "ve-ll-row ve-ll-fixed ve-ll-brand";
  row.dataset.kind = "brand";
  row.title = "המיתוג חל על הסגנון כולו (לוגו, צבעים, גופן) - נערך בספרייה";
  const label = document.createElement("span");
  label.className = "ve-ll-name";
  label.textContent = `🏷️ מיתוג: ${name}`;
  const lock = document.createElement("span");
  lock.className = "ve-ll-lock-mark";
  lock.textContent = "🔒";
  lock.setAttribute("aria-label", "נעול");
  row.append(label, lock);
  row.addEventListener("click", () => openVeLibrary("brand"));
  return row;
}

// --- יישור ופיזור ---
const VE_PRESET_CENTERS = {
  "top-left": [0.1, 0.1], "top-center": [0.5, 0.1], "top-right": [0.9, 0.1], "center": [0.5, 0.5],
  "bottom-left": [0.1, 0.9], "bottom-center": [0.5, 0.9], "bottom-right": [0.9, 0.9],
};
const VE_ALIGN = {left: ["x", 0.1], hcenter: ["x", 0.5], right: ["x", 0.9], top: ["y", 0.1], vcenter: ["y", 0.5], bottom: ["y", 0.9]};

function _veLayerCenter(layer) {
  if (layer.position === "custom" && Number.isFinite(layer.x) && Number.isFinite(layer.y)) return [layer.x, layer.y];
  return VE_PRESET_CENTERS[layer.position] || VE_PRESET_CENTERS["bottom-center"];
}

function alignVeLayer(where) {
  if (!_veSelected || _veSelected.kind !== "layer") { uiToast("בחר שכבה קודם - בנגן, בציר-הזמן או ברשימה", "warn"); return; }
  const index = _veSelected.index;
  _veEditLayers((layers) => {
    const layer = layers[index];
    if (!layer || layer.locked) return false;
    const [axis, value] = VE_ALIGN[where];
    const [x, y] = _veLayerCenter(layer);
    Object.assign(layer, {position: "custom", x: axis === "x" ? value : x, y: axis === "y" ? value : y});
  });
}

function distributeVeLayers() {
  const now = typeof _veCurrentOutputTime === "function" ? _veCurrentOutputTime() : 0;
  _veEditLayers((layers) => {
    const shown = layers.filter(l => !l.hidden && !l.locked && l.type !== "video"
      && (Number(l.start) || 0) <= now && (l.end === null || l.end === undefined || l.end === "" || Number(l.end) > now));
    if (shown.length < 3) { uiToast("צריך לפחות 3 שכבות שמוצגות יחד ברגע הזה", "warn"); return false; }
    shown.sort((a, b) => _veLayerCenter(a)[0] - _veLayerCenter(b)[0]);
    const first = _veLayerCenter(shown[0])[0], last = _veLayerCenter(shown[shown.length - 1])[0];
    const [from, to] = last - first > 0.2 ? [first, last] : [0.15, 0.85];
    shown.forEach((layer, i) => {
      const y = _veLayerCenter(layer)[1];
      Object.assign(layer, {position: "custom", x: Math.round((from + (to - from) * i / (shown.length - 1)) * 1000) / 1000, y});
    });
  });
}

function toggleVeGuides() {
  const on = !_veLoadPref("veGuides", false);
  _veSavePref("veGuides", on);
  _veApplyGuides();
}

function _veApplyGuides() {
  const on = !!_veLoadPref("veGuides", false);
  _veEl("vePreviewStage").classList.toggle("ve-guides-on", on);
  _veEl("veGuidesBtn").setAttribute("aria-pressed", String(on));
}

// --- שכבות מוכנות מובנות (גם בלי מיתוג), עם תצוגה בספרייה ---
const VE_BUILTIN_READY = [
  {name: "כותרת תחתונה", layer: {type: "text", text: "שם · תפקיד", start: 1, end: 6, position: "bottom-left", font_size: 42, color: "#FFFFFF", box: true, animation: "slide", opacity: 1}},
  {name: "הירשמו לערוץ", layer: {type: "text", text: "🔔 הירשמו לערוץ", start: 0, end: 4, position: "top-center", font_size: 44, color: "#FFD400", box: true, animation: "fade", opacity: 1}},
  {name: "ספירה לאחור", layer: {type: "timer", text: "", start: 0, end: null, position: "top-right", font_size: 40, color: "#FFFFFF", box: true, animation: "none", timer_mode: "countdown", timer_seconds: null, opacity: 1}},
  {name: "תאריך ושעה", layer: {type: "timestamp", text: "", start: 0, end: null, position: "bottom-right", font_size: 30, color: "#FFFFFF", box: true, animation: "none", opacity: 0.85}},
];

function _veReadyPreview(layer) {
  const box = document.createElement("span");
  box.className = "ve-ready-preview";
  box.dataset.position = layer.position || "bottom-center";
  const sample = document.createElement("span");
  sample.className = "ve-ready-sample" + (layer.box ? " ve-ready-box" : "");
  sample.textContent = layer.type === "timer" ? "0:42" : layer.type === "timestamp" ? "15.10 12:30" : layer.type === "image" ? "🖼️" : (layer.text || "Aa").slice(0, 18);
  sample.style.color = layer.color || "";
  box.appendChild(sample);
  return box;
}

function _veAddReadyLayer(tpl) {
  const layers = _veLayersValue();
  layers.push({...JSON.parse(JSON.stringify(tpl.layer)), ..._veClipLayerTag()});
  _veWriteLayers(layers);
  _veRenderLayersEditor(true);
  uiToast(`➕ "${tpl.name}" נוסף לשכבות`, "ok");
}

// --- מרכז ריצות: תור, היסטוריה ותוצאות במקום אחד ---
async function refreshVeRunsHub() {
  const queue = _veEl("veHubQueue"), history = _veEl("veHubHistory"), results = _veEl("veHubResults");
  if (!queue) return;
  try {
    const data = await (await fetch("/api/render_queue")).json();
    queue.textContent = (data.running ? `🎬 רץ: ${data.running.label || data.running.script || ""}` : "אין ריצה פעילה")
      + (data.pending && data.pending.length ? ` · ${data.pending.length} ממתינות` : "") + (data.paused ? " · ⏸ מושהה" : "");
  } catch (e) { queue.textContent = "—"; }
  const runs = (typeof _veRunsCache !== "undefined" && _veRunsCache) || [];
  const last = runs[0];
  history.textContent = runs.length ? `${runs.length} ריצות · האחרונה ${(last.started_at || "").replace("T", " ").slice(0, 16)}` : "עוד אין ריצות";
  results.textContent = _veLastManifest ? `${(_veLastManifest.counts || {}).files_created || 0} נוצרו בריצה האחרונה` : "פתח את התוצאות האחרונות";
  _veSyncCompareButton();
}

// --- שמות ותגיות לריצות, והשוואה בין שתיים ---
const _veCompareRuns = new Set();

function _veRunLabelText(run) {
  const tags = (run.tags || []).map(t => "#" + t).join(" ");
  return [run.name, tags].filter(Boolean).join(" · ");
}

// נקרא מ-_renderVeRuns (56-editor-runs-automation.js) לכל שורה
function _veDecorateRunRow(row, run, main) {
  const label = _veRunLabelText(run);
  if (label) {
    const tag = document.createElement("div");
    tag.className = "ve-run-label";
    tag.textContent = "🏷️ " + label;
    main.prepend(tag);
  }
  const pick = document.createElement("label");
  pick.className = "ve-run-compare-pick";
  pick.title = "סמן שתי ריצות להשוואה";
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = _veCompareRuns.has(run.id);
  box.setAttribute("aria-label", "סמן להשוואה");
  box.onchange = () => {
    if (box.checked) _veCompareRuns.add(run.id); else _veCompareRuns.delete(run.id);
    while (_veCompareRuns.size > 2) _veCompareRuns.delete(_veCompareRuns.values().next().value);
    _renderVeRuns();
  };
  pick.append(box, document.createTextNode("⇆"));
  row.prepend(pick);
  row.appendChild(_veRcButton("✎", "שם ותגיות לריצה (#תגית)", () => labelVeRun(run.id)));
}

async function labelVeRun(runId) {
  const run = (_veRunsCache || []).find(r => r.id === runId);
  if (!run) return;
  const current = [run.name || "", ...(run.tags || []).map(t => "#" + t)].join(" ").trim();
  const text = await vePrompt("שם לריצה - אפשר להוסיף #תגיות:", {value: current});
  if (text === null || text === undefined) return;
  const tags = (String(text).match(/#[^\s#]+/g) || []).map(t => t.slice(1));
  const name = String(text).replace(/#[^\s#]+/g, "").trim();
  const res = await fetch(`/api/video_editor/runs/${encodeURIComponent(runId)}/label`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name, tags})});
  if (!res.ok) { uiToast("השמירה נכשלה", "warn"); return; }
  await loadVeRuns();
}

function _veSyncCompareButton() {
  const btn = _veEl("veHubCompareBtn");
  if (!btn) return;
  btn.disabled = _veCompareRuns.size !== 2;
  btn.textContent = _veCompareRuns.size === 2 ? "⇆ השווה את שתי הריצות" : `⇆ סמן ${2 - _veCompareRuns.size} ריצות להשוואה`;
}

function _veCompareValue(value) {
  if (value === undefined || value === null || value === "") return "—";
  if (typeof value === "boolean") return value ? "✓" : "✗";
  if (typeof value === "object") return JSON.stringify(value).slice(0, 60);
  return String(value).split(/[\\/]/).pop().slice(0, 60);
}

function openVeRunCompare() {
  const [a, b] = [..._veCompareRuns].map(id => (_veRunsCache || []).find(r => r.id === id));
  if (!a || !b) return;
  const rows = [
    ["ריצה", a.name || a.started_at, b.name || b.started_at],
    ["תיקייה", _veCompareValue(a.folder), _veCompareValue(b.folder)],
    ["סגנון", a.profile_name || "—", b.profile_name || "—"],
    ["נוצרו / נכשלו", `${a.files_created ?? "—"} / ${a.errors ?? 0}`, `${b.files_created ?? "—"} / ${b.errors ?? 0}`],
    ["משך", a.duration_seconds ? _veFormatTime(a.duration_seconds) : "—", b.duration_seconds ? _veFormatTime(b.duration_seconds) : "—"],
  ];
  const sa = a.settings || {}, sb = b.settings || {};
  const keys = [...new Set([...Object.keys(sa), ...Object.keys(sb)])].filter(k => JSON.stringify(sa[k] ?? null) !== JSON.stringify(sb[k] ?? null));
  for (const key of keys.sort()) rows.push([(VE_FAVORITABLE_FIELDS[key] || {}).label || key, _veCompareValue(sa[key]), _veCompareValue(sb[key])]);
  const table = document.createElement("table");
  table.className = "ve-run-compare-table";
  rows.forEach((cells, i) => {
    const tr = table.insertRow();
    tr.className = i < 5 ? "ve-compare-meta" : "ve-compare-diff";
    cells.forEach(text => { const td = tr.insertCell(); td.textContent = text; });
  });
  _veEl("veRunCompareNote").textContent = keys.length ? `${keys.length} הגדרות שונות` : "ההגדרות זהות";
  _veEl("veRunCompareBody").replaceChildren(table);
  _veEl("veRunCompareModalBg").classList.add("show");
}

function closeVeRunCompare() {
  _veEl("veRunCompareModalBg").classList.remove("show");
}

// --- תזמון מהגיליון שלפני הריצה ---
function scheduleFromVeRunSheet() {
  closeVeRunSheet();
  openVeScheduleDialog();
}

// --- "פתח את הפרויקט שיצר את זה" מהתוצאות ---
function _veSyncResultsProject(manifest) {
  const btn = _veEl("veResultsProjectBtn");
  const folder = manifest && manifest.input_dir;
  const norm = (p) => String(p || "").replace(/[\\/]+$/, "").toLowerCase();
  btn.hidden = !folder || norm(folder) === norm(state.folder);
  btn.dataset.folder = folder || "";
  btn.title = folder ? `טוען את ${folder} - ההגדרות של הפרויקט נטענות איתו` : "";
}

function openVeResultsProject() {
  const folder = _veEl("veResultsProjectBtn").dataset.folder;
  if (!folder) return;
  closeVeResults();
  _veEl("folderInput").value = folder;
  onFolderTyped();
}

// --- תבניות יצוא שמורות ---
const VE_EXPORT_TEMPLATE_SUBCATS = ["file", "naming", "extra-outputs"];

function _veExportValues() {
  const values = {};
  for (const key of VE_EXPORT_TEMPLATE_SUBCATS) {
    const sub = document.querySelector(`#veCategories .ve-subcat[data-subcat="${key}"]`);
    if (sub) for (const [field, , el] of _veSubcatFields(sub)) values[field] = _veFieldValue(el);
  }
  return values;
}

function _veRenderExportTemplates(selected) {
  const select = _veEl("veExportTemplate");
  const templates = _veLoadPref("veExportTemplates", {});
  const names = Object.keys(templates).sort((a, b) => a.localeCompare(b, "he"));
  select.replaceChildren(new Option("— תבנית יצוא —", ""), ...names.map(n => new Option(`📦 ${n}`, n)));
  select.value = selected && names.includes(selected) ? selected : "";
  _veEl("veExportTemplateDelete").hidden = !select.value;
}

async function saveVeExportTemplate() {
  const name = ((await vePrompt("שם לתבנית היצוא (קודק, מיכל, איכות, שמות וקבצים נוספים):", {value: _veEl("veExportTemplate").value})) || "").trim().slice(0, 40);
  if (!name) return;
  const templates = _veLoadPref("veExportTemplates", {});
  templates[name] = _veExportValues();
  _veSavePref("veExportTemplates", templates);
  _veRenderExportTemplates(name);
  uiToast(`📦 התבנית "${name}" נשמרה`, "ok");
}

function applyVeExportTemplate(name) {
  const values = _veLoadPref("veExportTemplates", {})[name];
  _veEl("veExportTemplateDelete").hidden = !values;
  if (!values) return;
  for (const [field, value] of Object.entries(values)) {
    const meta = VE_FAVORITABLE_FIELDS[field];
    const el = meta && _veEl(meta.id);
    if (el && _veFieldValue(el) !== value) _veApplyFieldValue(el, value);
  }
  uiToast(`📦 הוחלה התבנית "${name}"`, "ok");
}

async function deleteVeExportTemplate() {
  const name = _veEl("veExportTemplate").value;
  if (!name || !(await veConfirm(`למחוק את תבנית היצוא "${name}"?`, {danger: true, okLabel: "🗑️ מחק"}))) return;
  const templates = _veLoadPref("veExportTemplates", {});
  delete templates[name];
  _veSavePref("veExportTemplates", templates);
  _veRenderExportTemplates("");
}

// --- יחידות עקביות, וגרירה על היחידה משנה את המספר ---
const VE_FIELD_UNITS = {
  veSilenceMinDuration: "שנ'", veHighlightBefore: "שנ'", veHighlightAfter: "שנ'", veWatermarkMoveSeconds: "שנ'",
  veProgressBarHeight: "px", veFrameThickness: "px", veCaptionFontSize: "px", veCustomWidth: "px", veCustomHeight: "px",
  veGifWidth: "px", veGifFps: "fps", veLoudnormTarget: "LUFS",
};

function _veScrubUnit(unit, input) {
  unit.classList.add("ve-scrub");
  unit.title = "↔ גרירה משנה את הערך (Shift = מהר, Alt = עדין)";
  unit.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || input.disabled) return;
    const startX = e.clientX;
    const start = parseFloat(input.value || input.placeholder) || 0;
    const step = parseFloat(input.step) || 1;
    const min = input.min !== "" ? parseFloat(input.min) : -Infinity, max = input.max !== "" ? parseFloat(input.max) : Infinity;
    unit.setPointerCapture(e.pointerId);
    const move = (ev) => {
      const factor = ev.shiftKey ? 10 : ev.altKey ? 0.1 : 1;
      const dx = (ev.clientX - startX) * (document.dir === "rtl" ? -1 : 1);
      const value = Math.max(min, Math.min(max, start + Math.round(dx / 4) * step * factor));
      const decimals = (String(step).split(".")[1] || "").length;
      _veSetFieldValue(input, decimals ? value.toFixed(decimals) : String(Math.round(value)));
    };
    unit.addEventListener("pointermove", move);
    unit.addEventListener("pointerup", () => unit.removeEventListener("pointermove", move), {once: true});
    e.preventDefault();
  });
}

function _veSetupUnits() {
  for (const [id, text] of Object.entries(VE_FIELD_UNITS)) {
    const input = _veEl(id);
    if (!input || (input.nextElementSibling && input.nextElementSibling.classList.contains("ve-unit"))) continue;
    const unit = document.createElement("span");
    unit.className = "ve-unit";
    unit.textContent = text;
    input.after(unit);
  }
  for (const unit of document.querySelectorAll("#veCategories .ve-unit")) {
    const input = unit.previousElementSibling;
    if (input && input.matches("input[type=number]") && !unit.classList.contains("ve-scrub")) _veScrubUnit(unit, input);
  }
}

function _veInitWave36() {
  _veApplyGuides();
  _veRenderExportTemplates("");
  _veSetupUnits();
  uiBus.on("ve:results-shown", (manifest) => { _veSyncResultsProject(manifest); refreshVeRunsHub(); });
  _veEl("veRunsDrawer").addEventListener("toggle", () => { if (_veEl("veRunsDrawer").open) refreshVeRunsHub(); });
}
