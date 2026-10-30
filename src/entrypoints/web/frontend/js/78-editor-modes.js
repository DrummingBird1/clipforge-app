// ============================================================================
// גל 34: רמות, לשוניות, ספרייה ומקלדת - "רגיל" בלי ההגדרות הטכניות הנדירות, הלשונית
// האחרונה לכל פרויקט, ספרייה אחת (סגנונות / מיתוג / יעדים / שכבות מוכנות), A/B למראה,
// מסך מלא לנגן, מעבר בין אזורים במקלדת, קיצורים שאפשר לשנות, סיור ו"מה חדש", ואיקון
// קבוע לכל מושג.
// ============================================================================

// --- איקון קבוע לכל מושג (נבדק ב-tests/test_web_ui_terms.py) ---
const VE_CONCEPT_ICONS = {project: "📁", style: "🗂️", brand: "🏷️", target: "🎯", ready: "📑"};

// --- "רגיל": ההגדרות הטכניות הנדירות מוסתרות (הגדרה ששונתה תמיד מוצגת; חיפוש מציג הכל) ---
const VE_RARE_FIELDS = new Set([
  "max_concurrent_nvenc", "effort", "container", "validate_only", "notify_per_file", "export_report", "number_prefix",
  "number_start", "smooth_fps", "force", "preview_only", "nvenc_cq", "nvenc_preset", "chromakey_similarity",
  "chromakey_blend", "remove_watermark_width_fraction", "remove_watermark_height_fraction", "remove_watermark_region",
  "concat_transition_duration", "silence_threshold_db", "silence_min_duration", "custom_width", "custom_height",
  "pad_color", "scale_algo", "tonemap", "deinterlace", "audio_track", "captions_model", "captions_no_burn",
  "timestamp_overlay", "progress_bar_height", "watermark_move_seconds", "meta_comment", "gif_width", "gif_fps",
  "audio_eq_mid_freq", "audio_denoise_model", "eq_gamma", "lut_intensity", "frame_thickness", "include_subfolders",
]);

function _veMarkRareRows() {
  const fields = Object.entries(VE_FAVORITABLE_FIELDS).map(([key, meta]) => [key, _veEl(meta.id)]).filter(([, el]) => el);
  for (const row of document.querySelectorAll("#veCategories .ve-row")) {
    if (row.closest("#veLegacyFields, .ve-favorite-row")) continue;
    const keys = fields.filter(([, el]) => row.contains(el)).map(([key]) => key);
    row.classList.toggle("ve-rare", keys.length > 0 && keys.every(key => VE_RARE_FIELDS.has(key)));
  }
  for (const sub of document.querySelectorAll("#veCategories .ve-subcat")) {
    const rows = [...sub.querySelectorAll(".ve-row")];
    sub.classList.toggle("ve-rare", rows.length > 0 && rows.every(row => row.classList.contains("ve-rare")));
  }
}

function _veRenderRareChip() {
  const chip = _veEl("veRareChip");
  if (!chip) return;
  const hidden = _veCurrentMode() === "regular" ? document.querySelectorAll("#veCategories .ve-row.ve-rare:not(.ve-row-changed)").length : 0;
  chip.hidden = !hidden;
  chip.textContent = `🧰 עוד ${hidden} הגדרות במצב מומחה`;
}

// --- הלשונית האחרונה לכל פרויקט (תיקייה) ---
const VE_TAB_BY_PROJECT = "veTabByProject";

function _veRememberProjectTab() {
  if (!state.folder) return;
  const map = _veLoadPref(VE_TAB_BY_PROJECT, {});
  delete map[state.folder];
  map[state.folder] = _veLoadPref("veActiveTab", VE_DEFAULT_TAB);
  const keys = Object.keys(map);
  for (const key of keys.slice(0, Math.max(0, keys.length - 40))) delete map[key];
  _veSavePref(VE_TAB_BY_PROJECT, map);
}

function _veRestoreProjectTab() {
  const tab = state.folder && _veLoadPref(VE_TAB_BY_PROJECT, {})[state.folder];
  if (tab && _veCurrentLayout() === "tabs" && _veCategoryByKey(tab)) _veActivateTab(tab);
}

// --- ספרייה אחת ---
const VE_LIBRARY_TABS = [["style", "סגנונות"], ["brand", "מיתוג"], ["target", "יעדים"], ["ready", "שכבות מוכנות"]];
let _veLibraryTab = "style";

