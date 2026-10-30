let state = { scripts: [], selectedId: null, folder: "", running: false, browsePath: "", videoEditorPresets: {}, videoEditorProfiles: {} };

async function loadScripts() {
  const [scriptsRes, recentRes] = await Promise.all([fetch("/api/scripts"), fetch("/api/scripts/recent")]);
  state.scripts = await scriptsRes.json();
  const recentData = await recentRes.json();
  state.recentScriptNames = recentData.names || [];
  // מצב מצומצם כברירת מחדל רק אם כבר יש מועדפים - זהה ל-ui/sidebar.py's
  // load_scripts (מסך ראשוני של משתמש חדש בלי מועדפים לא היה נראה כמעט ריק).
  // מחושב פעם אחת בלבד (undefined) - רענון אחרי toggleFavorite לא ישבור מצב
  // הרחבה/כיווץ שהמשתמש כבר בחר בעצמו.
  if (state.showAllCategories === undefined) {
    state.showAllCategories = !state.scripts.some(s => s.is_favorite);
  }
  renderScripts();
}

async function loadVideoEditorPresets() {
  const res = await fetch("/api/video_editor_presets");
  state.videoEditorPresets = await res.json();
  const select = document.getElementById("vePreset");
  const builtinGroup = document.createElement("optgroup");
  builtinGroup.label = "סגנונות מובנים";
  for (const name of Object.keys(state.videoEditorPresets)) {
    const opt = document.createElement("option");
    opt.value = name; opt.textContent = name;
    builtinGroup.appendChild(opt);
  }
  select.appendChild(builtinGroup);
  await loadVideoEditorProfiles();
}

// item: פרופיל אישי - להבדיל מ-videoEditorPresets הקבועים למעלה (מוגדרים
// בקוד, utils/video_editor.py), אלה נוצרים/נמחקים ע"י המשתמש עצמו
// (data/video_editor_profiles.json), אז נטענים בנפרד וברענון עצמאי אחרי כל
// שמירה/מחיקה - לא רק פעם אחת בטעינת הדף כמו הפרופילים המובנים.
async function loadVideoEditorProfiles() {
  const [profilesRes, metaRes] = await Promise.all([fetch("/api/video_editor_profiles"), fetch("/api/video_editor_profiles_meta_all")]);
  state.videoEditorProfiles = await profilesRes.json();
  state.videoEditorProfileMeta = metaRes.ok ? (await metaRes.json()).meta : {};
  const select = document.getElementById("vePreset");
  const current = select.value;
  const oldGroup = document.getElementById("veProfilesGroup");
  if (oldGroup) oldGroup.remove();
  const group = document.createElement("optgroup");
  group.id = "veProfilesGroup";
  group.label = "הסגנונות שלי";
  // item 60/61: סינון לפי תגית + מיון (שם/בשימוש לאחרונה/הכי הרבה הרצות/נוצרו לאחרונה)
  const tagFilter = document.getElementById("veProfileTagFilter");
  const sortSelect = document.getElementById("veProfileSort");
  if (!sortSelect.dataset.restored) { sortSelect.value = _veLoadPref("veProfileSort", "name"); sortSelect.dataset.restored = "1"; }
  _veRenderProfileTagFilterOptions();
  const tag = tagFilter.value;
  const names = _veSortedProfileNames(sortSelect.value).filter(name => !tag || (_veProfileMeta(name).tags || []).includes(tag));
  for (const name of names) {
    const opt = document.createElement("option");
    opt.value = "profile:" + name;
    opt.textContent = _veProfileOptionLabel(name);
    const meta = _veProfileMeta(name);
    opt.title = [meta.tags.length ? "#" + meta.tags.join(" #") : "", meta.notes].filter(Boolean).join("\n");
    group.appendChild(opt);
  }
  select.appendChild(group);
  if (Array.from(select.options).some(o => o.value === current)) select.value = current;
  _veRenderProfileChips();
}

// value בפורמט "profile:<שם>" מבדיל פרופיל אישי (snapshot מלא, כולל
// watermark_path/opacity) מ-preset מובנה (רק vertical/target_seconds/
// keep_audio/loudnorm/codec) - שני המקורות חולקים את אותו <select> בכוונה
// (פחות בלבול למשתמש מ-2 תפריטים נפרדים), אבל applyVideoEditorPreset צריך
// להבדיל ביניהם כדי להחיל את השדות הנכונים.
function applyVideoEditorPreset() {
  const rawValue = document.getElementById("vePreset").value;
  // item: אישור לפני מעבר עם שינויים לא-שמורים - נבדק לפני שמשנים משהו
  // בפועל; אם המשתמש מבטל, מחזירים את התפריט לבחירה הקודמת.
  if (!confirmDiscardUnsavedIfNeeded()) {
    document.getElementById("vePreset").value = state.vePresetPrevious || "";
    _veAskDiscardThenApply(rawValue);
    return;
  }
  state.vePresetPrevious = rawValue;
  try { localStorage.setItem("veLastProfileValue", rawValue); } catch (e) { /* פרטי/מוגבל - לא קריטי */ }

  if (rawValue.startsWith("profile:")) {
    const name = rawValue.slice("profile:".length);
    const profile = state.videoEditorProfiles[name];
    _setVeProfileButtonsVisible(true);
    _loadAndShowProfileMeta(name);
    if (!profile) return;
    _applyVideoEditorFields(_veStyleKeepingWork(profile));
    // item 57: פרופיל שנשמר עם תור - הסדר/הסימון משוחזרים אחרי טעינת קבצי התיקייה.
    if (Array.isArray(profile.queue_files) && profile.queue_files.length && state.folder) {
      veFlow.requestQueueRestore(profile.queue_files, "profile");
      document.getElementById("veSaveQueueWithProfile").checked = true;
      refreshVeQueue().then(captureVideoEditorBaseline);
    }
    captureVideoEditorBaseline();
    return;
  }

  _setVeProfileButtonsVisible(false);
  document.getElementById("veProfileMetaInfo").textContent = "";
  state.veBaseline = null;
  updateUnsavedIndicator();
  const preset = state.videoEditorPresets[rawValue];
  if (!preset) return;  // "בחר סגנון..." הפלייסהולדר עצמו

  document.getElementById("veVertical").checked = preset.vertical;
  document.getElementById("veTargetSeconds").value = preset.target_seconds;
  document.getElementById("veKeepAudio").checked = preset.keep_audio;
  document.getElementById("veLoudnorm").checked = preset.loudnorm;
  document.getElementById("veCodec").value = preset.codec;
  syncAutoFavorites();
  updateWatermarkPreview();
}

// סגנון לא מוחק עבודה (הרצה מקצה לקצה, 16.10): קודם בחירת סגנון אישי איפסה את היעדים ואת השכבות (גם שכבות של
// קליפ אחד). השכבות שכבר יש נשארות ושל הסגנון מתווספות (בלי כפילות), והיעדים של הסגנון גוברים רק אם יש לו
function _veStyleKeepingWork(profile) {
  const layers = _veLayersValue();
  const present = new Set(layers.map(layer => JSON.stringify(layer)));
  const styleLayers = (Array.isArray(profile.layers) ? profile.layers : []).filter(layer => !present.has(JSON.stringify(layer)));
  const targets = Array.isArray(profile.targets) && profile.targets.length ? profile.targets : _veTargets();
  return {...profile, layers: [...layers, ...styleLayers], targets};
}

// item: חותמת "בשימוש לאחרונה" + מספר הרצות - שם הפרופיל האישי הנבחר כרגע
// (null אם נבחר preset קבוע, שאין לו מטא-דאטת שימוש), נשלח עם payload הריצה
// כדי ש-/api/run יוכל לעדכן record_profile_used בלי לנחש מה-URL/state נפרד.
function _currentVeProfileName() {
  const rawValue = document.getElementById("vePreset").value || "";
  return rawValue.startsWith("profile:") ? rawValue.slice("profile:".length) : null;
}

// item: שינויים לא-שמורים + אישור-מעבר - relevantת רק כשפרופיל אישי אמיתי
// נבחר כרגע (rawValue מתחיל ב-"profile:"); ל-presets קבועים אין מושג "לא-שמור".
function _isPersonalProfileSelected() {
  return (document.getElementById("vePreset").value || "").startsWith("profile:");
}

function captureVideoEditorBaseline() {
  state.veBaseline = _isPersonalProfileSelected() ? _veComparableOptionsJson() : null;
  updateUnsavedIndicator();
}

// גל 30: חלק מאינדיקטור השמירה האחד (_veRenderSaveState, 74-editor-simple.js)
function _veStyleDirty() {
  return !!state.veBaseline && _isPersonalProfileSelected() && _veComparableOptionsJson() !== state.veBaseline;
}

function updateUnsavedIndicator() {
  if (typeof _veRenderSaveState === "function") _veRenderSaveState();
}

function confirmDiscardUnsavedIfNeeded() {
  // item: תוקן תוך כדי בדיקה ידנית בדפדפן - לא בודק _isPersonalProfileSelected()
  // כאן: applyVideoEditorPreset() קורא לזה *אחרי* ש-<select>'s value כבר
  // השתנה לערך החדש (התנהגות DOM טבעית - onchange יורה אחרי שהערך כבר
  // עודכן), אז בדיקת "האם הבחירה *הנוכחית* היא פרופיל אישי" הייתה תמיד
  // שוגה - היא בודקת את היעד, לא את המקור. state.veBaseline לבדו מספיק:
  // הוא non-null אך ורק כשפרופיל אישי אמיתי נטען/נשמר (ראו captureVideoEditorBaseline),
  // ומתאפס בכל מעבר-הלאה משם - בדיוק הסמן שצריך.
  if (_veDiscardConfirmed) { _veDiscardConfirmed = false; return true; }
  if (!state.veBaseline) return true;
  return _veComparableOptionsJson() === state.veBaseline;
}

// ההגדרות כפי שהן נשמרות בפרופיל - בלי ve_profile_name, שנקרא מבורר-הפרופיל
// עצמו: בזמן הבדיקה הבורר כבר מצביע על היעד, אז כל מעבר מפרופיל אישי נראה
// כ"שינוי לא-שמור" (הוסתר עד עכשיו בטסטים שאישרו confirm() אוטומטית).
function _veComparableOptionsJson() {
  const options = {..._collectRunOptions()};
  delete options.ve_profile_name;
  return _veCanonicalJson(options);
}

// השוואת "שינויים לא-שמורים" לפי תוכן, לא לפי סדר-מפתחות: JSON.stringify רגיל
// תלוי בסדר ההכנסה, ואחרי טעינת פרופילים מחדש (למשל יצירת פרופיל-ילד) אותן
// הגדרות בדיוק נבנו בסדר אחר - והמעבר הציג אישור "שינויים לא-שמורים" מדומה.
function _veCanonicalJson(value) {
  const canon = (v) => Array.isArray(v) ? v.map(canon)
    : (v && typeof v === "object") ? Object.fromEntries(Object.keys(v).sort().map(k => [k, canon(v[k])])) : v;
  return JSON.stringify(canon(value));
}

// גל 9 (item 102): אישור המעבר עצמו דרך veConfirm (לא confirm() החוסם) - הבחירה
// חוזרת מיד לפרופיל הקודם, ורק אחרי "עבור" מוחלת שוב עם דגל-עקיפה חד-פעמי.
let _veDiscardConfirmed = false;

function _veAskDiscardThenApply(targetValue) {
  veConfirm("יש שינויים לא-שמורים בסגנון הנוכחי. לעבור בכל זאת ולוותר עליהם?", {danger: true, okLabel: "עבור בלי לשמור"}).then((ok) => {
    if (!ok) return;
    _veDiscardConfirmed = true;
    document.getElementById("vePreset").value = targetValue;
    applyVideoEditorPreset();
  });
}

