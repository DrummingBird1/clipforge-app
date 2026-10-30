// ============================================================================
// גל 29: ציר-הזמן והנגן כמשטח העריכה - פסי השכבות וה-B-roll נגררים ומשנים אורך
// ישירות על ציר-הזמן (עם הצמדה), ציר-זמן גדול שמשנה גובה עם מסלולים קבועים, לחיצה
// על אובייקט פותחת את ההגדרות שלו, סרגל צף ליד האובייקט שנבחר בנגן (עם ידית שינוי
// גודל בפינה), רשימת שכבות אמיתית (שם, 👁, 🔒, שכפול, גרירה לסדר), וגרירת קבצים
// מהמחשב לנגן ולציר-הזמן.
// ============================================================================

let _veSelected = null;   // {kind: "logo"|"pip"|"layer", index?}
let _veBarDrag = null;    // גרירת פס בציר-הזמן שבעיצומה - {renderPending}

// --- זמנים: מיקום על ציר-הזמן (זמן מקור) <-> זמן הפלט שבו השכבות נמדדות ---
function _veSurfaceTimeline() {
  if (!_veTimeline || !_veTimeline.duration) return null;
  try { return _veLiveTimeline(_veLiveOptions(_veEl("vePreviewFile").value), _veTimeline.duration); }
  catch (e) { return null; }
}

function _veSourceAtX(clientX) {
  const rect = _veEl("veTimeline").getBoundingClientRect();
  return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)) * _veTimeline.duration;
}

// נקודות הצמדה בזמן הפלט: ראש-הניגון, קצוות שכבות אחרות, התחלה/סוף, וחילופי סצנה/שקט/שיאים
function _veLayerSnapPoints(timeline, skipIndex) {
  const points = [0, timeline.outDuration];
  if (_veTimelineCursor !== null) points.push(_veLiveSourceToOut(timeline, _veTimelineCursor));
  _veLayersValue().forEach((layer, i) => {
    if (i === skipIndex) return;
    points.push(Number(layer.start) || 0);
    if (layer.end !== null && layer.end !== undefined && layer.end !== "") points.push(Number(layer.end));
  });
  for (const t of _veSnapCandidates()) points.push(_veLiveSourceToOut(timeline, t));
  return points;
}

function _veSnapOut(value, points, timeline, altKey) {
  if (altKey || !_veEl("veTimelineSnap").checked) return {value, hit: null};
  const width = Math.max(1, _veEl("veTimeline").getBoundingClientRect().width);
  const tolerance = 8 / width * timeline.outDuration;
  let best = null;
  for (const p of points) if (Math.abs(p - value) <= tolerance && (best === null || Math.abs(p - value) < Math.abs(best - value))) best = p;
  return best === null ? {value, hit: null} : {value: best, hit: best};
}

function _veShowSnapLine(timeline, out) {
  const line = _veEl("veTlSnapLine");
  if (!line) return;
  line.hidden = out === null;
  if (out !== null) line.style.setProperty("--x", (_veLiveOutToSource(timeline, out) / _veTimeline.duration * 100) + "%");
}

