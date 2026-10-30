// ============================================================================
// גל 31 - נוחות:
//  * לפני/אחרי בנגן החי: קו נגרר - משמאל המקור בלי הצבע והמראה, מימין התוצאה.
//  * מפת קיצורים אחת (?) שנבנית מרשימה אחת, וקיצורי הנגן (רווח, J/K/L, I/O, Delete) בכל העורך -
//    לא רק כשציר-הזמן בפוקוס (למשל אחרי לחיצה בעורך השכבות או בעקומות).
//  * Ctrl+K שמבצע: "קודק hevc", "מהירות 1.5", "הוסף לוגו", "מראה קולנועי", "יעד tiktok".
// ============================================================================

// --- לפני/אחרי בנגן החי ---
// הקנבס מצייר את פריים המקור (drawImage מתעלם מ-filter של ה-CSS) מעל הווידאו, חתוך עד הקו
let _veLiveCompareRaf = null;

function toggleVeLiveCompare(force) {
  const on = typeof force === "boolean" ? force : !_veStage().classList.contains("ve-live-compare");
  _veStage().classList.toggle("ve-live-compare", on);
  _veEl("veLiveCompareBtn").setAttribute("aria-pressed", String(on));
  _veEl("veLiveBefore").hidden = !on;
  cancelAnimationFrame(_veLiveCompareRaf);
  if (on) _veDrawLiveBefore();
}

function _veDrawLiveBefore() {
  const canvas = _veEl("veLiveBefore"), video = _veEl("veLiveVideo");
  if (canvas.hidden) return;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (w && h && video.videoWidth) {
    const ratio = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(w * ratio)) { canvas.width = Math.round(w * ratio); canvas.height = Math.round(h * ratio); }
    const ctx = canvas.getContext("2d");
    const scaleX = canvas.width / video.videoWidth, scaleY = canvas.height / video.videoHeight;
    const scale = video.style.objectFit === "cover" ? Math.max(scaleX, scaleY) : Math.min(scaleX, scaleY);
    const dw = video.videoWidth * scale, dh = video.videoHeight * scale;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    try { ctx.drawImage(video, (canvas.width - dw) / 2, (canvas.height - dh) / 2, dw, dh); } catch (e) { /* פריים לא מוכן */ }
  }
  _veLiveCompareRaf = requestAnimationFrame(_veDrawLiveBefore);
}

// --- מפת קיצורים: רשימה אחת, ממנה נבנית החלונית ---
const VE_SHORTCUTS = [
  ["כללי", "Ctrl+Enter", "הרץ (קודם הגיליון \"לפני הרצה\")"],
  ["כללי", "Ctrl+S", "שמור את הסגנון - עדכן את הנבחר או שמור כחדש"],
  ["כללי", "Ctrl+Z / Ctrl+Y", "בטל / בצע שוב - בכל העורך, גם בעורך השכבות ובעקומות"],
  ["כללי", "Ctrl+K", "לוח פקודות - חיפוש וגם ביצוע: \"קודק hevc\", \"מהירות 1.5\", \"הוסף לוגו\""],
  ["כללי", "/", "חיפוש הגדרה"],
  ["כללי", "?", "מפת הקיצורים הזו"],
  ["כללי", "Esc", "סגירת תפריט או חלון, ניקוי חיפוש או בחירה"],
  ["נגן וציר-זמן", "רווח", "נגן / השהה"],
  ["נגן וציר-זמן", "J / K / L", "אחורה / עצור / קדימה (לחיצה חוזרת על L מאיצה)"],
  ["נגן וציר-זמן", "I / O", "התחלת / סוף החיתוך בנקודה הנוכחית"],
  ["נגן וציר-זמן", "← / →", "פריים אחורה / קדימה (בציר-הזמן); עם Shift - שנייה"],
  ["נגן וציר-זמן", "Home / End", "לתחילת / סוף החיתוך"],
  ["נגן וציר-זמן", "+ / -", "זום בציר-הזמן (או Ctrl+גלגלת)"],
  ["עריכה", "Delete", "מחיקת השכבה שנבחרה"],
  ["עריכה", "גרירה בעכבר", "הזזת שכבה או טווח בציר; הקצוות משנים אורך"],
  ["עריכה", "Alt+גרירה", "בלי הצמדה"],
  ["עריכה", "Shift+גרירה", "סימון טווח להסרה בציר-הזמן"],
  ["עריכה", "לחיצה כפולה", "על טווח להסרה - מחיקה"],
  ["עריכה", "חיצים", "על ידית בנגן: הזזה עדינה, עם Shift קפיצה. בשדה זמן: עשירית שנייה, עם Shift שנייה שלמה"],
  ["עריכה", "Alt+↑ / ↓", "הזזת אזור הגדרות (כשהכותרת שלו בפוקוס)"],
  ["אזורים", "F6 / Shift+F6", "מעבר לאזור הבא / הקודם במסך"],
  ["אזורים", "Alt+1 / Alt+2 / Alt+3 / Alt+4", "קבצים / נגן / הגדרות / הפס העליון"],
];

