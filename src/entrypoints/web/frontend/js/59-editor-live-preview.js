// ============================================================================
// גל 10ב: תצוגה מקדימה - קטע וידאו עם שמע, מחיצה נגררת לפני/אחרי, אזורי
// בטיחות של Shorts/TikTok/Reels, ידיות גרירה ללוגו/PiP/שכבות, וציר-זמן אינטראקטיבי
// ============================================================================

// --- קטע וידאו (3-8 שניות) עם שמע: אותה שרשרת בדיוק כמו הרינדור ---
let _vePreviewClipInFlight = false;

function _veStage() { return document.getElementById("vePreviewStage"); }
function _veInClipMode() { return _veStage().classList.contains("ve-stage-video"); }

async function refreshVePreviewClip() {
  const status = document.getElementById("vePreviewStatus");
  if (!state.folder) { status.textContent = "⚠️ בחר תיקיית קלט קודם."; return; }
  if (_vePreviewClipInFlight) return;
  _vePreviewClipInFlight = true;
  const seconds = parseFloat(document.getElementById("vePreviewClipSeconds").value) || 5;
  const button = document.getElementById("vePreviewClipBtn");
  button.disabled = true;
  status.className = "ve-field-msg";
  status.textContent = `⏳ מרנדר קטע של ${seconds} שניות עם ההגדרות הנוכחיות...`;
  try {
    const res = await fetch("/api/video_editor/preview_clip", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: _vePreviewRequestBody({time: document.getElementById("vePreviewTime").value, clip_seconds: seconds}),
    });
    const data = await res.json();
    if (!res.ok) {
      status.className = "ve-field-msg bad";
      status.textContent = "⚠️ " + (data.error || "קטע התצוגה המקדימה נכשל") + (data.detail ? "\n" + data.detail : "");
      return;
    }
    _veShowPreviewClip(data);
    const notes = document.getElementById("vePreviewNotes");
    notes.innerHTML = "";
    for (const note of data.notes || []) {
      const li = document.createElement("li");
      li.textContent = note;
      notes.appendChild(li);
    }
    status.textContent = `✓ ${data.file} · 🎬 ${_veFormatTime(data.time)}–${_veFormatTime(data.time + (data.clip_seconds || seconds))} בפלט · ${data.output_width}×${data.output_height}`;
  } catch (e) {
    status.className = "ve-field-msg bad";
    status.textContent = "⚠️ שגיאת רשת בקטע התצוגה המקדימה";
  } finally {
    _vePreviewClipInFlight = false;
    button.disabled = false;
  }
}

// תיקייה חדשה: השורה של התצוגה הקודמת כבר לא נכונה
uiBus.on("ve:folder-changed", () => {
  const status = document.getElementById("vePreviewStatus");
  status.className = "ve-field-msg";
  status.textContent = "";
  document.getElementById("vePreviewNotes").replaceChildren();
});

function _veShowPreviewClip(data) {
  const after = document.getElementById("vePreviewClip");
  const before = document.getElementById("vePreviewClipBefore");
  after.src = data.after_url;
  before.src = data.before_url || data.after_url;
  _veStage().classList.add("ve-stage-video");
  _veStage().dataset.outputWidth = data.output_width;
  _veStage().dataset.outputHeight = data.output_height;
  document.getElementById("vePreviewStageWrap").hidden = false;
  document.getElementById("vePreviewClipWrap").hidden = false;
  const loop = document.getElementById("vePreviewClipLoop").checked;
  after.loop = before.loop = loop;
  applyVePreviewSplit();
  after.currentTime = 0;
  before.currentTime = 0;
  // ניגון אוטומטי עם שמע יכול להיחסם אחרי ה-fetch (אין "הפעלה" טרייה של המשתמש) - אז פשוט מחכה ל-▶️
  after.play().catch(() => {});
  _veRenderDragHandles();
  applyVeSafeZones();
}

function closeVePreviewClip() {
  for (const id of ["vePreviewClip", "vePreviewClipBefore"]) document.getElementById(id).pause();
  _veStage().classList.remove("ve-stage-video");
  document.getElementById("vePreviewClipWrap").hidden = true;
  if (!document.getElementById("vePreviewAfter").getAttribute("src")) document.getElementById("vePreviewStageWrap").hidden = true;
  _veRenderDragHandles();
  applyVeSafeZones();
}

