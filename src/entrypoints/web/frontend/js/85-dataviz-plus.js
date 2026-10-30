// ============================================================================
// 27.10.2026: 25 ההצעות לעורך הגרפים מהבדיקה הטכנית (25.10) - bundle רביעי של המסך (dataviz_plus), שנטען אחרי
// dataviz_tools. כל ההצעות עוטפות את מה שכבר יש (התצוגה החיה, העורך, הסיפור, הישויות) ולא מחליפות אותו:
//  * עריכה על התצוגה: לחיצה על כותרת / ישות / תיבת הסיום פותחת את מה שצריך, עריכת טקסט במקום, גרירת תיבת הסיום
//    והערות לישות, צבע בלחיצה על עמודה (אזורי הלחיצה מגיעים מהשרת - preview_frame?meta=1)
//  * תצוגה: לאורך לצד הרגילה, אזורים בטוחים של Shorts / TikTok, גלילה חלקה בסליידר, וידאו במקום GIF, לפני / אחרי
//  * סיפור: מצב במאי (M / קליק ימני), בלוקים נגררים מתחת לסליידר, הקלטה רציפה, רינדור טווח
//  * עוד: sparkline ודגלים בלשונית הישויות, מראות עם תמונות, תצוגת גופן, לפני / אחרי בריחוף, ציון פרק, גרסאות עם
//    תמונות, שמירה כתבנית, מצב כרטיס המסך בזמן רינדור ושימור הצופים מיוטיוב
// ============================================================================

const dvzPlus = {meta: null, timeline: null, timelineKey: "", range: null, frames: new Map(), spark: {}, flags: {}, retention: {},
  sideBySide: false, safeZones: false, beforeAfter: false, scrub: null, gpuTimer: 0, recording: null, scores: {}};
const DVZ_INLINE_PATHS = ["title", "subtitle", "labels.total", "intro.title", "intro.subtitle", "intro.question", "end_screen.text", "outro.title"];
const DVZ_SCRUB_FRAMES = 60;

function _dvzPlusStage() {
  return document.querySelector("#dvzPreviewPane .dvz-preview-stage");
}

function _dvzDraftKey() {
  return `${dvzState.selected}|${_dvzDraftParam()}|${document.getElementById("dvzChart").value}`;
}

// ============================================================================
// 1-3, 15: אזורי לחיצה על התצוגה - שדה, עריכה במקום, ישות (צבע), גרירה
// ============================================================================
function _dvzHitLayer() {
  const stage = _dvzPlusStage();
  let layer = document.getElementById("dvzHitLayer");
  if (!layer && stage) {
    layer = _dvzEdEl("div", "dvz-hit-layer");
    layer.id = "dvzHitLayer";
    stage.append(layer);
    if (typeof ResizeObserver === "function") new ResizeObserver(() => _dvzFitOverlays()).observe(document.getElementById("dvzPreviewImg"));
  }
  return layer;
}

// השכבות שמעל התמונה (אזורי הלחיצה, לפני / אחרי, אזורים בטוחים) בדיוק על התמונה - הבמה רחבה ממנה והתמונה במרכז
function _dvzFitToImage(el, img) {
  if (!el || !img) return;
  Object.assign(el.style, {left: `${img.offsetLeft}px`, top: `${img.offsetTop}px`, width: `${img.offsetWidth}px`, height: `${img.offsetHeight}px`});
}

function _dvzFitOverlays() {
  const img = document.getElementById("dvzPreviewImg");
  for (const id of ["dvzHitLayer", "dvzBeforeWrap"]) _dvzFitToImage(document.getElementById(id), img);
  const stage = _dvzPlusStage();
  const zones = stage && stage.querySelector(":scope > .dvz-safe-zones");
  _dvzFitToImage(zones, img);
  const side = document.getElementById("dvzPreviewSide");
  if (side) _dvzFitToImage(side.querySelector(".dvz-safe-zones"), document.getElementById("dvzPreviewImg2"));
}

async function _dvzLoadFrameMeta() {
  const layer = _dvzHitLayer();
  if (!layer) return;
  if (dvzState.animate || !dvzState.selected) { layer.replaceChildren(); dvzPlus.meta = null; return; }
  const request = uiLatest("dvz:meta");
  try {
    const url = _dvzThumbUrl(dvzState.selected, _dvzPosition().toFixed(3), 0.5, {..._dvzPreviewParams(), meta: "1"});
    const resp = await fetch(url, {signal: request.signal});
    if (!resp.ok || !request.current()) return;
    dvzPlus.meta = await resp.json();
  } catch (e) {
    if (uiIsAbort(e)) return;
    dvzPlus.meta = null;
  }
  _dvzRenderHits();
  _dvzRenderSafeZones();
}

function _dvzHitLabel(target) {
  if (target.startsWith("entity:")) return "🎨 " + target.slice(7);
  if (target === "outro") return "✥ תיבת הסיום - גרירה מזיזה, לחיצה עורכת";
  if (target.startsWith("callout:")) return "✥ הערה לישות - גרירה מזיזה";
  if (target.startsWith("tab:")) return "✏️ עריכה בעורך";
  return "✏️ לחיצה לעריכה";
}

