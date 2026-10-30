// item: ארכיון - סקריפטים ש-video_editor.py מייתר לגמרי (ARCHIVED_SCRIPTS
// בצד השרת) מוצגים כאן במקום ברשימה הראשית - ניתנים להרצה עדיין, לחיצה
// עליהם רק עוברת לטאב "סקריפטים" עם אותו סקריפט כבר נבחר (משתמשת ב-
// selectScript() הרגיל, לא מכפילה לוגיקת-הרצה).
// Scripts catalog (sidebar): categories (collapsible, with counts), search, favorites and "archive"
// - the favorites / locally-archived scripts / collapsed categories live in this browser's localStorage.
const SC_FAV_KEY = "clipforgeFavScripts";
const SC_ARCH_KEY = "clipforgeArchivedScripts";
const SC_COLLAPSED_KEY = "clipforgeCollapsedCategories";
const SC_CATEGORY_ORDER = ["video", "stream", "tools", "steam"];

function _scLoad(key) {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return null;
    const arr = JSON.parse(raw);
    return new Set(Array.isArray(arr) ? arr : []);
  } catch (e) { return null; }
}

function _scSave(key, set) {
  try { localStorage.setItem(key, JSON.stringify([...set].sort())); } catch (e) { /* storage unavailable: keep working without persistence */ }
}

// Never touched in this browser -> seed from the server's favorites (the shared config), then it is purely local.
function _scFavorites() {
  const stored = _scLoad(SC_FAV_KEY);
  if (stored) return stored;
  return new Set((state.scripts || []).filter(s => s.is_favorite).map(s => s.id));
}
function _scLocalArchived() { return _scLoad(SC_ARCH_KEY) || new Set(); }
function _scCollapsed() { return _scLoad(SC_COLLAPSED_KEY) || new Set(); }
function _scIsArchived(s) { return !!s.archived || _scLocalArchived().has(s.id); }

function renderArchiveList() {
  const container = document.getElementById("archiveList");
  container.innerHTML = "";
  const localArchived = _scLocalArchived();
  const archived = (state.scripts || []).filter(_scIsArchived);
  if (!archived.length) {
    const hint = document.createElement("div");
    hint.className = "hint"; hint.style.display = "block";
    hint.textContent = "אין סקריפטים בארכיון.";
    container.appendChild(hint);
    return;
  }
  for (const s of archived) {
    const row = document.createElement("div");
    row.className = "script-row";
    const btn = document.createElement("button");
    btn.className = "script-btn";
    btn.textContent = s.name;
    btn.title = s.description || "";
    btn.onclick = () => { switchTab("scripts"); selectScript(s.id); };
    row.appendChild(btn);
    if (!s.archived && localArchived.has(s.id)) {
      const restore = document.createElement("button");
      restore.className = "star-btn archive-btn";
      restore.title = "החזר מהארכיון";
      restore.setAttribute("aria-label", restore.title + " · " + s.name);
      restore.textContent = "\u21A9";
      restore.onclick = () => restoreScript(s.id);
      row.appendChild(restore);
    }
    container.appendChild(row);
  }
}

function _appendScriptRow(container, s) {
  const row = document.createElement("div");
  row.className = "script-row";
  const isFav = _scFavorites().has(s.id);

  // star-btn first in the DOM (dir="rtl" puts it on the right), like ui/sidebar.py
  const star = document.createElement("button");
  star.className = "star-btn";
  star.title = isFav ? "הסר ממועדפים" : "הוסף למועדפים";
  star.setAttribute("aria-label", star.title + " · " + s.name);
  star.setAttribute("aria-pressed", isFav ? "true" : "false");
  star.textContent = isFav ? "\u2605" : "\u2606";
  star.onclick = (e) => { e.stopPropagation(); toggleFavorite(s.id); };
  row.appendChild(star);

  const btn = document.createElement("button");
  btn.className = "script-btn" + (s.id === state.selectedId ? " selected" : "");
  const badge = s.safety === "modifies" ? "\u26A0\uFE0F " : "";
  btn.textContent = badge + s.name;
  if (s.description) btn.title = s.description;
  btn.onclick = () => selectScript(s.id);
  row.appendChild(btn);

  const arch = document.createElement("button");
  arch.className = "star-btn archive-btn";
  arch.title = "העבר לארכיון";
  arch.setAttribute("aria-label", arch.title + " · " + s.name);
  arch.textContent = "\uD83D\uDDC4\uFE0F";
  arch.onclick = (e) => { e.stopPropagation(); archiveScript(s.id); };
  row.appendChild(arch);

  container.appendChild(row);
}

function toggleFavorite(id) {
  const favs = _scFavorites();
  if (favs.has(id)) favs.delete(id); else favs.add(id);
  _scSave(SC_FAV_KEY, favs);
  renderScripts();
}

function archiveScript(id) {
  const set = _scLocalArchived();
  set.add(id);
  _scSave(SC_ARCH_KEY, set);
  renderScripts();
  renderArchiveList();
}

function restoreScript(id) {
  const set = _scLocalArchived();
  set.delete(id);
  _scSave(SC_ARCH_KEY, set);
  renderScripts();
  renderArchiveList();
}

function toggleCategory(key) {
  const set = _scCollapsed();
  if (set.has(key)) set.delete(key); else set.add(key);
  _scSave(SC_COLLAPSED_KEY, set);
  renderScripts();
}

function _scCategoryRank(key) {
  const i = SC_CATEGORY_ORDER.indexOf(key);
  return i < 0 ? SC_CATEGORY_ORDER.length : i;
}

function renderScripts() {
  const q = document.getElementById("search").value.trim().toLowerCase();
  const isUnfiltered = !q;
  // archived scripts (server-archived or archived in this browser) only show in the "archive" tab
  const visibleScripts = state.scripts.filter(s => !_scIsArchived(s));
  const matches = s => !q || [s.name, s.id, s.description, s.category].some(v => (v || "").toLowerCase().includes(q));
  const filtered = visibleScripts.filter(matches);
  const container = document.getElementById("scriptList");
  container.innerHTML = "";

  // "favorites" / "recently used" only without a search filter (like ui/sidebar.py's is_unfiltered)
  const favSet = _scFavorites();
  const favorites = isUnfiltered ? visibleScripts.filter(s => favSet.has(s.id)).sort((a, b) => a.name.localeCompare(b.name)) : [];
  const recentScripts = isUnfiltered
    ? (state.recentScriptNames || []).map(name => visibleScripts.find(s => s.id.split("/").pop() === name)).filter(Boolean)
    : [];

  if (favorites.length) {
    const catEl = document.createElement("div");
    catEl.className = "category"; catEl.textContent = "\u2B50 מועדפים";
    container.appendChild(catEl);
    for (const s of favorites) _appendScriptRow(container, s);
  }

  if (recentScripts.length) {
    const catEl = document.createElement("div");
    catEl.className = "category"; catEl.textContent = "🕒 הורצו לאחרונה";
    container.appendChild(catEl);
    for (const s of recentScripts) _appendScriptRow(container, s);
  }

  // Favorites exist: collapse the full category list behind a toggle (like ui/sidebar.py)
  if (isUnfiltered && favorites.length && !state.showAllCategories) {
    const btn = document.createElement("button");
    btn.className = "collapse-toggle-btn";
    btn.textContent = "📂 הצג את כל הקטגוריות";
    btn.onclick = () => { state.showAllCategories = true; renderScripts(); };
    container.appendChild(btn);
    return;
  }

  if (!filtered.length) {
    const hint = document.createElement("div");
    hint.className = "hint"; hint.style.display = "block";
    hint.textContent = "לא נמצאו סקריפטים.";
    container.appendChild(hint);
  }

  const groups = new Map();
  for (const s of filtered) {
    const key = s.category_key || s.category;
    if (!groups.has(key)) groups.set(key, { label: s.category, scripts: [] });
    groups.get(key).scripts.push(s);
  }
  const collapsed = _scCollapsed();
  const ordered = [...groups.entries()].sort((a, b) => _scCategoryRank(a[0]) - _scCategoryRank(b[0]));
  for (const [key, group] of ordered) {
    const isCollapsed = isUnfiltered && collapsed.has(key);   // a search always shows every match
    const head = document.createElement("button");
    head.className = "category category-toggle";
    head.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
    head.dataset.category = key;
    head.append((isCollapsed ? "\u25B8 " : "\u25BE ") + group.label, " (" + group.scripts.length + ")");
    head.onclick = () => toggleCategory(key);
    container.appendChild(head);
    if (isCollapsed) continue;
    for (const s of group.scripts) _appendScriptRow(container, s);
  }

  if (isUnfiltered && favorites.length && state.showAllCategories) {
    const btn = document.createElement("button");
    btn.className = "collapse-toggle-btn";
    btn.textContent = "📁 הצג פחות";
    btn.onclick = () => { state.showAllCategories = false; renderScripts(); };
    container.appendChild(btn);
  }
}
function selectScript(id) {
  state.selectedId = id;
  const s = state.scripts.find(x => x.id === id);
  document.getElementById("selName").textContent = "📁 " + s.name;
  document.getElementById("selDesc").textContent = s.description || "אין תיאור זמין.";
  renderScripts();
  updateRunEnabled();

  // פאנלים ספציפיים-לסקריפט (זהה בעיקרון ל-ui/settings_tab.py בגרסה השולחנית) -
  // רק story_cutter.py/video_editor.py/rocket_shorts_publisher.py מכירים את
  // הדגלים האלה בכלל.
  const basename = id.split("/").pop();
  document.getElementById("storyCutterOptions").hidden = basename !== "story_cutter.py";
  document.getElementById("videoEditorOptions").hidden = basename !== "video_editor.py";
  document.getElementById("superManagerOptions").hidden = basename !== "super_manager.py";
  if (basename === "super_manager.py") updateSuperManagerModeVisibility();
  document.getElementById("superStreamerOptions").hidden = basename !== "super_streamer.py";
  if (basename === "super_streamer.py") updateSuperStreamerModeVisibility();
  if (basename === "video_editor.py") {
    rebuildFavoritesBox();
    updateCategorySummaries();
    // item: טור הכרות ראשוני - מוצג רק אם עדיין לא נדחה בדפדפן הזה (localStorage,
    // לא state בצד-שרת - זה טיפ פר-דפדפן, לא הגדרה שצריך לסנכרן בין מכשירים).
    document.getElementById("veOnboardingBanner").hidden = !!localStorage.getItem("veOnboardingSeen");
    _veResetUndoHistory();
    updateVeEtaDisplay();
    updateChangedSinceRunIndicator();
    _veRefreshFolderCounts();
    _veScheduleTrimReference();
    _veRefreshAllDerivedUi();
    setTimeout(_veLoadSystemFonts, 1500);  // בורר הגופנים מוכן לפני שמגיעים לשדה
    _handleVeDeepLinkHash();
  }
  document.getElementById("rocketShortsOptions").hidden = basename !== "rocket_shorts_publisher.py";
  if (basename !== "video_editor.py") document.getElementById("wmPreviewBox").hidden = true;
  document.getElementById("vePreset").value = "";
  _setVeProfileButtonsVisible(false);
  document.getElementById("veProfileMetaInfo").textContent = "";
  state.veBaseline = null;
  updateUnsavedIndicator();
}