// --- גרירת פס שכבה: גוף = הזזה, קצה = שינוי התחלה/סוף ---
function _veStartBarDrag(e, bar) {
  if (e.button !== 0) return;
  const index = parseInt(bar.dataset.index, 10);
  const layers = _veLayersValue();
  const layer = layers[index];
  const timeline = _veSurfaceTimeline();
  if (!layer || !timeline) return;
  if (layer.locked || _veClipModeLocksLayer(layer)) { _veSelectObject("layer", index); return; }
  const edge = e.target.closest(".ve-tl-edge");
  const mode = edge ? edge.dataset.edge : "move";
  const start0 = Number(layer.start) || 0;
  const open = layer.end === null || layer.end === undefined || layer.end === "";
  const end0 = open ? timeline.outDuration : Number(layer.end);
  const grab = _veLiveSourceToOut(timeline, _veSourceAtX(e.clientX));
  const points = _veLayerSnapPoints(timeline, index);
  let moved = false;
  _veBarDrag = {renderPending: false};
  bar.setPointerCapture(e.pointerId);
  e.preventDefault();
  e.stopPropagation();
  const round = (v) => Math.round(v * 10) / 10;
  const move = (ev) => {
    const now = _veLiveSourceToOut(timeline, _veSourceAtX(ev.clientX));
    if (!moved && Math.abs(ev.clientX - e.clientX) < 3) return;
    moved = true;
    let start = start0, end = end0, hit = null;
    if (mode === "move") {
      const length = end0 - start0;
      let s = Math.max(0, Math.min(timeline.outDuration - length, start0 + now - grab));
      const a = _veSnapOut(s, points, timeline, ev.altKey), b = _veSnapOut(s + length, points, timeline, ev.altKey);
      if (a.hit !== null) { s = a.value; hit = a.hit; } else if (b.hit !== null) { s = b.value - length; hit = b.hit; }
      start = s; end = s + length;
    } else if (mode === "start") {
      const snapped = _veSnapOut(Math.max(0, Math.min(end0 - 0.1, now)), points, timeline, ev.altKey);
      start = Math.min(end0 - 0.1, snapped.value); hit = snapped.hit;
    } else {
      const snapped = _veSnapOut(Math.max(start0 + 0.1, Math.min(timeline.outDuration, now)), points, timeline, ev.altKey);
      end = Math.max(start0 + 0.1, snapped.value); hit = snapped.hit;
    }
    bar.style.setProperty("--from", (_veLiveOutToSource(timeline, start) / _veTimeline.duration * 100) + "%");
    bar.style.setProperty("--width", Math.max(0.4, (_veLiveOutToSource(timeline, end) - _veLiveOutToSource(timeline, start)) / _veTimeline.duration * 100) + "%");
    bar.dataset.dragStart = String(round(start));
    bar.dataset.dragEnd = String(round(end));
    bar.classList.add("ve-tl-dragging");
    _veShowSnapLine(timeline, hit);
  };
  const finishDrag = () => {
    const pending = _veBarDrag && _veBarDrag.renderPending;
    _veBarDrag = null;
    return pending;
  };
  const up = () => {
    bar.removeEventListener("pointermove", move);
    _veShowSnapLine(timeline, null);
    const pending = finishDrag();
    if (!moved) { if (pending) _veRenderLayersTrack(); _veSelectObject("layer", index); return; }
    const fresh = _veLayersValue();
    const target = fresh[index];
    if (!target) return;
    target.start = parseFloat(bar.dataset.dragStart);
    // שכבה פתוחה (בלי סוף) נשארת פתוחה אם רק הוזזה עד הסוף; אחרת מקבלת סוף מפורש
    const newEnd = parseFloat(bar.dataset.dragEnd);
    target.end = open && mode === "start" ? null : (open && mode === "move" && newEnd >= timeline.outDuration - 0.05 ? null : newEnd);
    _veWriteLayers(fresh);
    _veRenderLayersEditor(true);
    _veSelectObject("layer", index, {quiet: true});
  };
  bar.addEventListener("pointermove", move);
  bar.addEventListener("pointerup", up, {once: true});
  bar.addEventListener("pointercancel", () => { bar.removeEventListener("pointermove", move); finishDrag(); _veRenderLayersTrack(); }, {once: true});
}

// --- בחירה: אובייקט אחד נבחר - מודגש בנגן, בציר-הזמן וברשימת השכבות ---
function _veSelectObject(kind, index, options) {
  _veSelected = {kind, index: kind === "layer" ? index : undefined};
  if (!(options && options.quiet)) _veRevealInspectorFor(kind, index || 0);
  _veSyncSelection();
}

function _veSyncSelection() {
  const sel = _veSelected;
  const same = (kind, index) => sel && sel.kind === kind && (kind !== "layer" || sel.index === index);
  for (const bar of document.querySelectorAll(".ve-tl-layer")) bar.classList.toggle("ve-selected", same("layer", parseInt(bar.dataset.index, 10)));
  for (const row of document.querySelectorAll("#veLayersList .ve-ll-row")) row.classList.toggle("ve-selected", same(row.dataset.kind, parseInt(row.dataset.index, 10)));
  let handle = null;
  for (const h of document.querySelectorAll("#veDragHandles .ve-drag-handle")) {
    const on = same(h.dataset.kind, parseInt(h.dataset.index || "-1", 10));
    h.classList.toggle("ve-selected", on);
    if (on) handle = h;
  }
  _veRenderObjectBar(handle);
}

// --- סרגל צף ליד האובייקט שנבחר בנגן + ידית שינוי גודל בפינה ---
const VE_SCALE_FIELDS = {logo: "veWatermarkScale", pip: "vePipScale"};

function _veObjectScale(kind, index) {
  if (VE_SCALE_FIELDS[kind]) return (parseFloat(_veEl(VE_SCALE_FIELDS[kind]).value) || (kind === "logo" ? 15 : 30)) / 100;
  const layer = _veLayersValue()[index] || {};
  if (layer.type === "image" || layer.type === "video") return Number(layer.scale) || (layer.type === "image" ? 0.2 : 0.35);
  return (Number(layer.font_size) || 48) / 240;  // טקסט/טיימר: גודל הגופן כ"קנה מידה"
}

