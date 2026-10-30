// ============================================================================
// גל 41: סדרות, תוצרים ופרסום בעורך הגרפים - תור של כמה פרקים בריצה אחת, יעד (YouTube / Shorts /
// TikTok), שכפול והפרק הבא בסדרה, תבנית לפרק חדש, ערכות ערוץ, השוואת שני תוצרים וסל מיחזור,
// חבילות הפרסום של הפרק בתוך המסך, ואשף פרסום (טקסטים, תמונה, אישור, שליחה ותזמון).
// ============================================================================

dvzState.queue = new Set();

// --- תור: כמה פרקים בריצה אחת ---
function _dvzQueueCheckbox(ep) {
  const label = _dvzEdEl("label", "dvz-queue-pick");
  label.title = "סמן כדי להריץ כמה פרקים בריצה אחת";
  const box = _dvzEdEl("input");
  box.type = "checkbox";
  box.checked = dvzState.queue.has(ep.name);
  box.disabled = !ep.valid;
  box.setAttribute("aria-label", `לתור: ${ep.title || ep.name}`);
  box.onchange = () => { if (box.checked) dvzState.queue.add(ep.name); else dvzState.queue.delete(ep.name); _dvzSyncQueueBar(); };
  label.append(box, document.createTextNode("לתור"));
  return label;
}

function _dvzSyncQueueBar() {
  const count = dvzState.queue.size;
  document.getElementById("dvzQueueBar").hidden = !count;
  document.getElementById("dvzQueueRun").textContent = `▶ הרץ ${count} פרקים ברצף`;
}

function dvzClearQueue() {
  dvzState.queue.clear();
  dvzRenderEpisodes();
  _dvzSyncQueueBar();
}

function _dvzRunOptions() {
  const options = {mode: document.getElementById("dvzMode").value, chart: document.getElementById("dvzChart").value,
          publish: document.getElementById("dvzPublish").value, target: document.getElementById("dvzTarget").value,
          lang: (document.getElementById("dvzRunLang") || {}).value || ""};   // גל 55: שפה (בהמשך הקובץ)
  uiBus.emit("dvz:run-options", options);   // 27.10.2026: רינדור טווח (85-dataviz-plus.js) - מוסיף range
  return options;
}

async function dvzRunQueue() {
  const episodes = dvzState.episodes.filter(ep => dvzState.queue.has(ep.name)).map(ep => ep.name);
  if (!episodes.length) return;
  _dvzSetRunning(true);
  document.getElementById("dvzProgressBar").style.width = "0%";
  _dvzSetStatus(`שולח ${episodes.length} פרקים לתור הרינדור...`);
  try {
    const resp = await fetch("/api/dataviz/run", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({..._dvzRunOptions(), range: undefined, episodes})});   // טווח - רק לפרק אחד
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "ההרצה נכשלה");
    _dvzSetStatus(`רץ - ${episodes.length} פרקים אחד אחרי השני.`);
    dvzWatchQueue();   // גל 44: התקדמות לכל פרק, והסרה מהתור
  } catch (e) {
    _dvzSetRunning(false);
    _dvzSetStatus("שגיאה: " + e.message, true);
  }
}

// --- שכפול והפרק הבא בסדרה ---
async function dvzDuplicate(nextInSeries) {
  const ep = dvzState.episodes.find(e => e.name === dvzState.selected);
  if (!ep) return;
  const number = ((ep.series || {}).number || 1) + 1;
  const suggestion = nextInSeries ? `${ep.name.replace(/-\d+$/, "")}-${number}` : `${ep.name}-copy`;
  const name = ((await vePrompt(nextInSeries ? "שם לפרק הבא בסדרה:" : "שם לעותק:", {value: suggestion.slice(0, 40)})) || "").trim();
  if (!name) return;
  try {
    const resp = await fetch("/api/dataviz/episodes/duplicate", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({episode: ep.name, name, next: nextInSeries})});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "השכפול נכשל");
    dvzState.selected = data.name;
    await loadDataviz();
    uiToast(`✅ נוצר "${data.name}"`, "ok");
  } catch (e) {
    uiToast("שגיאה: " + e.message, "warn");
  }
}

// --- תקציב לחיצות: ניחוש העמודות של קובץ חדש - הערך = העמודה המספרית הראשונה, הקבוצה = עמודת הטקסט הראשונה ---
// 19.10.2026 (מהסיור): השורות מפוצלות כמו CSV אמיתי - שם עם פסיק במרכאות ("(°C, בית דגן)") הזיז את העמודות, ועמודת
// טקסט נבחרה כערך. וגם התקופה: עמודת זמן של שנים שלמות = שנה, של YYYY-MM = חודש
function _dvzCsvCells(line) {
  const cells = [];
  let cell = "", quoted = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (quoted && c === '"' && line[i + 1] === '"') { cell += '"'; i++; }
    else if (c === '"') quoted = !quoted;
    else if (c === "," && !quoted) { cells.push(cell); cell = ""; }
    else cell += c;
  }
  cells.push(cell);
  return cells;
}

function _dvzGuessMapping(csvText, columns) {
  const rows = csvText.split(/\r?\n/).slice(1, 21).filter(Boolean).map(_dvzCsvCells);
  if (!rows.length) return {};
  const cells = (i) => rows.map(r => (r[i] ?? "").trim());
  const numeric = (i) => cells(i).every(v => v !== "" && !isNaN(Number(v)));
  const timeIndex = Math.max(0, columns.findIndex(col => /^(date|time|year|month|day|תאריך|שנה|חודש)$/i.test(col)));
  const times = cells(timeIndex);
  const period = times.every(v => /^\d{4}$/.test(v)) ? "year" : times.every(v => /^\d{4}[-/.]\d{1,2}$/.test(v)) ? "month" : "day";
  const value = columns.findIndex((col, i) => i !== timeIndex && numeric(i));
  const group = columns.findIndex((col, i) => i !== timeIndex && !numeric(i));
  return { time_column: columns[timeIndex], period, value_column: value >= 0 ? columns[value] : "", group_column: group >= 0 ? columns[group] : "" };
}

function _dvzGuessColumns(csvText, columns) {
  const guess = _dvzGuessMapping(csvText, columns);
  for (const [id, key] of [["dvzNewTime", "time_column"], ["dvzNewPeriod", "period"], ["dvzNewValue", "value_column"], ["dvzNewGroup", "group_column"]]) {
    if (guess[key] !== undefined) document.getElementById(id).value = guess[key];
  }
}

// --- תבנית לפרק חדש: רשימת הפרקים ---
function _dvzFillTemplates() {
  const select = document.getElementById("dvzNewTemplate");
  if (!select) return;
  const current = select.value;
  select.replaceChildren(new Option("בלי תבנית", ""), ...dvzState.episodes.filter(ep => ep.valid).map(ep => new Option(ep.title || ep.name, ep.name)));
  select.value = dvzState.episodes.some(ep => ep.name === current) ? current : "";
  uiBus.emit("dvz:templates-filled");   // 27.10.2026: התבניות השמורות (85-dataviz-plus.js)
}

// --- ערכות ערוץ ---
async function dvzOpenKits() {
  const box = document.getElementById("dvzKits");
  box.hidden = !box.hidden;
  if (!box.hidden) await _dvzRenderKits();
}

async function _dvzKitPost(path, body, okText) {
  const resp = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const data = await _dvzJson(resp);
  if (!resp.ok) throw new Error(data.error || "הפעולה נכשלה");
  if (okText) uiToast(okText, "ok");
  return data;
}

async function _dvzRenderKits() {
  const box = document.getElementById("dvzKits");
  const data = await (await fetch("/api/dataviz/kits")).json();
  const nodes = [_dvzEdEl("p", "hint", "ערכה = ערכת צבעים, צבע הדגשה, פלטה, גופן, לוגו ואינטרו / אאוטרו מקליפ. החלה על פרק נשמרת בקובץ השינויים שלו.")];
  for (const kit of data.kits) {
    const row = _dvzEdEl("div", "dvz-kit");
    const swatch = _dvzEdEl("span", "dvz-kit-swatch");
    for (const color of [kit.accent, ...kit.palette.slice(0, 5)].filter(Boolean)) {
      const dot = _dvzEdEl("span", "dvz-kit-dot");
      dot.style.background = color;
      swatch.append(dot);
    }
    const apply = _dvzEdEl("button", "btn-sm", "החל על הפרק");
    apply.type = "button";
    apply.onclick = async () => {
      try {
        await _dvzKitPost("/api/dataviz/kits/apply", {episode: dvzState.selected, name: kit.name}, `🏷️ הערכה "${kit.name}" הוחלה`);
        dvzPreviewSoon();
        if (dvzEd.data) dvzLoadEditor();
      } catch (e) { uiToast("שגיאה: " + e.message, "warn"); }
    };
    const remove = _dvzEdEl("button", "btn-xs", "🗑");
    remove.type = "button";
    remove.setAttribute("aria-label", `מחק את הערכה ${kit.name}`);
    remove.onclick = async () => {
      if (!(await veConfirm(`למחוק את הערכה "${kit.name}"? הפרקים שהיא הוחלה עליהם לא משתנים.`, {danger: true}))) return;
      await _dvzKitPost("/api/dataviz/kits/delete", {name: kit.name});
      _dvzRenderKits();
    };
    const extras = [kit.logo ? `🖼️ ${kit.logo}` : "", kit.font ? `🔤 ${kit.font}` : "", ...(kit.bumpers || []).map(b => `🎬 ${b}`)].filter(Boolean).join(" · ");
    row.append(_dvzEdEl("strong", "", kit.name), swatch, _dvzEdEl("span", "hint", extras), apply, remove);
    nodes.push(row);
  }
  const save = _dvzEdEl("button", "btn-sm", "💾 שמור את העיצוב של הפרק כערכה");
  save.type = "button";
  save.onclick = async () => {
    const name = ((await vePrompt("שם לערכה:", {value: "הערוץ שלי"})) || "").trim();
    if (!name) return;
    try { await _dvzKitPost("/api/dataviz/kits/save", {name, episode: dvzState.selected}, "💾 הערכה נשמרה"); _dvzRenderKits(); }
    catch (e) { uiToast("שגיאה: " + e.message, "warn"); }
  };
  nodes.push(save);
  if (data.brand_kits.length) {
    const select = _dvzEdEl("select");
    select.setAttribute("aria-label", "מיתוג של עורך-העל");
    select.append(...data.brand_kits.map(n => new Option(n, n)));
    const importBtn = _dvzEdEl("button", "btn-sm", "📥 ייבא ממיתוג של עורך-העל");
    importBtn.type = "button";
    importBtn.onclick = async () => {
      try { await _dvzKitPost("/api/dataviz/kits/save", {name: select.value, brand_kit: select.value}, "📥 המיתוג יובא כערכה"); _dvzRenderKits(); }
      catch (e) { uiToast("שגיאה: " + e.message, "warn"); }
    };
    const row = _dvzEdEl("div", "tc-row");
    row.append(select, importBtn);
    nodes.push(row);
  }
  box.replaceChildren(...nodes);
}