// item: מנהל-העל - מציג רק את השדות הרלוונטיים למצב הנבחר (scan/report/clean),
// אותו עיקרון בדיוק כמו "↳ לפי זיהוי-פנים" בעורך-העל (disabled/hidden עד
// שהמצב הרלוונטי נבחר).
function updateSuperManagerModeVisibility() {
  const mode = document.getElementById("smMode").value;
  document.getElementById("smScanFields").hidden = mode !== "scan";
  document.getElementById("smCleanFields").hidden = mode !== "clean";
}

function updateSuperStreamerModeVisibility() {
  const mode = document.getElementById("ssMode").value;
  document.getElementById("ssTwitchFields").hidden = mode !== "twitch";
}

function dismissVideoEditorOnboarding() {
  try { localStorage.setItem("veOnboardingSeen", "1"); } catch (e) { /* פרטי/מוגבל - לא קריטי, רק מציג את הבאנר שוב בפעם הבאה */ }
  document.getElementById("veOnboardingBanner").hidden = true;
}

function onWatermarkOpacityInput() {
  // מעדכן ישירות (בלי fetch לשרת) - שקיפות היא CSS opacity טהור על התצוגה
  // המקדימה הקיימת, לא משנה גיאומטריה, אז אין צורך לקרוא ל-updateWatermarkPreview()
  // המלאה (async) על כל תזוזת סליידר.
  const raw = document.getElementById("veWatermarkOpacity").value;
  const opacity = parseFloat(raw);
  const clamped = Number.isFinite(opacity) ? Math.max(0, Math.min(1, opacity)) : 1;
  document.getElementById("veWatermarkOpacityValue").textContent = clamped.toFixed(2);
  document.getElementById("wmPreviewImg").style.opacity = clamped;
}

function onWatermarkScaleInput() {
  // בניגוד לשקיפות - שינוי גודל *כן* משנה גיאומטריה (target_w/target_h/x/y),
  // אז חייב לקרוא ל-updateWatermarkPreview() המלאה (מחשבת מחדש בצד השרת).
  const value = document.getElementById("veWatermarkScale").value;
  document.getElementById("veWatermarkScaleValue").textContent = value + "%";
  updateWatermarkPreview();
}

function onWatermarkPositionSelected() {
  // בחירת preset מהרשימה גוברת על מיקום מותאם-אישית קודם (גרירה) - אחרת
  // ה-preset הנבחר לא היה משפיע כלל בפועל (custom_x/custom_y עדיין גוברים).
  document.getElementById("veWatermarkX").value = "";
  document.getElementById("veWatermarkY").value = "";
  updateWatermarkPreview();
}

function clearWatermarkCustomPosition() {
  document.getElementById("veWatermarkX").value = "";
  document.getElementById("veWatermarkY").value = "";
  document.getElementById("veWmDragCoords").textContent = "";
  updateWatermarkPreview();
}

async function updateWatermarkPreview() {
  // תצוגה מקדימה אמיתית (לא ניחוש) של מיקום/גודל ה-watermark - מחשבת את
  // הגיאומטריה בצד השרת (compute_watermark_geometry, אותה פונקציה בדיוק
  // שה-ffmpeg command בפועל ישתמש בה) ומציגה אותה יחסית לקופסה קטנה בדפדפן.
  const path = document.getElementById("veWatermarkPath").value.trim();
  const box = document.getElementById("wmPreviewBox");
  const img = document.getElementById("wmPreviewImg");
  const errorEl = document.getElementById("wmPreviewError");
  errorEl.hidden = true;
  if (!path) { box.hidden = true; return; }

  const vertical = document.getElementById("veVertical").checked;
  const position = document.getElementById("veWatermarkPosition").value;
  const scale = (parseFloat(document.getElementById("veWatermarkScale").value) || 15) / 100;
  const params = new URLSearchParams({ path, vertical: vertical ? "true" : "false", position, scale: String(scale) });
  const customX = document.getElementById("veWatermarkX").value;
  const customY = document.getElementById("veWatermarkY").value;
  if (customX !== "" && customY !== "") {
    params.set("custom_x", customX);
    params.set("custom_y", customY);
  }

  let data;
  try {
    const res = await fetch("/api/watermark_preview?" + params.toString());
    data = await res.json();
  } catch (e) {
    box.hidden = true;
    errorEl.hidden = false;
    errorEl.textContent = "⚠️ שגיאה בטעינת התצוגה המקדימה";
    return;
  }
  if (data.error) {
    box.hidden = true;
    errorEl.hidden = false;
    errorEl.textContent = "⚠️ " + data.error;
    return;
  }

  // ממדי הקופסה נקבעים כאן כערכים ידועים (לא נמדדים חזרה מה-DOM) בכוונה -
  // box עדיין hidden בשלב הזה (display:none), ואלמנט חבוי תמיד מדווח
  // offsetWidth/offsetHeight כ-0 בלי קשר לכל style.width/height שהוגדר עליו.
  const boxWidth = vertical ? 120 : 213;
  const boxHeight = vertical ? 213 : 120;
  box.style.width = boxWidth + "px";
  box.style.height = boxHeight + "px";
  const scaleX = boxWidth / data.output_width;
  const scaleY = boxHeight / data.output_height;
  img.style.left = (data.x * scaleX) + "px";
  img.style.top = (data.y * scaleY) + "px";
  img.style.width = (data.target_w * scaleX) + "px";
  img.style.height = (data.target_h * scaleY) + "px";
  // שקיפות (item: watermark opacity) - CSS opacity בלבד, אין צורך בעיבוד
  // תמונה בצד השרת (בניגוד לדסקטופ, שמרכיב PIL alpha channel בפועל) - זו
  // רק תצוגה מקדימה, ה-ffmpeg command עצמו הוא זה שבאמת קובע את הפלט.
  const opacity = parseFloat(document.getElementById("veWatermarkOpacity").value);
  img.style.opacity = Number.isFinite(opacity) ? Math.max(0, Math.min(1, opacity)) : 1;
  img.src = "/api/watermark_image?path=" + encodeURIComponent(path);
  box.hidden = false;
  // item: מספרים מדויקים ליד גרירת ה-watermark - מוצג גם בטעינה/מעבר-פרופיל
  // (לא רק תוך כדי גרירה עצמה, ראו _wmPreviewMouseMove למטה).
  const coordsEl = document.getElementById("veWmDragCoords");
  if (coordsEl) coordsEl.textContent = (customX !== "" && customY !== "") ? `x=${Math.round(parseFloat(customX) * 100)}%  y=${Math.round(parseFloat(customY) * 100)}%` : "";
}

// item: גרירת watermark חופשית - גרירה חופשית של #wmPreviewImg בתוך
// #wmPreviewBox (position:relative/absolute, ראו ה-CSS) קובעת מיקום מדויק
// (לא רק preset). mousemove/mouseup רשומים על document (לא רק על ה-img
// עצמו) כדי שגרירה שממשיכה אחרי שהעכבר יצא מהקופסה הקטנה עדיין תיתפס.
let _wmDragState = null;

function _wmPreviewMouseDown(e) {
  const img = document.getElementById("wmPreviewImg");
  if (!img.src) return;
  const box = document.getElementById("wmPreviewBox");
  _wmDragState = {
    startClientX: e.clientX, startClientY: e.clientY,
    startLeft: parseFloat(img.style.left) || 0, startTop: parseFloat(img.style.top) || 0,
    boxWidth: box.getBoundingClientRect().width, boxHeight: box.getBoundingClientRect().height,
    imgWidth: img.offsetWidth, imgHeight: img.offsetHeight,
  };
  e.preventDefault();
}

