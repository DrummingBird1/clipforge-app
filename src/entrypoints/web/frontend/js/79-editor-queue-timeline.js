// ============================================================================
// גל 35: תור וציר-זמן - תצוגת רשת, מיון וקיבוץ, תגיות צבע (גם כפעולה קבוצתית), קובץ
// שכבר רונדר מוביל לתוצר, הקובץ הקודם/הבא בתור ליד הנגן, סימנים עם שם על ציר-הזמן,
// עריכת קליפ מסומנת גם על ציר-הזמן, מיני-מפה בזום, זמן שאפשר להקליד, ושמות ונעילה
// למסלולים.
// ============================================================================

// --- תגיות צבע (לכל תיקייה, בדפדפן) ---
const VE_QUEUE_TAGS = {red: ["🔴", "אדום"], orange: ["🟠", "כתום"], yellow: ["🟡", "צהוב"], green: ["🟢", "ירוק"], blue: ["🔵", "כחול"], purple: ["🟣", "סגול"]};

function _veQueueTags() {
  return _veLoadPref("veQueueTags", {})[state.folder] || {};
}

function setVeQueueTag(color) {
  const picked = _veQueueState.filter(f => f._picked);
  if (!picked.length || !state.folder) return;
  const all = _veLoadPref("veQueueTags", {});
  const tags = {...(all[state.folder] || {})};
  for (const item of picked) { if (color) tags[item.name] = color; else delete tags[item.name]; }
  delete all[state.folder];
  all[state.folder] = tags;
  const folders = Object.keys(all);
  for (const folder of folders.slice(0, Math.max(0, folders.length - 30))) delete all[folder];
  _veSavePref("veQueueTags", all);
  _renderVeQueue();
}

// --- קיבוץ ומיון ---
const VE_QUEUE_STATUS_GROUPS = {created: "✅ נוצר", skipped: "⏭️ דולג", error: "❌ נכשל"};

function _veQueueGroupKey(item, group) {
  if (group === "day") {
    const info = _veQueueMeta[state.folder + "|" + item.name];
    return info && info.mtime ? new Date(info.mtime * 1000).toLocaleDateString("he-IL") : "⏳";
  }
  if (group === "tag") {
    const tag = _veQueueTags()[item.name];
    return tag ? VE_QUEUE_TAGS[tag].join(" ") : "בלי תגית";
  }
  if (group === "status") return VE_QUEUE_STATUS_GROUPS[(_veQueueLastRun[item.name] || {}).status] || "🆕 עוד לא עובד";
  if (group === "folder") return "📂 התיקייה הראשית";   // גל 47: תתי-התיקיות מוצגות מתחת לתור
  return "";
}

// --- גל 47: קיבוץ לפי תיקייה - תתי-התיקיות (שהסקריפט מעבד במלואן) כקבוצות מתחת לתור ---
const _veSubfolderCache = {};

async function _veSubfolderGroups(folder) {
  if (_veSubfolderCache[folder]) return _veSubfolderCache[folder];
  const listing = await (await fetch("/api/browse?path=" + encodeURIComponent(folder))).json();
  const groups = [];
  for (const name of (listing.folders || []).slice(0, 30)) {
    const sub = await (await fetch("/api/browse?path=" + encodeURIComponent(listing.path + "/" + name))).json();
    const videos = (sub.files || []).filter(f => VE_VIDEO_EXTENSIONS.some(ext => f.name.toLowerCase().endsWith(ext)));
    if (videos.length) groups.push({name, videos: videos.map(v => v.name), more: (sub.folders || []).length});
  }
  _veSubfolderCache[folder] = groups;
  return groups;
}