// מחיל snapshot מלא של טופס video_editor.py (item: פרופיל אישי) - כל שדה
// חסר (פרופיל ישן/פגום) נופל לברירת המחדל הרגילה של השדה עצמו, לא משאיר את
// הטופס בערך קודם שלא קשור לפרופיל הנטען.
function _applyVideoEditorFields(fields) {
  // גל 30: החלת הגדרות (סגנון, ביטול, מיתוג) היא תמיד לכל הקבצים - יוצאים קודם ממצב עריכת קליפ
  if (typeof exitVeClipMode === "function") exitVeClipMode();
  document.getElementById("veWatermarkPath").value = fields.watermark_path || "";
  document.getElementById("veWatermarkPosition").value = fields.watermark_position || "bottom-right";
  document.getElementById("veWatermarkOpacity").value = fields.watermark_opacity ?? 1.0;
  onWatermarkOpacityInput();
  document.getElementById("veWatermarkScale").value = Math.round((fields.watermark_scale ?? 0.15) * 100);
  document.getElementById("veWatermarkX").value = fields.watermark_x ?? "";
  document.getElementById("veWatermarkY").value = fields.watermark_y ?? "";
  onWatermarkScaleInput();
  document.getElementById("veRemoveWatermarkPosition").value = fields.remove_watermark_position || "";
  document.getElementById("vePipPath").value = fields.pip_path || "";
  document.getElementById("vePipPosition").value = fields.pip_position || "bottom-right";
  document.getElementById("vePipX").value = fields.pip_x ?? "";
  document.getElementById("vePipY").value = fields.pip_y ?? "";
  document.getElementById("vePipScale").value = Math.round((fields.pip_scale ?? 0.3) * 100);
  document.getElementById("vePipScaleValue").textContent = document.getElementById("vePipScale").value + "%";
  document.getElementById("vePipOpacity").value = fields.pip_opacity ?? 1.0;
  document.getElementById("vePipOpacityValue").textContent = parseFloat(document.getElementById("vePipOpacity").value).toFixed(2);
  document.getElementById("veVertical").checked = !!fields.vertical;
  document.getElementById("veSmartCrop").checked = !!fields.smart_crop;
  document.getElementById("veSmartCropFace").disabled = !fields.smart_crop;
  document.getElementById("veSmartCropFace").checked = !!fields.smart_crop_face;
  document.getElementById("veBlurBackground").checked = !!fields.blur_background;
  document.getElementById("veTrimStart").value = fields.trim_start ?? 0;
  document.getElementById("veTrimDuration").value = fields.trim_duration ?? "";
  document.getElementById("veTrimSilence").checked = !!fields.trim_silence;
  document.getElementById("veTargetSeconds").value = fields.target_seconds ?? 0;
  document.getElementById("veKeepAudio").checked = !!fields.keep_audio;
  document.getElementById("veCaptions").checked = !!fields.captions;
  document.getElementById("veCaptionsTranslate").checked = !!fields.captions_translate;
  document.getElementById("veLoudnorm").checked = !!fields.loudnorm;
  document.getElementById("veLoudnormTarget").value = fields.loudnorm_target ?? "";
  document.getElementById("veDenoise").checked = !!fields.denoise;
  document.getElementById("veSharpen").checked = !!fields.sharpen;
  document.getElementById("veThumbnail").checked = !!fields.thumbnail;
  document.getElementById("veFps").value = fields.fps || "";
  document.getElementById("veLutPath").value = fields.lut_path || "";
  document.getElementById("veAutoLevels").checked = !!fields.auto_levels;
  document.getElementById("veNoiseGate").checked = !!fields.noise_gate;
  document.getElementById("veRemoveMidSilence").checked = !!fields.remove_mid_silence;
  document.getElementById("veStabilize").checked = !!fields.stabilize;
  document.getElementById("veChromakey").checked = !!fields.chromakey;
  document.getElementById("veChromakeyColor").value = fields.chromakey_color || "0x00FF00";
  document.getElementById("veChromakeyBgColor").value = fields.chromakey_bg_color || "0x000000";
  document.getElementById("veCaptionFont").value = fields.caption_font || "Arial";
  document.getElementById("veCaptionFontSize").value = fields.caption_font_size ?? 16;
  document.getElementById("veCaptionColor").value = fields.caption_color || "#FFFFFF";
  document.getElementById("veCaptionPosition").value = fields.caption_position || "bottom";
  document.getElementById("veFadeInSeconds").value = fields.fade_in_seconds ?? 0;
  document.getElementById("veFadeOutSeconds").value = fields.fade_out_seconds ?? 0;
  document.getElementById("veRemoveRanges").value = fields.remove_ranges || "";
  document.getElementById("veReplaceAudioPath").value = fields.replace_audio_path || "";
  document.getElementById("veText").value = fields.text || "";
  document.getElementById("veTextPosition").value = fields.text_position || "bottom";
  document.getElementById("veTextFont").value = fields.text_font || "Arial";
  document.getElementById("veTextFontSize").value = fields.text_font_size ?? 24;
  document.getElementById("veTextColor").value = fields.text_color || "#FFFFFF";
  document.getElementById("veCodec").value = fields.codec || "h264";
  document.getElementById("vePreserveResolution").checked = !!fields.preserve_resolution;
  document.getElementById("veNoSuffix").checked = !!fields.no_suffix;
  document.getElementById("veNumberVideos").checked = !!fields.number_videos;
  document.getElementById("veNumberPrefix").value = fields.number_prefix || "Clip";
  document.getElementById("veNumberStart").value = fields.number_start ?? "";
  document.getElementById("veNumberStart").dataset.lastValue = fields.number_start ?? "";
  document.getElementById("veParallel").value = fields.parallel ?? 1;
  document.getElementById("veMaxConcurrentNvenc").value = fields.max_concurrent_nvenc ?? "";
  document.getElementById("veEffort").value = fields.effort || "high";
  document.getElementById("veContainer").value = fields.container || "mp4";
  document.getElementById("veOutputTemplate").value = fields.output_template || "";
  document.getElementById("veValidateOnly").checked = !!fields.validate_only;
  document.getElementById("veNotifyPerFile").checked = !!fields.notify_per_file;
  document.getElementById("veExportReport").value = fields.export_report || "";
  // "folder" (item: תיקיית קלט בפרופיל) חורג מהמוסכמה - state.folder המשותף
  // לכל הסקריפטים, לא שדה video_editor ספציפי - נטען כאן בנפרד, לא ב-loop גנרי.
  if (fields.folder) {
    const folderChanged = state.folder !== fields.folder;
    state.folder = fields.folder;
    document.getElementById("folderInput").value = fields.folder;
    updateRunEnabled();
    if (folderChanged) _veRefreshFolderCounts();
  }
  _applyGenericVeFields(fields);
  document.getElementById("veFavoriteFields").value = fields.favorite_fields || "";
  syncAutoFavorites();
  rebuildFavoritesBox();
  updateWatermarkPreview();
  updateCategorySummaries();
  uiBus.emit("ve:fields-applied", fields);
}

// item: איפוס לברירת מחדל - מאשר, ואז משתמש ב-_applyVideoEditorFields({})
// הקיים (כל שדה נופל לברירת המחדל שלו כשהמפתח חסר, בדיוק כמו טעינת פרופיל
// עם מפתחות חסרים) - לא נוגע בפרופילים שמורים על הדיסק.
async function resetVideoEditorToDefaults() {
  if (!(await veConfirm("לאפס את כל הגדרות עורך-העל לברירת המחדל?\nסגנונות שמורים לא יימחקו.", {danger: true, okLabel: "↺ אפס הכל"}))) return;
  _applyVideoEditorFields({});
  document.getElementById("vePreset").value = "";
  state.vePresetPrevious = "";
  state.veBaseline = null;
  updateUnsavedIndicator();
  _setVeProfileButtonsVisible(false);
  document.getElementById("veProfileMetaInfo").textContent = "";
}

// item: מקראה - דיאלוג עם כל המונחים/הסברים מ-FIELD_HELP (מאותו מקור-אמת
// כמו הדסקטופ, /api/video_editor/field_help - לא משוכפל כאן כ-JS סטטי),
// עם חיפוש טקסט חי - להבדיל מהטולטיפים (title=, per-field) זו רשימה מלאה
// ניתנת-לסריקה/חיפוש.
let _fieldHelpCache = null;
async function openGlossaryDialog() {
  if (!_fieldHelpCache) {
    const res = await fetch("/api/video_editor/field_help");
    _fieldHelpCache = await res.json();
  }
  _renderGlossaryList("");
  document.getElementById("glossarySearch").value = "";
  document.getElementById("glossaryModalBg").classList.add("show");
}

function _renderGlossaryList(query) {
  const list = document.getElementById("glossaryList");
  list.innerHTML = "";
  const q = query.trim().toLowerCase();
  const entries = Object.entries(_fieldHelpCache || {})
    .map(([key, help]) => ({key, term: help.term, tooltip: help.tooltip}))
    .sort((a, b) => a.term.localeCompare(b.term, "he"));
  for (const entry of entries) {
    if (q && !entry.term.toLowerCase().includes(q) && !entry.tooltip.toLowerCase().includes(q)) continue;
    const row = document.createElement("div");
    // item: ניווט מקלדת במקראה - שורה לחיצה שקופצת לשדה האמיתי בפאנל (רק
    // כשיש לו UI ברור, ראו VE_FAVORITABLE_FIELDS) - לא כל מפתח ב-FIELD_HELP
    // חייב אחד (למשל watermark_x/y, קואורדינטות גרירה בלי שדה UI עצמאי).
    const clickable = !!VE_FAVORITABLE_FIELDS[entry.key];
    row.style.cssText = "padding:8px 10px;border-bottom:1px solid var(--border2)" + (clickable ? ";cursor:pointer" : "");
    row.dataset.fieldKey = entry.key;
    const term = document.createElement("div");
    term.style.cssText = "font-weight:700;font-size:13px;margin-bottom:2px";
    term.textContent = entry.term;
    const tooltip = document.createElement("div");
    tooltip.style.cssText = "font-size:12px;color:var(--text-muted)";
    tooltip.textContent = entry.tooltip;
    row.appendChild(term); row.appendChild(tooltip);
    if (clickable) row.addEventListener("click", () => { closeGlossaryDialog(); veScrollToField(entry.key); });
    list.appendChild(row);
  }
}

function closeGlossaryDialog() { document.getElementById("glossaryModalBg").classList.remove("show"); }

function veScrollToField(fieldKey) {
  const meta = VE_FAVORITABLE_FIELDS[fieldKey];
  if (!meta) return;
  const el = document.getElementById(meta.id);
  if (!el) return;
  _veRevealElement(el);
  el.scrollIntoView({behavior: "smooth", block: "center"});
  const row = el.closest(".ve-row") || el;
  row.classList.remove("ve-flash-highlight");
  void row.offsetWidth;  // מכריח reflow כדי שההבהוב יחזור על עצמו גם כשלוחצים על אותו שדה שוב ברצף
  row.classList.add("ve-flash-highlight");
}

function _setupGlossaryKeyboardNav() {
  const input = document.getElementById("glossarySearch");
  input.addEventListener("keydown", (e) => {
    const rows = Array.from(document.getElementById("glossaryList").children);
    if (!rows.length) return;
    let idx = rows.findIndex(r => r.classList.contains("ve-glossary-active"));
    if (e.key === "ArrowDown") { e.preventDefault(); idx = Math.min(rows.length - 1, idx + 1); _highlightGlossaryRow(rows, idx); }
    else if (e.key === "ArrowUp") { e.preventDefault(); idx = Math.max(0, idx - 1); _highlightGlossaryRow(rows, idx); }
    else if (e.key === "Enter" && idx >= 0) { e.preventDefault(); rows[idx].click(); }
  });
}

function _highlightGlossaryRow(rows, idx) {
  rows.forEach(r => r.classList.remove("ve-glossary-active"));
  rows[idx].classList.add("ve-glossary-active");
  rows[idx].scrollIntoView({block: "nearest"});
}

// item: קישור עמוק לקטגוריה/שדה בעורך-העל (#ve-<data-cat>, למשל #ve-captions) -
// לשלוח למישהו "תבדוק את ההגדרה הזו" בלי לתאר במילים איפה לגלול.
function veScrollToCategory(catKey) {
  // item: ארגון מחדש - watermark/pip/text הם עכשיו תתי-קטגוריות של "🧩 שכבות",
  // אז קישור עמוק ישן (#ve-watermark) עדיין עובד: קופץ לתת-הקטגוריה בתוכה.
  const target = document.querySelector(`#videoEditorOptions details.ve-category[data-cat="${catKey}"]`)
    || document.querySelector(`#videoEditorOptions .ve-subcat[data-subcat="${catKey}"]`);
  if (!target) return;
  _veRevealElement(target);
  target.scrollIntoView({behavior: "smooth", block: "start"});
}

function _handleVeDeepLinkHash() {
  const hash = location.hash;
  if (!hash.startsWith("#ve-")) return;
  if (!_veIsActive()) return;  // לא בוחרים סקריפט בשם המשתמש, רק אם כבר נבחר
  veScrollToCategory(hash.slice(4));
}
window.addEventListener("hashchange", _handleVeDeepLinkHash);

// item: הרחב-הכל/כווץ-הכל - כפתור יחיד שמתחלף לפי המצב הרוב (רוב הקטגוריות
// פתוחות -> "כווץ הכל", אחרת -> "הרחב הכל"), לא toggle עיוור שמתעלם ממצב נוכחי.
function toggleAllVeCategories() {
  const details = document.querySelectorAll("#videoEditorOptions details.ve-category");
  const openCount = Array.from(details).filter(d => d.open).length;
  const shouldOpen = openCount < details.length / 2;
  details.forEach(d => d.open = shouldOpen);
  document.getElementById("veToggleAllBtn").textContent = shouldOpen ? "⏫ כווץ הכל" : "⏬ הרחב הכל";
}

// item: אזהרה לפני סגירת טאב עם שינויים לא-שמורים - הרחבה טבעית של אינדיקציית
// "שינויים לא-שמורים" הקיימת (state.veBaseline), כמעט חינם בווב (אין מקבילה
// אמיתית ב-Tkinter לחלון-דסקטופ בלאו הכי). רק כשהסגנון באמת שונה - קודם כל רענון עם סגנון אישי שאף אחד
// לא נגע בו שאל "לעזוב את האתר?" (הרצה מקצה לקצה, 16.10)
window.addEventListener("beforeunload", (e) => {
  if (state.veBaseline && _veIsActive() && _veComparableOptionsJson() !== state.veBaseline) {
    e.preventDefault();
    e.returnValue = "";
  }
});

function _veIsActive() {
  return (state.selectedId || "").endsWith("video_editor.py") && !document.getElementById("videoEditorOptions").hidden;
}

// item: איפוס לשדה בודד - ↺ קטן ליד כל שדה-מועדף (VE_FAVORITABLE_FIELDS כבר
// מכסה כל שדה עם UI ברור, ראו FIELD_HELP) לצד "אפס לברירת מחדל" הגלובלי
// הקיים - נלכד פעם אחת מהערכים שה-HTML נטען איתם (לפני כל אינטראקציה של
// המשתמש), לא ממקור-אמת Python נפרד שהיה צריך להישאר מסונכרן ידנית.
let _veFieldDefaults = null;
function _captureVeFieldDefaults() {
  _veFieldDefaults = {};
  for (const key in VE_FAVORITABLE_FIELDS) {
    const el = document.getElementById(VE_FAVORITABLE_FIELDS[key].id);
    if (el) _veFieldDefaults[el.id] = el.type === "checkbox" ? el.checked : el.value;
  }
}

function _setupPerFieldResetButtons() {
  for (const key in VE_FAVORITABLE_FIELDS) {
    const el = document.getElementById(VE_FAVORITABLE_FIELDS[key].id);
    if (!el) continue;
    const row = el.closest(".ve-row");
    if (!row || row.querySelector(".ve-field-reset")) continue;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ve-field-reset";
    btn.textContent = "↺";
    btn.title = "אפס שדה זה לברירת המחדל";
    btn.onclick = () => _resetSingleVeField(el);
    row.appendChild(btn);
  }
}