function _wmPreviewMouseMove(e) {
  if (!_wmDragState) return;
  const img = document.getElementById("wmPreviewImg");
  const dx = e.clientX - _wmDragState.startClientX;
  const dy = e.clientY - _wmDragState.startClientY;
  const maxLeft = Math.max(0, _wmDragState.boxWidth - _wmDragState.imgWidth);
  const maxTop = Math.max(0, _wmDragState.boxHeight - _wmDragState.imgHeight);
  const newLeft = Math.max(0, Math.min(_wmDragState.startLeft + dx, maxLeft));
  const newTop = Math.max(0, Math.min(_wmDragState.startTop + dy, maxTop));
  img.style.left = newLeft + "px";
  img.style.top = newTop + "px";
  // מרכז ה-watermark (לא הפינה השמאלית-עליונה) - תואם ל-compute_watermark_geometry's
  // custom_center_fraction, כדי שגודל שמשתנה אח"כ לא "יזיז" את הנקודה שנגררה.
  const centerXFraction = Math.max(0, Math.min(1, (newLeft + _wmDragState.imgWidth / 2) / _wmDragState.boxWidth));
  const centerYFraction = Math.max(0, Math.min(1, (newTop + _wmDragState.imgHeight / 2) / _wmDragState.boxHeight));
  document.getElementById("veWatermarkX").value = centerXFraction.toFixed(4);
  document.getElementById("veWatermarkY").value = centerYFraction.toFixed(4);
  // item: מספרים מדויקים ליד גרירת ה-watermark - עדכון חי בזמן הגרירה עצמה.
  document.getElementById("veWmDragCoords").textContent = `x=${Math.round(centerXFraction * 100)}%  y=${Math.round(centerYFraction * 100)}%`;
}

function _wmPreviewMouseUp() {
  _wmDragState = null;
}

document.getElementById("wmPreviewImg").addEventListener("mousedown", _wmPreviewMouseDown);
document.addEventListener("mousemove", _wmPreviewMouseMove);
document.addEventListener("mouseup", _wmPreviewMouseUp);

function onFolderTyped() {
  // רק שינוי אמיתי של התיקייה מאפס את התור - אירוע change נוסף על אותו ערך
  // (למשל Enter ואז יציאה מהשדה) היה מוחק בשקט תור שכבר נערך/סודר.
  const next = document.getElementById("folderInput").value.trim();
  const changed = next !== state.folder;
  state.folder = next;
  updateRunEnabled();
  // גל 32: אותה תיקייה שוב כשהתור ריק (למשל כונן שלא היה מחובר כשהדף נטען) - נטענת מחדש; אין מה לאבד
  if (changed || (next && !_veQueueState.length)) _onVeFolderChanged();
}

function updateRunEnabled() {
  document.getElementById("runBtn").disabled = !(state.selectedId && state.folder && !state.running);
}

async function openBrowser() {
  state.browseTarget = "folder";
  state.browseMode = "folder";
  await browseTo(state.folder || "");
  document.getElementById("modalBg").classList.add("show");
}

async function openBackupFolderBrowser() {
  // אותו מודל דפדוף בדיוק כמו בחירת תיקיית עבודה (openBrowser) - state.browseTarget
  // קובע לאן chooseCurrentFolder כותב את התוצאה, כדי לא לשכפל את כל דיאלוג
  // הדפדוף (כוננים/תיקיות/קבצים) פעם נוספת רק בשביל שדה יעד אחר.
  state.browseTarget = "backup";
  state.browseMode = "folder";
  await browseTo(document.getElementById("gsNasFolder").value || "");
  document.getElementById("modalBg").classList.add("show");
}

async function openRocketFolderBrowser(target) {
  state.browseTarget = target;
  state.browseMode = "folder";
  const fieldId = target === "rocket_input" ? "rsInputDir" : "rsOutputDir";
  await browseTo(document.getElementById(fieldId).value || "");
  document.getElementById("modalBg").classList.add("show");
}

async function openRocketOverlayBrowser() {
  // browseMode="file" - קליק על שורת קובץ ב-browseTo בוחר אותו (ראו שם),
  // לא רק מוריד אותו כמו בברירת המחדל (בחירת תיקייה).
  state.browseTarget = "rocket_overlay";
  state.browseMode = "file";
  const current = document.getElementById("rsOverlayPath").value;
  await browseTo(current ? current.substring(0, current.lastIndexOf("/")) : "");
  document.getElementById("modalBg").classList.add("show");
}

async function openWaveformFileBrowser() {
  // זהה ל-ui/rocket_settings_tab.py's show_waveform_dialog - filedialog.askopenfilename
  // שם, אותו מודל דפדוף-קבצים (browseMode="file") כאן.
  state.browseTarget = "waveform";
  state.browseMode = "file";
  await browseTo(state.folder || "");
  document.getElementById("modalBg").classList.add("show");
}

function closeBrowser() {
  document.getElementById("modalBg").classList.remove("show");
  state.browseExtensions = null;
}

async function browseTo(path) {
  const res = await fetch("/api/browse?path=" + encodeURIComponent(path));
  const data = await res.json();
  if (data.error) { alert(data.error); return; }
  state.browsePath = data.path;
  document.getElementById("modalPath").textContent = data.path;
  // במצב "בחירת קובץ" בוחרים ע"י קליק על שורת קובץ ספציפית (ראו למטה) - כפתור
  // "בחר תיקייה זו" לא רלוונטי שם ועלול לבלבל (אין קובץ שנבחר סתם מבחירת התיקייה).
  document.getElementById("modalChooseFolderBtn").hidden = state.browseMode === "file";

  // כוננים (C:\, D:\ וכו') - תמיד מוצגים, לא רק בהגעה לשורש כונן, כדי שקפיצה
  // לכונן אחר תהיה זמינה מכל נקודה בדפדוף (בלי זה אפשר היה להגיע רק לכוננים
  // שנמצאים "מעל" נתיב הבית של המשתמש - בדרך כלל C: בלבד).
  const drivesRow = document.getElementById("modalDrives");
  drivesRow.innerHTML = "";
  for (const drive of (data.drives || [])) {
    const btn = document.createElement("button");
    btn.textContent = "🖴 " + drive;
    if (data.path.toLowerCase().startsWith(drive.toLowerCase())) btn.classList.add("active");
    btn.onclick = () => browseTo(drive);
    drivesRow.appendChild(btn);
  }

  const list = document.getElementById("modalList");
  list.innerHTML = "";
  if (data.parent) {
    const up = document.createElement("div"); up.textContent = "⬆️ .. (תיקיית אב)";
    up.onclick = () => browseTo(data.parent);
    list.appendChild(up);
  }
  for (const folder of data.folders) {
    const row = document.createElement("div"); row.textContent = "📁 " + folder;
    row.onclick = () => browseTo(data.path + "/" + folder);
    list.appendChild(row);
  }
  // קבצים (לא רק תיקיות) - כדי שאפשר יהיה לדפדף לתיקיית התוצרים (למשל
  // workspace/vertical) ולהוריד ישירות את הסרטון המרונדר, בלי לצאת לדפדפן קבצים.
  // item: בוררי-קבצים לשדות העורך - מסננים לפי סוג הקובץ שהשדה מצפה לו.
  const allowedExtensions = state.browseMode === "file" ? state.browseExtensions : null;
  for (const file of (data.files || [])) {
    if (allowedExtensions && !allowedExtensions.some(ext => file.name.toLowerCase().endsWith(ext))) continue;
    const row = document.createElement("div");
    row.style.display = "flex"; row.style.justifyContent = "space-between"; row.style.alignItems = "center";
    const label = document.createElement("span"); label.textContent = "📄 " + file.name + " (" + _formatFileSize(file.size) + ")";
    const dl = document.createElement("a");
    dl.textContent = "⬇️"; dl.title = "הורדה";
    dl.href = "/api/download?path=" + encodeURIComponent(data.path + "/" + file.name);
    dl.onclick = (e) => e.stopPropagation();
    row.appendChild(label); row.appendChild(dl);
    // מצב "בחירת קובץ" (state.browseMode, ראו openRocketOverlayBrowser) - קליק
    // על השורה עצמה בוחר את הקובץ, לא רק מוריד אותו (ברירת המחדל, לבחירת תיקייה).
    if (state.browseMode === "file") {
      row.style.cursor = "pointer";
      row.onclick = () => chooseCurrentFile(file.name);
    }
    list.appendChild(row);
  }
}

function _formatFileSize(bytes) {
  if (bytes >= 1024 ** 3) return (bytes / 1024 ** 3).toFixed(1) + " GB";
  if (bytes >= 1024 ** 2) return (bytes / 1024 ** 2).toFixed(1) + " MB";
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + " KB";
  return bytes + " B";
}
function chooseCurrentFolder() {
  if (state.browseTarget === "backup") {
    document.getElementById("gsNasFolder").value = state.browsePath;
  } else if (state.browseTarget === "rocket_input") {
    document.getElementById("rsInputDir").value = state.browsePath;
  } else if (state.browseTarget === "rocket_output") {
    document.getElementById("rsOutputDir").value = state.browsePath;
  } else if (typeof state.browseTarget === "function") {   // 19.10.2026: מסך שמעביר פונקציה (עורך הגרפים - ייבוא תיקייה)
    const target = state.browseTarget;
    state.browseTarget = "folder";
    closeBrowser();
    target(state.browsePath);
    return;
  } else {
    state.folder = state.browsePath;
    document.getElementById("folderInput").value = state.folder;
    updateRunEnabled();
    _onVeFolderChanged();
  }
  closeBrowser();
}

