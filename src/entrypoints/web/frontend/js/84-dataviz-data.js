// ============================================================================
// גל 40: הנתונים של פרק בעורך הגרפים - מקורות (מיפוי עמודות ו-20 שורות), בדיקה לפני ריצה,
// טבלת המצטבר, קצב (פריימים ליום, כלל ה-STEP) עם ציר האירועים, ההאטות והשיאים, פיזור סכום
// של חודש/שנה על הימים, עדכון נתונים עם השוואת סכומים, Excel/JSON וגרירת קובץ למסך, ומוזיקה
// על גרף גלי הקול (לשונית בעורך המלא).
// ============================================================================

// 21.10.2026: "✅ בדיקה" ו"🔎 בדיקת עובדות" עברו לרשימה "✅ לפני רינדור" (86-dataviz-publish.js) - _dvzCheckView ו-_dvzFactsView נשארו בשבילה
const DVZ_DATA_TABS = [["sources", "🗂️ מקורות"], ["clean", "🧹 ניקוי"], ["cumulative", "📈 מצטבר"], ["pacing", "⏱ קצב וציר זמן"], ["spread", "🧮 פיזור"],
  ["update", "🔄 עדכון נתונים"], ["remote", "🌐 מכתובת ותזמון"]];   // גל 52: ניקוי ומכתובת (בהמשך הקובץ)
let dvzData = {tab: "sources", cache: {}, source: 0, update: null};

async function _dvzFetchPart(part, source) {
  const key = `${dvzState.selected}|${part}|${source || 0}`;
  if (dvzData.cache[key]) return dvzData.cache[key];
  const resp = await fetch("/api/dataviz/episodes/data?" + new URLSearchParams({episode: dvzState.selected, part, source: String(source || 0)}));
  const data = await _dvzJson(resp);
  if (!resp.ok) throw new Error(data.error || "הטעינה נכשלה");
  dvzData.cache[key] = data.data;
  return data.data;
}

function dvzLoadData() {
  _dvzRenderDataTabs();
  _dvzRenderDataTab();
}

function _dvzRenderDataTabs() {
  document.getElementById("dvzDataTabs").replaceChildren(...DVZ_DATA_TABS.map(([key, label]) => {
    const btn = _dvzEdEl("button", key === dvzData.tab ? "active" : "", label);
    btn.type = "button";
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", String(key === dvzData.tab));
    btn.dataset.tab = key;
    btn.onclick = () => { dvzData.tab = key; dvzLoadData(); };
    return btn;
  }));
}

async function _dvzRenderDataTab() {
  const body = document.getElementById("dvzDataBody");
  const status = document.getElementById("dvzDataStatus");
  if (!dvzState.selected) return;
  const ticket = dvzData.ticket = (dvzData.ticket || 0) + 1;   // רק הבקשה האחרונה מציירת - תשובה איטית של לשונית קודמת לא דורסת
  status.textContent = "⏳";
  try {
    const node = await {sources: _dvzSourcesView, check: _dvzCheckView, cumulative: _dvzCumulativeView, pacing: _dvzPacingView,
      spread: _dvzSpreadView, update: _dvzUpdateView, clean: _dvzCleanView, remote: _dvzRemoteView, facts: _dvzFactsView}[dvzData.tab]();
    if (ticket !== dvzData.ticket) return;
    body.replaceChildren(node);
    status.textContent = "";
  } catch (e) {
    if (ticket !== dvzData.ticket) return;
    body.replaceChildren();
    status.textContent = "שגיאה: " + e.message;
  }
}

function _dvzTable(headers, rows, cls) {
  const table = _dvzEdEl("table", "dvz-data-table" + (cls ? " " + cls : ""));
  const head = table.createTHead().insertRow();
  for (const title of headers) head.appendChild(_dvzEdEl("th", "", title));
  const body = table.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    for (const cell of row) tr.insertCell().textContent = cell === null || cell === undefined ? "" : (typeof cell === "number" ? cell.toLocaleString("he-IL", {maximumFractionDigits: 2}) : String(cell));
  }
  return table;
}

// --- מקורות: מיפוי העמודות ו-20 השורות הראשונות ---
async function _dvzSourcesView() {
  const sources = await _dvzFetchPart("sources");
  const box = _dvzEdEl("div", "dvz-sources");
  for (const src of sources) {
    const card = _dvzEdEl("div", "dvz-source");
    const head = _dvzEdEl("div", "dvz-source-head");
    head.append(_dvzEdEl("strong", "", `${src.index + 1}. ${src.path}`), _dvzEdEl("span", "dvz-chip", src.type),
      _dvzEdEl("span", "dvz-chip", `⏱ ${src.time.column} (${{day: "יום", month: "חודש", year: "שנה"}[src.time.period] || src.time.period})`),
      _dvzEdEl("span", "dvz-chip", `🔢 ${src.value === "count" ? "ספירת שורות" : src.value}`),
      _dvzEdEl("span", "dvz-chip", `🏷️ ${src.entity}`));
    if (src.legend) head.append(_dvzEdEl("span", "dvz-chip", `מקרא: ${src.legend}`));
    if (src.kind === "level") head.append(_dvzEdEl("span", "dvz-chip", "📈 רמה"));
    if (src.axis === "right") head.append(_dvzEdEl("span", "dvz-chip", "↔️ ציר ימני"));
    if (src.fill && src.fill !== "none") head.append(_dvzEdEl("span", "dvz-chip", src.fill === "step" ? "📶 מדרגות" : "📈 קו ישר"));
    head.append(_dvzEditMappingButton(src, card));
    head.append(_dvzEditGridButton(src, card));   // 20.10.2026
    if (src.removable) head.append(_dvzRemoveSourceButton(src));
    if (src.weights) head.append(_dvzEdEl("span", "dvz-chip", `⚖️ משקלות: ${src.weights}`));
    if (src.weights_removable) head.append(_dvzRemoveWeightsButton(src));
    const counts = _dvzEdEl("div", "hint", [`${src.total_rows} שורות`, `${src.valid_rows} תקינות`, src.dropped_rows ? `⚠️ ${src.dropped_rows} נזרקו` : ""].filter(Boolean).join(" · "));
    const scroll = _dvzEdEl("div", "dvz-table-scroll");
    scroll.append(_dvzTable(src.columns, src.rows));
    card.append(head, counts, scroll);
    box.append(card);
  }
  return box;
}

// 19.10.2026: עריכת המיפוי של מקור קיים - נשמר ב-override של הפרק (config.yaml וקובץ הנתונים לא משתנים)
function _dvzEditMappingButton(src, card) {
  const button = _dvzEdEl("button", "btn-sm dvz-edit-mapping", "✏️ מיפוי");
  button.type = "button";
  button.title = "עמודת התאריך, התקופה, הערך, הקיבוץ וסוג הערכים של המקור הזה";
  button.onclick = () => {
    const open = card.querySelector(".dvz-mapping-edit");
    if (open) { open.remove(); return; }
    const box = _dvzEdEl("div", "dvz-mapping-edit");
    const entity = String(src.entity || "");
    const mapping = _dvzSourceMapping(src.columns, {time_column: src.time.column, period: src.time.period, value_column: src.value === "count" ? "" : src.value,
      group_column: entity.startsWith("from_time:") ? "" : entity, legend: src.legend, kind: src.kind, axis: src.axis, fill: src.fill});
    const save = _dvzEdEl("button", "btn-sm btn-primary", "💾 שמור מיפוי");
    save.type = "button";
    save.onclick = () => _dvzDataAction(async () => {
      const resp = await fetch("/api/dataviz/episodes/source_mapping", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({episode: dvzState.selected, source: src.index, mapping: _dvzMappingValues(mapping)})});
      const data = await _dvzJson(resp);
      if (!resp.ok) throw new Error(data.error || "השמירה נכשלה");
      await _dvzDataChanged();
    }, "✅ המיפוי נשמר - config.yaml לא השתנה.");
    box.append(mapping, save);
    card.querySelector(".dvz-source-head").after(box);
  };
  return button;
}