function _resetSingleVeField(el) {
  if (!_veFieldDefaults || !(el.id in _veFieldDefaults)) return;
  const value = _veFieldDefaults[el.id];
  if (el.type === "checkbox") el.checked = value; else el.value = value;
  el.dispatchEvent(new Event("input", {bubbles: true}));
  el.dispatchEvent(new Event("change", {bubbles: true}));
}

// item: Undo/Redo (Ctrl+Z/Ctrl+Y) על עריכה חיה - נפרד לגמרי מהיסטוריית-שינויים
// לפרופיל שמור (roadmap, snapshot-ים על הדיסק) - זה zero-cost, in-memory,
// לכל עריכת-טופס בסשן הנוכחי, גם בלי פרופיל בכלל. לא מתערב ב-undo המובנה
// של הדפדפן בתוך שדה טקסט חופשי (ראו isTextEditable למטה).
let _veUndoStack = [];
let _veRedoStack = [];
let _veUndoSuppressed = false;
let _veUndoDebounceTimer = null;

function _pushVeUndoSnapshot() {
  if (_veUndoSuppressed || !_veIsActive()) return;
  const snap = JSON.stringify(_collectRunOptions());
  if (_veUndoStack.length && _veUndoStack[_veUndoStack.length - 1] === snap) return;
  _veUndoStack.push(snap);
  if (_veUndoStack.length > 50) _veUndoStack.shift();
  _veRedoStack = [];
}

function _veResetUndoHistory() {
  _veUndoStack = [];
  _veRedoStack = [];
  if (_veIsActive()) _pushVeUndoSnapshot();
}

function veUndo() {
  if (_veUndoStack.length < 2) return;  // הערך האחרון הוא המצב *הנוכחי*, לא צעד-אחורה
  const current = _veUndoStack.pop();
  _veRedoStack.push(current);
  _veUndoSuppressed = true;
  try { _applyVideoEditorFields(JSON.parse(_veUndoStack[_veUndoStack.length - 1])); }
  finally { _veUndoSuppressed = false; }
}

function veRedo() {
  if (!_veRedoStack.length) return;
  const snap = _veRedoStack.pop();
  _veUndoStack.push(snap);
  _veUndoSuppressed = true;
  try { _applyVideoEditorFields(JSON.parse(snap)); }
  finally { _veUndoSuppressed = false; }
}

document.getElementById("videoEditorOptions").addEventListener("input", (e) => {
  clearTimeout(_veUndoDebounceTimer);
  _veUndoDebounceTimer = setTimeout(_pushVeUndoSnapshot, 400);
  if (e.target.type === "range") _veRefreshRangeLabels();
  if (!e.target.closest(".ve-favorite-row")) _veScheduleFavoritesSync();
});
document.getElementById("videoEditorOptions").addEventListener("change", (e) => {
  clearTimeout(_veUndoDebounceTimer);
  _veUndoDebounceTimer = setTimeout(_pushVeUndoSnapshot, 400);
  if (!e.target.closest(".ve-favorite-row")) _veScheduleFavoritesSync();
});
// גל 9 (item 101): חישוב המועדפים האוטומטיים עובר על כל השדות - לא בכל הקשה
// (גרירת סליידר יורה עשרות input בשנייה), אלא פעם אחת אחרי שההקלדה נרגעת.
let _veFavoritesSyncTimer = null;
function _veScheduleFavoritesSync() {
  clearTimeout(_veFavoritesSyncTimer);
  _veFavoritesSyncTimer = setTimeout(syncAutoFavorites, 200);
}
document.addEventListener("keydown", (e) => {
  if (!_veIsActive()) return;
  const active = document.activeElement;
  const isTextEditable = active && ((active.tagName === "INPUT" && (active.type === "text" || active.type === "number")) || active.tagName === "TEXTAREA");
  if (isTextEditable) return;  // תן לדפדפן לטפל ב-undo/redo של הקלדת טקסט עצמה
  const key = e.key.toLowerCase();
  if ((e.ctrlKey || e.metaKey) && key === "z" && !e.shiftKey) { e.preventDefault(); veUndo(); }
  else if ((e.ctrlKey || e.metaKey) && (key === "y" || (key === "z" && e.shiftKey))) { e.preventDefault(); veRedo(); }
});

// item: תצוגת "הפקודה שתישלח בפועל" - קורא לאותו /api/video_editor/preview_command
// שמריץ בעצמו _build_extra_args האמיתי בצד השרת, לא מחשב argv ב-JS בנפרד.
async function openCommandPreviewDialog() {
  const res = await fetch("/api/video_editor/preview_command", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(_collectRunOptions()),
  });
  const data = await res.json();
  document.getElementById("commandPreviewText").value = data.command || "";
  document.getElementById("commandPreviewModalBg").classList.add("show");
}

function closeCommandPreviewDialog() { document.getElementById("commandPreviewModalBg").classList.remove("show"); }

function _copyCommandPreview() {
  const textarea = document.getElementById("commandPreviewText");
  textarea.select();
  navigator.clipboard.writeText(textarea.value).catch(() => { try { document.execCommand("copy"); } catch (e2) {} });
}

// item: תור-אצווה ניתן-לעריכה - _veQueueState הוא סדר-האמת המקומי (לא נשמר
// לשרת בכלל) לקבצי תיקיית-השורש הנבחרת; _veQueueDirty מבדיל "המשתמש לא נגע
// בתור" (only_files=null, מתנהג בדיוק כמו לפני התכונה הזו) מ"המשתמש כן ערך"
// (גם אם בסוף התוצאה זהה לברירת המחדל - נשלח מפורשות ברגע שנגעו בזה).
let _veQueueState = [];
let _veQueueDirty = false;
const VE_VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm"];

function _onVeFolderChanged() {
  veFlow.folderChanged();
  _veQueueState = [];
  _veQueueDirty = false;
  const list = document.getElementById("veQueueList");
  if (list) list.innerHTML = "";
  const summary = document.getElementById("veCatSummary-queue");
  if (summary) summary.textContent = "";
  _veRefreshFolderCounts();
  _veScheduleTrimReference();
  uiBus.emit("ve:folder-changed", state.folder);
}

async function refreshVeQueue() {
  const container = document.getElementById("veQueueList");
  if (!state.folder) { container.innerHTML = '<div class="hint" style="display:block">בחר תיקייה קודם.</div>'; return; }
  // רק הקריאה האחרונה קובעת: רשימה ישנה שחוזרת מאוחר (למשל מהחלפת תיקייה) לא דורסת
  // תור שכבר שוחזר מפרופיל/פרויקט בקריאה חדשה יותר (veFlow, 07-ui-flow.js)
  const seq = veFlow.beginQueueRefresh();
  try {
    const res = await fetch("/api/browse?path=" + encodeURIComponent(state.folder));
    const data = await res.json();
    if (!veFlow.isLatestQueueRefresh(seq)) return;
    const files = (data.files || []).filter(f => VE_VIDEO_EXTENSIONS.some(ext => f.name.toLowerCase().endsWith(ext)));
    // דריסות פר-קובץ שכבר הוגדרו נשמרות לפי שם-קובץ ברענון (לא נמחקות בשקט).
    const previous = Object.fromEntries(_veQueueState.map(f => [f.name, f]));
    _veQueueState = files.map(f => ({
      name: f.name, selected: true, overrides: (previous[f.name] || {}).overrides || {}, size: f.size,
    }));
    _veQueueDirty = false;
    // item 57: תור שנשמר עם הפרופיל - סדר+סימון משוחזרים (קבצים חדשים בסוף, מסומנים).
    const restore = veFlow.takeQueueRestore();
    if (restore) {
      const saved = restore.files;
      const byName = Object.fromEntries(_veQueueState.map(f => [f.name, f]));
      const ordered = [];
      for (const entry of saved) {
        const item = byName[entry.name];
        if (!item) continue;
        item.selected = entry.selected !== false;
        ordered.push(item);
        delete byName[entry.name];
      }
      _veQueueState = [...ordered, ...Object.values(byName)];
      _veQueueDirty = true;
    }
    _veQueueLastPickIndex = null;
    _renderVeQueue();
    _veLoadQueueMeta();
    _veLoadQueueLastRun();
  } catch (e) {
    container.innerHTML = '<div class="hint" style="display:block">שגיאה בטעינת רשימת הקבצים.</div>';
  }
}

// item 51: מידע עשיר לכל שורה (משך/רזולוציה/FPS/HDR) - נטען בנתחים של 10 קבצים
// ברקע אחרי שהתור כבר מוצג, כך שתיקייה גדולה לא "נתקעת" על ה-probe.
let _veQueueMeta = {};
let _veQueueLastRun = {};
let _veQueueLastPickIndex = null;

async function _veLoadQueueMeta() {
  const folder = state.folder;
  const request = uiLatest("ve:queue-meta");
  const missing = _veQueueState.map(f => f.name).filter(n => !_veQueueMeta[folder + "|" + n]);
  for (let i = 0; i < missing.length; i += 10) {
    if (state.folder !== folder || !request.current()) return;
    try {
      const res = await fetch("/api/video_editor/probe_batch", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({folder, names: missing.slice(i, i + 10)}), signal: request.signal});
      const data = await res.json();
      for (const [name, info] of Object.entries(data.files || {})) _veQueueMeta[folder + "|" + name] = info;
    } catch (e) { return; }
    if (!request.current()) return;
    _renderVeQueue();
    _veRenderWarnings(_veEvaluateRules());   // "יש שמע במקור" נודע רק עכשיו (50-editor-organization.js)
  }
}

// item 54: סטטוס ✅/❌/⏭️ לכל קובץ מהריצה האחרונה על התיקייה הזו (run manifest).
async function _veLoadQueueLastRun() {
  _veQueueLastRun = {};
  if (!state.folder) return;
  const request = uiLatest("ve:queue-last-run");
  const lastRun = {};
  try {
    const res = await fetch("/api/video_editor/latest_manifest?quiet=1&folder=" + encodeURIComponent(state.folder), {signal: request.signal});
    if (!res.ok) return;
    const manifest = await res.json();
    for (const file of manifest.files || []) lastRun[file.source] = file;
    lastRun.__when = manifest.finished_at;
  } catch (e) { return; }
  if (!request.current()) return;  // תיקייה אחרת כבר נטענה בינתיים
  _veQueueLastRun = lastRun;
  _renderVeQueue();
}

function _veQueueMetaText(info) {
  if (!info) return "⏳";
  const parts = [];
  if (info.duration) parts.push(_veFormatTime(info.duration));
  if (info.width && info.height) parts.push(`${info.width}×${info.height}`);
  if (info.fps) { const fps = _veParseFps(info.fps); if (fps) parts.push(`${Math.round(fps * 100) / 100}fps`); }
  if (info.size) parts.push(_formatFileSize(info.size));
  if (info.mtime) parts.push(new Date(info.mtime * 1000).toLocaleDateString("he-IL"));
  if (!info.has_audio) parts.push("🔇");
  return parts.join(" · ");
}

function _veParseFps(text) {
  const [num, den] = String(text).split("/").map(Number);
  return den ? num / den : num;
}

const VE_LAST_RUN_BADGES = {created: ["✅", "נוצר בריצה האחרונה"], skipped: ["⏭️", "דולג בריצה האחרונה"], error: ["❌", "נכשל בריצה האחרונה"], valid: ["🧪", "תקין בבדיקה האחרונה"], invalid: ["🧪❌", "לא תקין בבדיקה האחרונה"]};

// גל 24: שורות התור נבנות מחדש רק כשמשהו בהן השתנה. קודם כל סימון/לחיצה בנה מחדש את
// כל הרשימה (מאות שורות עם תמונה ו-listeners); עכשיו כל שורה שמורה לפי אובייקט הפריט
// שלה עם "חתימה" של מה שהיא מציגה, שורה שהשתנתה מוחלפת במקומה, והסדר מתוקן רק כשצריך.
let _veQueueRows = new WeakMap();  // פריט -> {signature, row}

function _veQueueRowSignature(item, index) {
  const info = _veQueueMeta[state.folder + "|" + item.name];
  const last = _veQueueLastRun[item.name];
  return JSON.stringify([state.folder, index, item.name, !!item.selected, !!item._picked,
    _veQueueMetaText(info), !!(info && info.hdr), last ? [last.status, last.reason || ""] : null,
    last ? _veQueueLastRun.__when || null : null]);
}

function _veQueueRowFor(item, index, container) {
  const signature = _veQueueRowSignature(item, index);
  const cached = _veQueueRows.get(item);
  if (cached && cached.signature === signature) return cached.row;
  const row = _buildVeQueueRow(item, index, cached ? cached.row : null);
  if (cached && cached.row.parentNode === container) cached.row.replaceWith(row);
  _veQueueRows.set(item, {signature, row});
  return row;
}

function _renderVeQueue() {
  const container = document.getElementById("veQueueList");
  const summary = document.getElementById("veCatSummary-queue");
  const concatOn = document.getElementById("veConcatMode").checked;
  summary.textContent = _veQueueState.length
    ? ` · ${_veQueueState.filter(f => f.selected).length}/${_veQueueState.length} נבחרו` + (concatOn ? " · 🔗 איחוד" : "")
    : (concatOn ? " · 🔗 איחוד (רענן את התור)" : " · כל התיקייה (לא נערך)");
  summary.classList.toggle("ve-empty", !_veQueueState.length && !concatOn);
  _veRenderFileCount();
  _veScheduleTrimReference();
  document.getElementById("veQueueToolbar").hidden = !_veQueueState.length;
  // גל 27: הפעולות הקבוצתיות מופיעות רק כשמסמנים שורות - בפס צף מתחת לרשימה
  const picked = _veQueueState.filter(f => f._picked).length;
  document.getElementById("veQueuePickedCount").textContent = picked ? `${picked} מסומנים לפעולה` : "";
  document.getElementById("veQueueBulkBar").hidden = !picked;
  if (!_veQueueState.length) {
    container.replaceChildren(_veQueueEmptyState());  // גל 31: מצב ריק עם פעולה (בחר תיקייה / רענן / גרור)
    _veQueueRows = new WeakMap();
    return;
  }
  const wanted = [];
  _veQueueState.forEach((item, index) => {
    wanted.push(_veQueueRowFor(item, index, container));
  });
  const keep = new Set(wanted);
  for (const child of [...container.children]) if (!keep.has(child)) child.remove();
  wanted.forEach((node, i) => { if (container.children[i] !== node) container.insertBefore(node, container.children[i] || null); });
  applyVeQueueSearch();
  uiBus.emit("ve:queue-rendered");  // גל 35: תגיות צבע, קיבוץ ותצוגת רשת (79-editor-queue-timeline.js)
}