async function _veRenderSubfolderGroups() {
  const container = _veEl("veQueueList");
  if (!container) return;
  let box = document.getElementById("veQueueSubfolders");
  const active = _veLoadPref("veQueueGroup", "") === "folder" && state.folder;
  if (!active) { if (box) box.remove(); return; }
  if (!box) {
    box = document.createElement("div");
    box.id = "veQueueSubfolders";
    box.className = "ve-queue-subfolders";
    container.after(box);
  }
  const include = document.getElementById("veIncludeSubfolders");
  if (include && !include.checked) {
    box.replaceChildren(Object.assign(document.createElement("p"), {className: "hint", textContent: "📁 תתי-התיקיות לא ירונדרו - \"כולל תתי-תיקיות\" כבוי."}));
    return;
  }
  let groups = [];
  try { groups = await _veSubfolderGroups(state.folder); } catch (e) { groups = []; }
  if (!groups.length) { box.replaceChildren(); return; }
  box.replaceChildren(...groups.map(group => {
    const details = document.createElement("details");
    details.className = "ve-queue-subfolder";
    const summary = document.createElement("summary");
    summary.textContent = `📁 ${group.name} · ${group.videos.length} סרטונים` + (group.more ? ` · עוד ${group.more} תיקיות בפנים` : "");
    const list = document.createElement("ul");
    for (const name of group.videos.slice(0, 50)) list.append(Object.assign(document.createElement("li"), {textContent: name}));
    const note = Object.assign(document.createElement("p"), {className: "hint", textContent: "תיקייה משנה מעובדת במלואה בכל ריצה - כדי לבחור ממנה קבצים, פתח אותה כתיקייה."});
    details.append(summary, note, list);
    return details;
  }));
}

function _veQueueSortValue(item, key) {
  const info = _veQueueMeta[state.folder + "|" + item.name] || {};
  if (key === "date") return -(info.mtime || 0);
  if (key === "duration") return -(info.duration || 0);
  if (key === "size") return -(info.size || item.size || 0);
  if (key === "tag") { const tag = _veQueueTags()[item.name]; return tag ? Object.keys(VE_QUEUE_TAGS).indexOf(tag) : 99; }
  if (key === "status") { const status = (_veQueueLastRun[item.name] || {}).status; return status ? Object.keys(VE_QUEUE_STATUS_GROUPS).indexOf(status) : 9; }
  return 0;
}

function sortVeQueue(key) {
  if (!key || !_veQueueState.length) return;
  if (key === "name") _veQueueState.sort((a, b) => a.name.localeCompare(b.name, "he", {numeric: true}));
  else _veQueueState.sort((a, b) => _veQueueSortValue(a, key) - _veQueueSortValue(b, key));
  _veQueueDirty = true;
  _veQueueLastPickIndex = null;
  _renderVeQueue();
  updateVeEtaDisplay();
  const select = _veEl("veQueueSort");
  if (select) select.value = "";
}

function setVeQueueGroup(group) {
  _veSavePref("veQueueGroup", group || "");
  if (group && group !== "folder") sortVeQueue(group === "day" ? "date" : group);
  else _renderVeQueue();
}

function toggleVeQueueGrid() {
  _veSavePref("veQueueView", _veLoadPref("veQueueView", "list") === "grid" ? "list" : "grid");
  _veDecorateQueueRows();
}

// --- קישוטים אחרי כל ציור של התור ---
function _veDecorateQueueRows() {
  const container = _veEl("veQueueList");
  if (!container) return;
  const grid = _veLoadPref("veQueueView", "list") === "grid";
  container.classList.toggle("ve-queue-grid", grid);
  _veEl("veQueueGridBtn").setAttribute("aria-pressed", String(grid));
  const group = _veLoadPref("veQueueGroup", "");
  _veEl("veQueueGroup").value = group;
  const tags = _veQueueTags();
  let previous = null;
  for (const row of container.querySelectorAll(".ve-queue-row")) {
    const name = row.dataset.name;
    const color = tags[name];
    let dot = row.querySelector(":scope > .ve-queue-tag");
    if (color && !dot) {
      dot = document.createElement("span");
      dot.className = "ve-queue-tag";
      row.querySelector(".ve-queue-main").before(dot);
    }
    if (dot && !color) dot.remove();
    else if (dot) { dot.textContent = VE_QUEUE_TAGS[color][0]; dot.title = "תגית: " + VE_QUEUE_TAGS[color][1]; dot.dataset.tag = color; }
    const label = group ? _veQueueGroupKey(_veQueueState.find(f => f.name === name) || {name}, group) : "";
    if (label && label !== previous) row.dataset.groupLabel = label; else delete row.dataset.groupLabel;
    previous = label;
    _veLinkRenderedBadge(row, name);
  }
  _veRenderSubfolderGroups();
}

