// ============================================================================
// גל 7א של 102-ההצעות: עריכה ותוכן (items 69-78, 83-84, 86, 89)
// ============================================================================

const VE_WAVE7_FIELDS = {
  aspect: {id: "veAspect", kind: "str", label: "יחס-רוחב"},
  custom_width: {id: "veCustomWidth", kind: "int", label: "רוחב מותאם"},
  custom_height: {id: "veCustomHeight", kind: "int", label: "גובה מותאם"},
  fit: {id: "veFit", kind: "str", label: "התאמה למסגרת"},
  pad_color: {id: "vePadColor", kind: "str", label: "צבע שוליים"},
  dual_output: {id: "veDualOutput", kind: "bool", label: "פלט כפול"},
  rotate: {id: "veRotate", kind: "int", label: "סיבוב"},
  flip: {id: "veFlip", kind: "str", label: "מראה"},
  watermark_position_vertical: {id: "veWatermarkPositionVertical", kind: "str", label: "מיקום watermark באנכי"},
  lut_intensity: {id: "veLutIntensity", kind: "float", label: "עוצמת LUT"},
  eq_brightness: {id: "veEqBrightness", kind: "float", label: "בהירות"},
  eq_contrast: {id: "veEqContrast", kind: "float", label: "ניגודיות"},
  eq_saturation: {id: "veEqSaturation", kind: "float", label: "רוויה"},
  eq_gamma: {id: "veEqGamma", kind: "float", label: "גמא"},
  denoise_level: {id: "veDenoiseLevel", kind: "str", label: "עוצמת הפחתת רעש"},
  sharpen_level: {id: "veSharpenLevel", kind: "str", label: "עוצמת חידוד"},
  tonemap: {id: "veTonemap", kind: "str", label: "Tone-mapping"},
  speed: {id: "veSpeed", kind: "float", label: "מהירות"},
  deinterlace: {id: "veDeinterlace", kind: "bool", label: "Deinterlace"},
  audio_track: {id: "veAudioTrack", kind: "int", label: "ערוץ שמע"},
  caption_style: {id: "veCaptionStyle", kind: "str", label: "עיצוב כתוביות"},
  captions_language: {id: "veCaptionsLanguage", kind: "str", label: "שפת תמלול"},
  captions_model: {id: "veCaptionsModel", kind: "str", label: "מודל Whisper"},
  captions_export: {id: "veCaptionsExport", kind: "str", label: "ייצוא קובץ כתוביות"},
  captions_no_burn: {id: "veCaptionsNoBurn", kind: "bool", label: "ייצוא כתוביות בלבד"},
  crf: {id: "veCrf", kind: "int", label: "איכות H.264 (CRF)"},
  resolution: {id: "veResolution", kind: "str", label: "רזולוציית פלט"},
  scale_algo: {id: "veScaleAlgo", kind: "str", label: "אלגוריתם שינוי גודל"},
};
Object.assign(VE_GENERIC_FIELDS, VE_WAVE7_FIELDS);
for (const [key, meta] of Object.entries(VE_WAVE7_FIELDS)) {
  VE_FAVORITABLE_FIELDS[key] = {id: meta.id, label: meta.label};
}

const _veValue = (id) => (document.getElementById(id) || {}).value || "";
Object.assign(VE_DEPENDENT_FIELDS, {
  veCustomWidth: () => _veValue("veAspect") === "custom",
  vePadColor: () => _veValue("veFit") !== "crop",
  veWatermarkPositionVertical: () => _veHasText("veWatermarkPath") && (_veIsChecked("veVertical") || _veIsChecked("veDualOutput")),
  veLutIntensity: () => _veHasText("veLutPath"),
  veDenoiseLevel: () => _veIsChecked("veDenoise"),
  veSharpenLevel: () => _veIsChecked("veSharpen"),
  veCaptionStyle: () => _veIsChecked("veCaptions"),
  veCaptionsLanguage: () => _veIsChecked("veCaptions"),
  veCaptionsExport: () => _veIsChecked("veCaptions"),
});

const _veNum = (value, fallback) => (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) ? fallback : Number(value);
const _veEqActive = (o) => Math.abs(_veNum(o.eq_brightness, 0)) > 0.001 || Math.abs(_veNum(o.eq_contrast, 1) - 1) > 0.001
  || Math.abs(_veNum(o.eq_saturation, 1) - 1) > 0.001 || Math.abs(_veNum(o.eq_gamma, 1) - 1) > 0.001;
