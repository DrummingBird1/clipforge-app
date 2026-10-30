// ============================================================================
// גל 14 - ציר-זמן מקצועי, keyframes לשכבות, וסקופים/עוצמת-שמע:
//  * ציר-זמן: זום, צעד של פריים/שנייה בחיצים, J/K/L לנגן החי, I/O לחיתוך,
//    והצמדה (🧲) לחילופי-סצנה, לגבולות שקט ולשיאי הייליטס בזמן גרירה.
//  * keyframes: מיקום/שקיפות/גודל לשכבה לאורך זמן - בגרירה על הנגן בזמן מסוים או
//    בטבלה; הרינדור מקבל ביטויי ffmpeg (utils/video_editor_layers.py keyframe_expr).
//  * סקופים: היסטוגרמה, waveform ו-vectorscope של מה שמוצג בנגן, ועוצמה (LUFS).
// ============================================================================

// --- ציר-זמן: זום ---
let _veTimelineZoom = 1;
let _veSceneCuts = null;     // {file, cuts: [שניות]}
let _veSnapHit = null;

function setVeTimelineZoom(zoom) {
  const next = Math.max(1, Math.min(16, zoom));
  const scroll = _veEl("veTimelineScroll");
  const center = scroll ? (scroll.scrollLeft + scroll.clientWidth / 2) / Math.max(1, scroll.scrollWidth) : 0.5;
  _veTimelineZoom = next;
  _veEl("veTimeline").style.width = (next * 100) + "%";
  const canvas = _veEl("veWaveformCanvas");
  canvas.style.width = (next * 100) + "%";
  canvas.width = Math.min(6000, Math.round(720 * next));
  _veEl("veTimelineZoomLabel").textContent = next === 1 ? "התאם" : `×${next}`;
  if (typeof drawVeWaveform === "function") drawVeWaveform();
  _veRenderTimelineOverlays();
  if (scroll) scroll.scrollLeft = center * scroll.scrollWidth - scroll.clientWidth / 2;
  // בזום גבוה - יותר תמונות ממוזערות לאורך הפס
  if (_veTimeline && next >= 2) _veLoadTimelineStrip(Math.min(64, Math.round(16 * next)));
}

async function _veLoadTimelineStrip(count) {
  if (!_veTimeline) return;
  const path = _veTimeline.path;
  const request = uiLatest("ve:timeline-strip");
  try {
    const data = await (await fetch(`/api/video_editor/timeline?count=${count}&path=` + encodeURIComponent(path), {signal: request.signal})).json();
    // זום מהיר: רק הפס של הזום האחרון, ורק אם הקובץ לא התחלף בינתיים
    if (!request.current() || !_veTimeline || _veTimeline.path !== path) return;
    if (data.url) _veEl("veTimelineImg").src = data.url;
  } catch (e) { /* נשאר הפס הקיים */ }
}

// --- הצמדה ---
function _veSnapCandidates() {
  const points = [];
  const file = _veEl("vePreviewFile").value;
  if (_veSceneCuts && _veSceneCuts.file === file) points.push(..._veSceneCuts.cuts);
  if (_veHighlightMarkers && _veHighlightMarkers.file === file) points.push(..._veHighlightMarkers.peaks);
  if (_veWaveformData && _veTimeline) {
    // גבולות שקט: מעבר מעל/מתחת לסף השקט בגל-הקול
    const peaks = _veWaveformData.peaks || [];
    const full = _veWaveformData.full_scale || _veWaveformData.max_peak || 1;
    const db = parseFloat(_veEl("veSilenceThresholdDb").value || "-30");
    const threshold = Math.pow(10, db / 20) * full;
    let loud = null;
    for (let i = 0; i < peaks.length; i++) {
      const now = peaks[i] > threshold;
      if (loud !== null && now !== loud) points.push(i / peaks.length * _veTimeline.duration);
      loud = now;
    }
  }
  return points;
}