async function openVeLibrary(tab) {
  if (tab) _veLibraryTab = tab;
  _veEl("veLibraryModalBg").classList.add("show");
  await _veRenderLibrary();
}

function closeVeLibrary() {
  _veEl("veLibraryModalBg").classList.remove("show");
}

function _veLibraryItem(icon, name, note, actionLabel, onAction, active, preview) {
  const item = document.createElement("div");
  item.className = "ve-library-item" + (active ? " active" : "") + (preview ? " ve-library-with-preview" : "");
  item.setAttribute("role", "listitem");
  const title = document.createElement("span");
  title.className = "ve-library-name";
  title.textContent = `${icon} ${name}`;
  const meta = document.createElement("span");
  meta.className = "ve-field-msg";
  meta.textContent = note || "";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = actionLabel;
  btn.onclick = async () => { await onAction(); await _veRenderLibrary(); };
  item.append(title, meta, btn);
  if (preview) item.prepend(preview);  // גל 36: תצוגה של השכבה המוכנה
  return item;
}

function _veLibraryFooterButton(label, onclick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "ve-library-footer";
  btn.textContent = label;
  btn.onclick = onclick;
  return btn;
}

async function _veLibraryItems(tab) {
  const items = [];
  if (tab === "style") {
    const select = _veEl("vePreset");
    for (const option of _veStyleOptions()) {
      const active = select.value === option.value;
      items.push(_veLibraryItem(VE_CONCEPT_ICONS.style, option.textContent.trim(), active ? "✓ פעיל" : "", active ? "↻ טען שוב" : "החל", () => {
        select.value = option.value;
        applyVideoEditorPreset();
      }, active));
    }
    items.push(_veLibraryFooterButton("⚙️ ניהול הסגנונות...", () => { closeVeLibrary(); openVeProfileManager(); }));
  } else if (tab === "brand") {
    if (!Object.keys(_veBrandKits).length) await loadVeBrandKits();
    const linked = _veEl("veBrandKit").value;
    for (const [name, kit] of Object.entries(_veBrandKits).sort(([a], [b]) => a.localeCompare(b, "he"))) {
      const note = `${Object.keys(kit.fields || {}).length} שדות · ${(kit.templates || []).length} שכבות מוכנות`;
      items.push(_veLibraryItem(VE_CONCEPT_ICONS.brand, name, note, name === linked ? "✓ מקושר" : "קשר לסגנון", async () => {
        _veEl("veBrandKit").value = name;
        await onVeBrandKitSelected();
      }, name === linked));
    }
    items.push(_veLibraryFooterButton("💾 שמור את ההגדרות הנוכחיות כמיתוג...", () => saveVeBrandKitFromCurrent()));
  } else if (tab === "target") {
    const schema = await _veLoadSchema();
    const active = _veTargets();
    for (const [id, target] of Object.entries(schema.targets || {})) {
      const on = active.includes(id);
      items.push(_veLibraryItem(target.icon || VE_CONCEPT_ICONS.target, target.label, on ? "✓ בריצה" : "", on ? "➖ הסר" : "➕ הוסף", () => {
        const current = _veTargets();
        _veSetTargets(current.includes(id) ? current.filter(x => x !== id) : [...current, id]);
      }, on));
    }
  } else if (tab === "ready") {
    // גל 36: שכבות מוכנות מובנות (גם בלי מיתוג), ואחריהן אלה שנשמרו במיתוג - כל אחת עם תצוגה
    for (const tpl of VE_BUILTIN_READY) {
      items.push(_veLibraryItem(VE_CONCEPT_ICONS.ready, tpl.name, "מובנית", "➕ הוסף שכבה", () => _veAddReadyLayer(tpl), false, _veReadyPreview(tpl.layer)));
    }
    if (!Object.keys(_veBrandKits).length) await loadVeBrandKits();
    for (const [kitName, kit] of Object.entries(_veBrandKits)) {
      for (const tpl of kit.templates || []) {
        items.push(_veLibraryItem(VE_CONCEPT_ICONS.ready, tpl.name, `${VE_CONCEPT_ICONS.brand} ${kitName}`, "➕ הוסף שכבה", () => _veAddReadyLayer(tpl), false, _veReadyPreview(tpl.layer || {})));
      }
    }
  }
  return items;
}