// 18.10.2026: הסרת מקור שנוסף מהדפדפן - רק מה-override; הקובץ נשאר בדיסק בלי שינוי
function _dvzRemoveSourceButton(src) {
  const button = _dvzEdEl("button", "btn-sm dvz-remove-source", "🗑️ הסר");
  button.type = "button";
  button.title = "הסר את המקור הזה מהפרק - הקובץ נשאר בדיסק";
  button.onclick = async () => {
    if (!await veConfirm(`להסיר את המקור "${src.path}" מהפרק? הקובץ עצמו נשאר בדיסק.`, {danger: true, okLabel: "🗑️ הסר"})) return;
    await _dvzDataAction(async () => {
      const resp = await fetch("/api/dataviz/episodes/remove_source", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({episode: dvzState.selected, source: src.index})});
      const data = await _dvzJson(resp);
      if (!resp.ok) throw new Error(data.error || "ההסרה נכשלה");
      await _dvzDataChanged();
    }, "✅ המקור הוסר מהפרק.");
  };
  return button;
}

// --- בדיקה לפני ריצה ---
async function _dvzCheckView() {
  const check = await _dvzFetchPart("check");
  const box = _dvzEdEl("div", "dvz-check");
  box.append(_dvzEdEl("p", "hint", `${check.days} ימים (${check.start} עד ${check.end}) · ${check.entities} ישויות · סכום ${Math.round(check.total).toLocaleString("he-IL")}`));
  if (!check.findings.length) box.append(_dvzEdEl("p", "dvz-check-ok", "✅ לא נמצא שום דבר חשוד בנתונים."));
  for (const finding of check.findings) box.append(_dvzEdEl("p", "dvz-finding is-" + finding.level, (finding.level === "warn" ? "⚠️ " : "ℹ️ ") + finding.text));
  return box;
}

// סימון ליד "הרץ" כשיש מה לבדוק בנתונים - נטען ברקע לכל פרק שנבחר
async function _dvzCheckBadge() {
  const badge = document.getElementById("dvzDataBadge");
  badge.hidden = true;
  if (!dvzState.selected) return;
  const name = dvzState.selected;
  try {
    const check = await _dvzFetchPart("check");
    if (dvzState.selected !== name) return;
    const warnings = check.findings.filter(f => f.level === "warn").length;
    badge.hidden = false;   // 21.10.2026: תמיד - הכניסה לרשימה "✅ לפני רינדור"; עם אזהרות בנתונים - המספר
    badge.classList.toggle("is-warn", !!warnings);
    badge.textContent = warnings ? `⚠️ לפני רינדור (${warnings})` : "✅ לפני רינדור";
  } catch (e) { /* בלי סימון */ }
}

// --- המצטבר ---
async function _dvzCumulativeView() {
  const table = await _dvzFetchPart("cumulative");
  const box = _dvzEdEl("div", "dvz-table-scroll");
  box.append(_dvzTable(["תאריך", ...table.columns], table.rows));
  return box;
}

// --- גרף: קצב (פריימים ליום) עם אירועים, האטות ושיאים ---
const SVG_NS = "http://www.w3.org/2000/svg";

function _dvzSvg(tag, attrs, text) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) el.setAttribute(key, String(value));
  if (text !== undefined) el.textContent = text;
  return el;
}