function _buildVeQueueRow(item, index, previousRow) {
  const row = document.createElement("div");
  row.className = "ve-queue-row" + (item._picked ? " ve-queue-picked" : "") + (item.selected ? "" : " ve-queue-excluded");
  row.draggable = true;
  row.dataset.index = String(index);
  row.dataset.name = item.name;
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = item.selected;
  checkbox.title = "לכלול בריצה";
  checkbox.onchange = () => { item.selected = checkbox.checked; _veQueueDirty = true; _renderVeQueue(); updateVeEtaDisplay(); };
  // התמונה של השורה הקודמת עוברת לחדשה (בלי הבהוב ובלי בקשה חוזרת) אם זה אותו קובץ
  const src = "/api/video_editor/file_thumbnail?path=" + encodeURIComponent(_veFolderPath(item.name));
  const previousThumb = previousRow && previousRow.querySelector(".ve-queue-thumb");
  const thumb = previousThumb && previousThumb.dataset.src === src ? previousThumb : document.createElement("img");
  if (thumb !== previousThumb) {
    thumb.className = "ve-queue-thumb";
    thumb.loading = "lazy";
    thumb.alt = "";
    thumb.dataset.src = src;
    thumb.src = src;
  }
  const main = document.createElement("div");
  main.className = "ve-queue-main";
  const name = document.createElement("span");
  name.className = "ve-queue-name";
  name.textContent = `${index + 1}. ${item.name}`;
  // כיוון לפי השם: שם באנגלית בעמודה צרה נחתך מההתחלה ("…ugh.mp4" בכל השורות) ו-"1." הפך ל-".1"
  name.dir = "auto";
  name.title = item.name;
  const info = _veQueueMeta[state.folder + "|" + item.name];
  const meta = document.createElement("span");
  meta.className = "ve-queue-meta";
  meta.dir = "auto";
  meta.textContent = _veQueueMetaText(info);
  main.append(name, meta);
  row.append(checkbox, thumb, main);
  if (info && info.hdr) {
    const hdr = document.createElement("span");
    hdr.className = "ve-queue-badge ve-badge-hdr"; hdr.textContent = "HDR";
    hdr.title = "מקור HDR - עם HEVC/AV1 נשמר HDR מלא, עם H.264 עובר tone-mapping ל-SDR";
    row.appendChild(hdr);
  }
  const last = _veQueueLastRun[item.name];
  if (last && VE_LAST_RUN_BADGES[last.status]) {
    const [icon, label] = VE_LAST_RUN_BADGES[last.status];
    const badge = document.createElement("span");
    badge.className = "ve-queue-badge ve-badge-status";
    badge.textContent = icon;
    badge.title = label + (last.reason ? ` - ${last.reason}` : "") + (_veQueueLastRun.__when ? ` (${new Date(_veQueueLastRun.__when).toLocaleString("he-IL")})` : "");
    row.appendChild(badge);
  }
  // גל 30: ✏️ = מצב עריכת קליפ לקובץ הזה (זמן, לוגו ושכבות רק לו) - במקום עורך הדריסות שהיה
  // נפתח בתוך השורה. הספירה (✏️ N) מתווספת ב-_veDecorateQueueClipBadges.
  const editBtn = document.createElement("button");
  editBtn.type = "button";
  editBtn.className = "ve-queue-clip-btn";
  editBtn.textContent = "✏️";
  editBtn.title = "ערוך רק את הקובץ הזה - זמן, לוגו ושכבות";
  editBtn.setAttribute("aria-label", `ערוך רק את ${item.name}`);
  editBtn.setAttribute("aria-pressed", "false");
  editBtn.onclick = (e) => {
    e.stopPropagation();
    if (_veTimeScope === "clip" && _veClipScopeFile === item.name) exitVeClipMode(); else enterVeClipMode(item.name);
  };
  row.appendChild(editBtn);
  // item 52: בחירה מרובה - לחיצה על שורה בוחרת אותה לפעולה קבוצתית (Ctrl מוסיף/
  // מסיר, Shift בוחר טווח). נפרד מתיבת-הסימון "לכלול בריצה".
  row.addEventListener("click", (e) => {
    if (e.target.closest("input, button")) return;
    if (e.shiftKey && _veQueueLastPickIndex !== null) {
      const [a, b] = [Math.min(_veQueueLastPickIndex, index), Math.max(_veQueueLastPickIndex, index)];
      _veQueueState.forEach((f, i) => { if (i >= a && i <= b) f._picked = true; });
    } else if (e.ctrlKey || e.metaKey) {
      item._picked = !item._picked;
    } else {
      const only = !item._picked || _veQueueState.filter(f => f._picked).length > 1;
      _veQueueState.forEach(f => { f._picked = false; });
      item._picked = only;
    }
    _veQueueLastPickIndex = index;
    _renderVeQueue();
  });
  row.addEventListener("dragstart", (e) => { row.classList.add("dragging"); e.dataTransfer.setData("text/x-ve-queue-index", String(index)); });
  row.addEventListener("dragend", () => row.classList.remove("dragging"));
  row.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("text/x-ve-queue-index")) { e.preventDefault(); row.classList.add("drag-over"); } });
  row.addEventListener("dragleave", () => row.classList.remove("drag-over"));
  row.addEventListener("drop", (e) => {
    const fromIndex = parseInt(e.dataTransfer.getData("text/x-ve-queue-index"), 10);
    row.classList.remove("drag-over");
    if (Number.isNaN(fromIndex)) return;
    e.preventDefault();
    e.stopPropagation();
    if (fromIndex === index) return;
    const [moved] = _veQueueState.splice(fromIndex, 1);
    _veQueueState.splice(index, 0, moved);
    _veQueueDirty = true;
    _renderVeQueue();
  });
  return row;
}

// item 52: פעולות קבוצתיות על השורות שנבחרו (או על כולן, אם לא נבחרה אף אחת).
function veQueueBulk(action) {
  const picked = _veQueueState.filter(f => f._picked);
  const targets = picked.length ? picked : _veQueueState;
  if (action === "pickAll") _veQueueState.forEach(f => { f._picked = _veQueueMatchesSearch(f); });
  else if (action === "pickNone") _veQueueState.forEach(f => { f._picked = false; });
  else if (action === "include") { targets.forEach(f => { f.selected = true; }); _veQueueDirty = true; }
  else if (action === "exclude") { targets.forEach(f => { f.selected = false; }); _veQueueDirty = true; }
  else if (action === "top" || action === "bottom") {
    const rest = _veQueueState.filter(f => !f._picked);
    _veQueueState = action === "top" ? [...picked, ...rest] : [...rest, ...picked];
    _veQueueDirty = true;
  }
  _renderVeQueue();
  updateVeEtaDisplay();
}

// item 55: סינון תור - מסמן "לכלול בריצה" רק קבצים שעונים לכל התנאים שמולאו.
function applyVeQueueFilter() {
  const since = document.getElementById("veQueueFilterSince").value;
  const minSeconds = _veParseTime(document.getElementById("veQueueFilterMinSeconds").value);
  const onlyNotCreated = document.getElementById("veQueueFilterNotCreated").checked;
  const sinceTs = since ? new Date(since + "T00:00:00").getTime() / 1000 : null;
  let kept = 0;
  for (const item of _veQueueState) {
    const info = _veQueueMeta[state.folder + "|" + item.name] || {};
    let ok = true;
    if (sinceTs !== null) ok = ok && (info.mtime || 0) >= sinceTs;
    if (Number.isFinite(minSeconds)) ok = ok && (info.duration || 0) > minSeconds;
    if (onlyNotCreated) ok = ok && !((_veQueueLastRun[item.name] || {}).status === "created");
    item.selected = ok;
    if (ok) kept++;
  }
  _veQueueDirty = true;
  _renderVeQueue();
  updateVeEtaDisplay();
  document.getElementById("veQueueFilterResult").textContent = `${kept}/${_veQueueState.length} עונים לסינון`;
}

function clearVeQueueFilter() {
  document.getElementById("veQueueFilterSince").value = "";
  document.getElementById("veQueueFilterMinSeconds").value = "";
  document.getElementById("veQueueFilterNotCreated").checked = false;
  _veQueueState.forEach(f => { f.selected = true; });
  _veQueueDirty = true;
  _renderVeQueue();
  document.getElementById("veQueueFilterResult").textContent = "";
}

// item 53: גרירת קבצי וידאו מהמערכת לתוך התור - מועתקים לתיקיית הקלט הנבחרת.
async function _veUploadDroppedFiles(fileList) {
  const files = Array.from(fileList).filter(f => VE_VIDEO_EXTENSIONS.some(ext => f.name.toLowerCase().endsWith(ext)));
  if (!files.length) { alert("אפשר לגרור לכאן רק קבצי וידאו (mp4/mkv/mov/avi/webm)."); return; }
  if (!state.folder) { alert("בחר קודם תיקיית קלט - הקבצים יועתקו אליה."); return; }
  const totalMb = files.reduce((sum, f) => sum + f.size, 0) / 1024 / 1024;
  if (!(await veConfirm(`להעתיק ${files.length} קבצים (${Math.round(totalMb)}MB) לתיקייה:\n${state.folder}\nהקבצים המקוריים לא ישתנו.`, {okLabel: "📥 העתק לתיקייה"}))) return;
  const status = document.getElementById("veQueueDropStatus");
  const failures = [];
  for (let i = 0; i < files.length; i++) {
    status.textContent = `⏳ מעתיק ${i + 1}/${files.length}: ${files[i].name}`;
    try {
      const res = await fetch(`/api/video_editor/upload?folder=${encodeURIComponent(state.folder)}&name=${encodeURIComponent(files[i].name)}`, {method: "POST", body: files[i]});
      if (!res.ok) failures.push(`${files[i].name}: ${(await res.json()).error || res.status}`);
    } catch (e) { failures.push(`${files[i].name}: שגיאת רשת`); }
  }
  status.textContent = failures.length ? `⚠️ ${files.length - failures.length}/${files.length} הועתקו` : `✅ ${files.length} קבצים הועתקו`;
  if (failures.length) alert("חלק מהקבצים לא הועתקו:\n" + failures.join("\n"));
  await refreshVeQueue();
  _veRefreshFolderCounts();
}

function _setupVeQueueDropZone() {
  const zone = document.querySelector('#videoEditorOptions details.ve-category[data-cat="queue"]');
  zone.addEventListener("dragover", (e) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    zone.classList.add("ve-queue-drop-active");
  });
  zone.addEventListener("dragleave", (e) => { if (!zone.contains(e.relatedTarget)) zone.classList.remove("ve-queue-drop-active"); });
  zone.addEventListener("drop", (e) => {
    if (!e.dataTransfer.files || !e.dataTransfer.files.length) return;
    e.preventDefault();
    zone.classList.remove("ve-queue-drop-active");
    zone.open = true;
    _veUploadDroppedFiles(e.dataTransfer.files);
  });
}

// item 57: שמירת תור עם פרופיל (אופציונלי) - העדפה פר-דפדפן.
function _veQueueSnapshotForProfile() {
  if (!document.getElementById("veSaveQueueWithProfile").checked || !_veQueueState.length) return null;
  return _veQueueState.map(f => ({name: f.name, selected: !!f.selected}));
}

function _veQueueSelectedFiles() {
  if (!_veQueueDirty || !_veQueueState.length) return null;
  return _veQueueState.filter(f => f.selected).map(f => f.name);
}

function _veConcatFiles() {
  return _veQueueState.filter(f => f.selected).map(f => f.name);
}

// דריסות פר-קובץ (--batch-overrides): מגל 30 נבנות מעריכות-הקליפ בצד השרת (clip_edits) -
// כאן נשארות רק דריסות ישנות שעוד יושבות על פריטי התור
function _veBatchOverrides() {
  const out = {};
  for (const item of _veQueueState) {
    if (item.overrides && Object.keys(item.overrides).length) out[item.name] = item.overrides;
  }
  return out;
}

// item: מצב "🔗 איחוד קטעים" - סדר התור הוא סדר האיחוד, אז התור נטען אוטומטית
// בהפעלה אם עדיין לא נטען (silent=true בטעינת פרופיל - בלי פנייה לשרת).
function onVeConcatModeToggled(silent) {
  const on = document.getElementById("veConcatMode").checked;
  document.getElementById("veConcatOptions").hidden = !on;
  if (on && silent !== true && !_veQueueState.length && state.folder) {
    const queueCat = document.querySelector('#videoEditorOptions details.ve-category[data-cat="queue"]');
    if (queueCat) queueCat.open = true;
    refreshVeQueue();
  }
}

// item: הערכת זמן-ריצה משוער - codec + --hwaccel (item: פער CLI→Web - עכשיו
// שדה אמיתי בווב, לא תמיד false), כפול מספר-קבצים אם תור-האצווה נערך בפועל,
// אחרת ברירת מחדל של קובץ אחד (הערכה-לקובץ, לא לכל batch).
async function updateVeEtaDisplay() {
  const el = document.getElementById("veEtaDisplay");
  if (!_veIsActive()) { el.textContent = ""; return; }
  const codec = document.getElementById("veCodec").value;
  const hwaccel = document.getElementById("veHwaccel").checked && codec !== "h264";
  const fileCount = (_veQueueDirty && _veQueueState.length) ? _veQueueState.filter(f => f.selected).length : 1;
  const request = uiLatest("ve:eta");
  try {
    const params = new URLSearchParams({codec, hwaccel: hwaccel ? "true" : "false", file_count: String(fileCount)});
    const res = await fetch("/api/video_editor/eta?" + params.toString(), {signal: request.signal});
    const data = await res.json();
    if (!request.current()) return;
    el.textContent = data ? `⏱️ ~${_veFormatSeconds(data.estimated_total_seconds)} (${data.run_count} ריצות קודמות)` : "";
  } catch (e) {
    if (!uiIsAbort(e)) el.textContent = "";
  }
}

