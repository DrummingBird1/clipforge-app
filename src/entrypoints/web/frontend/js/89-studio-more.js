// 89-studio-more.js - תוספות לסטודיו שנטענות כשהוא נפתח (24.10.2026, LAZY_JS["studio_more"], setVeFocus ב-62-editor-studio.js):
// התיקונים מסיור השימושיות של 23.10, בלי להגדיל את הדף הראשי. כשהטעינה נכשלת הסטודיו עובד כמו קודם, וננסה שוב בפתיחה הבאה.

// --- ממצא 1: בחירת התיקייה - שדה נתיב (הדבקה ו-Enter), התיקיות האחרונות (uiRecent) ופתיחה בתיקיית האב של האחרונה ---
function _veParentPath(path) {
  const parent = String(path || "").replace(/[\\/]+$/, "").replace(/[\\/][^\\/]*$/, "");
  return /^[A-Za-z]:$/.test(parent) ? parent + "\\" : parent;
}

// נכנס לתיקייה רק אם היא קיימת - בלי ה-alert של browseTo על נתיב שגוי
async function _veBrowseIfExists(path) {
  let data;
  try { data = await (await fetch("/api/browse?path=" + encodeURIComponent(path))).json(); } catch (e) { data = {error: true}; }
  if (!path || data.error) return false;
  await browseTo(path);
  return true;
}

openBrowser = async function () {
  state.browseTarget = "folder";
  state.browseMode = "folder";
  const last = state.folder || (uiRecent.list().find((item) => item.kind === "project") || {}).id;
  if (!last || !(await _veBrowseIfExists(_veParentPath(last)))) await browseTo("");
  document.getElementById("modalBg").classList.add("show");
};

const _veBrowseToBase = browseTo;
browseTo = async function (path) {
  await _veBrowseToBase(path);
  _veRenderBrowseExtras();
};

function _veBrowseMissing(missing) {
  document.getElementById("modalPathNote").hidden = !missing;
}

function _veRenderBrowseExtras() {
  let input = document.getElementById("modalPathInput");
  if (!input) {
    input = Object.assign(document.createElement("input"), {id: "modalPathInput", type: "text", dir: "ltr", spellcheck: false, placeholder: "C:\\Videos\\Clips"});
    input.setAttribute("aria-label", "נתיב התיקייה - אפשר להדביק נתיב וללחוץ Enter");
    input.addEventListener("keydown", async (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      _veBrowseMissing(!(await _veBrowseIfExists(input.value.trim().replace(/^"(.*)"$/, "$1"))));
    });
    const note = Object.assign(document.createElement("div"), {id: "modalPathNote", className: "hint bad", hidden: true, textContent: "התיקייה לא נמצאה"});
    const recent = Object.assign(document.createElement("div"), {id: "modalRecent", className: "drives"});
    document.getElementById("modalPath").after(input, note);
    document.getElementById("modalDrives").after(recent);
  }
  document.getElementById("modalPath").hidden = true;
  input.value = state.browsePath || "";
  _veBrowseMissing(false);
  const items = state.browseTarget === "folder" ? uiRecent.list().filter((item) => item.kind === "project" && item.id !== state.folder).slice(0, 5) : [];
  const row = document.getElementById("modalRecent");
  row.hidden = !items.length;
  row.replaceChildren(...items.map((item) => {
    const button = Object.assign(document.createElement("button"), {type: "button", textContent: "🕘 " + item.label, title: item.id});
    button.onclick = async () => _veBrowseMissing(!(await _veBrowseIfExists(item.id)));
    return button;
  }));
}

// --- ממצא 7: "💾 נשמר ב-..." בגיליון "לפני הרצה" ובתוצאות, כמו בעורך הגרפים (#54). התיקייה של הסטודיו לפי /api/export_dir:
// התיקייה שלו, <תיקיית הייצוא>/studio, או workspace/studio כשהיא לא הוגדרה או לא זמינה (ואז גם אזהרה) ---
const _veOpenRunSheetBase = openVeRunSheet;
openVeRunSheet = function () {
  _veOpenRunSheetBase();
  _veFillRunSheetSavedTo();
};

function _veSavedToLine(id, after) {
  let line = document.getElementById(id);
  if (!line) {
    line = Object.assign(document.createElement("div"), {id, className: "ve-field-msg"});
    document.getElementById(after).after(line);
  }
  return line;
}