// --- תוצרים: השוואה בין שניים, וסל מיחזור ---
dvzState.compare = [];

function _dvzOutputExtras(out, card, actions) {
  if (out.kind === "video") {
    const pick = _dvzEdEl("label", "dvz-compare-pick");
    const box = _dvzEdEl("input");
    box.type = "checkbox";
    box.checked = dvzState.compare.some(o => o.name === out.name && o.orientation === out.orientation);
    box.setAttribute("aria-label", `להשוואה: ${out.name}`);
    box.onchange = () => {
      dvzState.compare = dvzState.compare.filter(o => !(o.name === out.name && o.orientation === out.orientation));
      if (box.checked) dvzState.compare.push(out);
      dvzState.compare = dvzState.compare.slice(-2);
      document.getElementById("dvzCompareOutputsBtn").hidden = dvzState.compare.length !== 2;
    };
    pick.append(box, document.createTextNode("⇆ להשוואה"));
    actions.prepend(pick);
  }
  _dvzStudioButton(out, actions);   // גל 56: פתח בסטודיו (87-dataviz-shell.js)
  const trash = _dvzEdEl("button", "btn-sm btn-outline", "🗑️ לסל המיחזור");
  trash.type = "button";
  trash.title = "עובר לסל המיחזור של המחשב (עם החבילה והתמונה שלו) - אפשר לשחזר משם";
  trash.onclick = async () => {
    if (!(await veConfirm(`להעביר את "${out.name}" לסל המיחזור?`, {danger: true, okLabel: "🗑️ לסל המיחזור"}))) return;
    try {
      await _dvzKitPost("/api/dataviz/outputs/trash", {orientation: out.orientation, name: out.name}, "🗑️ עבר לסל המיחזור");
      loadDatavizOutputs();
    } catch (e) { uiToast("שגיאה: " + e.message, "warn"); }
  };
  actions.append(trash);
}

function dvzCompareOutputs() {
  const box = document.getElementById("dvzOutputCompare");
  if (dvzState.compare.length !== 2) return;
  const videos = dvzState.compare.map(out => {
    const figure = _dvzEdEl("figure");
    const video = _dvzEdEl("video", "dvz-video");
    video.controls = true;
    video.preload = "metadata";
    video.src = _dvzMediaUrl(out, out.name);
    figure.append(video, _dvzEdEl("figcaption", "hint", out.name));
    return {figure, video};
  });
  // הראשון מוביל (עם קול), השני עוקב אחריו בלי קול
  const [a, b] = videos.map(v => v.video);
  b.muted = true;
  const follow = () => { if (Math.abs(b.currentTime - a.currentTime) > 0.25) b.currentTime = a.currentTime; };
  a.addEventListener("play", () => { follow(); b.play().catch(() => {}); });
  a.addEventListener("pause", () => b.pause());
  a.addEventListener("seeked", follow);
  const close = _dvzEdEl("button", "btn-sm", "✕ סגור השוואה");
  close.type = "button";
  close.onclick = () => { box.hidden = true; box.replaceChildren(); };
  box.replaceChildren(...videos.map(v => v.figure), close);
  box.hidden = false;
  box.scrollIntoView({block: "nearest"});
}

// --- חבילות הפרסום של הפרק, בתוך המסך ---
async function dvzLoadPackages() {
  const section = document.getElementById("dvzPublishSection");
  const list = document.getElementById("dvzPackages");
  if (!section || !dvzState.selected) return;
  try {
    const packages = (await (await fetch("/api/dataviz/packages")).json()).filter(p => _dvzMatchesEpisode(p.name, dvzState.selected));
    dvzState.packages = packages;
    section.hidden = !packages.length;
    list.replaceChildren(...packages.map(pkg => {
      const card = _datavizCard(pkg);
      const wizard = _dvzEdEl("button", "btn-sm btn-primary", "📦 אשף פרסום");
      wizard.type = "button";
      wizard.onclick = () => openDvzWizard(pkg.id);
      card.append(wizard);
      return card;
    }));
  } catch (e) { section.hidden = true; }
}

// --- אשף הפרסום ---
const DVZ_WIZARD_STEPS = ["טקסטים", "תמונה", "אישור", "שליחה"];
let dvzWizard = {pkg: null, step: 0};

function openDvzWizard(id) {
  const pkg = (dvzState.packages || []).find(p => p.id === id);
  if (!pkg) return;
  dvzWizard = {pkg, step: pkg.status === "approved" ? 3 : 0};
  document.getElementById("dvzWizardBg").classList.add("show");
  _dvzRenderWizard();
}

function closeDvzWizard() {
  document.getElementById("dvzWizardBg").classList.remove("show");
  dvzLoadPackages();
}

async function dvzWizardStep(delta) {
  const status = document.getElementById("dvzWizardStatus");
  status.textContent = "";
  try {
    if (delta > 0 && dvzWizard.step === 0) await _dvzWizardSaveTexts();
    if (delta > 0 && dvzWizard.step === 2 && dvzWizard.pkg.status !== "approved") {
      const resp = await fetch(_datavizPackageUrl(dvzWizard.pkg, "/decide"), {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({decision: "approved"})});
      if (!resp.ok) throw new Error((await _dvzJson(resp)).error || "האישור נכשל");
      dvzWizard.pkg.status = "approved";
    }
    if (delta > 0 && dvzWizard.step === 3) { await _dvzWizardSend(); return; }
    dvzWizard.step = Math.max(0, Math.min(DVZ_WIZARD_STEPS.length - 1, dvzWizard.step + delta));
    _dvzRenderWizard();
  } catch (e) {
    status.textContent = "שגיאה: " + e.message;
  }
}

function _dvzWizardField(label, id, value, multiline) {
  const row = _dvzEdEl("div", "dvz-field");
  const lab = _dvzEdEl("label", "dvz-field-label", label);
  lab.htmlFor = id;
  const input = _dvzEdEl(multiline ? "textarea" : "input");
  if (!multiline) input.type = "text";
  else input.rows = 4;
  input.id = id;
  input.value = value || "";
  input.disabled = !!(dvzWizard.pkg.sent && dvzWizard.pkg.sent.length);
  row.append(lab, input);
  return row;
}