function toggleVePreviewClipPlay() {
  const after = document.getElementById("vePreviewClip");
  if (after.paused) after.play().catch(() => {}); else after.pause();
}

function toggleVePreviewClipMute() {
  const after = document.getElementById("vePreviewClip");
  after.muted = !after.muted;
  document.getElementById("vePreviewClipMuteBtn").textContent = after.muted ? "🔇" : "🔊";
}

(function _veSetupPreviewClipSync() {
  const after = document.getElementById("vePreviewClip");
  const before = document.getElementById("vePreviewClipBefore");
  const seek = document.getElementById("vePreviewClipSeek");
  const playBtn = document.getElementById("vePreviewClipPlayBtn");
  const sync = () => { if (Math.abs(before.currentTime - after.currentTime) > 0.12) before.currentTime = after.currentTime; };
  after.addEventListener("play", () => { sync(); before.play().catch(() => {}); playBtn.textContent = "⏸️"; });
  after.addEventListener("pause", () => { before.pause(); sync(); playBtn.textContent = "▶️"; });
  after.addEventListener("seeked", sync);
  after.addEventListener("timeupdate", () => {
    sync();
    if (after.duration) seek.value = String(Math.round(after.currentTime / after.duration * 1000));
    document.getElementById("vePreviewClipTime").textContent = `${_veFormatTime(Math.round(after.currentTime * 10) / 10)} / ${_veFormatTime(Math.round((after.duration || 0) * 10) / 10)}`;
  });
  after.addEventListener("loadedmetadata", () => { _veRenderDragHandles(); applyVeSafeZones(); });
  seek.addEventListener("input", () => { if (after.duration) after.currentTime = after.duration * seek.value / 1000; });
  document.getElementById("vePreviewClipLoop").addEventListener("change", (e) => { after.loop = before.loop = e.target.checked; });
})();

// פריים חדש מחליף קטע שמוצג (הצגת הפריים החדש היא מה שהמשתמש ביקש)
const _refreshVePreviewBeforeWave10b = refreshVePreview;
refreshVePreview = async function () {
  const afterImg = document.getElementById("vePreviewAfter");
  const previousSrc = afterImg.getAttribute("src");
  await _refreshVePreviewBeforeWave10b();
  if (afterImg.getAttribute("src") !== previousSrc && _veInClipMode()) closeVePreviewClip();
};
document.getElementById("vePreviewAfter").addEventListener("load", () => { _veRenderDragHandles(); applyVeSafeZones(); });

// --- מחיצה נגררת לפני/אחרי (עכבר, מגע ומקלדת) ---
function _veSetPreviewSplit(percent) {
  const value = Math.round(Math.max(0, Math.min(100, percent)));
  document.getElementById("vePreviewSplit").value = String(value);
  document.getElementById("vePreviewDivider").setAttribute("aria-valuenow", String(value));
  applyVePreviewSplit();
}

(function _veSetupPreviewDivider() {
  const divider = document.getElementById("vePreviewDivider");
  let dragging = false;
  const moveTo = (clientX) => {
    const rect = _veStage().getBoundingClientRect();
    if (rect.width > 0) _veSetPreviewSplit((clientX - rect.left) / rect.width * 100);
  };
  divider.addEventListener("pointerdown", (e) => {
    dragging = true;
    divider.setPointerCapture(e.pointerId);
    moveTo(e.clientX);
    e.preventDefault();
  });
  divider.addEventListener("pointermove", (e) => { if (dragging) moveTo(e.clientX); });
  const stop = () => { dragging = false; };
  divider.addEventListener("pointerup", stop);
  divider.addEventListener("pointercancel", stop);
  divider.addEventListener("keydown", (e) => {
    const current = parseFloat(document.getElementById("vePreviewSplit").value) || 50;
    const step = e.shiftKey ? 10 : 2;
    // במה ב-direction:ltr - חץ ימינה מזיז את המחיצה ימינה (יותר "לפני")
    if (e.key === "ArrowRight") { _veSetPreviewSplit(current + step); e.preventDefault(); }
    else if (e.key === "ArrowLeft") { _veSetPreviewSplit(current - step); e.preventDefault(); }
    else if (e.key === "Home") { _veSetPreviewSplit(0); e.preventDefault(); }
    else if (e.key === "End") { _veSetPreviewSplit(100); e.preventDefault(); }
  });
})();