const _veSpeedActive = (o) => Math.abs(_veNum(o.speed, 1) - 1) > 0.001;
VE_RULES.push(
  {cats: ["format"], field: "aspect", when: o => ["16:9", "9:16"].includes(o.aspect) && (o.aspect === "9:16") !== !!o.vertical && !o.dual_output, msg: 'יחס-הרוחב שנבחר גובר על תיבת "פורמט אנכי".', level: "info"},
  {cats: ["format"], field: "dual_output", when: o => o.dual_output && !!o.aspect, msg: "פלט כפול מפיק תמיד 16:9 וגם 9:16 - יחס-הרוחב שנבחר יתעלם."},
  {cats: ["format"], field: "custom_width", when: o => o.aspect === "custom" && !(o.custom_width && o.custom_height), msg: "יחס-רוחב מותאם דורש רוחב וגובה - בלעדיהם הפלט יישאר 16:9/9:16."},
  {cats: ["format", "resources"], field: "rotate", when: o => (o.rotate || o.flip && o.flip !== "none" || o.deinterlace || _veEqActive(o)) && _veHwFull(o), msg: "סיבוב/מראה/deinterlace/תיקון צבע עם פייפליין GPU מלא - מצב היברידי: פענוח, סיבוב, deinterlace והקטנה נשארים על ה-GPU, ורק שאר הסינון רץ ב-CPU על פריים קטן.", level: "info"},
  {cats: ["format", "resources"], field: "aspect", when: o => (!!o.aspect && !["16:9", "9:16"].includes(o.aspect) || ["crop", "pad"].includes(o.fit)) && _veHwFull(o), msg: "יחס-רוחב/fit מותאם עם פייפליין GPU מלא - הסינון יעבור ל-CPU.", level: "info"},
  {cats: ["format"], field: "smart_crop", when: o => o.smart_crop && [90, 270].includes(Number(o.rotate)), msg: "קרופ חכם לא נתמך עם סיבוב 90/270 - יתעלם (קרופ מרכזי)."},
  {cats: ["format", "export"], field: "resolution", when: o => o.resolution && o.resolution !== "auto" && o.preserve_resolution, msg: "רזולוציית פלט קבועה גוברת על שימור רזולוציית המקור.", level: "info"},
  {cats: ["motion", "trim"], field: "speed", when: o => _veSpeedActive(o) && (o.target_seconds || 0) > 0, msg: "שינוי מהירות מתעלם כשיש טיימלאפס (אורך יעד) - הטיימלאפס קובע את המהירות."},
  {cats: ["export"], field: "crf", when: o => o.crf !== null && o.crf !== undefined && o.codec === "h264" && !!o.target_size_mb, msg: "איכות CRF מתעלמת כשיש יעד גודל קובץ."},
  {cats: ["captions"], field: "captions_no_burn", when: o => o.captions_no_burn && !o.captions_export, msg: '"ייצוא בלבד" דורש לבחור פורמט ייצוא (SRT/VTT) - אחרת הכתוביות נשרפות כרגיל.'},
  {cats: ["captions"], field: "caption_style", when: o => o.captions && o.caption_style === "karaoke" && o.captions_translate, msg: "קריוקי עם תרגום לאנגלית - התזמון המילולי מגיע מהתרגום של Whisper ועלול להיות פחות מדויק.", level: "info"},
  {cats: ["color"], field: "tonemap", when: o => o.tonemap && o.tonemap !== "hable", msg: "Tone-mapping חל רק על מקורות HDR - בקבצי SDR אין לו השפעה.", level: "info"},
);