function _veSetObjectScale(kind, index, scale) {
  const s = Math.max(0.02, Math.min(1, scale));
  if (VE_SCALE_FIELDS[kind]) { _veSetFieldValue(_veEl(VE_SCALE_FIELDS[kind]), String(Math.round(s * 100))); return; }
  const layers = _veLayersValue();
  const layer = layers[index];
  if (!layer) return;
  if (layer.type === "image" || layer.type === "video") layer.scale = Math.round(s * 100) / 100;
  else layer.font_size = Math.max(8, Math.min(300, Math.round(s * 240)));
  _veWriteLayers(layers);
  _veRenderLayersEditor(true);
}

function _veRenderObjectBar(handle) {
  let bar = _veEl("veObjectBar");
  if (!handle || _veEl("vePreviewStageWrap").hidden) { if (bar) bar.hidden = true; return; }
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "veObjectBar";
    bar.className = "ve-object-bar";
    bar.setAttribute("role", "toolbar");
    bar.setAttribute("aria-label", "פעולות על האובייקט שנבחר");
    _veEl("vePreviewStage").appendChild(bar);
  }
  const {kind, index} = _veSelected;
  // גל 30: במצב עריכת קליפ - PiP ושכבות של כל הקבצים נעולים
  const locked = _veTimeScope === "clip" && (kind === "pip" || (kind === "layer" && _veClipModeLocksLayer(_veLayersValue()[index])));
  bar.inert = locked;
  bar.classList.toggle("ve-clip-locked", locked);
  const buttons = [["⚙️", "הגדרות", () => _veRevealInspectorFor(kind, index || 0)]];
  if (kind === "layer") {
    buttons.push(["⧉", "שכפל", () => duplicateVeLayer(index)], ["👁", "הסתר", () => toggleVeLayerFlag(index, "hidden")]);
    buttons.push(["🗑", "מחק", () => deleteVeLayer(index)]);
  } else {
    buttons.push(["🗑", "הסר", () => { removeVeLayerCard(kind); _veSelected = null; _veSyncSelection(); }]);
  }
  bar.replaceChildren(...buttons.map(([icon, label, action]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = icon;
    b.title = label;
    b.setAttribute("aria-label", label);
    b.onclick = (e) => { e.stopPropagation(); action(); };
    return b;
  }));
  bar.style.setProperty("--x", (parseFloat(handle.dataset.x) * 100) + "%");
  bar.style.setProperty("--y", (parseFloat(handle.dataset.y) * 100) + "%");
  bar.hidden = false;
  // ידית שינוי גודל בפינת הידית שנבחרה
  if (!handle.querySelector(".ve-resize-corner")) {
    const corner = document.createElement("span");
    corner.className = "ve-resize-corner";
    corner.title = "גרור לשינוי גודל";
    corner.addEventListener("pointerdown", (e) => _veStartResize(e, corner));
    handle.appendChild(corner);
  }
}

function _veStartResize(e, corner) {
  e.preventDefault();
  e.stopPropagation();
  const {kind, index} = _veSelected || {};
  if (!kind) return;
  const stage = _veStage().getBoundingClientRect();
  const handle = corner.closest(".ve-drag-handle");
  const cx = stage.left + parseFloat(handle.dataset.x) * stage.width, cy = stage.top + parseFloat(handle.dataset.y) * stage.height;
  const startDistance = Math.max(4, Math.hypot(e.clientX - cx, e.clientY - cy));
  const startScale = _veObjectScale(kind, index);
  corner.setPointerCapture(e.pointerId);
  let scale = startScale;
  const move = (ev) => {
    scale = startScale * Math.hypot(ev.clientX - cx, ev.clientY - cy) / startDistance;
    handle.dataset.scale = String(Math.round(Math.max(0.02, Math.min(1, scale)) * 100));
  };
  corner.addEventListener("pointermove", move);
  corner.addEventListener("pointerup", () => {
    corner.removeEventListener("pointermove", move);
    _veSetObjectScale(kind, index, scale);
  }, {once: true});
}

// --- רשימת שכבות ---
const VE_FIXED_OBJECTS = [
  {kind: "logo", icon: "🏷️", label: "לוגו", active: () => _veHasText("veWatermarkPath"), name: () => String(_veValue("veWatermarkPath")).split(/[\\/]/).pop()},
  {kind: "pip", icon: "📺", label: "PiP", active: () => _veHasText("vePipPath"), name: () => String(_veValue("vePipPath")).split(/[\\/]/).pop()},
  {kind: "progress", icon: "▬", label: "סרגל התקדמות", active: () => _veIsChecked("veProgressBar"), name: () => ""},
  {kind: "frame", icon: "🖼️", label: "מסגרת", active: () => (parseInt(_veValue("veFrameThickness"), 10) || 0) > 0, name: () => ""},
  {kind: "removal", icon: "🧽", label: "מחיקת לוגו ישן", active: () => _veHasText("veRemoveWatermarkRegion") || _veHasText("veRemoveWatermarkPosition"), name: () => ""},
];