// --- אזורי בטיחות: איפה ממשק האפליקציה מסתיר את הסרטון (שברים של הפריים) ---
const VE_SAFE_ZONES = {
  shorts: {name: "YouTube Shorts", vertical: true, zones: [
    {x: 0, y: 0, w: 1, h: 0.12, label: "חיפוש / כותרת"},
    {x: 0, y: 0.8, w: 1, h: 0.2, label: "כותרת, ערוץ ומוזיקה"},
    {x: 0.86, y: 0.42, w: 0.14, h: 0.38, label: "לייק / תגובה / שיתוף"},
  ]},
  tiktok: {name: "TikTok", vertical: true, zones: [
    {x: 0, y: 0, w: 1, h: 0.1, label: "עוקבים / בשבילך"},
    {x: 0, y: 0.78, w: 0.86, h: 0.22, label: "שם משתמש וכיתוב"},
    {x: 0.86, y: 0.38, w: 0.14, h: 0.5, label: "פרופיל / לייק / שיתוף"},
  ]},
  reels: {name: "Instagram Reels", vertical: true, zones: [
    {x: 0, y: 0, w: 1, h: 0.1, label: "כותרת Reels"},
    {x: 0, y: 0.8, w: 0.86, h: 0.2, label: "שם וכיתוב"},
    {x: 0.86, y: 0.45, w: 0.14, h: 0.45, label: "לייק / תגובה / שליחה"},
  ]},
  youtube: {name: "YouTube", vertical: false, zones: [
    {x: 0, y: 0, w: 1, h: 0.1, label: "כותרת (בריחוף)"},
    {x: 0, y: 0.88, w: 1, h: 0.12, label: "פקדי הנגן"},
  ]},
};

function _veActiveSafeZones() {
  const key = document.getElementById("veSafeZones").value;
  return VE_SAFE_ZONES[key] || null;
}

function applyVeSafeZones() {
  const select = document.getElementById("veSafeZones");
  _veSavePref("veSafeZones", select.value);
  const overlay = document.getElementById("veSafeZonesOverlay");
  const preset = _veActiveSafeZones();
  overlay.innerHTML = "";
  overlay.hidden = !preset;
  if (preset) {
    for (const zone of preset.zones) {
      const box = document.createElement("div");
      box.style.cssText = `left:${zone.x * 100}%;top:${zone.y * 100}%;width:${zone.w * 100}%;height:${zone.h * 100}%`;
      box.title = zone.label;
      const label = document.createElement("span");
      label.textContent = zone.label;
      label.style.cssText = `left:${(zone.x + 0.01) * 100}%;top:${(zone.y + 0.005) * 100}%`;
      // אזור צר וגבוה: תווית לאורך
      if (zone.w < 0.25 && zone.h > zone.w * 2) { label.className = "ve-zone-tall"; label.style.maxHeight = `${(zone.h - 0.01) * 100}%`; }
      overlay.append(box, label);
    }
  }
  _veCheckHandlesInSafeZones();
}

function _veCheckHandlesInSafeZones() {
  const warn = document.getElementById("veSafeZonesWarn");
  const preset = _veActiveSafeZones();
  const hits = [];
  for (const handle of document.querySelectorAll("#veDragHandles .ve-drag-handle")) {
    const x = parseFloat(handle.dataset.x), y = parseFloat(handle.dataset.y);
    const zone = preset && preset.zones.find(z => x >= z.x && x <= z.x + z.w && y >= z.y && y <= z.y + z.h);
    handle.classList.toggle("ve-in-zone", !!zone);
    if (zone) hits.push(`${handle.dataset.label} מתחת ל"${zone.label}"`);
  }
  const notes = [];
  if (preset) {
    const stage = _veStage();
    const w = parseFloat(stage.dataset.outputWidth) || 0, h = parseFloat(stage.dataset.outputHeight) || 0;
    if (w && h && preset.vertical !== (h > w)) notes.push(`האזורים של ${preset.name} מיועדים לפלט ${preset.vertical ? "אנכי" : "אופקי"}.`);
  }
  if (hits.length) notes.unshift(`⚠️ ${preset.name}: ` + hits.join(" · "));
  warn.textContent = notes.join("\n");
  warn.hidden = !notes.length;
}