async function _veFillRunSheetSavedTo() {
  const line = _veSavedToLine("veRunSheetSavedTo", "veRunSheetFolder");
  line.replaceChildren();
  let data;
  try { data = await (await fetch("/api/export_dir")).json(); } catch (e) { return; }
  const studio = (data.tools || []).find((tool) => tool.tool === "studio") || data;
  if (!studio.effective) return;
  line.append(Object.assign(document.createElement("span"), {textContent: `💾 נשמר ב-${studio.effective}`}));
  if (studio.problem) {
    const warn = Object.assign(document.createElement("span"), {className: "bad", textContent: " ⚠️ תיקיית הייצוא לא זמינה עכשיו, אז התוצרים נשמרים ב-workspace"});
    warn.title = `${studio.problem} · ${studio.root || data.root || ""}`;
    line.append(warn);
  }
}

uiBus.on("ve:results-shown", (manifest) => {
  _veSavedToLine("veResultsSavedTo", "veResultsSummary").textContent = manifest.output_dir ? `💾 נשמר ב-${manifest.output_dir}` : "";
});

// --- פריטים 11-12 בתוכנית: המלבן המשוער של כל פריט על הפריים (שברים) - לאזור הבטוח ולאזהרת חפיפה. הלוגו ו-PiP לפי הגודל
// שלהם, שכבת טקסט לפי גודל הגופן ואורך הטקסט, ותמונה לפי הרוחב שלה (ריבוע משוער) ---
function _veTargetBox(target, size) {
  let w = 0.08, h = 0.05;
  if (target.kind === "logo") {
    const img = document.getElementById("wmPreviewImg");
    w = (parseFloat(document.getElementById("veWatermarkScale").value) || 15) / 100;
    h = w * (img && img.naturalWidth ? img.naturalHeight / img.naturalWidth : 1) * size.w / size.h;
  } else if (target.kind === "pip") {
    w = (parseFloat(document.getElementById("vePipScale").value) || 30) / 100;
    h = w * 9 / 16 * size.w / size.h;
  } else if (target.kind === "layer") {
    const layer = _veLayersValue()[target.index] || {};
    if (layer.type === "image" || layer.type === "video") {
      w = layer.scale || (layer.type === "image" ? 0.2 : 0.3);
      h = w * (layer.type === "image" ? 1 : 9 / 16) * size.w / size.h;
    } else {
      const font = layer.font_size || 48;
      w = Math.min(1, Math.max(4, (layer.text || "").trim().length) * font * 0.55 / size.w);
      h = font * 1.3 / size.h;
    }
  }
  return {kind: target.kind, label: target.label, x: target.x - w / 2, y: target.y - h / 2, w, h};
}