const _veTimelineTimeAtBeforeW14 = _veTimelineTimeAt;
_veTimelineTimeAt = function (clientX, ...rest) {
  const raw = _veTimelineTimeAtBeforeW14(clientX, ...rest);
  _veSnapHit = null;
  if (!_veTimelineDrag || !_veEl("veTimelineSnap").checked || window.__veAltDown || !_veTimeline) return raw;
  const rect = _veEl("veTimeline").getBoundingClientRect();
  const tolerance = 7 / Math.max(1, rect.width) * _veTimeline.duration;
  let best = null;
  for (const point of _veSnapCandidates()) {
    const distance = Math.abs(point - raw);
    if (distance <= tolerance && (best === null || distance < Math.abs(best - raw))) best = point;
  }
  if (best === null) return raw;
  _veSnapHit = best;
  return Math.round(best * 100) / 100;
};
document.addEventListener("keydown", (e) => { if (e.key === "Alt") window.__veAltDown = true; });
document.addEventListener("keyup", (e) => { if (e.key === "Alt") window.__veAltDown = false; });

async function _veLoadSceneCuts() {
  const file = _veEl("vePreviewFile").value;
  if (!state.folder || !file || (_veSceneCuts && _veSceneCuts.file === file)) return;
  _veSceneCuts = {file, cuts: []};
  try {
    const data = await (await fetch("/api/video_editor/scene_cuts?folder=" + encodeURIComponent(state.folder) + "&file=" + encodeURIComponent(file))).json();
    if (Array.isArray(data.cuts) && _veSceneCuts.file === file) { _veSceneCuts.cuts = data.cuts; _veRenderTimelineOverlays(); }
  } catch (e) { /* בלי הצמדה לסצנות */ }
}

// סימוני חילופי-סצנה + אינדיקציית הצמדה על הפס
const _veRenderTimelineExtrasBeforeW14 = _veRenderTimelineExtras;
_veRenderTimelineExtras = function () {
  _veRenderTimelineExtrasBeforeW14();
  const layer = _veEl("veTimelineOverlays");
  if (!layer || !_veTimeline) return;
  const pct = (t) => `${Math.max(0, Math.min(100, t / _veTimeline.duration * 100))}%`;
  const file = _veEl("vePreviewFile").value;
  if (_veSceneCuts && _veSceneCuts.file === file) {
    for (const cut of _veSceneCuts.cuts) {
      const mark = document.createElement("div");
      mark.className = "ve-tl-scene";
      mark.style.left = pct(cut);
      layer.appendChild(mark);
    }
  }
  if (_veSnapHit !== null && _veTimelineDrag) {
    const snap = document.createElement("div");
    snap.className = "ve-tl-snap";
    snap.style.left = pct(_veSnapHit);
    layer.appendChild(snap);
  }
};

const _loadVeTimelineBeforeW14 = loadVeTimeline;
loadVeTimeline = async function (...args) {
  const result = await _loadVeTimelineBeforeW14(...args);
  _veLoadSceneCuts();
  if (_veTimelineZoom > 1) setVeTimelineZoom(_veTimelineZoom);
  return result;
};

// --- ציר-זמן: מקלדת ---
function _veFileFps() {
  const file = _veEl("vePreviewFile").value;
  const item = (_veQueueState || []).find(f => f.name === file);
  const fps = item && item.meta && parseFloat(item.meta.fps);
  return fps && fps > 1 ? fps : 30;
}

function _veMoveTimelineCursor(seconds) {
  if (!_veTimeline) return;
  _veTimelineCursor = Math.max(0, Math.min(_veTimeline.duration, Math.round(seconds * 1000) / 1000));
  _veEl("veTimelineCursorText").textContent = `📍 ${_veFormatTime(Math.round(_veTimelineCursor * 100) / 100)} במקור`;
  if (_veInLiveMode()) _veEl("veLiveVideo").currentTime = _veTimelineCursor;
  _veRenderTimelineOverlays();
}

