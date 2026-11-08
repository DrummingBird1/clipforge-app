// ============================================================================
// גל 13 - נגן חי: מנגן את קובץ המקור עצמו ומצייר מעליו בזמן אמת את מה שהרינדור
// יעשה - פורמט/קרופ/שוליים/רקע מטושטש, סיבוב, צבע, לוגו, PiP, שכבות מתוזמנות,
// סרגל התקדמות, מסגרת, וינייטה, כתובית לדוגמה, fade, חיתוך וטווחים שהוסרו, מהירות.
// קירוב לעבודה מהירה; "🎯 בדיקה מדויקת" = פריים מהשרת באותה שרשרת כמו הרינדור.
// ============================================================================

const VE_LIVE_ASPECTS = {"16:9": [1920, 1080], "9:16": [1080, 1920], "1:1": [1080, 1080], "4:5": [1080, 1350], "4:3": [1440, 1080]};
let _veLive = null;          // {file, timeline, opts, out: {w,h}, raf, proxy}
let _veLiveBuildTimer = null;

function _veInLiveMode() { return _veStage().classList.contains("ve-stage-live"); }

// ההגדרות האפקטיביות לנגן: המתכון + היעד שנבחר לתצוגה + ערכת המותג + עריכת הקליפ של הקובץ
function _veLiveOptions(file) {
  const opts = {..._collectRunOptions()};
  const schema = _veSchema;
  const previewTarget = _veEl("vePreviewTarget");
  const targetId = previewTarget && !previewTarget.closest("[hidden]") ? previewTarget.value : "";
  if (schema && targetId && schema.targets[targetId]) {
    for (const [key, value] of Object.entries(schema.targets[targetId].fields || {})) {
      if (value === null) delete opts[key]; else opts[key] = value;
    }
  }
  const kit = _veBrandKits[opts.brand_kit];
  if (kit) Object.assign(opts, kit.fields || {});
  const edit = (opts.clip_edits || {})[file];
  if (edit && ("trim_start" in edit || "remove_ranges" in edit)) {
    opts.trim_start = edit.trim_start || 0;
    opts.trim_duration = edit.trim_duration;
    opts.remove_ranges = edit.remove_ranges || [];
    opts._clipTimeEdit = true;
  }
  // גל 30: הלוגו של הקליפ (מיקום פינה מפורש מבטל את מרכז הגרירה, כמו ברנדרר)
  if (edit) {
    for (const key of ["watermark_path", "watermark_position", "watermark_scale", "watermark_opacity"]) if (key in edit) opts[key] = edit[key];
    if ("watermark_x" in edit) { opts.watermark_x = edit.watermark_x; opts.watermark_y = edit.watermark_y; }
    else if ("watermark_position" in edit) { opts.watermark_x = null; opts.watermark_y = null; }
  }
  const layers = Array.isArray(opts.layers) ? opts.layers : [];
  opts._layers = layers.filter(layer => !layer.clip || layer.clip === file);
  return opts;
}

function _veLiveOutputSize(opts) {
  if (opts.dual_output) return opts.vertical ? {w: 1080, h: 1920} : {w: 1920, h: 1080};
  if (opts.aspect === "custom" && opts.custom_width > 0 && opts.custom_height > 0) return {w: +opts.custom_width, h: +opts.custom_height};
  if (opts.aspect && VE_LIVE_ASPECTS[opts.aspect]) { const [w, h] = VE_LIVE_ASPECTS[opts.aspect]; return {w, h}; }
  return opts.vertical ? {w: 1080, h: 1920} : {w: 1920, h: 1080};
}

function _veParseRangesValue(value) {
  let ranges = value;
  if (typeof ranges === "string") { try { ranges = JSON.parse(ranges || "[]"); } catch (e) { ranges = []; } }
  if (!Array.isArray(ranges)) return [];
  return ranges.map(r => [Number(r[0]), Number(r[1])]).filter(([a, b]) => Number.isFinite(a) && Number.isFinite(b) && b > a && a >= 0)
    .sort((x, y) => x[0] - y[0]);
}