async function _dvzWizardSaveTexts() {
  if (dvzWizard.pkg.sent && dvzWizard.pkg.sent.length) return;
  const val = (id) => document.getElementById(id).value;
  const body = {youtube_title: val("dvzWzTitle"), description: val("dvzWzDesc"), tiktok_caption: val("dvzWzTiktok"),
                hashtags: val("dvzWzTags").split(/[\s,]+/).filter(Boolean)};
  const resp = await fetch(_datavizPackageUrl(dvzWizard.pkg, "/metadata"), {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const data = await _dvzJson(resp);
  if (!resp.ok) throw new Error(data.error || "השמירה נכשלה");
  Object.assign(dvzWizard.pkg, {youtube_title: body.youtube_title, description: body.description, tiktok_caption: body.tiktok_caption, hashtags: data.metadata.hashtags});
}

async function _dvzWizardSend() {
  const target = (document.querySelector("input[name=dvzWzTarget]:checked") || {}).value || "dry_run";
  const when = document.getElementById("dvzWzWhen").value;
  const question = target === "rocket" ? "לשלוח את הסרטון לתיקיית הקלט של Shorts?"
    : when ? "להעלות את הסרטון ליוטיוב כפרטי, ולפרסם אותו בזמן שנבחר?" : "להעלות את הסרטון ל-YouTube כסרטון פרטי?";
  if (target !== "dry_run" && !(await veConfirm(question))) return;
  const resp = await fetch(_datavizPackageUrl(dvzWizard.pkg, "/send"), {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({target, confirm: target !== "dry_run", ...(when && target === "youtube" ? {publish_at: when} : {})})});
  const data = await _dvzJson(resp);
  if (!resp.ok) throw new Error(data.error || "השליחה נכשלה");
  const status = document.getElementById("dvzWizardStatus");
  status.textContent = data.dry_run ? `בדיקה בלבד - לא נשלח כלום: "${data.plan.title}" · ${data.plan.video}`
    : target === "rocket" ? "✅ הסרטון הועתק ל-Shorts." : when ? "✅ ההעלאה ליוטיוב התחילה - פרטי עד הזמן שנבחר." : "✅ ההעלאה ליוטיוב התחילה (פרטי)";
}

function _dvzRenderWizard() {
  const pkg = dvzWizard.pkg;
  document.getElementById("dvzWizardSteps").replaceChildren(...DVZ_WIZARD_STEPS.map((title, i) => {
    const li = _dvzEdEl("li", i === dvzWizard.step ? "is-current" : (i < dvzWizard.step ? "is-done" : ""), title);
    if (i === dvzWizard.step) li.setAttribute("aria-current", "step");
    return li;
  }));
  const body = document.getElementById("dvzWizardBody");
  const nodes = [];
  if (dvzWizard.step === 0) {
    nodes.push(_dvzWizardField("כותרת ליוטיוב", "dvzWzTitle", pkg.youtube_title || pkg.title),
      _dvzWizardField("תיאור", "dvzWzDesc", pkg.description, true),
      _dvzWizardField("כיתוב לטיקטוק", "dvzWzTiktok", pkg.tiktok_caption, true),
      _dvzWizardField("תגיות", "dvzWzTags", (pkg.hashtags || []).join(" ")), _dvzSuggestButton());   // גל 44
  } else if (dvzWizard.step === 1) {
    if (pkg.has_thumbnail) {
      const img = _dvzEdEl("img", "dvz-wizard-thumb");
      img.src = _datavizPackageUrl(pkg, "/thumbnail") + (pkg.thumbVersion ? "?v=" + pkg.thumbVersion : "");
      img.alt = "התמונה הממוזערת";
      nodes.push(img);
    } else {
      nodes.push(_dvzEdEl("p", "hint", "לחבילה הזו אין תמונה ממוזערת."));
    }
    nodes.push(_dvzCandidatesBox(pkg));   // גל 44: שלוש אפשרויות מהסרטון
  } else if (dvzWizard.step === 2) {
    nodes.push(_dvzEdEl("p", "", pkg.status === "approved" ? "✅ החבילה כבר אושרה." : "\"הבא\" מאשר את החבילה לשליחה. דחייה - מכרטיס החבילה."));
  } else {
    const sent = pkg.sent_info || {};
    if (sent.youtube && sent.youtube.video_id) {
      const link = _dvzEdEl("a", "", `▶ הסרטון ביוטיוב (${sent.youtube.video_id})`);
      link.href = `https://youtu.be/${encodeURIComponent(sent.youtube.video_id)}`;
      link.target = "_blank";
      link.rel = "noopener";
      nodes.push(link);
    }
    for (const [value, label] of [["dry_run", "בדיקה בלי שליחה"], ["rocket", "העתק ל-Shorts"], ["youtube", "העלה ליוטיוב (פרטי)"]]) {
      const lab = _dvzEdEl("label", "dvz-wizard-target");
      const radio = _dvzEdEl("input");
      radio.type = "radio";
      radio.name = "dvzWzTarget";
      radio.value = value;
      radio.checked = value === "dry_run";
      radio.disabled = value !== "dry_run" && (pkg.sent || []).includes(value);
      lab.append(radio, document.createTextNode(" " + label + (radio.disabled ? " ✓" : "")));
      nodes.push(lab);
    }
    const when = _dvzEdEl("input");
    when.type = "datetime-local";
    when.id = "dvzWzWhen";
    when.setAttribute("aria-label", "זמן פרסום ביוטיוב");
    const whenRow = _dvzEdEl("div", "dvz-field");
    const whenLabel = _dvzEdEl("label", "dvz-field-label", "תזמון פרסום ביוטיוב (לא חובה):");
    whenLabel.htmlFor = "dvzWzWhen";
    whenRow.append(whenLabel, when);
    nodes.push(whenRow);
  }
  body.replaceChildren(...nodes);
  document.getElementById("dvzWizardBack").disabled = dvzWizard.step === 0;
  document.getElementById("dvzWizardNext").textContent = dvzWizard.step === 3 ? "📤 שלח" : (dvzWizard.step === 2 && pkg.status !== "approved" ? "✅ אשר והמשך" : "הבא ←");
}

// ============================================================================
// גל 55: פרסום בעורך הגרפים - לשונית "🌍 שפות" (הגרסה באנגלית: כותרות, פתיח וסיום, תוויות, הערות, אירועים
// ושמות הישויות), בחירת שפה להרצה (עברית / אנגלית / שתיהן), ולוח צפיות לכל סדרה (גרף צפיות לכל פרק לאורך
// הזמן, מהחבילות שהועלו ליוטיוב). ב-bundle השני של המסך (dataviz_pro).
// ============================================================================

// [נתיב בתוך התרגום, תווית, סוג] - text, lines (רשימת שורות) או long (טקסט ארוך)
const DVZ_LANG_FIELDS = [
  ["title", "כותרת", "text"], ["subtitle", "תת-כותרת", "text"],
  ["intro.title", "פתיח: כותרת", "text"], ["intro.subtitle", "פתיח: תת-כותרת", "text"], ["intro.question", "פתיח: שאלה", "text"],
  ["outro.title", "סיום: כותרת", "text"], ["outro.places", "סיום: שמות המקומות", "lines"], ["outro.credits", "מקורות הנתונים", "lines"],
  ["labels.total", "תווית הסכום", "text"], ["labels.leader", "תווית המוביל", "text"], ["labels.record", "התראת שיא ({entity})", "text"],
  ["labels.others", "עוגה: \"אחרים\"", "text"], ["notes", "הערות בתחתית", "lines"], ["teaser.label", "טיזר: הכיתוב", "text"],
  ["end_screen.text", "מסך סיום: כיתוב", "text"], ["publish.title", "כותרת ביוטיוב", "text"], ["publish.description", "תיאור ביוטיוב", "long"],
  // סבב הייצוב: בלי אלה הגרסה באנגלית יצאה עם המקרא והתגיות בעברית
  ["publish.hashtags", "תגיות ביוטיוב", "lines"], ["legends", "מקרא המקורות (שורה לכל מקור, לפי הסדר)", "lines"],
];

function _dvzLangDraft() {
  const path = "translations.en";
  return JSON.parse(JSON.stringify(path in dvzEd.draft ? dvzEd.draft[path] : ((dvzEd.data.translations || {}).en || {})));
}

function _dvzGetIn(obj, path) {
  return path.split(".").reduce((node, key) => (node && typeof node === "object" ? node[key] : undefined), obj);
}

function _dvzSetIn(obj, path, value) {
  const keys = path.split(".");
  let node = obj;
  for (const key of keys.slice(0, -1)) node = node[key] = (node[key] && typeof node[key] === "object") ? node[key] : {};
  const last = keys[keys.length - 1];
  if (value === "" || (Array.isArray(value) && !value.length)) delete node[last]; else node[last] = value;
}

function _dvzLangsTab() {
  const box = _dvzEdEl("div", "dvz-langs");
  const english = _dvzLangDraft();
  const commit = () => _dvzStage("translations.en", english);
  box.append(_dvzEdEl("p", "hint", "הגרסה באנגלית של הפרק - רק מה שכתוב כאן מתורגם (השאר כמו בעברית). מריצים אותה בבחירת \"שפה: אנגלית\" או \"שתי השפות\" ליד \"הרץ\", והיא נשמרת בקובץ משלה (עם _en בסוף השם)."));
  box.append(_dvzLangCompleteness(english));
  const grid = _dvzEdEl("div", "dvz-lang-grid");
  for (const [path, label, kind] of DVZ_LANG_FIELDS) {
    const row = _dvzEdEl("label", "dvz-lang-row", label);
    const input = _dvzEdEl(kind === "text" ? "input" : "textarea");
    if (kind === "text") input.type = "text"; else input.rows = kind === "long" ? 4 : 2;
    const value = _dvzGetIn(english, path);
    input.value = Array.isArray(value) ? value.join("\n") : (value || "");
    input.dataset.path = path;
    input.setAttribute("aria-label", label + " (English)");
    input.dir = "ltr";
    input.oninput = () => {
      const text = input.value;
      _dvzSetIn(english, path, kind === "lines" ? text.split("\n").map(line => line.trim()).filter(Boolean) : text.trim());
      commit();
    };
    row.append(input);
    grid.append(row);
  }
  box.append(grid);
  // אירועים: אותם תאריכים, תיאור באנגלית
  const events = dvzEd.data.events || [];
  if (events.length) {
    box.append(_dvzEdEl("h4", "", "📅 אירועים"));
    const table = _dvzEdEl("table", "dvz-lang-table");
    for (const event of events) {
      const tr = table.insertRow();
      tr.insertCell().textContent = event.date;
      tr.insertCell().textContent = event.label;
      const input = _dvzEdEl("input");
      input.type = "text";
      input.dir = "ltr";
      input.value = ((english.events || {})[event.date]) || "";
      input.setAttribute("aria-label", `${event.label} (English)`);
      input.oninput = () => { english.events = {...(english.events || {})}; if (input.value.trim()) english.events[event.date] = input.value.trim(); else delete english.events[event.date]; commit(); };
      tr.insertCell().append(input);
    }
    box.append(table);
  }
  // שמות הישויות (רק לתצוגה)
  const entities = (dvzEd.data.entities || []).filter(e => !/^\d+$/.test(e.name)).slice(0, 60);
  if (entities.length) {
    box.append(_dvzEdEl("h4", "", "🏷️ שמות הישויות"));
    const table = _dvzEdEl("table", "dvz-lang-table");
    for (const entity of entities) {
      const tr = table.insertRow();
      tr.insertCell().textContent = entity.name;
      const input = _dvzEdEl("input");
      input.type = "text";
      input.dir = "ltr";
      input.value = ((english.entities || {})[entity.name]) || "";
      input.setAttribute("aria-label", `${entity.name} (English)`);
      input.oninput = () => { english.entities = {...(english.entities || {})}; if (input.value.trim()) english.entities[entity.name] = input.value.trim(); else delete english.entities[entity.name]; commit(); };
      tr.insertCell().append(input);
    }
    box.append(table);
  }
  return box;
}

function _dvzLangCompleteness(english) {
  const filled = DVZ_LANG_FIELDS.filter(([path]) => { const v = _dvzGetIn(english, path); return Array.isArray(v) ? v.length : !!v; }).length;
  const events = (dvzEd.data.events || []).length;
  const translated = Object.keys(english.events || {}).length;
  return _dvzEdEl("p", "dvz-lang-status", `✍️ ${filled}/${DVZ_LANG_FIELDS.length} שדות · ${translated}/${events} אירועים`);
}

// --- בחירת שפה להרצה ---
function _dvzSyncRunLang(ep) {
  const select = document.getElementById("dvzRunLang");
  if (!select) return;
  const hasEnglish = !!(ep && (ep.languages || []).includes("en"));
  select.closest(".dvz-run-lang").hidden = !hasEnglish;
  if (!hasEnglish) select.value = "";
}

function _dvzInitRunLang() {
  const target = document.getElementById("dvzTarget");
  if (!target || document.getElementById("dvzRunLang")) return;
  const row = _dvzEdEl("div", "tc-row dvz-run-lang");
  row.hidden = true;
  const label = _dvzEdEl("label", "u-flex-0", "שפה:");
  label.htmlFor = "dvzRunLang";
  const select = _dvzEdEl("select");
  select.id = "dvzRunLang";
  for (const [value, text] of [["", "עברית"], ["en", "אנגלית"], ["both", "שתי השפות"]]) select.appendChild(new Option(text, value));
  row.append(label, select);
  target.closest(".tc-row").after(row);
}

// --- לוח צפיות לסדרה ---
function _dvzSparkline(history) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 120 32");
  svg.setAttribute("class", "dvz-spark");
  svg.setAttribute("aria-hidden", "true");
  const values = history.map(point => point[1]);
  if (values.length < 2) return svg;
  const max = Math.max(...values, 1);
  const line = document.createElementNS(ns, "polyline");
  line.setAttribute("points", values.map((v, i) => `${(i / (values.length - 1) * 118 + 1).toFixed(1)},${(31 - v / max * 29).toFixed(1)}`).join(" "));
  line.setAttribute("fill", "none");
  line.setAttribute("stroke", "currentColor");
  line.setAttribute("stroke-width", "2");
  svg.append(line);
  return svg;
}

async function dvzOpenBoard() {
  let dialog = document.getElementById("dvzBoard");
  if (!dialog) {
    dialog = _dvzEdEl("dialog", "dvz-board");
    dialog.id = "dvzBoard";
    dialog.setAttribute("aria-label", "לוח צפיות");
    document.body.append(dialog);
  }
  dialog.replaceChildren(_dvzEdEl("p", "hint", "⏳"));
  if (!dialog.open) dialog.showModal();
  let resp, data;
  try {
    resp = await fetch("/api/dataviz/series_board");
    data = await _dvzJson(resp);
  } catch (e) {   // נ15: בלי רשת / שרת הלוח נתקע על "⏳"
    resp = {ok: false};
    data = {error: e.message};
  }
  const head = _dvzEdEl("div", "tc-row dvz-board-head");
  const refresh = _dvzEdEl("button", "btn-sm", "🔄 רענן את כל הצפיות");
  refresh.type = "button";
  refresh.onclick = () => _dvzRefreshAllStats(data, refresh);
  const close = _dvzEdEl("button", "btn-sm", "✖ סגור");
  close.type = "button";
  close.onclick = () => dialog.close();
  head.append(_dvzEdEl("h3", "", "📈 לוח צפיות"), refresh, close);
  const body = [head];
  if (!resp.ok) body.push(_dvzEdEl("p", "empty-msg bad", "שגיאה: " + (data.error || "הטעינה נכשלה")));
  else if (!(data.series || []).length) body.push(_dvzEdEl("p", "empty-msg", "עוד אין פרקים שהועלו ליוטיוב עם צפיות."));
  for (const series of data.series || []) {
    const section = _dvzEdEl("section", "dvz-board-series");
    section.append(_dvzEdEl("h4", "", series.name ? `📚 ${series.name}` : "📄 בלי סדרה"));
    const max = Math.max(...series.episodes.map(e => e.stats.views || 0), 1);
    const table = _dvzEdEl("table", "dvz-board-table");
    const headRow = table.createTHead().insertRow();
    for (const title of ["#", "פרק", "צפיות", "", "לייקים", "תגובות", "לאורך הזמן"]) headRow.appendChild(_dvzEdEl("th", "", title));
    const tbody = table.createTBody();
    for (const ep of series.episodes) {
      const tr = tbody.insertRow();
      tr.dataset.episode = ep.episode;
      tr.insertCell().textContent = ep.number || "";
      tr.insertCell().textContent = ep.title;
      tr.insertCell().textContent = (ep.stats.views || 0).toLocaleString("he-IL");
      const bar = _dvzEdEl("span", "dvz-board-bar");
      bar.style.inlineSize = `${Math.round((ep.stats.views || 0) / max * 100)}%`;
      tr.insertCell().append(bar);
      tr.insertCell().textContent = (ep.stats.likes || 0).toLocaleString("he-IL");
      tr.insertCell().textContent = (ep.stats.comments || 0).toLocaleString("he-IL");
      tr.insertCell().append(_dvzSparkline(ep.history || []));
    }
    section.append(table);
    body.push(section);
  }
  dialog.replaceChildren(...body);
}

async function _dvzRefreshAllStats(data, button) {
  button.disabled = true;
  for (const series of data.series || []) {
    for (const ep of series.episodes) {
      try {
        await fetch(_datavizPackageUrl(ep.package, "/stats"), {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
      } catch (e) { /* פרק בלי חיבור - ממשיכים */ }
    }
  }
  await dvzOpenBoard();
}

function _dvzInitPublish2() {
  _dvzInitRunLang();   // 21.10.2026: לוח הצפיות - ב"🧰 כלים" (87-dataviz-shell.js)
}

_dvzInitPublish2();

// --- 21.10.2026 (סבב הפישוט): "✅ לפני רינדור" - רשימה אחת במקום שלושה מקומות: בדיקת הנתונים (הייתה לשונית "✅ בדיקה" ותג
// בסרגל), בדיקת העובדות (לשונית "🔎 בדיקת עובדות") ובדיקת הקריאות (חלון מתפריט ⋯). לכל שורה ✓ / ⚠ והתיקון שהיה לה:
// "🔧" של הקריאות מכניס לטיוטה (לא נשמר עד "שמור"), "🧹 לניקוי" פותח את הניקוי של הנתונים, ופירוט העובדות נפתח במקום ---
const DVZ_READ_ICONS = {small: "🔍", overlap: "⚠️", contrast: "🌓", crowded: "👥"};

// נבנה בפתיחה הראשונה (לא ב-HTML של המסך - תקציב ה-HTML של dataviz הוא 30K)
function _dvzPrerenderDialog() {
  if (!document.getElementById("dvzPrerender")) document.getElementById("dvzNewDialog").insertAdjacentHTML("afterend", `
<dialog id="dvzPrerender" class="dvz-dialog" aria-labelledby="dvzPrerenderHeading">
    <div class="tc-row dvz-dialog-head">
      <h3 id="dvzPrerenderHeading">✅ לפני רינדור</h3>
      <button type="button" class="btn-sm" onclick="document.getElementById('dvzPrerender').close()">✕ סגור</button>
    </div>
    <p class="hint" id="dvzPreSummary" role="status" aria-live="polite"></p>
    <h4>📊 הנתונים</h4>
    <div id="dvzPreData"></div>
    <h4>🔎 המספרים על המסך מול הקבצים</h4>
    <div id="dvzPreFacts"></div>
    <h4>📏 קריאות</h4>
    <div class="tc-row"><label class="u-flex-0" for="dvzReadTarget">יעד:</label><select id="dvzReadTarget" onchange="dvzRunReadability()"></select>
      <button type="button" class="btn-sm" id="dvzReadCheckBtn" onclick="dvzRunReadability()">🔄 בדוק שוב</button></div>
    <p class="hint">כמה פריימים בגודל המלא של היעד, עם השינויים שעוד לא נשמרו. "תקן" מכניס את ההצעה לטיוטה - בודקים שוב ושומרים.</p>
    <div id="dvzReadResults"></div>
    <div class="hint u-block" id="dvzReadMsg" role="status" aria-live="polite"></div>
    <div class="tc-row dvz-review-foot"><button type="button" class="btn-sm btn-primary" id="dvzPreRunBtn" onclick="dvzPrerenderRun()">▶ הרץ</button></div>
</dialog>`);
}

let _dvzPre = {data: null, facts: null, read: null};

async function dvzOpenPrerender() {
  if (!dvzState.selected) return;
  _dvzPrerenderDialog();
  const dialog = document.getElementById("dvzPrerender");
  if (!dialog.open) dialog.showModal();
  _dvzPre = {data: null, facts: null, read: null, ticket: _dvzPre.ticket};
  const select = document.getElementById("dvzReadTarget");
  if (!select.options.length) {
    const data = await _dvzJson(await fetch("/api/dataviz/readability/targets"));
    for (const t of data.targets || []) select.appendChild(new Option(t.label, t.id));
  }
  if (!dvzEd.data || dvzEd.data.episode !== dvzState.selected) await dvzLoadEditor();
  _dvzPreSummary();
  _dvzOnboardHint(3);
  await Promise.all([_dvzPreData(), _dvzPreFacts(), dvzRunReadability()]);
}

function _dvzPreRow(ok, text, ...extra) {
  const row = _dvzEdEl("div", "dvz-finding " + (ok ? "is-info" : "is-warn"));
  row.append(_dvzEdEl("strong", "", (ok ? "✓ " : "⚠ ") + text), ...extra);
  return row;
}

function _dvzPreSummary() {
  const parts = [_dvzPre.data, _dvzPre.facts, _dvzPre.read];
  const warnings = parts.reduce((sum, n) => sum + (n || 0), 0);
  document.getElementById("dvzPreSummary").textContent = parts.some(n => n === null) ? "⏳ בודק..."
    : warnings === 1 ? "⚠ דבר אחד לבדוק - אפשר לתקן או להריץ בכל זאת."
    : warnings ? `⚠ ${warnings} דברים לבדוק - אפשר לתקן או להריץ בכל זאת.` : "✓ הכל נראה טוב - אפשר להריץ.";
  uiBus.emit("dvz:pre-summary");   // 27.10.2026: ציון הפרק (85-dataviz-plus.js)
}

async function _dvzPreData() {
  const box = document.getElementById("dvzPreData");
  box.replaceChildren(_dvzEdEl("p", "hint", "⏳"));
  try {
    const check = await _dvzFetchPart("check");
    const warnings = check.findings.filter(f => f.level === "warn");
    const clean = _dvzEdEl("button", "btn-xs", "🧹 לניקוי");
    clean.type = "button";
    clean.onclick = () => { document.getElementById("dvzPrerender").close(); dvzData.tab = "clean"; const d = document.getElementById("dvzData"); d.open = true; dvzLoadData(); d.scrollIntoView({block: "nearest"}); };
    box.replaceChildren(_dvzEdEl("p", "hint", `${check.days} ימים (${check.start} עד ${check.end}) · ${check.entities} ישויות · סכום ${Math.round(check.total).toLocaleString("he-IL")}`),
      ...(check.findings.length ? check.findings.map(f => _dvzPreRow(f.level !== "warn", f.text)) : [_dvzPreRow(true, "לא נמצא שום דבר חשוד בנתונים.")]));
    if (warnings.length) box.append(clean);
    _dvzPre.data = warnings.length;
  } catch (e) {
    box.replaceChildren(_dvzEdEl("p", "hint", "שגיאה: " + e.message));
    _dvzPre.data = 0;
  }
  _dvzPreSummary();
}

async function _dvzPreFacts() {
  const box = document.getElementById("dvzPreFacts");
  box.replaceChildren(_dvzEdEl("p", "hint", "⏳"));
  try {
    const facts = await _dvzFetchPart("facts");
    const details = _dvzEdEl("details", "dvz-pre-details");
    details.append(_dvzEdEl("summary", "", "פירוט"), await _dvzFactsView());
    details.open = !!facts.mismatches;
    box.replaceChildren(_dvzPreRow(!facts.mismatches, facts.mismatches ? `${facts.mismatches} מספרים לא מתאימים לקבצים (מתוך ${facts.checked})` : `כל ${facts.checked} המספרים שנבדקו מתאימים לקבצים`), details);
    _dvzPre.facts = facts.mismatches ? 1 : 0;
  } catch (e) {
    box.replaceChildren(_dvzEdEl("p", "hint", "שגיאה: " + e.message));
    _dvzPre.facts = 0;
  }
  _dvzPreSummary();
}

async function dvzRunReadability() {
  const msg = document.getElementById("dvzReadMsg");
  const box = document.getElementById("dvzReadResults");
  const ticket = _dvzPre.ticket = (_dvzPre.ticket || 0) + 1;   // רק הבדיקה האחרונה מציירת (החלפת יעד באמצע בדיקה)
  msg.textContent = "⏳ מצייר כמה פריימים בגודל מלא...";
  box.replaceChildren();
  _dvzPre.read = null;
  _dvzPreSummary();
  try {
    const resp = await fetch("/api/dataviz/readability", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({episode: dvzState.selected, target: document.getElementById("dvzReadTarget").value, draft: dvzEd.draft})});
    const data = await _dvzJson(resp);
    if (ticket !== _dvzPre.ticket) return;
    if (!resp.ok) throw new Error(data.error || "הבדיקה נכשלה");
    msg.textContent = `${data.label} - ${data.size[0]}x${data.size[1]}, ${data.frames} פריימים, טקסט קריא מ-${data.min_px}px`;
    _dvzPre.read = data.warnings.length;
    if (!data.warnings.length) {
      box.replaceChildren(_dvzPreRow(true, "הכל קריא ביעד הזה"));
      return;
    }
    box.replaceChildren(...data.warnings.map(w => {
      const row = _dvzPreRow(false, `${DVZ_READ_ICONS[w.kind] || ""} ${w.message}`.trim());
      row.dataset.kind = w.kind;
      if (w.examples.length) row.append(_dvzEdEl("div", "hint", w.examples.join(" · ")));
      if (w.fix) {
        const fix = _dvzEdEl("button", "btn-sm", "🔧 " + w.fix.label);
        fix.type = "button";
        fix.onclick = () => {
          _dvzStage(w.fix.path, w.fix.value);
          fix.disabled = true;
          fix.textContent = "✅ בטיוטה - בודקים שוב ושומרים";
        };
        row.append(fix);
      }
      return row;
    }));
  } catch (e) {
    msg.textContent = "שגיאה: " + e.message;
    _dvzPre.read = 0;
  } finally {
    if (ticket === _dvzPre.ticket) _dvzPreSummary();
  }
}

function dvzPrerenderRun() {
  document.getElementById("dvzPrerender").close();
  if (dvzOnboard.step === 3) dvzOnboardEnd(true);
  dvzRun();
}

// --- 20.10.2026: היסטוריית גרסאות - תמונת מצב של קובץ השינויים בכל שמירה (dataviz/web/history.py). "השוואה" מראה מה
// ישתנה, "↺ שחזר" כותב את הגרסה לקובץ השינויים (גם השחזור נכנס להיסטוריה - אפשר לחזור ממנו) ---
function _dvzHistoryDialog() {
  if (document.getElementById("dvzHistory")) return;
  document.getElementById("dvzNewDialog").insertAdjacentHTML("afterend", `<dialog id="dvzHistory" class="dvz-dialog" aria-labelledby="dvzHistoryHeading">
  <div class="tc-row dvz-dialog-head">
    <h3 id="dvzHistoryHeading">🕘 היסטוריית גרסאות</h3>
    <button type="button" class="btn-sm" onclick="document.getElementById('dvzHistory').close()">✕ סגור</button>
  </div>
  <p class="hint">תמונת מצב בכל שמירה (רק האחרונות נשמרות). שחזור משנה רק את קובץ השינויים - config.yaml לא נכתב.</p>
  <div id="dvzHistList"></div>
  <div id="dvzHistDiff"></div>
  <div class="hint u-block" id="dvzHistMsg" role="status" aria-live="polite"></div>
</dialog>`);
}

function _dvzHistValue(value) {
  if (value !== null && typeof value === "object") return JSON.stringify(value).slice(0, 90);
  return _dvzShow(value);
}

async function dvzOpenHistory() {
  if (!dvzState.selected) return;
  _dvzHistoryDialog();
  const dialog = document.getElementById("dvzHistory");
  if (!dialog.open) dialog.showModal();
  document.getElementById("dvzHistDiff").replaceChildren();
  document.getElementById("dvzHistMsg").textContent = "";
  const list = document.getElementById("dvzHistList");
  let data;
  try {   // 23.10.2026: שגיאת שרת הוצגה כ"עוד אין גרסאות"
    data = await _dvzJsonOk(await fetch("/api/dataviz/history?episode=" + encodeURIComponent(dvzState.selected)));
  } catch (e) {
    list.replaceChildren(_dvzEdEl("p", "empty-msg bad", "שגיאה: " + e.message));
    return;
  }
  if (!(data.versions || []).length) {
    list.replaceChildren(_dvzEdEl("p", "hint", "עוד אין גרסאות - הן נשמרות מהשמירה הבאה."));
    return;
  }
  const table = _dvzEdEl("table", "dvz-changes-table");
  const head = table.createTHead().insertRow();
  for (const title of ["מתי", "שונה מעכשיו", ""]) head.appendChild(_dvzEdEl("th", "", title));
  const tbody = table.createTBody();
  for (const v of data.versions) {
    const tr = tbody.insertRow();
    tr.dataset.version = v.id;
    tr.insertCell().textContent = v.time + (v.note ? " - " + v.note : "");
    const changed = tr.insertCell();
    changed.textContent = v.changes ? `${v.changes} הגדרות` : "זהה לעכשיו";
    if (v.config_changed) changed.append(_dvzEdEl("div", "hint", "config.yaml השתנה מאז"));
    const actions = tr.insertCell();
    const show = _dvzEdEl("button", "btn-sm", "השוואה");
    show.type = "button";
    show.onclick = () => _dvzHistoryDiff(v.id);
    const restore = _dvzEdEl("button", "btn-sm", "↺ שחזר");
    restore.type = "button";
    restore.disabled = !v.changes;
    restore.onclick = () => _dvzHistoryRestore(v);
    actions.append(show, restore);
  }
  list.replaceChildren(table);
  uiBus.emit("dvz:history-shown");   // 27.10.2026: תמונה לכל גרסה (85-dataviz-plus.js)
}

async function _dvzHistoryDiff(id) {
  const data = await _dvzJson(await fetch(`/api/dataviz/history/diff?episode=${encodeURIComponent(dvzState.selected)}&id=${encodeURIComponent(id)}`));
  const box = document.getElementById("dvzHistDiff");
  if (!data.changes) { box.replaceChildren(_dvzEdEl("p", "hint", data.error || "")); return; }
  const fields = dvzEd.data && dvzEd.data.episode === dvzState.selected ? (dvzEd.data.groups || []).flatMap(g => g.fields) : [];
  const table = _dvzEdEl("table", "dvz-changes-table");
  const head = table.createTHead().insertRow();
  for (const title of ["הגדרה", "עכשיו", "בגרסה"]) head.appendChild(_dvzEdEl("th", "", title));
  const tbody = table.createTBody();
  for (const row of data.changes) {
    const tr = tbody.insertRow();
    tr.insertCell().textContent = (fields.find(f => f.path === row.path) || {}).label || row.path;
    tr.insertCell().textContent = _dvzHistValue(row.now);
    tr.insertCell().textContent = _dvzHistValue(row.then);
  }
  box.replaceChildren(data.changes.length ? table : _dvzEdEl("p", "hint", "זהה לעכשיו."));
  if (data.config_changed) box.append(_dvzEdEl("p", "hint", "config.yaml השתנה מאז הגרסה הזו - הוא לא משוחזר."));
}

async function _dvzHistoryRestore(version) {
  if (!await veConfirm(`לשחזר את הגרסה מ-${version.time}? (גם המצב הנוכחי נשמר בהיסטוריה)`, {okLabel: "↺ שחזר"})) return;
  const msg = document.getElementById("dvzHistMsg");
  try {
    const resp = await fetch("/api/dataviz/history/restore", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({episode: dvzState.selected, id: version.id})});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "השחזור נכשל");
    await loadDataviz();
    await dvzLoadEditor();
    dvzPreviewSoon();
    await dvzOpenHistory();
    uiToast("↺ הגרסה שוחזרה - config.yaml לא השתנה", "ok");
  } catch (e) {
    msg.textContent = "שגיאה: " + e.message;
  }
}