function _veLayerDefaultName(layer) {
  if (layer.type === "image" || layer.type === "video") return String(layer.path || "").split(/[\\/]/).pop() || (layer.type === "video" ? "B-roll" : "תמונה");
  if (layer.type === "text") return String(layer.text || "").trim().slice(0, 24) || "טקסט";
  return layer.type === "timer" ? "טיימר" : "חותמת-זמן";
}

function _veLayerRow(layer, index, count) {
  const row = document.createElement("div");
  row.className = "ve-ll-row" + (layer.hidden ? " ve-ll-hidden" : "") + (layer.locked ? " ve-ll-locked" : "");
  row.dataset.kind = "layer";
  row.dataset.index = String(index);
  row.draggable = true;
  const grip = document.createElement("span");
  grip.className = "ve-ll-grip";
  grip.textContent = "⋮⋮";
  grip.title = "גרור לשינוי הסדר (למעלה = מעל)";
  const icon = document.createElement("span");
  icon.textContent = VE_LAYER_KIND_ICONS[layer.type] || "🧩";
  const name = document.createElement("input");
  name.type = "text";
  name.className = "ve-ll-name";
  name.value = layer.name || "";
  name.placeholder = _veLayerDefaultName(layer);
  name.setAttribute("aria-label", "שם השכבה");
  name.addEventListener("change", () => {
    const layers = _veLayersValue();
    if (!layers[index]) return;
    if (name.value.trim()) layers[index].name = name.value.trim().slice(0, 40); else delete layers[index].name;
    _veWriteLayers(layers);
    _veLayersListSignature = _veLayersListSig();  // השורה כבר מציגה את השם - בלי לבנות את הרשימה מחדש
  });
  const clipTag = document.createElement("span");
  clipTag.className = "ve-ll-clip";
  clipTag.hidden = !layer.clip;
  clipTag.textContent = "🎬";
  clipTag.title = layer.clip ? `רק ל-${layer.clip}` : "";
  const time = document.createElement("span");
  time.className = "ve-ll-time";
  time.dir = "ltr";  // "0:02–0:04.5" - בלי היפוך של RTL
  time.textContent = `${_veFormatTime(Number(layer.start) || 0)}–${layer.end === null || layer.end === undefined || layer.end === "" ? "סוף" : _veFormatTime(Number(layer.end))}`;
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
  row.append(grip, icon, name, clipTag, time,
    tool(layer.hidden ? "🙈" : "👁", layer.hidden ? "הצג (השכבה לא מרונדרת)" : "הסתר בלי למחוק", !layer.hidden, () => toggleVeLayerFlag(index, "hidden")),
    tool(layer.locked ? "🔒" : "🔓", layer.locked ? "בטל נעילה" : "נעל (לא זז בגרירה)", !!layer.locked, () => toggleVeLayerFlag(index, "locked")),
    tool("📂", layer.group ? `בקבוצה "${layer.group}" - לשינוי` : "הכנס לקבוצה", null, () => setVeLayerGroup(index)),  // גל 36
    tool("⧉", "שכפל", null, () => duplicateVeLayer(index)),
    tool("✕", "מחק", null, () => deleteVeLayer(index)));
  row.addEventListener("click", (e) => { if (!e.target.closest("input, button")) _veSelectObject("layer", index); });
  row.addEventListener("dragstart", (e) => { e.dataTransfer.setData("text/x-ve-layer-index", String(index)); row.classList.add("dragging"); });
  row.addEventListener("dragend", () => row.classList.remove("dragging"));
  row.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("text/x-ve-layer-index")) { e.preventDefault(); row.classList.add("drag-over"); } });
  row.addEventListener("dragleave", () => row.classList.remove("drag-over"));
  row.addEventListener("drop", (e) => {
    row.classList.remove("drag-over");
    const from = parseInt(e.dataTransfer.getData("text/x-ve-layer-index"), 10);
    if (!Number.isInteger(from) || from === index) return;
    e.preventDefault();
    moveVeLayer(from, index);
  });
  if (count < 2) grip.hidden = true;
  if (_veClipModeLocksLayer(layer)) { row.classList.add("ve-clip-locked"); row.inert = true; }
  return row;
}