function chooseCurrentFile(filename) {
  // אותו מודל דפדוף בדיוק, במצב "בחירת קובץ" (state.browseMode) - קליק על
  // שורת קובץ בוחר אותו במקום להוריד (הקישור ⬇️ עדיין עובד כרגיל, לחיצה עליו
  // עוצרת את ה-bubbling כדי לא לבחור בטעות תוך כדי הורדה).
  const fullPath = state.browsePath.replace(/[\\/]+$/, "") + "/" + filename;
  if (String(state.browseTarget || "").startsWith("ve-field:")) {
    const input = document.getElementById(state.browseTarget.slice("ve-field:".length));
    if (input) _veSetFieldValue(input, fullPath);
  } else if (state.browseTarget === "rocket_overlay") {
    document.getElementById("rsOverlayPath").value = fullPath;
  } else if (state.browseTarget === "waveform") {
    loadWaveform(fullPath, filename);
  }
  closeBrowser();
}

function _collectRunOptions() {
  const basename = (state.selectedId || "").split("/").pop();
  if (basename === "story_cutter.py") {
    return { ai_provider: document.getElementById("aiProviderSelect").value };
  }
  if (basename === "super_manager.py") {
    return {
      sm_mode: document.getElementById("smMode").value,
      sm_target_dir: document.getElementById("smTargetDir").value,
      sm_export_excel: document.getElementById("smExportExcel").checked,
      sm_export_html: document.getElementById("smExportHtml").checked,
      sm_keep_policy: document.getElementById("smKeepPolicy").value,
      sm_execute: document.getElementById("smExecute").checked,
    };
  }
  if (basename === "super_streamer.py") {
    return {
      ss_mode: document.getElementById("ssMode").value,
      ss_twitch_limit: parseInt(document.getElementById("ssTwitchLimit").value || "10", 10),
    };
  }
  if (basename === "video_editor.py") {
    const loudnormTargetRaw = document.getElementById("veLoudnormTarget").value;
    return {
      watermark_path: document.getElementById("veWatermarkPath").value,
      watermark_position: document.getElementById("veWatermarkPosition").value,
      watermark_opacity: parseFloat(document.getElementById("veWatermarkOpacity").value || "1.0"),
      watermark_scale: (parseFloat(document.getElementById("veWatermarkScale").value || "15")) / 100,
      watermark_x: document.getElementById("veWatermarkX").value === "" ? null : parseFloat(document.getElementById("veWatermarkX").value),
      watermark_y: document.getElementById("veWatermarkY").value === "" ? null : parseFloat(document.getElementById("veWatermarkY").value),
      remove_watermark_position: document.getElementById("veRemoveWatermarkPosition").value,
      pip_path: document.getElementById("vePipPath").value,
      pip_position: document.getElementById("vePipPosition").value,
      pip_scale: (parseFloat(document.getElementById("vePipScale").value || "30")) / 100,
      pip_opacity: parseFloat(document.getElementById("vePipOpacity").value || "1.0"),
      pip_x: document.getElementById("vePipX").value === "" ? null : parseFloat(document.getElementById("vePipX").value),
      pip_y: document.getElementById("vePipY").value === "" ? null : parseFloat(document.getElementById("vePipY").value),
      vertical: document.getElementById("veVertical").checked,
      smart_crop: document.getElementById("veSmartCrop").checked,
      smart_crop_face: document.getElementById("veSmartCropFace").checked,
      blur_background: document.getElementById("veBlurBackground").checked,
      trim_start: _veTimeValue("veTrimStart", 0),
      trim_duration: _veTimeValue("veTrimDuration", null),
      trim_silence: document.getElementById("veTrimSilence").checked,
      target_seconds: Math.round(_veTimeValue("veTargetSeconds", 0)),
      keep_audio: document.getElementById("veKeepAudio").checked,
      captions: document.getElementById("veCaptions").checked,
      captions_translate: document.getElementById("veCaptionsTranslate").checked,
      loudnorm: document.getElementById("veLoudnorm").checked,
      loudnorm_target: loudnormTargetRaw === "" ? null : parseFloat(loudnormTargetRaw),
      denoise: document.getElementById("veDenoise").checked,
      sharpen: document.getElementById("veSharpen").checked,
      thumbnail: document.getElementById("veThumbnail").checked,
      fps: document.getElementById("veFps").value,
      lut_path: document.getElementById("veLutPath").value,
      auto_levels: document.getElementById("veAutoLevels").checked,
      noise_gate: document.getElementById("veNoiseGate").checked,
      remove_mid_silence: document.getElementById("veRemoveMidSilence").checked,
      stabilize: document.getElementById("veStabilize").checked,
      chromakey: document.getElementById("veChromakey").checked,
      chromakey_color: document.getElementById("veChromakeyColor").value,
      chromakey_bg_color: document.getElementById("veChromakeyBgColor").value,
      caption_font: document.getElementById("veCaptionFont").value,
      caption_font_size: parseInt(document.getElementById("veCaptionFontSize").value || "16", 10),
      caption_color: document.getElementById("veCaptionColor").value,
      caption_position: document.getElementById("veCaptionPosition").value,
      fade_in_seconds: _veTimeValue("veFadeInSeconds", 0),
      fade_out_seconds: _veTimeValue("veFadeOutSeconds", 0),
      remove_ranges: document.getElementById("veRemoveRanges").value,
      replace_audio_path: document.getElementById("veReplaceAudioPath").value,
      text: document.getElementById("veText").value,
      text_position: document.getElementById("veTextPosition").value,
      text_font: document.getElementById("veTextFont").value,
      text_font_size: parseInt(document.getElementById("veTextFontSize").value || "24", 10),
      text_color: document.getElementById("veTextColor").value,
      codec: document.getElementById("veCodec").value,
      preserve_resolution: document.getElementById("vePreserveResolution").checked,
      no_suffix: document.getElementById("veNoSuffix").checked,
      number_videos: document.getElementById("veNumberVideos").checked,
      number_prefix: document.getElementById("veNumberPrefix").value,
      number_start: document.getElementById("veNumberStart").value === "" ? null : parseInt(document.getElementById("veNumberStart").value, 10),
      folder: state.folder,
      parallel: parseInt(document.getElementById("veParallel").value || "1", 10),
      max_concurrent_nvenc: document.getElementById("veMaxConcurrentNvenc").value === "" ? null : parseInt(document.getElementById("veMaxConcurrentNvenc").value, 10),
      effort: document.getElementById("veEffort").value,
      container: document.getElementById("veContainer").value,
      output_template: document.getElementById("veOutputTemplate").value,
      validate_only: document.getElementById("veValidateOnly").checked,
      notify_per_file: document.getElementById("veNotifyPerFile").checked,
      export_report: document.getElementById("veExportReport").value,
      favorite_fields: document.getElementById("veFavoriteFields").value,
      only_files: _veQueueSelectedFiles(),
      ve_profile_name: _currentVeProfileName(),
      ..._collectGenericVeFields(),
      // item: מצב איחוד קטעים - הקבצים המסומנים בתור לפי הסדר שלהם (null כשהמצב כבוי).
      concat_files: document.getElementById("veConcatMode").checked ? _veConcatFiles() : null,
      // item: דריסות פר-קובץ - רק שורות תור שבאמת יש להן דריסה.
      batch_overrides: _veBatchOverrides(),
      // item 57: תור שמור עם הפרופיל (רק כש"📋 שמור גם את התור" מסומן).
      queue_files: _veQueueSnapshotForProfile(),
    };
  }
  if (basename === "rocket_shorts_publisher.py") {
    return {
      dry_run: document.getElementById("rsDryRun").checked,
      no_square: document.getElementById("rsNoSquare").checked,
      no_loudnorm: document.getElementById("rsNoLoudnorm").checked,
    };
  }
  return {};
}

async function runScript() {
  const runOptions = _collectRunOptions();
  // item: תור-אצווה ניתן-לעריכה - מערך ריק (לא null) אומר שהמשתמש ערך את
  // התור וביטל את כל הסימונים בפועל - עדיף לחסום מפורשות מאשר ליפול-בחזרה
  // בשקט ל"כל הקבצים" (התנהגות מפתיעה, לא מה שהמשתמש כנראה התכוון אליו).
  if (Array.isArray(runOptions.only_files) && runOptions.only_files.length === 0) {
    alert('כל הקבצים בתור העיבוד בוטלו - סמן לפחות קובץ אחד, או רענן/סגור את "📋 תור עיבוד".');
    return;
  }
  const res = await fetch("/api/run", {
    method: "POST", headers: {"Content-Type": "application/json"},
    // גל 8: פעולות סוף-ריצה/פרסום הן העדפות-ריצה (לא הגדרות פרופיל) - רק בגוף הבקשה
    body: JSON.stringify({ script: state.selectedId, folder: state.folder, ...runOptions, ...((state.selectedId || "").endsWith("video_editor.py") ? _veRunExtras() : {}) })
  });
  const data = await res.json();
  if (data.error) { alert(data.error); return; }
  state.running = true;
  // item: "מה השתנה מאז ההרצה האחרונה" - נלכד רק כשההרצה באמת שוגרה בהצלחה
  // (לא בכל שינוי טופס), ורק ל-video_editor.py - לצד veBaseline (פרופיל
  // שמור) זה ציר השוואה שונה: "מול מה שבאמת רץ", לא "מול מה ששמור".
  if ((state.selectedId || "").endsWith("video_editor.py")) {
    state.veLastRunSnapshot = JSON.stringify(runOptions);
    updateChangedSinceRunIndicator();
  }
  state.veLastRunScript = state.selectedId || "";
  clearVeLogTail();
  _veFileProgress = {};
  document.getElementById("console").textContent = "";
  document.getElementById("progressBar").style.width = "0%";
  document.getElementById("pctLabel").textContent = "";
  document.getElementById("runBtn").disabled = true;
  document.getElementById("stopBtn").disabled = false;
  document.getElementById("pauseBtn").disabled = false;
}

