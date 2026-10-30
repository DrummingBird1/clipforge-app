// ============================================================================
// גל 39: עורך ההגדרות המלא של פרק - כל השדות בקבוצות עם הסבר (מהסכימה, dataviz/schema.py), ובכל
// שדה ברירת המחדל מול הקובץ מול מה ששונה כאן + איפוס; עורך אירועים בטבלה עם גרירה על ציר;
// צבעים (ערכה, פלטה וצבע קבוע לישות); ישויות (שם חלופי / מיזוג / החרגה); ו"מה שונה" מול
// config.yaml. כל שינוי הוא טיוטה שמוצגת מיד בתצוגה החיה, ו"שמור" כותב לקובץ ה-override.
// ============================================================================

let dvzEd = {data: null, tab: "fields", draft: {}, unset: new Set()};

const DVZ_EDITOR_TABS = [["fields", "⚙️ הגדרות"], ["events", "📅 אירועים"], ["story", "📖 סיפור"], ["colors", "🎨 צבעים"], ["entities", "🏷️ ישויות"],
  ["map", "🗺 מפה"], ["voice", "🎙 קריינות"], ["music", "🎵 מוזיקה"], ["langs", "🌍 שפות"], ["changes", "🔍 מה שונה"]];   // גל 55: שפות (86-dataviz-publish.js)   // גל 45: מפה וקריינות (47-dataviz-engine.js); גל 50: סיפור (82-dataviz-story.js)
const DVZ_TEXT_MOMENT = {intro: 0.01, outro: 0.99};

function _dvzEdEl(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined) el.textContent = text;
  return el;
}

function _dvzShow(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.map(v => typeof v === "object" ? `${v.date} ${v.label}` : v).join(", ").slice(0, 80) : "—";
  if (typeof value === "boolean") return value ? "כן" : "לא";
  if (typeof value === "object") return Object.entries(value).map(([k, v]) => `${k}: ${v}`).join(", ").slice(0, 80) || "—";
  return String(value);
}

// סבב הייצוב (16.10): טעינה אחת בכל פעם לאותו פרק. open = true מפעיל גם את ontoggle של ה-details, ושתי טעינות במקביל ציירו את
// העורך פעמיים - קבוצה שנפתחה בין שתיהן נסגרה מחדש. קריאה נוספת בזמן טעינה מקבלת את הטעינה שכבר בדרך
let _dvzEditorLoading = null;

function dvzLoadEditor() {
  if (!dvzState.selected) return Promise.resolve();
  if (_dvzEditorLoading && _dvzEditorLoading.episode === dvzState.selected) return _dvzEditorLoading.promise;
  const load = {episode: dvzState.selected};
  load.promise = _dvzFetchEditor(load.episode).finally(() => { if (_dvzEditorLoading === load) _dvzEditorLoading = null; });
  _dvzEditorLoading = load;
  return load.promise;
}

async function _dvzFetchEditor(episode) {
  const status = document.getElementById("dvzEditorStatus");
  status.textContent = "⏳";
  try {
    const resp = await fetch("/api/dataviz/episodes/editor?" + new URLSearchParams({episode, lang: _uiLang}));   // גל 47: תוויות והסברים בשפת הממשק
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "הטעינה נכשלה");
    if (episode !== dvzState.selected) return;   // בינתיים נבחר פרק אחר - הטעינה שלו תצייר
    if (dvzEd.data && dvzEd.data.episode !== data.episode) { dvzEd.draft = {}; dvzEd.unset = new Set(); }
    dvzEd.data = data;
    status.textContent = "";
    _dvzRenderEditor();
  } catch (e) {
    status.textContent = "שגיאה: " + e.message;
  }
}

function _dvzStage(path, value) {
  _dvzRecordUndo(path);   // גל 53: ביטול וחזרה (בהמשך הקובץ)
  // 23.10.2026: עותק - הלשוניות (אירועים, סיפור, שפות) ממשיכות לשנות את האובייקט שלהן, והשינוי הגיע לתמונת המצב של
  // הביטול לפני שנשמר בה (Ctrl+Z לא החזיר כלום, והשני מחק את שני השינויים)
  dvzEd.draft[path] = value !== null && typeof value === "object" ? JSON.parse(JSON.stringify(value)) : value;
  dvzEd.unset.delete(path);
  _dvzSyncDraftBar();
  _dvzSyncSourceChip(path);
  dvzPreviewSoon();
}

function _dvzStageUnset(path) {
  _dvzRecordUndo("");
  delete dvzEd.draft[path];
  dvzEd.unset.add(path);
  _dvzSyncDraftBar();
  _dvzRenderEditor();
}

function _dvzSyncDraftBar() {
  const count = Object.keys(dvzEd.draft).length + dvzEd.unset.size;
  document.getElementById("dvzDraftCount").textContent = count ? `${count} שינויים שלא נשמרו` : "";
  document.getElementById("dvzDraftSave").disabled = !count;
  document.getElementById("dvzDraftDiscard").disabled = !count;
}

async function dvzSaveDraft() {
  const status = document.getElementById("dvzEditorStatus");
  if (dvzEd.saving) return;   // 23.10.2026: Ctrl+S / לחיצה כפולה שלחו שמירה שנייה זהה
  dvzEd.saving = true;
  document.getElementById("dvzDraftSave").disabled = true;
  // 23.10.2026: רק מה שנשלח יוצא מהטיוטה - מה שהוקלד בזמן הבקשה נשאר (קודם draft = {} מחק אותו)
  const sent = JSON.stringify(dvzEd.draft), sentUnset = [...dvzEd.unset];
  try {
    const resp = await fetch("/api/dataviz/episodes/override", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({episode: dvzState.selected, set: JSON.parse(sent), unset: sentUnset})});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "השמירה נכשלה");
    const was = JSON.parse(sent);
    for (const path of Object.keys(was)) if (JSON.stringify(dvzEd.draft[path]) === JSON.stringify(was[path])) delete dvzEd.draft[path];
    for (const path of sentUnset) dvzEd.unset.delete(path);
    _dvzResetUndo();   // מה שנשמר הוא נקודת ההתחלה החדשה
    delete dvzState.estimates[dvzState.selected];
    dvzData.cache = {};   // גל 40: הנתונים (קצב, אירועים, מוזיקה) נטענים מחדש
    _dvzSyncDraftBar();
    await loadDataviz();
    await dvzLoadEditor();
    status.textContent = "✅ נשמר - config.yaml של הפרק לא השתנה.";   // אחרי הטעינה מחדש (שמנקה את השורה)
  } catch (e) {
    status.textContent = "שגיאה: " + e.message;
  } finally {
    dvzEd.saving = false;
    _dvzSyncDraftBar();
  }
}