function _veFixedRow(object) {
  const row = document.createElement("div");
  row.className = "ve-ll-row ve-ll-fixed";
  row.dataset.kind = object.kind;
  const icon = document.createElement("span");
  icon.textContent = object.icon;
  const name = document.createElement("span");
  name.className = "ve-ll-name";
  name.textContent = object.label + (object.name() ? " · " + object.name() : "");
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "ve-ll-tool";
  remove.textContent = "✕";
  remove.title = "הסר";
  remove.setAttribute("aria-label", "הסר " + object.label);
  remove.onclick = (e) => { e.stopPropagation(); removeVeLayerCard(object.kind); };
  row.append(icon, name, remove);
  if (_veTimeScope === "clip" && object.kind !== "logo") { row.classList.add("ve-clip-locked"); row.inert = true; }
  row.addEventListener("click", (e) => {
    if (e.target.closest("button")) return;
    if (object.kind === "logo" || object.kind === "pip") _veSelectObject(object.kind);
    else addVeLayerCard(object.kind);
  });
  return row;
}

// השכבה העליונה (האחרונה במערך - מצוירת אחרונה) בראש הרשימה, כמו בתוכנות עריכה
let _veLayersListSignature = null;
const _veLayersListSig = () => JSON.stringify([_veLayersValue(), VE_FIXED_OBJECTS.map(o => o.active() && o.name()), _veValue("veBrandKit")]);

function _veRenderLayersList() {
  const box = _veEl("veLayersList");
  if (!box) return;
  const layers = _veLayersValue();
  // נבנית מחדש רק כשמשהו בה השתנה - ולא מתחת לשדה שם שמקלידים בו
  const signature = _veLayersListSig();
  if (signature === _veLayersListSignature) { _veSyncSelection(); return; }
  if (box.contains(document.activeElement) && document.activeElement.matches("input")) return;
  _veLayersListSignature = signature;
  // גל 36: כותרת לכל קבוצת שכבות, והמיתוג כשורה נעולה בראש הרשימה
  const rows = _veWithGroupHeaders(layers.map((layer, i) => _veLayerRow(layer, i, layers.length)).reverse(), layers);
  const brand = _veBrandRow();
  if (brand) rows.unshift(brand);
  for (const object of VE_FIXED_OBJECTS) if (object.active()) rows.push(_veFixedRow(object));
  if (!rows.length) rows.push(_veLayersEmptyState());  // גל 31: גרור תמונה לכאן או בחר שכבה מוכנה
  box.replaceChildren(...rows);
  _veSyncSelection();
}

function _veEditLayers(mutator) {
  const layers = _veLayersValue();
  if (mutator(layers) === false) return;
  _veWriteLayers(layers);
  _veRenderLayersEditor(true);
}

function toggleVeLayerFlag(index, flag) {
  _veEditLayers((layers) => {
    if (!layers[index]) return false;
    if (layers[index][flag]) delete layers[index][flag]; else layers[index][flag] = true;
  });
}

function duplicateVeLayer(index) {
  _veEditLayers((layers) => {
    if (!layers[index]) return false;
    const copy = JSON.parse(JSON.stringify(layers[index]));
    delete copy.locked;
    if (copy.name) copy.name = copy.name + " (עותק)";
    layers.splice(index + 1, 0, copy);
  });
  _veSelectObject("layer", index + 1, {quiet: true});
}

function deleteVeLayer(index) {
  _veEditLayers((layers) => { if (!layers[index]) return false; layers.splice(index, 1); });
  if (_veSelected && _veSelected.kind === "layer") _veSelected = null;
  _veSyncSelection();
}

function moveVeLayer(from, to) {
  _veEditLayers((layers) => {
    if (!layers[from] || to < 0 || to >= layers.length) return false;
    const [item] = layers.splice(from, 1);
    layers.splice(to, 0, item);
  });
}

// --- גרירת קבצים מהמחשב לנגן ולציר-הזמן ---
const VE_IMAGE_EXT = [".png", ".jpg", ".jpeg", ".webp", ".gif"];
const VE_AUDIO_EXT = [".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"];
const _veExtOf = (name) => (String(name).toLowerCase().match(/\.[a-z0-9]+$/) || [""])[0];

async function _veUploadAsset(file) {
  if (!state.folder) { uiToast("בחר קודם תיקייה (פרויקט)", "warn"); return null; }
  const res = await fetch(`/api/video_editor/upload_asset?folder=${encodeURIComponent(state.folder)}&name=${encodeURIComponent(file.name)}`, {method: "POST", body: file});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { uiToast("❌ " + (data.error || res.status), "bad"); return null; }
  return data.path;
}