// --- ידיות גרירה על הפריים: לוגו, PiP, שכבות ---
// מיקום-preset מקורב (אותו margin של 20px ואותו רוחב יחסי כמו compute_watermark_geometry)
// - אחרי גרירה המיקום מדויק (מרכז בשברים), ופריים חדש מרונדר כדי להראות את התוצאה האמיתית.
function _veOutputSize() {
  const stage = _veStage();
  if (_veInClipMode()) {
    const v = document.getElementById("vePreviewClip");
    if (v.videoWidth) return {w: v.videoWidth, h: v.videoHeight};
  }
  const img = document.getElementById("vePreviewAfter");
  if (img.naturalWidth) return {w: img.naturalWidth, h: img.naturalHeight};
  return {w: parseFloat(stage.dataset.outputWidth) || 1920, h: parseFloat(stage.dataset.outputHeight) || 1080};
}

function _vePresetCenter(position, boxW, boxH, size) {
  const mx = 20 / size.w, my = 20 / size.h;
  const [vertical, horizontal] = position === "center" ? ["center", "center"] : String(position || "bottom-right").split("-");
  const x = horizontal === "left" ? mx + boxW / 2 : horizontal === "right" ? 1 - mx - boxW / 2 : 0.5;
  const y = vertical === "top" ? my + boxH / 2 : vertical === "bottom" ? 1 - my - boxH / 2 : 0.5;
  return {x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y))};
}

function _veDragTargets() {
  const size = _veOutputSize();
  const targets = [];
  if ((document.getElementById("veWatermarkPath").value || "").trim()) {
    const cx = document.getElementById("veWatermarkX").value, cy = document.getElementById("veWatermarkY").value;
    let center;
    if (cx !== "" && cy !== "") center = {x: parseFloat(cx), y: parseFloat(cy)};
    else {
      const scale = (parseFloat(document.getElementById("veWatermarkScale").value) || 15) / 100;
      const img = document.getElementById("wmPreviewImg");
      const aspect = img && img.naturalWidth ? img.naturalHeight / img.naturalWidth : 1;
      const vertPos = document.getElementById("veWatermarkPositionVertical").value;
      const position = size.h > size.w && vertPos ? vertPos : document.getElementById("veWatermarkPosition").value;
      center = _vePresetCenter(position, scale, scale * aspect * size.w / size.h, size);
    }
    targets.push({kind: "logo", label: "🖼️ לוגו", ...center});
  }
  if ((document.getElementById("vePipPath").value || "").trim()) {
    const cx = document.getElementById("vePipX").value, cy = document.getElementById("vePipY").value;
    let center;
    if (cx !== "" && cy !== "") center = {x: parseFloat(cx), y: parseFloat(cy)};
    else {
      const scale = (parseFloat(document.getElementById("vePipScale").value) || 30) / 100;
      center = _vePresetCenter(document.getElementById("vePipPosition").value, scale, scale * 9 / 16 * size.w / size.h, size);
    }
    targets.push({kind: "pip", label: "📺 PiP", ...center});
  }
  const presetXY = {left: 0.14, center: 0.5, right: 0.86, top: 0.07, bottom: 0.93};
  _veLayersValue().forEach((layer, index) => {
    if (layer.type === "text" && !(layer.text || "").trim()) return;
    if (layer.type === "image" && !(layer.path || "").trim()) return;
    if (layer.type === "video" && (layer.fit !== "pip" || !(layer.path || "").trim())) return;  // גל 26: מסך מלא לא נגרר
    let center;
    if (layer.position === "custom" && Number.isFinite(layer.x) && Number.isFinite(layer.y)) center = {x: layer.x, y: layer.y};
    else {
      const position = layer.position || "bottom-center";
      const [v, h] = position === "center" ? ["center", "center"] : position.split("-");
      center = {x: presetXY[h] ?? 0.5, y: presetXY[v] ?? 0.5};
    }
    const icon = VE_LAYER_KIND_ICONS[layer.type] || "🧩";
    const text = layer.type === "text" ? " " + layer.text.trim().slice(0, 12) : "";
    targets.push({kind: "layer", index, label: icon + text, ...center});
  });
  return targets;
}