// 23.10.2026: מעבר לפרק אחר זרק את הטיוטה ואת היסטוריית הביטול בלי לשאול. true = אפשר לעזוב (אין טיוטה, או שהמשתמש אישר)
async function _dvzLeaveDraftOk() {
  const count = Object.keys(dvzEd.draft).length + dvzEd.unset.size;
  return !count || veConfirm(`יש ${count} שינויים שלא נשמרו בפרק הזה - לעבור בלי לשמור?`, {okLabel: "לעבור בלי לשמור", danger: true});
}

// ורענון / סגירה של הלשונית עם טיוטה - האזהרה של הדפדפן (לא תחת אוטומציה, כמו הסיור - טסטים מרעננים דפים)
window.addEventListener("beforeunload", (e) => {
  if (navigator.webdriver || !(Object.keys(dvzEd.draft).length || dvzEd.unset.size)) return;
  e.preventDefault();
  e.returnValue = "";
});

function dvzDiscardDraft() {
  _dvzRecordUndo("");
  dvzEd.draft = {};
  dvzEd.unset = new Set();
  _dvzSyncDraftBar();
  _dvzRenderEditor();
  dvzPreviewSoon();
}

// נקרא מ-_dvzPreviewParams (43-dataviz-studio.js): הטיוטה מוצגת בתצוגה החיה
function _dvzDraftParam() {
  return Object.keys(dvzEd.draft).length ? JSON.stringify(dvzEd.draft) : "";
}

function _dvzRenderEditor() {
  const tabs = document.getElementById("dvzEditorTabs");
  tabs.replaceChildren(...DVZ_EDITOR_TABS.map(([key, label]) => {
    const btn = _dvzEdEl("button", key === dvzEd.tab ? "active" : "", label);
    btn.type = "button";
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", String(key === dvzEd.tab));
    btn.dataset.tab = key;
    btn.onclick = () => { dvzEd.tab = key; _dvzRenderEditor(); };
    return btn;
  }));
  const body = document.getElementById("dvzEditorBody");
  if (!dvzEd.data) { body.replaceChildren(); return; }
  const render = {fields: _dvzFieldsTab, events: _dvzEventsTab, story: _dvzStoryTab, colors: _dvzColorsTab, entities: _dvzEntitiesTab, map: _dvzMapTab, voice: _dvzVoiceTab, music: _dvzMusicTab, langs: _dvzLangsTab, changes: _dvzChangesTab}[dvzEd.tab];
  body.replaceChildren(render());
  if (dvzEd.tab === "fields") _dvzFieldSearch(body);   // גל 53: חיפוש הגדרה
  _dvzSyncDraftBar();
  uiBus.emit("dvz:editor-rendered");   // 27.10.2026: לפני / אחרי בריחוף ובלוקי הסיפור (85-dataviz-plus.js)
}

// --- כל ההגדרות בקבוצות, עם ברירת מחדל / קובץ / שונה כאן ---
function _dvzFieldInput(field) {
  const value = field.path in dvzEd.draft ? dvzEd.draft[field.path] : (dvzEd.unset.has(field.path) ? (field.in_file ? field.file : field.default) : field.value);
  let input;
  if (field.type === "bool") {
    input = _dvzEdEl("input");
    input.type = "checkbox";
    input.checked = !!value;
    input.onchange = () => _dvzStage(field.path, input.checked);
  } else if (field.type === "choice") {
    input = _dvzEdEl("select");
    for (const choice of field.choices) input.appendChild(new Option((field.choice_labels || {})[choice] || choice, choice));
    input.value = value;
    input.onchange = () => _dvzStage(field.path, input.value);
  } else if (field.multiline) {   // סבב הייצוב: טקסט בכמה שורות (התיאור לפרסום) - ירידות השורה נשמרות
    input = _dvzEdEl("textarea");
    input.rows = 4;
    if (field.max !== undefined) input.maxLength = field.max;
    input.value = value ?? "";
    input.oninput = () => _dvzStage(field.path, input.value);
  } else if (field.type === "lines") {
    input = _dvzEdEl("textarea");
    input.rows = 3;
    input.value = (value || []).join("\n");
    input.oninput = () => _dvzStage(field.path, input.value.split("\n"));
  } else {
    input = _dvzEdEl("input");
    input.type = field.type === "date" ? "date" : (field.type === "int" || field.type === "number") ? "number" : "text";
    if (field.type === "int") input.step = "1";
    if (field.type === "number") input.step = "any";
    if (field.min !== undefined) input.min = String(field.min);
    if (field.max !== undefined && input.type === "number") input.max = String(field.max);
    if (field.max !== undefined && input.type === "text") input.maxLength = field.max;
    input.value = value ?? "";
    input.oninput = () => {
      if (input.type !== "number") { _dvzStage(field.path, input.value); return; }
      const number = Number(input.value);
      if (input.value !== "" && Number.isFinite(number)) _dvzStage(field.path, number);
    };
  }
  input.id = "dvzF-" + field.path.replace(/\./g, "-");
  input.setAttribute("aria-label", field.label);
  // טקסט של הפתיח או הסיום - התצוגה קופצת לרגע שבו הוא מופיע
  const moment = DVZ_TEXT_MOMENT[field.path.split(".")[0]];
  if (moment !== undefined) input.addEventListener("focus", () => { document.getElementById("dvzPreviewPos").value = String(Math.round(moment * 1000)); dvzPreviewSoon(); });
  return input;
}