function _veFormatSeconds(seconds) {
  const s = Math.round(seconds);
  if (s < 60) return `${s} שנ'`;
  const m = Math.floor(s / 60);
  return `${m} דק' ${s % 60} שנ'`;
}

// item: היסטוריית ערכים אחרונים לשדות טקסט חופשי - datalist מקומי (localStorage,
// לא state בצד-שרת - נוחות פר-דפדפן, לא הגדרה שצריך לסנכרן), 5 ערכים אחרונים
// לכל שדה, ללא כפילויות (ערך שכבר קיים עולה לראש הרשימה במקום להתווסף שוב).
const VE_HISTORY_FIELD_IDS = ["veOutputTemplate", "veLutPath", "veWatermarkPath", "vePipPath", "veChromakeyColor", "veChromakeyBgColor"];

function _veHistoryKey(id) { return "veFieldHistory_" + id; }

function _veHistoryValues(id) {
  try { return JSON.parse(localStorage.getItem(_veHistoryKey(id)) || "[]"); } catch (e) { return []; }
}

// item: היסטוריית ערכים לכל שדות הטקסט - לא רק לרשימה הקבועה: כל שדה-טקסט
// בפאנל (חוץ משדות-זמן, גופנים - שלהם datalist של גופני-המערכת - ושם-פרופיל).
function _veHistoryFieldIds() {
  const ids = new Set(VE_HISTORY_FIELD_IDS);
  for (const input of document.querySelectorAll('#veCategories input[type="text"][id]')) {
    if (input.hidden || input.classList.contains("ve-time") || input.hasAttribute("data-ve-font") || input.id === "veProfileName") continue;
    ids.add(input.id);
  }
  return Array.from(ids);
}

function _setupVeFieldHistory() {
  for (const id of _veHistoryFieldIds()) {
    const input = document.getElementById(id);
    if (!input) continue;
    const listId = id + "History";
    let datalist = document.getElementById(listId);
    if (!datalist) {
      datalist = document.createElement("datalist");
      datalist.id = listId;
      document.body.appendChild(datalist);
      input.setAttribute("list", listId);
    }
    _renderVeFieldHistoryOptions(id, datalist);
    input.addEventListener("change", () => {
      const value = input.value.trim();
      if (!value) return;
      let values = _veHistoryValues(id).filter(v => v !== value);
      values.unshift(value);
      values = values.slice(0, 5);
      try { localStorage.setItem(_veHistoryKey(id), JSON.stringify(values)); } catch (e) { /* פרטי/מוגבל - לא קריטי */ }
      _renderVeFieldHistoryOptions(id, datalist);
    });
  }
}

function _renderVeFieldHistoryOptions(id, datalist) {
  datalist.innerHTML = "";
  for (const value of _veHistoryValues(id)) {
    const opt = document.createElement("option");
    opt.value = value;
    datalist.appendChild(opt);
  }
}

// item: בחירת פרופיל אחרונה נשמרת בין ריענונים - localStorage (פר-דפדפן),
// נכתב רק אחרי שה-select כבר עבר את בדיקת אישור-לפני-מעבר הקיימת (לא נשמר
// ניסיון-בחירה שהמשתמש בסוף ביטל).
function _restoreVeLastProfileSelection() {
  const select = document.getElementById("vePreset");
  // item 63: פרופיל ברירת-מחדל מפורש גובר על "הבחירה האחרונה" (שהיא רק זיכרון מרומז).
  const defaultName = Object.entries(state.videoEditorProfileMeta || {}).find(([, meta]) => meta.is_default);
  let target = defaultName ? "profile:" + defaultName[0] : null;
  if (!target) {
    try { target = localStorage.getItem("veLastProfileValue"); } catch (e) { return; }
  }
  if (!target) return;
  if (!Array.from(select.options).some(opt => opt.value === target)) return;
  select.value = target;
  applyVideoEditorPreset();
}

// item: תקציר-מצב + שינויים לא-שמורים - מעגל-רענון תקופתי משותף (זול: רק
// DOM queries על widgets קיימים, בלי fetch/I/O), אותו עיקרון כמו הדסקטופ
// (ui/settings_tab.py's _start_periodic_ui_refresh) - עדיף על trace/onchange
// נפרד ל-45+ שדות.
setInterval(() => {
  if (!document.getElementById("videoEditorOptions").hidden) {
    _veRefreshAllDerivedUi();
    updateUnsavedIndicator();
    updateChangedSinceRunIndicator();
  }
}, 1500);

// item: תיבת העדפות לכל פרופיל - מיפוי field_key (PROFILE_FIELDS) -> {id, label}
// לבניית ה-widget ה'משתף' בתיבת "⭐ מועדפים" (זהה בעיקרון ל-settings_tab.py's
// _favorite_field_registry - אותו הרעיון, מנגנון פשוט יותר כאן כי אלמנטי DOM
// אמיתיים ניתנים לשכפול/סנכרון גנרית (ראו buildFavoriteMirror/syncMirror),
// בלי צורך להבחין entry/switch/option כמו ב-Tkinter).
// item: מונח קצר במקום רצף-מילים - התוויות כאן זהות למונחים הקצרים ב-HTML
// למעלה ובFIELD_HELP הפייתוני (utils/video_editor_field_help.py) - לא
// מדויק-אחד-לאחד אוטומטי (JS לא יכול לייבא ישירות מ-Python), אבל אותו
// ניסוח בדיוק בכוונה, כדי שמונח של שדה יהיה זהה בין הקטגוריה המקורית שלו
// למועדפים/דיאלוג-הבחירה.
const VE_FAVORITABLE_FIELDS = {
  watermark_path: {id: "veWatermarkPath", label: "קובץ סימן מים (Watermark)"},
  watermark_position: {id: "veWatermarkPosition", label: "מיקום סימן מים (Watermark)"},
  watermark_opacity: {id: "veWatermarkOpacity", label: "שקיפות סימן מים (Watermark)"},
  watermark_scale: {id: "veWatermarkScale", label: "גודל סימן מים (Watermark)"},
  remove_watermark_position: {id: "veRemoveWatermarkPosition", label: "מחיקת סימן מים (Watermark)"},
  pip_path: {id: "vePipPath", label: "קובץ PiP"},
  pip_position: {id: "vePipPosition", label: "מיקום PiP"},
  pip_scale: {id: "vePipScale", label: "גודל PiP"},
  pip_opacity: {id: "vePipOpacity", label: "שקיפות PiP"},
  vertical: {id: "veVertical", label: "פורמט אנכי"},
  smart_crop: {id: "veSmartCrop", label: "קרופ חכם"},
  smart_crop_face: {id: "veSmartCropFace", label: "קרופ חכם לפי פנים"},
  blur_background: {id: "veBlurBackground", label: "רקע מטושטש"},
  preserve_resolution: {id: "vePreserveResolution", label: "שימור רזולוציית מקור"},
  trim_start: {id: "veTrimStart", label: "התחלת חיתוך"},
  trim_duration: {id: "veTrimDuration", label: "אורך חיתוך"},
  trim_silence: {id: "veTrimSilence", label: "חיתוך שקט אוטומטי"},
  target_seconds: {id: "veTargetSeconds", label: "אורך יעד לטיימלאפס"},
  keep_audio: {id: "veKeepAudio", label: "שמירת אודיו"},
  captions: {id: "veCaptions", label: "כתוביות אוטומטיות"},
  captions_translate: {id: "veCaptionsTranslate", label: "תרגום כתוביות"},
  caption_font: {id: "veCaptionFont", label: "גופן כתוביות"},
  caption_font_size: {id: "veCaptionFontSize", label: "גודל גופן כתוביות"},
  caption_color: {id: "veCaptionColor", label: "צבע כתוביות"},
  caption_position: {id: "veCaptionPosition", label: "מיקום כתוביות"},
  fade_in_seconds: {id: "veFadeInSeconds", label: "Fade-in"},
  fade_out_seconds: {id: "veFadeOutSeconds", label: "Fade-out"},
  remove_ranges: {id: "veRemoveRanges", label: "חיתוך כמה טווחים"},
  replace_audio_path: {id: "veReplaceAudioPath", label: "החלפת פס קול"},
  text: {id: "veText", label: "כיתוב טקסט קבוע"},
  text_position: {id: "veTextPosition", label: "מיקום טקסט"},
  text_font: {id: "veTextFont", label: "גופן טקסט"},
  text_font_size: {id: "veTextFontSize", label: "גודל טקסט"},
  text_color: {id: "veTextColor", label: "צבע טקסט"},
  loudnorm: {id: "veLoudnorm", label: "נרמול עוצמת קול"},
  loudnorm_target: {id: "veLoudnormTarget", label: "יעד עוצמת קול (LUFS)"},
  denoise: {id: "veDenoise", label: "הפחתת רעש"},
  sharpen: {id: "veSharpen", label: "חידוד"},
  thumbnail: {id: "veThumbnail", label: "תמונה ממוזערת"},
  codec: {id: "veCodec", label: "קידוד יצוא"},
  fps: {id: "veFps", label: "קצב פריימים (FPS)"},
  lut_path: {id: "veLutPath", label: "קובץ LUT"},
  auto_levels: {id: "veAutoLevels", label: "מתיחת בהירות אוטומטית"},
  noise_gate: {id: "veNoiseGate", label: "שער רעש"},
  remove_mid_silence: {id: "veRemoveMidSilence", label: "הסרת שקט באמצע"},
  stabilize: {id: "veStabilize", label: "ייצוב וידאו"},
  chromakey: {id: "veChromakey", label: "כרומה קי"},
  chromakey_color: {id: "veChromakeyColor", label: "צבע להסרה (כרומה קי)"},
  chromakey_bg_color: {id: "veChromakeyBgColor", label: "צבע רקע חלופי"},
  no_suffix: {id: "veNoSuffix", label: "בלי סיומת שם-קובץ"},
  parallel: {id: "veParallel", label: "קידוד מקבילי"},
  max_concurrent_nvenc: {id: "veMaxConcurrentNvenc", label: "מגבלת NVENC מקבילי"},
  effort: {id: "veEffort", label: "דרגת מאמץ"},
  container: {id: "veContainer", label: "מיכל יצוא"},
  output_template: {id: "veOutputTemplate", label: "תבנית שם קובץ"},
  validate_only: {id: "veValidateOnly", label: "בדיקה בלבד"},
  notify_per_file: {id: "veNotifyPerFile", label: "התראה לכל קובץ"},
  export_report: {id: "veExportReport", label: "ייצוא דוח קידוד"},
  number_videos: {id: "veNumberVideos", label: "מספור סרטונים ברצף"},
  number_prefix: {id: "veNumberPrefix", label: "קידומת מספור"},
  number_start: {id: "veNumberStart", label: "מספר התחלתי"},
};

// item: פער CLI→Web (וכל שדה חדש מכאן והלאה) - רישום גנרי של id/סוג/תווית לכל
// שדה, כדי ש-_applyVideoEditorFields/_collectRunOptions/מועדפים/איפוס-לשדה
// יטפלו בו בלולאה אחת - בלי לשכפל עוד שלוש-ארבע שורות ידניות לכל שדה חדש
// (כמו שהשדות הוותיקים למעלה עדיין עושים). kind: bool (checkbox), str
// (text/select), float/int (number/range - ריק נשלח כ-null, "לא הוגדר").
// ברירת המחדל לשדה חסר (פרופיל ישן) היא הערך שה-HTML נטען איתו
// (_veFieldDefaults), בדיוק כמו "איפוס לשדה בודד".
const VE_GENERIC_FIELDS = {
  hwaccel: {id: "veHwaccel", kind: "bool", label: "פייפליין GPU מלא"},
  hwaccel_decode: {id: "veHwaccelDecode", kind: "bool", label: "פענוח מואץ-GPU (NVDEC)"},
  smooth_fps: {id: "veSmoothFps", kind: "bool", label: "אינטרפולציה חלקה"},
  target_size_mb: {id: "veTargetSizeMb", kind: "float", label: "יעד גודל קובץ (MB)"},
  force: {id: "veForce", kind: "bool", label: "רנדר מחדש"},
  preview_only: {id: "vePreviewOnly", kind: "bool", label: "תצוגה מקדימה בלבד"},
  nvenc_cq: {id: "veNvencCq", kind: "int", label: "איכות NVENC (CQ)"},
  nvenc_preset: {id: "veNvencPreset", kind: "str", label: "פריסט NVENC"},
  chromakey_similarity: {id: "veChromakeySimilarity", kind: "float", label: "רגישות כרומה-קי"},
  chromakey_blend: {id: "veChromakeyBlend", kind: "float", label: "החלקת קצוות כרומה-קי"},
  remove_watermark_width_fraction: {id: "veRemoveWatermarkWidthFraction", kind: "float", label: "רוחב אזור המחיקה"},
  remove_watermark_height_fraction: {id: "veRemoveWatermarkHeightFraction", kind: "float", label: "גובה אזור המחיקה"},
  concat_mode: {id: "veConcatMode", kind: "bool", label: "איחוד קטעים"},
  concat_transition: {id: "veConcatTransition", kind: "str", label: "סוג מעבר"},
  concat_transition_duration: {id: "veConcatTransitionDuration", kind: "float", label: "משך מעבר (שניות)"},
  concat_output_name: {id: "veConcatOutputName", kind: "str", label: "שם קובץ האיחוד"},
};
for (const [key, meta] of Object.entries(VE_GENERIC_FIELDS)) {
  VE_FAVORITABLE_FIELDS[key] = {id: meta.id, label: meta.label};
}