function updateChangedSinceRunIndicator() {
  const el = document.getElementById("veChangedSinceRun");
  if (!state.veLastRunSnapshot || !(state.selectedId || "").endsWith("video_editor.py")) {
    el.hidden = true;
    return;
  }
  const changed = JSON.stringify(_collectRunOptions()) !== state.veLastRunSnapshot;
  el.hidden = !changed;
  el.textContent = changed ? "🔀 שונה מההרצה האחרונה" : "";
}

async function stopScript() {
  await fetch("/api/stop", { method: "POST" });
}

// השהיה/המשך (item: Pause) - מקפיא את התהליך הרץ (psutil.suspend בצד השרת,
// לא עוצר) כדי לפנות CPU/GPU זמנית בלי לאבד התקדמות; מצב הכפתור מנוהל כאן
// מקומית (בלי לחכות ל-WS) בדיוק כמו stopScript() - אין הבדל-מצב לחכות לו.
let _paused = false;

async function togglePause() {
  const btn = document.getElementById("pauseBtn");
  if (_paused) {
    await fetch("/api/resume", { method: "POST" });
    _paused = false;
    btn.textContent = "⏸️ השהה";
  } else {
    await fetch("/api/pause", { method: "POST" });
    _paused = true;
    btn.textContent = "▶️ המשך";
  }
}

function _renderHistoryRows(rows, emptyMessage) {
  const container = document.getElementById("historyList");
  container.innerHTML = "";
  if (!rows.length) { container.innerHTML = `<div class='hist-row'>${uiEscape(emptyMessage)}</div>`; return; }
  for (const r of rows) {
    const div = document.createElement("div"); div.className = "hist-row";
    const icon = document.createElement("span");
    icon.className = r.status === "success" ? "ok" : "fail";
    icon.textContent = r.status === "success" ? "✅" : "❌";
    const small = document.createElement("small");
    small.textContent = r.summary || r.started_at;
    div.append(icon, " " + r.script, document.createElement("br"), small);
    container.appendChild(div);
  }
}

async function loadHistory() {
  const res = await fetch("/api/history");
  const rows = await res.json();
  _renderHistoryRows(rows, "עוד לא בוצעו ריצות.");
}

let _historySearchDebounce = null;
function onHistorySearchInput() {
  // דיבאונס קטן (250ms) - בלי זה כל הקשת מקש הייתה שולחת בקשת רשת נפרדת.
  clearTimeout(_historySearchDebounce);
  _historySearchDebounce = setTimeout(searchHistory, 250);
}

async function searchHistory() {
  const q = document.getElementById("historySearch").value.trim();
  if (!q) { loadHistory(); return; }
  const res = await fetch("/api/history/search?q=" + encodeURIComponent(q));
  const rows = await res.json();
  _renderHistoryRows(rows, "לא נמצאו ריצות תואמות.");
}

async function checkUndoStatus() {
  const res = await fetch("/api/undo/status");
  const data = await res.json();
  document.getElementById("undoLastMoveBtn").hidden = !data.pending;
}

async function undoLastMoveBatch() {
  const res = await fetch("/api/undo/last_move_batch", { method: "POST" });
  const data = await res.json();
  if (data.error) {
    alert(data.error);
  } else {
    alert(`↩️ הוחזרו ${data.restored} קבצים למקורם (${data.skipped} דולגו)`);
  }
  await checkUndoStatus();
}

// item: log spam - ריצה ארוכה (רינדור ffmpeg על תיקייה שלמה) יכולה להזרים
// אלפי שורות; בלי תקרה כל שורה נשארת ב-DOM לצמיתות ומכבידה על הדפדפן/המחשב.
// שני תנאים משלימים - מה שמוחק יותר קובע: חלון-זמן (30 דקות אחורה) לריצה
// רגילה, ותקרת-מספר-שורות כרשת ביטחון נגד הרבה שורות אמיתיות (לא רק tqdm)
// בפרק זמן קצר. ההיסטוריה המלאה תמיד נשארת ב-data/logs/script_runs.log
// בצד השרת (utils/worker.py) - זו רק תקרה על מה שמוצג *כרגע* בדפדפן.
const CONSOLE_LOG_RETENTION_MS = 30 * 60 * 1000;
const CONSOLE_LOG_MAX_LINES = 4000;
let _consoleEntries = [];

function appendLog(line, tag) {
  appendLogBatch([{line, tag}]);
}

// item: log spam - הודעה אחת עם N שורות (מ-ws.onmessage, "log_batch") מוכנסת
// ב-DOM operation *אחת* (DocumentFragment + appendChild יחיד + scrollTop יחיד),
// לא N קריאות appendChild/reflow נפרדות - זה מה שבפועל מונע קפיאה כשמגיע פרץ
// גדול של שורות אמיתיות (לא רק tqdm, שכבר סוננו בצד השרת), לא רק כמות הטקסט.
function appendLogBatch(lines) {
  if (!lines.length) return;
  _veRecordLogTail(lines);  // item 49: זנב-לוג מסונן בתוך פאנל העורך
  const c = document.getElementById("console");
  const frag = document.createDocumentFragment();
  const now = Date.now();
  for (const {line, tag} of lines) {
    const span = document.createElement("span");
    if (tag === "red") span.className = "red";
    span.textContent = line;
    frag.appendChild(span);
    _consoleEntries.push({el: span, time: now});
  }
  c.appendChild(frag);
  c.scrollTop = c.scrollHeight;
  _pruneConsoleLog();
}

function _pruneConsoleLog() {
  // Array.shift() בלולאה הוא O(n) *לכל* הסרה (שאר האיברים זזים) - O(n²) סה"כ
  // כשצריך להסיר הרבה בבת אחת (למשל אחרי הודעת log_batch ענקית) - נמדד בפועל
  // כמה שניות של הקפאה על ~4500 הסרות. splice() יחיד על כל הטווח בבת אחת
  // (item: log spam) הוא O(n) פעם אחת, לא O(n) פעם לכל איבר.
  const cutoff = Date.now() - CONSOLE_LOG_RETENTION_MS;
  const excess = _consoleEntries.length - CONSOLE_LOG_MAX_LINES;
  let removeCount = 0;
  while (removeCount < _consoleEntries.length && (_consoleEntries[removeCount].time < cutoff || removeCount < excess)) {
    removeCount++;
  }
  if (removeCount === 0) return;
  for (const entry of _consoleEntries.splice(0, removeCount)) entry.el.remove();
}

function connectWs() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === "log_batch") appendLogBatch(msg.lines);
    else if (msg.type === "progress") {
      document.getElementById("progressBar").style.width = msg.pct + "%";
      document.getElementById("pctLabel").textContent = msg.pct + "%" + (msg.eta && msg.pct < 100 ? ` · נותרו כ-${msg.eta}` : "");
      // item: התקדמות חיה בתוך עורך-העל - אותה הודעת /ws בדיוק (לא ערוץ נפרד),
      // מוצגת גם בפס-הפעולות הצף כשהפאנל גלוי, כדי שלא צריך לגלול לטאב הלוג.
      // item 47: + התקדמות פר-קובץ (msg.files = {קובץ: אחוז}) בפס הצף.
      _veUpdateFileProgress(msg.files, msg.pct, msg.eta);
      document.dispatchEvent(new CustomEvent("cf-progress", { detail: msg }));
    } else if (msg.type === "finished") {
      document.dispatchEvent(new CustomEvent("cf-finished", { detail: msg }));
      state.running = false;
      document.getElementById("runBtn").disabled = false;
      document.getElementById("stopBtn").disabled = true;
      const pauseBtn = document.getElementById("pauseBtn");
      pauseBtn.disabled = true;
      pauseBtn.textContent = "⏸️ השהה";
      _paused = false;
      updateRunEnabled();
      appendLog("\n" + (msg.success ? "✅ הסתיים בהצלחה!" : "❌ נכשל.") + "\n", msg.success ? null : "red");
      loadHistory();
      notifyJobFinished(msg.success);
      if (msg.shutdown_seconds) _showShutdownBanner(msg.shutdown_seconds);
      if (typeof _veOnRunFinished === "function") _veOnRunFinished(msg);
      document.getElementById("veStickyProgress").hidden = true;
      _veFileProgress = {};
      // item 48: פאנל תוצאות בסוף ריצה של עורך-העל (manifest שהסקריפט כתב).
      if (msg.result && msg.result.manifest_path && (state.veLastRunScript || "").endsWith("video_editor.py")) {
        openVeResults(msg.result.manifest_path);
      }
      // item: פער CLI→Web (--preview-only) - ה-contact-sheet מוצג מיד בסיום, לא
      // רק נתיב בלוג שצריך לחפש ולפתוח ידנית.
      if (msg.success && msg.result && msg.result.preview_path) {
        showVeImageResult(msg.result.preview_path, `🖼️ תצוגה מקדימה - ${msg.result.videos_found ?? "?"} סרטונים נמצאו`);
      }
    }
  };
  ws.onclose = () => setTimeout(connectWs, 1500);
}

// --- כיבוי אוטומטי (מצב לילה, ראו /api/settings/global) ---
let _shutdownTimer = null;