const VE_ASPECT_CHIPS = {"16:9": "🖥️ 16:9", "9:16": "📱 9:16", "1:1": "⬛ 1:1", "4:5": "🖼️ 4:5", "4:3": "📺 4:3"};
const _veBuildSummaryChipsBeforeWave7 = _veBuildSummaryChips;
_veBuildSummaryChips = function (o) {
  const chips = _veBuildSummaryChipsBeforeWave7(o);
  const orientationIndex = chips.findIndex(c => c === "📱 אנכי 9:16" || c === "🖥️ אופקי 16:9");
  let orientation = null;
  if (o.dual_output) orientation = "🔀 16:9 + 9:16";
  else if (o.aspect === "custom" && o.custom_width && o.custom_height) orientation = `📐 ${o.custom_width}×${o.custom_height}`;
  else if (VE_ASPECT_CHIPS[o.aspect]) orientation = VE_ASPECT_CHIPS[o.aspect];
  if (orientation && orientationIndex >= 0) chips[orientationIndex] = orientation;
  const extra = [];
  if (o.fit === "pad") extra.push("▭ שוליים"); else if (o.fit === "crop") extra.push("✂️ חיתוך למסגרת");
  if (o.resolution && o.resolution !== "auto") extra.push(`📏 ${o.resolution}`);
  if (Number(o.rotate)) extra.push(`↻ ${o.rotate}°`);
  if (o.flip && o.flip !== "none") extra.push("↔ מראה");
  if (_veSpeedActive(o)) extra.push(`⚡ x${_veNum(o.speed, 1)}`);
  if (o.deinterlace) extra.push("deinterlace");
  if (_veEqActive(o)) extra.push("🎚️ תיקון צבע");
  if ((o.lut_path || "").trim() && _veNum(o.lut_intensity, 1) < 0.999) extra.push(`🎨 LUT ${Math.round(_veNum(o.lut_intensity, 1) * 100)}%`);
  if (o.codec === "h264" && o.crf !== null && o.crf !== undefined) extra.push(`CRF ${o.crf}`);
  if (o.audio_track !== null && o.audio_track !== undefined) extra.push(`🔊 ערוץ ${o.audio_track}`);
  if (o.captions && o.keep_audio) {
    if (o.caption_style && o.caption_style !== "classic") extra.push(`💬 ${_veSelectText("veCaptionStyle")}`);
    if (o.captions_export) extra.push(`📄 ${o.captions_export === "both" ? "SRT+VTT" : o.captions_export.toUpperCase()}${o.captions_no_burn ? " בלבד" : ""}`);
  }
  const countIndex = chips.findIndex(c => c.startsWith("📁 "));
  chips.splice(countIndex >= 0 ? countIndex : chips.length, 0, ...extra);
  return chips;
};

// --- item 70: עורך תמלול לפני שריפה ---
let _veTranscriptJob = null;

function _veTranscriptSourcePath() {
  const name = _veValue("veTranscriptFile");
  return name ? _veFolderPath(name) : "";
}

function _veSyncTranscriptFiles() {
  const source = document.getElementById("vePreviewFile");
  const target = document.getElementById("veTranscriptFile");
  if (!source || !target) return;
  const previous = target.value;
  target.innerHTML = source.innerHTML;
  if ([...target.options].some(o => o.value === previous)) target.value = previous;
}

const _vePopulatePreviewFilesBeforeWave7 = _vePopulatePreviewFiles;
_vePopulatePreviewFiles = async function () {
  await _vePopulatePreviewFilesBeforeWave7();
  _veSyncTranscriptFiles();
};

function _veTranscriptStatus(text) {
  document.getElementById("veTranscriptStatus").textContent = text;
}