_veEl("veTimeline").tabIndex = 0;
_veEl("veTimeline").setAttribute("aria-label", "ציר-זמן: חיצים = פריים, Shift+חיצים = שנייה, I/O = התחלה/סוף, J/K/L = נגינה");
_veEl("veTimeline").addEventListener("keydown", (e) => {
  if (!_veTimeline) return;
  const cursor = _veTimelineCursor ?? _veTrimBounds().start;
  const step = e.shiftKey ? 1 : 1 / _veFileFps();
  const key = e.key.toLowerCase();
  // בפס בכיוון LTR - ימינה = קדימה בזמן
  if (e.key === "ArrowRight") { _veMoveTimelineCursor(cursor + step); e.preventDefault(); }
  else if (e.key === "ArrowLeft") { _veMoveTimelineCursor(cursor - step); e.preventDefault(); }
  else if (e.key === "Home") { _veMoveTimelineCursor(_veTrimBounds().start); e.preventDefault(); }
  else if (e.key === "End") { _veMoveTimelineCursor(_veTrimBounds().end); e.preventDefault(); }
  else if (key === "i") { _veApplyTrimEdge("start", cursor); _veRenderTimelineOverlays(); e.preventDefault(); }
  else if (key === "o") { _veApplyTrimEdge("end", cursor); _veRenderTimelineOverlays(); e.preventDefault(); }
  else if (key === "k" || e.key === " ") { if (_veInLiveMode()) _veEl("veLiveVideo").pause(); e.preventDefault(); }
  else if (key === "l") { _veLivePlayRate(1); e.preventDefault(); }
  else if (key === "j") { _veLivePlayRate(-1); e.preventDefault(); }
  else if ((e.key === "+" || e.key === "=") && !e.ctrlKey) { setVeTimelineZoom(_veTimelineZoom * 2); e.preventDefault(); }
  else if (e.key === "-" && !e.ctrlKey) { setVeTimelineZoom(_veTimelineZoom / 2); e.preventDefault(); }
});
_veEl("veTimeline").addEventListener("wheel", (e) => {
  if (!e.ctrlKey || !_veTimeline) return;
  e.preventDefault();
  setVeTimelineZoom(_veTimelineZoom * (e.deltaY < 0 ? 2 : 0.5));
}, {passive: false});

// L = קדימה (לחיצה חוזרת מאיצה ×2/×4), J = אחורה (קפיצות של שנייה - לדפדפן אין נגינה הפוכה)
let _veJklTimer = null;
function _veLivePlayRate(direction) {
  if (!_veInLiveMode()) { if (_veEl("vePreviewFile").value) startVeLivePreview(); return; }
  const video = _veEl("veLiveVideo");
  clearInterval(_veJklTimer);
  if (direction > 0) {
    const base = _veLive && _veLive.timeline ? _veLive.timeline.speed : 1;
    const current = video.paused ? 0 : video.playbackRate / base;
    video.playbackRate = Math.min(16, base * (current >= 1 ? Math.min(4, current * 2) : 1));
    video.play().catch(() => {});
  } else {
    video.pause();
    _veJklTimer = setInterval(() => {
      video.currentTime = Math.max(_veLive && _veLive.timeline ? _veLive.timeline.start : 0, video.currentTime - 0.5);
      if (_veLive && _veLive.timeline && video.currentTime <= _veLive.timeline.start + 0.01) clearInterval(_veJklTimer);
    }, 250);
    document.addEventListener("keyup", () => clearInterval(_veJklTimer), {once: true});
  }
}

// הנגן החי מזיז את סמן ציר-הזמן (בזמני המקור), ב-10 פריימים לשנייה
let _veLastCursorSync = 0;
function _veOnLiveTick() {
  const now = performance.now();
  if (now - _veLastCursorSync < 100 || !_veTimeline) return;
  _veLastCursorSync = now;
  _veTimelineCursor = _veEl("veLiveVideo").currentTime;
  const cursor = _veEl("veTimelineCursor");
  if (cursor) { cursor.hidden = false; cursor.style.left = `${Math.max(0, Math.min(100, _veTimelineCursor / _veTimeline.duration * 100))}%`; }
}

// --- keyframes ---
function _veInterpKeyframes(layer, t) {
  const frames = Array.isArray(layer.keyframes) ? layer.keyframes : [];
  if (frames.length < 2) return null;
  const out = {};
  for (const key of ["x", "y", "opacity", "scale"]) {
    const points = frames.filter(f => Number.isFinite(f[key])).map(f => [Number(f.t), Number(f[key])]).sort((a, b) => a[0] - b[0]);
    if (points.length < 2) continue;
    if (t <= points[0][0]) { out[key] = points[0][1]; continue; }
    if (t >= points[points.length - 1][0]) { out[key] = points[points.length - 1][1]; continue; }
    for (let i = 0; i < points.length - 1; i++) {
      const [t0, v0] = points[i], [t1, v1] = points[i + 1];
      if (t >= t0 && t <= t1) {
        let u = (t - t0) / Math.max(0.001, t1 - t0);
        if (layer.easing === "ease") u = u * u * (3 - 2 * u);
        out[key] = v0 + (v1 - v0) * u;
        break;
      }
    }
  }
  return out;
}