function _veRenderDragHandles() {
  const container = document.getElementById("veDragHandles");
  container.innerHTML = "";
  const wrapVisible = !document.getElementById("vePreviewStageWrap").hidden;
  if (!wrapVisible || !document.getElementById("vePreviewHandles").checked) { _veCheckHandlesInSafeZones(); return; }
  for (const target of _veDragTargets()) {
    const handle = document.createElement("div");
    handle.className = "ve-drag-handle";
    handle.textContent = target.label;
    handle.tabIndex = 0;
    handle.setAttribute("role", "button");
    handle.setAttribute("aria-label", `גרור את ${target.label} (חיצים להזזה)`);
    handle.title = "גרור למיקום מדויק · חיצים = הזזה עדינה · Shift+חיצים = קפיצה";
    handle.dataset.kind = target.kind;
    handle.dataset.label = target.label;
    if (target.index !== undefined) handle.dataset.index = String(target.index);
    _vePlaceHandle(handle, target.x, target.y);
    // גל 30: במצב עריכת קליפ זזים רק הלוגו ושכבות של הקליפ - השאר חל על כל הקבצים
    if (_veTimeScope === "clip" && target.kind !== "logo" && !(target.kind === "layer" && !_veClipModeLocksLayer(_veLayersValue()[target.index]))) {
      handle.classList.add("ve-handle-locked");
      handle.title = "חל על כל הקבצים - סיים את עריכת הקליפ כדי להזיז";
    } else {
      _veAttachHandleDrag(handle);
    }
    container.appendChild(handle);
  }
  _veCheckHandlesInSafeZones();
  _veSyncSelection();
}

function _vePlaceHandle(handle, x, y) {
  handle.dataset.x = String(x);
  handle.dataset.y = String(y);
  handle.style.left = `${x * 100}%`;
  handle.style.top = `${y * 100}%`;
}

function _veCommitHandle(handle) {
  const x = Math.round(parseFloat(handle.dataset.x) * 10000) / 10000;
  const y = Math.round(parseFloat(handle.dataset.y) * 10000) / 10000;
  const kind = handle.dataset.kind;
  if (kind === "logo") {
    document.getElementById("veWatermarkX").value = x.toFixed(4);
    _veSetFieldValue(document.getElementById("veWatermarkY"), y.toFixed(4));
    if (typeof updateWatermarkPreview === "function") updateWatermarkPreview();
  } else if (kind === "pip") {
    document.getElementById("vePipX").value = x.toFixed(4);
    _veSetFieldValue(document.getElementById("vePipY"), y.toFixed(4));
    const coords = document.getElementById("vePipDragCoords");
    if (coords) coords.textContent = `✋ x=${Math.round(x * 100)}%  y=${Math.round(y * 100)}%`;
  } else if (kind === "layer") {
    const layers = _veLayersValue();
    const layer = layers[parseInt(handle.dataset.index, 10)];
    if (!layer) return;
    Object.assign(layer, {position: "custom", x, y});
    _veWriteLayers(layers);
    _veRenderLayersEditor(true);
  }
  const status = document.getElementById("vePreviewStatus");
  if (_veInClipMode()) {
    status.className = "ve-field-msg";
    status.textContent = "✋ המיקום עודכן - לחץ 🎬 קטע כדי לרנדר את הקטע מחדש.";
  } else {
    refreshVePreview();
  }
}

