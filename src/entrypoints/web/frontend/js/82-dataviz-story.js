// ============================================================================
// גל 50: לשונית "📖 סיפור" בעורך המלא של עורך הגרפים - פרקים בתוך הסרטון (כרטיס כותרת על פריים קפוא),
// עצירות עם הסבר, הערה לישות בתאריך, תקופות מוצללות וקטעי מהירות. כל רשימה נשמרת כמו כל שדה בעורך
// (טיוטה שמוצגת מיד בתצוגה החיה, "שמור" כותב לקובץ השינויים - config.yaml לא משתנה).
// הקובץ ב-bundle השני של המסך (dataviz_pro), שנטען מיד אחרי הראשון.
// ============================================================================

// [מפתח, סוג, כותרת העמודה] - סוגים: date, text, number, int, entity (בחירה מהישויות), color, style (סגנון הערה)
const DVZ_ANNOTATION_STYLES = [["default", "רגיל"], ["accent", "הדגשה"], ["muted", "עמום"]];
const DVZ_STORY_LISTS = [
  {key: "chapters", title: "📑 פרקים בתוך הסרטון", hint: "בתאריך הזה הסרטון קופא וכרטיס כותרת מכסה את הגרף.",
    required: ["date", "title"], columns: [["date", "date", "תאריך"], ["title", "text", "כותרת"], ["subtitle", "text", "תת-כותרת"], ["seconds", "number", "שניות"]],
    blank: (mid) => ({date: mid, title: "פרק חדש"})},
  {key: "pauses", title: "⏸ עצירות עם הסבר", hint: "הסרטון קופא בתאריך הזה וההסבר מופיע למעלה.",
    required: ["date", "text"], columns: [["date", "date", "תאריך"], ["text", "text", "הסבר"], ["seconds", "number", "שניות"]],
    blank: (mid) => ({date: mid, text: "מה קרה כאן"})},
  {key: "callouts", title: "💬 הערה לישות", hint: "הערה שמצביעה על ישות מסוימת (בעמודות ובקווים; בשאר - בפינה).",
    required: ["date", "entity", "text"], columns: [["date", "date", "מתאריך"], ["entity", "entity", "ישות"], ["text", "text", "הערה"], ["days", "int", "ימים"]],
    blank: (mid) => ({date: mid, entity: ((dvzEd.data.entities || [])[0] || {}).name || "", text: "הערה"})},
  {key: "periods", title: "🟪 תקופות מוצללות", hint: "טווח תאריכים עם שם - מוצלל על הציר, ובתרשים בלי ציר זמן מופיע כתגית.",
    required: ["start", "end", "label"], columns: [["start", "date", "מ-"], ["end", "date", "עד"], ["label", "text", "שם"], ["color", "color", "צבע"]],
    blank: (mid) => ({start: mid, end: mid, label: "תקופה"})},
  {key: "annotations", title: "📌 הערות על הגרף", hint: "חץ וטקסט שמצביעים על נקודה (תאריך + ערך) - בקווים ובשטח מוערם. \"📌 הערה\" ליד התצוגה: לחיצה מוסיפה, גרירה מזיזה. ימים ריק = עד הסוף.",
    required: ["date", "value", "text"], columns: [["date", "date", "תאריך"], ["value", "number", "ערך"], ["text", "text", "טקסט"], ["days", "int", "ימים"],
      ["dx", "int", "היסט אופקי"], ["dy", "int", "היסט אנכי"], ["style", "style", "סגנון"]],
    blank: (mid) => ({date: mid, value: 0, text: "הערה"})},
  {key: "focus", title: "🔦 החלפת פוקוס", hint: "מהתאריך הזה הפוקוס עובר לישויות האלה (שמות מופרדים בפסיק); השאר מתעמעמות. הפוקוס מההתחלה - \"בפוקוס\" בלשונית הישויות.",
    required: ["date", "entities"], columns: [["date", "date", "מתאריך"], ["entities", "text", "ישויות בפוקוס"]],
    blank: (mid) => ({date: mid, entities: ((dvzEd.data.entities || [])[0] || {}).name || ""})},
  {key: "script", title: "🎙 תסריט קריינות", hint: "משפט שהקריינות מקריאה כשהסרטון מגיע לתאריך (צריך קריינות פעילה - לשונית 🎙). \"✨ טיוטה מהנתונים\" כותבת טיוטה מהרגעים החזקים.",
    required: ["date", "text"], columns: [["date", "date", "תאריך"], ["text", "text", "משפט"]],
    blank: (mid) => ({date: mid, text: "מה קורה כאן"}), extra: _dvzScriptDraftButton},
  {key: "speed", title: "⏩ קטעי מהירות", hint: "2 = פי שניים מהר יותר, 0.5 = לאט פי שניים. מעל כלל הצעד המקסימלי.",
    required: ["start", "end", "speed"], columns: [["start", "date", "מ-"], ["end", "date", "עד"], ["speed", "number", "מהירות"]],
    blank: (mid) => ({start: mid, end: mid, speed: 2})},
];