function _veCurrentOutputTime() {
  if (_veInLiveMode()) return _veLiveCurrentOut();
  return _veParseTimeText(_veEl("vePreviewTime").value) || 0;
}

function _veLayerCenterNow(layers, index) {
  const handle = document.querySelector(`#veDragHandles .ve-drag-handle[data-kind=layer][data-index="${index}"]`);
  if (handle) return {x: parseFloat(handle.dataset.x), y: parseFloat(handle.dataset.y)};
  const layer = layers[index];
  if (layer.position === "custom" && Number.isFinite(layer.x)) return {x: layer.x, y: layer.y};
  return {x: 0.5, y: 0.5};
}

function _veUpsertKeyframe(layers, index, values) {
  const layer = layers[index];
  const t = Math.round(_veCurrentOutputTime() * 100) / 100;
  const frames = Array.isArray(layer.keyframes) ? [...layer.keyframes] : [];
  const existing = frames.findIndex(f => Math.abs(Number(f.t) - t) < 0.05);
  const frame = {...(existing >= 0 ? frames[existing] : {opacity: layer.opacity ?? 1, scale: 1}), t, ...values};
  if (existing >= 0) frames[existing] = frame; else frames.push(frame);
  frames.sort((a, b) => a.t - b.t);
  layer.keyframes = frames;
  if (!layer.easing) layer.easing = "linear";
  return frame;
}

function addVeKeyframe(index) {
  const layers = _veLayersValue();
  if (!layers[index]) return;
  const center = _veLayerCenterNow(layers, index);
  _veUpsertKeyframe(layers, index, {x: center.x, y: center.y});
  _veWriteLayers(layers);
  _veRenderLayersEditor(true);
  _veOpenKeyframes.add(index);
}

const _veOpenKeyframes = new Set();

function _veKeyframePanel(layer, index) {
  const panel = document.createElement("div");
  panel.className = "ve-kf-panel";
  const head = document.createElement("div");
  head.className = "ve-row";
  head.style.flexWrap = "wrap";
  const add = document.createElement("button");
  add.type = "button"; add.textContent = "➕ מפתח בזמן הנוכחי"; add.onclick = () => addVeKeyframe(index);
  const easing = _veLayerSelect({linear: "ליניארי", ease: "רך (ease)"}, layer.easing || "linear", "מעבר");
  easing.addEventListener("change", () => { const layers = _veLayersValue(); layers[index].easing = easing.value; _veWriteLayers(layers); });
  const hint = document.createElement("span");
  hint.className = "ve-field-msg";
  hint.textContent = "💡 גרירת השכבה בנגן כשיש לה מפתחות = מפתח בזמן הנוכחי";
  head.append(add, easing, hint);
  panel.appendChild(head);
  (layer.keyframes || []).forEach((frame, i) => {
    const row = document.createElement("div");
    row.className = "ve-row ve-kf-row";
    const field = (key, value, factor, label, attrs) => {
      const input = _veLayerInput("number", value === undefined ? "" : Math.round(value * factor * 10) / 10, "", label, {"aria-label": label, style: "width:62px", ...attrs});
      input.addEventListener("change", () => {
        // שדה שנעלם בציור-מחדש עדיין שולח change כשהוא מאבד פוקוס - לא לכתוב דרכו למפתח אחר
        if (!input.isConnected) return;
        const layers = _veLayersValue();
        const target = (layers[index].keyframes || []).find(f => f.t === frame.t);
        if (!target) return;
        const parsed = parseFloat(input.value);
        if (Number.isFinite(parsed)) target[key] = parsed / factor; else delete target[key];
        layers[index].keyframes.sort((a, b) => a.t - b.t);
        _veWriteLayers(layers);
      });
      return input;
    };
    const time = _veLayerInput("text", _veFormatTime(frame.t), "ve-layer-time", "זמן (בפלט)", {"aria-label": "זמן המפתח"});
    time.addEventListener("change", () => {
      if (!time.isConnected) return;
      const parsed = _veParseTimeText(time.value);
      if (parsed === null) { time.classList.add("ve-invalid"); return; }
      const layers = _veLayersValue();
      const target = (layers[index].keyframes || []).find(f => f.t === frame.t);
      if (!target) return;
      target.t = parsed;
      layers[index].keyframes.sort((a, b) => a.t - b.t); _veWriteLayers(layers); _veRenderLayersEditor(true);
    });
    const remove = document.createElement("button");
    remove.type = "button"; remove.textContent = "✕"; remove.setAttribute("aria-label", "מחק מפתח");
    remove.onclick = () => { const layers = _veLayersValue(); layers[index].keyframes = layers[index].keyframes.filter(f => f.t !== frame.t); _veWriteLayers(layers); _veRenderLayersEditor(true); };
    row.append("◆", time, "x%", field("x", frame.x, 100, "x (%)", {min: 0, max: 100}), "y%", field("y", frame.y, 100, "y (%)", {min: 0, max: 100}),
      "שקיפות%", field("opacity", frame.opacity, 100, "שקיפות (%)", {min: 0, max: 100}), "גודל%", field("scale", frame.scale, 100, "גודל (%)", {min: 10, max: 500}), remove);
    panel.appendChild(row);
  });
  return panel;
}