// ציר-הזמן של הפלט מול המקור: קטעים שנשארים, מהירות ואורך הפלט
function _veLiveTimeline(opts, sourceDuration) {
  const d = sourceDuration || 0;
  const start = Math.max(0, Math.min(d, Number(opts.trim_start) || 0));
  const length = Number(opts.trim_duration) > 0 ? Number(opts.trim_duration) : null;
  const end = length === null ? d : Math.min(d, start + length);
  const explicitTrim = start > 0 || length !== null;
  const ranges = (opts._clipTimeEdit || !explicitTrim) ? _veParseRangesValue(opts.remove_ranges) : [];
  const segments = [];
  let cursor = start;
  for (const [a, b] of ranges) {
    if (b <= cursor || a >= end) continue;
    if (a > cursor) segments.push([cursor, Math.min(a, end)]);
    cursor = Math.max(cursor, b);
  }
  if (cursor < end) segments.push([cursor, end]);
  const kept = segments.reduce((sum, [a, b]) => sum + (b - a), 0);
  const target = Number(opts.target_seconds) || 0;
  const speed = target > 0 && kept > target ? kept / target : Math.max(0.25, Math.min(4, Number(opts.speed) || 1));
  return {start, end, segments, speed, outDuration: kept / speed};
}

function _veLiveSourceToOut(timeline, t) {
  let kept = 0;
  for (const [a, b] of timeline.segments) {
    if (t <= a) break;
    kept += Math.min(t, b) - a;
  }
  return kept / timeline.speed;
}

function _veLiveOutToSource(timeline, o) {
  let remaining = Math.max(0, o) * timeline.speed;
  for (const [a, b] of timeline.segments) {
    if (remaining <= b - a) return a + remaining;
    remaining -= b - a;
  }
  const last = timeline.segments[timeline.segments.length - 1];
  return last ? last[1] : timeline.start;
}

// גל 31 (נמצא בבדיקת לפני/אחרי): רוויה 0 (שחור-לבן) היא ערך אמיתי - "|| 1" הפך אותה ל-1
function _veLiveSaturation(opts) {
  const value = opts.eq_saturation;
  return value === undefined || value === null || value === "" || !Number.isFinite(Number(value)) ? 1 : Number(value);
}

// הצבע בנגן החי: בהירות/ניגודיות/רוויה, וגלגלי צבע ועקומות דרך פילטר SVG (גל 25, 70-editor-grade.js)
function _veLiveColorFilter(opts) {
  const brightness = 1 + (Number(opts.eq_brightness) || 0);
  return `brightness(${brightness}) contrast(${Number(opts.eq_contrast) || 1}) saturate(${_veLiveSaturation(opts)})${_veLiveGradeFilter(opts)}`;
}

// גל 57: כשעמודת הנגן מוגבלת בגובה (הסטודיו) - הגובה שנשאר לנגן אחרי השורות שמעליו ופס הנגן (הפעלה, מיקום, זמן) שמתחתיו,
// כדי ששניהם ייכנסו בלי גלילה (היה 55% מגובה החלון: ב-1440x900 נחתכו 166 פיקסלים). מה שמתחת לפס הנגן (ציר-הזמן במצב
// מומחה) ממשיך להיגלל. לפי max-height ולא לפי הגובה בפועל - אחרת נגן קטן לא היה גדל כשמתפנה מקום (למשל כשהלוג מתקפל)
function _veLiveRoom() {
  const viewer = _veEl("veViewer"), live = _veEl("veLive"), bar = _veEl("veLiveBar");
  if (!viewer || !live) return 0;
  const style = getComputedStyle(viewer);
  const limit = parseFloat(style.maxHeight);
  if (!limit || style.position === "static") return 0;
  const end = bar && !bar.hidden ? bar : live;
  const top = viewer.getBoundingClientRect().top - viewer.scrollTop;
  return limit - (end.getBoundingClientRect().bottom - top - live.offsetHeight) - 8;
}

function _veLiveStageSize(out) {
  const wrap = _veEl("vePreviewStageWrap");
  const maxW = Math.max(160, (wrap.clientWidth || 480) - 4);
  // גל 31: במסך נייד קצת פחות גובה - כדי שפס הנגן (הפעלה, זמן) יישאר בתוך העמודה
  let maxH = Math.min(window.innerHeight * (document.body.classList.contains("ve-laptop") ? 0.48 : 0.55), 560);
  const room = _veLiveRoom();
  if (room > 0) maxH = Math.max(160, Math.min(room, window.innerHeight * 0.75));
  let h = maxH;
  let w = h * out.w / out.h;
  if (w > maxW) { w = maxW; h = w * out.h / out.w; }
  return {w: Math.round(w), h: Math.round(h)};
}