function _dvzStoryMid() {
  const [start, end] = dvzEd.data.date_range || [];
  return start ? _dvzAddDays(start, Math.round(_dvzDayOffset(end, start) / 2)) : new Date().toISOString().slice(0, 10);
}

function _dvzStoryItems(key) {
  const path = "story." + key;
  if (path in dvzEd.draft) return dvzEd.draft[path];
  if (dvzEd.unset.has(path)) return [];
  return ((dvzEd.data.story || {})[key]) || [];
}

function _dvzStoryCell(item, column, commit) {
  const [key, type, label] = column;
  let input;
  if (type === "style") {   // 20.10.2026: סגנון של הערה על הגרף
    input = _dvzEdEl("select");
    for (const [value, text] of DVZ_ANNOTATION_STYLES) input.appendChild(new Option(text, value));
    input.value = item[key] || "default";
    input.onchange = () => { item[key] = input.value; commit(); };
  } else if (type === "entity") {
    input = _dvzEdEl("select");
    const names = (dvzEd.data.entities || []).map(e => e.name);
    if (item[key] && !names.includes(item[key])) names.unshift(item[key]);
    for (const name of names) input.appendChild(new Option(name, name));
    input.value = item[key] || "";
    input.onchange = () => { item[key] = input.value; commit(); };
  } else {
    input = _dvzEdEl("input");
    input.type = type === "int" || type === "number" ? "number" : type;
    if (type === "int") input.step = "1";
    if (type === "number") input.step = "any";
    if (type === "text") input.maxLength = 160;
    input.value = item[key] ?? (type === "color" ? "#d1495b" : "");
    input.oninput = () => {
      if (input.value === "") delete item[key];
      else item[key] = type === "int" ? parseInt(input.value, 10) : type === "number" ? Number(input.value) : input.value;
      commit();
    };
  }
  input.setAttribute("aria-label", label);
  return input;
}

function _dvzStoryList(spec) {
  const path = "story." + spec.key;
  const items = _dvzStoryItems(spec.key).map(item => ({...item}));
  const section = _dvzEdEl("section", "dvz-story-list");
  section.dataset.list = spec.key;
  // לתצוגה החיה נשלחים רק פריטים שמולאו בהם כל שדות החובה (תוך כדי הקלדה הפריט עוד חסר)
  const commit = () => _dvzStage(path, items.filter(item => spec.required.every(key => item[key] !== undefined && item[key] !== "")));
  section.append(_dvzEdEl("h4", "", spec.title), _dvzEdEl("p", "hint", spec.hint));
  if (items.length) {
    const table = _dvzEdEl("table", "dvz-story-table");
    const head = table.createTHead().insertRow();
    for (const [, , label] of spec.columns) head.appendChild(_dvzEdEl("th", "", label));
    head.appendChild(_dvzEdEl("th"));
    const body = table.createTBody();
    items.forEach((item, i) => {
      const tr = body.insertRow();
      for (const column of spec.columns) tr.insertCell().append(_dvzStoryCell(item, column, commit));
      const remove = _dvzEdEl("button", "btn-xs", "🗑");
      remove.type = "button";
      remove.setAttribute("aria-label", "מחק את השורה");
      remove.onclick = () => { items.splice(i, 1); commit(); _dvzRenderEditor(); };
      tr.insertCell().append(remove);
    });
    section.append(table);
  }
  const row = _dvzEdEl("div", "tc-row");
  const add = _dvzEdEl("button", "btn-sm", "➕ הוסף");
  add.type = "button";
  add.onclick = () => { items.push(spec.blank(_dvzStoryMid())); commit(); _dvzRenderEditor(); };
  const reset = _dvzEdEl("button", "btn-sm", "↺ כמו בקובץ הפרק");
  reset.type = "button";
  reset.disabled = !(path in dvzEd.draft) && !(dvzEd.data.changes || []).some(c => c.path === path);
  reset.onclick = () => _dvzStageUnset(path);
  row.append(add, reset);
  if (spec.extra) row.append(spec.extra(items, commit));   // 20.10.2026: טיוטת קריינות
  section.append(row);
  return section;
}