function _dvzRenderHits() {
  const layer = _dvzHitLayer();
  if (!layer) return;
  const hits = (dvzPlus.meta && dvzPlus.meta.hits) || [];
  layer.classList.toggle("is-off", !!dvzState.annotate);
  const keep = [...layer.querySelectorAll(".dvz-inline-edit, .dvz-entity-pop")];   // עריכה פתוחה לא נעלמת בטעינה
  _dvzFitOverlays();
  layer.replaceChildren(...keep, ...hits.map((hit, i) => {
    const box = _dvzEdEl("button", "dvz-hit");
    box.type = "button";
    box.dataset.target = hit.target;
    box.dataset.index = String(i);
    const [x0, y0, x1, y1] = hit.box;
    Object.assign(box.style, {left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%`});
    box.title = _dvzHitLabel(hit.target);
    box.setAttribute("aria-label", box.title);
    return box;
  }));
}

function _dvzHitTarget(target) {
  const [kind, ...rest] = target.split(":");
  return {kind, value: rest.join(":"), parts: rest};
}

async function _dvzOnHitClick(box) {
  const {kind, value, parts} = _dvzHitTarget(box.dataset.target);
  if (kind === "path") {
    if (DVZ_INLINE_PATHS.includes(value)) await _dvzInlineEdit(box, value);
    else await dvzEditField(value);
  } else if (kind === "outro") {
    await _dvzInlineEdit(box, "outro.title");
  } else if (kind === "entity") {
    await _dvzEntityPopover(box, value);
  } else if (kind === "callout") {
    await _dvzOpenEditorTab("story");
  } else if (kind === "tab") {
    await _dvzOpenEditorTab(value);
  }
  return parts;
}

async function _dvzOpenEditorTab(tab) {
  const editor = document.getElementById("dvzEditor");
  editor.open = true;
  await dvzLoadEditor();
  dvzEd.tab = tab;
  _dvzRenderEditor();
  editor.scrollIntoView({block: "nearest"});
}

function _dvzFieldValue(path) {
  if (path in dvzEd.draft) return dvzEd.draft[path];
  for (const group of (dvzEd.data && dvzEd.data.groups) || []) {
    const field = group.fields.find(f => f.path === path);
    if (field) return field.value;
  }
  return "";
}

// --- 3: עריכת טקסט במקום - שדה מעל הטקסט בתצוגה; Enter שומר לטיוטה, Esc מבטל ---
async function _dvzInlineEdit(box, path) {
  await dvzLoadEditor();
  document.querySelectorAll(".dvz-inline-edit").forEach(el => el.remove());
  const input = _dvzEdEl("input", "dvz-inline-edit");
  input.type = "text";
  input.maxLength = 200;
  input.value = _dvzFieldValue(path) || "";
  input.setAttribute("aria-label", "עריכה במקום");
  input.title = "Enter - לטיוטה · Esc - ביטול";
  Object.assign(input.style, {left: box.style.left, top: box.style.top, minWidth: box.style.width});
  let done = false;
  const finish = (save) => {
    if (done) return;
    done = true;
    if (save && input.value !== String(_dvzFieldValue(path) || "")) {
      _dvzStage(path, input.value);
      if (document.getElementById("dvzEditor").open) _dvzRenderEditor();
    }
    input.remove();
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); finish(true); }
    else if (e.key === "Escape") { e.preventDefault(); finish(false); }
  });
  input.addEventListener("blur", () => finish(true));
  _dvzHitLayer().append(input);
  input.focus();
  input.select();
}

// --- 15: לחיצה על ישות - צבע קבוע, ולשונית הישויות ---
async function _dvzEntityPopover(box, name) {
  await dvzLoadEditor();
  document.querySelectorAll(".dvz-entity-pop").forEach(el => el.remove());
  const pop = _dvzEdEl("div", "dvz-entity-pop");
  pop.setAttribute("role", "dialog");
  pop.setAttribute("aria-label", "צבע לישות");
  Object.assign(pop.style, {left: box.style.left, top: `calc(${box.style.top} + ${box.style.height})`});
  const colors = {...("colors" in dvzEd.draft ? dvzEd.draft.colors : (dvzEd.data.colors || {}))};
  const color = _dvzColorInput(colors[name] || "#3f6a9e", (v) => { colors[name] = v; _dvzStage("colors", {...colors}); }, "צבע לישות");
  const clear = _dvzEdEl("button", "btn-xs", "↺ מהפלטה");
  clear.type = "button";
  clear.onclick = () => { delete colors[name]; _dvzStage("colors", {...colors}); pop.remove(); };
  const more = _dvzEdEl("button", "btn-xs", "🏷️ בלשונית הישויות");
  more.type = "button";
  more.onclick = () => { pop.remove(); _dvzOpenEditorTab("entities"); };
  const close = _dvzEdEl("button", "btn-xs btn-ghost", "✕");
  close.type = "button";
  close.setAttribute("aria-label", "סגור");
  close.onclick = () => pop.remove();
  pop.append(_dvzEdEl("strong", "", name), color, clear, more, close);
  _dvzHitLayer().append(pop);
  color.focus();
}

// --- 2: גרירה של תיבת הסיום ושל הערה לישות ---
function _dvzInitHitDrag() {
  const layer = _dvzHitLayer();
  if (!layer || layer.dataset.ready) return;
  layer.dataset.ready = "1";
  let drag = null;
  layer.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".dvz-inline-edit, .dvz-entity-pop")) return;
    const box = e.target.closest(".dvz-hit");
    if (!box || e.button !== 0) return;
    const target = box.dataset.target;
    drag = {box, target, x: e.clientX, y: e.clientY, moved: false, rect: layer.getBoundingClientRect(),
      draggable: target === "outro" || target.startsWith("callout:")};
    if (drag.draggable) box.setPointerCapture(e.pointerId);
  });
  layer.addEventListener("pointermove", (e) => {
    if (!drag || !drag.draggable) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 5) return;
    drag.moved = true;
    drag.box.classList.add("is-dragging");
    drag.box.style.transform = `translate(${dx}px, ${dy}px)`;
  });
  layer.addEventListener("pointerup", async (e) => {
    if (!drag) return;
    const current = drag;
    drag = null;
    if (!current.moved) { await _dvzOnHitClick(current.box); return; }
    const fx = (e.clientX - current.x) / current.rect.width, fy = (e.clientY - current.y) / current.rect.height;
    await dvzLoadEditor();
    if (current.target === "outro") _dvzDropOutro(current.box, fx, fy);
    else _dvzDropCallout(current.target, fx, fy);
  });
}

function _dvzDropOutro(box, fx, fy) {
  const meta = dvzPlus.meta;
  if (!meta || !meta.axes_box) return;
  const [ax0, ay0, ax1, ay1] = meta.axes_box;   // חלקים של הפריים, מלמטה-שמאל
  const left = parseFloat(box.style.left) / 100 + fx, top = parseFloat(box.style.top) / 100 + fy;
  const cx = left + parseFloat(box.style.width) / 200, cy = 1 - (top + parseFloat(box.style.height) / 200);
  const clamp = (v) => Math.max(-0.5, Math.min(1.5, Math.round(v * 1000) / 1000));
  _dvzStage("outro.position", [clamp((cx - ax0) / (ax1 - ax0)), clamp((cy - ay0) / (ay1 - ay0))]);
  uiToast('תיבת הסיום זזה - "שמור" כדי שתישאר שם', "ok");
}

function _dvzDropCallout(target, fx, fy) {
  const meta = dvzPlus.meta;
  const [, index, dx0, dy0] = target.split(":");
  const items = _dvzStoryItems("callouts").map(item => ({...item}));
  const item = items[Number(index)];
  if (!item || !meta || !meta.fig_pt) return;
  const [wpt, hpt] = meta.fig_pt;
  const baseX = item.dx !== undefined ? Number(item.dx) : Number(dx0 || 28);
  const baseY = item.dy !== undefined ? Number(item.dy) : Number(dy0 || -30);
  item.dx = Math.max(-400, Math.min(400, Math.round(baseX + fx * wpt)));
  item.dy = Math.max(-400, Math.min(400, Math.round(baseY - fy * hpt)));   // בנקודות y עולה למעלה
  _dvzStage("story.callouts", items);
}

// ============================================================================
// 4-5: לאורך לצד הרגילה, ואזורים בטוחים של Shorts / TikTok
// ============================================================================
const DVZ_SAFE_ZONES = {
  shorts: [[0.86, 0.42, 1, 0.88, "כפתורים"], [0, 0.82, 1, 1, "כותרת וערוץ"], [0, 0, 1, 0.07, "חיפוש"]],
  tiktok: [[0.84, 0.38, 1, 0.86, "כפתורים"], [0, 0.8, 1, 1, "כיתוב ושם"], [0, 0, 1, 0.09, "לשוניות"]],
};

function _dvzVerticalTarget() {
  const select = document.getElementById("dvzTarget");
  return select && (select.value === "tiktok" || select.value === "shorts") ? select.value : "shorts";
}

async function _dvzLoadSideBySide() {
  const stage = _dvzPlusStage();
  let side = document.getElementById("dvzPreviewSide");
  if (!dvzPlus.sideBySide || !stage || !dvzState.selected) {
    if (side) side.remove();
    stage && stage.classList.remove("has-side");
    return;
  }
  if (!side) {
    side = _dvzEdEl("figure", "dvz-preview-side");
    side.id = "dvzPreviewSide";
    const img = _dvzEdEl("img");
    img.id = "dvzPreviewImg2";
    img.alt = "אותו רגע לאורך";
    side.append(img, _dvzEdEl("figcaption", "hint", "📱 לאורך"));
    stage.after(side);
  }
  stage.classList.add("has-side");
  const img = document.getElementById("dvzPreviewImg2");
  const url = _dvzThumbUrl(dvzState.selected, _dvzPosition().toFixed(3), 0.35, {..._dvzPreviewParams(), target: _dvzVerticalTarget()});
  try {
    const resp = await fetch(url);
    if (!resp.ok) return;
    if (img.dataset.blob) URL.revokeObjectURL(img.dataset.blob);
    img.dataset.blob = URL.createObjectURL(await resp.blob());
    img.src = img.dataset.blob;
  } catch (e) { /* בלי התצוגה לאורך */ }
  _dvzRenderSafeZones();
}

function dvzToggleSideBySide() {
  dvzPlus.sideBySide = !dvzPlus.sideBySide;
  document.getElementById("dvzSideBtn").setAttribute("aria-pressed", String(dvzPlus.sideBySide));
  _dvzLoadSideBySide();
}

function dvzToggleSafeZones() {
  dvzPlus.safeZones = !dvzPlus.safeZones;
  document.getElementById("dvzSafeBtn").setAttribute("aria-pressed", String(dvzPlus.safeZones));
  _dvzRenderSafeZones();
}

function _dvzSafeLayer(host) {
  let svg = host.querySelector(".dvz-safe-zones");
  if (!svg) {
    svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "dvz-safe-zones");
    svg.setAttribute("viewBox", "0 0 100 100");
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("aria-hidden", "true");
    host.append(svg);
  }
  return svg;
}

function _dvzRenderSafeZones() {
  const hosts = [];
  const side = document.getElementById("dvzPreviewSide");
  if (side) hosts.push([side, _dvzVerticalTarget()]);
  const select = document.getElementById("dvzTarget");
  if (select && DVZ_SAFE_ZONES[select.value]) hosts.push([_dvzPlusStage(), select.value]);
  document.querySelectorAll(".dvz-safe-zones").forEach(svg => { if (!dvzPlus.safeZones || !hosts.some(([h]) => h && h.contains(svg))) svg.remove(); });
  if (!dvzPlus.safeZones) return;
  for (const [host, target] of hosts) {
    if (!host) continue;
    const svg = _dvzSafeLayer(host);
    svg.replaceChildren(...DVZ_SAFE_ZONES[target].map(([x0, y0, x1, y1, label]) => {
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      for (const [k, v] of Object.entries({x: x0 * 100, y: y0 * 100, width: (x1 - x0) * 100, height: (y1 - y0) * 100})) rect.setAttribute(k, String(v));
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = label;
      rect.append(title);
      return rect;
    }));
  }
  _dvzFitOverlays();
}

// ============================================================================
// 17: גלילה חלקה - בזמן גרירת הסליידר פריים קטן (מהמטמון או מהשרת), והשכנים נטענים מראש
// ============================================================================
function _dvzScrubKey(pos) {
  return `${_dvzDraftKey()}|${pos}`;
}

async function _dvzSmallFrame(pos) {
  const key = _dvzScrubKey(pos);
  if (dvzPlus.frames.has(key)) {
    const url = dvzPlus.frames.get(key);
    dvzPlus.frames.delete(key);
    dvzPlus.frames.set(key, url);   // הכי חדש בסוף (LRU)
    return url;
  }
  const resp = await fetch(_dvzThumbUrl(dvzState.selected, (pos / 1000).toFixed(3), 0.2, _dvzPreviewParams()));
  if (!resp.ok) return null;
  const url = URL.createObjectURL(await resp.blob());
  dvzPlus.frames.set(key, url);
  while (dvzPlus.frames.size > DVZ_SCRUB_FRAMES) {
    const [oldKey, oldUrl] = dvzPlus.frames.entries().next().value;
    URL.revokeObjectURL(oldUrl);
    dvzPlus.frames.delete(oldKey);
  }
  return url;
}

function _dvzOnScrub() {
  if (dvzState.animate || !dvzState.selected) return;
  const pos = Math.round(parseInt(document.getElementById("dvzPreviewPos").value, 10) / 5) * 5;
  dvzPlus.scrub = pos;
  uiDebounce("dvz:scrub", async () => {
    if (dvzPlus.scrub !== pos) return;
    try {
      const url = await _dvzSmallFrame(pos);
      if (url && dvzPlus.scrub === pos) document.getElementById("dvzPreviewImg").src = url;
    } catch (e) { /* הפריים המלא יגיע בכל מקרה */ }
  }, 40);
}

function _dvzPrefetchNeighbors() {
  if (dvzState.animate || !dvzState.selected) return;
  const here = Math.round(parseInt(document.getElementById("dvzPreviewPos").value, 10) / 5) * 5;
  const queue = [10, -10, 25, -25, 50, -50].map(d => here + d).filter(p => p >= 0 && p <= 1000 && !dvzPlus.frames.has(_dvzScrubKey(p)));
  const next = () => {
    const pos = queue.shift();
    if (pos === undefined || dvzState.running) return;
    _dvzSmallFrame(pos).catch(() => null).then(() => setTimeout(next, 60));
  };
  uiDebounce("dvz:prefetch", next, 500);
}

// ============================================================================
// 18: התצוגה המונפשת כווידאו (MP4, בכרטיס המסך כשאפשר) במקום GIF
// ============================================================================
function _dvzSyncVideo() {
  const img = document.getElementById("dvzPreviewImg");
  let video = document.getElementById("dvzPreviewVideo");
  if (!dvzState.animate) {
    if (video) video.remove();
    img.hidden = false;
    return;
  }
  if (!video) {
    video = _dvzEdEl("video", "dvz-preview-video");
    video.id = "dvzPreviewVideo";
    video.muted = true;
    video.loop = true;
    video.autoplay = true;
    video.playsInline = true;
    img.after(video);
  }
  if (video.src !== img.src) {
    video.src = img.src;
    video.play().catch(() => null);
  }
  img.hidden = true;
}

// ============================================================================
// 19: לפני / אחרי - הפריים השמור מתחת לטיוטה, עם מפריד נגרר
// ============================================================================
async function dvzToggleBeforeAfter() {
  dvzPlus.beforeAfter = !dvzPlus.beforeAfter;
  document.getElementById("dvzBeforeAfterBtn").setAttribute("aria-pressed", String(dvzPlus.beforeAfter));
  await _dvzLoadBeforeAfter();
}

async function _dvzLoadBeforeAfter() {
  const stage = _dvzPlusStage();
  let wrap = document.getElementById("dvzBeforeWrap");
  const btn = document.getElementById("dvzBeforeAfterBtn");
  const hasDraft = !!_dvzDraftParam();
  if (btn) btn.disabled = !hasDraft && !dvzPlus.beforeAfter;
  if (!dvzPlus.beforeAfter || !hasDraft || dvzState.animate || !stage) {
    if (wrap) wrap.remove();
    return;
  }
  if (!wrap) {
    wrap = _dvzEdEl("div", "dvz-before-wrap");
    wrap.id = "dvzBeforeWrap";
    const img = _dvzEdEl("img");
    img.id = "dvzBeforeImg";
    img.alt = "לפני השינויים";
    const handle = _dvzEdEl("input", "dvz-before-handle");
    handle.type = "range";
    handle.min = "0";
    handle.max = "100";
    handle.value = "50";
    handle.setAttribute("aria-label", "לפני / אחרי");
    handle.oninput = () => wrap.style.setProperty("--split", handle.value + "%");
    wrap.append(img, handle, _dvzEdEl("span", "dvz-before-tag", "לפני"), _dvzEdEl("span", "dvz-after-tag", "אחרי"));
    wrap.style.setProperty("--split", "50%");
    stage.append(wrap);
  }
  _dvzFitOverlays();
  const params = _dvzPreviewParams();
  delete params.draft;
  try {
    const resp = await fetch(_dvzThumbUrl(dvzState.selected, _dvzPosition().toFixed(3), 0.5, params));
    if (!resp.ok) return;
    const img = document.getElementById("dvzBeforeImg");
    if (img.dataset.blob) URL.revokeObjectURL(img.dataset.blob);
    img.dataset.blob = URL.createObjectURL(await resp.blob());
    img.src = img.dataset.blob;
  } catch (e) { /* בלי השוואה */ }
}

// ============================================================================
// 7, 10, 16: מצב במאי, טווח לרינדור ובלוקי הסיפור מתחת לסליידר - לפי התאריך של כל מקום בסליידר (/api/dataviz/timeline)
// ============================================================================
async function _dvzLoadTimeline() {
  const key = _dvzDraftKey();
  if (dvzPlus.timeline && dvzPlus.timelineKey === key) return dvzPlus.timeline;
  const params = {episode: dvzState.selected};
  const draft = _dvzDraftParam();
  if (draft) params.draft = draft;
  try {
    const data = await _dvzJsonOk(await fetch("/api/dataviz/timeline?" + new URLSearchParams(params)));
    dvzPlus.timeline = data;
    dvzPlus.timelineKey = key;
  } catch (e) {
    dvzPlus.timeline = null;
  }
  return dvzPlus.timeline;
}

function _dvzDateAt(pos) {
  const points = (dvzPlus.timeline && dvzPlus.timeline.points) || [];
  if (!points.length) return "";
  let best = points[0];
  for (const point of points) if (point[0] <= pos) best = point;
  return best[1];
}

function _dvzPosOf(date) {
  const points = (dvzPlus.timeline && dvzPlus.timeline.points) || [];
  if (!points.length) return null;
  for (let i = 0; i < points.length; i++) {
    if (points[i][1] >= date) return points[i][0];
  }
  return points[points.length - 1][0];
}

function _dvzCurrentDate() {
  return (dvzPlus.meta && dvzPlus.meta.iso_date) || _dvzDateAt(_dvzPosition());
}

// --- 7: התפריט של מצב הבמאי ---
function _dvzDirectorMenu(x, y) {
  document.querySelectorAll(".dvz-director").forEach(el => el.remove());
  const date = _dvzCurrentDate();
  if (!date) { uiToast("אין תאריך ברגע הזה (פתיח או סיום) - הזז את הסליידר לקטע הראשי", "warn"); return; }
  const menu = _dvzEdEl("div", "dvz-director ve-menu");
  menu.setAttribute("role", "menu");
  Object.assign(menu.style, {left: `${x}px`, top: `${y}px`});
  menu.append(_dvzEdEl("div", "hint", "🎬 " + date));
  const item = (label, action) => {
    const btn = _dvzEdEl("button", "", label);
    btn.type = "button";
    btn.setAttribute("role", "menuitem");
    btn.onclick = () => { menu.remove(); action(); };
    menu.append(btn);
  };
  item("📑 פרק כאן", () => _dvzDirectorText("chapters", date, "title", "כותרת הפרק"));
  item("⏸ עצירה כאן", () => _dvzDirectorText("pauses", date, "text", "מה מסבירים בעצירה"));
  item("💬 הערה לישות כאן", () => _dvzDirectorText("callouts", date, "text", "טקסט ההערה"));
  item("⟦ תחילת טווח לרינדור", () => _dvzSetRange("start", date));
  item("⟧ סוף טווח לרינדור", () => _dvzSetRange("end", date));
  document.body.append(menu);
  const close = (e) => { if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener("pointerdown", close, true); } };
  document.addEventListener("pointerdown", close, true);
  menu.querySelector("button").focus();
}

function _dvzDirectorText(key, date, field, label) {
  document.querySelectorAll(".dvz-director-form").forEach(el => el.remove());
  const form = _dvzEdEl("div", "tc-row dvz-director-form");
  const text = _dvzEdEl("input");
  text.type = "text";
  text.maxLength = 160;
  text.setAttribute("aria-label", label);
  text.placeholder = label;
  let entity = null;
  if (key === "callouts") {
    entity = _dvzEdEl("select");
    entity.setAttribute("aria-label", "הישות");
    const names = ((dvzPlus.meta && dvzPlus.meta.hits) || []).filter(h => h.target.startsWith("entity:")).map(h => h.target.slice(7));
    for (const name of new Set(names.length ? names : (dvzEd.data ? dvzEd.data.entities.map(e => e.name) : []))) entity.append(new Option(name, name));
  }
  const add = _dvzEdEl("button", "btn-sm btn-primary", "➕ הוסף");
  add.type = "button";
  add.onclick = async () => {
    await dvzLoadEditor();
    const items = _dvzStoryItems(key).map(i => ({...i}));
    const item = {date, [field]: text.value.trim() || label};
    if (entity) item.entity = entity.value;
    items.push(item);
    _dvzStage("story." + key, items);
    form.remove();
    if (dvzEd.tab === "story" && document.getElementById("dvzEditor").open) _dvzRenderEditor();
    uiToast('נוסף לסיפור - עריכה בלשונית "📖 סיפור"', "ok");
  };
  const cancel = _dvzEdEl("button", "btn-sm", "ביטול");
  cancel.type = "button";
  cancel.onclick = () => form.remove();
  form.append(_dvzEdEl("span", "hint", date), ...(entity ? [entity] : []), text, add, cancel);
  text.addEventListener("keydown", (e) => { if (e.key === "Enter") add.click(); else if (e.key === "Escape") form.remove(); });
  document.querySelector("#dvzPreviewPane .dvz-preview-bar").after(form);
  text.focus();
}

function _dvzOnDirectorKey(e) {
  const panel = document.querySelector('[data-tab-panel="dataviz"]');
  if (!panel || panel.hidden || !dvzState.selected || e.ctrlKey || e.metaKey || e.altKey || _dvzTyping(e.target)) return;
  if (e.code !== "KeyM") return;   // המקש עצמו - גם במקלדת עברית
  e.preventDefault();
  const img = document.getElementById("dvzPreviewImg");
  const rect = img.getBoundingClientRect();
  _dvzLoadTimeline().then(() => _dvzDirectorMenu(rect.left + rect.width * 0.5, rect.top + rect.height * 0.4));
}

// --- 10: טווח לרינדור ---
function _dvzSetRange(edge, date) {
  const range = {...(dvzPlus.range || {})};
  range[edge] = date;
  if (range.start && range.end && range.start > range.end) [range.start, range.end] = [range.end, range.start];
  dvzPlus.range = range;
  _dvzRenderRange();
}

function dvzClearRange() {
  dvzPlus.range = null;
  _dvzRenderRange();
}

function _dvzRenderRange() {
  const chip = document.getElementById("dvzRangeChip");
  const band = document.getElementById("dvzRangeBand");
  const range = dvzPlus.range || {};
  if (chip) {
    chip.hidden = !(range.start || range.end);
    chip.querySelector("span").textContent = `⟦ ${range.start || "…"} - ${range.end || "…"} ⟧`;
  }
  if (band) {
    const a = range.start ? _dvzPosOf(range.start) : null, b = range.end ? _dvzPosOf(range.end) : null;
    band.hidden = a === null && b === null;
    if (!band.hidden) {
      const lo = a ?? 0, hi = b ?? 1;
      Object.assign(band.style, {insetInlineStart: `${lo * 100}%`, width: `${Math.max(0.5, (hi - lo) * 100)}%`});
    }
  }
}

// --- 16: בלוקי הסיפור הנגררים ---
const DVZ_STORY_BLOCKS = [["chapters", "📑", "title"], ["pauses", "⏸", "text"], ["callouts", "💬", "text"]];
const DVZ_STORY_RANGES = [["periods", "label"], ["speed", "speed"]];

async function _dvzRenderStoryTrack() {
  const track = document.getElementById("dvzStoryTrack");
  if (!track || !dvzState.selected) return;
  if (!dvzEd.data || dvzEd.data.episode !== dvzState.selected) { track.replaceChildren(); return; }
  await _dvzLoadTimeline();
  const blocks = [];
  for (const [key, icon, label] of DVZ_STORY_BLOCKS) {
    _dvzStoryItems(key).forEach((item, index) => {
      const pos = _dvzPosOf(item.date);
      if (pos === null) return;
      const block = _dvzEdEl("button", "dvz-story-block is-point", icon);
      block.type = "button";
      block.title = `${item.date} · ${item[label] || ""}`;
      block.setAttribute("aria-label", block.title);
      Object.assign(block.dataset, {key, index: String(index), edge: "date"});
      block.style.insetInlineStart = `${pos * 100}%`;
      blocks.push(block);
    });
  }
  for (const [key, label] of DVZ_STORY_RANGES) {
    _dvzStoryItems(key).forEach((item, index) => {
      const a = _dvzPosOf(item.start), b = _dvzPosOf(item.end);
      if (a === null || b === null) return;
      const bar = _dvzEdEl("div", "dvz-story-block is-range is-" + key, key === "speed" ? `×${item.speed}` : String(item[label] || ""));
      bar.title = `${item.start} - ${item.end}`;
      Object.assign(bar.dataset, {key, index: String(index), edge: "move"});
      Object.assign(bar.style, {insetInlineStart: `${Math.min(a, b) * 100}%`, width: `${Math.max(0.8, Math.abs(b - a) * 100)}%`});
      for (const edge of ["start", "end"]) {
        const grip = _dvzEdEl("span", "dvz-story-grip");
        grip.dataset.edge = edge;
        bar.append(grip);
      }
      blocks.push(bar);
    });
  }
  track.replaceChildren(...blocks);
}

function _dvzInitStoryTrack() {
  const track = document.getElementById("dvzStoryTrack");
  if (!track || track.dataset.ready) return;
  track.dataset.ready = "1";
  let drag = null;
  const rtl = () => getComputedStyle(track).direction === "rtl";
  const posAt = (x) => {
    const rect = track.getBoundingClientRect();
    const f = Math.max(0, Math.min(1, (x - rect.left) / rect.width));
    return rtl() ? 1 - f : f;
  };
  track.addEventListener("pointerdown", (e) => {
    const block = e.target.closest(".dvz-story-block");
    if (!block) return;
    const grip = e.target.closest(".dvz-story-grip");
    drag = {block, key: block.dataset.key, index: Number(block.dataset.index), edge: grip ? grip.dataset.edge : block.dataset.edge,
      from: posAt(e.clientX), moved: false};
    block.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  track.addEventListener("pointermove", (e) => {
    if (!drag) return;
    drag.moved = drag.moved || Math.abs(posAt(e.clientX) - drag.from) > 0.004;
    drag.to = posAt(e.clientX);
    if (drag.moved) drag.block.classList.add("is-dragging");
  });
  track.addEventListener("pointerup", () => {
    if (!drag) return;
    const d = drag;
    drag = null;
    if (!d.moved) {
      document.getElementById("dvzPreviewPos").value = String(Math.round(d.from * 1000));
      dvzLoadPreview();
      return;
    }
    const items = _dvzStoryItems(d.key).map(i => ({...i}));
    const item = items[d.index];
    if (!item) return;
    if (d.edge === "date") item.date = _dvzDateAt(d.to);
    else if (d.edge === "start" || d.edge === "end") item[d.edge] = _dvzDateAt(d.to);
    else {   // הזזה של כל הטווח - שני הקצוות זזים באותו מרחק בסליידר
      const shift = d.to - d.from;
      item.start = _dvzDateAt(Math.max(0, Math.min(1, _dvzPosOf(item.start) + shift)));
      item.end = _dvzDateAt(Math.max(0, Math.min(1, _dvzPosOf(item.end) + shift)));
    }
    if (item.start && item.end && item.start > item.end) [item.start, item.end] = [item.end, item.start];
    _dvzStage("story." + d.key, items);
    if (dvzEd.tab === "story" && document.getElementById("dvzEditor").open) _dvzRenderEditor();
    _dvzRenderStoryTrack();
  });
}

// ============================================================================
// 20: הקלטה רציפה - הסליידר מתקדם בזמן אמת והקול מוקלט; בסוף נשמר כ-narration.track מהשנייה שבה התחיל
// ============================================================================
async function dvzToggleTrackRecording() {
  const btn = document.getElementById("dvzTrackBtn");
  if (dvzPlus.recording) {
    dvzPlus.recording.recorder.stop();
    return;
  }
  if (!navigator.mediaDevices || typeof MediaRecorder !== "function") { uiToast("הדפדפן לא מאפשר הקלטה", "warn"); return; }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio: true});
  } catch (e) {
    uiToast("אין גישה למיקרופון", "warn");
    return;
  }
  const meta = dvzPlus.meta || {};
  const fps = Number(meta.fps) || 30, frames = Number(meta.frames) || 1;
  const startSeconds = (Number(meta.index) || 0) / fps;
  const recorder = new MediaRecorder(stream);
  const chunks = [];
  recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  const slider = document.getElementById("dvzPreviewPos");
  const startedAt = performance.now(), from = parseInt(slider.value, 10);
  const timer = setInterval(() => {
    const seconds = (performance.now() - startedAt) / 1000;
    slider.value = String(Math.min(1000, Math.round(from + seconds * fps / Math.max(frames - 1, 1) * 1000)));
    _dvzOnScrub();
  }, 250);
  recorder.onstop = async () => {
    clearInterval(timer);
    stream.getTracks().forEach(t => t.stop());
    dvzPlus.recording = null;
    btn.setAttribute("aria-pressed", "false");
    btn.textContent = "🎙 הקלטה רציפה";
    const blob = new Blob(chunks, {type: recorder.mimeType || "audio/webm"});
    try {
      await _dvzJsonOk(await fetch("/api/dataviz/narration_track", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({episode: dvzState.selected, ext: (recorder.mimeType || "").includes("ogg") ? "ogg" : "webm",
          data: await _dvzBase64(blob), start: startSeconds})}));
      uiToast("ההקלטה נשמרה - היא תיכנס לסרטון המלא ולבדיקה", "ok");
      await dvzLoadEditor();
    } catch (e) {
      uiToast(e.message, "warn");
    }
    dvzLoadPreview();
  };
  dvzPlus.recording = {recorder};
  recorder.start(1000);
  btn.setAttribute("aria-pressed", "true");
  btn.textContent = "⏹ סיום הקלטה";
}

// ============================================================================
// 6, 9: sparkline ודגלים בלשונית הישויות
// ============================================================================
function _dvzSparkSvg(info) {
  const values = info.values || [];
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "dvz-spark");
  svg.setAttribute("viewBox", "0 0 100 24");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("aria-hidden", "true");
  if (!values.length) return svg;
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const x = (i) => values.length > 1 ? i / (values.length - 1) * 100 : 50;
  const y = (v) => 22 - (v - lo) / span * 20;
  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  line.setAttribute("points", values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" "));
  svg.append(line);
  for (const i of info.jumps || []) {
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    for (const [k, v] of Object.entries({cx: x(i), cy: y(values[i] ?? lo), r: 2.6})) dot.setAttribute(k, String(v));
    svg.append(dot);
  }
  return svg;
}

async function _dvzDecorateEntities(box) {
  const episode = dvzState.selected;
  if (!dvzPlus.spark[episode]) {
    try {
      dvzPlus.spark[episode] = await _dvzJsonOk(await fetch("/api/dataviz/episodes/sparklines?episode=" + encodeURIComponent(episode)));
    } catch (e) {
      dvzPlus.spark[episode] = {entities: {}};
    }
  }
  const spark = dvzPlus.spark[episode].entities || {};
  for (const row of box.querySelectorAll(".dvz-entity-table tbody tr")) {
    const cell = row.cells[0];
    const info = spark[cell.textContent];
    if (!info || cell.querySelector(".dvz-spark")) continue;
    const svg = _dvzSparkSvg(info);
    if ((info.jumps || []).length) {
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = 'נקודה = קפיצה חשודה - בדיקה בחלון הנתונים, לשונית "ניקוי"';
      svg.append(title);
    }
    cell.append(svg);
  }
  await _dvzFlagsBar(box);
}

async function _dvzFlagsBar(box) {
  const episode = dvzState.selected;
  let data = dvzPlus.flags[episode];
  if (!data) {
    try {
      data = dvzPlus.flags[episode] = await _dvzJsonOk(await fetch("/api/dataviz/flags?episode=" + encodeURIComponent(episode)));
    } catch (e) {
      return;
    }
  }
  if (!(data.countries || []).length || !box.isConnected) return;
  const bar = _dvzEdEl("div", "tc-row dvz-flags-bar");
  const on = _dvzEdEl("input");
  on.type = "checkbox";
  on.id = "dvzFlagsOn";
  on.checked = !!_dvzFieldValue("images.flags");
  on.onchange = () => _dvzStage("images.flags", on.checked);
  const label = _dvzEdEl("label", "", "🏳️ דגלים למדינות");
  label.htmlFor = on.id;
  const count = _dvzEdEl("span", "hint");
  count.append("מדינות שזוהו: ", String(data.countries.length), " · חסרים: ", String(data.missing.length));
  bar.append(on, label, count);
  if (data.missing.length) {
    const get = _dvzEdEl("button", "btn-sm", "📥 הורד דגלים");
    get.type = "button";
    get.title = "הדגלים החסרים לפרק הזה בלבד, מ-flagcdn.com - רק עכשיו, בלחיצה";
    get.onclick = async () => {
      get.disabled = true;
      try {
        const result = await _dvzJsonOk(await fetch("/api/dataviz/flags/download", {method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({episode})}));
        dvzPlus.flags[episode] = result;
        uiToast(result.failed.length ? "חלק מהדגלים לא ירדו - נסה שוב" : "הדגלים ירדו", result.failed.length ? "warn" : "ok");
        if (!on.checked) { on.checked = true; _dvzStage("images.flags", true); }
        dvzPreviewSoon();
        bar.remove();
        _dvzFlagsBar(box);
      } catch (e) {
        uiToast(e.message, "warn");
        get.disabled = false;
      }
    };
    bar.append(get);
  }
  box.querySelectorAll(".dvz-flags-bar").forEach(el => el.remove());
  box.prepend(bar);
}

// ============================================================================
// 21-23: מראות עם תמונה, תצוגת גופן, ולפני / אחרי בריחוף על שדה
// ============================================================================
function _dvzLookThumbs(row) {
  const pos = _dvzPosition().toFixed(3);
  for (const btn of row.querySelectorAll("button[data-look]")) {
    const look = ((dvzEd.data && dvzEd.data.looks) || []).find(l => l.id === btn.dataset.look);
    if (!look || btn.querySelector("img")) continue;
    const img = _dvzEdEl("img", "dvz-look-thumb");
    img.alt = "";
    img.loading = "lazy";
    img.src = _dvzThumbUrl(dvzState.selected, pos, 0.2, {draft: JSON.stringify({...dvzEd.draft, ...look.set})});
    img.onerror = () => img.remove();
    btn.prepend(img);
  }
}

function _dvzFontSample(row) {
  const select = row.querySelector("select");
  if (!select || row.querySelector(".dvz-font-sample")) return;
  const sample = _dvzEdEl("span", "dvz-font-sample", "אבג 1,234 · ABC");
  sample.setAttribute("aria-hidden", "true");
  const update = () => { sample.style.fontFamily = select.value ? `"${select.value}", sans-serif` : ""; };
  for (const option of select.options) if (option.value) option.style.fontFamily = `"${option.value}", sans-serif`;
  select.addEventListener("change", update);
  update();
  row.append(sample);
}

function _dvzInitHoverPreview() {
  const body = document.getElementById("dvzEditorBody");
  if (!body || body.dataset.hoverReady) return;
  body.dataset.hoverReady = "1";
  let timer = 0;
  body.addEventListener("mouseover", (e) => {
    const label = e.target.closest(".dvz-field-label");
    if (!label || label.dataset.peek) return;
    clearTimeout(timer);
    timer = setTimeout(() => _dvzPeekField(label), 700);
  });
  body.addEventListener("mouseout", (e) => {
    if (e.target.closest(".dvz-field-label")) clearTimeout(timer);
    const peek = document.querySelector(".dvz-peek");
    if (peek && !peek.contains(e.relatedTarget) && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest(".dvz-field-label"))) peek.remove();
  });
}

function _dvzPeekField(label) {
  const row = label.closest(".dvz-field");
  const path = row && row.dataset.path;
  const field = path && (dvzEd.data.groups || []).flatMap(g => g.fields).find(f => f.path === path);
  if (!field || !["bool", "choice", "int", "number"].includes(field.type) || typeof _dvzAltValue !== "function") return;
  const current = _dvzFieldValue(path);
  const other = field.type === "bool" ? !current : (field.type === "choice" ? (field.choices || []).find(c => c !== current) : _dvzAltValue({...field, default: current}));
  if (other === undefined) return;
  document.querySelectorAll(".dvz-peek").forEach(el => el.remove());
  const peek = _dvzEdEl("div", "dvz-peek");
  peek.setAttribute("role", "tooltip");
  const pos = _dvzPosition().toFixed(3);
  for (const [caption, value] of [["עכשיו", current], ["אחרת", other]]) {
    const figure = _dvzEdEl("figure");
    const img = _dvzEdEl("img");
    img.alt = caption;
    img.src = _dvzThumbUrl(dvzState.selected, pos, 0.2, {draft: JSON.stringify({...dvzEd.draft, [path]: value})});
    img.onerror = () => figure.remove();
    const shown = typeof value === "boolean" ? (value ? "כן" : "לא") : String((field.choice_labels || {})[value] || value);
    figure.append(img, _dvzEdEl("figcaption", "hint", caption + ": " + shown));
    peek.append(figure);
  }
  label.after(peek);
}

// ============================================================================
// 24: ציון פרק - מהרשימה "✅ לפני רינדור"
// ============================================================================
function _dvzScore(parts) {
  const [data, facts, read] = parts.map(n => n || 0);
  return Math.max(0, 100 - 12 * data - 20 * facts - 8 * read);
}

function _dvzShowScore() {
  const parts = [_dvzPre.data, _dvzPre.facts, _dvzPre.read];
  const summary = document.getElementById("dvzPreSummary");
  if (!summary || parts.some(n => n === null)) return;
  const score = _dvzScore(parts);
  dvzPlus.scores[dvzState.selected] = score;
  const chip = _dvzEdEl("span", "dvz-score " + (score >= 85 ? "is-good" : score >= 60 ? "is-ok" : "is-bad"));
  chip.append("🏅 ", String(score), "/100");
  chip.title = "ציון הפרק: 100, פחות 12 לכל אזהרה בנתונים, 20 למספרים שלא מתאימים לקבצים ו-8 לכל בעיית קריאות";
  summary.append(" ", chip);
  const badge = document.getElementById("dvzDataBadge");
  if (badge) badge.dataset.score = String(score);
}

// ============================================================================
// 25: גרסאות עם תמונה
// ============================================================================
function _dvzHistoryThumbs() {
  const pos = _dvzPosition().toFixed(3);
  for (const tr of document.querySelectorAll("#dvzHistList tr[data-version]")) {
    const cell = tr.cells[0];
    if (!cell || cell.querySelector("img")) continue;
    const img = _dvzEdEl("img", "dvz-history-thumb");
    img.alt = "";
    img.loading = "lazy";
    img.src = _dvzThumbUrl(dvzState.selected, pos, 0.2, {version: tr.dataset.version});
    img.onerror = () => img.remove();
    cell.prepend(img);
  }
}

// ============================================================================
// 11: שמירה כתבנית, והתבניות השמורות ברשימת "תבנית" של פרק חדש
// ============================================================================
async function dvzSaveTemplate() {
  if (!dvzState.selected) return;
  document.querySelectorAll(".dvz-template-form").forEach(el => el.remove());
  const ep = dvzState.episodes.find(e => e.name === dvzState.selected) || {};
  const form = _dvzEdEl("div", "tc-row dvz-template-form");
  const name = _dvzEdEl("input");
  name.type = "text";
  name.maxLength = 40;
  name.value = (ep.title || ep.name || "").slice(0, 40).replace(/[^\w\- ֐-׿]/g, "");
  name.setAttribute("aria-label", "שם התבנית");
  const save = _dvzEdEl("button", "btn-sm btn-primary", "💾 שמור תבנית");
  save.type = "button";
  save.onclick = async () => {
    try {
      const data = await _dvzJsonOk(await fetch("/api/dataviz/templates", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({episode: dvzState.selected, title: name.value})}));
      uiToast(`התבנית "${data.title}" נשמרה`, "ok");
      form.remove();
      _dvzFillTemplates();
    } catch (e) {
      uiToast(e.message, "warn");
    }
  };
  const cancel = _dvzEdEl("button", "btn-sm", "ביטול");
  cancel.type = "button";
  cancel.onclick = () => form.remove();
  form.append(_dvzEdEl("span", "hint", "העיצוב, הקצב, התוויות והסדרה - בלי הנתונים והכותרת:"), name, save, cancel);
  document.querySelector("#dvzControls .dvz-pane-head").after(form);
  name.focus();
}

async function _dvzAddSavedTemplates() {
  const select = document.getElementById("dvzNewTemplate");
  if (!select) return;
  let rows = [];
  try {
    rows = (await _dvzJsonOk(await fetch("/api/dataviz/templates"))).templates || [];
  } catch (e) {
    return;
  }
  select.querySelectorAll("optgroup.dvz-saved-templates").forEach(el => el.remove());
  if (!rows.length) return;
  const group = document.createElement("optgroup");
  group.className = "dvz-saved-templates";
  group.label = "📑 תבניות שמורות";
  for (const row of rows) group.append(new Option("📑 " + row.title, row.id));
  select.append(group);
}

// ============================================================================
// 13: מצב כרטיס המסך בזמן רינדור; 14: שימור הצופים מיוטיוב על הסליידר
// ============================================================================
async function _dvzPollGpu() {
  const chip = document.getElementById("dvzGpuChip");
  if (!chip) return;
  if (!dvzState.running) { chip.hidden = true; clearInterval(dvzPlus.gpuTimer); dvzPlus.gpuTimer = 0; return; }
  try {
    const gpu = await _dvzJsonOk(await fetch("/api/dataviz/gpu"));
    chip.hidden = !gpu.available;
    if (gpu.available) {
      chip.textContent = `🎮 GPU ${gpu.gpu ?? "?"}% · NVENC ${gpu.encoder ?? "?"}%`;
      chip.title = `${gpu.name} · ${gpu.memory_used}/${gpu.memory_total}MB · ${gpu.temperature}°C`;
    }
  } catch (e) {
    chip.hidden = true;
  }
}

function _dvzWatchGpu() {
  if (dvzState.running && !dvzPlus.gpuTimer) {
    dvzPlus.gpuTimer = setInterval(_dvzPollGpu, 2000);
    _dvzPollGpu();
  }
  if (!dvzState.running) _dvzPollGpu();
}

async function _dvzLoadRetention(refresh) {
  const episode = dvzState.selected;
  if (!episode) return;
  try {
    const data = refresh
      ? await _dvzJsonOk(await fetch("/api/dataviz/retention", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({episode})}))
      : await _dvzJsonOk(await fetch("/api/dataviz/retention?episode=" + encodeURIComponent(episode)));
    dvzPlus.retention[episode] = data;
    const btn = document.getElementById("dvzRetentionBtn");
    if (btn) btn.hidden = !refresh && !data.uploaded;
    if (refresh) uiToast((data.points || []).length ? "השימור נטען - הקו מעל הסליידר" : "ליוטיוב עוד אין נתוני שימור לסרטון", "ok");
  } catch (e) {
    if (refresh) uiToast(e.message, "warn");
  }
  _dvzRenderRetention();
}

function _dvzRenderRetention() {
  const wrap = document.querySelector("#dvzPreviewPane .dvz-slider-wrap");
  if (!wrap) return;
  let svg = wrap.querySelector(".dvz-retention");
  const points = ((dvzPlus.retention[dvzState.selected] || {}).points) || [];
  if (!points.length) { if (svg) svg.remove(); return; }
  if (!svg) {
    svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "dvz-retention");
    svg.setAttribute("viewBox", "0 0 100 20");
    svg.setAttribute("preserveAspectRatio", "none");
    wrap.prepend(svg);
  }
  const top = Math.max(1, ...points.map(p => p.watch));
  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  line.setAttribute("points", points.map(p => `${(p.at * 100).toFixed(1)},${(19 - p.watch / top * 18).toFixed(1)}`).join(" "));
  const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
  title.textContent = "שימור צופים מיוטיוב - כמה מהצופים עוד צופים בכל נקודה בסרטון";
  svg.replaceChildren(title, line);
}

// ============================================================================
// אתחול: כפתורים ושכבות שנוספים לתצוגה, ועטיפות של מה שכבר קיים
// ============================================================================
function _dvzPlusButton(id, label, title, onclick, pressed) {
  const btn = _dvzEdEl("button", "btn-sm", label);
  btn.type = "button";
  btn.id = id;
  btn.title = title;
  btn.onclick = onclick;
  if (pressed) btn.setAttribute("aria-pressed", "false");
  return btn;
}

function _dvzInitPlus() {
  const adv = document.querySelector("#dvzPreviewPane .dvz-adv");
  if (!adv || document.getElementById("dvzSideBtn")) return;
  adv.append(
    _dvzPlusButton("dvzSideBtn", "📱 גם לאורך", "אותו רגע לאורך (Shorts / TikTok), ליד התצוגה הרגילה", dvzToggleSideBySide, true),
    _dvzPlusButton("dvzSafeBtn", "🛡 אזורים בטוחים", "איפה הכפתורים והכיתוב של Shorts / TikTok מכסים את הסרטון", dvzToggleSafeZones, true),
    _dvzPlusButton("dvzBeforeAfterBtn", "⇆ לפני / אחרי", "הפריים השמור מול הטיוטה, עם מפריד נגרר", dvzToggleBeforeAfter, true),
    _dvzPlusButton("dvzTrackBtn", "🎙 הקלטה רציפה", "מקליטים קריינות לכל הסרטון: הסליידר מתקדם בזמן אמת, וההקלטה נכנסת מהרגע שבו התחילה", dvzToggleTrackRecording, true),
    _dvzPlusButton("dvzRetentionBtn", "📈 שימור צופים", "מיוטיוב, לסרטון שכבר הועלה - כמה מהצופים עוד צופים בכל נקודה (רק בלחיצה)", () => _dvzLoadRetention(true)));
  document.getElementById("dvzBeforeAfterBtn").disabled = true;
  document.getElementById("dvzRetentionBtn").hidden = true;
  // טווח לרינדור ובלוקי הסיפור, מתחת לסליידר
  const wrap = document.querySelector("#dvzPreviewPane .dvz-slider-wrap");
  if (wrap) {
    const band = _dvzEdEl("div", "dvz-range-band");
    band.id = "dvzRangeBand";
    band.hidden = true;
    const track = _dvzEdEl("div", "dvz-story-track");
    track.id = "dvzStoryTrack";
    track.setAttribute("aria-label", "הסיפור על ציר הסרטון - גרירה מזיזה");
    wrap.append(band);
    wrap.after(track);
  }
  const chip = _dvzEdEl("span", "dvz-range-chip");
  chip.id = "dvzRangeChip";
  chip.hidden = true;
  chip.title = "בסרטון מלא או בדיקה - רק הטווח הזה ירונדר (לקובץ _range)";
  const clear = _dvzEdEl("button", "btn-xs btn-ghost", "✕");
  clear.type = "button";
  clear.setAttribute("aria-label", "בטל טווח");
  clear.onclick = dvzClearRange;
  chip.append(_dvzEdEl("span"), clear);
  const runBtn = document.getElementById("dvzRunBtn");
  runBtn.before(chip);
  const gpu = _dvzEdEl("span", "dvz-gpu-chip");
  gpu.id = "dvzGpuChip";
  gpu.hidden = true;
  gpu.setAttribute("aria-live", "polite");
  document.getElementById("dvzStopBtn").after(gpu);
  // שמירה כתבנית - בתפריט ⋯ של הפרק
  const menu = document.getElementById("dvzEpisodeMenu");
  if (menu && !document.getElementById("dvzSaveTemplateBtn")) {
    const item = _dvzEdEl("button", "dvz-adv", "📑 שמור כתבנית");
    item.type = "button";
    item.id = "dvzSaveTemplateBtn";
    item.setAttribute("role", "menuitem");
    item.title = "העיצוב והקצב של הפרק כתבנית לפרקים חדשים";
    item.onclick = () => { menu.hidden = true; dvzSaveTemplate(); };
    menu.append(item);
  }
  _dvzHitLayer();
  _dvzInitHitDrag();
  _dvzInitStoryTrack();
  const slider = document.getElementById("dvzPreviewPos");
  slider.addEventListener("input", _dvzOnScrub);
  const img = document.getElementById("dvzPreviewImg");
  for (const el of [img, slider, _dvzHitLayer()]) {
    el.addEventListener("contextmenu", (e) => {
      if (!dvzState.selected) return;
      e.preventDefault();
      const x = e.clientX, y = e.clientY;
      if (el === slider) {
        const rect = slider.getBoundingClientRect();
        const f = (x - rect.left) / rect.width;
        slider.value = String(Math.round((getComputedStyle(slider).direction === "rtl" ? 1 - f : f) * 1000));
        dvzLoadPreview();
      }
      _dvzLoadTimeline().then(() => _dvzDirectorMenu(x, y));
    });
  }
  document.addEventListener("keydown", _dvzOnDirectorKey);
}

// --- המאזינים: הקבצים הקיימים משדרים אירוע (uiBus), וכאן מוסיפים - בלי לעטוף את הפונקציות שלהם ---
uiBus.on("dvz:preview-loaded", () => {
  _dvzSyncVideo();
  _dvzLoadFrameMeta();
  _dvzLoadSideBySide();
  _dvzLoadBeforeAfter();
  _dvzPrefetchNeighbors();
  _dvzRenderRange();
  uiDebounce("dvz:storytrack", _dvzRenderStoryTrack, 300);
});
uiBus.on("dvz:entities-tab", (box) => _dvzDecorateEntities(box));
uiBus.on("dvz:looks-row", (row) => _dvzLookThumbs(row));
uiBus.on("dvz:font-row", (row) => _dvzFontSample(row));
uiBus.on("dvz:editor-rendered", () => {
  _dvzInitHoverPreview();
  uiDebounce("dvz:storytrack", _dvzRenderStoryTrack, 300);
});
uiBus.on("dvz:pre-summary", _dvzShowScore);
uiBus.on("dvz:history-shown", _dvzHistoryThumbs);
uiBus.on("dvz:templates-filled", _dvzAddSavedTemplates);
uiBus.on("dvz:run-options", (options) => {
  const range = dvzPlus.range || {};
  if (range.start && range.end && (options.mode === "full" || options.mode === "test")) options.range = `${range.start},${range.end}`;
});
uiBus.on("dvz:running", _dvzWatchGpu);
uiBus.on("dvz:selection-changed", () => {
  dvzPlus.range = null;
  dvzPlus.timeline = null;
  _dvzLoadRetention(false);
});
// "📌 הערה" - הלחיצות עוברות לתמונה (אזורי הלחיצה מושבתים כל עוד מצב ההערות פעיל)
uiBus.on("dvz:annotate", (on) => {
  const layer = document.getElementById("dvzHitLayer");
  if (layer) layer.classList.toggle("is-off", !!on);
});

_dvzInitPlus();