function _applyGenericVeFields(fields) {
  for (const [key, meta] of Object.entries(VE_GENERIC_FIELDS)) {
    const el = document.getElementById(meta.id);
    if (!el) continue;
    const raw = fields[key];
    if (meta.kind === "json") {
      // גל 7ב: ערך מובנה (רשימת שכבות) - נשמר כ-JSON בשדה נסתר, העורך נבנה ממנו מחדש
      el.value = JSON.stringify(Array.isArray(raw) ? raw : []);
      if (typeof meta.onApply === "function") meta.onApply();
      continue;
    }
    if (meta.kind === "bool") {
      // ערך חסר (פרופיל ישן, מלפני שהשדה נוסף) -> ברירת המחדל של ה-HTML, לא "כבוי"
      // (חשוב לשדות שברירת המחדל שלהם דלוקה, כמו "כולל תתי-תיקיות").
      el.checked = (raw === null || raw === undefined) ? !!(_veFieldDefaults && _veFieldDefaults[meta.id]) : !!raw;
      continue;
    }
    const fallback = (_veFieldDefaults && meta.id in _veFieldDefaults) ? _veFieldDefaults[meta.id] : "";
    el.value = (raw === null || raw === undefined) ? fallback : raw;
  }
  _veRefreshRangeLabels();
  onVeConcatModeToggled(true);
  updateVeCodecDependentRows();
  if (typeof _veSyncEnhancedInputs === "function" && document.getElementById("veTrimSliderBox")) _veSyncEnhancedInputs();
}

function _collectGenericVeFields() {
  const out = {};
  for (const [key, meta] of Object.entries(VE_GENERIC_FIELDS)) {
    const el = document.getElementById(meta.id);
    if (!el) continue;
    if (meta.kind === "bool") out[key] = el.checked;
    else if (meta.kind === "json") { try { out[key] = JSON.parse(el.value || "[]"); } catch (e) { out[key] = []; } }
    else if (meta.kind === "float") out[key] = el.value === "" ? null : parseFloat(el.value);
    else if (meta.kind === "int") out[key] = el.value === "" ? null : parseInt(el.value, 10);
    else out[key] = el.value;
  }
  return out;
}

// תווית-ערך ליד סליידר (<span class="ve-range-value" data-for="<id>">) - גנרית
// לכל סליידר חדש, במקום oninput ייעודי לכל אחד כמו בסליידרים הוותיקים.
function _veFormatRangeValue(el) {
  const value = parseFloat(el.value);
  if (!Number.isFinite(value)) return "";
  if (el.dataset.veValueFormat === "percent") return `${Math.round(value * 100)}%`;
  if (el.dataset.veValueFormat === "db") return `${value > 0 ? "+" : ""}${value.toFixed(1)} dB`;  // גל 25: EQ
  return value.toFixed(2);
}

function _veRefreshRangeLabels() {
  for (const span of document.querySelectorAll("#videoEditorOptions .ve-range-value[data-for]")) {
    const el = document.getElementById(span.dataset.for);
    if (el) span.textContent = _veFormatRangeValue(el);
  }
}

// item: פער CLI→Web - פריסט/CQ של NVENC רלוונטיים רק ל-HEVC/AV1 (מוסתרים עם H.264).
function updateVeCodecDependentRows() {
  const isNvenc = document.getElementById("veCodec").value !== "h264";
  for (const row of document.querySelectorAll("#videoEditorOptions .ve-nvenc-only")) row.hidden = !isNvenc;
  for (const row of document.querySelectorAll("#videoEditorOptions .ve-h264-only")) row.hidden = isNvenc;
}

function _favoriteFieldKeys() {
  return (document.getElementById("veFavoriteFields").value || "").split(",").map(s => s.trim()).filter(Boolean);
}

function syncMirror(mirror, original) {
  // מסונכרן משני הכיוונים: שינוי מה-mirror מעדכן את המקור *וגם* מפעיל את
  // ה-onchange/oninput המקוריים שלו (dispatchEvent, לא רק original.value=) -
  // כדי שתופעות-לוואי קיימות (updateWatermarkPreview() וכו') עדיין יקרו.
  // שינוי מהמקור (מכל מקור - כתיבה ישירה, טעינת פרופיל) מעדכן את ה-mirror.
  const isCheckbox = original.type === "checkbox";
  const copy = (from, to) => { if (isCheckbox) to.checked = from.checked; else to.value = from.value; };
  copy(original, mirror);
  const mirrorEvent = (original.tagName === "SELECT" || isCheckbox) ? "change" : "input";
  mirror.addEventListener(mirrorEvent, () => {
    copy(mirror, original);
    original.dispatchEvent(new Event("input", {bubbles: true}));
    original.dispatchEvent(new Event("change", {bubbles: true}));
  });
  original.addEventListener("input", () => copy(original, mirror));
  original.addEventListener("change", () => copy(original, mirror));
}

function buildFavoriteMirror(fieldKey, isFirst, isLast) {
  const meta = VE_FAVORITABLE_FIELDS[fieldKey];
  if (!meta) return null;  // שדה ששמו שונה/הוסר מאז שנשמר כמועדף - מדולג בשקט
  const original = document.getElementById(meta.id);
  if (!original) return null;

  const row = document.createElement("div");
  row.className = "ve-row ve-favorite-row";

  // item: גרירה אמיתית למועדפים - עכשיו שהדסקטופ קפוא (אין יותר צורך במנגנון
  // שעובד זהה בשתי הפלטפורמות), HTML5 native drag-and-drop זמין בלי עלות -
  // ▲/▼ נשארים גם כן (לא הוסרו) כגיבוי נגיש למקלדת/מגע, לא רק גרירה.
  row.draggable = true;
  row.dataset.fieldKey = fieldKey;
  row.addEventListener("dragstart", (e) => {
    row.classList.add("dragging");
    e.dataTransfer.setData("text/plain", fieldKey);
    e.dataTransfer.effectAllowed = "move";
  });
  row.addEventListener("dragend", () => row.classList.remove("dragging"));
  row.addEventListener("dragover", (e) => { e.preventDefault(); row.classList.add("drag-over"); });
  row.addEventListener("dragleave", () => row.classList.remove("drag-over"));
  row.addEventListener("drop", (e) => {
    e.preventDefault();
    row.classList.remove("drag-over");
    const draggedKey = e.dataTransfer.getData("text/plain");
    if (draggedKey && draggedKey !== fieldKey) reorderFavoriteBeforeTarget(draggedKey, fieldKey);
  });

  const reorderBox = document.createElement("div");
  reorderBox.className = "ve-favorite-reorder";
  const upBtn = document.createElement("button");
  upBtn.type = "button"; upBtn.textContent = "▲"; upBtn.disabled = !!isFirst;
  upBtn.onclick = () => moveFavorite(fieldKey, -1);
  const downBtn = document.createElement("button");
  downBtn.type = "button"; downBtn.textContent = "▼"; downBtn.disabled = !!isLast;
  downBtn.onclick = () => moveFavorite(fieldKey, 1);
  reorderBox.appendChild(upBtn); reorderBox.appendChild(downBtn);
  row.appendChild(reorderBox);

  const label = document.createElement("label");
  label.textContent = meta.label;
  row.appendChild(label);

  let mirror;
  if (original.tagName === "SELECT") {
    mirror = document.createElement("select");
    mirror.innerHTML = original.innerHTML;
  } else {
    mirror = document.createElement("input");
    mirror.type = original.type;
    if (original.type === "range") {
      mirror.min = original.min; mirror.max = original.max; mirror.step = original.step;
      mirror.style.width = "100px";
    }
  }
  syncMirror(mirror, original);
  row.appendChild(mirror);
  return row;
}

function moveFavorite(fieldKey, direction) {
  const keys = _favoriteFieldKeys();
  const i = keys.indexOf(fieldKey);
  const j = i + direction;
  if (i === -1 || j < 0 || j >= keys.length) return;
  [keys[i], keys[j]] = [keys[j], keys[i]];
  document.getElementById("veFavoriteFields").value = keys.join(",");
  rebuildFavoritesBox();
}

function reorderFavoriteBeforeTarget(draggedKey, targetKey) {
  const keys = _favoriteFieldKeys();
  const from = keys.indexOf(draggedKey);
  if (from === -1) return;
  keys.splice(from, 1);
  const to = keys.indexOf(targetKey);
  if (to === -1) { keys.push(draggedKey); } else { keys.splice(to, 0, draggedKey); }
  document.getElementById("veFavoriteFields").value = keys.join(",");
  rebuildFavoritesBox();
}

function rebuildFavoritesBox() {
  const container = document.getElementById("veFavoritesBox");
  if (!container) return;  // סידור מחדש: הקופסה הוחלפה ב"✎ רק מה ששיניתי"
  container.innerHTML = "";
  const keys = _favoriteFieldKeys();
  if (keys.length === 0) {
    const hint = document.createElement("div");
    hint.className = "hint";
    hint.style.display = "block";
    hint.textContent = "אין מועדפים כרגע - כל הגדרה מסומנת (✓) או שונתה מברירת המחדל תצטרף לכאן אוטומטית.";
    container.appendChild(hint);
    return;
  }
  keys.forEach((key, index) => {
    const row = buildFavoriteMirror(key, index === 0, index === keys.length - 1);
    if (row) container.appendChild(row);
  });
}

// item: מועדפים אוטומטיים - מחליף לגמרי את הבחירה הידנית הקודמת ("⭐ הגדר
// מועדפים..."): שדה checkbox מצטרף למועדפים ברגע שהוא מסומן (✓), ויוצא ברגע
// שהוא מבוטל; כל שדה אחר (טקסט/מספר/select/range) מצטרף ברגע שהערך שלו שונה
// מברירת המחדל שנלכדה ב-_veFieldDefaults (אותו מקור בדיוק כמו "איפוס לשדה
// בודד"), ויוצא ברגע שהוא חוזר לברירת המחדל בדיוק - מיידי (על כל input/change
// בפאנל, לא רק בשמירה), לא רק בפועל כשנשמר כפרופיל. שומר על סדר-התצוגה
// הקיים של שדות שכבר במועדפים (כולל סידור-ידני שנעשה בגרירה) - שדה חדש
// שמצטרף נוסף בסוף הרשימה, לא זורק את הסדר הקיים מחדש.
// item: מועדפים אוטומטיים - שדות שאין להם שום השפעה בלי שדה-נתיב אחר מוגדר
// (מיקום/שקיפות/גודל של Watermark/PiP רק "עושים משהו" כש-watermark_path/
// pip_path בפועל לא ריקים) - גם אם ערכם שונה מברירת המחדל שלהם, הם לא
// אמורים להישאר במועדפים אחרי שהנתיב שממנו הם תלויים נמחק, כי בפועל אין
// עוד watermark/PiP בכלל להחיל עליו את ההגדרה הזאת.
const VE_FAVORITE_DEPENDS_ON = {
  watermark_position: "veWatermarkPath",
  watermark_opacity: "veWatermarkPath",
  watermark_scale: "veWatermarkPath",
  pip_position: "vePipPath",
  pip_opacity: "vePipPath",
  pip_scale: "vePipPath",
  text_position: "veText",
  text_font: "veText",
  text_font_size: "veText",
  text_color: "veText",
};

function _computeAutoFavoriteKeys() {
  const keys = [];
  // בעריכת קליפ שדות הזמן מציגים את הקליפ, לא את המתכון - המועדפים נגזרים מהמתכון
  // (נמצא ב-CI: חישוב מושהה שנפל בזמן עריכת קליפ הוסיף trim_start וסימן שינוי בפרופיל)
  const recipeTime = _veRecipeTimeValues();
  for (const [fieldKey, meta] of Object.entries(VE_FAVORITABLE_FIELDS)) {
    const el = document.getElementById(meta.id);
    if (!el || !_veFieldDefaults || !(el.id in _veFieldDefaults)) continue;
    const value = recipeTime && fieldKey in recipeTime ? recipeTime[fieldKey] : el.value;
    let isFavorite = el.type === "checkbox" ? el.checked : String(value) !== String(_veFieldDefaults[el.id]);
    const dependsOnId = VE_FAVORITE_DEPENDS_ON[fieldKey];
    if (isFavorite && dependsOnId) {
      const dependsOnEl = document.getElementById(dependsOnId);
      if (!dependsOnEl || !dependsOnEl.value.trim()) isFavorite = false;
    }
    if (isFavorite) keys.push(fieldKey);
  }
  return keys;
}

function syncAutoFavorites() {
  const computed = new Set(_computeAutoFavoriteKeys());
  const existingOrder = _favoriteFieldKeys().filter(k => computed.has(k));
  const newlyAdded = Array.from(computed).filter(k => !existingOrder.includes(k));
  const nextKeys = [...existingOrder, ...newlyAdded];
  const nextValue = nextKeys.join(",");
  if (nextValue === document.getElementById("veFavoriteFields").value) return;
  document.getElementById("veFavoriteFields").value = nextValue;
  rebuildFavoritesBox();
}

async function saveVideoEditorProfile() {
  const nameInput = document.getElementById("veProfileName");
  let name = nameInput.value.trim();
  // item: "💾 שמור" גם מהפס הצף/Ctrl+S - אם שדה השם (בקטגוריית הפרופילים) ריק,
  // שואלים כאן במקום לדרוש לגלול אליו קודם.
  if (!name) {
    const typed = await vePrompt("שם לסגנון החדש:");
    if (typed === null) return;
    name = typed.trim();
  }
  if (!name) { alert("צריך לתת שם לסגנון."); return; }
  const settings = _collectRunOptions();
  const res = await fetch("/api/video_editor_profiles", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, settings }),
  });
  if (!res.ok) { alert("שמירת הסגנון נכשלה."); return; }
  nameInput.value = "";
  await loadVideoEditorProfiles();
  document.getElementById("vePreset").value = "profile:" + name;
  state.vePresetPrevious = "profile:" + name;
  _setVeProfileButtonsVisible(true);
  _loadAndShowProfileMeta(name);
  captureVideoEditorBaseline();
  // item: הודעת אישור שמירת/עדכון פרופיל - בלי זה, לחיצה על "שמור פרופיל" לא
  // נתנה שום משוב גלוי (רק הופעת התפריט/כפתורים, קל לפספס).
  alert(`הסגנון "${name}" נשמר בהצלחה.`);
}