function _dvzStoryTab() {
  const box = _dvzEdEl("div", "dvz-story");
  const tool = _dvzEdEl("button", "btn-sm", "📖 סוג הסיפור - הצעה ושינוי");   // 21.10.2026: כלי הסיפור (גם מתפריט ⋯)
  tool.type = "button";
  tool.onclick = () => dvzOpenStoryWizard();
  box.append(tool, _dvzEdEl("p", "hint", "כמה זמן כל פרק או עצירה, הטיזר ומסך הסיום - בקבוצה \"📖 סיפור\" בלשונית ההגדרות."));
  for (const spec of DVZ_STORY_LISTS) box.append(_dvzStoryList(spec));
  return box;
}

// --- 20.10.2026: "📌 הערה" - לחיצה על התצוגה מוסיפה הערה בנקודה (תאריך + ערך), וגרירה של נקודה קיימת מזיזה אותה.
// הצירים של הפריים מגיעים מהשרת (X-Frame-Axes); בלי צירים (פתיח, סיום, תרשים בלי ציר ערך) - אין הערות ---
function _dvzAnnotationPoint(event) {
  const axes = dvzState.previewAxes;
  const img = document.getElementById("dvzPreviewImg");
  if (!axes || !img) return null;
  const rect = img.getBoundingClientRect();
  const fx = (event.clientX - rect.left) / rect.width, fy = 1 - (event.clientY - rect.top) / rect.height;
  const [x0, y0, x1, y1] = axes.box;
  if (fx < x0 || fx > x1 || fy < y0 || fy > y1) return null;
  const day = axes.xlim[0] + (fx - x0) / (x1 - x0) * (axes.xlim[1] - axes.xlim[0]);
  const value = axes.ylim[0] + (fy - y0) / (y1 - y0) * (axes.ylim[1] - axes.ylim[0]);
  return {date: _dvzAddDays(axes.start, Math.max(0, Math.round(day))), value: Number(value.toPrecision(4))};
}

function _dvzAnnotationPixel(item) {
  const axes = dvzState.previewAxes;
  const img = document.getElementById("dvzPreviewImg");
  const [x0, y0, x1, y1] = axes.box;
  const rect = img.getBoundingClientRect();
  const day = _dvzDayOffset(item.date, axes.start);
  const fx = x0 + (day - axes.xlim[0]) / (axes.xlim[1] - axes.xlim[0]) * (x1 - x0);
  const fy = y0 + (item.value - axes.ylim[0]) / (axes.ylim[1] - axes.ylim[0]) * (y1 - y0);
  return {x: rect.left + fx * rect.width, y: rect.top + (1 - fy) * rect.height};
}

async function dvzToggleAnnotate(on) {
  dvzState.annotate = on === undefined ? !dvzState.annotate : !!on;
  const btn = document.getElementById("dvzAnnotateBtn");
  btn.setAttribute("aria-pressed", String(dvzState.annotate));
  document.getElementById("dvzPreviewImg").classList.toggle("is-annotating", dvzState.annotate);
  uiBus.emit("dvz:annotate", dvzState.annotate);
  document.getElementById("dvzAnnotateForm").hidden = true;
  if (dvzState.annotate && dvzState.animate) dvzToggleAnimation(false);   // הערות - על פריים בודד
  if (dvzState.annotate && (!dvzEd.data || dvzEd.data.episode !== dvzState.selected)) await dvzLoadEditor();   // ההערות השמורות של הפרק
}

function _dvzAnnotationItems() {
  return _dvzStoryItems("annotations").map(item => ({...item}));
}

function _dvzStageAnnotations(items) {
  _dvzStage("story.annotations", items);
  if (dvzEd.tab === "story" && document.getElementById("dvzEditor").open) _dvzRenderEditor();
}

