// ============================================================================
// גל 18 - הסטודיו כתוכנה מקצועית: סביבות עבודה, פקד הרצה אחד (השהיה בפס העליון),
// מפרידים נגררים בין העמודות, שינוי מספר בגרירה על התווית, מסלול שכבות בציר-הזמן
// עם תגיות מסלול, וצורת יחס-הרוחב על שבבי היעדים.
// ============================================================================

// --- סביבות עבודה: אילו אזורים פתוחים ---
const VE_WORKSPACES = {
  edit: ["time", "layers"],
  color: ["look", "effects"],
  audio: ["sound"],
};
let _veWorkspaceSnapshot = null;

// גל 28: בסטודיו הלשוניות הן סביבות העבודה - "עריכה" פותחת את הזמן, "צבע" את הצבע, "שמע" את השמע
const VE_WORKSPACE_TABS = {all: VE_DEFAULT_TAB, edit: "time", color: "look", audio: "sound"};

function setVeWorkspace(name) {
  if (_veCurrentLayout() === "tabs") {
    _veActivateTab(VE_WORKSPACE_TABS[name] || VE_DEFAULT_TAB);
    if (name === "color" && _veEl("veScopes").hidden && typeof toggleVeScopes === "function") toggleVeScopes();
    return;
  }
  const areas = _veCategoryEls();
  if (name === "all") {
    const snapshot = _veWorkspaceSnapshot;
    for (const details of areas) details.open = snapshot ? !!snapshot[details.dataset.cat] : true;
    _veWorkspaceSnapshot = null;
  } else {
    if (!_veWorkspaceSnapshot) {
      _veWorkspaceSnapshot = {};
      for (const details of areas) _veWorkspaceSnapshot[details.dataset.cat] = details.open;
    }
    const open = new Set(VE_WORKSPACES[name] || []);
    for (const details of areas) details.open = open.has(details.dataset.cat);
    if (name === "color" && _veEl("veScopes").hidden && typeof toggleVeScopes === "function") toggleVeScopes();
  }
  for (const btn of document.querySelectorAll(".ve-workspaces button")) btn.setAttribute("aria-pressed", String(btn.dataset.workspace === name));
  const main = document.querySelector("#videoEditorOptions .ve-main");
  if (main) main.scrollTop = 0;
}

// --- פקד הרצה אחד: כפתור ההשהיה בפס העליון משקף את זה של הדף ---
function _veSyncStickyPause() {
  const source = document.getElementById("pauseBtn");
  const mirror = document.getElementById("veStickyPauseBtn");
  if (!source || !mirror) return;
  mirror.disabled = source.disabled;
  const paused = typeof _paused !== "undefined" && _paused;  // מצב אמיתי - לא טקסט הכפתור (מתורגם באנגלית)
  const label = paused ? "▶️" : "⏸️";
  if (mirror.textContent !== label) mirror.textContent = label;
  mirror.title = paused ? "המשך את הריצה" : "השהה את הריצה";
  mirror.setAttribute("aria-label", paused ? "המשך" : "השהה");
}

// --- מצב "יש תיקייה" (מצב ריק בנגן) ---
const _updateRunEnabledBeforeStudio = updateRunEnabled;
updateRunEnabled = function (...args) {
  const result = _updateRunEnabledBeforeStudio(...args);
  const editor = document.getElementById("videoEditorOptions");
  if (editor) editor.classList.toggle("ve-has-folder", !!state.folder);
  return result;
};

// --- מפרידים נגררים בין עמודות הסטודיו ---
const VE_PANEL_LIMITS = {side: [200, 520], main: [320, 820]};

function _veShellRtl() { return getComputedStyle(document.querySelector(".ve-shell")).direction === "rtl"; }

function _vePlaceResizers() {
  const shell = document.querySelector("#videoEditorOptions .ve-shell");
  if (!shell) return;
  const shellRect = shell.getBoundingClientRect();
  const side = shell.querySelector(".ve-side");
  const main = shell.querySelector(".ve-main");
  const rtl = _veShellRtl();
  for (const resizer of shell.querySelectorAll(".ve-resizer")) {
    const panel = resizer.dataset.panel === "side" ? side : main;
    const rect = panel.getBoundingClientRect();
    // הגבול הפנימי של הפאנל (הצד שפונה לנגן)
    const innerEdge = resizer.dataset.panel === "side" ? (rtl ? rect.left : rect.right) : (rtl ? rect.right : rect.left);
    const gapHalf = resizer.dataset.panel === "side" ? (rtl ? -6 : 6) : (rtl ? 6 : -6);
    resizer.style.left = (innerEdge - shellRect.left + gapHalf - 6) + "px";
  }
}