// קובץ שכבר רונדר: ✅ בשורה מוביל לתוצר (כרטיס התוצאה מתנגן)
function _veLinkRenderedBadge(row, name) {
  const badge = row.querySelector(".ve-badge-status");
  const last = _veQueueLastRun[name];
  if (!badge || badge.dataset.link || !last || !last.output || last.status !== "created") return;
  badge.dataset.link = "1";
  badge.setAttribute("role", "button");
  badge.tabIndex = 0;
  badge.title = badge.title + " · " + "לחץ כדי לראות את התוצר";
  const open = (e) => { e.stopPropagation(); showVeQueueOutput(name); };
  badge.addEventListener("click", open);
  badge.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(e); } });
}

async function showVeQueueOutput(name) {
  await openVeLatestResults();
  const card = [...document.querySelectorAll("#veResultsList .ve-result-card")].find(c => c.dataset.source === name);
  if (!card) return;
  card.scrollIntoView({block: "nearest"});
  card.classList.remove("ve-flash-highlight"); void card.offsetWidth; card.classList.add("ve-flash-highlight");
  const media = card.querySelector(".ve-result-playable");
  if (media) media.click();
}

// --- הקובץ הקודם / הבא בתור ---
function stepVePreviewFile(delta) {
  const select = _veEl("vePreviewFile");
  if (!select.options.length) return;
  const next = Math.max(0, Math.min(select.options.length - 1, select.selectedIndex + delta));
  if (next === select.selectedIndex) return;
  select.selectedIndex = next;
  select.dispatchEvent(new Event("change", {bubbles: true}));
}

function _veSyncPreviewStepButtons() {
  const select = _veEl("vePreviewFile");
  _veEl("vePrevFileBtn").disabled = select.selectedIndex <= 0;
  _veEl("veNextFileBtn").disabled = select.selectedIndex < 0 || select.selectedIndex >= select.options.length - 1;
}

// --- סימנים עם שם על ציר-הזמן (לכל קובץ בתיקייה) ---
function _veMarkersKey() {
  return `${state.folder}|${_veEl("vePreviewFile").value}`;
}

function _veMarkers() {
  return _veLoadPref("veMarkers", {})[_veMarkersKey()] || [];
}

function _veSaveMarkers(list) {
  const all = _veLoadPref("veMarkers", {});
  if (list.length) all[_veMarkersKey()] = list; else delete all[_veMarkersKey()];
  _veSavePref("veMarkers", all);
  _veRenderTimelineOverlays();
}

async function addVeMarker() {
  if (!_veTimeline) return;
  const t = _veTimelineCursor ?? (typeof _veCurrentSourceTime === "function" ? _veCurrentSourceTime() : 0);
  const markers = _veMarkers();
  const name = ((await vePrompt(`שם לסימן ב-${_veFormatTime(t)}:`, {value: `סימן ${markers.length + 1}`})) || "").trim();
  if (!name) return;
  markers.push({t: Math.round(t * 100) / 100, name});
  markers.sort((a, b) => a.t - b.t);
  _veSaveMarkers(markers);
}

async function removeVeMarker(index) {
  const markers = _veMarkers();
  if (!markers[index] || !(await veConfirm(`למחוק את הסימן "${markers[index].name}"?`, {danger: true, okLabel: "🗑️ מחק"}))) return;
  markers.splice(index, 1);
  _veSaveMarkers(markers);
}

function _veRenderMarkers() {
  const layer = _veEl("veTimelineOverlays");
  if (!layer || !_veTimeline) return;
  const d = _veTimeline.duration;
  _veMarkers().forEach((marker, index) => {
    const flag = document.createElement("span");
    flag.className = "ve-tl-marker";
    flag.textContent = "📍";
    flag.dataset.name = marker.name;
    flag.style.left = `${Math.max(0, Math.min(100, marker.t / d * 100))}%`;
    flag.title = `${marker.name} · ${_veFormatTime(marker.t)} - לחיצה קופצת, לחיצה כפולה מוחקת`;
    flag.addEventListener("click", (e) => { e.stopPropagation(); _veMoveTimelineCursor(marker.t); });
    flag.addEventListener("dblclick", (e) => { e.stopPropagation(); removeVeMarker(index); });
    layer.appendChild(flag);
  });
}