const _veLayerRowElBeforeW14 = _veLayerRowEl;
_veLayerRowEl = function (layer, index, total) {
  const row = _veLayerRowElBeforeW14(layer, index, total);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "ve-kf-toggle";
  const count = (layer.keyframes || []).length;
  button.textContent = count ? `◆ ${count}` : "◆";
  button.title = "keyframes - מיקום/שקיפות/גודל שמשתנים לאורך זמן";
  button.setAttribute("aria-label", "keyframes");
  button.setAttribute("aria-expanded", String(_veOpenKeyframes.has(index)));
  button.onclick = () => { if (_veOpenKeyframes.has(index)) _veOpenKeyframes.delete(index); else _veOpenKeyframes.add(index); _veRenderLayersEditor(true); };
  const remove = row.querySelector(".ve-layer-remove");
  row.insertBefore(button, remove);
  return row;
};

const _veRenderLayersEditorBeforeW14 = _veRenderLayersEditor;
_veRenderLayersEditor = function (...args) {
  const result = _veRenderLayersEditorBeforeW14(...args);
  const layers = _veLayersValue();
  for (const row of document.querySelectorAll("#veLayersRows .ve-layer-row")) {
    const index = parseInt(row.dataset.index, 10);
    if (_veOpenKeyframes.has(index) && layers[index]) row.after(_veKeyframePanel(layers[index], index));
  }
  return result;
};

// גרירת שכבה עם keyframes = מפתח בזמן הנוכחי (לא מיקום קבוע)
const _veCommitHandleBeforeW14 = _veCommitHandle;
_veCommitHandle = function (handle) {
  if (handle.dataset.kind === "layer") {
    const layers = _veLayersValue();
    const index = parseInt(handle.dataset.index, 10);
    if (layers[index] && (layers[index].keyframes || []).length) {
      _veUpsertKeyframe(layers, index, {x: Math.round(parseFloat(handle.dataset.x) * 10000) / 10000, y: Math.round(parseFloat(handle.dataset.y) * 10000) / 10000});
      _veWriteLayers(layers);
      _veRenderLayersEditor(true);
      _veScheduleLiveRebuild();
      return;
    }
  }
  return _veCommitHandleBeforeW14(handle);
};

// ידיות של שכבות עם keyframes עומדות במקום של הזמן הנוכחי
const _veDragTargetsBeforeW14 = _veDragTargets;
_veDragTargets = function () {
  const targets = _veDragTargetsBeforeW14();
  const layers = _veLayersValue();
  const t = _veCurrentOutputTime();
  for (const target of targets) {
    if (target.kind !== "layer") continue;
    const values = _veInterpKeyframes(layers[target.index] || {}, t);
    if (values && Number.isFinite(values.x)) target.x = values.x;
    if (values && Number.isFinite(values.y)) target.y = values.y;
  }
  return targets;
};