function _showShutdownBanner(seconds) {
  const banner = document.getElementById("shutdownBanner");
  const text = document.getElementById("shutdownBannerText");
  let remaining = seconds;
  banner.hidden = false;
  if (_shutdownTimer) clearInterval(_shutdownTimer);
  const tick = () => { text.textContent = `💤 מצב לילה: הריצה הסתיימה בהצלחה, המחשב יכבה בעוד ${remaining} שניות.`; };
  tick();
  _shutdownTimer = setInterval(() => {
    remaining -= 1;
    if (remaining <= 0) { clearInterval(_shutdownTimer); banner.hidden = true; return; }
    tick();
  }, 1000);
}

async function cancelShutdown() {
  if (_shutdownTimer) { clearInterval(_shutdownTimer); _shutdownTimer = null; }
  document.getElementById("shutdownBanner").hidden = true;
  await fetch("/api/cancel_shutdown", { method: "POST" });
}

// --- בדיקת עדכון גרסה (GitHub Releases, ראו utils/update_checker.py) ---
async function checkForUpdate() {
  try {
    const res = await fetch("/api/update_check");
    const data = await res.json();
    document.getElementById("rotateTokenBtn").hidden = data.can_rotate_token === false;   // רק במחשב עצמו (22.10.2026)
    if (!data.latest_version) return;
    document.getElementById("updateBannerText").textContent =
      `🔔 גרסה חדשה זמינה: ${data.latest_version} (המותקנת: ${data.current_version})`;
    document.getElementById("updateBannerOpenBtn").onclick = () => window.open(data.releases_url, "_blank");
    document.getElementById("updateApplyBtn").hidden = !!data.portable;   // חבילה ניידת: מורידים מה-Release, אין git pull
    document.getElementById("updateBanner").hidden = false;
  } catch (e) {
    // בדיקה לא-קריטית ברקע - כשל רשת פשוט לא מציג באנר, בלי alert מפחיד.
  }
}

// item: true auto-update - git pull --ff-only + uv sync (utils/update_checker.apply_update),
// זהה ל-gui_manager.pyw's _do_apply_update. אישור מפורש (confirm) לפני שליחה -
// לעולם לא רץ אוטומטית.
async function applyUpdate() {
  if (!(await veConfirm('זה ירוץ "git pull" ואז "uv sync" על תיקיית הפרויקט בשרת. ממשיכים?', {okLabel: "עדכן"}))) return;
  const status = document.getElementById("updateApplyStatus");
  status.textContent = "מריץ git pull + uv sync...";
  try {
    const res = await fetch("/api/update_check/apply", { method: "POST" });
    const data = await res.json();
    status.textContent = (data.ok ? "✅ " : "❌ ") + (data.message || data.error || "");
  } catch (e) {
    status.textContent = "❌ " + e.message;
  }
}

async function loadLockStatus() {
  // מציג רק כשהמנעול תפוס. 30.10.2026: כשהוא משתחרר, ההודעה הכללית חוזרת (קודם "רינדור אחר תפוס" נשאר עד רענון)
  const el = document.getElementById("lockStatus");
  if (!el.dataset.idle) el.dataset.idle = el.textContent;   // לפני ה-await: עוד בעברית, המתרגם מתרגם כשהיא חוזרת
  try {
    const res = await fetch("/api/lock_status");
    const data = await res.json();
    if (!data.locked) {
      if (el.textContent !== el.dataset.idle) el.textContent = el.dataset.idle;
      return;
    }
    const queueSuffix = data.queue_length ? ` · עוד ${data.queue_length} בתור` : "";
    const age = typeof data.age_seconds === "number" ? _formatDuration(data.age_seconds) : data.age;
    el.textContent = data.is_stale
      ? `⚠️ מנעול רינדור תקוע (PID ${data.pid}, ${age}) - ישוחרר אוטומטית בניסיון הבא`
      : `🔒 רינדור אחר תפוס כרגע (PID ${data.pid}, ${age}) - הרצה מכאן תמתין${queueSuffix}`;
  } catch (e) { /* לא קריטי - רק תצוגה */ }
}

function _formatDuration(seconds) {
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  return `${(seconds / 60).toFixed(1)}m`;
}

async function openStats() {
  const list = document.getElementById("statsList");
  uiSkeleton(list, 4, "row");
  try {
    const res = await fetch("/api/render_stats");
    const rows = await res.json();
    list.innerHTML = "";
    if (!rows.length) {
      list.innerHTML = '<div class="empty-msg">עוד לא בוצעו ריצות מוצלחות.</div>';
    } else {
      for (const row of rows) {
        const div = document.createElement("div");
        div.className = "stats-row";
        const scriptSpan = document.createElement("span");
        scriptSpan.className = "script";
        scriptSpan.textContent = row.script;
        const metaSpan = document.createElement("span");
        metaSpan.className = "meta";
        metaSpan.textContent = `${_formatDuration(row.avg_seconds)} · ${row.run_count} ריצות`;
        div.appendChild(scriptSpan);
        div.appendChild(metaSpan);
        list.appendChild(div);
      }
    }
  } catch (e) {
    list.innerHTML = '<div class="empty-msg bad">שגיאה בטעינת הסטטיסטיקות.</div>';
  }
  document.getElementById("statsModalBg").classList.add("show");
  await loadHwaccelSavings();
  await loadHardwareHistoryGraph();
  await loadGamePlaytime();
  await loadClipsHistoryGraph();
}

async function loadGamePlaytime() {
  // item: personal stats dashboard - נצבר מ-gui_manager.pyw's game_loop
  // (utils/game_playtime.py), לא כאן; זה רק קורא ומציג את המצטבר.
  const el = document.getElementById("gamePlaytimeList");
  uiSkeleton(el, 2, "line");
  try {
    const res = await fetch("/api/game_playtime");
    const rows = await res.json();
    if (!rows.length) {
      el.textContent = "עוד לא נרשם זמן משחק.";
      return;
    }
    el.replaceChildren(...rows.flatMap((r, i) => [...(i ? [document.createElement("br")] : []), `${r.game}: ${r.hours.toFixed(1)} שעות`]));
  } catch (e) {
    el.textContent = "שגיאה בטעינת נתוני משחק.";
  }
}

async function loadClipsHistoryGraph() {
  // זהה בעיקרון ל-loadHardwareHistoryGraph למעלה - עמודות (לא קווים), יום
  // ליחידה, גובה יחסי למקסימום בטווח המוצג (זהה ל-ui/stats_tab.py's
  // _draw_clips_captured_graph).
  const canvas = document.getElementById("clipsHistoryCanvas");
  const ctx = canvas.getContext("2d");
  const width = canvas.width, height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  try {
    const res = await fetch("/api/clips_captured_by_day?days=30");
    const data = await res.json();
    const counts = data.counts;
    if (!counts.length) return;
    const maxCount = Math.max(...counts, 1);
    const barWidth = width / counts.length;
    ctx.fillStyle = "#00e5ff";
    counts.forEach((count, i) => {
      const barHeight = (count / maxCount) * height;
      ctx.fillRect(i * barWidth + 1, height - barHeight, Math.max(1, barWidth - 2), barHeight);
    });
  } catch (e) { /* לא קריטי - רק תצוגה */ }
}

async function loadHwaccelSavings() {
  const el = document.getElementById("hwaccelSavings");
  el.textContent = "";
  try {
    const res = await fetch("/api/hwaccel_savings");
    const data = await res.json();
    if (!data) return;  // אין עדיין מספיק היסטוריה (חסרה קבוצה עם/בלי --hwaccel) להשוואה
    const direction = data.percent_faster >= 0 ? "מהיר יותר" : "איטי יותר";
    el.textContent = `⚡ --hwaccel ב-video_editor.py: ${Math.abs(data.percent_faster).toFixed(0)}% ${direction} בממוצע ` +
      `(${data.hwaccel_avg_seconds_per_file.toFixed(1)}s/קובץ, ${data.hwaccel_run_count} ריצות ` +
      `לעומת ${data.no_hwaccel_avg_seconds_per_file.toFixed(1)}s/קובץ, ${data.no_hwaccel_run_count} ריצות בלי)`;
  } catch (e) { /* לא קריטי - רק תצוגה */ }
}

function closeStats() { document.getElementById("statsModalBg").classList.remove("show"); }