function _veRenderShortcuts() {
  const box = _veEl("veShortcutsList");
  if (box.childElementCount) return;
  let group = null, table = null;
  for (const [section, keys, label] of VE_SHORTCUTS) {
    if (section !== group) {
      group = section;
      const title = document.createElement("div");
      title.className = "ve-subcat-title";
      title.textContent = section;
      table = document.createElement("table");
      table.className = "ve-shortcuts-table";
      box.append(title, table);
    }
    const row = table.insertRow();
    const keyCell = row.insertCell(), labelCell = row.insertCell();
    _veShortcutKeysFor(keys).split(" / ").forEach((combo, i) => {  // גל 34: קיצור ששונה מוצג בצירוף החדש
      if (i) keyCell.append(" / ");
      combo.split("+").forEach((part, j) => {
        if (j) keyCell.append("+");
        const kbd = document.createElement("kbd");
        kbd.textContent = part;
        keyCell.appendChild(kbd);
      });
    });
    labelCell.textContent = label;
    _veShortcutRowExtras(row, keys);  // גל 34: ✎ לשינוי הקיצור
  }
}

// הזמן הנוכחי במקור: הנגן החי אם הוא פתוח, אחרת סמן ציר-הזמן
function _veCurrentSourceTime() {
  if (_veInLiveMode()) return _veEl("veLiveVideo").currentTime;
  return _veTimelineCursor ?? 0;
}

function _veSetTrimAt(which) {
  const t = _veCurrentSourceTime();
  if (_veTimeline) { _veApplyTrimEdge(which, t); _veRenderTimelineOverlays(); return; }
  const start = _veTimeValue("veTrimStart", 0);
  if (which === "start") _veSetFieldValue(_veEl("veTrimStart"), String(Math.round(t * 10) / 10));
  else if (t > start) _veSetFieldValue(_veEl("veTrimDuration"), String(Math.round((t - start) * 10) / 10));
}

// קיצורי הנגן בכל העורך - כשלא מקלידים, אין חלון פתוח, ואף רכיב לא טיפל במקש (ציר-הזמן מטפל בעצמו)
document.addEventListener("keydown", (e) => {
  if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || !_veIsActive() || _veIsTyping() || document.querySelector(".modal-bg.show")) return;
  const key = e.key.toLowerCase();
  const onControl = !!(document.activeElement && document.activeElement.closest("button, summary, a, [role=button], [role=tab], input[type=checkbox], input[type=radio]"));
  if (key === " ") {
    if (onControl) return;
    if (_veInLiveMode()) toggleVeLivePlay(); else if (_veEl("vePreviewFile").value) startVeLivePreview(); else return;
  } else if (key === "j") _veLivePlayRate(-1);
  else if (key === "l") _veLivePlayRate(1);
  else if (key === "k") { if (_veInLiveMode()) _veEl("veLiveVideo").pause(); }
  else if (key === "i") _veSetTrimAt("start");
  else if (key === "o") _veSetTrimAt("end");
  else if ((e.key === "Delete" || e.key === "Backspace") && _veSelected && _veSelected.kind === "layer" && !onControl) deleteVeLayer(_veSelected.index);
  else return;
  e.preventDefault();
});