// --- סקופים ---
let _veScopesTimer = null;
function toggleVeScopes() {
  const panel = _veEl("veScopes");
  panel.hidden = !panel.hidden;
  _veEl("veScopesBtn").setAttribute("aria-pressed", String(!panel.hidden));
  clearInterval(_veScopesTimer);
  if (!panel.hidden) { drawVeScopes(); _veScopesTimer = setInterval(() => { if (_veInLiveMode() || _veInClipMode()) drawVeScopes(); }, 300); }
}

function _veScopeSource() {
  if (_veInLiveMode()) return {el: _veEl("veLiveVideo"), filter: _veEl("veLiveVideo").style.filter || "none"};
  if (_veInClipMode()) return {el: _veEl("vePreviewClip"), filter: "none"};
  const img = _veEl("vePreviewAfter");
  return img.naturalWidth ? {el: img, filter: "none"} : null;
}

function drawVeScopes() {
  const source = _veScopeSource();
  if (!source) return;
  const W = 192, H = 108;
  const work = document.createElement("canvas");
  work.width = W; work.height = H;
  const ctx = work.getContext("2d", {willReadFrequently: true});
  ctx.filter = source.filter;
  try { ctx.drawImage(source.el, 0, 0, W, H); } catch (e) { return; }
  let data;
  try { data = ctx.getImageData(0, 0, W, H).data; } catch (e) { return; }
  const hist = {r: new Array(256).fill(0), g: new Array(256).fill(0), b: new Array(256).fill(0), l: new Array(256).fill(0)};
  const wave = _veEl("veScopeWave"), vec = _veEl("veScopeVector"), histCanvas = _veEl("veScopeHist");
  const wctx = wave.getContext("2d"), vctx = vec.getContext("2d"), hctx = histCanvas.getContext("2d");
  wctx.fillStyle = "#000"; wctx.fillRect(0, 0, wave.width, wave.height);
  vctx.fillStyle = "#000"; vctx.fillRect(0, 0, vec.width, vec.height);
  wctx.fillStyle = "rgba(120,255,140,0.25)"; vctx.fillStyle = "rgba(255,255,255,0.25)";
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const i = (y * W + x) * 4;
      const r = data[i], g = data[i + 1], b = data[i + 2];
      const luma = Math.round(0.2126 * r + 0.7152 * g + 0.0722 * b);
      hist.r[r]++; hist.g[g]++; hist.b[b]++; hist.l[luma]++;
      wctx.fillRect(x / W * wave.width, wave.height - 1 - luma / 255 * (wave.height - 1), 1, 1);
      const cb = -0.1146 * r - 0.3854 * g + 0.5 * b, cr = 0.5 * r - 0.4542 * g - 0.0458 * b;
      vctx.fillRect(vec.width / 2 + cb / 128 * (vec.width / 2 - 4), vec.height / 2 - cr / 128 * (vec.height / 2 - 4), 1, 1);
    }
  }
  vctx.strokeStyle = "rgba(255,255,255,.3)";
  vctx.beginPath(); vctx.arc(vec.width / 2, vec.height / 2, vec.width / 2 - 4, 0, Math.PI * 2); vctx.stroke();
  hctx.fillStyle = "#000"; hctx.fillRect(0, 0, histCanvas.width, histCanvas.height);
  const max = Math.max(1, ...hist.l, ...hist.r, ...hist.g, ...hist.b);
  for (const [key, color] of [["r", "rgba(255,80,80,.55)"], ["g", "rgba(80,255,120,.55)"], ["b", "rgba(90,140,255,.55)"], ["l", "rgba(255,255,255,.7)"]]) {
    hctx.strokeStyle = color; hctx.beginPath();
    for (let v = 0; v < 256; v++) {
      const x = v / 255 * histCanvas.width, y = histCanvas.height - Math.sqrt(hist[key][v] / max) * histCanvas.height;
      if (v === 0) hctx.moveTo(x, y); else hctx.lineTo(x, y);
    }
    hctx.stroke();
  }
  const clipped = (hist.l[255] + hist.l[254]) / (W * H), crushed = (hist.l[0] + hist.l[1]) / (W * H);
  const notes = [];
  if (clipped > 0.02) notes.push(`⚠️ ${Math.round(clipped * 100)}% שרוף (לבן מלא)`);
  if (crushed > 0.05) notes.push(`⚠️ ${Math.round(crushed * 100)}% שחור מלא`);
  _veEl("veScopesNote").textContent = notes.join(" · ") || "✓ בלי שריפה/קריסה משמעותית";
}
_veEl("vePreviewAfter").addEventListener("load", () => { if (!_veEl("veScopes").hidden) drawVeScopes(); });