function _veLiveSourceUrl(file) {
  return "/api/video_editor/source_stream?folder=" + encodeURIComponent(state.folder) + "&file=" + encodeURIComponent(file);
}

async function startVeLivePreview() {
  const file = _veEl("vePreviewFile").value;
  const status = _veEl("vePreviewStatus");
  if (!state.folder || !file) { status.textContent = "⚠️ בחר תיקייה וקובץ קודם."; return; }
  _veSavePref("veLiveAuto", true);
  if (_veInClipMode()) closeVePreviewClip();
  const stage = _veStage();
  stage.classList.add("ve-stage-live");
  _veEl("vePreviewStageWrap").hidden = false;
  _veEl("veLiveBar").hidden = false;
  const video = _veEl("veLiveVideo");
  const sameFile = _veLive && _veLive.file === file;
  _veLive = {file, timeline: null, opts: null, out: null, raf: null, proxy: sameFile ? _veLive.proxy : null};
  status.className = "ve-field-msg";
  status.textContent = "🎥 תצוגה חיה (מקורבת) - " + file;
  const src = _veLive.proxy || _veLiveSourceUrl(file);
  if (video.getAttribute("src") !== src) {
    video.src = src;
    _veEl("veLiveBg").src = src;
    _veEl("veLiveError").hidden = true;
  } else if (!video.error) {
    // גל 27: הנגן כבר נפתח לבד כשנטענה התיקייה - לחיצה חוזרת על "חי" לא מסתירה שגיאת נגינה קיימת
    _veEl("veLiveError").hidden = true;
  }
  _veRebuildLive();
}

function stopVeLivePreview() {
  const video = _veEl("veLiveVideo");
  video.pause();
  _veEl("veLiveBg").pause();
  _veStage().classList.remove("ve-stage-live");
  _veEl("veLiveBar").hidden = true;
  if (_veLive && _veLive.raf) cancelAnimationFrame(_veLive.raf);
  if (!_veEl("vePreviewAfter").getAttribute("src") && !_veInClipMode()) _veEl("vePreviewStageWrap").hidden = true;
  _veRenderDragHandles();
}

function toggleVeLivePlay() {
  const video = _veEl("veLiveVideo");
  if (video.paused) video.play().catch(() => {}); else video.pause();
}

function toggleVeLiveMute() {
  const video = _veEl("veLiveVideo");
  video.muted = !video.muted;
  _veEl("veLiveMuteBtn").textContent = video.muted ? "🔇" : "🔊";
}

function _veLiveCurrentOut() {
  return _veLive && _veLive.timeline ? _veLiveSourceToOut(_veLive.timeline, _veEl("veLiveVideo").currentTime) : 0;
}

// "🎯 בדיקה מדויקת" - פריים מהשרת באותה נקודה בדיוק (אותה שרשרת כמו הרינדור)
function exactCheckVeLive() {
  _veEl("vePreviewTime").value = String(Math.round(_veLiveCurrentOut() * 10) / 10);
  stopVeLivePreview();
  refreshVePreview();
}

async function requestVeLiveProxy() {
  const status = _veEl("veLiveErrorText");
  const file = _veLive && _veLive.file;
  if (!file) return;
  status.textContent = "⏳ יוצר עותק קל לנגינה (480p) - פעם אחת לקובץ...";
  for (let attempt = 0; attempt < 900; attempt++) {
    let data;
    try {
      data = await (await fetch("/api/video_editor/proxy", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({folder: state.folder, file, retry: attempt === 0})})).json();
    } catch (e) { status.textContent = "⚠️ שגיאת רשת ביצירת הפרוקסי"; return; }
    if (data.state === "ready") {
      if (!_veLive || _veLive.file !== file) return;
      _veLive.proxy = data.url;
      _veEl("veLiveError").hidden = true;
      _veEl("veLiveVideo").src = data.url;
      _veEl("veLiveBg").src = data.url;
      _veRebuildLive();
      return;
    }
    if (data.state === "error" || data.error) { status.textContent = "⚠️ יצירת הפרוקסי נכשלה: " + (data.error || ""); return; }
    await new Promise(r => setTimeout(r, 2000));
  }
}