function _dvzInitAnnotations() {
  const anchor = document.getElementById("dvzAnimateBtn");
  const img = document.getElementById("dvzPreviewImg");
  if (!anchor || !img || document.getElementById("dvzAnnotateBtn")) return;
  const btn = _dvzEdEl("button", "btn-sm", "📌 הערה");
  btn.type = "button";
  btn.id = "dvzAnnotateBtn";
  btn.title = "לחיצה על הגרף מוסיפה הערה עם חץ בנקודה; גרירה של הערה קיימת מזיזה אותה";
  btn.setAttribute("aria-pressed", "false");
  btn.onclick = () => dvzToggleAnnotate();
  anchor.after(btn);
  const form = _dvzEdEl("div", "tc-row dvz-annotate-form");
  form.id = "dvzAnnotateForm";
  form.hidden = true;
  const text = _dvzEdEl("input");
  text.id = "dvzAnnotateText";
  text.maxLength = 160;
  text.setAttribute("aria-label", "טקסט ההערה");
  const where = _dvzEdEl("span", "hint");
  const add = _dvzEdEl("button", "btn-sm btn-primary", "➕ הוסף הערה");
  add.type = "button";
  add.onclick = async () => {
    if (!dvzEd.data || dvzEd.data.episode !== dvzState.selected) await dvzLoadEditor();   // בלי ההערות השמורות - לא להחליף אותן
    const items = _dvzAnnotationItems();
    items.push({...form._point, text: text.value.trim() || "הערה"});
    _dvzStageAnnotations(items);
    form.hidden = true;
  };
  form.append(where, text, add);
  img.closest(".dvz-preview-wrap, figure, div").after(form);
  let drag = null;
  img.addEventListener("pointerdown", (e) => {
    if (!dvzState.annotate || !dvzState.previewAxes) return;
    const items = _dvzAnnotationItems();
    const near = items.findIndex(item => { const p = _dvzAnnotationPixel(item); return Math.hypot(p.x - e.clientX, p.y - e.clientY) < 16; });
    if (near >= 0) { drag = {items, index: near}; img.setPointerCapture(e.pointerId); e.preventDefault(); }
  });
  img.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const point = _dvzAnnotationPoint(e);
    if (point) Object.assign(drag.items[drag.index], point);
  });
  img.addEventListener("pointerup", () => {
    if (!drag) return;
    _dvzStageAnnotations(drag.items);
    drag = null;
    img.dataset.dragged = "1";   // ה-click שאחרי הגרירה לא מוסיף הערה חדשה
  });
  img.addEventListener("click", (e) => {
    if (!dvzState.annotate) return;
    if (img.dataset.dragged) { delete img.dataset.dragged; return; }
    const point = _dvzAnnotationPoint(e);
    if (!point) return;
    form._point = point;
    where.textContent = `${point.date} · ${point.value}`;
    text.value = "";
    form.hidden = false;
    text.focus();
  });
}

_dvzInitAnnotations();

// --- 20.10.2026: מצב פוקוס - "בפוקוס" לכל ישות בלשונית הישויות (focus.entities); השאר מתעמעמות לפי focus.dim ---
function _dvzFocusNames() {
  return "focus.entities" in dvzEd.draft ? dvzEd.draft["focus.entities"] : ((dvzEd.data.focus || {}).entities || []).map(String);
}

function _dvzFocusCell(name) {
  const box = _dvzEdEl("input");
  box.type = "checkbox";
  box.checked = _dvzFocusNames().includes(String(name));
  box.setAttribute("aria-label", `${name} בפוקוס`);
  box.onchange = () => {
    const names = new Set(_dvzFocusNames());
    if (box.checked) names.add(String(name)); else names.delete(String(name));
    _dvzStage("focus.entities", [...names]);
  };
  return box;
}

// --- 20.10.2026: אשף תבניות סיפור - מרוץ / מגמה / השוואה של שניים / לפני-אחרי, מהשאלה. "מה ישתנה" מראה לפני ואחרי לכל
// הגדרה בלי לכתוב; "החל" כותב לקובץ השינויים של הפרק (config.yaml לא משתנה) ---
let _dvzWiz = {types: [], type: ""};