// --- 20.10.2026: גרסאות של פרק - שכבה עם שם (השינויים שבטיוטה) מעל אותו בסיס, עם יעד ושפה משלה, ורינדור לבד דרך התור
// (dataviz/web/variants.py). הבסיס לא משתנה; הסרטון של גרסה נשמר בשם <פרק>_<גרסה> ---
const DVZ_VARIANT_TARGETS = [["", "כמו הפרק"], ["youtube", "YouTube (16:9)"], ["shorts", "Shorts (9:16)"], ["tiktok", "TikTok (9:16)"]];
const DVZ_VARIANT_MODES = [["stills", "תמונות"], ["test", "בדיקה"], ["full", "מלא"]];

function _dvzVariantsDialog() {
  if (document.getElementById("dvzVariants")) return;
  document.getElementById("dvzNewDialog").insertAdjacentHTML("afterend", `<dialog id="dvzVariants" class="dvz-dialog" aria-labelledby="dvzVariantsHeading">
  <div class="tc-row dvz-dialog-head">
    <h3 id="dvzVariantsHeading">🧬 גרסאות של הפרק</h3>
    <button type="button" class="btn-sm" onclick="document.getElementById('dvzVariants').close()">✕ סגור</button>
  </div>
  <div id="dvzVarList"></div>
  <h4>גרסה חדשה מהטיוטה</h4>
  <p class="hint">משנים בעורך בלי לשמור, ואז "שמור כגרסה" - השינויים שבטיוטה הופכים לשכבה של הגרסה, והבסיס לא משתנה.</p>
  <div class="tc-row"><label class="u-flex-0" for="dvzVarName">שם:</label><input id="dvzVarName" maxlength="30" placeholder="short">
    <label class="u-flex-0" for="dvzVarLabel">תיאור:</label><input id="dvzVarLabel" maxlength="60" placeholder="גרסה קצרה"></div>
  <div class="tc-row"><label class="u-flex-0" for="dvzVarTarget">יעד:</label><select id="dvzVarTarget"></select>
    <label class="u-flex-0" for="dvzVarLang">שפה:</label><select id="dvzVarLang"><option value="">כמו הפרק</option><option value="en">English (translations.en)</option></select>
    <button type="button" class="btn-sm btn-primary" id="dvzVarSaveBtn" onclick="dvzSaveVariant()">💾 שמור כגרסה</button></div>
  <div class="hint u-block" id="dvzVarMsg" role="status" aria-live="polite"></div>
</dialog>`);
  const select = document.getElementById("dvzVarTarget");
  for (const [value, label] of DVZ_VARIANT_TARGETS) select.appendChild(new Option(label, value));
}