function _dvzLineChart(points, opts) {
  const width = 640, height = 180, pad = 24;
  const values = points.map(p => p.value);
  const max = Math.max(...values, opts.base || 0, 1e-9);
  const x = (i) => pad + (points.length > 1 ? i / (points.length - 1) : 0) * (width - 2 * pad);
  const y = (v) => height - pad - v / max * (height - 2 * pad);
  const svg = _dvzSvg("svg", {viewBox: `0 0 ${width} ${height}`, class: "dvz-chart", role: "img", "aria-label": opts.label});
  const indexOf = (date) => points.findIndex(p => p.date >= date);
  for (const window of opts.windows || []) {
    const a = indexOf(window.from), b = indexOf(window.to);
    if (a < 0) continue;
    svg.append(_dvzSvg("rect", {class: "dvz-chart-window", x: x(a), y: pad, width: Math.max(2, x(b < 0 ? points.length - 1 : b) - x(a)), height: height - 2 * pad}));
  }
  if (opts.base) {
    svg.append(_dvzSvg("line", {class: "dvz-chart-base", x1: pad, x2: width - pad, y1: y(opts.base), y2: y(opts.base)}),
      _dvzSvg("text", {class: "dvz-chart-note", x: width - pad, y: y(opts.base) - 4, "text-anchor": "end"}, opts.baseLabel || ""));
  }
  svg.append(_dvzSvg("polyline", {class: "dvz-chart-line", points: points.map((p, i) => `${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ")}));
  for (const mark of opts.marks || []) {
    const i = indexOf(mark.date);
    if (i < 0) continue;
    const g = _dvzSvg("g", {class: "dvz-chart-mark " + (mark.kind || "")});
    g.append(_dvzSvg("line", {x1: x(i), x2: x(i), y1: pad, y2: height - pad}), _dvzSvg("title", {}, mark.title));
    svg.append(g);
  }
  svg.append(_dvzSvg("text", {class: "dvz-chart-axis", x: pad, y: height - 6}, points[0] ? points[0].date : ""),
    _dvzSvg("text", {class: "dvz-chart-axis", x: width - pad, y: height - 6, "text-anchor": "end"}, points.length ? points[points.length - 1].date : ""),
    _dvzSvg("text", {class: "dvz-chart-axis", x: pad, y: pad - 8}, opts.yLabel || ""));
  return svg;
}

async function _dvzPacingView() {
  const pace = await _dvzFetchPart("pacing");
  const box = _dvzEdEl("div", "dvz-pacing");
  box.append(_dvzEdEl("p", "hint", `${pace.total_frames} פריימים ≈ ${_dvzDuration(pace.seconds)} ב-${pace.fps} פריימים לשנייה.`),
    _dvzEdEl("p", "hint", `כלל ה-STEP: אף ערך לא מתקדם ביותר מ-${(pace.step * 100).toFixed(2)}% מהציר בפריים אחד - ב-${pace.step_limited_days} ימים הוא האט את הסרטון (מעל הקו).`));
  box.append(_dvzLineChart(pace.points.map(p => ({date: p.date, value: p.frames})), {
    label: "פריימים לכל יום לאורך הפרק", yLabel: "פריימים ליום", base: pace.base, baseLabel: "קצב בסיס",
    windows: pace.slowdowns,
    marks: [...pace.events.map(e => ({date: e.date, title: `📍 ${e.date} · ${e.label}`, kind: "is-event"})),
            ...pace.peaks.map(p => ({date: p.date, title: `🔥 ${p.date} · ${Math.round(p.total).toLocaleString("he-IL")}`, kind: "is-peak"}))],
  }));
  const legend = _dvzEdEl("div", "dvz-chart-legend");
  legend.append(_dvzEdEl("span", "is-event", "📍 אירוע"), _dvzEdEl("span", "is-window", "▒ האטה סביב אירוע"), _dvzEdEl("span", "is-peak", "🔥 שיא יומי"));
  box.append(legend);
  box.append(_dvzTable(["אירוע", "תאריך"], pace.events.map(e => [e.label, e.date])));
  return box;
}

// --- פיזור סכום של חודש/שנה על הימים ---
async function _dvzSpreadView() {
  const sources = await _dvzFetchPart("sources");
  const box = _dvzEdEl("div", "dvz-spread");
  const select = _dvzEdEl("select");
  select.setAttribute("aria-label", "מקור");
  sources.forEach(src => select.appendChild(new Option(`${src.index + 1}. ${src.path} (${src.time.period})`, String(src.index))));
  select.value = String(dvzData.source);
  select.onchange = () => { dvzData.source = parseInt(select.value, 10); _dvzRenderDataTab(); };
  box.append(select);
  const spread = await _dvzFetchPart("spread", dvzData.source);
  if (!spread.points.length) {
    box.append(_dvzEdEl("p", "hint", spread.note || "אין פיזור למקור הזה."));
    return box;
  }
  box.append(_dvzEdEl("p", "hint", `${spread.entity}: סכום של ${Math.round(spread.total).toLocaleString("he-IL")} מתפזר על ${spread.points.length} ימים.`));
  box.append(_dvzLineChart(spread.points, {label: "הפיזור היומי של הסכום", yLabel: "ליום"}));
  return box;
}

// --- עדכון נתונים לפרק קיים ---
async function _dvzUpdateView() {
  const sources = await _dvzFetchPart("sources");   // גל 43: גם מקורות Excel / JSON (הנתונים החדשים נשמרים כ-CSV)
  const box = _dvzEdEl("div", "dvz-update");
  box.append(_dvzEdEl("p", "hint", "קובץ חדש עם אותן עמודות מחליף את הנתונים של מקור. קודם רואים את השינוי בסכומים, ורק אחרי אישור הוא נשמר - כקובץ חדש; הקובץ המקורי לא משתנה."));
  if (!sources.length) { box.append(_dvzEdEl("p", "empty-msg", "אין בפרק מקורות נתונים לעדכן.")); return box; }
  const select = _dvzEdEl("select");
  select.id = "dvzUpdateSource";
  select.setAttribute("aria-label", "המקור לעדכון");
  sources.forEach(src => select.appendChild(new Option(`${src.index + 1}. ${src.path} (${src.columns.join(", ")})`, String(src.index))));
  const file = _dvzEdEl("input");
  file.type = "file";
  file.id = "dvzUpdateFile";
  file.accept = ".csv,.tsv,.xlsx,.xls,.json";
  file.setAttribute("aria-label", "קובץ הנתונים החדש");
  const result = _dvzEdEl("div", "dvz-update-result");
  file.onchange = async () => {
    const chosen = file.files && file.files[0];
    if (!chosen) return;
    try {
      const csv = await _dvzFileAsCsv(chosen);
      dvzData.update = {source: parseInt(select.value, 10), csv};
      await _dvzPreviewUpdate(result);
    } catch (e) {
      result.replaceChildren(_dvzEdEl("p", "bad", "שגיאה: " + e.message));
    }
  };
  const first = sources[0];   // ברירת המחדל לקובץ נוסף - המיפוי של המקור הראשון
  box.append(select, file, result, _dvzAddSourceBox({time_column: first.time.column, period: first.time.period,
    value_column: first.value === "count" ? "" : first.value, group_column: String(first.entity).startsWith("from_time:") ? "" : first.entity}),
    _dvzWeightsBox(sources));
  return box;
}

// 18.10.2026: מיפוי העמודות של קובץ נתונים נוסף (פרק חדש מכמה קבצים, או "קובץ נתונים נוסף" לפרק קיים)
function _dvzSourceMapping(columns, defaults) {
  const box = _dvzEdEl("div", "tc-row dvz-source-mapping");
  const d = defaults || {};
  const field = (key, label, options, value) => {
    const wrap = _dvzEdEl("label", "dvz-field-label", label + " ");
    const select = _dvzEdEl("select");
    select.dataset.field = key;
    for (const [v, text] of options) select.appendChild(new Option(text, v));
    select.value = options.some(([v]) => v === value) ? value : options[0][0];
    wrap.append(select);
    box.append(wrap);
  };
  const cols = columns.map(c => [c, c]);
  field("time_column", "עמודת תאריך:", cols, d.time_column);
  field("period", "רזולוציית הזמן:", [["day", "יום"], ["month", "חודש"], ["year", "שנה"]], d.period || "day");
  field("value_column", "ערך:", [["", "ספור שורות"], ...cols], d.value_column);
  field("group_column", "קבץ לפי:", [["", "שנת התאריך"], ...cols], d.group_column);
  field("kind", "סוג הערכים:", [["amount", "כמות (מצטבר)"], ["level", "רמה (טמפרטורה, מפלס)"]], d.kind || "amount");   // 19.10.2026
  field("axis", "ציר (מרוץ קווים):", [["left", "שמאל"], ["right", "ימין - יחידות אחרות"]], d.axis || "left");   // 20.10.2026
  field("fill", "תקופות חסרות:", [["none", "בלי השלמה"], ["step", "מדרגות - הערך הקודם"], ["linear", "קו ישר בין הנקודות"]], d.fill || "none");   // 20.10.2026
  const legend = _dvzEdEl("label", "dvz-field-label", "שם במקרא (לא חובה) ");
  const input = _dvzEdEl("input");
  input.dataset.field = "legend";
  input.maxLength = 120;
  input.value = d.legend || "";
  legend.append(input);
  box.append(legend);
  return box;
}

function _dvzMappingValues(box) {
  const out = {};
  for (const el of box.querySelectorAll("[data-field]")) out[el.dataset.field] = el.value.trim();
  return out;
}

// 18.10.2026: קובץ נתונים נוסף - מקור חדש לצד המקורות שכבר יש (לא מחליף אף אחד)
function _dvzAddSourceBox(defaults) {
  const box = _dvzEdEl("div", "dvz-update");
  box.append(_dvzEdEl("h4", "", "➕ קובץ נתונים נוסף"),
    _dvzEdEl("p", "hint", "קובץ נוסף הופך למקור חדש לצד המקורות שכבר יש. קודם רואים את השינוי בסכומים, ורק אחרי אישור הוא נשמר - כקובץ חדש; קובצי הפרק לא משתנים."));
  const file = _dvzEdEl("input");
  file.type = "file";
  file.id = "dvzAddSourceFile";
  file.accept = ".csv,.tsv,.xlsx,.xls,.json";
  file.setAttribute("aria-label", "קובץ הנתונים הנוסף");
  const mapping = _dvzEdEl("div");
  const result = _dvzEdEl("div", "dvz-update-result");
  file.onchange = async () => {
    const chosen = file.files && file.files[0];
    if (!chosen) return;
    try {
      const csv = await _dvzFileAsCsv(chosen);
      const resp = await fetch("/api/dataviz/episodes/csv_columns", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({csv_text: csv})});
      const data = await _dvzJson(resp);
      if (!resp.ok) throw new Error(data.error || "קריאת ה-CSV נכשלה");
      const fields = _dvzSourceMapping(data.columns, defaults);
      const post = async (confirm) => {
        const r = await fetch("/api/dataviz/episodes/add_source", {method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({..._dvzMappingValues(fields), episode: dvzState.selected, filename: chosen.name, csv_text: csv, confirm})});
        const answer = await _dvzJson(r);
        if (!r.ok) throw new Error(answer.error || "ההוספה נכשלה");
        return answer;
      };
      const check = _dvzEdEl("button", "btn-sm", "🔍 בדוק את השינוי");
      check.type = "button";
      check.id = "dvzAddSourceCheck";
      check.onclick = () => _dvzPreviewUpdate(result, {post, applyText: "✅ הוסף את הקובץ", applyId: "dvzAddSourceApply",
        done: (saved) => `✅ הקובץ נוסף כמקור ${saved.sources} (${saved.file}). קובצי הפרק לא השתנו.`})
        .catch(e => result.replaceChildren(_dvzEdEl("p", "bad", "שגיאה: " + e.message)));
      mapping.replaceChildren(fields, check);
      result.replaceChildren();
    } catch (e) {
      result.replaceChildren(_dvzEdEl("p", "bad", "שגיאה: " + e.message));
    }
  };
  box.append(file, mapping, result);
  return box;
}

async function _dvzPostUpdate(confirm) {
  const resp = await fetch("/api/dataviz/episodes/update_data", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({episode: dvzState.selected, source: dvzData.update.source, csv_text: dvzData.update.csv, confirm})});
  const data = await _dvzJson(resp);
  if (!resp.ok) throw new Error(data.error || "העדכון נכשל");
  return data;
}

async function _dvzPreviewUpdate(result, how) {
  const o = how || {post: _dvzPostUpdate, applyText: "✅ החלף את הנתונים", applyId: "dvzUpdateApply",
    done: (saved) => `✅ הנתונים הוחלפו (${saved.file}). הקובץ המקורי נשאר כמו שהיה.`};   // 18.10.2026: גם לקובץ נוסף
  const cmp = await o.post(false);
  const fmt = (v) => v === null || v === undefined ? "—" : Math.round(v).toLocaleString("he-IL");
  const summary = _dvzEdEl("p", "", `סכום: ${fmt(cmp.total_before)} ← ${fmt(cmp.total_after)} (${cmp.total_after >= cmp.total_before ? "+" : ""}${fmt(cmp.total_after - cmp.total_before)})`);
  const extra = _dvzEdEl("p", "hint", [cmp.new.length ? `חדשות: ${cmp.new.join(", ")}.` : "", cmp.gone.length ? `נעלמו: ${cmp.gone.join(", ")}.` : ""].filter(Boolean).join(" "));
  const table = _dvzTable(["ישות", "לפני", "אחרי", "הפרש"], cmp.rows.map(r => [r.entity, fmt(r.before), fmt(r.after), (r.diff >= 0 ? "+" : "") + fmt(r.diff)]), "dvz-compare-table");
  const apply = _dvzEdEl("button", "btn-primary", o.applyText);
  apply.type = "button";
  apply.id = o.applyId;
  apply.onclick = async () => {
    apply.disabled = true;
    try {
      const saved = await o.post(true);
      result.replaceChildren(_dvzEdEl("p", "", o.done(saved)));
      dvzData.cache = {};
      delete dvzState.estimates[dvzState.selected];
      dvzLoadPreview();
      _dvzCheckBadge();
    } catch (e) {
      apply.disabled = false;
      result.append(_dvzEdEl("p", "bad", "שגיאה: " + e.message));
    }
  };
  result.replaceChildren(summary, extra, table, apply);
}

// --- Excel / JSON / CSV, וגרירת קובץ למסך ---
async function _dvzFileAsCsv(file) {
  if (file.size > 25 * 1024 * 1024) throw new Error("הקובץ גדול מ-25MB.");   // 18.10.2026: כמו CSV_MAX_MB בשרת
  if (/\.(csv|tsv|txt)$/i.test(file.name) && !/\.tsv$/i.test(file.name)) return await file.text();
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  const resp = await fetch("/api/dataviz/convert_table", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({filename: file.name, data_base64: btoa(binary)})});
  const data = await _dvzJson(resp);
  if (!resp.ok) throw new Error(data.error || "ההמרה נכשלה");
  return data.csv_text;
}

function _dvzSetupDrop() {
  const panel = document.querySelector('[data-tab-panel="dataviz"]');
  if (!panel || panel.dataset.dvzDrop) return;
  panel.dataset.dvzDrop = "1";
  panel.addEventListener("dragover", (e) => { if (e.dataTransfer && [...e.dataTransfer.types].includes("Files")) { e.preventDefault(); panel.classList.add("dvz-drop-active"); } });
  panel.addEventListener("dragleave", (e) => { if (e.target === panel) panel.classList.remove("dvz-drop-active"); });
  panel.addEventListener("drop", (e) => {
    const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    panel.classList.remove("dvz-drop-active");
    if (!file) return;
    e.preventDefault();   // 23.10.2026: גם לקובץ לא נתמך - אחרת הדפדפן פותח אותו במקום האפליקציה (והטיוטה אובדת)
    if (!/\.(csv|tsv|txt|xlsx|xls|xlsm|json)$/i.test(file.name)) {
      uiToast("סוג קובץ לא נתמך - CSV, Excel או JSON", "warn");
      return;
    }
    dvzOpenNew("files");   // גל 59: הטופס בחלון (21.10.2026: הדרך "מקבצים")
    dvzTableFile(file);
  });
}

// --- מוזיקה על גרף גלי הקול (לשונית בעורך המלא) ---
function _dvzMusicTab() {
  const box = _dvzEdEl("div", "dvz-music");
  box.append(_dvzEdEl("p", "hint", "⏳"));
  (async () => {
    try {
      const info = await _dvzFetchPart("music");
      box.replaceChildren(..._dvzMusicNodes(info));
    } catch (e) {
      box.replaceChildren(_dvzEdEl("p", "bad", "שגיאה: " + e.message));
    }
  })();
  return box;
}

function _dvzMusicNodes(info) {
  const nodes = [];
  const current = "audio.path" in dvzEd.draft ? dvzEd.draft["audio.path"] : info.current;
  const start = "audio.start" in dvzEd.draft ? dvzEd.draft["audio.start"] : info.start;
  const select = _dvzEdEl("select");
  select.id = "dvzMusicFile";
  select.setAttribute("aria-label", "קובץ המוזיקה");
  select.appendChild(new Option("בלי מוזיקה", ""));
  for (const name of info.files) select.appendChild(new Option(name, name));
  select.value = current;
  select.onchange = () => { _dvzStage("audio.path", select.value); _dvzRenderEditor(); };
  nodes.push(select);
  if (!info.files.length) nodes.push(_dvzEdEl("p", "hint", "אין קובצי מוזיקה בתיקיית הפרק (mp3, wav, m4a...)."));
  if (!current) return nodes;
  const wave = _dvzEdEl("div", "dvz-wave");
  wave.setAttribute("aria-label", "גרף גלי הקול - לחיצה בוחרת מאיפה המוזיקה מתחילה");
  const note = _dvzEdEl("p", "hint", "");
  nodes.push(wave, note);
  (async () => {
    try {
      const resp = await fetch("/api/dataviz/episodes/waveform?" + new URLSearchParams({episode: dvzState.selected, file: current}));
      const data = await _dvzJson(resp);
      if (!resp.ok) throw new Error(data.error || "הטעינה נכשלה");
      const draw = (from) => {
        const width = 640, height = 70;
        const svg = _dvzSvg("svg", {viewBox: `0 0 ${width} ${height}`, class: "dvz-chart dvz-wave-svg"});
        const step = width / Math.max(1, data.peaks.length);
        data.peaks.forEach((p, i) => svg.append(_dvzSvg("rect", {class: "dvz-wave-bar", x: (i * step).toFixed(1), y: ((1 - p) * height / 2).toFixed(1), width: Math.max(1, step - 0.5).toFixed(1), height: Math.max(1, p * height).toFixed(1)})));
        const toX = (t) => data.duration ? t / data.duration * width : 0;
        svg.append(_dvzSvg("rect", {class: "dvz-wave-window", x: toX(from).toFixed(1), y: 0, width: Math.max(2, toX(Math.min(data.duration, from + info.video_seconds)) - toX(from)).toFixed(1), height}));
        svg.addEventListener("click", (e) => {
          const rect = svg.getBoundingClientRect();
          const t = Math.max(0, Math.min(data.duration, (e.clientX - rect.left) / rect.width * data.duration));
          const rounded = Math.round(t * 10) / 10;
          _dvzStage("audio.start", rounded);
          draw(rounded);
        });
        wave.replaceChildren(svg);
        note.textContent = [`המוזיקה מתחילה ב-${_dvzDuration(from)}`, `אורך הסרטון: ${_dvzDuration(info.video_seconds)}`, `אורך הקובץ: ${_dvzDuration(data.duration)}`,
          from + info.video_seconds > data.duration ? "⚠️ המוזיקה נגמרת לפני הסרטון" : ""].filter(Boolean).join(" · ");
      };
      draw(start);
    } catch (e) {
      note.textContent = "שגיאה: " + e.message;
    }
  })();
  return nodes;
}

// נקרא מ-dvzSelectionChanged (43-dataviz-studio.js)
function _dvzDataSelectionChanged() {
  dvzData.cache = {};
  dvzData.update = null;
  dvzData.source = 0;
  _dvzCheckBadge();
  if (document.getElementById("dvzData").open) dvzLoadData();
}

_dvzSetupDrop();

// ============================================================================
// גל 52: עוד שתי לשוניות בחלון הנתונים של עורך הגרפים -
//   🧹 ניקוי: הצעות מיזוג לשמות דומים של אותה ישות, קפיצות חשודות (עם פיזור / החלקה בלחיצה), התיקונים שנשמרו
//      והגדרת הימים החסרים. כל לחיצה נשמרת בקובץ השינויים של הפרק - קבצי הנתונים לא משתנים.
//   🌐 מכתובת ותזמון: מקור נתונים מכתובת או Google Sheets (מורד רק בלחיצה), "רענן נתונים" עם מה השתנה,
//      ומשימה מתוזמנת לפרק (רינדור בלילה, ואם רוצים - רענון קודם ודילוג כשאין חדש).
// ============================================================================

async function _dvzPostOverride(set, unset) {
  const resp = await fetch("/api/dataviz/episodes/override", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({episode: dvzState.selected, set: set || {}, unset: unset || []})});
  const data = await _dvzJson(resp);
  if (!resp.ok) throw new Error(data.error || "השמירה נכשלה");
  await _dvzDataChanged();
  return data;
}

// אחרי שינוי בנתונים: הלשוניות, האומדן, העורך והתצוגה החיה נטענים מחדש
async function _dvzDataChanged() {
  dvzData.cache = {};
  delete dvzState.estimates[dvzState.selected];
  if (document.getElementById("dvzEditor").open) await dvzLoadEditor();
  dvzPreviewSoon();
  await _dvzRenderDataTab();
}

function _dvzDataNote(text, bad) {
  const status = document.getElementById("dvzDataStatus");
  status.textContent = text;
  status.classList.toggle("bad", !!bad);
}

async function _dvzDataAction(action, done) {
  try {
    await action();
    if (done) _dvzDataNote(done);
  } catch (e) {
    _dvzDataNote("שגיאה: " + e.message, true);
  }
}

// --- 🧹 ניקוי ---
async function _dvzCleanView() {
  const report = await _dvzFetchPart("clean");
  const box = _dvzEdEl("div", "dvz-clean");
  // שמות דומים
  box.append(_dvzEdEl("h4", "", "🔤 שמות דומים"));
  if (!report.similar.length) box.append(_dvzEdEl("p", "hint", "לא נמצאו שמות שנראים כמו אותה ישות בכתיב אחר."));
  for (const group of report.similar) {
    const row = _dvzEdEl("div", "dvz-clean-row");
    row.dataset.names = group.names.join("|");
    row.append(_dvzEdEl("span", "dvz-chip", group.reason === "same" ? "זהים" : "דומים"));
    for (const name of group.names) row.append(_dvzEdEl("span", "dvz-clean-name", `${name} (${Math.round(group.totals[name]).toLocaleString("he-IL")})`));
    const target = _dvzEdEl("select");
    target.setAttribute("aria-label", "השם שנשאר");
    for (const name of group.names) target.appendChild(new Option(name, name));
    const merge = _dvzEdEl("button", "btn-sm", "🔗 מזג");
    merge.type = "button";
    merge.onclick = () => _dvzDataAction(async () => {
      const aliases = {...report.aliases};
      for (const name of group.names) if (name !== target.value) aliases[name] = target.value;
      await _dvzPostOverride({"entities.aliases": aliases});
    }, `✅ מוזגו ל-${target.value}`);
    row.append(_dvzEdEl("span", "hint", "← נשאר:"), target, merge);
    box.append(row);
  }
  // קפיצות חשודות
  box.append(_dvzEdEl("h4", "", "📈 קפיצות חשודות"));
  const fixed = new Set(report.fixes.map(f => `${f.entity}|${f.date}`));
  const open = report.outliers.filter(o => !fixed.has(`${o.entity}|${o.date}`));
  if (!open.length) box.append(_dvzEdEl("p", "hint", "אין יום שבו ישות קפצה הרבה מעל הרגיל שלה."));
  else {
    const table = _dvzEdEl("table", "dvz-data-table dvz-outliers");
    const head = table.createTHead().insertRow();
    for (const title of ["ישות", "תאריך", "ביום הזה", "רגיל", "פי", ""]) head.appendChild(_dvzEdEl("th", "", title));
    const body = table.createTBody();
    for (const item of open) {
      const tr = body.insertRow();
      for (const cell of [item.entity, item.date, Math.round(item.value).toLocaleString("he-IL"), Math.round(item.typical).toLocaleString("he-IL"), item.ratio.toFixed(1)]) tr.insertCell().textContent = cell;
      const actions = tr.insertCell();
      for (const [action, label, title] of [["spread", "פזר", "מה שמעל הרגיל מתפזר על 30 הימים שלפני - הסכום נשמר (דיווח מצטבר שנזרק ליום אחד)"],
                                             ["smooth", "החלק", "היום מקבל את הערך הרגיל - הסכום קטן"]]) {
        const btn = _dvzEdEl("button", "btn-xs", label);
        btn.type = "button";
        btn.title = title;
        btn.dataset.action = action;
        btn.onclick = () => _dvzDataAction(() => _dvzPostOverride({"data.fixes": [...report.fixes, {entity: item.entity, date: item.date, action, days: 30}]}),
          `✅ ${item.entity} ${item.date} תוקן`);
        actions.append(btn);
      }
    }
    box.append(table);
  }
  // תיקונים שנשמרו
  if (report.fixes.length) {
    box.append(_dvzEdEl("h4", "", "✅ תיקונים שנשמרו"));
    const list = _dvzEdEl("ul", "dvz-fixes");
    report.fixes.forEach((fix, i) => {
      const li = _dvzEdEl("li", "", `${fix.entity} · ${fix.date} · ${{spread: "פוזר", smooth: "הוחלק", set: "נקבע ערך"}[fix.action] || fix.action} `);
      const undo = _dvzEdEl("button", "btn-xs", "↺");
      undo.type = "button";
      undo.title = "בטל את התיקון";
      undo.setAttribute("aria-label", undo.title);
      undo.onclick = () => _dvzDataAction(() => _dvzPostOverride({"data.fixes": report.fixes.filter((_f, k) => k !== i)}), "✅ התיקון בוטל");
      li.append(undo);
      list.append(li);
    });
    box.append(list);
  }
  // ימים חסרים
  const missing = _dvzEdEl("label", "dvz-missing", "📅 יום חסר במקור יומי: ");
  const select = _dvzEdEl("select");
  select.id = "dvzMissingSelect";
  for (const [value, label] of [["zero", "אפס (כמו שהוא)"], ["previous", "הערך של היום הקודם"], ["interpolate", "קו ישר בין הימים שסביבו"]]) select.appendChild(new Option(label, value));
  select.value = report.missing;
  select.onchange = () => _dvzDataAction(() => _dvzPostOverride({"data.missing": select.value}), "✅ נשמר");
  missing.append(select);
  box.append(_dvzEdEl("h4", "", "🧩 ימים חסרים"), missing,
    _dvzEdEl("p", "hint", "רק לנתונים שבהם כל שורה היא הערך של יום (קריאה, מדידה) - בנתונים של מופעים יום בלי שורות הוא באמת אפס."));
  return box;
}

// --- 🌐 מכתובת ותזמון ---
async function _dvzRemoteView() {
  const resp = await fetch("/api/dataviz/episodes/remote?episode=" + encodeURIComponent(dvzState.selected));
  const remote = await _dvzJson(resp);
  if (!resp.ok) throw new Error(remote.error || "הטעינה נכשלה");
  const box = _dvzEdEl("div", "dvz-remote");
  box.append(_dvzEdEl("h4", "", "🌐 מקורות מכתובת"));
  if (!remote.sources.length) box.append(_dvzEdEl("p", "hint", "לפרק אין מקור מכתובת. אפשר להוסיף קובץ CSV / JSON / Excel מהרשת או גיליון Google Sheets משותף."));
  for (const source of remote.sources) {
    const row = _dvzEdEl("div", "dvz-remote-row");
    row.append(_dvzEdEl("code", "", source.url), _dvzEdEl("span", "hint", source.at
      ? `הורד ${source.at.replace("T", " ")} · השתנה לאחרונה ${(source.changed_at || source.at).replace("T", " ")}` : "עוד לא הורד"));
    box.append(row);
  }
  if (remote.sources.length) {
    const refresh = _dvzEdEl("button", "btn-sm", "🔄 רענן נתונים");
    refresh.type = "button";
    refresh.id = "dvzRefreshBtn";
    refresh.onclick = () => _dvzDataAction(async () => {
      refresh.disabled = true;
      const r = await fetch("/api/dataviz/episodes/refresh", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({episode: dvzState.selected})});
      const data = await _dvzJson(r);
      refresh.disabled = false;
      if (!r.ok) throw new Error(data.error || "הרענון נכשל");
      const failed = data.sources.filter(s => s.error);
      if (failed.length) throw new Error(failed[0].error);
      await _dvzDataChanged();
      _dvzDataNote(data.changed ? "✅ הנתונים השתנו - התצוגה מתעדכנת" : "✅ הנתונים לא השתנו מאז ההורדה הקודמת");
    });
    box.append(refresh);
  }
  // הוספת מקור
  const form = _dvzEdEl("details", "dvz-remote-add");
  form.append(_dvzEdEl("summary", "", "➕ מקור חדש מכתובת"));
  const fields = {};
  for (const [key, label, placeholder] of [["url", "כתובת", "https://docs.google.com/spreadsheets/d/..."], ["time_column", "עמודת התאריך", "date"],
    ["value_column", "עמודת הערך (ריק = ספירת שורות)", "value"], ["entity_column", "עמודת הקיבוץ (ריק = לפי שנה)", "city"], ["legend", "שם במקרא (לא חובה)", ""]]) {
    const wrap = _dvzEdEl("label", "dvz-field-label", label + " ");
    const input = _dvzEdEl("input");
    input.type = key === "url" ? "url" : "text";
    if (key !== "legend") input.dir = "ltr";   // נ15: כתובת ושמות עמודות - משמאל לימין
    input.placeholder = placeholder;
    input.dataset.field = key;
    fields[key] = input;
    wrap.append(input);
    form.append(wrap);
  }
  const period = _dvzEdEl("select");
  for (const [value, label] of [["day", "יום"], ["month", "חודש"], ["year", "שנה"]]) period.appendChild(new Option(label, value));
  const periodLabel = _dvzEdEl("label", "dvz-field-label", "כל שורה היא: ");
  periodLabel.append(period);
  const add = _dvzEdEl("button", "btn-sm", "⬇️ הורד והוסף");
  add.type = "button";
  add.onclick = () => _dvzDataAction(async () => {
    const payload = {episode: dvzState.selected, period: period.value};
    for (const [key, input] of Object.entries(fields)) payload[key] = input.value.trim();
    const r = await fetch("/api/dataviz/episodes/url_source", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    const data = await _dvzJson(r);
    if (!r.ok) throw new Error(data.error || "ההוספה נכשלה");
    await _dvzDataChanged();
  }, "✅ המקור נוסף לפרק");
  form.append(periodLabel, add, _dvzEdEl("p", "hint", "הקובץ מורד עכשיו ושוב רק כשלוחצים \"רענן נתונים\" או במשימה מתוזמנת. גיליון Google Sheets צריך שיתוף \"כל מי שיש לו את הקישור\"."));
  box.append(form);
  box.append(_dvzScheduleBox(remote.schedules || [], remote.sources.length > 0));
  return box;
}

function _dvzScheduleBox(schedules, hasRemote) {
  const box = _dvzEdEl("div", "dvz-schedule");
  box.append(_dvzEdEl("h4", "", "⏰ תזמון"));
  for (const task of schedules) {
    const when = task.schedule_type === "interval_hours" ? `כל ${task.interval_hours} שעות` : task.schedule_type === "weekly" ? `כל שבוע (${task.weekday}) ב-${task.time}` : `כל יום ב-${task.time}`;
    const args = task.extra_args || [];
    box.append(_dvzEdEl("p", "dvz-schedule-task", `${task.enabled ? "🟢" : "⏸"} ${when} · ${args[args.indexOf("--mode") + 1] || ""}${args.includes("--refresh-data") ? " · רענון קודם" : ""}${args.includes("--only-if-changed") ? " · רק כשהשתנה" : ""}`));
  }
  const row = _dvzEdEl("div", "tc-row dvz-schedule-form");
  const mode = _dvzEdEl("select");
  mode.setAttribute("aria-label", "מה להפיק");
  for (const [value, label] of [["full", "סרטון מלא"], ["test", "בדיקה"], ["share", "תמונה ו-GIF"]]) mode.appendChild(new Option(label, value));
  const type = _dvzEdEl("select");
  type.setAttribute("aria-label", "תדירות");
  for (const [value, label] of [["daily", "כל יום"], ["weekly", "כל שבוע"], ["interval_hours", "כל כמה שעות"]]) type.appendChild(new Option(label, value));
  const time = _dvzEdEl("input");
  time.type = "time";
  time.value = "03:00";
  time.setAttribute("aria-label", "שעה");
  const hours = _dvzEdEl("input");
  hours.type = "number";
  hours.min = "1";
  hours.value = "24";
  hours.setAttribute("aria-label", "כל כמה שעות");
  const refresh = _dvzEdEl("input");
  refresh.type = "checkbox";
  refresh.checked = hasRemote;
  const refreshLabel = _dvzEdEl("label", "", " רענן נתונים קודם");
  refreshLabel.prepend(refresh);
  const changed = _dvzEdEl("input");
  changed.type = "checkbox";
  changed.checked = hasRemote;
  const changedLabel = _dvzEdEl("label", "", " רק כשהנתונים השתנו");
  changedLabel.prepend(changed);
  const save = _dvzEdEl("button", "btn-sm", "⏰ תזמן");
  save.type = "button";
  save.onclick = () => _dvzDataAction(async () => {
    const r = await fetch("/api/dataviz/schedule", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
      episode: dvzState.selected, mode: mode.value, schedule_type: type.value, time_str: time.value || "03:00",
      interval_hours: parseInt(hours.value, 10) || 24, refresh: refresh.checked, only_if_changed: refresh.checked && changed.checked})});
    const data = await _dvzJson(r);
    if (!r.ok) throw new Error(data.error || "התזמון נכשל");
    _dvzRenderDataTab();
  }, "✅ המשימה נוספה למתזמן");
  row.append(mode, type, time, hours, refreshLabel, changedLabel, save);
  box.append(row, _dvzEdEl("p", "hint", "המשימה רצה כשהאפליקציה פתוחה. עריכה, השהיה ומחיקה - במסך המתזמן."));
  return box;
}

// 18.10.2026: קובץ משקלות (spread.weights) - כאן ב-dataviz_pro (19.10.2026: כל הנתונים כאן), כדי שה-bundle הראשון
// של המסך יישאר עם 15K פנויים (test_dataviz_dogfood). נקרא מחלון הנתונים, שנפתח אחרי ששני ה-bundles נטענו.
// 18.10.2026: הסרת קובץ משקלות שנוסף מהדפדפן - רק מה-override (חזרה למשקלות של config.yaml); הקובץ נשאר בדיסק
function _dvzRemoveWeightsButton(src) {
  const button = _dvzEdEl("button", "btn-sm dvz-remove-weights", "🗑️ הסר משקלות");
  button.type = "button";
  button.title = "הסר את קובץ המשקלות מהמקור - הקובץ נשאר בדיסק";
  button.onclick = async () => {
    if (!await veConfirm(`להסיר את קובץ המשקלות "${src.weights}" מהמקור? הקובץ עצמו נשאר בדיסק.`, {danger: true, okLabel: "🗑️ הסר"})) return;
    await _dvzDataAction(async () => {
      const resp = await fetch("/api/dataviz/episodes/remove_weights", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({episode: dvzState.selected, source: src.index})});
      const data = await _dvzJson(resp);
      if (!resp.ok) throw new Error(data.error || "ההסרה נכשלה");
      await _dvzDataChanged();
    }, "✅ קובץ המשקלות הוסר מהמקור.");
  };
  return button;
}

// 18.10.2026: קובץ משקלות (spread.weights) למקור של חודש/שנה - קובע את צורת הפיזור על הימים; הסכום לא משתנה
function _dvzWeightsBox(sources) {
  const box = _dvzEdEl("div", "dvz-update");
  box.append(_dvzEdEl("h4", "", "⚖️ קובץ משקלות"),
    _dvzEdEl("p", "hint", "קובץ משקלות קובע איך הסכום של שנה או חודש מתפזר על הימים (למשל סכומים חודשיים) - הסכום עצמו לא משתנה. עמודות window_start ו-window_end (לא חובה) הן חלון ימים מפורש. נשמר כקובץ חדש; קובצי הפרק לא משתנים."));
  const periodic = sources.filter(src => src.time.period !== "day");
  if (!periodic.length) { box.append(_dvzEdEl("p", "empty-msg", "אין בפרק מקור של חודש או שנה - אין מה לפזר.")); return box; }
  const select = _dvzEdEl("select");
  select.id = "dvzWeightsSource";
  select.setAttribute("aria-label", "המקור למשקלות");
  periodic.forEach(src => select.appendChild(new Option(`${src.index + 1}. ${src.path}`, String(src.index))));
  const file = _dvzEdEl("input");
  file.type = "file";
  file.id = "dvzWeightsFile";
  file.accept = ".csv,.tsv,.xlsx,.xls,.json";
  file.setAttribute("aria-label", "קובץ המשקלות");
  const mapping = _dvzEdEl("div");
  const result = _dvzEdEl("div", "dvz-update-result");
  file.onchange = async () => {
    const chosen = file.files && file.files[0];
    if (!chosen) return;
    try {
      const csv = await _dvzFileAsCsv(chosen);
      const resp = await fetch("/api/dataviz/episodes/csv_columns", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({csv_text: csv})});
      const data = await _dvzJson(resp);
      if (!resp.ok) throw new Error(data.error || "קריאת ה-CSV נכשלה");
      const fields = _dvzEdEl("div", "tc-row dvz-weights-mapping");
      const cols = data.columns.map(c => [c, c]);
      for (const [key, label, options, preferred] of [["period_column", "עמודת השנה:", cols, "year"],
        ["month_column", "עמודת החודש:", [["", "בלי - רק חלונות ימים"], ...cols], "month"], ["value", "משקל:", cols, "total"]]) {
        const wrap = _dvzEdEl("label", "dvz-field-label", label + " ");
        const field = _dvzEdEl("select");
        field.dataset.field = key;
        for (const [v, text] of options) field.appendChild(new Option(text, v));
        field.value = options.some(([v]) => v === preferred) ? preferred : options[0][0];
        wrap.append(field);
        fields.append(wrap);
      }
      const apply = _dvzEdEl("button", "btn-primary", "⚖️ הוסף את קובץ המשקלות");
      apply.type = "button";
      apply.id = "dvzWeightsApply";
      apply.onclick = async () => {
        apply.disabled = true;
        const source = parseInt(select.value, 10);
        try {
          const r = await fetch("/api/dataviz/episodes/set_weights", {method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({..._dvzMappingValues(fields), episode: dvzState.selected, source, filename: chosen.name, csv_text: csv})});
          const answer = await _dvzJson(r);
          if (!r.ok) throw new Error(answer.error || "ההוספה נכשלה");
          result.replaceChildren(_dvzEdEl("p", "", `✅ קובץ המשקלות נוסף למקור ${source + 1} (${answer.file}) - ${answer.matched} מתוך ${answer.periods} השנים שלו. קובצי הפרק לא השתנו.`));
          dvzData.cache = {};
          delete dvzState.estimates[dvzState.selected];
          dvzLoadPreview();
        } catch (e) {
          apply.disabled = false;
          result.replaceChildren(_dvzEdEl("p", "bad", "שגיאה: " + e.message));
        }
      };
      mapping.replaceChildren(fields, apply);
      result.replaceChildren();
    } catch (e) {
      result.replaceChildren(_dvzEdEl("p", "bad", "שגיאה: " + e.message));
    }
  };
  box.append(select, file, mapping, result);
  return box;
}

// --- 20.10.2026: קטלוג מקורות נתונים (למ"ס, הבנק העולמי, OECD) - רשימה וחיפוש בלי הורדה; "⬇️ הורד" = ההסכמה להורדה ---
let _dvzCatalog = {items: [], picked: null};

async function dvzOpenCatalog() {
  const dialog = document.getElementById("dvzCatalogDialog");
  document.getElementById("dvzCatalogMsg").textContent = "";
  if (!dialog.open) dialog.showModal();
  await dvzCatalogSearch();
}

async function dvzCatalogSearch() {
  const q = document.getElementById("dvzCatalogSearch").value.trim();
  const latest = uiLatest("dvz:catalog");   // נ15: תשובה של חיפוש קודם שחזרה מאוחר לא דורסת את התוצאות של האחרון
  let items;
  try {
    items = (await _dvzJson(await fetch("/api/dataviz/catalog?" + new URLSearchParams({q, lang: _uiLang}), {signal: latest.signal}))).items || [];
  } catch (e) {
    if (uiIsAbort(e)) return;
    throw e;
  }
  if (!latest.current()) return;
  _dvzCatalog.items = items;
  document.getElementById("dvzCatalogList").replaceChildren(..._dvzCatalog.items.map(item => {
    const row = _dvzEdEl("button", "dvz-catalog-item" + (_dvzCatalog.picked && _dvzCatalog.picked.id === item.id ? " active" : ""));
    row.type = "button";
    row.setAttribute("role", "listitem");
    row.dataset.catalogId = item.id;
    row.append(_dvzEdEl("span", "dvz-chip", item.provider_name), _dvzEdEl("strong", "", item.title), _dvzEdEl("span", "hint", item.units));
    row.onclick = () => _dvzCatalogPick(item);
    return row;
  }));
}

function _dvzCatalogPick(item) {
  _dvzCatalog.picked = item;
  for (const row of document.querySelectorAll("#dvzCatalogList .dvz-catalog-item")) row.classList.toggle("active", row.dataset.catalogId === item.id);
  const meta = document.getElementById("dvzCatalogMeta");
  const lines = [["מקור", item.provider_name], ["טבלה / מדד", item.table], ["יחידות", item.units],
    ["תקופה", item.period === "year" ? "שנה" : "חודש"], ["סוג הערכים", item.kind === "level" ? "רמה" : "כמות"], ["רישיון", item.license], ["כתובת", item.url]];
  meta.replaceChildren(_dvzEdEl("h4", "", item.title), ...lines.map(([k, v]) => {
    const row = _dvzEdEl("div", "dvz-catalog-row");
    row.append(_dvzEdEl("span", "hint", k + ":"), _dvzEdEl("span", k === "כתובת" ? "dvz-catalog-url" : "", v));
    return row;
  }));
  document.getElementById("dvzCatalogName").value = item.id;
  document.getElementById("dvzCatalogSourceBtn").disabled = !dvzState.selected;
  document.getElementById("dvzCatalogDetail").hidden = false;
}

async function dvzCatalogFetch(target) {
  const item = _dvzCatalog.picked;
  const msg = document.getElementById("dvzCatalogMsg");
  if (!item) return;
  const body = target === "source" ? {id: item.id, target, episode: dvzState.selected} : {id: item.id, target, name: document.getElementById("dvzCatalogName").value.trim()};
  msg.textContent = "⏳ מוריד...";
  const buttons = ["dvzCatalogNewBtn", "dvzCatalogSourceBtn"].map(id => document.getElementById(id)).filter(Boolean);
  const was = buttons.map(button => button.disabled);
  for (const button of buttons) button.disabled = true;   // 23.10.2026: לחיצה כפולה הוסיפה את הסדרה פעמיים
  try {
    const resp = await fetch("/api/dataviz/catalog/fetch", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...body, lang: _uiLang})});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "ההורדה נכשלה");
    if (target === "new") dvzState.selected = data.name;
    dvzData.cache = {};
    await loadDataviz();
    document.getElementById("dvzCatalogDialog").close();
    uiToast("📚 " + item.title + " - " + data.rows + " " + "שורות" + " (" + data.range.join(" - ") + ")", "ok");
  } catch (e) {
    msg.textContent = "שגיאה: " + e.message;
  } finally {
    buttons.forEach((button, i) => { button.disabled = was[i]; });
  }
}

// --- 20.10.2026: עריכת נתונים בטבלה - תא, מחיקת שורה, שורה חדשה, הדבקה מ-Excel. "בדוק" משווה סכומים (update_data בלי confirm),
// ו"שמור" יוצר קובץ חדש תחת data/dataviz_overrides/<פרק>/ - הקובץ המקורי לא נכתב ---
function _dvzEditGridButton(src, card) {
  const button = _dvzEdEl("button", "btn-sm dvz-edit-grid", "✏️ נתונים");
  button.type = "button";
  button.title = "לערוך את השורות של המקור בטבלה - נשמר כקובץ חדש, המקורי לא משתנה";
  button.onclick = () => {
    const open = card.querySelector(".dvz-grid-edit");
    if (open) { open.remove(); return; }
    _dvzOpenGrid(src, card);
  };
  return button;
}

function _dvzCsvCell(value) {
  const text = String(value ?? "");
  return /[",\n\r]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
}

function _dvzGridCsv(table) {
  const columns = [...table.tHead.rows[0].cells].slice(0, -1).map(th => th.textContent);
  const rows = [...table.tBodies[0].rows].map(tr => [...tr.cells].slice(0, -1).map(td => td.textContent.trim()));
  return [columns, ...rows].map(row => row.map(_dvzCsvCell).join(",")).join("\n") + "\n";
}

function _dvzGridRow(table, values, editable) {
  const tr = table.tBodies[0].insertRow();
  const count = table.tHead.rows[0].cells.length - 1;
  for (let i = 0; i < count; i++) {
    const td = tr.insertCell();
    td.textContent = values[i] ?? "";
    td.contentEditable = editable ? "true" : "false";
  }
  const remove = _dvzEdEl("button", "btn-xs", "🗑");
  remove.type = "button";
  remove.title = "מחק את השורה";
  remove.setAttribute("aria-label", remove.title);
  remove.disabled = !editable;
  remove.onclick = () => { tr.remove(); table.dispatchEvent(new Event("input")); };
  tr.insertCell().append(remove);
  return tr;
}

async function _dvzOpenGrid(src, card) {
  const box = _dvzEdEl("div", "dvz-grid-edit");
  card.querySelector(".dvz-source-head").after(box);
  box.append(_dvzEdEl("p", "hint", "⏳"));
  const resp = await fetch("/api/dataviz/episodes/data?" + new URLSearchParams({episode: dvzState.selected, part: "table", source: String(src.index)}));
  const data = (await _dvzJson(resp)).data;
  if (!resp.ok || !data) { box.replaceChildren(_dvzEdEl("p", "hint", "הטבלה לא נטענה.")); return; }
  const table = _dvzEdEl("table", "dvz-grid");
  const head = table.createTHead().insertRow();
  for (const column of [...data.columns, ""]) head.appendChild(_dvzEdEl("th", "", column));
  table.createTBody();
  for (const row of data.rows) _dvzGridRow(table, row, data.editable);
  const status = _dvzEdEl("span", "hint dvz-grid-status", data.editable ? `${data.total} שורות` : `${data.total} שורות - גדול מדי לעריכה כאן; "🔄 עדכון נתונים" מקובץ`);
  const add = _dvzEdEl("button", "btn-sm", "➕ שורה");
  add.type = "button";
  add.disabled = !data.editable;
  add.onclick = () => { _dvzGridRow(table, [], true).cells[0].focus(); table.dispatchEvent(new Event("input")); };
  const check = _dvzEdEl("button", "btn-sm", "🔍 בדוק שינויים");
  check.type = "button";
  check.disabled = !data.editable;
  const save = _dvzEdEl("button", "btn-sm btn-primary", "💾 שמור כקובץ חדש");
  save.type = "button";
  save.disabled = true;
  const post = async (confirm) => {
    const r = await fetch("/api/dataviz/episodes/update_data", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({episode: dvzState.selected, source: src.index, csv_text: _dvzGridCsv(table), confirm})});
    const result = await _dvzJson(r);
    if (!r.ok) throw new Error(result.error || "הבדיקה נכשלה");
    return result;
  };
  table.addEventListener("input", () => { save.disabled = true; });
  check.onclick = async () => {
    try {
      const result = await post(false);
      const fmt = (n) => Math.round(n).toLocaleString("he-IL");
      const changes = [`${fmt(result.total_before)} ← ${fmt(result.total_after)}`];
      if (result.new.length) changes.push("חדשים: " + result.new.join(", "));
      if (result.gone.length) changes.push("נעלמו: " + result.gone.join(", "));
      status.textContent = changes.join(" · ");
      save.disabled = false;
    } catch (e) {
      status.textContent = "שגיאה: " + e.message;
    }
  };
  save.onclick = () => _dvzDataAction(async () => {
    await post(true);
    await _dvzDataChanged();
  }, "✅ נשמר כקובץ חדש - הקובץ המקורי לא השתנה.");
  // הדבקה מ-Excel / גיליון: שורות מופרדות בירידת שורה, תאים בטאב - מהתא שבפוקוס והלאה (שורות חדשות כשצריך)
  table.addEventListener("paste", (e) => {
    const text = (e.clipboardData || window.clipboardData).getData("text");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const cell = document.activeElement && document.activeElement.closest ? document.activeElement.closest("td") : null;
    const body = table.tBodies[0];
    let r = cell ? cell.parentElement.sectionRowIndex : body.rows.length;
    const c0 = cell ? cell.cellIndex : 0;
    for (const line of text.replace(/\r/g, "").split("\n").filter(l => l.length)) {
      const tr = body.rows[r] || _dvzGridRow(table, [], true);
      line.split("\t").forEach((value, k) => { if (tr.cells[c0 + k] && c0 + k < tr.cells.length - 1) tr.cells[c0 + k].textContent = value; });
      r++;
    }
    table.dispatchEvent(new Event("input"));
  });
  const scroll = _dvzEdEl("div", "dvz-table-scroll");
  scroll.append(table);
  const bar = _dvzEdEl("div", "tc-row");
  bar.append(add, check, save, status);
  box.replaceChildren(_dvzEdEl("p", "hint", "תא - לחיצה ועריכה; הדבקה מ-Excel מהתא שבפוקוס. קודם \"בדוק\" (השוואת סכומים), ואז \"שמור\" - קובץ חדש, המקורי לא משתנה."), scroll, bar);
}

// --- 20.10.2026: בדיקת עובדות לפני רינדור - המספרים שיופיעו על המסך ליד שורות המקור; ❌ = לא מתאים, ➖ = שינוי מכוון ---
function _dvzFactsTable(title, rows, withText) {
  const box = _dvzEdEl("div", "dvz-facts");
  box.append(_dvzEdEl("h4", "", title));
  if (!rows.length) { box.append(_dvzEdEl("p", "hint", "אין.")); return box; }
  const table = _dvzEdEl("table", "dvz-changes-table dvz-facts-table");
  const head = table.createTHead().insertRow();
  for (const label of ["", "תאריך", "ישות", "על המסך", "מהקבצים", "שורות המקור", ...(withText ? ["התראה"] : [])]) head.appendChild(_dvzEdEl("th", "", label));
  const body = table.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    tr.dataset.ok = String(row.ok);
    tr.insertCell().textContent = row.ok === true ? "✅" : row.ok === false ? "❌" : "➖";
    tr.insertCell().textContent = row.date;
    tr.insertCell().textContent = row.entity;
    tr.insertCell().textContent = row.shown;
    tr.insertCell().textContent = row.expected;
    tr.insertCell().textContent = row.source_rows.map(r => `${r.time}: ${r.value} (${r.source})`).join(" · ");
    if (withText) tr.insertCell().textContent = row.text || "";
  }
  const scroll = _dvzEdEl("div", "dvz-table-scroll");
  scroll.append(table);
  box.append(scroll);
  return box;
}

async function _dvzFactsView() {
  const facts = await _dvzFetchPart("facts");
  const box = _dvzEdEl("div", "dvz-facts-view");
  const summary = _dvzEdEl("p", facts.mismatches ? "dvz-finding is-warn" : "dvz-finding is-info",
    facts.mismatches ? `❌ ${facts.mismatches} מספרים לא מתאימים לקבצים (מתוך ${facts.checked})` : `✅ כל ${facts.checked} המספרים שנבדקו מתאימים לקבצים`);
  box.append(summary, _dvzEdEl("p", "hint", "לקריאה בלבד. \"על המסך\" - הערך בסרטון באותו יום, בפורמט של הסרטון; \"מהקבצים\" - סכום הערכים עד סוף התקופה (כמות) או הערך האחרון (רמה)."));
  if (facts.transforms.length) {
    const list = _dvzEdEl("ul", "hint");
    for (const t of facts.transforms) list.append(_dvzEdEl("li", "", `➖ ${t.entity === "*" ? "כל הישויות" : t.entity}: ${t.reason}`));
    box.append(_dvzEdEl("h4", "", "שינויים מכוונים (לא נבדקים)"), list);
  }
  const mismatches = facts.key_frames.filter(r => r.ok === false);
  box.append(_dvzFactsTable("תיבת הסיום", facts.end_box), _dvzFactsTable("התראות שיא", facts.records, true),
    _dvzFactsTable(mismatches.length ? "נקודות מפתח - רק מה שלא מתאים" : "נקודות מפתח (סוף כל שנה)", mismatches.length ? mismatches : facts.key_frames));
  return box;
}