function _veAddLayerAt(type, fields) {
  _veEditLayers((layers) => {
    const base = type === "video"
      ? {type, start: 0, end: null, position: "top-right", opacity: 1, path: "", source_in: 0, fit: "fill", scale: 0.35, audio: "mute", volume: 1}
      : {type, start: 0, end: null, position: "top-left", opacity: 1, path: "", scale: 0.2};
    layers.push(Object.assign(base, _veClipLayerTag(), fields));
  });
  _veSelectObject("layer", _veLayersValue().length - 1, {quiet: true});
}

// קובץ (מהמחשב או שורה מהתור) שנזרק על ציר-הזמן: וידאו = B-roll בזמן שבו נזרק (בקצוות = פתיח/סיום), שמע = פס-קול
async function _veDropOnTimeline(e) {
  const queueName = e.dataTransfer.getData("text/x-ve-queue-name");
  const file = e.dataTransfer.files && e.dataTransfer.files[0];
  if (!queueName && !file) return;
  e.preventDefault();
  const timeline = _veSurfaceTimeline();
  const rect = _veEl("veTimeline").getBoundingClientRect();
  const fraction = (e.clientX - rect.left) / Math.max(1, rect.width);
  const name = queueName || file.name;
  const ext = _veExtOf(name);
  const path = queueName ? _veFolderPath(queueName) : await _veUploadAsset(file);
  if (!path) return;
  if (VE_AUDIO_EXT.includes(ext)) {
    if (_veClipModeRefuses("פס-הקול")) return;
    _veSetComposite("audio", "file");
    _veSetFieldValue(_veEl("veReplaceAudioPath"), path);
    uiToast(`🎵 פס-הקול הוחלף - ${name}`, "ok");
    return;
  }
  if (!VE_VIDEO_EXTENSIONS.includes(ext)) { uiToast("לציר-הזמן אפשר לגרור וידאו או שמע", "warn"); return; }
  if ((fraction < 0.04 || fraction > 0.96) && !_veClipModeRefuses("פתיח/סיום")) {
    const id = fraction < 0.04 ? "veIntroPath" : "veOutroPath";
    _veSetFieldValue(_veEl(id), path);
    uiToast(fraction < 0.04 ? `🎬 פתיח - ${name}` : `🎬 סיום - ${name}`, "ok");
    return;
  }
  const at = timeline && _veTimeline ? Math.round(_veLiveSourceToOut(timeline, fraction * _veTimeline.duration) * 10) / 10 : 0;
  _veAddLayerAt("video", {path, start: at, end: Math.round((at + 5) * 10) / 10});
  uiToast(`🎞️ B-roll נוסף - ${_veFormatTime(at)}`, "ok");
}

// תמונה שנזרקה על הנגן: לוגו (אם אין) או מדבקה במקום שבו נזרקה; וידאו = PiP
async function _veDropOnPlayer(e) {
  const file = e.dataTransfer.files && e.dataTransfer.files[0];
  if (!file) return;
  e.preventDefault();
  const ext = _veExtOf(file.name);
  const isImage = VE_IMAGE_EXT.includes(ext), isVideo = VE_VIDEO_EXTENSIONS.includes(ext);
  if (!isImage && !isVideo) { uiToast("לנגן אפשר לגרור תמונה (לוגו/מדבקה) או וידאו (PiP)", "warn"); return; }
  const path = await _veUploadAsset(file);
  if (!path) return;
  const rect = _veStage().getBoundingClientRect();
  const x = Math.round(Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)) * 10000) / 10000;
  const y = Math.round(Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)) * 10000) / 10000;
  if (isVideo && _veTimeScope === "clip") {
    _veAddLayerAt("video", {path, position: "custom", x, y, fit: "pip"});  // PiP חל על כל הקבצים - בקליפ: B-roll בחלון
    uiToast(`🎞️ ${file.name} - רק לקליפ הזה`, "ok");
  } else if (isVideo) {
    _veSetFieldValue(_veEl("vePipPath"), path);
    _veEl("vePipX").value = String(x);
    _veSetFieldValue(_veEl("vePipY"), String(y));
    uiToast(`📺 PiP - ${file.name}`, "ok");
  } else if (!_veHasText("veWatermarkPath")) {
    _veSetFieldValue(_veEl("veWatermarkPath"), path);
    _veEl("veWatermarkX").value = String(x);
    _veSetFieldValue(_veEl("veWatermarkY"), String(y));
    uiToast(`🏷️ לוגו - ${file.name}`, "ok");
  } else {
    _veAddLayerAt("image", {path, position: "custom", x, y});
    uiToast("🖼️ מדבקה נוספה", "ok");
  }
  _veSyncLayerCards();
}