async function dvzOpenVariants() {
  if (!dvzState.selected) return;
  _dvzVariantsDialog();
  const dialog = document.getElementById("dvzVariants");
  if (!dialog.open) dialog.showModal();
  if (!dvzEd.data || dvzEd.data.episode !== dvzState.selected) await dvzLoadEditor();
  document.getElementById("dvzVarMsg").textContent = "";
  await _dvzRenderVariants();
}

async function _dvzRenderVariants() {
  const list = document.getElementById("dvzVarList");
  let data;
  try {   // 23.10.2026: שגיאת שרת הוצגה כ"עוד אין גרסאות לפרק הזה"
    data = await _dvzJsonOk(await fetch("/api/dataviz/variants?episode=" + encodeURIComponent(dvzState.selected)));
  } catch (e) {
    list.replaceChildren(_dvzEdEl("p", "empty-msg bad", "שגיאה: " + e.message));
    return;
  }
  if (!(data.variants || []).length) {
    list.replaceChildren(_dvzEdEl("p", "hint", "עוד אין גרסאות לפרק הזה."));
    return;
  }
  const targets = Object.fromEntries(DVZ_VARIANT_TARGETS);
  const table = _dvzEdEl("table", "dvz-changes-table");
  const head = table.createTHead().insertRow();
  for (const title of ["גרסה", "יעד ושפה", "שינויים", ""]) head.appendChild(_dvzEdEl("th", "", title));
  const tbody = table.createTBody();
  for (const v of data.variants) {
    const tr = tbody.insertRow();
    tr.dataset.variant = v.name;
    tr.insertCell().textContent = `${v.label} (${v.name})`;
    tr.insertCell().textContent = (targets[v.target] || v.target) + (v.lang ? " · English" : "");
    tr.insertCell().textContent = Object.keys(v.set).map(path => (dvzEd.data.groups || []).flatMap(g => g.fields).find(f => f.path === path)?.label || path).join(", ") || "—";
    const actions = tr.insertCell();
    const mode = _dvzEdEl("select");
    mode.setAttribute("aria-label", "סוג הרינדור");
    for (const [value, label] of DVZ_VARIANT_MODES) mode.appendChild(new Option(label, value));
    const run = _dvzEdEl("button", "btn-sm", "▶ רנדר");
    run.type = "button";
    run.onclick = () => _dvzRunVariant(v.name, mode.value);
    const remove = _dvzEdEl("button", "btn-sm", "🗑 הסר");
    remove.type = "button";
    remove.onclick = async () => {
      if (!await veConfirm(`להסיר את הגרסה "${v.label}"? הקובץ שלה עובר הצידה ולא נמחק.`, {danger: true, okLabel: "🗑 הסר"})) return;
      await fetch("/api/dataviz/variants/remove", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({episode: dvzState.selected, name: v.name})});
      await _dvzRenderVariants();
    };
    actions.append(mode, run, remove);
  }
  list.replaceChildren(table);
}