function _dvzFieldRow(field) {
  const row = _dvzEdEl("div", "dvz-field");
  row.dataset.path = field.path;
  const label = _dvzEdEl("label", "dvz-field-label", field.label);
  label.htmlFor = "dvzF-" + field.path.replace(/\./g, "-");
  if (field.help) label.title = field.help;
  const changed = field.path in dvzEd.draft || (field.overridden && !dvzEd.unset.has(field.path));
  row.classList.toggle("is-changed", changed);
  const meta = _dvzEdEl("div", "dvz-field-meta");
  meta.append(_dvzEdEl("span", "dvz-chip", `ברירת מחדל: ${_dvzShow(field.default)}`));
  if (field.in_file) meta.append(_dvzEdEl("span", "dvz-chip", `📄 בקובץ: ${_dvzShow(field.file)}`));
  meta.prepend(_dvzSourceChip(field, changed));   // 19.10.2026: מאיפה הערך (בהמשך הקובץ)
  if (changed) {
    const reset = _dvzEdEl("button", "btn-xs", "↺");
    reset.type = "button";
    reset.title = field.in_file ? "חזרה לערך שבקובץ הפרק" : "חזרה לברירת המחדל";
    reset.setAttribute("aria-label", reset.title);
    reset.onclick = () => _dvzStageUnset(field.path);
    meta.append(reset);
  }
  if (field.help) meta.append(_dvzEdEl("span", "dvz-field-help", field.help));
  row.append(label, _dvzFieldInput(field), meta);
  return row;
}

function _dvzFieldsTab() {
  const box = _dvzEdEl("div", "dvz-editor-groups");
  dvzEd.data.groups.forEach((group, i) => {
    const details = _dvzEdEl("details", "dvz-group");
    details.dataset.group = group.id;
    details.open = i < 2 || group.fields.some(f => f.path in dvzEd.draft);   // גל 59: "⭐ בסיסי" ו"טקסטים" פתוחות
    const summary = _dvzEdEl("summary", "", group.title);
    const changed = group.fields.filter(f => f.overridden || f.path in dvzEd.draft).length;
    if (changed) summary.append(_dvzEdEl("span", "dvz-chip is-changed", `✏️ ${changed}`));
    details.append(summary, _dvzEdEl("p", "hint", group.about), ...group.fields.map(_dvzFieldRow));
    box.append(details);
  });
  return box;
}

// --- אירועים: טבלה + ציר עם גרירה ---
function _dvzEvents() {
  return "events" in dvzEd.draft ? dvzEd.draft.events : (dvzEd.unset.has("events") ? null : dvzEd.data.events);
}

function _dvzDayOffset(date, start) {
  return Math.round((new Date(date + "T00:00:00Z") - new Date(start + "T00:00:00Z")) / 86400000);
}