function _veAttachHandleDrag(handle) {
  let drag = null;
  handle.addEventListener("pointerdown", (e) => {
    const rect = _veStage().getBoundingClientRect();
    drag = {rect, moved: false};
    handle.setPointerCapture(e.pointerId);
    e.preventDefault();
    e.stopPropagation();
  });
  handle.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const x = Math.max(0, Math.min(1, (e.clientX - drag.rect.left) / drag.rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - drag.rect.top) / drag.rect.height));
    drag.moved = true;
    _vePlaceHandle(handle, x, y);
    _veCheckHandlesInSafeZones();
  });
  const end = () => {
    if (drag && drag.moved) _veCommitHandle(handle);
    drag = null;
  };
  handle.addEventListener("pointerup", end);
  handle.addEventListener("pointercancel", () => { drag = null; _veRenderDragHandles(); });
  handle.addEventListener("keydown", (e) => {
    const deltas = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};
    if (!deltas[e.key]) return;
    e.preventDefault();
    const step = e.shiftKey ? 0.05 : 0.01;
    const x = Math.max(0, Math.min(1, parseFloat(handle.dataset.x) + deltas[e.key][0] * step));
    const y = Math.max(0, Math.min(1, parseFloat(handle.dataset.y) + deltas[e.key][1] * step));
    _vePlaceHandle(handle, x, y);
    _veCheckHandlesInSafeZones();
    clearTimeout(handle._commitTimer);
    handle._commitTimer = setTimeout(() => _veCommitHandle(handle), 600);
  });
}

function clearVePipCustomPosition() {
  document.getElementById("vePipX").value = "";
  document.getElementById("vePipY").value = "";
  const coords = document.getElementById("vePipDragCoords");
  if (coords) coords.textContent = "";
  _veRenderDragHandles();
}

window.addEventListener("resize", () => _veCheckHandlesInSafeZones());

// --- ציר-זמן אינטראקטיבי: ידיות חיתוך נגררות, Shift+גרירה = טווח להסרה, 🔥 הייליטס ---
let _veHighlightMarkers = null;   // {file, peaks: [שניות]}
let _veTimelineDrag = null;
let _veTimelineSuppressClick = false;

VE_LAYER_POSITIONS.custom = "✋ מותאם (גרירה)";

function _veTimelineTimeAt(clientX) {
  const rect = document.getElementById("veTimeline").getBoundingClientRect();
  const fraction = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  return Math.round(fraction * _veTimeline.duration * 10) / 10;
}

function _veEnsureTimelineHandles() {
  const timeline = document.getElementById("veTimeline");
  for (const which of ["start", "end"]) {
    if (document.getElementById(`veTlHandle-${which}`)) continue;
    const handle = document.createElement("div");
    handle.id = `veTlHandle-${which}`;
    handle.className = "ve-tl-handle";
    handle.tabIndex = 0;
    handle.setAttribute("role", "slider");
    handle.setAttribute("aria-label", which === "start" ? "התחלת החיתוך" : "סוף החיתוך");
    handle.title = (which === "start" ? "התחלת החיתוך" : "סוף החיתוך") + " - גרור, או חיצים (Shift = 5 שנ')";
    handle.addEventListener("pointerdown", (e) => {
      if (!_veTimeline) return;
      _veTimelineDrag = {kind: which, moved: false};
      handle.setPointerCapture(e.pointerId);
      e.preventDefault();
      e.stopPropagation();
    });
    handle.addEventListener("pointermove", (e) => {
      if (!_veTimelineDrag || _veTimelineDrag.kind !== which) return;
      _veTimelineDrag.moved = true;
      _veTimelineDrag.time = _veTimelineTimeAt(e.clientX);
      _veRenderTimelineOverlays();
    });
    const finish = () => {
      if (_veTimelineDrag && _veTimelineDrag.kind === which && _veTimelineDrag.moved) {
        _veApplyTrimEdge(which, _veTimelineDrag.time);
        _veTimelineSuppressClick = true;
      }
      _veTimelineDrag = null;
      _veRenderTimelineOverlays();
    };
    handle.addEventListener("pointerup", finish);
    handle.addEventListener("pointercancel", () => { _veTimelineDrag = null; _veRenderTimelineOverlays(); });
    handle.addEventListener("keydown", (e) => {
      if (!_veTimeline || !["ArrowLeft", "ArrowRight"].includes(e.key)) return;
      e.preventDefault();
      const {start, end} = _veTrimBounds();
      const step = (e.shiftKey ? 5 : 0.5) * (e.key === "ArrowRight" ? 1 : -1);
      _veApplyTrimEdge(which, (which === "start" ? start : end) + step);
      _veRenderTimelineOverlays();
    });
    timeline.appendChild(handle);
  }
}