async function dvzSaveVariant() {
  const msg = document.getElementById("dvzVarMsg");
  const name = document.getElementById("dvzVarName").value.trim();
  if (!Object.keys(dvzEd.draft).length) { msg.textContent = "אין שינויים בטיוטה - משנים משהו בעורך (בלי לשמור) ואז שומרים כגרסה."; return; }
  try {
    const resp = await fetch("/api/dataviz/variants/save", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({episode: dvzState.selected, name, label: document.getElementById("dvzVarLabel").value.trim(),
        target: document.getElementById("dvzVarTarget").value, lang: document.getElementById("dvzVarLang").value, set: dvzEd.draft})});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "השמירה נכשלה");
    dvzDiscardDraft();   // השינויים עברו לגרסה - הבסיס נשאר כמו שהיה
    msg.textContent = `✅ הגרסה ${name} נשמרה - הבסיס לא השתנה.`;
    await _dvzRenderVariants();
  } catch (e) {
    msg.textContent = "שגיאה: " + e.message;
  }
}

async function _dvzRunVariant(name, mode) {
  const msg = document.getElementById("dvzVarMsg");
  try {
    const resp = await fetch("/api/dataviz/run", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({episode: dvzState.selected, mode, variant: name})});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "ההרצה נכשלה");
    _dvzSetRunning(true);
    _dvzSetStatus("רץ... אפשר לעקוב גם בלוג של מסך הסקריפטים.");
    document.getElementById("dvzVariants").close();
  } catch (e) {
    msg.textContent = "שגיאה: " + e.message;
  }
}

// --- 20.10.2026: דוח תמונות - כמה פריימים לכל פרק בתיקייה (טיוטה / תיקייה אחרת / הפרקים של האפליקציה), ברקע, עם דף דוח.
// רינדור מלא - רק בלחיצה מפורשת (פעמיים), דרך התור הקיים, ורק לפרקים של האפליקציה (dataviz/web/batch.py) ---
let _dvzBatchTimer = 0;

function _dvzBatchDialog() {
  if (document.getElementById("dvzBatch")) return;
  document.getElementById("dvzNewDialog").insertAdjacentHTML("afterend", `<dialog id="dvzBatch" class="dvz-dialog" aria-labelledby="dvzBatchHeading">
  <div class="tc-row dvz-dialog-head">
    <h3 id="dvzBatchHeading">🖼 דוח תמונות</h3>
    <button type="button" class="btn-sm" onclick="document.getElementById('dvzBatch').close()">✕ סגור</button>
  </div>
  <p class="hint">שלוש תמונות לכל פרק (התחלה, אמצע, סוף) בגודל קטן - בלי וידאו. תיקיות המקור רק נקראות; הדוח נשמר בתיקייה חדשה ב-workspace/dataviz/batch.</p>
  <div class="tc-row"><label class="u-flex-0" for="dvzBatchSource">מקור:</label><select id="dvzBatchSource"></select></div>
  <div class="tc-row" id="dvzBatchPathRow" hidden><label class="u-flex-0" for="dvzBatchPath">תיקייה:</label><input id="dvzBatchPath" dir="ltr" placeholder="C:\...\episodes"></div>
  <div class="tc-row"><button type="button" class="btn-sm btn-primary" id="dvzBatchStartBtn" onclick="dvzStartBatch()">▶ צור דוח</button></div>
  <div class="progress-wrap"><div class="progress-bar" id="dvzBatchBar"></div></div>
  <div id="dvzBatchResult"></div>
  <div class="hint u-block" id="dvzBatchMsg" role="status" aria-live="polite"></div>
</dialog>`);
  document.getElementById("dvzBatchSource").onchange = e => { document.getElementById("dvzBatchPathRow").hidden = e.target.value !== "folder"; };
}

async function dvzOpenBatch() {
  _dvzBatchDialog();
  const dialog = document.getElementById("dvzBatch");
  if (!dialog.open) dialog.showModal();
  const data = await _dvzJson(await fetch("/api/dataviz/batch/sources"));
  const select = document.getElementById("dvzBatchSource");
  select.replaceChildren();
  if (data.staging) select.appendChild(new Option("תיקיית הטיוטה (staging)", "staging"));
  select.appendChild(new Option("כל הפרקים באפליקציה", "app:"));
  for (const folder of data.folders || []) select.appendChild(new Option(`פרקים בתיקייה: ${folder}`, "app:" + folder));
  select.appendChild(new Option("תיקייה אחרת...", "folder"));
  document.getElementById("dvzBatchPathRow").hidden = select.value !== "folder";
  _dvzShowBatch(data);
  if (data.running) _dvzPollBatch();
}

async function dvzStartBatch() {
  const msg = document.getElementById("dvzBatchMsg");
  const value = document.getElementById("dvzBatchSource").value;
  const body = value.startsWith("app:") ? {source: "app", folder: value.slice(4)} : {source: value, path: document.getElementById("dvzBatchPath").value.trim()};
  try {
    const resp = await fetch("/api/dataviz/batch/start", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "הדוח לא התחיל");
    msg.textContent = "";
    _dvzShowBatch(data);
    _dvzPollBatch();
  } catch (e) {
    msg.textContent = "שגיאה: " + e.message;
  }
}

function _dvzPollBatch() {
  clearTimeout(_dvzBatchTimer);
  _dvzBatchTimer = setTimeout(async () => {
    const data = await _dvzJson(await fetch("/api/dataviz/batch/status"));
    _dvzShowBatch(data);
    if (data.running) _dvzPollBatch();
  }, 800);
}