// item: אפשרות לעדכן פרופיל קיים - שומר מחדש (דורס, אותו /api/video_editor_profiles
// POST ש-saveVideoEditorProfile משתמש בו - save_profile בצד השרת כבר דורס
// אם השם קיים) את הפרופיל האישי שנבחר כרגע עם ההגדרות הנוכחיות של הטופס,
// בלי לדרוש הקלדת השם שוב.
async function updateVideoEditorProfile() {
  const rawValue = document.getElementById("vePreset").value;
  if (!rawValue.startsWith("profile:")) return;
  const name = rawValue.slice("profile:".length);
  const settings = _collectRunOptions();
  const res = await fetch("/api/video_editor_profiles", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, settings }),
  });
  if (!res.ok) { alert("עדכון הסגנון נכשל."); return; }
  await loadVideoEditorProfiles();
  document.getElementById("vePreset").value = "profile:" + name;
  state.vePresetPrevious = "profile:" + name;
  captureVideoEditorBaseline();
  alert(`הסגנון "${name}" עודכן בהצלחה.`);
}

async function deleteVideoEditorProfile() {
  const rawValue = document.getElementById("vePreset").value;
  if (!rawValue.startsWith("profile:")) return;
  const name = rawValue.slice("profile:".length);
  if (!(await veConfirm(`למחוק את הסגנון "${name}"?\nהוא יועבר לסל המחזור (🗑️) ואפשר יהיה להחזיר אותו משם.`, {danger: true}))) return;
  await fetch("/api/video_editor_profiles/" + encodeURIComponent(name), { method: "DELETE" });
  await loadVideoEditorProfiles();
  document.getElementById("vePreset").value = "";
  state.vePresetPrevious = "";
  state.veBaseline = null;
  updateUnsavedIndicator();
  _setVeProfileButtonsVisible(false);
  document.getElementById("veProfileMetaInfo").textContent = "";
}

// item: שינוי שם לפרופיל - prompt() המובנה של הדפדפן (בניגוד לדסקטופ,
// שם ctk.CTkInputDialog לא תומך בערך-ברירת-מחדל מוכן, כאן prompt() כן) עם
// שם הפרופיל הנוכחי כערך התחלתי. השרת (rename_profile) זה שדוחה שם ריק/תפוס.
async function renameVideoEditorProfile() {
  const rawValue = document.getElementById("vePreset").value;
  if (!rawValue.startsWith("profile:")) return;
  const oldName = rawValue.slice("profile:".length);
  const newName = await vePrompt("שם חדש לסגנון:", {value: oldName});
  if (newName === null) return;  // ביטול
  if (!newName.trim() || newName.trim() === oldName) return;
  const res = await fetch("/api/video_editor_profiles/" + encodeURIComponent(oldName) + "/rename", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ new_name: newName }),
  });
  if (!res.ok) { alert((await res.json()).error || "שינוי השם נכשל."); return; }
  const data = await res.json();
  await loadVideoEditorProfiles();
  document.getElementById("vePreset").value = "profile:" + data.name;
}

// item: שכפול פרופיל / "שמור בשם..." - בניגוד ל-updateVideoEditorProfile
// (דורס את הפרופיל הנוכחי), זה תמיד יוצר עותק חדש ועובר אליו - המקור נשאר
// כפי שהיה.
async function duplicateVideoEditorProfile() {
  const rawValue = document.getElementById("vePreset").value;
  if (!rawValue.startsWith("profile:")) return;
  const sourceName = rawValue.slice("profile:".length);
  const newName = await vePrompt(`שם לעותק החדש (משוכפל מ-"${sourceName}"):`, {value: sourceName + " (עותק)"});
  if (newName === null) return;  // ביטול
  if (!newName.trim()) return;
  const res = await fetch("/api/video_editor_profiles/" + encodeURIComponent(sourceName) + "/duplicate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ new_name: newName }),
  });
  if (!res.ok) { alert((await res.json()).error || "שכפול הסגנון נכשל."); return; }
  const data = await res.json();
  await loadVideoEditorProfiles();
  document.getElementById("vePreset").value = "profile:" + data.name;
  applyVideoEditorPreset();
}

// item: ייצוא/ייבוא פרופיל - מוריד קובץ JSON (שם+הגדרות, לא metadata-שימוש
// שלא רלוונטית למכונה/משתמש אחר) דרך Blob - אין endpoint ייעודי-הורדה בצד
// השרת, ה-JSON הרגיל שה-API כבר מחזיר מספיק.
async function exportVideoEditorProfile() {
  const rawValue = document.getElementById("vePreset").value;
  if (!rawValue.startsWith("profile:")) return;
  const name = rawValue.slice("profile:".length);
  const res = await fetch("/api/video_editor_profiles/" + encodeURIComponent(name) + "/export");
  if (!res.ok) { alert("ייצוא הסגנון נכשל."); return; }
  const data = await res.json();
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `video_editor_profile_${name}.json`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

function openImportProfileDialog() { document.getElementById("veImportProfileFile").click(); }

async function _handleImportProfileFileChosen(event) {
  const file = event.target.files[0];
  event.target.value = "";  // מאפשר לייבא שוב את אותו קובץ שוב ברצף
  if (!file) return;
  let parsed;
  try { parsed = JSON.parse(await file.text()); }
  catch (e) { alert("קובץ לא תקין - לא JSON."); return; }
  const suggestedName = (parsed && typeof parsed.name === "string" && parsed.name) || file.name.replace(/\.json$/i, "");
  const settings = (parsed && typeof parsed.settings === "object" && parsed.settings) ? parsed.settings : parsed;
  const name = await vePrompt("שם לסגנון המיובא:", {value: suggestedName});
  if (name === null || !name.trim()) return;
  let res = await fetch("/api/video_editor_profiles/import", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, settings }),
  });
  if (res.status === 400) {
    const err = (await res.json()).error || "";
    if (err.includes("כבר קיים") && await veConfirm(`סגנון בשם "${name}" כבר קיים - לדרוס אותו?`, {danger: true, okLabel: "דרוס"})) {
      res = await fetch("/api/video_editor_profiles/import", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, settings, overwrite: true }),
      });
    } else if (!err.includes("כבר קיים")) {
      alert(err || "ייבוא הסגנון נכשל.");
      return;
    }
  }
  if (!res.ok) { alert((await res.json()).error || "ייבוא הסגנון נכשל."); return; }
  const data = await res.json();
  await loadVideoEditorProfiles();
  document.getElementById("vePreset").value = "profile:" + data.name;
  applyVideoEditorPreset();
}

// item: חותמת "בשימוש לאחרונה" + מספר הרצות - מוצג ליד בורר הפרופילים כשפרופיל
// אישי נבחר. run_count=0/last_used_at=null (פרופיל שעדיין לא הורץ בפועל) לא
// מוצג בכלל, לא כ"אף פעם" מבלבל.
async function _loadAndShowProfileMeta(name) {
  const info = document.getElementById("veProfileMetaInfo");
  const pullBtn = document.getElementById("vePullParentBtn");
  const notesRow = document.getElementById("veProfileNotesRow");
  info.textContent = "";
  pullBtn.hidden = true;
  notesRow.hidden = true;
  // מעבר מהיר בין פרופילים: המידע של הפרופיל הקודם לא מוצג ליד הנוכחי
  const request = uiLatest("ve:profile-meta");
  let res, meta;
  try {
    res = await fetch("/api/video_editor_profiles/" + encodeURIComponent(name) + "/meta", {signal: request.signal});
    if (!res.ok) return;
    meta = await res.json();
  } catch (e) { return; }
  if (!request.current()) return;
  const parts = [];
  if (meta.is_default) parts.push("⭐ ברירת המחדל");
  if (meta.run_count) {
    const when = meta.last_used_at ? new Date(meta.last_used_at).toLocaleString("he-IL") : "";
    parts.push(`🕒 בשימוש לאחרונה: ${when} · ${meta.run_count} הרצות`);
  }
  if (meta.tags && meta.tags.length) parts.push("🏷️ #" + meta.tags.join(" #"));
  // item 68: ירושה - "מבוסס על X, שונה ב-Y" (Y = השדות שהפרופיל הזה דורס בפועל)
  if (meta.parent) {
    const parentExists = !!(state.videoEditorProfiles || {})[meta.parent];
    const overridden = (meta.overridden_fields || []).map(f => (VE_FAVORITABLE_FIELDS[f] || {}).label || f);
    parts.push(`🧬 מבוסס על "${meta.parent}"${parentExists ? "" : " (ההורה נמחק)"}` + (overridden.length ? ` · שונה ב: ${overridden.join(", ")}` : " · זהה להורה"));
    pullBtn.hidden = !parentExists;
  }
  info.textContent = parts.join(" · ");
  if (meta.notes) { document.getElementById("veProfileNotesText").textContent = "📝 " + meta.notes; notesRow.hidden = false; }
  document.getElementById("veDefaultProfileBtn").textContent = meta.is_default ? "☆ בטל ברירת מחדל" : "⭐ קבע כברירת מחדל";
}

// item: השוואת שני פרופילים - {field: [value_a, value_b]} רק לשדות שונים,
// מתויגים במונח הקצר מהמקראה (_fieldHelpCache, אותו מקור כמו VE_FAVORITABLE_FIELDS)
// כשיש כזה, אחרת שם-השדה הגולמי.
async function openCompareProfilesDialog() {
  if (!_fieldHelpCache) {
    const res = await fetch("/api/video_editor/field_help");
    _fieldHelpCache = await res.json();
  }
  const names = Object.keys(state.videoEditorProfiles || {}).sort((a, b) => a.localeCompare(b, "he"));
  for (const selectId of ["compareProfileA", "compareProfileB"]) {
    const select = document.getElementById(selectId);
    // שמות פרופילים מגיעים גם מקישורי שיתוף של אחרים - כטקסט, לא כ-HTML
    select.replaceChildren(...names.map(n => new Option(n, n)));
  }
  if (names.length > 1) document.getElementById("compareProfileB").value = names[1];
  document.getElementById("compareProfilesResult").innerHTML = "";
  document.getElementById("compareProfilesModalBg").classList.add("show");
}

async function _runProfileComparison() {
  const a = document.getElementById("compareProfileA").value;
  const b = document.getElementById("compareProfileB").value;
  const result = document.getElementById("compareProfilesResult");
  if (!a || !b) return;
  if (a === b) { result.innerHTML = "<div style=\"padding:8px\">בחר שני סגנונות שונים.</div>"; return; }
  const request = uiLatest("ve:profile-diff");
  let diff;
  try {
    const res = await fetch(`/api/video_editor_profiles/diff?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`, {signal: request.signal});
    if (res.ok) diff = (await res.json()).diff;
  } catch (e) { if (uiIsAbort(e)) return; }
  if (!request.current()) return;
  if (!diff) { result.innerHTML = "<div style=\"padding:8px\">ההשוואה נכשלה.</div>"; return; }
  const fields = Object.keys(diff);
  result.innerHTML = "";
  if (!fields.length) { result.innerHTML = "<div class=\"empty-msg\">שני הסגנונות זהים בכל השדות.</div>"; return; }
  for (const field of fields) {
    const label = (_fieldHelpCache && _fieldHelpCache[field] && _fieldHelpCache[field].term) || field;
    const [va, vb] = diff[field];
    const row = document.createElement("div");
    row.className = "ve-list-row";
    const text = document.createElement("div");
    const title = document.createElement("div");
    title.style.cssText = "font-weight:700;font-size:13px;margin-bottom:2px";
    title.textContent = label;
    const values = document.createElement("div");
    values.style.cssText = "font-size:12px;display:flex;gap:10px;flex-wrap:wrap";
    values.append(`${a}: ${_veDisplayValue(va)}`, "   ", `${b}: ${_veDisplayValue(vb)}`);
    text.append(title, values);
    // item 65: "מזג שדה" - מעתיק את הערך לפרופיל השני (הפיך דרך היסטוריית הפרופיל).
    const actions = document.createElement("div");
    actions.className = "ve-list-row-actions";
    const toB = document.createElement("button");
    toB.type = "button"; toB.className = "ve-merge-btn"; toB.textContent = `העתק ל-${b} ←`;
    toB.onclick = () => _veMergeProfileField(b, field, va);
    const toA = document.createElement("button");
    toA.type = "button"; toA.className = "ve-merge-btn"; toA.textContent = `→ העתק ל-${a}`;
    toA.onclick = () => _veMergeProfileField(a, field, vb);
    actions.append(toA, toB);
    row.append(text, actions);
    result.appendChild(row);
  }
}

function _veDisplayValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "✓" : "✗";
  if (typeof value === "object") return JSON.stringify(value).slice(0, 80);
  return String(value);
}

async function _veMergeProfileField(target, field, value) {
  const label = (VE_FAVORITABLE_FIELDS[field] || {}).label || field;
  if (!(await veConfirm(`להעתיק את "${label}" = ${_veDisplayValue(value)} לסגנון "${target}"?\n(הגרסה הקודמת נשמרת בהיסטוריה שלו)`))) return;
  const res = await fetch("/api/video_editor_profiles/" + encodeURIComponent(target) + "/set_field", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({field, value}),
  });
  if (!res.ok) { alert((await res.json()).error || "המיזוג נכשל."); return; }
  await loadVideoEditorProfiles();
  if (document.getElementById("vePreset").value === "profile:" + target) applyVideoEditorPreset();
  await _runProfileComparison();
}

function closeCompareProfilesDialog() { document.getElementById("compareProfilesModalBg").classList.remove("show"); }

// item: היסטוריית-שינויים/undo לפרופיל - snapshot-ים קודמים (עד 5), הישן
// ביותר ראשון בשרת אז הופכים לתצוגה כרונולוגית-הפוכה (האחרון קודם) לנוחות.
let _profileHistoryOpenFor = null;

async function openProfileHistoryDialog() {
  const rawValue = document.getElementById("vePreset").value;
  if (!rawValue.startsWith("profile:")) return;
  _profileHistoryOpenFor = rawValue.slice("profile:".length);
  await _renderProfileHistoryList();
  document.getElementById("profileHistoryModalBg").classList.add("show");
}