function _veSetupDropZones() {
  const zones = [[_veEl("veTimelineScroll"), _veDropOnTimeline, ["Files", "text/x-ve-queue-name"]], [_veStage(), _veDropOnPlayer, ["Files"]]];
  for (const [zone, handler, types] of zones) {
    if (!zone) continue;
    zone.addEventListener("dragover", (e) => {
      if (!types.some(t => e.dataTransfer.types.includes(t))) return;
      e.preventDefault();
      zone.classList.add("ve-drop-target");
    });
    zone.addEventListener("dragleave", (e) => { if (!zone.contains(e.relatedTarget)) zone.classList.remove("ve-drop-target"); });
    zone.addEventListener("drop", (e) => { zone.classList.remove("ve-drop-target"); handler(e); });
  }
}

// --- ציר-זמן גדול: גובה בגרירה ---
function _veSetupTimelineResizer() {
  const dock = _veEl("veTimelineDock");
  if (!dock || _veEl("veTlResizer")) return;
  const grip = document.createElement("div");
  grip.id = "veTlResizer";
  grip.className = "ve-tl-resizer";
  grip.title = "גרור כדי לשנות את גובה ציר-הזמן";
  grip.setAttribute("role", "separator");
  grip.setAttribute("aria-orientation", "horizontal");
  grip.setAttribute("aria-label", "גובה ציר-הזמן");
  grip.tabIndex = 0;
  dock.prepend(grip);
  const apply = (h) => {
    const height = Math.max(36, Math.min(220, Math.round(h)));
    dock.style.setProperty("--ve-tl-h", height + "px");
    return height;
  };
  apply(_veLoadPref("veTimelineHeight", 64));
  grip.addEventListener("pointerdown", (e) => {
    const startY = e.clientY;
    const start = parseFloat(getComputedStyle(dock).getPropertyValue("--ve-tl-h")) || 64;
    grip.setPointerCapture(e.pointerId);
    const move = (ev) => apply(start + (startY - ev.clientY));
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", (ev) => { grip.removeEventListener("pointermove", move); _veSavePref("veTimelineHeight", apply(start + (startY - ev.clientY))); }, {once: true});
  });
  grip.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    e.preventDefault();
    const now = parseFloat(getComputedStyle(dock).getPropertyValue("--ve-tl-h")) || 64;
    _veSavePref("veTimelineHeight", apply(now + (e.key === "ArrowUp" ? 12 : -12)));
  });
}

// --- טווחים להסרה: גרירה על ציר-הזמן (זמן מקור) ---
let _veRangeDragSwallowClick = false;
let _veRangeDrag = null;   // גרירת טווח שבעיצומה - {renderPending}
let _veLastRangeDown = null;  // לזיהוי לחיצה כפולה (הלחיצה הראשונה מזיזה את הסמן ומציירת את הטווחים מחדש)

function _veDeleteRange(index) {
  let ranges;
  try { ranges = JSON.parse(_veEl("veRemoveRanges").value || "[]"); } catch (err) { return; }
  ranges.splice(index, 1);
  _veSetFieldValue(_veEl("veRemoveRanges"), ranges.length ? JSON.stringify(ranges) : "");
  _veRenderRangesEditor(true);
  _veRenderTimelineOverlays();
}