function _dvzAddDays(start, days) {
  const d = new Date(start + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function _dvzEventsTab() {
  const box = _dvzEdEl("div", "dvz-events");
  const events = (_dvzEvents() || []).map(e => ({...e}));
  const [start, end] = dvzEd.data.date_range;
  const span = start && end ? Math.max(1, _dvzDayOffset(end, start)) : 1;
  const source = dvzEd.data.events_source === "file" && !("events" in dvzEd.draft)
    ? `האירועים נקראים מ-${dvzEd.data.events_file}. שינוי כאן נשמר ברשימה משלו (הקובץ לא משתנה).`
    : "שינוי כאן נשמר בקובץ השינויים של הפרק.";
  box.append(_dvzEdEl("p", "hint", source + " גרירת סימן על הציר משנה את התאריך."));
  const commit = () => { _dvzStage("events", events.filter(e => e.label.trim())); };
  // הציר
  const track = _dvzEdEl("div", "dvz-ev-track");
  track.setAttribute("aria-label", "האירועים על ציר הזמן");
  events.forEach((event, i) => {
    if (!start) return;
    const offset = _dvzDayOffset(event.date, start);
    if (offset < 0 || offset > span) return;
    const mark = _dvzEdEl("span", "dvz-ev-mark", "📍");
    mark.style.left = `${offset / span * 100}%`;
    mark.title = `${event.date} · ${event.label}`;
    mark.addEventListener("pointerdown", (e) => {
      mark.setPointerCapture(e.pointerId);
      const rect = track.getBoundingClientRect();
      const move = (ev) => {
        const ratio = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
        event.date = _dvzAddDays(start, Math.round(ratio * span));
        mark.style.left = `${ratio * 100}%`;
        mark.title = `${event.date} · ${event.label}`;
        const dateInput = box.querySelector(`input[data-ev="${i}"][type=date]`);
        if (dateInput) dateInput.value = event.date;
      };
      mark.addEventListener("pointermove", move);
      mark.addEventListener("pointerup", () => { mark.removeEventListener("pointermove", move); commit(); }, {once: true});
      e.preventDefault();
    });
    track.appendChild(mark);
  });
  if (start) track.append(_dvzEdEl("span", "dvz-ev-edge dvz-ev-start", start), _dvzEdEl("span", "dvz-ev-edge dvz-ev-end", end));
  // הטבלה
  const table = _dvzEdEl("table", "dvz-ev-table");
  events.forEach((event, i) => {
    const tr = table.insertRow();
    const date = _dvzEdEl("input");
    date.type = "date";
    date.value = event.date;
    date.dataset.ev = String(i);
    date.setAttribute("aria-label", "תאריך");
    date.onchange = () => { event.date = date.value; commit(); };
    const label = _dvzEdEl("input");
    label.type = "text";
    label.maxLength = 120;
    label.value = event.label;
    label.dataset.ev = String(i);
    label.setAttribute("aria-label", "תיאור האירוע");
    label.oninput = () => { event.label = label.value; commit(); };
    const remove = _dvzEdEl("button", "btn-xs", "🗑");
    remove.type = "button";
    remove.setAttribute("aria-label", "מחק את האירוע");
    remove.onclick = () => { events.splice(i, 1); commit(); _dvzRenderEditor(); };
    tr.insertCell().append(date);
    tr.insertCell().append(label);
    tr.insertCell().append(remove);
  });
  const add = _dvzEdEl("button", "btn-sm", "➕ אירוע");
  add.type = "button";
  add.onclick = () => {
    events.push({date: start ? _dvzAddDays(start, Math.round(span / 2)) : new Date().toISOString().slice(0, 10), label: "אירוע חדש"});
    commit();
    _dvzRenderEditor();
  };
  const reset = _dvzEdEl("button", "btn-sm", "↺ חזרה לקובץ הפרק");
  reset.type = "button";
  reset.disabled = dvzEd.data.events_source !== "override" && !("events" in dvzEd.draft);
  reset.onclick = () => _dvzStageUnset("events");
  box.append(track, table, _dvzEdEl("div", "tc-row"));
  box.lastChild.append(add, reset);
  return box;
}

// --- צבעים: ערכה, פלטה וצבע קבוע לישות ---
function _dvzColorInput(value, onChange, label) {
  const input = _dvzEdEl("input");
  input.type = "color";
  input.value = /^#[0-9a-f]{6}$/i.test(value || "") ? value : "#888888";
  input.setAttribute("aria-label", label);
  input.oninput = () => onChange(input.value);
  return input;
}

function _dvzColorsTab() {
  const box = _dvzEdEl("div", "dvz-colors");
  const theme = dvzEd.data.theme;
  const themeRow = _dvzEdEl("div", "dvz-color-row");
  themeRow.append(_dvzEdEl("strong", "", `ערכה (${theme.name === "dark" ? "כהה" : "בהירה"}):`));
  for (const [key, label] of [["bg", "רקע"], ["ink", "טקסט"], ["accent", "הדגשה"]]) {
    const path = "theme_overrides." + key;
    const wrap = _dvzEdEl("label", "dvz-color-pick", label + " ");
    wrap.append(_dvzColorInput(dvzEd.draft[path] || theme[key], (v) => _dvzStage(path, v), label));
    themeRow.append(wrap);
  }
  const palette = [...(dvzEd.draft["theme_overrides.categorical"] || theme.categorical)];
  const paletteRow = _dvzEdEl("div", "dvz-color-row");
  paletteRow.append(_dvzEdEl("strong", "", "פלטה (ישויות בלי סדר):"));
  palette.forEach((color, i) => paletteRow.append(_dvzColorInput(color, (v) => { palette[i] = v; _dvzStage("theme_overrides.categorical", [...palette]); }, `צבע ${i + 1} בפלטה`)));
  const resetTheme = _dvzEdEl("button", "btn-sm", "↺ ערכה ופלטה כמו בקובץ");
  resetTheme.type = "button";
  resetTheme.disabled = !theme.overridden.length && !Object.keys(dvzEd.draft).some(k => k.startsWith("theme_overrides."));
  resetTheme.onclick = () => {
    _dvzRecordUndo("");
    for (const key of Object.keys(dvzEd.draft)) if (key.startsWith("theme_overrides.")) delete dvzEd.draft[key];
    for (const key of theme.overridden) dvzEd.unset.add("theme_overrides." + key);
    _dvzSyncDraftBar();
    _dvzRenderEditor();
    dvzPreviewSoon();
  };
  // צבע קבוע לישות
  const colors = {...("colors" in dvzEd.draft ? dvzEd.draft.colors : dvzEd.data.colors)};
  const table = _dvzEdEl("table", "dvz-entity-table");
  for (const entity of dvzEd.data.entities.slice(0, 30)) {
    const tr = table.insertRow();
    tr.insertCell().textContent = entity.name;
    const cell = tr.insertCell();
    if (colors[entity.name]) {
      cell.append(_dvzColorInput(colors[entity.name], (v) => { colors[entity.name] = v; _dvzStage("colors", {...colors}); }, `צבע של ${entity.name}`));
      const clear = _dvzEdEl("button", "btn-xs", "✕");
      clear.type = "button";
      clear.title = "חזרה לצבע מהפלטה";
      clear.setAttribute("aria-label", clear.title);
      clear.onclick = () => { delete colors[entity.name]; _dvzStage("colors", {...colors}); _dvzRenderEditor(); };
      cell.append(clear);
    } else {
      const pick = _dvzEdEl("button", "btn-xs", "🎨 צבע קבוע");
      pick.type = "button";
      pick.onclick = () => { colors[entity.name] = palette[0] || "#3f6a9e"; _dvzStage("colors", {...colors}); _dvzRenderEditor(); };
      cell.append(_dvzEdEl("span", "hint", "מהפלטה "), pick);
    }
  }
  box.append(themeRow, paletteRow, resetTheme, _dvzEdEl("h4", "", "צבע קבוע לישות"), table);
  _dvzLookExtras(box);   // גל 43: גופן ובדיקת ניגודיות (83-dataviz-look.js)
  _dvzLookTools(box);    // גל 51: מראות מוכנים ועיוורון צבעים (83-dataviz-look.js)
  return box;
}

// --- ישויות: שם חלופי (אותו שם = מיזוג) והחרגה ---
function _dvzEntitiesTab() {
  const box = _dvzEdEl("div", "dvz-entities");
  box.append(_dvzEdEl("p", "hint", "שם חלופי משנה את השם בסרטון; שתי ישויות עם אותו שם חלופי מתמזגות והסכומים שלהן מצטרפים. מוחרגת = לא מוצגת בכלל."));
  const aliases = {...("entities.aliases" in dvzEd.draft ? dvzEd.draft["entities.aliases"] : dvzEd.data.entity_rules.aliases)};
  const exclude = new Set("entities.exclude" in dvzEd.draft ? dvzEd.draft["entities.exclude"] : dvzEd.data.entity_rules.exclude);
  const table = _dvzEdEl("table", "dvz-entity-table");
  const head = table.createTHead().insertRow();
  for (const title of ["ישות", "סכום", "שם חלופי", "מוחרגת", "תמונה", "בפוקוס"]) head.appendChild(_dvzEdEl("th", "", title));
  const tbody = table.createTBody();
  for (const entity of dvzEd.data.entities) {
    const tr = tbody.insertRow();
    tr.classList.toggle("is-excluded", exclude.has(entity.name));
    tr.insertCell().textContent = entity.name;
    tr.insertCell().textContent = Math.round(entity.total).toLocaleString("he-IL");
    const alias = _dvzEdEl("input");
    alias.type = "text";
    alias.maxLength = 80;
    alias.value = aliases[entity.name] || "";
    alias.placeholder = entity.name;
    alias.setAttribute("aria-label", `שם חלופי ל-${entity.name}`);
    alias.oninput = () => {
      if (alias.value.trim()) aliases[entity.name] = alias.value.trim(); else delete aliases[entity.name];
      _dvzStage("entities.aliases", {...aliases});
    };
    tr.insertCell().append(alias);
    const out = _dvzEdEl("input");
    out.type = "checkbox";
    out.checked = exclude.has(entity.name);
    out.setAttribute("aria-label", `להחריג את ${entity.name}`);
    out.onchange = () => {
      if (out.checked) exclude.add(entity.name); else exclude.delete(entity.name);
      tr.classList.toggle("is-excluded", out.checked);
      _dvzStage("entities.exclude", [...exclude]);
    };
    tr.insertCell().append(out);
    tr.insertCell().append(_dvzEntityImageCell(entity.name));   // גל 51 (83-dataviz-look.js)
    tr.insertCell().append(_dvzFocusCell(entity.name));   // 20.10.2026: מצב פוקוס (82-dataviz-story.js)
  }
  box.append(table);
  uiBus.emit("dvz:entities-tab", box);   // 27.10.2026: sparkline ודגלים (85-dataviz-plus.js)
  return box;
}

// --- מה שונה מול config.yaml ---
function _dvzChangesTab() {
  const box = _dvzEdEl("div", "dvz-changes");
  const changes = dvzEd.data.changes;
  if (!changes.length && !Object.keys(dvzEd.draft).length) {
    box.append(_dvzEdEl("p", "empty-msg", "הפרק בדיוק כמו config.yaml שלו - אין שינויים שמורים."));
    return box;
  }
  const table = _dvzEdEl("table", "dvz-changes-table");
  const head = table.createTHead().insertRow();
  for (const title of ["הגדרה", "בקובץ / ברירת מחדל", "עכשיו", ""]) head.appendChild(_dvzEdEl("th", "", title));
  const tbody = table.createTBody();
  for (const change of changes) {
    const tr = tbody.insertRow();
    tr.classList.toggle("is-reset", dvzEd.unset.has(change.path));
    tr.insertCell().textContent = change.label;
    tr.insertCell().textContent = (change.from_file ? "📄 " : "") + _dvzShow(change.was);
    tr.insertCell().textContent = _dvzShow(change.now);
    const reset = _dvzEdEl("button", "btn-xs", "↺");
    reset.type = "button";
    reset.title = "בטל את השינוי הזה";
    reset.setAttribute("aria-label", reset.title);
    reset.onclick = () => _dvzStageUnset(change.path);
    tr.insertCell().append(reset);
  }
  for (const [path, value] of Object.entries(dvzEd.draft)) {
    const tr = tbody.insertRow();
    tr.className = "is-draft";
    tr.insertCell().textContent = path;
    tr.insertCell().textContent = "—";
    tr.insertCell().textContent = "✏️ " + _dvzShow(value);
    tr.insertCell();
  }
  box.append(table);
  return box;
}

// ============================================================================
// גל 53: נוחות בעורך הגרפים - ביטול וחזרה לטיוטה של העורך המלא, קיצורי מקלדת, סימני האירועים / הפרקים /
// העצירות על הסליידר של התצוגה החיה, חיפוש הגדרה בעורך, תצוגה מונפשת (GIF קצר סביב הרגע, לא רק פריים בודד),
// ותגיות ותיקיות לפרקים ברשימה. ב-bundle השני של המסך (dataviz_pro).
// ============================================================================

// --- ביטול וחזרה: תמונת מצב של הטיוטה לפני כל שינוי (הקלדה רצופה באותו שדה = שינוי אחד) ---
const DVZ_UNDO_LIMIT = 100;
let dvzUndo = {past: [], future: [], lastPath: "", lastAt: 0};

function _dvzSnapshot() {
  return {draft: JSON.parse(JSON.stringify(dvzEd.draft)), unset: [...dvzEd.unset]};
}

// נקרא מ-_dvzStage / _dvzStageUnset / ביטול הטיוטה (44-dataviz-editor.js) לפני שהטיוטה משתנה
function _dvzRecordUndo(path) {
  const now = Date.now();
  if (path && path === dvzUndo.lastPath && now - dvzUndo.lastAt < 1200) { dvzUndo.lastAt = now; return; }
  dvzUndo.past.push(_dvzSnapshot());
  if (dvzUndo.past.length > DVZ_UNDO_LIMIT) dvzUndo.past.shift();
  dvzUndo.future = [];
  dvzUndo.lastPath = path || "";
  dvzUndo.lastAt = now;
  _dvzSyncUndoButtons();
}

function _dvzResetUndo() {
  dvzUndo = {past: [], future: [], lastPath: "", lastAt: 0};
  _dvzSyncUndoButtons();
}

function _dvzRestore(state) {
  dvzEd.draft = state.draft;
  dvzEd.unset = new Set(state.unset);
  dvzUndo.lastPath = "";
  _dvzSyncDraftBar();
  _dvzRenderEditor();
  dvzPreviewSoon();
  _dvzSyncUndoButtons();
}

function dvzUndoDraft() {
  if (!dvzUndo.past.length) return;
  dvzUndo.future.push(_dvzSnapshot());
  _dvzRestore(dvzUndo.past.pop());
}

function dvzRedoDraft() {
  if (!dvzUndo.future.length) return;
  dvzUndo.past.push(_dvzSnapshot());
  _dvzRestore(dvzUndo.future.pop());
}

function _dvzSyncUndoButtons() {
  const undo = document.getElementById("dvzUndoBtn");
  const redo = document.getElementById("dvzRedoBtn");
  if (undo) undo.disabled = !dvzUndo.past.length;
  if (redo) redo.disabled = !dvzUndo.future.length;
}

// --- חיפוש הגדרה בעורך המלא ---
function _dvzFieldSearch(body) {
  const input = _dvzEdEl("input", "dvz-field-search");
  input.type = "search";
  input.id = "dvzFieldSearch";
  input.placeholder = "🔍 חיפוש הגדרה (שם, הסבר או נתיב)...";
  input.setAttribute("aria-label", "חיפוש הגדרה");
  input.value = dvzEd.search || "";
  const apply = () => {
    dvzEd.search = input.value;
    const query = input.value.trim().toLowerCase();
    body.classList.toggle("dvz-searching", !!query);   // חיפוש מציג הכל, גם קבוצות שהרמה מסתירה
    for (const group of body.querySelectorAll(".dvz-group")) {
      let hits = 0;
      for (const row of group.querySelectorAll(".dvz-field")) {
        const text = `${row.dataset.path} ${row.textContent}`.toLowerCase();
        const match = !query || text.includes(query);
        row.hidden = !match;
        if (match) hits++;
      }
      group.hidden = !!query && !hits;
      if (query && hits) group.open = true;
    }
  };
  input.oninput = apply;
  body.prepend(input);
  if (input.value) apply();
  _dvzApplyMode();
}

// --- מאיפה הערך (19.10.2026): שבב אחד בראש השדה שאומר מי קובע - טיוטה, שינוי מהדפדפן, config.yaml או ברירת המחדל ---
function _dvzSourceChip(field, changed) {
  const [cls, text, title] = field.path in dvzEd.draft ? ["is-changed is-draft", "📝 טיוטה - עוד לא נשמרה", "שינוי בטיוטה - ייכנס רק אחרי 💾 שמור"]
    : changed ? ["is-changed", "✏️ שונה בדפדפן", "הערך נשמר בקובץ השינויים של הפרק (data/dataviz_overrides) - config.yaml לא השתנה"]
    : field.in_file && !dvzEd.unset.has(field.path) ? ["is-file", "📄 config.yaml", "הערך מ-config.yaml של הפרק"]
    : ["is-default", "⚙️ ברירת מחדל", "ברירת המחדל של המנוע - לא בקובץ ולא שונה כאן"];
  const chip = _dvzEdEl("span", "dvz-chip dvz-src " + cls, text);
  chip.title = title;
  return chip;
}

// נקרא מ-_dvzStage: שדה שנערך עכשיו הוא טיוטה (בלי לצייר את כל העורך מחדש באמצע הקלדה)
function _dvzSyncSourceChip(path) {
  const chip = document.querySelector(`#dvzEditorBody .dvz-field[data-path="${CSS.escape(path)}"] .dvz-src`);
  const field = chip && dvzEd.data.groups.flatMap(g => g.fields).find(f => f.path === path);
  if (field) chip.replaceWith(_dvzSourceChip(field, true));
}

// --- ההגדרות הסופיות: מה שהרינדור יקבל (config.yaml + שינויים מהדפדפן + ברירות המחדל), לקריאה בלבד ---
const DVZ_SOURCE_LABELS = {override: "✏️ שונה בדפדפן", file: "📄 config.yaml", default: "⚙️ ברירת מחדל"};
let _dvzFinal = null;

// 21.10.2026: נבנה בפתיחה הראשונה (לא ב-HTML של המסך - תקציב ה-HTML של dataviz הוא 30K)
function _dvzFinalDialog() {
  if (!document.getElementById("dvzFinalDialog")) document.getElementById("dvzNewDialog").insertAdjacentHTML("afterend", `<dialog id="dvzFinalDialog" class="dvz-dialog" aria-labelledby="dvzFinalHeading">
    <div class="tc-row dvz-dialog-head">
      <h3 id="dvzFinalHeading">📜 ההגדרות הסופיות של הרינדור</h3>
      <button type="button" class="btn-sm" onclick="document.getElementById('dvzFinalDialog').close()">✕ סגור</button>
    </div>
    <div class="hint u-block">config.yaml של הפרק, מעליו השינויים מהדפדפן (data/dataviz_overrides), ומתחת ברירות המחדל של המנוע - בדיוק מה שהרינדור יקבל. לקריאה בלבד.</div>
    <div class="tc-row">
      <label><input type="checkbox" id="dvzFinalChanged" checked onchange="_dvzRenderFinal()"> רק מה שלא ברירת מחדל</label>
      <button type="button" class="btn-sm" onclick="dvzCopyFinalYaml()">📋 העתק כ-YAML</button>
      <span class="hint" id="dvzFinalMsg" role="status" aria-live="polite"></span>
    </div>
    <div id="dvzFinalBody"></div>
</dialog>`);
  return document.getElementById("dvzFinalDialog");
}

async function dvzShowFinalConfig() {
  const dialog = _dvzFinalDialog();
  const msg = document.getElementById("dvzFinalMsg");
  msg.textContent = "⏳";
  document.getElementById("dvzFinalBody").replaceChildren();
  if (!dialog.open) dialog.showModal();
  try {
    const resp = await fetch("/api/dataviz/episodes/final_config?" + new URLSearchParams({episode: dvzState.selected}));
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "הטעינה נכשלה");
    _dvzFinal = data;
    msg.textContent = Object.keys(dvzEd.draft).length ? "יש טיוטה שלא נשמרה - היא לא כאן עד 💾 שמור." : "";
    _dvzRenderFinal();
  } catch (e) {
    msg.textContent = "שגיאה: " + e.message;
  }
}

function _dvzRenderFinal() {
  if (!_dvzFinal) return;
  const onlyChanged = document.getElementById("dvzFinalChanged").checked;
  const table = _dvzEdEl("table", "dvz-changes-table dvz-final-table");
  const head = table.createTHead().insertRow();
  for (const title of ["הגדרה", "ערך", "מקור"]) head.appendChild(_dvzEdEl("th", "", title));
  const tbody = table.createTBody();
  for (const row of _dvzFinal.rows) {
    if (onlyChanged && row.source === "default") continue;
    const tr = tbody.insertRow();
    tr.dataset.source = row.source;
    tr.insertCell().textContent = row.path;
    tr.insertCell().textContent = typeof row.value === "object" && row.value !== null ? JSON.stringify(row.value).slice(0, 160) : _dvzShow(row.value);
    const origin = tr.insertCell();
    origin.textContent = DVZ_SOURCE_LABELS[row.source];
    if (row.auto) {   // 20.10.2026: בחירה של עורך הגרפים החכם - למה, ובאיזה ביטחון
      tr.dataset.auto = "1";
      origin.prepend("🤖 ");
      origin.title = `${row.auto.reason} (ביטחון ${Math.round(row.auto.confidence * 100)}%)`;
    }
  }
  document.getElementById("dvzFinalBody").replaceChildren(table);
}

async function dvzCopyFinalYaml() {
  if (!_dvzFinal) return;
  try {
    await navigator.clipboard.writeText(_dvzFinal.yaml);
    document.getElementById("dvzFinalMsg").textContent = "📋 הועתק";
  } catch (e) {
    document.getElementById("dvzFinalMsg").textContent = "ההעתקה נכשלה: " + e.message;
  }
}

// --- שלוש רמות כמו בסטודיו (19.10.2026): "פשוט" = בסיסי, טקסטים, וידאו ומוזיקה; "רגיל" = בלי הקבוצות הנדירות;
// "מומחה" = הכל. קבוצה עם הגדרה ששונתה תמיד מוצגת, וחיפוש מציג הכל. הבחירה נשמרת בדפדפן ---
const DVZ_MODES = ["simple", "regular", "advanced"];
const DVZ_SIMPLE_GROUPS = new Set(["basic", "texts", "video", "audio"]);
const DVZ_RARE_GROUPS = new Set(["series", "brand", "captions", "map", "share", "data"]);

function _dvzCurrentMode() {
  let mode = null;
  try { mode = localStorage.getItem("dvzMode"); } catch (e) { /* בלי אחסון - ברירת המחדל */ }
  return DVZ_MODES.includes(mode) ? mode : "simple";
}

function setDvzMode(mode) {
  try { localStorage.setItem("dvzMode", DVZ_MODES.includes(mode) ? mode : "simple"); } catch (e) { /* רק לטעינה הזו */ }
  _dvzApplyMode();
}

function _dvzGroupInMode(id, mode) {
  return mode === "advanced" || (mode === "simple" ? DVZ_SIMPLE_GROUPS.has(id) : !DVZ_RARE_GROUPS.has(id));
}

function _dvzApplyMode() {
  const mode = _dvzCurrentMode();
  const panel = document.querySelector('[data-tab-panel="dataviz"]');   // 21.10.2026: הרמה לכל המסך - מה שמוסתר ב"פשוט" ב-27-dataviz-pro.css
  if (panel) panel.dataset.dvzMode = mode;
  for (const [key, id] of [["simple", "dvzModeSimpleBtn"], ["regular", "dvzModeRegularBtn"], ["advanced", "dvzModeAdvancedBtn"]]) {
    const btn = document.getElementById(id);
    if (btn) btn.setAttribute("aria-pressed", String(key === mode));
  }
  const body = document.getElementById("dvzEditorBody");
  if (!body) return;
  let hidden = 0;
  for (const group of body.querySelectorAll(".dvz-group")) {
    const rare = !_dvzGroupInMode(group.dataset.group, mode) && !group.querySelector(".dvz-field.is-changed");
    group.classList.toggle("dvz-rare", rare);
    if (rare) hidden += group.querySelectorAll(".dvz-field").length;
  }
  let chip = document.getElementById("dvzRareChip");
  if (!chip) {
    chip = _dvzEdEl("button", "dvz-chip dvz-rare-chip");
    chip.type = "button";
    chip.id = "dvzRareChip";
    chip.title = "מעבר למצב מומחה - כל ההגדרות";
    chip.onclick = () => setDvzMode("advanced");
  }
  const groups = body.querySelector(".dvz-editor-groups");
  if (groups && chip.parentNode !== groups) groups.append(chip);
  chip.hidden = !hidden;
  chip.textContent = `🧰 עוד ${hidden} הגדרות במצב מומחה`;
}

// --- תצוגה מונפשת ---
function _dvzClipUrl(name, pos, extra) {
  // 27.10.2026: format=mp4 - וידאו קצר (בכרטיס המסך כשאפשר) במקום GIF; השרת חוזר ל-GIF כש-ffmpeg נכשל
  return "/api/dataviz/preview_clip?" + new URLSearchParams({episode: name, pos: String(pos), format: "mp4", ...(extra || {})}).toString();
}

function dvzToggleAnimation(on) {
  dvzState.animate = on === undefined ? !dvzState.animate : !!on;
  const btn = document.getElementById("dvzAnimateBtn");
  if (btn) {
    btn.setAttribute("aria-pressed", String(dvzState.animate));
    btn.textContent = dvzState.animate ? "⏸ פריים בודד" : "▶ הנפשה";
  }
  dvzLoadPreview();
}

// --- סימנים על הסליידר ---
const DVZ_MARKER_ICONS = {event: "📍", chapter: "📑", pause: "⏸", start: "▶", outro: "🏁"};
let _dvzMarkersFor = "";

// נקרא בסוף dvzLoadPreview: הסימנים נטענים מחדש רק כשהפרק או הטיוטה השתנו (אירוע / פרק חדש), לא בכל הזזה
function _dvzMaybeReloadMarkers() {
  const key = `${dvzState.selected}|${_dvzDraftParam()}`;
  if (key === _dvzMarkersFor) return;
  _dvzMarkersFor = key;
  uiDebounce("dvz:markers", _dvzLoadMarkers, 400);
}

async function _dvzLoadMarkers() {
  const layer = document.getElementById("dvzMarkers");
  if (!layer || !dvzState.selected) return;
  const episode = dvzState.selected;
  const params = {episode};
  const draft = _dvzDraftParam();
  if (draft) params.draft = draft;
  try {
    const resp = await fetch("/api/dataviz/preview_markers?" + new URLSearchParams(params));
    const data = await _dvzJson(resp);
    if (!resp.ok || dvzState.selected !== episode) return;
    layer.replaceChildren(...data.markers.map(marker => {
      const btn = _dvzEdEl("button", "dvz-marker is-" + marker.kind, DVZ_MARKER_ICONS[marker.kind] || "•");
      btn.type = "button";
      btn.style.insetInlineStart = `${(marker.pos * 100).toFixed(2)}%`;
      btn.title = marker.label || {start: "תחילת המרוץ", outro: "הסיום"}[marker.kind] || "";
      btn.setAttribute("aria-label", btn.title || marker.kind);
      btn.dataset.pos = String(marker.pos);
      btn.onclick = () => { document.getElementById("dvzPreviewPos").value = String(Math.round(marker.pos * 1000)); dvzLoadPreview(); };
      return btn;
    }));
  } catch (e) { /* בלי סימנים */ }
}

// --- תגיות ותיקיות לפרקים ---
// נקרא מ-_dvzCardBadges (43-dataviz-studio.js) - תוויות בלבד (הכרטיס כולו כפתור; חיפוש "#תגית" מסנן)
function _dvzTagChips(ep, box) {
  for (const tag of ep.tags || []) box.append(_dvzEdEl("span", "dvz-badge is-tag", "#" + tag));
}

// נקרא מ-_dvzEpisodeWrap (42-dataviz-screen.js) - ליד "הסתר מהרשימה", מחוץ לכפתור של הכרטיס
function _dvzTagEditButton(ep) {
  const edit = _dvzEdEl("button", "btn-xs btn-ghost dvz-tag-edit", "🏷️ תגיות");
  edit.type = "button";
  edit.title = "תגיות ותיקייה ברשימה";
  edit.setAttribute("aria-label", `תגיות ותיקייה ל-${ep.title || ep.name}`);
  edit.onclick = () => _dvzOpenTagEditor(ep, edit);
  return edit;
}

function _dvzOpenTagEditor(ep, anchor) {
  document.querySelectorAll(".dvz-tag-form").forEach(f => f.remove());
  const form = _dvzEdEl("div", "dvz-tag-form");
  const tags = _dvzEdEl("input");
  tags.type = "text";
  tags.value = (ep.tags || []).join(", ");
  tags.placeholder = "תגיות, מופרדות בפסיק";
  tags.setAttribute("aria-label", "תגיות");
  const folder = _dvzEdEl("input");
  folder.type = "text";
  folder.value = ep.folder || "";
  folder.placeholder = "תיקייה (לא חובה)";
  folder.setAttribute("aria-label", "תיקייה");
  folder.setAttribute("list", "dvzFolderNames");
  const names = _dvzEdEl("datalist");
  names.id = "dvzFolderNames";
  for (const name of new Set(dvzState.episodes.map(e => e.folder).filter(Boolean))) names.appendChild(new Option(name, name));
  const save = _dvzEdEl("button", "btn-xs btn-primary", "💾");
  save.type = "button";
  save.setAttribute("aria-label", "שמור תגיות");
  save.onclick = async () => {
    const resp = await fetch("/api/dataviz/episodes/tags", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({episode: ep.name, tags: tags.value.split(",").map(t => t.trim().replace(/^#/, "")).filter(Boolean), folder: folder.value})});
    const data = await _dvzJson(resp);
    if (!resp.ok) { uiToast(data.error || "השמירה נכשלה", "warn"); return; }
    ep.tags = data.tags;
    ep.folder = data.folder;
    dvzRenderEpisodes();
  };
  form.append(tags, folder, names, save);
  anchor.after(form);
  tags.focus();
}

// הטקסט שהחיפוש ברשימה מחפש בו - גם התגיות (עם #) והתיקייה
function _dvzEpisodeSearchText(ep) {
  return `${ep.name} ${ep.title || ""} ${ep.subtitle || ""} ${(ep.tags || []).map(t => "#" + t).join(" ")} ${ep.folder || ""}`.toLowerCase();
}

// נקרא מסוף dvzRenderEpisodes (43-dataviz-studio.js): כותרת לכל תיקייה, פרקים בלי תיקייה בסוף
function _dvzGroupByFolder(list) {
  const cards = [...list.children];
  const folderOf = (node) => (dvzState.episodes.find(e => e.name === (node.querySelector(".dvz-card") || node).dataset.episode) || {}).folder || "";
  if (!cards.some(folderOf)) return;
  const groups = new Map();
  for (const node of cards) {
    const key = folderOf(node);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(node);
  }
  const ordered = [...groups.keys()].sort((a, b) => (a === "") - (b === "") || a.localeCompare(b, "he"));
  list.replaceChildren(...ordered.flatMap(key => [_dvzEdEl("div", "dvz-folder-head", key ? `📁 ${key}` : "📄 בלי תיקייה"), ...groups.get(key)]));
}

// --- קיצורי מקלדת ---
function _dvzTyping(target) {
  return target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
}

function _dvzStepPreview(delta) {
  const slider = document.getElementById("dvzPreviewPos");
  slider.value = String(Math.max(0, Math.min(1000, parseInt(slider.value, 10) + delta)));
  dvzPreviewSoon();
}

function _dvzOnKey(e) {
  const panel = document.querySelector('[data-tab-panel="dataviz"]');
  if (!panel || panel.hidden || !dvzState.selected) return;
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && e.key.toLowerCase() === "s") {
    if (!document.getElementById("dvzDraftSave").disabled) { e.preventDefault(); dvzSaveDraft(); }
    return;
  }
  if (_dvzTyping(e.target)) return;   // בתוך שדה - הדפדפן מבטל / מזיז את הסמן כרגיל
  const rtl = document.documentElement.dir === "rtl";
  const step = e.shiftKey ? 100 : 10;
  if (ctrl && (e.key.toLowerCase() === "y" || (e.shiftKey && e.key.toLowerCase() === "z"))) { e.preventDefault(); dvzRedoDraft(); }
  else if (ctrl && e.key.toLowerCase() === "z") { e.preventDefault(); dvzUndoDraft(); }
  else if (ctrl || e.altKey) return;
  else if (e.key === " ") {
    if (["BUTTON", "A", "SUMMARY"].includes(e.target.tagName)) return;   // רווח על כפתור ממוקד - לוחץ עליו, כרגיל
    e.preventDefault();
    dvzToggleAnimation();
  }
  else if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); _dvzStepPreview((e.key === "ArrowRight") !== rtl ? step : -step); }
  else if (e.key === "Home" || e.key === "End") { e.preventDefault(); _dvzStepPreview(e.key === "Home" ? -1000 : 1000); }
  else if (e.key === "?") uiToast("⌨️ רווח - הנפשה · חצים - הזזת הרגע (Shift - צעד גדול) · Home/End - התחלה/סוף · Ctrl+Z / Ctrl+Y - ביטול וחזרה · Ctrl+S - שמירה", "info");
}

// --- אתחול: כפתורים שנוספים לדף, והסליידר עטוף בשכבת סימנים ---
function _dvzInitEditor2() {
  const save = document.getElementById("dvzDraftSave");
  if (save && !document.getElementById("dvzUndoBtn")) {
    for (const [id, label, title, action] of [["dvzUndoBtn", "↶", "בטל (Ctrl+Z)", dvzUndoDraft], ["dvzRedoBtn", "↷", "חזור (Ctrl+Y)", dvzRedoDraft]]) {
      const btn = _dvzEdEl("button", "btn-sm", label);
      btn.type = "button";
      btn.id = id;
      btn.title = title;
      btn.setAttribute("aria-label", title);
      btn.disabled = true;
      btn.onclick = action;
      save.before(btn);
    }
  }
  const slider = document.getElementById("dvzPreviewPos");
  if (slider && !document.getElementById("dvzMarkers")) {
    const wrap = _dvzEdEl("div", "dvz-slider-wrap");
    slider.before(wrap);
    const layer = _dvzEdEl("div", "dvz-markers");
    layer.id = "dvzMarkers";
    wrap.append(slider, layer);
    const play = _dvzEdEl("button", "btn-sm", "▶ הנפשה");
    play.type = "button";
    play.id = "dvzAnimateBtn";
    play.title = "GIF קצר סביב הרגע שנבחר (רווח)";
    play.setAttribute("aria-pressed", "false");
    play.onclick = () => dvzToggleAnimation();
    wrap.after(play);
  }
  document.addEventListener("keydown", _dvzOnKey);
}

_dvzInitEditor2();