const VE_LIBRARY_EMPTY = {
  style: "עוד אין סגנונות - שמור את ההגדרות הנוכחיות כסגנון (💾 בפס העליון).",
  brand: "עוד אין מיתוג - לוגו, צבעים וגופן שמשותפים לכמה סגנונות.",
  target: "אין יעדים.",
  ready: "עוד אין שכבות מוכנות - הן נשמרות בתוך מיתוג (📌 בעורך השכבות).",
};

async function _veRenderLibrary() {
  const tabs = _veEl("veLibraryTabs");
  tabs.replaceChildren(...VE_LIBRARY_TABS.map(([key, label]) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", String(key === _veLibraryTab));
    btn.className = key === _veLibraryTab ? "active" : "";
    btn.textContent = `${VE_CONCEPT_ICONS[key]} ${label}`;
    btn.onclick = () => { _veLibraryTab = key; _veRenderLibrary(); };
    return btn;
  }));
  const items = await _veLibraryItems(_veLibraryTab);
  const list = _veEl("veLibraryList");
  const empty = !items.some(item => item.classList.contains("ve-library-item"));
  if (empty) {
    const note = document.createElement("div");
    note.className = "ve-field-msg ve-library-empty";
    note.textContent = VE_LIBRARY_EMPTY[_veLibraryTab];
    items.unshift(note);
  }
  list.replaceChildren(...items);
}

// --- A/B למראה: שתי גרסאות של הצבע, מעבר ביניהן עם הנגן החי ---
const VE_LOOK_SUBCATS = ["color", "grade"];
let _veLookAB = null;   // {a, b, showing}

function _veLookSnapshot() {
  const values = {};
  for (const key of VE_LOOK_SUBCATS) {
    const sub = document.querySelector(`#veCategories .ve-subcat[data-subcat="${key}"]`);
    if (sub) for (const [field, , el] of _veSubcatFields(sub)) values[field] = _veFieldValue(el);
  }
  return values;
}

function _veApplyLookSnapshot(values) {
  for (const [field, value] of Object.entries(values || {})) {
    const meta = VE_FAVORITABLE_FIELDS[field];
    const el = meta && _veEl(meta.id);
    if (el && _veFieldValue(el) !== value) _veApplyFieldValue(el, value);
  }
}

function toggleVeLookAB() {
  if (!_veLookAB) {
    _veLookAB = {a: _veLookSnapshot(), b: null, showing: "b"};
    uiToast("📌 המראה הנוכחי נשמר כ-A - שנה את הצבע ולחץ שוב כדי לעבור בין A ל-B", "ok");
  } else if (_veLookAB.showing === "b") {
    _veLookAB.b = _veLookSnapshot();
    _veApplyLookSnapshot(_veLookAB.a);
    _veLookAB.showing = "a";
  } else {
    _veLookAB.a = _veLookSnapshot();
    _veApplyLookSnapshot(_veLookAB.b);
    _veLookAB.showing = "b";
  }
  _veRenderLookAB();
}

function clearVeLookAB() {
  _veLookAB = null;
  _veRenderLookAB();
}

function _veRenderLookAB() {
  const btn = _veEl("veLookAbBtn");
  btn.textContent = _veLookAB ? `A/B: ${_veLookAB.showing.toUpperCase()}` : "📌 A/B";
  btn.setAttribute("aria-pressed", String(!!_veLookAB && _veLookAB.showing === "a"));
  _veEl("veLookAbClearBtn").hidden = !_veLookAB;
}

// --- מסך מלא לנגן ---
function toggleVeFullscreen() {
  if (document.fullscreenElement) { document.exitFullscreen(); return; }
  const viewer = _veEl("veViewer");
  if (!viewer.requestFullscreen) { uiToast("הדפדפן לא תומך במסך מלא", "warn"); return; }
  viewer.requestFullscreen().catch(() => uiToast("הדפדפן לא אישר מסך מלא", "warn"));
}

function _veSyncFullscreen() {
  const on = document.fullscreenElement === _veEl("veViewer");
  _veEl("veFullscreenBtn").setAttribute("aria-pressed", String(on));
  window.dispatchEvent(new Event("resize"));   // הנגן החי והידיות מחשבים מחדש את הגודל
}

// --- מעבר בין אזורי המסך במקלדת: F6 / Shift+F6, Alt+1..4 ---
const VE_REGIONS = [["veSide", "קבצים"], ["veViewer", "נגן"], ["veInspectorTools", "הגדרות"], ["veStickyBar", "פס עליון"]];