function _veBoxesOverlap(a, b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

function _veLogoCovers(boxes) {
  const logo = boxes.find((box) => box.kind === "logo");
  return logo ? boxes.filter((box) => box !== logo && _veBoxesOverlap(logo, box)).map((box) => box.label) : [];
}

// במקום הבדיקה לפי מרכז הידית: פריט שחלק מהמלבן שלו מתחת לממשק של הפלטפורמה, ולוגו שמכסה טקסט או שכבה
_veCheckHandlesInSafeZones = function () {
  const warn = document.getElementById("veSafeZonesWarn");
  const preset = _veActiveSafeZones();
  const size = _veOutputSize();
  const boxes = [];
  const hits = [];
  for (const handle of document.querySelectorAll("#veDragHandles .ve-drag-handle")) {
    const index = handle.dataset.index === undefined ? undefined : parseInt(handle.dataset.index, 10);
    const box = _veTargetBox({kind: handle.dataset.kind, label: handle.dataset.label, index, x: parseFloat(handle.dataset.x), y: parseFloat(handle.dataset.y)}, size);
    boxes.push(box);
    const zone = preset && preset.zones.find((z) => _veBoxesOverlap(box, z));
    handle.classList.toggle("ve-in-zone", !!zone);
    if (zone) hits.push(`${box.label} מתחת ל"${zone.label}"`);
  }
  const notes = [];
  if (hits.length) notes.push(`⚠️ ${preset.name}: ` + hits.join(" · "));
  const covered = _veLogoCovers(boxes);
  if (covered.length) notes.push(`⚠️ הלוגו מכסה: ${covered.join(", ")}`);
  if (preset) {
    const stage = _veStage();
    const w = parseFloat(stage.dataset.outputWidth) || 0, h = parseFloat(stage.dataset.outputHeight) || 0;
    if (w && h && preset.vertical !== (h > w)) notes.push(`האזורים של ${preset.name} מיועדים לפלט ${preset.vertical ? "אנכי" : "אופקי"}.`);
  }
  warn.textContent = notes.join("\n");
  warn.hidden = !notes.length;
};

// גם ברשימת האזהרות (פס הסטטוס ו"לפני הרצה") - לפי ההגדרות, בלי תלות בתצוגה
VE_RULES.push({cats: ["layers"], field: "watermark_path", msg: "הלוגו מכסה טקסט או שכבה באותו מקום - אפשר לגרור אחד מהם בתצוגה.",
  when: () => { const size = _veOutputSize(); return _veLogoCovers(_veDragTargets().map((target) => _veTargetBox(target, size))).length > 0; }});

// --- "⏭ עוד N שניות": אחרי קטע, הקטע הבא מתחיל איפה שהקודם נגמר ---
const _veShowPreviewClipBase = _veShowPreviewClip;
_veShowPreviewClip = function (data) {
  _veShowPreviewClipBase(data);
  const seconds = parseFloat(document.getElementById("vePreviewClipSeconds").value) || 5;
  let next = document.getElementById("vePreviewNextClip");
  if (!next) {
    next = Object.assign(document.createElement("button"), {type: "button", id: "vePreviewNextClip", className: "btn-sm"});
    next.onclick = () => { document.getElementById("vePreviewTime").value = next.dataset.at; refreshVePreviewClip(); };
    document.getElementById("vePreviewStatus").after(next);
  }
  next.dataset.at = String(Math.round((Number(data.time) + (Number(data.clip_seconds) || seconds)) * 100) / 100);
  next.textContent = `⏭ עוד ${seconds} שניות`;
  next.hidden = false;
};
uiBus.on("ve:folder-changed", () => {
  const next = document.getElementById("vePreviewNextClip");
  if (next) next.hidden = true;
});

// --- החלטה 3 (24.10): "🔊 הדלק" באזהרה על השמע - מדליק את "שמירת אודיו" במקום. ברירת המחדל לא משתנה. כלל עם fix מקבל כפתור
// ליד השורה שלו, ברשימת האזהרות ובגיליון "לפני הרצה" ---
const _veAudioRule = VE_RULES.find((rule) => rule.field === "keep_audio" && rule.msg.includes("שמירת אודיו"));   // לא לפי cats - VE_CAT_ALIASES משנה אותם בטעינה
if (_veAudioRule) _veAudioRule.fix = {label: "🔊 הדלק", apply: () => _applyVideoEditorFields({keep_audio: true})};

function _veAddFixButtons(box, rules) {
  [...box.children].forEach((row, index) => {
    const fix = rules[index] && rules[index].fix;
    if (!fix) return;
    const button = Object.assign(document.createElement("button"), {type: "button", className: "btn-sm", textContent: fix.label});
    button.onclick = (e) => {
      e.stopPropagation();
      fix.apply();
      if (_veEl("veRunSheetBg").classList.contains("show")) _veRenderRunSheetWarnings(_veEvaluateRules());
    };
    row.after(button);
  });
}

const _veRenderWarningsBase = _veRenderWarnings;
_veRenderWarnings = function (active) {
  _veRenderWarningsBase(active);
  _veAddFixButtons(document.getElementById("veWarningsBox"), active);
};
const _veRenderRunSheetWarningsBase = _veRenderRunSheetWarnings;
_veRenderRunSheetWarnings = function (rules) {
  _veRenderRunSheetWarningsBase(rules);
  _veAddFixButtons(_veEl("veRunSheetWarnings"), rules);
};

// --- החלטה 9 (24.10): בלשונית "✂️ זמן" ציר הזמן צמוד לתחתית העמודה האמצעית (89-studio-more.css), והנגן מקבל את הגובה שנשאר
// מעליו - הנגן, פס הנגן וציר הזמן נראים יחד בלי גלילה. בשאר הלשוניות וב"הכל ברשימה" - כמו קודם ---
function _veTimelineDocked() {
  const time = _veCategoryByKey("time");
  const dock = _veEl("veTimelineDock");
  return !!time && time.classList.contains("ve-tab-active") && _veCurrentLayout() === "tabs" && !!dock && !dock.closest("[hidden]");
}

function _veSyncTimelineDock() {
  _veEl("videoEditorOptions").classList.toggle("ve-tl-docked", _veTimelineDocked());
  _veFitTimelineDock();
  _veScheduleLiveRebuild();
}

const _veLiveRoomBase = _veLiveRoom;
_veLiveRoom = function () {
  const room = _veLiveRoomBase();
  if (!(room > 0 && _veEl("videoEditorOptions").classList.contains("ve-tl-docked"))) return room;
  _veFitTimelineDock();
  return room - _veEl("veTimelineDock").offsetHeight - 8;
};

const _veActivateTabBase = _veActivateTab;
_veActivateTab = function (key) {
  _veActivateTabBase(key);
  _veSyncTimelineDock();
};
const _veApplyLayoutBase = _veApplyLayout;
_veApplyLayout = function () {
  _veApplyLayoutBase();
  _veSyncTimelineDock();
};
uiBus.on("ve:mode-changed", _veSyncTimelineDock);
new ResizeObserver(() => { if (_veEl("videoEditorOptions").classList.contains("ve-tl-docked")) _veScheduleLiveRebuild(); }).observe(_veEl("veTimelineDock"));
_veSyncTimelineDock();

// --- החלטת LUFS (24.10): עוצמת השמע של הפלט בשורת התוצאה, רק כשהנרמול דלוק - video_editor.py שומר output_lufs מהסיכום של
// loudnorm באותו קידוד. ✓ עד 1 LU מהיעד, ⚠️ מעבר לזה ---
const _veResultCardBase = _veResultCard;
_veResultCard = function (manifest, file) {
  const card = _veResultCardBase(manifest, file);
  if (typeof file.output_lufs === "number") {
    const target = typeof file.lufs_target === "number" ? file.lufs_target : -14;
    card.querySelector(".ve-result-main .ve-field-msg").textContent += ` · ${file.output_lufs.toFixed(1)} LUFS ${Math.abs(file.output_lufs - target) <= 1 ? "✓" : "⚠️"}`;
  }
  return card;
};

// --- הערת המפנה ל-#72: גובה שגררו לציר הזמן (veTlResizer, מעל 64px) גובר על 22vh, עד גבול שמשאיר לנגן את 160px שהוא מקבל
// ממילא לכל הפחות (_veLiveStageSize). הגבול לא תלוי בגובה ציר הזמן עצמו, אז אין לולאה בין המדידה לשינוי ---
function _veFitTimelineDock() {
  const dock = _veEl("veTimelineDock");
  const dragged = (parseFloat(dock.style.getPropertyValue("--ve-tl-h")) || 64) > 64;
  const room = dragged && _veEl("videoEditorOptions").classList.contains("ve-tl-docked") ? _veLiveRoomBase() : 0;
  const value = room > 0 ? `${Math.round(Math.max(room - 160 - 8, window.innerHeight * 0.22))}px` : "";
  if (dock.style.maxHeight !== value) dock.style.maxHeight = value;
}
new MutationObserver(_veFitTimelineDock).observe(_veEl("veTimelineDock"), {attributes: true, attributeFilter: ["style"]});

// --- החלטה 12/13 (24.10): פרויקט מתבנית. תבנית = סגנון מורחב (ההגדרות, השכבות, המיתוג והיעדים, בלי הקבצים) שמסומן kind=template
// (save_template, video_editor_profiles.py). תיקייה חדשה בלי פרויקט שמור: "להתחיל מ: הפרויקט הקודם / סגנון או תבנית / ברירת
// מחדל" - ברירת המחדל כמו היום (מה שבטופס). התבניות גם ב"📋 כל הפרויקטים" ובבורר הסגנונות (📑) ---
function _veIsTemplate(name) { return _veProfileMeta(name).kind === "template"; }

async function saveVeProjectAsTemplate() {
  const name = ((await vePrompt("שם לתבנית (ההגדרות, השכבות, המיתוג והיעדים - בלי הקבצים):")) || "").trim();
  if (!name) return;
  const res = await fetch("/api/video_editor_profiles", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name, settings: _collectRunOptions(), kind: "template"})});
  if (!res.ok) { uiToast((await res.json().catch(() => ({}))).error || "שמירת התבנית נכשלה", "warn"); return; }
  await loadVideoEditorProfiles();
  uiToast(`📑 התבנית "${name}" נשמרה`, "ok");
}
(() => {
  const anchor = document.querySelector("#veViewMenu button[onclick*='veImportProjectFile']");
  const item = Object.assign(document.createElement("button"), {type: "button", textContent: "📑 שמור את הפרויקט כתבנית"});
  item.setAttribute("role", "menuitem");
  item.onclick = () => { closeVeMenus(); saveVeProjectAsTemplate(); };
  if (anchor) anchor.after(item);
})();