// --- עריכת קליפ מסומנת גם על ציר-הזמן ---
function _veSyncTimelineClipMark() {
  const dock = _veEl("veTimelineDock");
  if (!dock) return;
  const clip = _veTimeScope === "clip" && _veClipScopeFile;
  dock.classList.toggle("ve-timeline-clip", !!clip);
  if (clip) dock.dataset.clipLabel = `✏️ עריכת קליפ: ${_veClipScopeFile}`; else delete dock.dataset.clipLabel;
}

// --- מיני-מפה של כל הקובץ (רק בזום) ---
function _veEnsureMinimap() {
  let map = _veEl("veTlMinimap");
  const scroll = _veEl("veTimelineScroll");
  if (map || !scroll) return map;
  map = document.createElement("div");
  map.id = "veTlMinimap";
  map.className = "ve-tl-minimap";
  map.setAttribute("aria-label", "מיני-מפה של כל הקובץ - לחיצה או גרירה מזיזה את התצוגה");
  map.innerHTML = '<div class="ve-tl-minimap-keep"></div><div class="ve-tl-minimap-view"></div>';
  scroll.before(map);
  const jump = (e) => {
    const rect = map.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    scroll.scrollLeft = ratio * scroll.scrollWidth - scroll.clientWidth / 2;
  };
  map.addEventListener("pointerdown", (e) => {
    jump(e);
    map.setPointerCapture(e.pointerId);
    const move = (ev) => jump(ev);
    map.addEventListener("pointermove", move);
    map.addEventListener("pointerup", () => map.removeEventListener("pointermove", move), {once: true});
  });
  scroll.addEventListener("scroll", _veRenderMinimap, {passive: true});
  return map;
}

function _veRenderMinimap() {
  const map = _veEnsureMinimap();
  if (!map) return;
  const scroll = _veEl("veTimelineScroll");
  map.hidden = !_veTimeline || _veTimelineZoom <= 1;
  if (map.hidden) return;
  const d = _veTimeline.duration;
  const {start, end} = _veTrimBounds();
  const keep = map.querySelector(".ve-tl-minimap-keep");
  keep.style.left = `${start / d * 100}%`;
  keep.style.width = `${Math.max(0, end - start) / d * 100}%`;
  const view = map.querySelector(".ve-tl-minimap-view");
  view.style.left = `${scroll.scrollLeft / scroll.scrollWidth * 100}%`;
  view.style.width = `${scroll.clientWidth / scroll.scrollWidth * 100}%`;
  for (const old of map.querySelectorAll(".ve-tl-minimap-marker")) old.remove();
  for (const marker of _veMarkers()) {
    const tick = document.createElement("span");
    tick.className = "ve-tl-minimap-marker";
    tick.style.left = `${marker.t / d * 100}%`;
    map.appendChild(tick);
  }
}

// --- זמן שאפשר להקליד ---
function onVeTimecodeKey(e) {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const input = e.target;
  const t = _veParseTime(input.value);
  if (!_veTimeline || !Number.isFinite(t)) { input.classList.add("ve-invalid"); return; }
  input.classList.remove("ve-invalid");
  _veMoveTimelineCursor(Math.min(t, _veTimeline.duration));
  input.value = "";
}

// --- שמות למסלולים, ונעילה של מסלול שלם ---
const VE_TRACK_KINDS = {veTimeline: "video", veTlBrollTrack: "broll", veTlLayersTrack: "layers", veWaveformCanvas: "audio"};

function _veTrackLayers(kind, layers) {
  return layers.filter(layer => (kind === "broll") === (layer.type === "video"));
}