function _dvzShowBatch(data) {
  document.getElementById("dvzBatchStartBtn").disabled = !!data.running;
  document.getElementById("dvzBatchBar").style.width = data.total ? Math.round(100 * (data.done || 0) / data.total) + "%" : "0%";
  const box = document.getElementById("dvzBatchResult");
  if (data.running) { box.replaceChildren(_dvzEdEl("p", "hint", `⏳ ${data.done || 0} מתוך ${data.total}`)); return; }
  if (!data.id) { box.replaceChildren(); return; }
  if (data.error) { box.replaceChildren(_dvzEdEl("p", "dvz-finding is-warn", "❌ " + data.error)); return; }
  const summary = _dvzEdEl("p", data.failed ? "dvz-finding is-warn" : "dvz-finding is-info", `✅ ${data.ok} תקינים, ${data.failed} נכשלו`);
  const link = _dvzEdEl("a", "btn-sm", "📄 פתח את הדוח");
  link.id = "dvzBatchReportLink";
  link.href = `/api/dataviz/batch/report/${encodeURIComponent(data.id)}/index.html`;
  link.target = "_blank";
  link.rel = "noopener";
  box.replaceChildren(summary, link);
  const names = data.names || [];
  if (data.source === "app" && names.length) {
    const full = _dvzEdEl("button", "btn-sm", `🎬 רינדור מלא ל-${Math.min(names.length, 30)} הפרקים (דרך התור)`);
    full.type = "button";
    full.id = "dvzBatchFullBtn";
    full.onclick = async () => {   // רינדור מלא ארוך - רק אחרי אישור מפורש
      if (!await veConfirm(`לשלוח ${Math.min(names.length, 30)} פרקים לרינדור מלא בתור? זה יכול לקחת הרבה זמן.`, {okLabel: "🎬 שלח לתור"})) return;
      const resp = await fetch("/api/dataviz/run", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({episodes: names.slice(0, 30), mode: "full"})});
      const result = await _dvzJson(resp);
      document.getElementById("dvzBatchMsg").textContent = resp.ok ? "רץ... אפשר לעקוב גם בלוג של מסך הסקריפטים." : "שגיאה: " + (result.error || "ההרצה נכשלה");
      if (resp.ok) _dvzSetRunning(true);
    };
    box.append(full);
  }
}

// --- 20.10.2026: התראה בסיום / כישלון רינדור - Discord webhook אופציונלי. הכתובת נשמרת כסוד בשרת ולא חוזרת לדפדפן
// (רק אם מוגדרת וסופה). dataviz_maker.py שולח בסוף כל ריצה (dataviz/web/notify.py) ---
// 21.10.2026 (סבב הפישוט): "⚙️ הגדרות עורך הגרפים" - ההגדרות החד-פעמיות בחלון אחד, מ"🧰 כלים" ולא מזרימת העבודה:
// התראות (היה "🔔 התראות" ליד רשימת הפרקים), תיקייה במעקב והעדפות שנלמדו (היה "⚙️ מעקב והעדפות" בחלון "מתיקייה")
function _dvzSettingsDialog() {
  if (document.getElementById("dvzSettings")) return;
  document.getElementById("dvzNewDialog").insertAdjacentHTML("afterend", `<dialog id="dvzSettings" class="dvz-dialog" aria-labelledby="dvzSettingsHeading">
  <div class="tc-row dvz-dialog-head">
    <h3 id="dvzSettingsHeading">⚙️ הגדרות עורך הגרפים</h3>
    <button type="button" class="btn-sm" onclick="document.getElementById('dvzSettings').close()">✕ סגור</button>
  </div>
  <h4>🔔 התראות על רינדור</h4>
  <p class="hint">כשרינדור של עורך הגרפים מסתיים או נכשל נשלחת הודעה ל-Discord (בנוסף להתראה באפליקציה). הכתובת נשמרת כסוד במחשב ולא מוצגת שוב.</p>
  <p id="dvzNotifyState"></p>
  <div class="tc-row"><label class="u-flex-0" for="dvzNotifyUrl">Webhook:</label><input id="dvzNotifyUrl" type="password" dir="ltr" autocomplete="off" placeholder="https://discord.com/api/webhooks/..."></div>
  <div class="tc-row"><button type="button" class="btn-sm btn-primary" id="dvzNotifySaveBtn" onclick="dvzSaveNotify(false)">💾 שמור</button>
    <button type="button" class="btn-sm" id="dvzNotifyTestBtn" onclick="dvzTestNotify()">🔔 שלח בדיקה</button>
    <button type="button" class="btn-sm" id="dvzNotifyClearBtn" onclick="dvzSaveNotify(true)">✕ בטל התראות</button></div>
  <div class="hint u-block" id="dvzNotifyMsg" role="status" aria-live="polite"></div>
  <h4>👁 תיקייה במעקב</h4>
  <p class="hint">תיקייה חדשה בתוך השורש -> טיוטת פרק, דוח תמונות והתראה (Discord אם הוגדר). השורש רק נקרא; אין רינדור מלא בלי אישור. התיקיות שכבר שם לא נכנסות.</p>
  <div class="tc-row"><label><input type="checkbox" id="dvzWatchOn"> מופעל</label>
    <label class="u-flex-0" for="dvzWatchRoot">שורש:</label><input id="dvzWatchRoot" dir="ltr"></div>
  <div class="tc-row"><label class="u-flex-0" for="dvzWatchEvery">כל כמה דקות:</label><input id="dvzWatchEvery" type="number" min="5" max="1440" value="30">
    <label class="u-flex-0" for="dvzWatchKit">ערכת ערוץ:</label><select id="dvzWatchKit"></select></div>
  <div class="tc-row"><button type="button" class="btn-sm btn-primary" id="dvzWatchSaveBtn" onclick="dvzSaveWatch()">💾 שמור</button>
    <button type="button" class="btn-sm" id="dvzWatchCheckBtn" onclick="dvzCheckWatch()">🔍 בדוק עכשיו</button></div>
  <div id="dvzWatchLog"></div>
  <h4>🧠 העדפות שנלמדו</h4>
  <p class="hint">כשמחליפים בחירה אוטומטית (תרשים, מספר ישויות, ערכת צבעים) - הטיוטה הבאה של אותה ערכת ערוץ תשתמש בה.</p>
  <div id="dvzPrefs"></div>
  <div class="hint u-block" id="dvzSmartSettingsMsg" role="status" aria-live="polite"></div>
</dialog>`);
}

async function dvzOpenSettings() {
  _dvzSettingsDialog();
  const dialog = document.getElementById("dvzSettings");
  if (dialog.closest("[hidden]")) document.body.append(dialog);   // נפתח גם מ"🌐 הגדרות כלליות", כשמסך עורך הגרפים מוסתר
  if (!dialog.open) dialog.showModal();
  document.getElementById("dvzNotifyMsg").textContent = "";
  document.getElementById("dvzSmartSettingsMsg").textContent = "";
  const [notify] = await Promise.all([fetch("/api/dataviz/notify").then(_dvzJson), _dvzLoadSmartSettings()]);
  _dvzShowNotify(notify);
}

function _dvzShowNotify(data) {
  document.getElementById("dvzNotifyState").textContent = data.configured ? `✅ מוגדר (${data.hint})` : "לא מוגדר - אין הודעות ל-Discord.";
  document.getElementById("dvzNotifyTestBtn").disabled = !data.configured;
  document.getElementById("dvzNotifyClearBtn").disabled = !data.configured;
}

async function dvzSaveNotify(clear) {
  const msg = document.getElementById("dvzNotifyMsg");
  const input = document.getElementById("dvzNotifyUrl");
  try {
    const resp = await fetch("/api/dataviz/notify", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({url: clear ? "" : input.value.trim()})});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "השמירה נכשלה");
    input.value = "";
    _dvzShowNotify(data);
    msg.textContent = clear ? "ההתראות בוטלו." : "נשמר.";
  } catch (e) {
    msg.textContent = "שגיאה: " + e.message;
  }
}