// 23.10.2026: הגרירה, המקלדת והשמירה - uiSplitter המשותף (35-ui-frame.js, נטען לפי דרישה), באותם מפתחות (veSideW,
// veMainW). כאן רק המיקום של המפרידים (הם צפים מעל הרווח בין העמודות); הם נוספים אחרי שה-bundle נטען
async function _veSetupResizers() {
  const shell = document.querySelector("#videoEditorOptions .ve-shell");
  if (!shell || shell.dataset.resizers) return;
  shell.dataset.resizers = "1";
  try {
    await uiLoadLazy("frame");
  } catch (e) {
    delete shell.dataset.resizers;   // בפתיחה הבאה של הסטודיו
    return;
  }
  for (const panel of ["side", "main"]) {
    const resizer = document.createElement("div");
    resizer.className = "ve-resizer";
    resizer.dataset.panel = panel;
    shell.appendChild(resizer);
    const [min, max] = VE_PANEL_LIMITS[panel];
    // side: הקצה החיצוני קבוע (ימין ב-RTL = start), main: הקצה החיצוני קבוע (שמאל ב-RTL = end)
    uiSplitter(resizer, {
      panel: shell.querySelector(panel === "side" ? ".ve-side" : ".ve-main"), target: document.getElementById("videoEditorOptions"),
      cssVar: panel === "side" ? "--ve-side-w" : "--ve-main-w", key: panel === "side" ? "veSideW" : "veMainW", min, max,
      edge: panel === "side" ? "start" : "end", label: panel === "side" ? "רוחב עמודת הקבצים" : "רוחב עמודת ההגדרות",
      onChange: (_width, done) => {
        _vePlaceResizers();
        if (done && typeof _veScheduleLiveRebuild === "function") _veScheduleLiveRebuild();
      },
    });
  }
  new ResizeObserver(() => _vePlaceResizers()).observe(shell);
  window.addEventListener("resize", _vePlaceResizers);
  requestAnimationFrame(_vePlaceResizers);
}

// --- שינוי מספר בגרירה על התווית (כמו בתוכנות עריכה): ימינה = יותר, Shift ×10, Alt ×0.1 ---
function _veScrubControlFor(label) {
  const row = label.closest(".ve-row");
  if (!row) return null;
  const next = label.nextElementSibling;
  if (next && next.matches("input[type=range], input[type=number], input.ve-time")) return next;
  if (label !== row.firstElementChild) return null;
  return row.querySelector("input[type=range]") || row.querySelector("input[type=number]") || row.querySelector("input.ve-time");
}

// גל 28: שדה זמן נגרר בעשיריות שנייה, ונשאר בפורמט שבו הוקלד (שניות או mm:ss)
const _veScrubRead = (control) => control.classList.contains("ve-time") ? (_veParseTime(control.value) || 0) : (parseFloat(control.value) || 0);

function _veScrubWrite(control, value, decimals, asClock) {
  if (control.classList.contains("ve-time")) return asClock || value >= 60 ? _veFormatTime(value) : String(Math.round(value * 10) / 10);
  return decimals ? value.toFixed(decimals) : String(Math.round(value));
}