// נבנה בפתיחה הראשונה (לא ב-HTML של המסך - תקציב ה-HTML של dataviz הוא 30K)
function _dvzStoryWizardDialog() {
  if (!document.getElementById("dvzStoryWizard")) document.getElementById("dvzNewDialog").insertAdjacentHTML("afterend", `
<dialog id="dvzStoryWizard" class="dvz-dialog" aria-labelledby="dvzStoryWizardHeading">
    <div class="tc-row dvz-dialog-head">
      <h3 id="dvzStoryWizardHeading">📖 הסיפור</h3>
      <button type="button" class="btn-sm" onclick="document.getElementById('dvzStoryWizard').close()">✕ סגור</button>
    </div>
    <div id="dvzWizSuggest" class="dvz-finding is-info" hidden></div>
    <div class="tc-row"><label class="u-flex-0" for="dvzWizQuestion">מה השאלה שהסרטון עונה עליה?</label><input id="dvzWizQuestion" maxlength="200"></div>
    <div id="dvzWizTypes" class="dvz-wiz-types" role="radiogroup" aria-label="סוג הסיפור"></div>
    <div id="dvzWizExtra" class="tc-row"></div>
    <div class="tc-row"><button type="button" class="btn-sm" id="dvzWizPreviewBtn" onclick="dvzStoryWizardPreview()">👁 מה ישתנה</button>
      <button type="button" class="btn-sm btn-primary" id="dvzWizApplyBtn" onclick="dvzStoryWizardApply()" disabled>✅ החל</button></div>
    <div id="dvzWizDiff"></div>
    <div class="hint u-block" id="dvzWizMsg" role="status" aria-live="polite"></div>
</dialog>`);
}

async function dvzOpenStoryWizard(type) {
  if (!dvzState.selected) return;
  _dvzStoryWizardDialog();
  const dialog = document.getElementById("dvzStoryWizard");
  if (!dialog.open) dialog.showModal();
  if (!_dvzWiz.types.length) _dvzWiz.types = (await _dvzJson(await fetch("/api/dataviz/story_templates"))).templates || [];
  if (!dvzEd.data || dvzEd.data.episode !== dvzState.selected) await dvzLoadEditor();
  document.getElementById("dvzWizQuestion").value = ((dvzEd.data.groups || []).flatMap(g => g.fields).find(f => f.path === "intro.question") || {}).value || "";
  document.getElementById("dvzWizDiff").replaceChildren();
  document.getElementById("dvzWizMsg").textContent = "";
  document.getElementById("dvzWizApplyBtn").disabled = true;
  // 21.10.2026 (סבב הפישוט): כלי סיפור אחד - נפתח על הסוג שהעורך החכם מציע (smart/story.py), עם הסיבה; לחיצה על סוג אחר מחליפה
  const box = document.getElementById("dvzWizSuggest");
  box.hidden = true;
  _dvzWiz.suggest = null;
  _dvzWiz.picked = !!type;
  _dvzWiz.type = type || "race";
  _dvzRenderWizardTypes();
  if (type) return;
  const found = await _dvzJson(await fetch("/api/dataviz/story_suggest?episode=" + encodeURIComponent(dvzState.selected)));
  const known = _dvzWiz.types.find(t => t.id === found.value);
  if (!known || !document.getElementById("dvzStoryWizard").open) return;
  _dvzWiz.suggest = found;
  box.replaceChildren(_dvzEdEl("strong", "", `🤖 מוצע: ${known.title}`), _dvzEdEl("span", "hint", ` - ${found.reason} (${Math.round(found.confidence * 100)}%)`),
    ...(found.moments || []).map(m => _dvzEdEl("div", "hint", `${m.date}: ${m.text}`)));
  box.hidden = false;
  if (_dvzWiz.picked) return;   // המשתמש כבר בחר סוג בזמן שההצעה נטענה - לא מחליפים לו
  _dvzWiz.type = found.value;
  _dvzRenderWizardTypes();
  dvzStoryWizardPreview();   // מה ישתנה - מיד, בלי לחיצה
}

function _dvzRenderWizardTypes() {
  document.getElementById("dvzWizTypes").replaceChildren(..._dvzWiz.types.map(t => {
    const card = _dvzEdEl("button", "dvz-wiz-type" + (t.id === _dvzWiz.type ? " active" : ""));
    card.type = "button";
    card.setAttribute("role", "radio");
    card.setAttribute("aria-checked", String(t.id === _dvzWiz.type));
    card.dataset.type = t.id;
    card.append(_dvzEdEl("strong", "", t.title), _dvzEdEl("span", "hint", t.about));
    card.onclick = () => { _dvzWiz.type = t.id; _dvzWiz.picked = true; document.getElementById("dvzWizApplyBtn").disabled = true; _dvzRenderWizardTypes(); };
    return card;
  }));
  const extra = document.getElementById("dvzWizExtra");
  extra.replaceChildren();
  if (_dvzWiz.type === "compare") {
    const names = (dvzEd.data.entities || []).map(e => e.name);
    for (const [i, label] of [[0, "ישות ראשונה:"], [1, "ישות שנייה:"]]) {
      const select = _dvzEdEl("select");
      select.dataset.pick = String(i);
      select.setAttribute("aria-label", label);
      for (const name of names) select.appendChild(new Option(name, name));
      select.value = names[i] || "";
      extra.append(_dvzEdEl("span", "hint", label), select);
    }
  } else if (_dvzWiz.type === "before_after") {
    const date = _dvzEdEl("input");
    date.type = "date";
    date.id = "dvzWizSplit";
    date.value = (_dvzWiz.suggest && _dvzWiz.suggest.split) || _dvzStoryMid();
    date.setAttribute("aria-label", "התאריך שמפריד בין לפני לאחרי");
    extra.append(_dvzEdEl("span", "hint", "התאריך שמפריד:"), date);
  }
}