function _veScheduleLiveRebuild() {
  if (!_veInLiveMode()) return;
  clearTimeout(_veLiveBuildTimer);
  _veLiveBuildTimer = setTimeout(_veRebuildLive, 120);
}

function _veLivePresetStyle(position, marginPx) {
  const [vertical, horizontal] = position === "center" ? ["center", "center"] : String(position || "bottom-center").split("-");
  const style = {left: "", right: "", top: "", bottom: "", transform: ""};
  const tx = [];
  if (horizontal === "left") style.left = marginPx + "px";
  else if (horizontal === "right") style.right = marginPx + "px";
  else { style.left = "50%"; tx.push("translateX(-50%)"); }
  if (vertical === "top") style.top = marginPx + "px";
  else if (vertical === "bottom") style.bottom = marginPx + "px";
  else { style.top = "50%"; tx.push("translateY(-50%)"); }
  style.transform = tx.join(" ");
  return style;
}

function _veLivePlace(el, layerLike, size, stage) {
  if (layerLike.position === "custom" && Number.isFinite(layerLike.x) && Number.isFinite(layerLike.y)) {
    Object.assign(el.style, {left: (layerLike.x * stage.w) + "px", top: (layerLike.y * stage.h) + "px", right: "", bottom: "", transform: "translate(-50%, -50%)"});
  } else {
    Object.assign(el.style, _veLivePresetStyle(layerLike.position, stage.h * 0.04));
  }
}

function _veRebuildLive() {
  if (!_veLive || !_veInLiveMode()) return;
  const video = _veEl("veLiveVideo");
  const opts = _veLiveOptions(_veLive.file);
  const out = _veLiveOutputSize(opts);
  const stageSize = _veLiveStageSize(out);
  const stage = _veStage();
  stage.dataset.outputWidth = out.w;
  stage.dataset.outputHeight = out.h;
  const live = _veEl("veLive");
  live.style.width = stageSize.w + "px";
  live.style.height = stageSize.h + "px";
  const scale = stageSize.h / out.h;
  _veLive.opts = opts;
  _veLive.out = out;
  _veLive.stage = stageSize;
  _veLive.timeline = video.duration ? _veLiveTimeline(opts, video.duration) : null;
  // נגן עצור מחוץ למה שנשאר (למשל אחרי שינוי התחלת החיתוך) קופץ לקטע הבא שנשאר - הפריים שמוצג הוא פריים של הפלט
  const kept = _veLive.timeline && _veLive.timeline.segments;
  if (kept && kept.length && video.paused && !kept.some(([a, b]) => video.currentTime >= a - 0.02 && video.currentTime < b)) {
    const next = kept.find(([a]) => a > video.currentTime);
    video.currentTime = next ? next[0] : _veLive.timeline.start;
  }
  // מילוי המסגרת: חיתוך (cover), שוליים (contain) או רקע מטושטש
  const portraitish = out.h >= out.w;
  const fill = opts.blur_background ? "blur" : opts.fit === "pad" ? "contain" : opts.fit === "crop" ? "cover" : (portraitish ? "cover" : "contain");
  live.dataset.fill = fill;
  live.style.background = fill === "contain" ? (opts.pad_color || "#000") : "#000";
  const rotate = Number(opts.rotate) || 0;
  const flipH = opts.flip === "h" || opts.flip === "both", flipV = opts.flip === "v" || opts.flip === "both";
  const rot = _veEl("veLiveRot");
  const swap = rotate === 90 || rotate === 270;
  rot.style.width = (swap ? stageSize.h : stageSize.w) + "px";
  rot.style.height = (swap ? stageSize.w : stageSize.h) + "px";
  rot.style.transform = `translate(-50%, -50%) rotate(${rotate}deg) scale(${flipH ? -1 : 1}, ${flipV ? -1 : 1})`;
  video.style.objectFit = fill === "cover" ? "cover" : "contain";
  const saturation = _veLiveSaturation(opts);
  video.style.filter = _veLiveColorFilter(opts);
  const bg = _veEl("veLiveBg");
  bg.hidden = fill !== "blur";
  bg.style.filter = `blur(${Math.max(8, stageSize.w / 30)}px) brightness(0.75) saturate(${saturation})`;
  video.playbackRate = _veLive.timeline ? Math.max(0.0625, Math.min(16, _veLive.timeline.speed)) : 1;
  const vignette = {light: 0.35, medium: 0.5, strong: 0.7}[opts.vignette] || 0;
  _veEl("veLiveVignette").style.background = vignette ? `radial-gradient(ellipse at center, transparent 45%, rgba(0,0,0,${vignette}) 100%)` : "none";
  const frame = Number(opts.frame_thickness) || 0, radius = frame > 0 ? Number(opts.frame_radius) || 0 : 0;
  const framePx = `${Math.max(1, frame * scale)}px`, frameColor = opts.frame_color || "#FFFFFF";
  Object.assign(_veEl("veLiveFrame").style, radius > 0
    ? {inset: framePx, borderRadius: `${radius * scale}px`, boxShadow: `0 0 0 100vmax ${frameColor}`}
    : {inset: "", borderRadius: "", boxShadow: frame > 0 ? `inset 0 0 0 ${framePx} ${frameColor}` : "none"});
  _veLiveBuildOverlays(opts, out, stageSize, scale);
  // מה שהנגן לא מדמה - שיידעו שצריך "בדיקה מדויקת"
  const skipped = [];
  if ((opts.lut_path || "").trim()) skipped.push("LUT");
  if (opts.denoise || opts.sharpen) skipped.push("רעש/חידוד");
  if (opts.stabilize) skipped.push("ייצוב");
  if (opts.chromakey) skipped.push("כרומה-קי");
  if (opts.auto_levels || (Number(opts.eq_gamma) || 1) !== 1) skipped.push("גמא/רמות");
  if ((opts.remove_watermark_region || "").trim()) skipped.push("מחיקת לוגו ישן");
  if (opts.trim_silence || opts.remove_mid_silence) skipped.push("הסרת שקט אוטומטית");
  if (_veAudioFxActive(opts) && _veHasAudioOut(opts)) skipped.push("EQ/קומפרסור/הפחתת רעש בשמע");
  if ((opts._layers || []).some(l => l.type === "video" && l.audio && l.audio !== "mute")) skipped.push("השמע של ה-B-roll");
  _veEl("veLiveNote").textContent = skipped.length ? `ℹ️ לא מוצג בתצוגה החיה: ${skipped.join(", ")} - "🎯 בדיקה מדויקת" מראה אותם.` : "";
  _veRenderDragHandles();
  applyVeSafeZones();
  _veLiveTick();
}