function focusVeRegion(index) {
  const [id] = VE_REGIONS[index] || [];
  let region = id && _veEl(id);
  if (id === "veInspectorTools" && region) region = region.parentElement;   // כל המפקח, לא רק שורת הכלים
  if (!region || !region.offsetParent) return;
  if (id === "veInspectorTools" && _veEl("videoEditorOptions").classList.contains("ve-inspector-rail")) setVePanelRail("inspector", false);
  if (id === "veSide" && _veEl("videoEditorOptions").classList.contains("ve-queue-rail")) setVePanelRail("queue", false);
  if (!region.hasAttribute("tabindex")) region.tabIndex = -1;
  region.focus();
  region.classList.remove("ve-region-flash");
  void region.offsetWidth;
  region.classList.add("ve-region-flash");
}

function _veCurrentRegion() {
  const active = document.activeElement;
  return VE_REGIONS.findIndex(([id]) => {
    const el = _veEl(id);
    const region = id === "veInspectorTools" && el ? el.parentElement : el;
    return region && region.contains(active);
  });
}

// --- קיצורים שאפשר לשנות ---
const VE_SHORTCUT_DEFAULTS = {run: "Ctrl+Enter", save: "Ctrl+S", palette: "Ctrl+K", search: "/", shortcuts: "?", play: "Space", "delete-layer": "Delete", areas: "F6"};
// השורה במפת הקיצורים (VE_SHORTCUTS) -> הפעולה
const VE_SHORTCUT_ROWS = {"Ctrl+Enter": "run", "Ctrl+S": "save", "Ctrl+K": "palette", "/": "search", "?": "shortcuts", "רווח": "play", "Delete": "delete-layer", "F6 / Shift+F6": "areas"};
const VE_SHORTCUT_MAP = "veShortcutMap";
let _veShortcutCapture = null;

function _veComboOf(e) {
  const key = e.key === " " ? "Space" : (e.key.length === 1 ? e.key.toUpperCase() : e.key);
  const parts = [];
  if (e.ctrlKey || e.metaKey) parts.push("Ctrl");
  if (e.altKey) parts.push("Alt");
  if (e.shiftKey && e.key.length > 1) parts.push("Shift");   // תו מודפס כבר כולל את ה-Shift (? ולא Shift+/)
  parts.push(key);
  return parts.join("+");
}

function _veShortcutKeysFor(keys) {
  const action = VE_SHORTCUT_ROWS[keys];
  const custom = action && _veLoadPref(VE_SHORTCUT_MAP, {})[action];
  return custom || keys;
}

function _veFireDefaultShortcut(action, target) {
  const combo = VE_SHORTCUT_DEFAULTS[action].split("+");
  const name = combo.pop();
  const key = name === "Space" ? " " : (name.length === 1 ? name.toLowerCase() : name);
  const event = new KeyboardEvent("keydown", {
    key: name === "?" ? "?" : key, code: name === "Space" ? "Space" : "", bubbles: true, cancelable: true,
    ctrlKey: combo.includes("Ctrl"), altKey: combo.includes("Alt"), shiftKey: combo.includes("Shift") || name === "?",
  });
  event.__veRemapped = true;
  (target || document.body).dispatchEvent(event);
}

function _veOnRemapKeydown(e) {
  if (e.__veRemapped || _veShortcutCapture || !_veIsActive()) return;
  const custom = _veLoadPref(VE_SHORTCUT_MAP, {});
  if (!Object.keys(custom).length) return;
  const combo = _veComboOf(e);
  if (_veIsTyping() && !/^(Ctrl|Alt)\+/.test(combo)) return;
  const action = Object.keys(custom).find(name => custom[name] === combo);
  if (action) {
    e.preventDefault();
    e.stopImmediatePropagation();
    _veFireDefaultShortcut(action, e.target);
    return;
  }
  // צירוף ברירת המחדל של פעולה שקיבלה צירוף אחר כבר לא עושה כלום (חוץ מבתוך כפתור או שדה)
  const moved = Object.keys(custom).find(name => VE_SHORTCUT_DEFAULTS[name] === combo);
  if (moved && !(e.target.closest && e.target.closest("button, a, input, select, textarea, [contenteditable]"))) {
    e.preventDefault();
    e.stopImmediatePropagation();
  }
}