function _veTrimBounds() {
  const d = _veTimeline ? _veTimeline.duration : 0;
  const start = _veTimeValue("veTrimStart", 0);
  const length = _veTimeValue("veTrimDuration", null);
  return {start, end: length === null ? d : Math.min(d, start + length)};
}

function _veApplyTrimEdge(which, t) {
  const d = _veTimeline.duration;
  const round = (v) => Math.round(v * 10) / 10;
  const {start, end} = _veTrimBounds();
  if (which === "start") {
    const next = round(Math.max(0, Math.min(t, end - 0.5)));
    _veSetFieldValue(document.getElementById("veTrimStart"), String(next));
    const wasFullLength = end >= d - 0.05;
    _veSetFieldValue(document.getElementById("veTrimDuration"), wasFullLength ? "" : String(round(end - next)));
  } else {
    const next = round(Math.max(start + 0.5, Math.min(t, d)));
    _veSetFieldValue(document.getElementById("veTrimDuration"), next >= d - 0.05 ? "" : String(round(next - start)));
  }
}

function _veRenderTimelineExtras() {
  const timeline = document.getElementById("veTimeline");
  if (!timeline || !_veTimeline) return;
  _veEnsureTimelineHandles();
  const d = _veTimeline.duration;
  const pct = (t) => `${Math.max(0, Math.min(100, t / d * 100))}%`;
  let {start, end} = _veTrimBounds();
  if (_veTimelineDrag && _veTimelineDrag.time !== undefined) {
    if (_veTimelineDrag.kind === "start") start = Math.min(_veTimelineDrag.time, end - 0.5);
    if (_veTimelineDrag.kind === "end") end = Math.max(_veTimelineDrag.time, start + 0.5);
  }
  const startHandle = document.getElementById("veTlHandle-start");
  const endHandle = document.getElementById("veTlHandle-end");
  startHandle.style.left = pct(start);
  endHandle.style.left = pct(end);
  startHandle.setAttribute("aria-valuetext", _veFormatTime(start));
  endHandle.setAttribute("aria-valuetext", _veFormatTime(end));
  const layer = document.getElementById("veTimelineOverlays");
  if (_veTimelineDrag && (_veTimelineDrag.kind === "start" || _veTimelineDrag.kind === "end") && _veTimelineDrag.time !== undefined) {
    // בזמן גרירה: עמעום לפי הערך הזמני (לפני שנכתב לשדות)
    for (const dim of layer.querySelectorAll(".ve-tl-dim")) dim.remove();
    for (const [from, to] of [[0, start], [end, d]]) {
      if (to <= from) continue;
      const el = document.createElement("div");
      el.className = "ve-tl-dim";
      el.style.left = pct(from);
      el.style.width = `calc(${pct(to)} - ${pct(from)})`;
      layer.appendChild(el);
    }
  }
  if (_veTimelineDrag && _veTimelineDrag.kind === "range" && _veTimelineDrag.to !== undefined) {
    const from = Math.min(_veTimelineDrag.from, _veTimelineDrag.to), to = Math.max(_veTimelineDrag.from, _veTimelineDrag.to);
    const draft = document.createElement("div");
    draft.className = "ve-tl-draft";
    draft.style.left = pct(from);
    draft.style.width = `calc(${pct(to)} - ${pct(from)})`;
    layer.appendChild(draft);
  }
  const fileName = document.getElementById("vePreviewFile").value;
  if (_veHighlightMarkers && _veHighlightMarkers.file === fileName) {
    for (const peak of _veHighlightMarkers.peaks) {
      const marker = document.createElement("span");
      marker.className = "ve-tl-peak";
      marker.textContent = "🔥";
      marker.style.left = pct(peak);
      marker.title = `שיא שמע ב-${_veFormatTime(Math.round(peak * 10) / 10)} - לחץ לבחירת הנקודה`;
      layer.appendChild(marker);
    }
  }
  uiBus.emit("ve:timeline-rendered");  // גל 35: סימנים, מיני-מפה ומסלולים (79-editor-queue-timeline.js)
}