async function dvzTestNotify() {
  const msg = document.getElementById("dvzNotifyMsg");
  const resp = await fetch("/api/dataviz/notify/test", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
  const data = await _dvzJson(resp);
  msg.textContent = resp.ok ? "✅ נשלחה הודעת בדיקה." : "שגיאה: " + (data.error || "השליחה נכשלה");
}

// --- 20.10.2026: עורך הגרפים החכם - תיקיית נתונים -> פרק עם טיוטה מוכנה (dataviz/smart/create.py; היצירה מ"➕ פרק חדש" ->
// "📂 מתיקייה", 87-dataviz-shell.js). 21.10.2026 (סבב הפישוט): מסך סקירה אחד - כרטיס לכל בחירה 🤖 עם "✓ מאשר" / "✏️ שנה" /
// "↺ בטל", מה שנקרא מהקבצים מקופל, שאלה אחת כשהביטחון נמוך, והצעות לאירועים רק בלחיצה (לטיוטה, לא נשמרות) ---
function _dvzSmartDialogs() {
  if (document.getElementById("dvzSmartPanel")) return;
  document.getElementById("dvzNewDialog").insertAdjacentHTML("afterend", `<dialog id="dvzSmartPanel" class="dvz-dialog" aria-labelledby="dvzSmartPanelHeading">
  <div class="tc-row dvz-dialog-head">
    <h3 id="dvzSmartPanelHeading">🤖 סקירת הטיוטה</h3>
    <button type="button" class="btn-sm" onclick="document.getElementById('dvzSmartPanel').close()">✕ סגור</button>
  </div>
  <p class="hint" id="dvzSmartSummary"></p>
  <div id="dvzSmartQuestion"></div>
  <div id="dvzSmartChoices" class="dvz-review"></div>
  <div id="dvzSmartEvents"></div>
  <div class="tc-row dvz-review-foot">
    <button type="button" class="btn-sm" id="dvzSmartAcceptAll" onclick="_dvzSmartAccept('')">✓ מאשר הכל</button>
    <button type="button" class="btn-sm btn-primary" id="dvzSmartToRun" onclick="dvzSmartToRun()">▶ לרינדור</button>
  </div>
  <div class="hint u-block" id="dvzSmartPanelMsg" role="status" aria-live="polite"></div>
</dialog>`);
}

function _dvzKitOptions(select, kits, current) {
  select.replaceChildren(new Option("בלי", ""), ...kits.map(k => new Option(k, k)));
  select.value = current || "";
}

async function dvzOpenSmartPanel() {
  if (!dvzState.selected) return;
  const data = await _dvzJson(await fetch("/api/dataviz/smart/record?episode=" + encodeURIComponent(dvzState.selected)));
  if (!data.episode) { uiToast("הפרק הזה לא נוצר מתיקייה - אין בחירות אוטומטיות", "info"); return; }
  _dvzShowSmart(data);
}

function _dvzSmartValue(value) {
  if (Array.isArray(value)) return `${value.length} פריטים`;
  if (typeof value === "boolean") return value ? "כן" : "לא";
  if (value !== null && typeof value === "object") return Object.values(value).filter(v => typeof v !== "object").join(" · ").slice(0, 60);
  const option = document.querySelector(`#dvzChart option[value="${CSS.escape(String(value))}"]`);   // שם התרשים בעברית
  return option && value ? option.textContent : String(value).slice(0, 80);
}

function _dvzReviewCard(c) {
  const card = _dvzEdEl("div", "dvz-review-card" + (c.undone ? " is-undone" : c.accepted ? " is-ok" : c.confidence < 0.65 ? " is-low" : ""));
  card.dataset.path = c.path;
  const head = _dvzEdEl("div", "dvz-review-head");
  head.append(_dvzEdEl("strong", "", c.label), _dvzEdEl("span", "dvz-review-value", _dvzSmartValue(c.value)),
    _dvzEdEl("span", "dvz-chip", Math.round(c.confidence * 100) + "%"));
  card.append(head, _dvzEdEl("div", "hint", c.reason));
  const actions = _dvzEdEl("div", "dvz-review-actions");
  const button = (text, onclick, cls) => {
    const b = _dvzEdEl("button", "btn-xs" + (cls ? " " + cls : ""), text);
    b.type = "button";
    b.onclick = onclick;
    actions.append(b);
  };
  if (c.undone) {
    actions.append(_dvzEdEl("span", "hint", "בוטל - לפי הקובץ או ברירת המחדל"));
  } else {
    if (c.accepted) actions.append(_dvzEdEl("span", "dvz-chip is-ok", "✓ אושר"));
    else button("✓ מאשר", () => _dvzSmartAccept(c.path), "btn-primary");
    button("✏️ שנה", () => { document.getElementById("dvzSmartPanel").close(); dvzEditField(c.path); });
    button("↺ בטל", () => _dvzSmartUndo(c.path));
  }
  card.append(actions);
  return card;
}

function _dvzShowSmart(record) {
  _dvzSmartDialogs();
  const dialog = document.getElementById("dvzSmartPanel");
  if (!dialog.open) dialog.showModal();
  const auto = (record.choices || []).filter(c => c.where === "override");
  const read = (record.choices || []).filter(c => c.where !== "override");
  const open = auto.filter(c => !c.undone && !c.accepted).length;
  document.getElementById("dvzSmartSummary").textContent = `${auto.length} בחירות של העורך - ${open} מחכות לאישור. כל שינוי מופיע מיד בתצוגה החיה.`;
  document.getElementById("dvzSmartAcceptAll").disabled = !open;
  document.getElementById("dvzSmartPanelMsg").textContent = (record.skipped || []).length ? `${record.skipped.length} בחירות לא נכנסו (לא עברו בדיקה)` : "";
  // השאלה האחת
  const q = record.question;
  const qBox = document.getElementById("dvzSmartQuestion");
  qBox.replaceChildren();
  if (q && !q.answered) {
    const card = _dvzEdEl("div", "dvz-finding is-warn");
    card.append(_dvzEdEl("strong", "", "❓ " + q.question), _dvzEdEl("div", "hint", q.reason));
    for (const option of q.options) {
      const b = _dvzEdEl("button", "btn-sm" + (option.value === q.current ? " btn-primary" : ""), option.label);
      b.type = "button";
      b.dataset.answer = option.value;
      b.onclick = () => _dvzSmartAnswer(option.value);
      card.append(b);
    }
    qBox.append(card);
  }
  // הבחירות: כרטיס לכל 🤖, ומה שנקרא מהקבצים (📄) מקופל
  const box = document.getElementById("dvzSmartChoices");
  box.replaceChildren(...auto.map(_dvzReviewCard));
  if (read.length) {
    const details = _dvzEdEl("details", "dvz-review-read");
    details.append(_dvzEdEl("summary", "", `📄 מה נקרא מהקבצים (${read.length})`),
      ...read.map(c => _dvzEdEl("div", "hint", `${c.label}: ${_dvzSmartValue(c.value)} - ${c.reason}`)));
    box.append(details);
  }
  // הצעות לאירועים - רק בלחיצה, לטיוטה
  const events = (record.events || {}).suggestions || [];
  const evBox = document.getElementById("dvzSmartEvents");
  evBox.replaceChildren();
  if (events.length) {
    evBox.append(_dvzEdEl("h4", "", "הצעות לאירועים (צריכות אישור)"));
    for (const ev of events) {
      const row = _dvzEdEl("div", "tc-row");
      const add = _dvzEdEl("button", "btn-sm", "➕ הוסף");
      add.type = "button";
      add.onclick = () => {
        const current = Array.isArray(dvzEd.draft.events) ? dvzEd.draft.events : (Array.isArray(dvzEd.data.events) ? dvzEd.data.events : []);
        _dvzStage("events", [...current, {date: ev.date, label: ev.label}]);
        add.disabled = true;
        add.textContent = "✅ בטיוטה";
      };
      row.append(add, _dvzEdEl("span", "", `${ev.date} - ${ev.label}`), _dvzEdEl("span", "hint", `(${ev.source}; ליד: ${ev.moment_text})`));
      evBox.append(row);
    }
  }
  _dvzOnboardHint(2);   // ההיכרות של הפעם הראשונה (87-dataviz-shell.js)
}

async function _dvzSmartPost(action, body) {
  const resp = await fetch("/api/dataviz/smart/" + action, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({episode: dvzState.selected, ...body})});
  const data = await _dvzJson(resp);
  if (!resp.ok) { document.getElementById("dvzSmartPanelMsg").textContent = "שגיאה: " + (data.error || ""); return false; }
  return true;
}

// אישור לא משנה את הפרק - רק מסמן ברשומה שהבחירה נבדקה (path ריק = כל מה שעוד פתוח)
async function _dvzSmartAccept(path) {
  if (await _dvzSmartPost("accept", {path})) await dvzOpenSmartPanel();
}

async function _dvzSmartUndo(path) {
  if (!await _dvzSmartPost("undo", {path})) return;
  await dvzLoadEditor();
  dvzPreviewSoon();
  await dvzOpenSmartPanel();
}

async function _dvzSmartAnswer(value) {
  if (!await _dvzSmartPost("answer", {value})) return;
  await dvzLoadEditor();
  dvzPreviewSoon();
  await dvzOpenSmartPanel();
}

// "▶ לרינדור": הסקירה נסגרת ונפתחת הרשימה "✅ לפני רינדור" (ובה "▶ הרץ") - תיקייה -> סקירה -> רינדור
function dvzSmartToRun() {
  document.getElementById("dvzSmartPanel").close();
  dvzOnboardNext(3);
  dvzOpenPrerender();
}

// --- 20.10.2026: תיקייה במעקב (פריט 15) והעדפות שנלמדו (פריט 16) - בחלון "⚙️ הגדרות עורך הגרפים" ---
async function _dvzLoadSmartSettings() {
  _dvzShowSmartSettings(await _dvzJson(await fetch("/api/dataviz/smart/settings")));
}

function _dvzShowSmartSettings(data) {
  const watch = data.watch || {};
  document.getElementById("dvzWatchOn").checked = !!watch.enabled;
  document.getElementById("dvzWatchRoot").value = watch.root || "";
  document.getElementById("dvzWatchEvery").value = watch.interval_minutes || 30;
  _dvzKitOptions(document.getElementById("dvzWatchKit"), data.kits || [], watch.kit);
  _dvzShowWatchLog(watch);
  const box = document.getElementById("dvzPrefs");
  const scopes = Object.entries(data.prefs || {});
  if (!scopes.length) { box.replaceChildren(_dvzEdEl("p", "hint", "עוד לא נלמד כלום.")); return; }
  box.replaceChildren(...scopes.map(([scope, prefs]) => {
    const row = _dvzEdEl("div", "tc-row");
    row.dataset.scope = scope;
    const items = Object.entries(prefs).map(([key, value]) => key === "chart"
      ? Object.entries(value).map(([from, to]) => `${from} -> ${to}`).join(", ") : `${key}: ${value}`);
    const reset = _dvzEdEl("button", "btn-sm", "↺ אפס");
    reset.type = "button";
    reset.onclick = async () => {
      await fetch("/api/dataviz/smart/prefs_reset", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({scope})});
      await _dvzLoadSmartSettings();
    };
    row.append(_dvzEdEl("strong", "", scope === "default" ? "בלי ערכה" : scope), _dvzEdEl("span", "", items.join(" · ")), reset);
    return row;
  }));
}

function _dvzShowWatchLog(watch) {
  const log = document.getElementById("dvzWatchLog");
  const lines = (watch.log || []).slice(0, 8).map(e => _dvzEdEl("div", "hint", `${e.time} - ${e.folder}: ` + (e.episode ? `✅ ${e.episode}` : `❌ ${e.error || ""}`)));
  const pending = (watch.pending || []).length ? [_dvzEdEl("div", "hint", `ממתינות: ${watch.pending.join(", ")}`)] : [];
  log.replaceChildren(...pending, ...lines);
}

async function dvzSaveWatch() {
  const msg = document.getElementById("dvzSmartSettingsMsg");
  try {
    const resp = await fetch("/api/dataviz/smart/watch", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({enabled: document.getElementById("dvzWatchOn").checked, root: document.getElementById("dvzWatchRoot").value.trim(),
        interval_minutes: Number(document.getElementById("dvzWatchEvery").value), kit: document.getElementById("dvzWatchKit").value})});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "השמירה נכשלה");
    _dvzShowWatchLog(data);
    msg.textContent = data.enabled ? `✅ במעקב - ${data.seen} תיקיות קיימות לא ייכנסו` : "המעקב כבוי.";
  } catch (e) {
    msg.textContent = "שגיאה: " + e.message;
  }
}

async function dvzCheckWatch() {
  const msg = document.getElementById("dvzSmartSettingsMsg");
  msg.textContent = "⏳";
  const resp = await fetch("/api/dataviz/smart/watch_check", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
  const data = await _dvzJson(resp);
  if (!resp.ok) { msg.textContent = "שגיאה: " + (data.error || ""); return; }
  _dvzShowWatchLog(data);
  msg.textContent = (data.done || []).length ? `${data.done.length} טיוטות חדשות` : "אין תיקיות חדשות.";
  if ((data.done || []).length) await loadDataviz();
}