function _veLiveBuildOverlays(opts, out, stage, scale) {
  const box = _veEl("veLiveOverlays");
  box.innerHTML = "";
  const items = [];
  // לוגו
  if ((opts.watermark_path || "").trim()) {
    const img = document.createElement("img");
    img.className = "ve-live-item";
    img.src = "/api/watermark_image?path=" + encodeURIComponent(opts.watermark_path.trim());
    img.style.width = ((Number(opts.watermark_scale) || 0.15) * stage.w) + "px";
    img.style.opacity = String(opts.watermark_opacity ?? 1);
    const vertPos = opts.watermark_position_vertical;
    const position = out.h > out.w && vertPos ? vertPos : opts.watermark_position;
    const custom = opts.watermark_x !== null && opts.watermark_x !== undefined && opts.watermark_y !== null && opts.watermark_y !== undefined;
    _veLivePlace(img, custom ? {position: "custom", x: +opts.watermark_x, y: +opts.watermark_y} : {position}, null, stage);
    box.appendChild(img);
  }
  // PiP
  if ((opts.pip_path || "").trim()) {
    const path = opts.pip_path.trim();
    const slash = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
    const pip = document.createElement("video");
    pip.className = "ve-live-item ve-live-pip";
    pip.muted = true; pip.playsInline = true; pip.preload = "auto";
    pip.src = "/api/video_editor/source_stream?folder=" + encodeURIComponent(path.slice(0, slash)) + "&file=" + encodeURIComponent(path.slice(slash + 1));
    pip.style.width = ((Number(opts.pip_scale) || 0.3) * stage.w) + "px";
    pip.style.opacity = String(opts.pip_opacity ?? 1);
    const custom = opts.pip_x !== null && opts.pip_x !== undefined && opts.pip_y !== null && opts.pip_y !== undefined;
    _veLivePlace(pip, custom ? {position: "custom", x: +opts.pip_x, y: +opts.pip_y} : {position: opts.pip_position || "bottom-right"}, null, stage);
    box.appendChild(pip);
    items.push({kind: "pip", el: pip});
  }
  // שכבות מתוזמנות
  for (const layer of opts._layers) {
    const el = layer.type === "image" ? document.createElement("img") : layer.type === "video" ? document.createElement("video") : document.createElement("div");
    el.className = "ve-live-item ve-live-layer";
    if (layer.type === "video") {
      // גל 26: B-roll - וידאו מושתק שמסונכרן לזמן הפלט (ב-tick), מסך מלא או חלון
      const path = (layer.path || "").trim();
      if (!path) continue;
      const slash = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
      el.muted = true; el.playsInline = true; el.preload = "auto";
      el.src = "/api/video_editor/source_stream?folder=" + encodeURIComponent(path.slice(0, slash)) + "&file=" + encodeURIComponent(path.slice(slash + 1));
      if (layer.fit === "pip") el.style.width = ((Number(layer.scale) || 0.35) * stage.w) + "px";
      else { el.classList.add("ve-live-broll-full"); el.style.objectFit = layer.fit === "fit" ? "contain" : "cover"; }
    } else if (layer.type === "image") {
      if (!(layer.path || "").trim()) continue;
      el.src = "/api/watermark_image?path=" + encodeURIComponent(layer.path.trim());
      el.style.width = ((Number(layer.scale) || 0.2) * stage.w) + "px";
    } else {
      if (layer.type === "text" && !(layer.text || "").trim()) continue;
      el.style.fontFamily = `"${layer.font || "Arial"}", sans-serif`;
      el.style.fontSize = Math.max(6, (Number(layer.font_size) || 48) * scale) + "px";
      el.style.color = layer.color || "#FFFFFF";
      if (layer.box) { el.style.background = "rgba(0,0,0,.5)"; el.style.padding = Math.max(1, 12 * scale) + "px"; }
    }
    if (!(layer.type === "video" && layer.fit !== "pip")) _veLivePlace(el, layer, null, stage);
    if ((layer.keyframes || []).length >= 2) el.style.transform = "translate(-50%, -50%)";  // מיקום מונפש = מרכז בנקודה
    el.dataset.baseTransform = el.style.transform || "";
    el.dataset.baseFont = el.style.fontSize || "";
    box.appendChild(el);
    items.push({kind: "layer", el, layer});
  }
  // סרגל התקדמות
  if (opts.progress_bar) {
    const bar = document.createElement("div");
    bar.className = "ve-live-progress";
    bar.style.height = Math.max(2, (Number(opts.progress_bar_height) || 8) * scale) + "px";
    bar.style.background = opts.progress_bar_color || "#FF0000";
    bar.style[opts.progress_bar_position === "top" ? "top" : "bottom"] = "0";
    box.appendChild(bar);
    items.push({kind: "progress", el: bar});
  }
  // כתובית לדוגמה בעיצוב שנבחר
  if (opts.captions) {
    const cap = document.createElement("div");
    cap.className = "ve-live-caption";
    cap.textContent = "כתובית לדוגמה · Sample caption";
    cap.style.fontFamily = `"${opts.caption_font || "Arial"}", sans-serif`;
    cap.style.fontSize = Math.max(8, (Number(opts.caption_font_size) || 24) * scale * 2) + "px";
    cap.style.color = opts.caption_color || "#FFFFFF";
    const position = opts.caption_position || "bottom";
    cap.style[position === "top" ? "top" : "bottom"] = position === "center" ? "45%" : (stage.h * 0.08) + "px";
    if (opts.caption_style === "box") { cap.style.background = "rgba(0,0,0,.6)"; cap.style.padding = "0 .3em"; }
    else if (opts.caption_style === "bold") cap.style.fontWeight = "800";
    cap.style.textShadow = opts.caption_style === "box" ? "none" : "0 0 3px #000, 0 0 3px #000";
    box.appendChild(cap);
  }
  _veLive.items = items;
}