const _veRenderTimelineOverlaysBeforeWave10b = _veRenderTimelineOverlays;
_veRenderTimelineOverlays = function () {
  _veRenderTimelineOverlaysBeforeWave10b();
  _veRenderTimelineExtras();
};

(function _veSetupTimelineRangeDrag() {
  const timeline = document.getElementById("veTimeline");
  timeline.addEventListener("pointerdown", (e) => {
    if (!_veTimeline || !e.shiftKey || e.target.closest(".ve-tl-handle")) return;
    const t = _veTimelineTimeAt(e.clientX);
    _veTimelineDrag = {kind: "range", from: t};
    timeline.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  timeline.addEventListener("pointermove", (e) => {
    if (!_veTimelineDrag || _veTimelineDrag.kind !== "range") return;
    _veTimelineDrag.to = _veTimelineTimeAt(e.clientX);
    _veRenderTimelineOverlays();
  });
  timeline.addEventListener("pointerup", () => {
    if (!_veTimelineDrag || _veTimelineDrag.kind !== "range") return;
    const {from, to} = _veTimelineDrag;
    _veTimelineDrag = null;
    if (to !== undefined && Math.abs(to - from) >= 0.3) {
      const input = document.getElementById("veRemoveRanges");
      let ranges = [];
      try { ranges = JSON.parse(input.value || "[]"); } catch (err) { ranges = []; }
      ranges.push([Math.min(from, to), Math.max(from, to)]);
      ranges.sort((a, b) => a[0] - b[0]);
      _veSetFieldValue(input, JSON.stringify(ranges));
      _veRenderRangesEditor(true);
      _veTimelineSuppressClick = true;
    }
    _veRenderTimelineOverlays();
  });
  // אחרי גרירה הדפדפן שולח גם click - לא להזיז בגללו את הסמן
  document.getElementById("veTimelineBox").addEventListener("click", (e) => {
    if (_veTimelineSuppressClick) {
      _veTimelineSuppressClick = false;
      e.stopPropagation();
      return;
    }
    const peak = e.target.closest(".ve-tl-peak");
    if (peak && _veTimeline) {
      // לחיצה על 🔥 = בחירת הנקודה המדויקת של השיא (לא המיקום היחסי של העכבר)
      e.stopPropagation();
      const index = [...document.querySelectorAll("#veTimelineOverlays .ve-tl-peak")].indexOf(peak);
      const value = _veHighlightMarkers.peaks[index];
      _veTimelineCursor = Math.round(value * 10) / 10;
      document.getElementById("veTimelineCursorText").textContent = `📍 ${_veFormatTime(_veTimelineCursor)} במקור (🔥 שיא)`;
      _veRenderTimelineOverlays();
    }
  }, true);
})();

// טעינה אוטומטית של ציר-הזמן כשהקובץ בתצוגה המקדימה משתנה ואזור "זמן" פתוח
let _veTimelineAutoLoadedFor = null;
function _veMaybeAutoLoadTimeline() {
  const name = document.getElementById("vePreviewFile").value;
  const dock = document.getElementById("veTimelineDock");
  if (!name || !state.folder || !dock || dock.closest("[hidden]")) return;
  const key = state.folder + "|" + name;
  if (_veTimelineAutoLoadedFor === key) return;
  _veTimelineAutoLoadedFor = key;
  loadVeTimeline().catch(() => {});
}
document.getElementById("vePreviewFile").addEventListener("change", _veMaybeAutoLoadTimeline);
new MutationObserver(() => setTimeout(_veMaybeAutoLoadTimeline, 0)).observe(document.getElementById("vePreviewFile"), {childList: true});
document.querySelector("#veCategories > details[data-cat=time]").addEventListener("toggle", _veMaybeAutoLoadTimeline);

function _veInitWave10b() {
  const saved = _veLoadPref("veSafeZones", "");
  const select = document.getElementById("veSafeZones");
  if ([...select.options].some(o => o.value === saved)) select.value = saved;
  document.getElementById("vePreviewHandles").checked = _veLoadPref("vePreviewHandles", true) !== false;
  applyVeSafeZones();
}