function toggleVeTrackLock(kind) {
  const layers = _veLayersValue();
  const inTrack = _veTrackLayers(kind, layers);
  if (!inTrack.length) { uiToast("אין שכבות במסלול הזה", "warn"); return; }
  const lock = !inTrack.every(layer => layer.locked);
  for (const layer of inTrack) layer.locked = lock;
  _veWriteLayers(layers);
  _veRenderLayersEditor(true);
  uiToast(lock ? `🔒 ${inTrack.length} שכבות ננעלו` : `🔓 ${inTrack.length} שכבות שוחררו`, "ok");
}

async function renameVeTrack(kind, tag) {
  const names = _veLoadPref("veTrackNames", {});
  const icon = tag.dataset.icon || "";
  const name = ((await vePrompt("שם למסלול:", {value: names[kind] || tag.dataset.defaultName})) || "").trim();
  if (!name) return;
  if (name === tag.dataset.defaultName) delete names[kind]; else names[kind] = name;
  _veSavePref("veTrackNames", names);
  tag.querySelector(".ve-track-name").textContent = `${icon} ${name}`.trim();
}

function _veDecorateTracks() {
  const names = _veLoadPref("veTrackNames", {});
  const layers = _veLayersValue();
  for (const row of document.querySelectorAll(".ve-track-tag-row")) {
    const kind = VE_TRACK_KINDS[(row.nextElementSibling || {}).id];
    const tag = row.querySelector(".ve-track-tag");
    if (!kind || !tag) continue;
    if (!row.dataset.track) {
      row.dataset.track = kind;
      const [icon, ...rest] = tag.textContent.trim().split(" ");
      tag.dataset.icon = icon;
      tag.dataset.defaultName = rest.join(" ");
      const label = document.createElement("span");
      label.className = "ve-track-name";
      label.textContent = tag.textContent.trim();
      label.title = "לחיצה כפולה לשינוי שם המסלול";
      label.addEventListener("dblclick", () => renameVeTrack(kind, tag));
      tag.replaceChildren(label);
      if (kind === "broll" || kind === "layers") {
        const lock = document.createElement("button");
        lock.type = "button";
        lock.className = "ve-track-lock";
        lock.onclick = () => toggleVeTrackLock(kind);
        tag.appendChild(lock);
      }
    }
    if (names[kind]) tag.querySelector(".ve-track-name").textContent = `${tag.dataset.icon} ${names[kind]}`;
    const lock = row.querySelector(".ve-track-lock");
    if (lock) {
      const inTrack = _veTrackLayers(kind, layers);
      const locked = inTrack.length > 0 && inTrack.every(layer => layer.locked);
      lock.textContent = locked ? "🔒" : "🔓";
      lock.setAttribute("aria-pressed", String(locked));
      lock.title = locked ? "שחרר את כל השכבות במסלול" : "נעל את כל השכבות במסלול";
      lock.setAttribute("aria-label", lock.title);
    }
  }
}

function _veOnTimelineRendered() {
  _veRenderMarkers();
  _veRenderMinimap();
  _veSyncTimelineClipMark();
  _veDecorateTracks();
}

function _veInitWave35() {
  uiBus.on("ve:queue-rendered", _veDecorateQueueRows);
  uiBus.on("ve:folder-changed", (folder) => { delete _veSubfolderCache[folder]; });
  uiBus.on("ve:timeline-rendered", _veOnTimelineRendered);
  const sync = () => { _veSyncTimelineClipMark(); _veSyncPreviewStepButtons(); };
  uiBus.on("ve:derived-refresh", () => uiDebounce("ve:wave35", sync, 180));
  uiBus.on("ve:fields-applied", () => uiDebounce("ve:wave35", sync, 180));
  uiBus.on("ve:preview-files", _veSyncPreviewStepButtons);
  _veEl("vePreviewFile").addEventListener("change", _veSyncPreviewStepButtons);
  document.addEventListener("keydown", (e) => {
    if (!_veIsActive() || _veIsTyping() || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "m" || e.key === "M") { if (_veTimeline) { e.preventDefault(); addVeMarker(); } }
  });
  _veSyncPreviewStepButtons();
}