async function loadHardwareHistoryGraph() {
  // זהה בעיקרון ל-ui/stats_tab.py's _draw_hardware_history_graph - אותו רעיון
  // (קו לכל סדרה, מנורמל 0-100), רק ב-canvas 2D של הדפדפן במקום Tk Canvas.
  const canvas = document.getElementById("hwHistoryCanvas");
  const ctx = canvas.getContext("2d");
  const width = canvas.width, height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  try {
    const res = await fetch("/api/hardware_history?hours=24");
    const data = await res.json();
    const plot = (history, color) => {
      const n = history.length;
      if (n < 2) return;
      const step = width / (n - 1);
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      history.forEach((v, i) => {
        const x = i * step;
        const y = height - (Math.min(100, Math.max(0, v)) / 100.0 * height);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
    };
    plot(data.cpu, "#00e5ff");
    plot(data.ram, "#ff007f");
    // gpu יכול לכלול null לדגימות בלי GPU של NVIDIA זמין - קו GPU רק אם *כל*
    // הדגימות כוללות ערך אמיתי (בדיוק כמו ui/stats_tab.py).
    if (data.gpu.length && data.gpu.every(v => v !== null)) plot(data.gpu, "#7c4dff");
  } catch (e) { /* לא קריטי - רק תצוגה */ }
}

async function openDiagnostics() {
  const list = document.getElementById("diagnosticsList");
  uiSkeleton(list, 4, "row");
  document.getElementById("diagnosticsModalBg").classList.add("show");
  loadCredentialRotationStatus();
  try {
    const res = await fetch("/api/diagnostics");
    const rows = await res.json();
    list.innerHTML = "";
    for (const row of rows) {
      const div = document.createElement("div");
      div.className = "stats-row";
      const nameSpan = document.createElement("span");
      nameSpan.className = "script";
      nameSpan.textContent = (row.ok ? "✅ " : "❌ ") + row.name;
      const detailSpan = document.createElement("span");
      detailSpan.className = "meta";
      detailSpan.textContent = row.detail;
      div.appendChild(nameSpan);
      div.appendChild(detailSpan);
      list.appendChild(div);
    }
  } catch (e) {
    list.innerHTML = '<div class="empty-msg bad">שגיאה בהרצת האבחון.</div>';
  }
}

function closeDiagnostics() { document.getElementById("diagnosticsModalBg").classList.remove("show"); }

async function checkCredentialValidity() {
  const el = document.getElementById("credentialValidityResult");
  el.innerHTML = "בודק...";
  try {
    const res = await fetch("/api/credentials/check_validity", { method: "POST" });
    const rows = await res.json();
    el.innerHTML = "";
    for (const row of rows) {
      const div = document.createElement("div");
      div.className = "stats-row";
      let icon = "➖", text = "לא מוגדר";
      if (row.configured) {
        icon = row.valid ? "✅" : "❌";
        text = row.detail;
      }
      // פרטי השגיאה מגיעים מ-Gemini/Twitch/Discord - טקסט חיצוני
      div.innerHTML = `<span class="script">${uiEscape(icon)} ${uiEscape(row.name)}</span><span class="meta">${uiEscape(text)}</span>`;
      el.appendChild(div);
    }
  } catch (e) {
    el.innerHTML = '<div class="empty-msg bad">שגיאה בבדיקת התוקף.</div>';
  }
}

// item: key-age tracking - גיל כל credential (utils/credential_rotation.py),
// בלי שום קריאת רשת (בניגוד ל-checkCredentialValidity), אז נטען אוטומטית
// בכל פתיחת הדיאלוג, לא רק על-פי-בקשה כמו בדיקת התוקף.
async function loadCredentialRotationStatus() {
  const el = document.getElementById("credentialRotationList");
  uiSkeleton(el, 3, "row");
  try {
    const res = await fetch("/api/credentials/rotation_status");
    const rows = await res.json();
    el.innerHTML = "";
    for (const row of rows) {
      let ageText;
      if (!row.configured) ageText = "לא מוגדר";
      else if (row.age_days === null) ageText = "גיל לא ידוע (הוגדר ידנית ב-.env, לא דרך הכספת)";
      else ageText = `${row.stale ? "⚠️ " : ""}${row.age_days} ימים מאז הסבב האחרון`;

      // גל 22: DOM במקום HTML עם שמות בתוך onclick="...('${name}')" - בלי הזרקה דרך מרכאות
      const div = document.createElement("div");
      div.className = "stats-row credential-row";
      const nameEl = document.createElement("span");
      nameEl.className = "script";
      nameEl.textContent = row.name;
      const age = document.createElement("span");
      age.className = "meta" + (row.stale ? " is-stale" : "");
      age.textContent = ageText;
      const actions = document.createElement("div");
      actions.className = "credential-actions";
      const input = document.createElement("input");
      input.type = "password";
      input.id = `rotateInput_${row.name}`;
      input.placeholder = "ערך חדש...";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn-sm";
      button.textContent = "🔄 סבב";
      button.addEventListener("click", () => rotateCredential(row.name));
      actions.append(input, button);
      div.append(nameEl, age, actions);
      el.appendChild(div);
    }
  } catch (e) {
    el.innerHTML = '<div class="empty-msg bad">שגיאה בטעינת גיל המפתחות.</div>';
  }
}

async function rotateCredential(name) {
  const input = document.getElementById(`rotateInput_${name}`);
  const value = input.value;
  if (!value) { alert("הזן ערך חדש קודם."); return; }
  try {
    const res = await fetch("/api/credentials/rotate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, value }),
    });
    const data = await res.json();
    if (!res.ok || data.error) { alert(data.error || "סבב ה-credential נכשל."); return; }
    input.value = "";
    await loadCredentialRotationStatus();
  } catch (e) {
    alert("סבב ה-credential נכשל: " + e.message);
  }
}

// --- פלטת פקודות (Ctrl+K) - זהה ל-ui/widgets.py's CommandPalette ---
function openCommandPalette() {
  document.getElementById("paletteInput").value = "";
  _renderPaletteList("");
  document.getElementById("paletteModalBg").classList.add("show");
  document.getElementById("paletteInput").focus();
}

function closeCommandPalette() { document.getElementById("paletteModalBg").classList.remove("show"); }


document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    openCommandPalette();
  }
});

function openSettingsModal() {
  document.getElementById("settingsImportFile").value = "";
  document.getElementById("settingsModalBg").classList.add("show");
  loadBackupList();
}

function closeSettingsModal() { document.getElementById("settingsModalBg").classList.remove("show"); }