function _veRerenderShortcuts() {
  _veEl("veShortcutsList").replaceChildren();
  _veRenderShortcuts();
}

function _veCaptureShortcut(action, btn) {
  _veShortcutCapture = action;
  btn.textContent = "לחץ על צירוף... (Esc ביטול)";
  const onKey = (e) => {
    if (["Control", "Shift", "Alt", "Meta"].includes(e.key)) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    window.removeEventListener("keydown", onKey, true);
    _veShortcutCapture = null;
    const map = _veLoadPref(VE_SHORTCUT_MAP, {});
    if (e.key === "Backspace") delete map[action];
    else if (e.key !== "Escape") {
      const combo = _veComboOf(e);
      const taken = Object.keys(VE_SHORTCUT_DEFAULTS).find(name => name !== action && (map[name] || VE_SHORTCUT_DEFAULTS[name]) === combo);
      if (taken) uiToast(`⚠️ ${combo} כבר בשימוש`, "warn");
      else if (combo === VE_SHORTCUT_DEFAULTS[action]) delete map[action];
      else map[action] = combo;
    }
    _veSavePref(VE_SHORTCUT_MAP, map);
    _veRerenderShortcuts();
  };
  window.addEventListener("keydown", onKey, true);
}

// נקרא מ-_veRenderShortcuts (76-editor-comfort.js) לכל שורה
function _veShortcutRowExtras(row, keys) {
  const action = VE_SHORTCUT_ROWS[keys];
  if (!action) return;
  const cell = row.insertCell();
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "ve-shortcut-edit";
  btn.textContent = "✎";
  btn.title = "שנה את הקיצור (Backspace מחזיר לברירת המחדל)";
  btn.setAttribute("aria-label", "שנה את הקיצור");
  btn.onclick = () => _veCaptureShortcut(action, btn);
  cell.appendChild(btn);
  if (_veLoadPref(VE_SHORTCUT_MAP, {})[action]) row.classList.add("ve-shortcut-custom");
}

function resetVeShortcuts() {
  _veSavePref(VE_SHORTCUT_MAP, {});
  _veRerenderShortcuts();
}

// --- סיור היכרות ---
const VE_TOUR = [
  ["veStickyBar", "הפס העליון", "הפרויקט (התיקייה), הסגנון ושמירה, רמת הפירוט - פשוט, רגיל או מומחה - והרצה."],
  ["veSide", "קבצים", "הקבצים בתיקייה. לחיצה מציגה קובץ בנגן, ✏️ פותח עריכה לקליפ אחד בלבד."],
  ["veViewer", "הנגן", "התוצאה בזמן אמת: ⇆ לפני/אחרי, A/B לשתי גרסאות של הצבע, ⛶ מסך מלא."],
  ["veInspectorTools", "ההגדרות", "חיפוש, \"רק מה ששיניתי\" והספרייה. הלשוניות בסדר העבודה: זמן, צבע, אפקטים, שכבות, שמע ופלט."],
  ["veTimelineDock", "ציר הזמן", "חיתוך, טווחים להסרה ושכבות לאורך הזמן. F6 עובר בין האזורים, ? מציג את כל הקיצורים."],
];
let _veTourStep = -1;

function startVeTour() {
  closeVeMenus();
  _veShowTourStep(0);
}

function endVeTour() {
  _veTourStep = -1;
  for (const el of document.querySelectorAll(".ve-tour-target")) el.classList.remove("ve-tour-target");
  _veEl("veTour").hidden = true;
  _veSavePref("veTourDone", true);
}

function _veShowTourStep(step) {
  const steps = VE_TOUR.filter(([id]) => { const el = _veEl(id); return el && el.offsetParent; });
  if (step < 0 || step >= steps.length) { endVeTour(); return; }
  _veTourStep = step;
  const [id, title, text] = steps[step];
  for (const el of document.querySelectorAll(".ve-tour-target")) el.classList.remove("ve-tour-target");
  const target = _veEl(id);
  target.classList.add("ve-tour-target");
  target.scrollIntoView({block: "nearest"});
  const box = _veEl("veTour");
  box.hidden = false;
  _veEl("veTourTitle").textContent = `${title} (${step + 1}/${steps.length})`;
  _veEl("veTourText").textContent = text;
  _veEl("veTourPrev").disabled = step === 0;
  _veEl("veTourNext").textContent = step === steps.length - 1 ? "✓ סיום" : "הבא ←";
  const rect = target.getBoundingClientRect();
  const top = rect.bottom + 8 + box.offsetHeight < window.innerHeight ? rect.bottom + 8 : Math.max(8, rect.top - box.offsetHeight - 8);
  box.style.top = `${Math.round(top)}px`;
  box.style.insetInlineStart = `${Math.round(Math.max(8, Math.min(window.innerWidth - box.offsetWidth - 8, window.innerWidth - rect.right)))}px`;
  _veEl("veTourNext").focus();
}