function _veStartRangeDrag(e, el) {
  if (e.button !== 0 || e.shiftKey || !_veTimeline) return;
  const input = _veEl("veRemoveRanges");
  let ranges;
  try { ranges = JSON.parse(input.value || "[]"); } catch (err) { return; }
  const index = parseInt(el.dataset.index, 10);
  if (!Array.isArray(ranges[index])) return;
  e.preventDefault();
  e.stopPropagation();
  const now = performance.now();
  if (_veLastRangeDown && _veLastRangeDown.index === index && now - _veLastRangeDown.t < 450) {
    _veLastRangeDown = null;
    _veRangeDragSwallowClick = true;
    _veDeleteRange(index);
    return;
  }
  _veLastRangeDown = {index, t: now};
  const [a0, b0] = ranges[index].map(Number);
  const edge = e.target.closest(".ve-tl-edge");
  const mode = edge ? edge.dataset.edge : "move";
  const d = _veTimeline.duration;
  const grab = _veSourceAtX(e.clientX);
  const width = Math.max(1, _veEl("veTimeline").getBoundingClientRect().width);
  const tolerance = 8 / width * d;
  const points = [0, d, ..._veSnapCandidates()];
  if (_veTimelineCursor !== null) points.push(_veTimelineCursor);
  ranges.forEach((r, i) => { if (i !== index) points.push(Number(r[0]), Number(r[1])); });
  const snap = (t, alt) => {
    if (alt || !_veEl("veTimelineSnap").checked) return t;
    let best = null;
    for (const p of points) if (Math.abs(p - t) <= tolerance && (best === null || Math.abs(p - t) < Math.abs(best - t))) best = p;
    return best === null ? t : best;
  };
  let moved = false, a = a0, b = b0;
  _veRangeDrag = {renderPending: false};
  el.setPointerCapture(e.pointerId);
  const move = (ev) => {
    if (!moved && Math.abs(ev.clientX - e.clientX) < 3) return;
    moved = true;
    _veLastRangeDown = null;  // גרירה היא לא חצי מלחיצה כפולה
    const t = _veSourceAtX(ev.clientX);
    if (mode === "move") {
      const length = b0 - a0;
      a = Math.max(0, Math.min(d - length, a0 + t - grab));
      const sa = snap(a, ev.altKey), sb = snap(a + length, ev.altKey);
      if (sa !== a) a = sa; else if (sb !== a + length) a = sb - length;
      b = a + length;
    } else if (mode === "start") {
      a = Math.min(b0 - 0.1, Math.max(0, snap(t, ev.altKey)));
    } else {
      b = Math.max(a0 + 0.1, Math.min(d, snap(t, ev.altKey)));
    }
    el.style.left = (a / d * 100) + "%";
    el.style.width = ((b - a) / d * 100) + "%";
  };
  el.addEventListener("pointermove", move);
  const finish = () => {
    el.removeEventListener("pointermove", move);
    const pending = _veRangeDrag && _veRangeDrag.renderPending;
    _veRangeDrag = null;
    return pending;
  };
  el.addEventListener("pointercancel", () => { finish(); _veRenderTimelineOverlays(); }, {once: true});
  el.addEventListener("pointerup", () => {
    const pending = finish();
    if (!moved) { if (pending) _veRenderTimelineOverlays(); return; }
    _veRangeDragSwallowClick = true;
    ranges[index] = [Math.round(a * 10) / 10, Math.round(b * 10) / 10];
    ranges.sort((x, y) => x[0] - y[0]);
    _veSetFieldValue(input, JSON.stringify(ranges));
    _veRenderRangesEditor(true);
    _veRenderTimelineOverlays();
  }, {once: true});
}

function _veSetupRangeDrag() {
  const timeline = _veEl("veTimeline");
  timeline.addEventListener("pointerdown", (e) => {
    const range = e.target.closest(".ve-tl-range");
    if (range) _veStartRangeDrag(e, range);
  }, true);
  // אחרי גרירה - הלחיצה שנוצרת ממנה לא מזיזה את הסמן
  timeline.addEventListener("click", (e) => {
    if (_veRangeDragSwallowClick) { _veRangeDragSwallowClick = false; e.stopImmediatePropagation(); }
  }, true);
}

function _veInitWave29() {
  _veSetupRangeDrag();
  _veSetupTimelineResizer();
  _veSetupDropZones();
  const snap = document.createElement("div");
  snap.id = "veTlSnapLine";
  snap.className = "ve-tl-snap-line";
  snap.hidden = true;
  const scroll = _veEl("veTimelineScroll");
  if (scroll) {
    scroll.appendChild(snap);
    // המסלולים נבנים מאוחר יותר (_uiInitStudio) - מאזין אחד על כל הציר
    scroll.addEventListener("pointerdown", (e) => { const bar = e.target.closest(".ve-tl-layer"); if (bar) _veStartBarDrag(e, bar); });
  }
  // לחיצה כפולה על מסלול פותחת את ההגדרות שלו
  _veEl("veTimeline").addEventListener("dblclick", () => _veRevealElement(_veEl("veTrimStart")));
  _veEl("veWaveformCanvas").addEventListener("dblclick", () => _veRevealElement(_veEl("veSilenceMode")));
  _veEl("veLayers").addEventListener("change", _veRenderLayersList);
  uiBus.on("ve:derived-refresh", () => { _veRenderLayersList(); });
  // שורת תור נגררת לציר-הזמן = B-roll מהקובץ הזה
  _veEl("veQueueList").addEventListener("dragstart", (e) => {
    const row = e.target.closest(".ve-queue-row");
    if (row && row.dataset.name) e.dataTransfer.setData("text/x-ve-queue-name", row.dataset.name);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && _veSelected && !_veIsTyping() && !document.querySelector(".modal-bg.show")) { _veSelected = null; _veSyncSelection(); }
  });
  _veRenderLayersList();
}