async function importSettings() {
  const fileInput = document.getElementById("settingsImportFile");
  const file = fileInput.files[0];
  if (!file) { alert("בחר קודם קובץ JSON לייבוא."); return; }
  if (!(await veConfirm("לייבא את ההגדרות מהקובץ הזה? ההגדרות הנוכחיות יגובו ל-config.json.bak, אבל השינוי בפועל דורס אותן.", {danger: true, okLabel: "ייבא"}))) return;

  let payload;
  try {
    payload = JSON.parse(await file.text());
  } catch (e) {
    alert("הקובץ שנבחר אינו JSON תקין.");
    return;
  }

  try {
    const resp = await fetch("/api/settings/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "ייבוא נכשל");
    alert("ההגדרות יובאו בהצלחה. הפעל מחדש את ה-GUI/הבוט כדי שהשינוי ייכנס לתוקף.");
    closeSettingsModal();
  } catch (e) {
    alert("ייבוא ההגדרות נכשל: " + e.message);
  }
}

function _formatBackupSize(bytes) {
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

async function loadBackupList() {
  const list = document.getElementById("backupList");
  const resp = await fetch("/api/backup/list");
  const backups = await resp.json();
  if (!backups.length) {
    list.innerHTML = '<div class="hint">אין עדיין גיבויים מוצפנים.</div>';
    return;
  }
  // גל 22: שם הקובץ כטקסט ו-handler אמיתי - לא בתוך onclick="...('${name}')"
  list.replaceChildren(...backups.map(b => {
    const row = document.createElement("div");
    row.className = "backup-row";
    const name = document.createElement("span");
    name.className = "backup-name";
    name.textContent = b.filename;
    const size = document.createElement("span");
    size.className = "hint backup-size";
    size.textContent = _formatBackupSize(b.size_bytes);
    const download = document.createElement("a");
    download.className = "btn-sm";
    download.href = "/api/backup/download/" + encodeURIComponent(b.filename);
    download.download = b.filename;
    download.textContent = "⬇️";
    download.title = "הורדה";
    const restore = document.createElement("button");
    restore.type = "button";
    restore.textContent = "♻️ שחזר";
    restore.addEventListener("click", () => restoreEncryptedBackup(b.filename));
    row.append(name, size, download, restore);
    return row;
  }));
}

async function createEncryptedBackup() {
  const passphraseInput = document.getElementById("backupPassphrase");
  const passphrase = passphraseInput.value;
  if (!passphrase) { alert("הזן סיסמה לגיבוי המוצפן."); return; }

  try {
    const resp = await fetch("/api/backup/create_encrypted", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passphrase }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "יצירת הגיבוי נכשלה");
    passphraseInput.value = "";
    await loadBackupList();
    alert(`הגיבוי המוצפן נוצר: ${data.filename} (${data.included_files.length} קבצים)`);
  } catch (e) {
    alert("יצירת הגיבוי המוצפן נכשלה: " + e.message);
  }
}

async function restoreEncryptedBackup(filename) {
  if (!(await veConfirm(`לשחזר את הגיבוי "${filename}"? כל קובץ קיים שיידרס יגובה קודם ל-.bak, אבל מומלץ לעצור את הבוט/ה-GUI לפני שחזור.`, {danger: true, okLabel: "שחזר"}))) return;
  const passphrase = await vePrompt("הזן את הסיסמה של הגיבוי הזה:", {type: "password"});
  if (!passphrase) return;

  try {
    const resp = await fetch("/api/backup/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passphrase, filename }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "שחזור הגיבוי נכשל");
    alert(`שוחזרו ${data.restored_files.length} קבצים. הפעל מחדש את ה-GUI/הבוט כדי שהשינוי ייכנס לתוקף.`);
  } catch (e) {
    alert("שחזור הגיבוי נכשל: " + e.message);
  }
}

async function loadQueueStatus() {
  // מוצג רק כשיש בפועל משהו בתור (למשל ה-GUI השולחני או הבוט דחפו משימות) -
  // אותו worker.pending_counts_by_lane() בדיוק כמו queue_label ב-ui/dashboard.py.
  try {
    const res = await fetch("/api/queue_status");
    const data = await res.json();
    const el = document.getElementById("queueStatus");
    if (!data.pending) { el.hidden = true; return; }
    el.hidden = false;
    el.textContent = `🗂️ ${data.pending} בתור (${data.light} קל, ${data.heavy} כבד)`;
  } catch (e) { /* לא קריטי - רק תצוגה */ }
}

async function loadHardwareStats() {
  // אותו utils/hardware.py בדיוק כמו הסיידבר השולחני - כדי שממשק הדפדפן לא
  // יישאר "עיוור" למה שקורה בפועל על המחשב תוך כדי רינדור.
  try {
    const res = await fetch("/api/hardware_stats");
    const data = await res.json();
    document.getElementById("hwCpuText").textContent = data.cpu != null ? data.cpu.toFixed(0) + "%" : "-";
    document.getElementById("hwCpuBar").style.width = (data.cpu || 0) + "%";
    document.getElementById("hwRamText").textContent = data.ram != null ? data.ram.toFixed(0) + "%" : "-";
    document.getElementById("hwRamBar").style.width = (data.ram || 0) + "%";
    document.getElementById("hwGpuText").textContent = data.gpu != null ? data.gpu.toFixed(0) + "%" : "לא זמין";
    document.getElementById("hwGpuBar").style.width = (data.gpu || 0) + "%";
    document.getElementById("hwVramText").textContent = data.vram != null ? data.vram.toFixed(0) + "%" : "-";
    document.getElementById("hwVramBar").style.width = (data.vram || 0) + "%";
    document.getElementById("hwEncoderText").textContent = data.encoder != null ? data.encoder.toFixed(0) + "%" : "-";
    document.getElementById("hwEncoderBar").style.width = (data.encoder || 0) + "%";
  } catch (e) { /* לא קריטי - רק תצוגה */ }
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  document.getElementById("themeToggle").textContent = {light: "☀️", contrast: "🌓"}[theme] || "🌙";
}

function toggleTheme() {
  // per-viewer בלבד (localStorage) - לא הגדרת שרת, כל דפדפן/מכשיר בוחר לעצמו.
  // גל 21: setUiTheme (69-ui-prefs.js) שומר ומחיל, כולל "אוטומטי" וניגודיות גבוהה.
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  setUiTheme(current === "light" ? "dark" : "light");
}

async function rotateToken() {
  // מבטל כל קישור/עוגייה ישנים מיד - שימושי אם הקישור עם הטוקן דלף (למשל
  // הועתק בטעות, נראה בצילום מסך). הטאב הזה עצמו ממשיך לעבוד כרגיל (מקבל
  // עוגייה מעודכנת בתגובה עצמה) - אין צורך לרענן או להתחבר מחדש.
  if (!(await veConfirm("להחליף את טוקן הגישה? כל קישור/עוגייה ישנים (כולל בטאבים/מכשירים אחרים) יפסיקו לעבוד מיד.", {danger: true, okLabel: "החלף טוקן"}))) return;
  try {
    const resp = await fetch("/api/rotate_token", { method: "POST" });
    if (!resp.ok) throw new Error("rotate failed");
    alert("הטוקן הוחלף בהצלחה. אם היה לך קישור שמור (בזיכרון/מסמך אחר), צריך להחליף אותו - הטאב הזה כבר מעודכן.");
  } catch (e) {
    alert("החלפת הטוקן נכשלה: " + e);
  }
}

let notifyEnabled = false;
try { notifyEnabled = localStorage.getItem("web_app_notify") === "1"; } catch (e) { /* לא קריטי */ }

function updateNotifyBtn() {
  const btn = document.getElementById("notifyBtn");
  if (!("Notification" in window)) { btn.hidden = true; return; }
  // btn.disabled מוגדר במפורש בכל מסלול (לא רק ב-"denied") - בלי זה, אם
  // permission עובר בחזרה ל-"default"/"granted" תוך כדי session (למשל אחרי
  // שינוי ידני בהגדרות האתר של הדפדפן, בלי רענון עמוד), הכפתור היה נשאר
  // disabled לצמיתות מפעם הראשונה שהיה "denied".
  btn.disabled = Notification.permission === "denied";
  const isActive = Notification.permission === "granted" && notifyEnabled;
  btn.classList.toggle("active", isActive);
  if (Notification.permission === "denied") {
    btn.textContent = "🔕 התראות חסומות (בהגדרות הדפדפן)";
  } else if (isActive) {
    btn.textContent = "🔔 התראות פעילות";
  } else {
    btn.textContent = "🔔 הפעל התראות";
  }
}

async function toggleNotifications() {
  // בקשת הרשאה מהדפדפן חייבת לקרות בתגובה ישירה ללחיצת משתמש (לא אוטומטית
  // בטעינת הדף) - זו בדיוק הסיבה שזה כפתור מפורש ולא הרשאה שמתבקשת מיד.
  if (!("Notification" in window) || Notification.permission === "denied") return;
  if (Notification.permission !== "granted") {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") { updateNotifyBtn(); return; }
  }
  notifyEnabled = !notifyEnabled;
  try { localStorage.setItem("web_app_notify", notifyEnabled ? "1" : "0"); } catch (e) { /* לא קריטי */ }
  updateNotifyBtn();
}

// מרכז ההתראות (23.10.2026): בדף הראשי רק המונה; הרשימה נטענת בלחיצה (LAZY_JS["notifications"], 34-notification-center.js)
async function refreshNotificationBadge() {
  try {
    const data = await (await fetch("/api/notifications/unread")).json();
    const badge = document.getElementById("notifBadge");
    badge.textContent = data.unread > 99 ? "99+" : String(data.unread);
    badge.hidden = !data.unread;
  } catch (e) {
    // רק המונה - מתעדכן בפעם הבאה
  }
}

function toggleNotificationCenter(open) {
  uiLoadLazy("notifications").then(() => toggleNotificationPanel(open)).catch((e) => uiToast(e.message, "warn"));
}

document.addEventListener("cf-finished", refreshNotificationBadge);   // השרת רושם את ההתראה לפני שהוא מודיע על הסיום

function notifyJobFinished(success) {
  // רק כשהטאב הזה לא פעיל כרגע (document.hidden) - אם המשתמש כבר מסתכל
  // עליו, הלוג בעמוד עצמו כבר מציג את התוצאה, אין טעם לכפול עם התראה.
  if (!notifyEnabled || !("Notification" in window) || Notification.permission !== "granted" || !document.hidden) return;
  const scriptName = state.scripts.find(s => s.id === state.selectedId)?.name || "";
  const title = success ? "✅ ClipForge - הריצה הסתיימה בהצלחה" : "❌ ClipForge - הריצה נכשלה";
  new Notification(uiTranslate(title) || title, {
    body: scriptName,
  });
}

// --- מעבר בין טאבים עליונים (סקריפטים/בוט/...) ---
let _botWsConnected = false;

// polling קבוע שמשתתק כשהלשונית מוסתרת (חומרה/תור/נעילה/בוט כל 2-5 שניות בלי סוף = רעש ב-API ובמעבד) וקורא מיד כשחוזרים אליה
function pollWhenVisible(fn, ms) {
  setInterval(() => { if (!document.hidden) fn(); }, ms);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) fn(); });
}

function switchTab(name) {
  if (document.getElementById("tourCard")) endUiTour();   // מעבר מסך סוגר את הסיור (68-ui-polish.js) - הכרטיס נשאר מעל המסך החדש
  document.querySelectorAll("[data-tab-panel]").forEach(el => { el.hidden = el.dataset.tabPanel !== name; });
  document.querySelectorAll(".tab-btn").forEach(el => el.classList.toggle("active", el.dataset.tab === name));
  if (name === "bot") {
    loadBotStatus();
    refreshRssList();
    refreshSteamList();
    if (!_botWsConnected) { _botWsConnected = true; connectBotWs(); }
  } else if (name === "globalsettings") {
    uiLoadLazy("settings").then(() => { loadGlobalSettings(); loadStyleSettings(); });   // 31-global-settings.js - רק כשפותחים את המסך
  } else if (name === "phone") {
    uiLoadLazy("phone").then(() => loadPhoneScreen()).catch((e) => uiToast(e.message, "warn"));   // 36-phone-screen.js
  } else if (name === "scheduler") {
    populateSchedulerScriptDropdown();
    updateSchedulerFieldVisibility();
    refreshSchedulerTaskList();
  } else if (name === "rocket") {
    loadRocketSettings();
  } else if (name === "gallery") {
    loadGallery();
    loadYoutubeAnalytics();
  } else if (name === "approvals") {
    loadApprovals();
    uiLoadLazy("dataviz").then(() => uiLoadLazy("dataviz_pro")).then(() => uiLoadLazy("dataviz_tools")).then(() => uiLoadLazy("dataviz_plus")).then(() => loadDatavizPackages()).catch((e) => uiToast(e.message, "warn"));  // גל 38: נטען לפי דרישה (גל 50: שני bundles)
  } else if (name === "dataviz") {
    uiLoadLazy("dataviz").then(() => uiLoadLazy("dataviz_pro")).then(() => uiLoadLazy("dataviz_tools")).then(() => uiLoadLazy("dataviz_plus")).then(() => loadDataviz()).catch((e) => uiToast(e.message, "warn"));  // 20.10.2026: שלושה bundles (23.10.2026: ה-.catch היה בתוך ההערה)
  } else if (name === "archive") {
    renderArchiveList();
  } else if (name === "outputs") {
    uiLoadLazy("outputs").then(() => loadOutputs()).catch((e) => uiToast(e.message, "warn"));   // 33-outputs-screen.js
  }
}