function veTourNext() { _veShowTourStep(_veTourStep + 1); }
function veTourPrev() { _veShowTourStep(_veTourStep - 1); }

// --- מה חדש ---
const VE_WHATS_NEW_VERSION = 34;
const VE_WHATS_NEW = [
  ["גל 34 - רמות, ספרייה ומקלדת", [
    "שלוש רמות: פשוט (ארבעה צעדים), רגיל (בלי ההגדרות הטכניות הנדירות) ומומחה (הכל).",
    "הלשוניות בסדר העבודה: זמן, צבע, אפקטים, שכבות, שמע, פלט - והלשונית האחרונה נזכרת לכל פרויקט.",
    "📚 ספרייה אחת: סגנונות, מיתוג, יעדים ושכבות מוכנות.",
    "A/B לצבע, ⛶ מסך מלא לנגן, F6 ו-Alt+1..4 בין האזורים, וקיצורים שאפשר לשנות (?).",
  ]],
  ["גל 33 - מפקח מסודר", [
    "מסלול ניווט, חיפוש ו\"רק מה ששיניתי\" בתוך המפקח.",
    "הגדרות שלא רלוונטיות עכשיו מעומעמות עם הסיבה, ואזהרות מופיעות ליד השדה.",
    "↺ 📋 📥 לכל קבוצה, \"?\" ליד כל הגדרה וקישור לתיעוד.",
  ]],
];

function openVeWhatsNew() {
  closeVeMenus();
  const box = _veEl("veWhatsNewList");
  box.replaceChildren(...VE_WHATS_NEW.flatMap(([title, items]) => {
    const head = document.createElement("div");
    head.className = "ve-subcat-title";
    head.textContent = title;
    const list = document.createElement("ul");
    list.replaceChildren(...items.map(text => { const li = document.createElement("li"); li.textContent = text; return li; }));
    return [head, list];
  }));
  _veEl("veWhatsNewModalBg").classList.add("show");
  _veSavePref("veWhatsNewSeen", VE_WHATS_NEW_VERSION);
  _veEl("veHelpMenuBtn").classList.remove("ve-has-news");   // גל 58: "מה חדש" בתפריט העזרה
}

function closeVeWhatsNew() {
  _veEl("veWhatsNewModalBg").classList.remove("show");
}

function _veInitWave34() {
  _veMarkRareRows();
  _veRenderRareChip();
  _veRenderLookAB();
  const refresh = () => uiDebounce("ve:wave34", _veRenderRareChip, 170);
  uiBus.on("ve:derived-refresh", refresh);
  uiBus.on("ve:fields-applied", refresh);
  uiBus.on("ve:mode-changed", _veRenderRareChip);
  uiBus.on("ve:folder-changed", () => setTimeout(_veRestoreProjectTab, 0));
  _veEl("veCatTabs").addEventListener("click", (e) => { if (e.target.closest("button[data-cat]")) setTimeout(_veRememberProjectTab, 0); });
  document.addEventListener("fullscreenchange", _veSyncFullscreen);
  window.addEventListener("keydown", _veOnRemapKeydown, true);
  document.addEventListener("keydown", (e) => {
    if (!_veIsActive()) return;
    if (e.key === "F6") {
      e.preventDefault();
      const current = _veCurrentRegion();
      const count = VE_REGIONS.length;
      focusVeRegion(((current < 0 ? (e.shiftKey ? 0 : -1) : current) + (e.shiftKey ? count - 1 : 1)) % count);
    } else if (e.altKey && !e.ctrlKey && !e.metaKey && /^[1-4]$/.test(e.key)) {
      e.preventDefault();
      focusVeRegion(Number(e.key) - 1);
    }
  });
  if (_veLoadPref("veWhatsNewSeen", 0) < VE_WHATS_NEW_VERSION) _veEl("veHelpMenuBtn").classList.add("ve-has-news");
}