// --- Ctrl+K שמבצע ---
const VE_PALETTE_ADD = [
  [["לוגו", "logo", "watermark"], () => addVeLayerCard("logo")],
  [["טקסט", "text", "כותרת"], () => addVeLayer("text")],
  [["תמונה", "מדבקה", "image", "sticker"], () => addVeLayer("image")],
  [["b-roll", "broll", "וידאו", "קליפ", "video"], () => addVeLayer("video")],
  [["טיימר", "timer"], () => addVeLayer("timer")],
  [["חותמת", "חותמת-זמן", "timestamp"], () => addVeLayer("timestamp")],
  [["pip"], () => addVeLayerCard("pip")],
  [["סרגל", "progress"], () => addVeLayerCard("progress")],
  [["מסגרת", "frame"], () => addVeLayerCard("frame")],
];
const _veNorm = (text) => String(text || "").toLowerCase().replace(/[()"'״׳:=]/g, " ").replace(/[_-]/g, " ").replace(/\s+/g, " ").trim();

function _vePaletteFields() {
  const fields = {...VE_GENERIC_FIELDS, ...VE_FAVORITABLE_FIELDS};
  // שדות נסתרים/JSON (יעדים, שכבות, טווחים) נערכים בכלים משלהם - לא "שם ערך"
  return Object.entries(fields).filter(([, meta]) => meta && meta.id && meta.label && meta.kind !== "json" && _veEl(meta.id) && _veEl(meta.id).type !== "hidden");
}

function _veFindField(name) {
  const q = _veNorm(name);
  if (q.length < 2) return null;
  let best = null;
  for (const [key, meta] of _vePaletteFields()) {
    const label = _veNorm(meta.label);
    const score = _veNorm(key) === q ? 4 : label === q ? 3 : label.startsWith(q) ? 2 : (q.length >= 3 && label.includes(q)) ? 1 : 0;
    if (score && (!best || score > best.score || (score === best.score && label.length < _veNorm(best.meta.label).length))) best = {key, meta, score};
  }
  return best;
}

// ערך מהטקסט לפי סוג השדה (null = לא מתאים לשדה הזה)
function _veParseFieldValue(el, raw) {
  const v = _veNorm(raw);
  if (el.type === "checkbox") {
    if (["on", "true", "1", "כן", "הפעל", "דלוק", "פעיל"].includes(v)) return true;
    if (["off", "false", "0", "לא", "כבה", "כבוי"].includes(v)) return false;
    return null;
  }
  if (el.tagName === "SELECT") {
    const options = [...el.options];
    const option = options.find(o => _veNorm(o.value) === v) || options.find(o => _veNorm(o.textContent).includes(v));
    return option ? option.value : null;
  }
  if (el.type === "range" || el.type === "number") {
    const number = parseFloat(String(raw).replace(",", "."));
    if (!Number.isFinite(number)) return null;
    const min = el.min === "" ? -Infinity : parseFloat(el.min), max = el.max === "" ? Infinity : parseFloat(el.max);
    return number >= min && number <= max ? String(number) : null;
  }
  return String(raw).trim() || null;
}

function _veSetFieldFromPalette(meta, value) {
  const el = _veEl(meta.id);
  if (_veClipModeRefuses(meta.label)) return;
  if (el.type === "checkbox") { el.checked = value; el.dispatchEvent(new Event("change", {bubbles: true})); }
  else _veSetFieldValue(el, value);
  uiToast(`✓ ${meta.label}: ${el.type === "checkbox" ? (value ? "פעיל" : "כבוי") : el.tagName === "SELECT" ? el.selectedOptions[0].textContent : value}`, "ok");
}

function _vePaletteCommands(query) {
  const q = String(query || "").trim();
  if (!q) return [];
  const out = [];
  const add = (label, run) => out.push({section: "⚡ ביצוע", label, run});
  const verb = /^(הוסף|add|מראה|look|יעד|target)\s+(.+)$/i.exec(q);
  if (verb) {
    const [, word, rest] = verb;
    const what = _veNorm(rest);
    if (/^(הוסף|add)$/i.test(word)) {
      for (const [names, run] of VE_PALETTE_ADD) if (names.some(n => n.startsWith(what) || what.startsWith(n))) add(`➕ הוסף · ${names[0]}`, run);
    } else if (/^(מראה|look)$/i.test(word)) {
      for (const look of VE_LOOKS) if (_veNorm(look.label).startsWith(what) || look.id.startsWith(what)) add(`🎨 מראה · ${look.label}`, () => applyVeLook(look.id));
    } else {
      for (const [id, target] of Object.entries((_veSchema || {}).targets || {})) {
        if (_veNorm(target.label).includes(what) || id.startsWith(what)) add(`🎯 יעד · ${target.label}`, () => { if (!_veTargets().includes(id)) _veSetTargets([..._veTargets(), id]); });
      }
    }
  }
  // "<הגדרה> <ערך>" - כל חלוקה של הטקסט לשם ולערך (הערך = המילים האחרונות)
  const words = q.split(/\s+/);
  for (let cut = words.length - 1; cut >= 1; cut--) {
    const found = _veFindField(words.slice(0, cut).join(" "));
    if (!found) continue;
    const value = _veParseFieldValue(_veEl(found.meta.id), words.slice(cut).join(" "));
    if (value === null) continue;
    const el = _veEl(found.meta.id);
    const shown = el.type === "checkbox" ? (value ? "פעיל" : "כבוי") : el.tagName === "SELECT" ? [...el.options].find(o => o.value === value).textContent : value;
    add(`⚡ ${found.meta.label} ← ${shown}`, () => _veSetFieldFromPalette(found.meta, value));
    break;
  }
  return out;
}

// --- מסך מחשב נייד: פאנלי הצד מתקפלים לפס אייקונים, והנגן מקבל את המקום ---
// בכל גודל אפשר לכווץ; במסך נייד (פחות מ-1440 רוחב או מ-800 גובה, למשל 1366×768) רשימת הקבצים
// מתחילה מכווצת.
function _veIsLaptop() { return window.innerWidth < 1440 || window.innerHeight < 800; }

function _veRailOn(panel) {
  const saved = _veLoadPref("veRail_" + panel, null);
  if (saved !== null) return !!saved;
  return panel === "queue" && _veIsLaptop();
}

function setVePanelRail(panel, on) {
  _veSavePref("veRail_" + panel, !!on);
  _veApplyRails();
}

function _veApplyRails() {
  document.body.classList.toggle("ve-laptop", _veIsLaptop());
  // במסך נייד כותרת התצוגה המקדימה מוסתרת (עוד גובה לנגן) - אז הפאנל תמיד פתוח
  if (_veIsLaptop()) document.querySelector('#veViewer details[data-cat="preview"]').open = true;
  const root = _veEl("videoEditorOptions");
  root.classList.toggle("ve-queue-rail", _veRailOn("queue"));
  root.classList.toggle("ve-inspector-rail", _veRailOn("inspector"));
  _veRenderInspectorRail();
  _veRenderQueueRailCount();
  if (typeof _vePlaceResizers === "function") _vePlaceResizers();
  _veScheduleLiveRebuild();
}

// פס ההגדרות: אייקון לכל אזור - לחיצה פותחת את הפאנל באותו אזור
function _veRenderInspectorRail() {
  const rail = _veEl("veInspectorRail");
  if (!_veEl("videoEditorOptions").classList.contains("ve-inspector-rail")) { rail.replaceChildren(); return; }
  rail.replaceChildren(...[...document.querySelectorAll("#veCategories > details.ve-category")].filter(d => d.dataset.cat !== "queue").map(details => {
    const title = details.querySelector(".ve-cat-title").textContent.trim();
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ve-rail-btn";
    button.dataset.cat = details.dataset.cat;
    button.textContent = title.split(" ")[0];
    button.title = title;
    button.setAttribute("aria-label", title);
    button.onclick = () => { setVePanelRail("inspector", false); veScrollToCategory(details.dataset.cat); };
    return button;
  }));
}

function _veRenderQueueRailCount() {
  const badge = _veEl("veRailQueueCount");
  const count = (_veQueueState || []).length;
  badge.textContent = count ? String(count) : "";
  badge.hidden = !count;
}

// --- מצב ריק מועיל בכל פאנל ---
function _veEmptyState(icon, title, text, actions) {
  const box = _uiEmpty(icon, title, text);
  box.classList.add("ve-empty");
  if (actions && actions.length) {
    const row = document.createElement("div");
    row.className = "ve-empty-actions";
    for (const [label, run] of actions) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = row.childElementCount ? "btn-sm" : "btn-sm ve-primary";  // הפעולה הראשונה היא הראשית
      button.textContent = label;
      button.onclick = run;
      row.appendChild(button);
    }
    box.appendChild(row);
  }
  return box;
}

function _veQueueEmptyState() {
  if (!state.folder) return _veEmptyState("📁", "עוד לא נבחרה תיקייה", "בחר תיקייה עם סרטונים - או גרור לכאן קבצי וידאו מהמחשב", [["📂 בחר תיקייה...", () => openBrowser()]]);
  if (_veFolderCounts && !_veFolderCounts.files) return _veEmptyState("🎬", "אין כאן קבצי וידאו", "גרור לכאן קבצי וידאו מהמחשב - הם יועתקו לתיקייה", [["🔄 רענן", () => refreshVeQueue()]]);
  return _veEmptyState("🎬", "הקבצים עוד לא נטענו", "רענן כדי לראות את הקבצים - או גרור לכאן קבצי וידאו מהמחשב", [["🔄 רענן", () => refreshVeQueue()]]);
}

function _veLayersEmptyState() {
  const actions = [["🔤 טקסט", () => addVeLayer("text")], ["🖼️ תמונה", () => addVeLayer("image")], ["🏷️ לוגו", () => addVeLayerCard("logo")]];
  const templates = _veEl("veBrandTemplate");
  if (templates && templates.options.length && !templates.closest("[hidden]")) actions.push(["📑 שכבה מוכנה", () => _veRevealElement(templates) && templates.focus()]);
  return _veEmptyState("🧩", "עוד אין שכבות", "גרור תמונה לכאן, לנגן או לציר-הזמן - או בחר שכבה מוכנה", actions);
}

// תמונה שנגררה לרשימת השכבות = שכבת תמונה (כמו בנגן, בלי מיקום)
function _veSetupLayersListDrop() {
  const box = _veEl("veLayersList");
  box.addEventListener("dragover", (e) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    box.classList.add("ve-drop-target");
  });
  box.addEventListener("dragleave", (e) => { if (!box.contains(e.relatedTarget)) box.classList.remove("ve-drop-target"); });
  box.addEventListener("drop", async (e) => {
    box.classList.remove("ve-drop-target");
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!file) return;
    e.preventDefault();
    if (!VE_IMAGE_EXT.includes(_veExtOf(file.name))) { uiToast("לרשימת השכבות אפשר לגרור תמונה", "warn"); return; }
    const path = await _veUploadAsset(file);
    if (path) { _veAddLayerAt("image", {path}); uiToast("🖼️ שכבת תמונה נוספה", "ok"); }
  });
}

function _veInitWave31() {
  _veEl("veRunSheetPref").checked = _veLoadPref("veRunSheet", true);
  _veApplyRails();
  window.addEventListener("resize", () => uiDebounce("ve:rails", _veApplyRails, 200));
  uiBus.on("ve:derived-refresh", () => _veRenderQueueRailCount());
  _veSetupLayersListDrop();
}