function _veSecondsToSrtClock(value) {
  const total = Math.max(0, Number(value) || 0);
  const h = Math.floor(total / 3600), m = Math.floor(total % 3600 / 60), sec = total % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${sec.toFixed(2).padStart(5, "0")}`;
}

function _veTranscriptRowEl(seg) {
  const row = document.createElement("div");
  row.className = "ve-transcript-row";
  const start = document.createElement("input");
  start.className = "ve-tr-start"; start.value = _veSecondsToSrtClock(seg.start); start.setAttribute("aria-label", "התחלה");
  const end = document.createElement("input");
  end.className = "ve-tr-end"; end.value = _veSecondsToSrtClock(seg.end); end.setAttribute("aria-label", "סיום");
  const text = document.createElement("input");
  text.className = "ve-tr-text"; text.value = seg.text || ""; text.setAttribute("aria-label", "טקסט");
  const remove = document.createElement("button");
  remove.type = "button"; remove.textContent = "✕"; remove.title = "מחק שורה";
  remove.onclick = () => row.remove();
  row.append(start, end, text, remove);
  return row;
}

function _veRenderTranscript(segments) {
  const box = document.getElementById("veTranscriptRows");
  box.innerHTML = "";
  for (const seg of segments) box.appendChild(_veTranscriptRowEl(seg));
  document.getElementById("veTranscriptEditor").hidden = false;
}

function addVeTranscriptRow() {
  const rows = [...document.querySelectorAll("#veTranscriptRows .ve-transcript-row")];
  const last = rows.length ? _veParseTimeText(rows[rows.length - 1].querySelector(".ve-tr-end").value) || 0 : 0;
  const row = _veTranscriptRowEl({start: last, end: last + 2, text: ""});
  document.getElementById("veTranscriptRows").appendChild(row);
  document.getElementById("veTranscriptEditor").hidden = false;
  row.querySelector(".ve-tr-text").focus();
}

// "00:01:02.50" / "1:02.5" / "62.5" -> שניות (null על טקסט לא תקין)
function _veParseTimeText(text) {
  const clean = String(text || "").trim().replace(",", ".");
  if (!clean) return null;
  const parts = clean.split(":");
  if (parts.length > 3 || parts.some(p => p === "" || isNaN(Number(p)))) return null;
  return parts.reduce((acc, p) => acc * 60 + Number(p), 0);
}

function _veCollectTranscript() {
  const segments = [];
  for (const row of document.querySelectorAll("#veTranscriptRows .ve-transcript-row")) {
    const text = row.querySelector(".ve-tr-text").value.trim();
    if (!text) continue;
    const start = _veParseTimeText(row.querySelector(".ve-tr-start").value);
    const end = _veParseTimeText(row.querySelector(".ve-tr-end").value);
    row.classList.toggle("ve-invalid", start === null || end === null || end <= start);
    segments.push({start, end, text});
  }
  return segments;
}

async function startVeTranscription() {
  const path = _veTranscriptSourcePath();
  if (!path) { _veTranscriptStatus("בחר קובץ קודם (טען תיקייה/תור)."); return; }
  _veTranscriptStatus("🎙️ מתמלל... (עשוי לקחת דקה-שתיים)");
  const res = await fetch("/api/video_editor/transcribe", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({path, language: _veValue("veCaptionsLanguage"), model: _veValue("veCaptionsModel") || "small"})});
  const data = await res.json();
  if (!res.ok) { _veTranscriptStatus("⚠️ " + (data.error || "התמלול נכשל")); return; }
  _veTranscriptJob = data.job_id;
  _vePollTranscription(data.job_id);
}

async function _vePollTranscription(jobId) {
  if (jobId !== _veTranscriptJob) return;
  const data = await (await fetch("/api/video_editor/transcribe_status?job_id=" + encodeURIComponent(jobId))).json();
  if (data.status === "running") { setTimeout(() => _vePollTranscription(jobId), 1500); return; }
  _veTranscriptJob = null;
  if (data.status === "error") { _veTranscriptStatus("⚠️ התמלול נכשל: " + data.error); return; }
  _veRenderTranscript(data.segments || []);
  _veTranscriptStatus(`✅ ${(data.segments || []).length} שורות - ערוך ושמור.`);
}

async function loadVeEditedTranscript() {
  const path = _veTranscriptSourcePath();
  if (!path) { _veTranscriptStatus("בחר קובץ קודם."); return; }
  const res = await fetch("/api/video_editor/captions_edit?path=" + encodeURIComponent(path));
  const data = await res.json();
  if (!res.ok) { _veTranscriptStatus("⚠️ " + (data.error || "הטעינה נכשלה")); return; }
  if (!data.exists) { _veTranscriptStatus("אין עדיין תמלול ערוך לקובץ הזה."); return; }
  _veRenderTranscript(data.segments);
  _veTranscriptStatus(`📂 נטען תמלול ערוך (${data.segments.length} שורות).`);
}

async function saveVeEditedTranscript() {
  const path = _veTranscriptSourcePath();
  const segments = _veCollectTranscript();
  if (document.querySelector("#veTranscriptRows .ve-invalid")) { _veTranscriptStatus("⚠️ יש שורות עם זמן לא תקין (מסומנות באדום)."); return; }
  const res = await fetch("/api/video_editor/captions_edit", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({path, segments})});
  const data = await res.json();
  _veTranscriptStatus(res.ok ? `💾 נשמר (${data.count} שורות) - ייעשה בו שימוש בריצה הבאה.` : "⚠️ " + (data.error || "השמירה נכשלה"));
}

async function deleteVeEditedTranscript() {
  const path = _veTranscriptSourcePath();
  if (!path || !(await veConfirm("למחוק את התמלול הערוך של הקובץ הזה? בריצה הבאה Whisper יתמלל מחדש.", {danger: true, okLabel: "מחק"}))) return;
  const res = await fetch("/api/video_editor/captions_edit?path=" + encodeURIComponent(path), {method: "DELETE"});
  const data = await res.json();
  document.getElementById("veTranscriptRows").innerHTML = "";
  document.getElementById("veTranscriptEditor").hidden = true;
  _veTranscriptStatus(data.deleted ? "🗑️ התמלול הערוך נמחק." : "לא היה תמלול ערוך.");
}