function _veLiveFormat(seconds) {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// מצב שתלוי-זמן: הופעה/היעלמות שכבות, הנפשות, טיימר, סרגל, fade, ושעון הנגן
function _veLiveTick() {
  if (!_veLive || !_veInLiveMode()) return;
  const video = _veEl("veLiveVideo");
  const timeline = _veLive.timeline;
  const opts = _veLive.opts || {};
  const o = timeline ? _veLiveSourceToOut(timeline, video.currentTime) : 0;
  const outDuration = timeline ? timeline.outDuration : 0;
  for (const item of _veLive.items || []) {
    if (item.kind === "progress") { item.el.style.width = (outDuration ? Math.min(100, o / outDuration * 100) : 0) + "%"; continue; }
    if (item.kind === "pip") {
      if (Math.abs(item.el.currentTime - o) > 0.3 && item.el.duration) item.el.currentTime = Math.min(o, item.el.duration - 0.05);
      if (video.paused !== item.el.paused) { if (video.paused) item.el.pause(); else item.el.play().catch(() => {}); }
      continue;
    }
    const layer = item.layer;
    const start = Number(layer.start) || 0;
    const end = layer.end === null || layer.end === undefined || layer.end === "" ? Infinity : Number(layer.end);
    const visible = o >= start && o < end;
    item.el.style.display = visible ? "" : "none";
    if (layer.type === "video") {
      const target = (Number(layer.source_in) || 0) + Math.max(0, o - start);
      if (!visible) { if (!item.el.paused) item.el.pause(); }
      else {
        if (Math.abs(item.el.currentTime - target) > 0.3 && item.el.readyState > 0) item.el.currentTime = target;
        if (video.paused !== item.el.paused) { if (video.paused) item.el.pause(); else item.el.play().catch(() => {}); }
      }
    }
    if (!visible) continue;
    let opacity = layer.opacity ?? 1;
    const since = o - start, until = end - o;
    const kf = typeof _veInterpKeyframes === "function" ? _veInterpKeyframes(layer, o) : null;
    if (kf) {
      const stage = _veLive.stage || {w: 0, h: 0};
      if (Number.isFinite(kf.x)) { item.el.style.left = (kf.x * stage.w) + "px"; item.el.style.right = ""; }
      if (Number.isFinite(kf.y)) { item.el.style.top = (kf.y * stage.h) + "px"; item.el.style.bottom = ""; }
      if (Number.isFinite(kf.opacity)) opacity = kf.opacity;
      if (Number.isFinite(kf.scale) && item.el.dataset.baseFont) item.el.style.fontSize = (parseFloat(item.el.dataset.baseFont) * kf.scale) + "px";
    }
    if (layer.animation === "fade") opacity *= Math.min(1, since / 0.5, until / 0.5);
    item.el.style.opacity = String(Math.max(0, opacity));
    let transform = item.el.dataset.baseTransform || "";
    if (layer.animation === "slide" && since < 0.5) transform += ` translateX(${-(1 - since / 0.5) * 120}%)`;
    item.el.style.transform = transform;
    if (layer.type === "text") {
      const text = layer.text || "";
      if (layer.animation === "typewriter") {
        const reveal = Math.min(2, Math.max(0.5, text.length * 0.06));
        item.el.textContent = text.slice(0, Math.ceil(text.length * Math.min(1, since / reveal)));
      } else item.el.textContent = text;
    } else if (layer.type === "timer") {
      const total = Number(layer.timer_seconds) > 0 ? Number(layer.timer_seconds) : (Number.isFinite(end) ? end - start : Math.max(0, outDuration - start));
      item.el.textContent = _veLiveFormat(layer.timer_mode === "elapsed" ? since : Math.max(0, total - since));
    } else if (layer.type === "timestamp") {
      item.el.textContent = new Date(Date.now() - (outDuration - o) * 1000).toLocaleTimeString("he-IL");
    }
  }
  const fadeIn = Number(opts.fade_in_seconds) || 0, fadeOut = Number(opts.fade_out_seconds) || 0;
  let dark = 0;
  if (fadeIn > 0 && o < fadeIn) dark = 1 - o / fadeIn;
  if (fadeOut > 0 && outDuration && o > outDuration - fadeOut) dark = Math.max(dark, (o - (outDuration - fadeOut)) / fadeOut);
  _veEl("veLiveFade").style.opacity = String(Math.max(0, Math.min(1, dark)));
  _veEl("veLiveTime").textContent = `${_veLiveFormat(o)} / ${_veLiveFormat(outDuration)}`;
  const seek = _veEl("veLiveSeek");
  if (document.activeElement !== seek && outDuration) seek.value = String(Math.round(o / outDuration * 1000));
  _veEl("veLivePlayBtn").textContent = video.paused ? "▶️" : "⏸️";
  if (typeof _veOnLiveTick === "function") _veOnLiveTick(o);
}

function _veLiveLoop() {
  if (!_veLive) return;
  _veLiveTick();
  const video = _veEl("veLiveVideo");
  _veLive.raf = video.paused ? null : requestAnimationFrame(_veLiveLoop);
}

(function _veSetupLivePlayer() {
  const video = _veEl("veLiveVideo");
  const bg = _veEl("veLiveBg");
  video.addEventListener("loadedmetadata", () => {
    if (!_veLive) return;
    _veLive.timeline = _veLiveTimeline(_veLive.opts || _veLiveOptions(_veLive.file), video.duration);
    video.currentTime = _veLive.timeline.start;
    _veRebuildLive();
  });
  video.addEventListener("play", () => { bg.play().catch(() => {}); if (_veLive && !_veLive.raf) _veLive.raf = requestAnimationFrame(_veLiveLoop); });
  video.addEventListener("pause", () => { bg.pause(); _veLiveTick(); });
  video.addEventListener("seeked", () => { if (Math.abs(bg.currentTime - video.currentTime) > 0.2) bg.currentTime = video.currentTime; _veLiveTick(); });
  video.addEventListener("timeupdate", () => {
    if (!_veLive || !_veLive.timeline) return;
    const t = video.currentTime, timeline = _veLive.timeline;
    const inside = timeline.segments.find(([a, b]) => t >= a - 0.02 && t < b);
    if (!inside) {
      const next = timeline.segments.find(([a]) => a > t);
      if (next) video.currentTime = next[0];
      else { video.currentTime = timeline.start; if (!_veEl("veLiveLoop").checked) video.pause(); }
    }
  });
  video.addEventListener("error", () => {
    if (!_veLive) return;
    _veEl("veLiveError").hidden = false;
    _veEl("veLiveErrorText").textContent = "⚠️ הדפדפן לא מצליח לנגן את הקובץ הזה ישירות (קודק/מיכל). אפשר ליצור עותק קל לנגינה:";
  });
  _veEl("veLiveSeek").addEventListener("input", (e) => {
    if (!_veLive || !_veLive.timeline) return;
    video.currentTime = _veLiveOutToSource(_veLive.timeline, e.target.value / 1000 * _veLive.timeline.outDuration);
  });
  // כל שינוי הגדרה מתעדכן בנגן מיד
  document.getElementById("videoEditorOptions").addEventListener("input", () => _veScheduleLiveRebuild());
  document.getElementById("videoEditorOptions").addEventListener("change", () => _veScheduleLiveRebuild());
  window.addEventListener("resize", () => _veScheduleLiveRebuild());
  _veEl("vePreviewFile").addEventListener("change", () => {
    if (_veInLiveMode() || (_veLoadPref("veLiveAuto", false) && !_veInClipMode() && _veEl("vePreviewStageWrap").hidden)) startVeLivePreview();
  });
})();

// ידיות גרירה ורינדור-מחדש בתצוגה החיה: מידות הפלט מהנגן, ובלי לבקש פריים מהשרת
const _veOutputSizeBeforeW13 = _veOutputSize;
_veOutputSize = function () {
  if (_veInLiveMode() && _veLive && _veLive.out) return {..._veLive.out};
  return _veOutputSizeBeforeW13();
};
const _veCommitHandleBeforeW13 = _veCommitHandle;
_veCommitHandle = function (handle) {
  if (!_veInLiveMode()) return _veCommitHandleBeforeW13(handle);
  const refresh = refreshVePreview;
  refreshVePreview = () => {};  // בתצוגה החיה השינוי נראה מיד - בלי לבקש פריים מהשרת
  try { _veCommitHandleBeforeW13(handle); } finally { refreshVePreview = refresh; }
  _veScheduleLiveRebuild();
};
// פריים/קטע מהשרת מחליפים את התצוגה החיה (זה מה שהמשתמש ביקש)
const _refreshVePreviewBeforeW13 = refreshVePreview;
refreshVePreview = async function () {
  if (_veInLiveMode()) stopVeLivePreview();
  return _refreshVePreviewBeforeW13();
};
const _refreshVePreviewClipBeforeW13 = refreshVePreviewClip;
refreshVePreviewClip = async function () {
  if (_veInLiveMode()) stopVeLivePreview();
  return _refreshVePreviewClipBeforeW13();
};