function _veSetupScrubLabels(root) {
  for (const label of (root || document).querySelectorAll("#veCategories .ve-row > label")) {
    if (label.classList.contains("ve-scrub") || label.querySelector("input, select")) continue;
    const control = _veScrubControlFor(label);
    if (!control) continue;
    label.classList.add("ve-scrub");
    label.title = (label.title ? label.title + "\n" : "") + "↔ גרירה על התווית משנה את הערך (Shift = מהר, Alt = עדין)";
    label.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || control.disabled) return;
      const startX = e.clientX;
      const startValue = _veScrubRead(control);
      const isTime = control.classList.contains("ve-time");
      const asClock = isTime && control.value.includes(":");
      const step = isTime ? 0.1 : (parseFloat(control.step) || 1);
      const min = isTime ? 0 : control.min !== "" ? parseFloat(control.min) : -Infinity;
      const max = control.max !== "" ? parseFloat(control.max) : Infinity;
      const decimals = (String(control.step).split(".")[1] || "").length;
      let dragging = false;
      const move = (ev) => {
        const dx = ev.clientX - startX;
        if (!dragging && Math.abs(dx) < 4) return;
        if (!dragging) { dragging = true; label.setPointerCapture(e.pointerId); label.classList.add("scrubbing"); }
        const factor = ev.shiftKey ? 10 : (ev.altKey ? 0.1 : 1);
        let value = startValue + Math.round(dx / 4) * step * factor;
        value = Math.max(min, Math.min(max, value));
        const text = _veScrubWrite(control, value, decimals, asClock);
        if (control.value !== text) {
          control.value = text;
          control.dispatchEvent(new Event("input", {bubbles: true}));
        }
      };
      const up = () => {
        label.removeEventListener("pointermove", move);
        if (dragging) {
          label.classList.remove("scrubbing");
          control.dispatchEvent(new Event("change", {bubbles: true}));
        }
      };
      label.addEventListener("pointermove", move);
      label.addEventListener("pointerup", up, {once: true});
      label.addEventListener("pointercancel", up, {once: true});
    });
  }
}

// --- ציר-זמן: מסלול שכבות + תגיות מסלול ---
function _veTrackTag(text) {
  const row = document.createElement("div");
  row.className = "ve-track-tag-row";
  const tag = document.createElement("span");
  tag.className = "ve-track-tag";
  tag.textContent = text;
  row.appendChild(tag);
  return row;
}

function _veSetupTimelineTracks() {
  const scroll = _veEl("veTimelineScroll");
  if (!scroll || _veEl("veTlLayersTrack")) return;
  const timeline = _veEl("veTimeline");
  const waveform = _veEl("veWaveformCanvas");
  const layersTrack = document.createElement("div");
  layersTrack.id = "veTlLayersTrack";
  layersTrack.className = "ve-tl-layers";
  layersTrack.setAttribute("aria-label", "מסלול השכבות");
  // גל 29: מסלול נפרד ל-B-roll (קליפים בתוך הפלט), מעל מסלול השכבות
  const brollTrack = document.createElement("div");
  brollTrack.id = "veTlBrollTrack";
  brollTrack.className = "ve-tl-layers ve-tl-broll";
  brollTrack.setAttribute("aria-label", "מסלול ה-B-roll");
  timeline.before(_veTrackTag("🎞️ וידאו"));
  timeline.after(brollTrack);
  brollTrack.before(_veTrackTag("🎬 B-roll"));
  brollTrack.after(layersTrack);
  layersTrack.before(_veTrackTag("🧩 שכבות"));
  waveform.before(_veTrackTag("🔊 שמע"));
}

function _veRenderLayersTrack() {
  // גל 29: בזמן גרירת פס לא מציירים מחדש (הפס הנגרר היה מוחלף והגרירה נופלת) - מציירים בסופה
  if (_veBarDrag) { _veBarDrag.renderPending = true; return; }
  const track = _veEl("veTlLayersTrack");
  const brollTrack = _veEl("veTlBrollTrack");
  if (!track) return;
  track.replaceChildren();
  if (brollTrack) brollTrack.replaceChildren();
  if (!_veTimeline || !_veTimeline.duration) { track.style.height = "22px"; if (brollTrack) brollTrack.style.height = "22px"; return; }
  const file = _veEl("vePreviewFile").value;
  let opts;
  try { opts = _veLiveOptions(file); } catch (e) { return; }
  const timeline = _veLiveTimeline(opts, _veTimeline.duration);
  const all = _veLayersValue();
  const items = [];
  all.forEach((layer, index) => {
    if (layer.clip && layer.clip !== file) return;
    const outStart = Math.max(0, Number(layer.start) || 0);
    if (outStart >= timeline.outDuration) return;
    const outEnd = layer.end === null || layer.end === undefined || layer.end === "" ? timeline.outDuration : Math.min(timeline.outDuration, Number(layer.end));
    if (!(outEnd > outStart)) return;
    items.push({layer, index, from: _veLiveOutToSource(timeline, outStart), to: _veLiveOutToSource(timeline, outEnd)});
  });
  items.sort((a, b) => a.from - b.from);
  const d = _veTimeline.duration;
  // גל 29: B-roll במסלול משלו; כל מסלול מחלק את הפסים לשורות כשהם חופפים
  for (const [target, group] of [[track, items.filter(i => i.layer.type !== "video" || !brollTrack)], [brollTrack, items.filter(i => i.layer.type === "video" && brollTrack)]]) {
    if (!target) continue;
    const lanes = [];
    for (const item of group) {
      let lane = lanes.findIndex(end => end <= item.from);
      if (lane < 0) { lane = lanes.length; lanes.push(0); }
      lanes[lane] = item.to;
      item.lane = lane;
    }
    target.style.height = Math.max(22, lanes.length * 21 + 2) + "px";
    for (const item of group) target.appendChild(_veTimelineBar(item, d));
  }
  if (typeof _veSyncSelection === "function") _veSyncSelection();
}