function _dvzWizardBody() {
  const body = {episode: dvzState.selected, template: _dvzWiz.type, question: document.getElementById("dvzWizQuestion").value.trim()};
  const picks = [...document.querySelectorAll("#dvzWizExtra select[data-pick]")].map(s => s.value);
  if (picks.length) body.pick = picks;
  const split = document.getElementById("dvzWizSplit");
  if (split) body.split = split.value;
  return body;
}

async function dvzStoryWizardPreview() {
  const msg = document.getElementById("dvzWizMsg");
  try {
    const resp = await fetch("/api/dataviz/story_templates/preview", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(_dvzWizardBody())});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "התצוגה נכשלה");
    const table = _dvzEdEl("table", "dvz-changes-table");
    const head = table.createTHead().insertRow();
    for (const title of ["הגדרה", "עכשיו", "אחרי"]) head.appendChild(_dvzEdEl("th", "", title));
    const tbody = table.createTBody();
    for (const change of data.changes) {
      const tr = tbody.insertRow();
      tr.insertCell().textContent = change.label;
      tr.insertCell().textContent = _dvzShow(change.before);
      tr.insertCell().textContent = _dvzShow(change.after);
    }
    document.getElementById("dvzWizDiff").replaceChildren(data.changes.length ? table : _dvzEdEl("p", "hint", "הפרק כבר כזה - אין מה לשנות."));
    document.getElementById("dvzWizApplyBtn").disabled = !data.changes.length;
    msg.textContent = "";
  } catch (e) {
    msg.textContent = "שגיאה: " + e.message;
  }
}

async function dvzStoryWizardApply() {
  const msg = document.getElementById("dvzWizMsg");
  try {
    const resp = await fetch("/api/dataviz/story_templates/apply", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(_dvzWizardBody())});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "ההחלה נכשלה");
    document.getElementById("dvzStoryWizard").close();
    await loadDataviz();
    await dvzLoadEditor();
    dvzPreviewSoon();
    uiToast("✨ הסיפור הוחל - config.yaml לא השתנה", "ok");
  } catch (e) {
    msg.textContent = "שגיאה: " + e.message;
  }
}

// --- 20.10.2026: טיוטת תסריט קריינות מהנתונים - הרגעים החזקים ומשפט לכל אחד (Gemini לפי כללי המכסה; בלעדיו - טיוטה מקומית) ---
function _dvzScriptDraftButton(items, commit) {
  const button = _dvzEdEl("button", "btn-sm", "✨ טיוטה מהנתונים");
  button.type = "button";
  button.id = "dvzScriptDraftBtn";
  button.title = "שיאים, החלפות מקום ראשון, הימים עם התוספת הגדולה והסוף - משפט לכל אחד, לעריכה";
  button.onclick = async () => {
    if (items.length && !await veConfirm("להחליף את התסריט הנוכחי בטיוטה חדשה?", {okLabel: "✨ החלף"})) return;
    const status = document.getElementById("dvzEditorStatus");
    status.textContent = "⏳";
    try {
      const resp = await fetch("/api/dataviz/narration_draft", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({episode: dvzState.selected, draft: dvzEd.draft})});
      const data = await _dvzJson(resp);
      if (!resp.ok) throw new Error(data.error || "הטיוטה נכשלה");
      items.splice(0, items.length, ...data.lines.map(line => ({date: line.date, text: line.text})));
      commit();
      _dvzRenderEditor();
      status.textContent = (data.source === "gemini" ? "✨ טיוטה מ-Gemini" : "📝 טיוטה מקומית") + (data.warning ? " - " + data.warning : "") + " - עורכים ושומרים.";
    } catch (e) {
      status.textContent = "שגיאה: " + e.message;
    }
  };
  return button;
}