const _veProfileOptionLabelBase = _veProfileOptionLabel;
_veProfileOptionLabel = function (name) { return (_veIsTemplate(name) ? "📑 " : "") + _veProfileOptionLabelBase(name); };

function _veApplyStyleByName(name) {
  _veEl("vePreset").value = "profile:" + name;
  applyVideoEditorPreset();
}

function _veStartFromBar(show) {
  let bar = _veEl("veStartFromBar");
  if (!bar) {
    bar = Object.assign(document.createElement("div"), {id: "veStartFromBar", className: "ve-project-banner", hidden: true});
    bar.setAttribute("role", "status");
    const keep = Object.assign(document.createElement("button"), {type: "button", textContent: "✓ הפרויקט הקודם"});
    keep.onclick = () => { bar.hidden = true; };
    const pick = Object.assign(document.createElement("select"), {id: "veStartFromStyle"});
    pick.setAttribute("aria-label", "סגנון או תבנית");
    pick.onchange = () => { if (pick.value) { bar.hidden = true; _veApplyStyleByName(pick.value); } };
    const reset = Object.assign(document.createElement("button"), {type: "button", textContent: "↺ ברירת מחדל"});
    reset.onclick = () => {   // כמו "↺ אפס הכל" (resetVideoEditorToDefaults), בלי האישור - כאן זו הבחירה עצמה
      bar.hidden = true;
      _applyVideoEditorFields({});
      _veEl("vePreset").value = "";
      state.vePresetPrevious = "";
      state.veBaseline = null;
      updateUnsavedIndicator();
      _setVeProfileButtonsVisible(false);
      _veEl("veProfileMetaInfo").textContent = "";
    };
    bar.append(Object.assign(document.createElement("span"), {textContent: "📁 תיקייה חדשה - להתחיל מ:"}), keep, pick, reset);
    _veEl("veProjectBanner").after(bar);
  }
  if (show) {
    const names = Object.keys(state.videoEditorProfiles || {}).sort((a, b) => _veIsTemplate(b) - _veIsTemplate(a) || a.localeCompare(b, "he"));
    _veEl("veStartFromStyle").replaceChildren(new Option("סגנון או תבנית...", ""), ...names.map((name) => new Option((_veIsTemplate(name) ? "📑 " : "") + name, name)));
  }
  bar.hidden = !show;
}