function _veTimelineBar(item, d) {
  const bar = document.createElement("div");
  bar.className = "ve-tl-layer" + (item.layer.hidden ? " ve-tl-hidden" : "") + (item.layer.locked ? " ve-tl-locked" : "");
  bar.dataset.type = item.layer.type || "text";
  bar.dataset.index = String(item.index);
  bar.style.setProperty("--from", (item.from / d * 100) + "%");
  bar.style.setProperty("--width", Math.max(0.4, (item.to - item.from) / d * 100) + "%");
  bar.style.setProperty("--lane-top", (2 + item.lane * 21) + "px");
  const label = ["image", "video"].includes(item.layer.type) ? String(item.layer.path || "").split(/[\\/]/).pop() : String(item.layer.text || item.layer.type || "");
  bar.textContent = `${VE_LAYER_KIND_ICONS[item.layer.type] || ""} ${item.layer.name || label}`.trim();
  bar.title = `${item.layer.name || label || item.layer.type} · ${_veFormatTime(Number(item.layer.start) || 0)}–${item.layer.end == null || item.layer.end === "" ? "סוף" : _veFormatTime(Number(item.layer.end))} (זמן פלט)`
    + (item.layer.locked ? " · 🔒 נעול" : " · גרירה = הזזה, קצוות = התחלה/סוף (Alt = בלי הצמדה)");
  for (const edge of ["start", "end"]) {
    const grip = document.createElement("span");
    grip.className = "ve-tl-edge";
    grip.dataset.edge = edge;
    bar.appendChild(grip);
  }
  return bar;
}

const _veRenderTimelineExtrasBeforeStudio = _veRenderTimelineExtras;
_veRenderTimelineExtras = function (...args) {
  const result = _veRenderTimelineExtrasBeforeStudio(...args);
  _veRenderLayersTrack();
  return result;
};

const _setVeTimelineZoomBeforeStudio = setVeTimelineZoom;
setVeTimelineZoom = function (zoom) {
  const result = _setVeTimelineZoomBeforeStudio(zoom);
  const scroll = _veEl("veTimelineScroll");
  if (scroll) scroll.style.setProperty("--tl-zoom", String(_veTimelineZoom));
  return result;
};

// --- יעדים: צורת יחס הרוחב על כל שבב ---
const _veRenderTargetChipsBeforeStudio = _veRenderTargetChips;
_veRenderTargetChips = async function (...args) {
  const result = await _veRenderTargetChipsBeforeStudio(...args);
  const schema = _veSchema || {};
  for (const button of document.querySelectorAll("#veTargetChips button[data-target], #veStepTargets button[data-target]")) {
    const fields = ((schema.targets || {})[button.dataset.target] || {}).fields || {};
    const [w, h] = fields.aspect === "1:1" ? [1, 1] : (fields.vertical ? [0.62, 1.1] : [1.4, 0.8]);
    button.dataset.ar = fields.aspect === "1:1" ? "1:1" : (fields.vertical ? "9:16" : "16:9");
    button.style.setProperty("--ar-w", String(w));
    button.style.setProperty("--ar-h", String(h));
  }
  return result;
};

function _uiInitStudio() {
  _veSetupResizers();
  _veSetupScrubLabels();
  _veSetupTimelineTracks();
  _veRenderLayersTrack();
  document.getElementById("veLayers").addEventListener("change", _veRenderLayersTrack);
  const pause = document.getElementById("pauseBtn");
  new MutationObserver(_veSyncStickyPause).observe(pause, {attributes: true, attributeFilter: ["disabled"], childList: true, subtree: true, characterData: true});
  _veSyncStickyPause();
  updateRunEnabled();
}