async function _renderProfileHistoryList() {
  const list = document.getElementById("profileHistoryList");
  uiSkeleton(list, 4, "row");
  const res = await fetch("/api/video_editor_profiles/" + encodeURIComponent(_profileHistoryOpenFor) + "/history");
  const { history } = await res.json();
  if (!history.length) { list.innerHTML = "<div class=\"empty-msg\">אין עדיין היסטוריה לסגנון הזה - נוצרת בכל דריסה של סגנון קיים.</div>"; return; }
  list.innerHTML = "";
  const currentSettings = (state.videoEditorProfiles || {})[_profileHistoryOpenFor] || {};
  for (let i = history.length - 1; i >= 0; i--) {
    const entry = history[i];
    // item 64: diff בין גרסאות - מה השתנה מהגרסה הזו לגרסה שבאה אחריה (או למצב הנוכחי).
    const next = i === history.length - 1 ? currentSettings : history[i + 1];
    const changes = _veProfileChanges(entry, next);
    const when = entry.saved_at ? new Date(entry.saved_at).toLocaleString("he-IL") : "";
    const row = document.createElement("div");
    row.style.cssText = "padding:8px 10px;border-bottom:1px solid var(--border2);display:flex;align-items:flex-start;justify-content:space-between;gap:8px";
    const text = document.createElement("div");
    const label = document.createElement("div");
    label.style.fontSize = "13px";
    label.textContent = `🕒 ${when} (codec: ${entry.codec || "—"})`;
    text.appendChild(label);
    const diffBox = document.createElement("div");
    if (!changes.length) {
      diffBox.className = "ve-diff-line";
      diffBox.textContent = "אין הבדל בהגדרות מול הגרסה שאחריה";
    } else {
      for (const change of changes.slice(0, 8)) {
        const line = document.createElement("div");
        line.className = "ve-diff-line";
        const bold = document.createElement("b");
        bold.textContent = change.label + ": ";
        line.append(bold, `${_veDisplayValue(change.from)} → ${_veDisplayValue(change.to)}`);
        diffBox.appendChild(line);
      }
      if (changes.length > 8) { const more = document.createElement("div"); more.className = "ve-diff-line"; more.textContent = `+ עוד ${changes.length - 8} שינויים`; diffBox.appendChild(more); }
    }
    text.appendChild(diffBox);
    const btn = document.createElement("button");
    btn.type = "button"; btn.textContent = "↩️ שחזר";
    btn.addEventListener("click", () => _revertProfileVersion(i));
    row.appendChild(text); row.appendChild(btn);
    list.appendChild(row);
  }
}

function _veProfileChanges(older, newer) {
  const changes = [];
  const keys = new Set([...Object.keys(older || {}), ...Object.keys(newer || {})]);
  for (const key of keys) {
    if (key === "saved_at" || key === "favorite_fields") continue;
    const a = (older || {})[key], b = (newer || {})[key];
    if (JSON.stringify(a ?? null) === JSON.stringify(b ?? null)) continue;
    changes.push({key, label: (VE_FAVORITABLE_FIELDS[key] || {}).label || key, from: a, to: b});
  }
  return changes;
}

async function _revertProfileVersion(index) {
  if (!(await veConfirm("לשחזר את הסגנון לגרסה הזו? המצב הנוכחי יישמר בהיסטוריה ואפשר יהיה לבטל.", {okLabel: "שחזר"}))) return;
  const res = await fetch("/api/video_editor_profiles/" + encodeURIComponent(_profileHistoryOpenFor) + "/revert", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index }),
  });
  if (!res.ok) { alert((await res.json()).error || "השחזור נכשל."); return; }
  await loadVideoEditorProfiles();
  if (document.getElementById("vePreset").value === "profile:" + _profileHistoryOpenFor) applyVideoEditorPreset();
  await _renderProfileHistoryList();
}

function closeProfileHistoryDialog() { document.getElementById("profileHistoryModalBg").classList.remove("show"); }

function showVeImageResult(path, title) {
  document.getElementById("veImageResultTitle").textContent = title || "🖼️ תצוגה מקדימה";
  document.getElementById("veImageResultImg").src = "/api/watermark_image?path=" + encodeURIComponent(path) + "&t=" + Date.now();
  document.getElementById("veImageResultPath").textContent = path;
  document.getElementById("veImageResultModalBg").classList.add("show");
}

// item: גיבוי אוטומטי מסתובב + "שחזר מגיבוי" - כל גיבוי מציג אילו פרופילים יש
// בו, כדי לדעת *מה* ישוחזר לפני שמשחזרים (לא רק חותמת-זמן עיוורת).
async function openProfileBackupsDialog() {
  await _renderProfileBackupsList();
  document.getElementById("profileBackupsModalBg").classList.add("show");
}

function closeProfileBackupsDialog() { document.getElementById("profileBackupsModalBg").classList.remove("show"); }

async function _renderProfileBackupsList() {
  const list = document.getElementById("profileBackupsList");
  uiSkeleton(list, 3, "row");
  const res = await fetch("/api/video_editor_profile_backups");
  const { backups } = await res.json();
  list.innerHTML = "";
  if (!backups.length) {
    list.innerHTML = '<div class="empty-msg">אין עדיין גיבויים - הראשון ייווצר בשמירה הבאה של סגנון (או בהפעלה הבאה של השרת).</div>';
    return;
  }
  const currentNames = new Set(Object.keys(state.videoEditorProfiles || {}));
  for (const backup of backups) {
    const row = document.createElement("div");
    row.className = "ve-list-row";
    const info = document.createElement("div");
    const when = backup.created_at ? new Date(backup.created_at).toLocaleString("he-IL") : backup.id;
    const missing = backup.profile_names.filter(n => !currentNames.has(n));
    const title = document.createElement("div");
    title.style.fontWeight = "600";
    title.textContent = `🕒 ${when} · ${backup.profile_count} סגנונות` + (missing.length ? ` · ${missing.length} חסרים כרגע` : "");
    const names = document.createElement("div");
    names.style.cssText = "font-size:11px;color:var(--text-muted)";
    names.textContent = backup.profile_names.join(" · ") || "(ריק)";
    info.appendChild(title); info.appendChild(names);
    const actions = document.createElement("div");
    actions.className = "ve-list-row-actions";
    const mergeBtn = document.createElement("button");
    mergeBtn.type = "button"; mergeBtn.textContent = "➕ הוסף חסרים";
    mergeBtn.disabled = !missing.length;
    mergeBtn.onclick = () => _restoreProfileBackup(backup.id, "merge_missing");
    const replaceBtn = document.createElement("button");
    replaceBtn.type = "button"; replaceBtn.textContent = "♻️ החלף הכל";
    replaceBtn.onclick = () => _restoreProfileBackup(backup.id, "replace");
    actions.appendChild(mergeBtn); actions.appendChild(replaceBtn);
    row.appendChild(info); row.appendChild(actions);
    list.appendChild(row);
  }
}

async function _restoreProfileBackup(backupId, mode) {
  const question = mode === "replace"
    ? "להחליף את כל הסגנונות הנוכחיים בגיבוי הזה? (המצב הנוכחי יגובה קודם, אז אפשר לחזור אליו)"
    : "להוסיף מהגיבוי הזה את הסגנונות שחסרים כרגע? סגנונות קיימים לא ישתנו.";
  if (!(await veConfirm(question, {danger: mode === "replace"}))) return;
  const res = await fetch("/api/video_editor_profile_backups/restore", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({id: backupId, mode}),
  });
  const data = await res.json();
  if (!res.ok) { alert(data.error || "השחזור נכשל."); return; }
  await loadVideoEditorProfiles();
  await _renderProfileBackupsList();
  alert(data.restored.length ? `שוחזרו ${data.restored.length} סגנונות: ${data.restored.join(", ")}` : "אין סגנונות חדשים לשחזר מהגיבוי הזה.");
}

// item: מחיקה רכה - סל מחזור לפרופילים.
async function openProfileTrashDialog() {
  await _renderProfileTrashList();
  document.getElementById("profileTrashModalBg").classList.add("show");
}

function closeProfileTrashDialog() { document.getElementById("profileTrashModalBg").classList.remove("show"); }

async function _renderProfileTrashList() {
  const list = document.getElementById("profileTrashList");
  uiSkeleton(list, 3, "row");
  const res = await fetch("/api/video_editor_profile_trash");
  const { entries } = await res.json();
  list.innerHTML = "";
  if (!entries.length) {
    list.innerHTML = '<div class="empty-msg">סל המחזור ריק.</div>';
    return;
  }
  for (const entry of entries) {
    const row = document.createElement("div");
    row.className = "ve-list-row";
    const info = document.createElement("span");
    const when = entry.deleted_at ? new Date(entry.deleted_at).toLocaleString("he-IL") : "";
    info.textContent = `${entry.name} · נמחק ${when}` + (entry.codec ? ` · ${entry.codec}` : "");
    const actions = document.createElement("div");
    actions.className = "ve-list-row-actions";
    const restoreBtn = document.createElement("button");
    restoreBtn.type = "button"; restoreBtn.textContent = "↩️ החזר";
    restoreBtn.onclick = () => _restoreProfileFromTrash(entry);
    const purgeBtn = document.createElement("button");
    purgeBtn.type = "button"; purgeBtn.textContent = "❌ מחק לצמיתות";
    purgeBtn.onclick = () => _purgeProfileTrashEntry(entry);
    actions.appendChild(restoreBtn); actions.appendChild(purgeBtn);
    row.appendChild(info); row.appendChild(actions);
    list.appendChild(row);
  }
}

async function _restoreProfileFromTrash(entry) {
  let newName = null;
  if ((state.videoEditorProfiles || {})[entry.name]) {
    newName = await vePrompt(`כבר קיים סגנון בשם "${entry.name}" - שם לסגנון המשוחזר:`, {value: entry.name + " (משוחזר)"});
    if (newName === null || !newName.trim()) return;
  }
  const res = await fetch("/api/video_editor_profile_trash/" + encodeURIComponent(entry.id) + "/restore", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({new_name: newName}),
  });
  const data = await res.json();
  if (!res.ok) { alert(data.error || "השחזור נכשל."); return; }
  await loadVideoEditorProfiles();
  await _renderProfileTrashList();
}

async function _purgeProfileTrashEntry(entry) {
  if (!(await veConfirm(`למחוק לצמיתות את "${entry.name}" מסל המחזור? (עדיין יישאר עותק בתיקיית הגיבויים)`, {danger: true}))) return;
  const res = await fetch("/api/video_editor_profile_trash/" + encodeURIComponent(entry.id), {method: "DELETE"});
  if (!res.ok) { alert((await res.json()).error || "המחיקה נכשלה."); return; }
  await _renderProfileTrashList();
}

// item: אישור עקבי למחיקה/איפוס - Promise-based (לא confirm() החוסם של הדפדפן),
// אותו מראה לכל פעולה הרסנית בעורך. {danger:true} צובע את כפתור האישור באדום.
// גל 22: קלט טקסט בתוך הדף במקום prompt() של הדפדפן (חוסם, לא מעוצב, לא מתורגם).
// מחזיר את הטקסט, או null בביטול - בדיוק כמו prompt().
// 20.10.2026: <dialog> שנפתח ב-showModal נמצא ב-top layer (מעל כל z-index) ושאר הדף inert - חלון אישור / שאלה שנפתח
// מעליו הוסתר מאחוריו ולא קיבל לחיצות. כל עוד החלון מוצג הוא עובר לתוך ה-dialog המודאלי העליון, ובסגירה חוזר למקומו
// (uiOverModal ב-06-ui-core.js).
function vePrompt(message, options) {
  const opts = options || {};
  return new Promise((resolve) => {
    const bg = document.getElementById("vePromptModalBg");
    const input = document.getElementById("vePromptInput");
    const okBtn = document.getElementById("vePromptOkBtn");
    const cancelBtn = document.getElementById("vePromptCancelBtn");
    document.getElementById("vePromptMessage").textContent = message;
    input.type = opts.type === "password" ? "password" : "text";
    input.value = opts.value ?? "";
    input.placeholder = opts.placeholder || "";
    okBtn.textContent = opts.okLabel || "אישור";
    const restore = uiOverModal(bg);
    const finish = (value) => {
      bg.classList.remove("show");
      restore();
      okBtn.onclick = null; cancelBtn.onclick = null; input.onkeydown = null; bg.onkeydown = null;
      input.value = "";  // סיסמה לא נשארת בשדה אחרי הסגירה
      resolve(value);
    };
    okBtn.onclick = () => finish(input.value);
    cancelBtn.onclick = () => finish(null);
    input.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); finish(input.value); } };
    bg.onkeydown = (e) => { if (e.key === "Escape") { e.preventDefault(); finish(null); } };   // preventDefault: לא לסגור גם את ה-dialog
    bg.classList.add("show");
    input.focus();
    input.select();
  });
}

function veConfirm(message, options) {
  const opts = options || {};
  return new Promise((resolve) => {
    const bg = document.getElementById("veConfirmModalBg");
    document.getElementById("veConfirmMessage").textContent = message;
    const okBtn = document.getElementById("veConfirmOkBtn");
    okBtn.textContent = opts.okLabel || (opts.danger ? "כן, בצע" : "אישור");
    okBtn.style.background = opts.danger ? "var(--fail)" : "";
    okBtn.style.color = opts.danger ? "#fff" : "";
    const cancelBtn = document.getElementById("veConfirmCancelBtn");
    const restore = uiOverModal(bg);
    const finish = (value) => {
      bg.classList.remove("show");
      restore();
      okBtn.onclick = null; cancelBtn.onclick = null; bg.onkeydown = null;
      resolve(value);
    };
    okBtn.onclick = () => finish(true);
    cancelBtn.onclick = () => finish(false);
    bg.onkeydown = (e) => { if (e.key === "Escape") { e.preventDefault(); finish(false); } };   // preventDefault: לא לסגור גם את ה-dialog
    bg.classList.add("show");
    (opts.danger ? cancelBtn : okBtn).focus();
  });
}