const _veLoadProjectForFolderBase = _veLoadProjectForFolder;
_veLoadProjectForFolder = async function (folder) {
  await _veLoadProjectForFolderBase(folder);
  _veStartFromBar(!!folder && state.folder === folder && _veProjectSaveInfo.state === "idle");
};

const _refreshVeJobsBase = refreshVeJobs;
refreshVeJobs = async function (...args) {
  const result = await _refreshVeJobsBase(...args);
  let box = _veEl("veJobsTemplates");
  if (!box) {
    box = Object.assign(document.createElement("div"), {id: "veJobsTemplates", className: "ve-jobs-list"});
    _veEl("veJobsList").after(box);
  }
  const names = Object.keys(state.videoEditorProfiles || {}).filter(_veIsTemplate).sort((a, b) => a.localeCompare(b, "he"));
  box.hidden = !names.length;
  box.replaceChildren(Object.assign(document.createElement("div"), {className: "ve-subcat-title", textContent: "📑 תבניות"}), ...names.map((name) => {
    const row = document.createElement("div");
    row.className = "ve-field-msg";
    const use = Object.assign(document.createElement("button"), {type: "button", className: "btn-sm", textContent: "החל על הפרויקט"});
    use.onclick = () => { closeVeJobs(); _veApplyStyleByName(name); };
    row.append(Object.assign(document.createElement("span"), {textContent: "📑 " + name + " "}), use);
    return row;
  }));
  return result;
};