async function loadVeLoudness() {
  const file = _veEl("vePreviewFile").value;
  const status = _veEl("veLoudnessStatus");
  if (!state.folder || !file) { status.textContent = "בחר קובץ קודם."; return; }
  status.textContent = "⏳ מודד עוצמה (ebur128)...";
  const request = uiLatest("ve:loudness");
  let data;
  try {
    const res = await fetch("/api/video_editor/loudness?folder=" + encodeURIComponent(state.folder) + "&file=" + encodeURIComponent(file), {signal: request.signal});
    data = await res.json();
    if (!request.current()) return;
    if (!res.ok) { status.textContent = "⚠️ " + (data.error || "המדידה נכשלה"); return; }
  } catch (e) {
    if (!uiIsAbort(e)) status.textContent = "⚠️ המדידה נכשלה";
    return;
  }
  if (_veEl("vePreviewFile").value !== file) return;  // קובץ אחר נבחר בזמן המדידה
  if (data.no_audio || !data.points.length) { status.textContent = "אין פס-קול בקובץ הזה."; return; }
  const canvas = _veEl("veLoudnessCanvas");
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  ctx.fillStyle = "#0b0b0f"; ctx.fillRect(0, 0, W, H);
  const lo = -50, hi = -5, y = (lufs) => H - (Math.max(lo, Math.min(hi, lufs)) - lo) / (hi - lo) * H;
  const target = _veEl("veLoudnorm").checked ? (parseFloat(_veEl("veLoudnormTarget").value) || -14) : -14;
  ctx.strokeStyle = "#f59e0b"; ctx.setLineDash([5, 4]);
  ctx.beginPath(); ctx.moveTo(0, y(target)); ctx.lineTo(W, y(target)); ctx.stroke(); ctx.setLineDash([]);
  const duration = data.points[data.points.length - 1][0] || 1;
  for (const [index, color] of [[1, "rgba(96,165,250,.45)"], [2, "#22d3ee"]]) {
    ctx.strokeStyle = color; ctx.beginPath();
    let started = false;
    for (const point of data.points) {
      if (point[index] === null) { started = false; continue; }
      const x = point[0] / duration * W;
      if (!started) { ctx.moveTo(x, y(point[index])); started = true; } else ctx.lineTo(x, y(point[index]));
    }
    ctx.stroke();
  }
  const integrated = data.integrated !== null ? `${data.integrated.toFixed(1)} LUFS` : "—";
  const delta = data.integrated !== null ? data.integrated - target : 0;
  status.textContent = `עוצמה כוללת: ${integrated} · טווח (LRA): ${data.lra ?? "—"} LU · יעד ${target} LUFS`
    + (data.integrated !== null ? (Math.abs(delta) < 1 ? " ✓" : ` (${delta > 0 ? "חזק" : "חלש"} ב-${Math.abs(delta).toFixed(1)} - ${_veEl("veLoudnorm").checked ? "הנרמול יתקן" : "כדאי להדליק נרמול עוצמה"})`) : "");
  canvas.hidden = false;
}

function _veInitWave14Timeline() {
  // עוטפים את הפס בגלילה אופקית לזום (גל-הקול באותה גלילה, מסונכרן)
  const timeline = _veEl("veTimeline");
  if (!_veEl("veTimelineScroll")) {
    const scroll = document.createElement("div");
    scroll.id = "veTimelineScroll";
    scroll.className = "ve-timeline-scroll";
    timeline.before(scroll);
    scroll.append(timeline, _veEl("veWaveformCanvas"));
  }
}
