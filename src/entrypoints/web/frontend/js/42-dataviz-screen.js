// --- מסך "סרטוני נתונים": פרקים, הרצה, התקדמות, תוצרים ופרק חדש מ-CSV ---
const DVZ_MODE_HINTS = {
  stills: "מפיק כמה פריימים בודדים (PNG) כדי לבדוק עיצוב - הכי מהיר.",
  preview: "תצוגה מקדימה של 5 שניות בחצי רזולוציה - לראות איך זה זז.",
  test: "סרטון קצר של כ-7 שניות ברזולוציה מלאה.",
  full: "הסרטון המלא. יכול לקחת זמן רב, ותופס את תור הרינדור.",
  share: "תמונה ו-GIF קצר מהרגע החזק בסרטון (היום עם התוספת הגדולה ביותר) - לשיתוף ברשתות.",
  shorts: "הרגעים הדרמטיים של הפרק (הקפיצה הגדולה, החלפת מוביל) כסרטונים קצרים לאורך - Shorts מוכנים.",   // גל 55
};
const DVZ_MODE_LABELS = { stills: "פריימים", preview: "תצוגה מקדימה", test: "בדיקה", full: "מלא", share: "שיתוף", shorts: "Shorts" };
const DVZ_CHART_LABELS = { bar_race: "מרוץ עמודות", line_race: "מרוץ קווים", stacked_area_race: "שטח מוערם", scatter_race: "פיזור", bump_race: "גרף דירוגים", heatmap_race: "מפת חום", map_race: "מפה", pie_race: "עוגה", small_multiples: "גרפים קטנים" };
let dvzState = { episodes: [], selected: "", running: false, showAll: false, showHidden: false, meta: {}, estimates: {} };

function _dvzJson(res) { return res.json().catch(() => ({})); }

// 23.10.2026: תשובת שגיאה (500 בלי JSON) הפכה ל-{} - והמסך הראה "אין פרקים" / "הסל ריק" / "עוד אין גרסאות" במקום שגיאה
async function _dvzJsonOk(res) {
  const data = await _dvzJson(res);
  if (!res.ok) throw new Error(data.error || "HTTP " + res.status);
  return data;
}

async function loadDataviz() {
  const list = document.getElementById("dvzEpisodes");
  uiSkeleton(list, 2, "row");
  const request = uiLatest("dvz:episodes");   // 23.10.2026: תשובה ישנה לא דורסת חדשה (פרק שנוצר עכשיו נעלם, והבחירה קפצה)
  try {
    const data = await _dvzJsonOk(await fetch("/api/dataviz/episodes" + (dvzState.showHidden ? "?show_hidden=1" : ""), {signal: request.signal}));
    if (!request.current()) return;
    dvzState.episodes = data.episodes || [];
    document.getElementById("dvzIntroHint").hidden = dvzState.episodes.length > 0;   // גל 59: ההסבר רק כשאין פרקים
    document.getElementById("dvzHiddenCount").textContent = data.hidden_count ? `(${data.hidden_count})` : "";
    await _dvzLoadEpisodeMeta();   // גל 38: ריצה אחרונה וסטטוס פרסום לכל פרק (43-dataviz-studio.js)
    if (!request.current()) return;
    for (const name of [...dvzState.queue]) if (!dvzState.episodes.some(ep => ep.name === name && ep.valid)) dvzState.queue.delete(name);
    dvzRenderEpisodes();
    _dvzSyncQueueBar();   // גל 41: תור של כמה פרקים ותבנית לפרק חדש (86-dataviz-publish.js)
    _dvzFillTemplates();
    // 23.10.2026: פרק מ"נפתחו לאחרונה" (65-ui-shell.js). הפרק הראשון שנבחר לבד כשנכנסים למסך לא נרשם שם
    const asked = dvzOpenRequest;
    dvzOpenRequest = "";
    if (asked && asked !== dvzState.selected) {
      if (!dvzState.episodes.some(ep => ep.name === asked)) uiToast("הפרק כבר לא קיים", "warn");
      else if (await _dvzLeaveDraftOk()) dvzState.selected = asked;
    }
    const chosen = dvzState.episodes.some(ep => ep.name === dvzState.selected);
    if (!chosen) {
      const first = dvzState.episodes.find(ep => ep.valid);
      dvzState.selected = first ? first.name : "";
    }
    _dvzApplySelection(chosen);
    _dvzSetupSplitters();
    dvzMaybeOnboard();   // 21.10.2026: ההיכרות בפעם הראשונה (88-dataviz-simple.js)
    await loadDatavizOutputs();
  } catch (e) {
    if (uiIsAbort(e) || !request.current()) return;
    list.innerHTML = '<div class="empty-msg bad">שגיאה בטעינת הפרקים.</div>';
  }
}

function _dvzEpisodeWrap(ep) {
  const wrap = document.createElement("div");
  wrap.className = "dvz-card-wrap";
  wrap.appendChild(_dvzEpisodeCard(ep));
  const tools = document.createElement("div");   // גל 59: שורה אחת שמופיעה בריחוף / בפוקוס
  tools.className = "dvz-card-tools";
  const hide = document.createElement("button");
  hide.type = "button";
  hide.className = "btn-xs btn-ghost dvz-hide-btn";
  hide.dataset.hideFor = ep.name;
  hide.textContent = ep.hidden ? "👁️ החזר לרשימה" : "🙈 הסתר";
  hide.title = "הפרק לא נמחק ולא זז - רק מוסתר מהרשימה, ואפשר להחזיר אותו";
  hide.onclick = () => dvzHideEpisode(ep.name, !ep.hidden);
  if (ep.valid && !ep.hidden) tools.appendChild(_dvzQueueCheckbox(ep));   // גל 41
  if (ep.valid) tools.appendChild(_dvzTagEditButton(ep));   // גל 53: תגיות ותיקייה (44-dataviz-editor.js)
  tools.appendChild(hide);
  tools.appendChild(_dvzDeleteButton(ep));   // 20.10.2026 (87-dataviz-shell.js)
  wrap.appendChild(tools);
  if (ep.hidden) wrap.classList.add("is-hidden");
  return wrap;
}

async function dvzHideEpisode(name, hidden) {
  try {
    const resp = await fetch("/api/dataviz/episodes/hide", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ episode: name, hidden }) });
    if (!resp.ok) throw new Error((await _dvzJson(resp)).error || "הפעולה נכשלה");
    await loadDataviz();
  } catch (e) {
    _dvzSetStatus("שגיאה: " + e.message, true);
  }
}

function dvzToggleHidden(checked) {
  dvzState.showHidden = checked;
  loadDataviz();
}

function _dvzEpisodeCard(ep) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "dvz-card";
  card.dataset.episode = ep.name;
  card.disabled = !ep.valid;
  const title = document.createElement("div");
  title.className = "dvz-card-title";
  title.textContent = ep.title || ep.name;
  const meta = document.createElement("div");
  meta.className = "dvz-card-meta";
  if (ep.valid) {
    const ltr = (text) => { const span = document.createElement("span"); span.dir = "ltr"; span.textContent = text; return span; };
    // כל תווית בצומת טקסט משלה - המתרגם (uiTranslate) לא תרגם את "מרוץ עמודות · כהה ·" כשהיו בצומת אחד
    meta.append(ltr(ep.name), " · ", DVZ_CHART_LABELS[ep.chart] || ep.chart, " · ", ep.theme === "dark" ? "כהה" : "בהיר", " · ", ltr(`${ep.width}×${ep.height}`));
  } else {
    meta.textContent = "⚠️ ההגדרות לא תקינות:" + " " + (ep.errors || []).join("; ");
    meta.classList.add("bad");
  }
  if (ep.valid) card.appendChild(_dvzCardThumb(ep));   // גל 38: תמונה מהסרטון, סוג תרשים, ריצה אחרונה וסטטוס פרסום
  card.appendChild(title);
  card.appendChild(meta);
  card.appendChild(_dvzCardBadges(ep));
  card.onclick = async () => {
    if (ep.name !== dvzState.selected && !(await _dvzLeaveDraftOk())) return;   // 23.10.2026 (44-dataviz-editor.js)
    dvzState.selected = ep.name;
    _dvzApplySelection();
    loadDatavizOutputs();
  };
  return card;
}

function _dvzApplySelection(remember = true) {
  for (const card of document.querySelectorAll("#dvzEpisodes .dvz-card")) {
    const on = card.dataset.episode === dvzState.selected;
    card.classList.toggle("selected", on);
    card.setAttribute("aria-pressed", on ? "true" : "false");
  }
  const ep = dvzState.episodes.find(e => e.name === dvzState.selected);
  if (dvzState.runOptionsFor !== dvzState.selected) {   // 23.10.2026: "שינויים להרצה הזו" לא עוברים לפרק אחר (ובמצב פשוט הם מוסתרים)
    dvzState.runOptionsFor = dvzState.selected;
    for (const [id, value] of [["dvzChart", ""], ["dvzTarget", ""], ["dvzPublish", "default"]]) document.getElementById(id).value = value;
  }
  document.getElementById("dvzControls").hidden = !ep;
  document.getElementById("dvzRunGroup").hidden = !ep;   // גל 57: הרץ בסרגל העליון
  document.getElementById("dvzPreviewPane").hidden = !ep;
  document.getElementById("dvzTopbarEpisode").textContent = ep ? "· " + (ep.title || ep.name) : "";   // גל 56: הסרגל העליון
  if (ep) {
    document.getElementById("dvzSelectedTitle").textContent = "🎛️ " + (ep.title || ep.name);
    document.getElementById("dvzSelectedInfo").textContent = `${ep.name} · ${ep.sources} מקורות נתונים` + (ep.has_audio ? " · " + "עם מוזיקה" : "");
    if (remember) uiRecent.remember("dataviz", ep.name, ep.title || ep.name);
  }
  dvzModeChanged();
  dvzSelectionChanged(ep);   // גל 38: תצוגה חיה, רצועת פריימים ואומדן
  dvzLoadPackages();   // גל 41: חבילות הפרסום של הפרק
}

// גל 59: הטופס "הגדרות הפרק (עריכה)" יצא - אותם 8 שדות בקבוצה "⭐ בסיסי" בראש העורך המלא (dataviz/schema.py)

function dvzModeChanged() {
  document.getElementById("dvzModeHint").textContent = DVZ_MODE_HINTS[document.getElementById("dvzMode").value] || "";
  _dvzRenderEstimate();
}

function _dvzSetStatus(text, bad) {
  const el = document.getElementById("dvzStatus");
  el.textContent = text;
  el.title = text;   // גל 57: בסרגל העליון ההודעה מקוצרת - המלאה בריחוף
  el.classList.toggle("bad", !!bad);
}

function _dvzSetRunning(running) {
  dvzState.running = running;
  if (running) uiMarkRunOwner("dataviz", "📊 עורך הגרפים");   // גל 60: נראה גם מהסטודיו
  document.getElementById("dvzRunBtn").disabled = running;
  document.getElementById("dvzStopBtn").disabled = !running;
  uiBus.emit("dvz:running", running);   // 27.10.2026: מצב כרטיס המסך בזמן רינדור (85-dataviz-plus.js)
}

async function dvzRun() {
  if (!dvzState.selected) return;
  // 23.10.2026: הרינדור קורא רק את מה שנשמר - בלי זה הטיוטה (שהתצוגה החיה כן מציגה) נעלמה מהסרטון בלי מילה
  if (Object.keys(dvzEd.draft).length || dvzEd.unset.size) {
    if (!(await veConfirm("יש שינויים שלא נשמרו - הסרטון ירונדר בלעדיהם. לשמור אותם ולהריץ?", {okLabel: "💾 שמור והרץ"}))) return;
    await dvzSaveDraft();
    if (Object.keys(dvzEd.draft).length || dvzEd.unset.size) return;   // השמירה נכשלה - ההודעה כבר בעורך
  }
  const body = { episode: dvzState.selected, ..._dvzRunOptions() };   // גל 41: כולל היעד (YouTube / Shorts / TikTok)
  _dvzSetRunning(true);
  document.getElementById("dvzProgressBar").style.width = "0%";
  _dvzSetStatus("שולח לתור הרינדור...");
  try {
    const resp = await fetch("/api/dataviz/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "ההרצה נכשלה");
    _dvzSetStatus("רץ... אפשר לעקוב גם בלוג של מסך הסקריפטים.");
  } catch (e) {
    _dvzSetRunning(false);
    _dvzSetStatus("שגיאה: " + e.message, true);
  }
}

async function dvzStop() {
  try { await fetch("/api/stop", { method: "POST" }); } catch (e) { /* הסיום יגיע דרך ה-WebSocket */ }
}

document.addEventListener("cf-progress", (evt) => {
  if (!dvzState.running) return;
  const msg = evt.detail;
  document.getElementById("dvzProgressBar").style.width = msg.pct + "%";
  _dvzSetStatus(`מרנדר ${msg.pct}%` + (msg.eta && msg.pct < 100 ? ` · נותרו כ-${msg.eta}` : ""));
});

document.addEventListener("cf-finished", (evt) => {
  if (!dvzState.running) return;
  _dvzSetRunning(false);
  uiToast(evt.detail.success ? "📊 הרינדור הסתיים" : "📊 הרינדור נכשל", evt.detail.success ? "ok" : "error");   // 20.10.2026: גם כשמסתכלים על מסך אחר
  if (evt.detail.success) {
    document.getElementById("dvzProgressBar").style.width = "100%";
    _dvzSetStatus("✅ הסתיים בהצלחה - התוצרים למטה.");
  } else {
    _dvzSetStatus("❌ ההרצה נכשלה - פרטים בלוג של מסך הסקריפטים.", true);
  }
  loadDatavizOutputs();
  dvzLoadPackages();
});

function dvzToggleAll() {
  dvzState.showAll = !dvzState.showAll;
  loadDatavizOutputs();
}

async function loadDatavizOutputs() {
  const box = document.getElementById("dvzOutputs");
  const query = dvzState.showAll || !dvzState.selected ? "" : "?episode=" + encodeURIComponent(dvzState.selected);
  document.getElementById("dvzShowAllBtn").textContent = dvzState.showAll ? "🔎 רק של הפרק שנבחר" : "🔎 הצג את כל התוצרים";
  const request = uiLatest("dvz:outputs");   // רק הבקשה האחרונה מציירת - כניסה למסך ולחיצה על פרק יוצאות כמעט יחד
  try {
    const data = await _dvzJsonOk(await fetch("/api/dataviz/outputs" + query, {signal: request.signal}));
    if (!request.current()) return;
    dvzState.folders = data.folders || {};
    _dvzShowSavedTo(data.save_to);
    box.innerHTML = "";
    const outputs = (data.outputs || []).slice(0, 12);
    if (!outputs.length) {
      box.innerHTML = '<div class="empty-msg">אין עדיין תוצרים. בחר מה להפיק ולחץ "הרץ".</div>';
      return;
    }
    for (const out of outputs) box.appendChild(_dvzOutputCard(out));
  } catch (e) {
    if (uiIsAbort(e) || !request.current()) return;
    box.innerHTML = '<div class="empty-msg bad">שגיאה בטעינת התוצרים.</div>';
  }
}

function _dvzMediaUrl(out, ...parts) {
  return "/api/dataviz/media/" + [out.orientation, ...parts].map(encodeURIComponent).join("/");
}

function _dvzOutputCard(out) {
  const card = document.createElement("div");
  card.className = "dvz-output";
  card.dataset.kind = out.kind;
  card.dataset.name = out.name;
  const head = document.createElement("div");
  head.className = "dvz-output-head";
  const name = document.createElement("span");
  name.className = "dvz-output-name";
  name.textContent = out.name;
  const badge = document.createElement("span");
  badge.className = "badge";
  badge.textContent = DVZ_MODE_LABELS[out.mode] || out.mode;
  const when = document.createElement("span");
  when.className = "hint";
  when.textContent = new Date(out.mtime * 1000).toLocaleString("he-IL");
  head.appendChild(name);
  head.appendChild(badge);
  head.appendChild(when);
  card.appendChild(head);

  const actions = document.createElement("div");
  actions.className = "tc-row";
  if (out.kind === "video") {
    const video = document.createElement("video");
    video.controls = true;
    video.preload = "metadata";
    video.className = "dvz-video";
    video.src = _dvzMediaUrl(out, out.name);
    card.appendChild(video);
    const link = document.createElement("a");
    link.className = "btn-sm btn-outline dvz-link";
    link.href = _dvzMediaUrl(out, out.name) + "?download=1";
    link.textContent = "⬇️ הורד";
    actions.appendChild(link);
    if (out.has_package) {
      const pkg = document.createElement("button");
      pkg.type = "button";
      pkg.className = "btn-sm btn-outline";
      pkg.textContent = "📦 חבילת פרסום ואישור";
      pkg.onclick = () => switchTab("approvals");
      actions.appendChild(pkg);
    }
  } else {
    const grid = document.createElement("div");
    grid.className = "dvz-stills";
    for (const file of out.files) {
      const a = document.createElement("a");
      a.href = _dvzMediaUrl(out, out.name, file);
      a.target = "_blank";
      a.rel = "noopener";
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = a.href;
      img.alt = file;
      a.appendChild(img);
      grid.appendChild(a);
    }
    card.appendChild(grid);
  }
  const open = document.createElement("button");
  open.type = "button";
  open.className = "btn-sm btn-outline";
  open.textContent = "📂 פתח תיקייה";
  open.onclick = () => dvzOpenFolder(out.orientation, out.folder);
  actions.appendChild(open);
  _dvzOutputExtras(out, card, actions);   // גל 41: השוואה וסל מיחזור
  card.appendChild(actions);
  return card;
}

// 23.10.2026 (תיקיית הייצוא): לאן נכתבים תוצרים חדשים עכשיו, ואזהרה כשתיקיית הייצוא שבהגדרות לא זמינה (התוצרים הולכים ל-workspace)
function _dvzShowSavedTo(saveTo) {
  const line = document.getElementById("dvzSavedTo");
  if (!line) return;
  line.hidden = !saveTo || !saveTo.folder;
  if (line.hidden) return;
  line.replaceChildren(Object.assign(document.createElement("span"), {textContent: `💾 נשמר ב-${saveTo.folder}`}));
  if (saveTo.problem) {
    const warn = Object.assign(document.createElement("span"), {className: "dvz-saved-problem", textContent: "⚠️ תיקיית הייצוא לא זמינה עכשיו, אז התוצרים נשמרים ב-workspace"});
    warn.title = `${saveTo.problem} · ${saveTo.root || ""}`;
    line.appendChild(warn);
  }
}

// folder: התיקייה שבה התוצר נמצא (תיקיית הייצוא או workspace); בלי - התיקייה הראשונה של הכיוון
async function dvzOpenFolder(orientation, folder) {
  const path = folder || (dvzState.folders || {})[orientation];
  if (!path) return;
  try {
    const resp = await fetch("/api/open_folder", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) });
    if (!resp.ok) _dvzSetStatus("שגיאה: " + ((await _dvzJson(resp)).error || "פתיחת התיקייה נכשלה"), true);
  } catch (e) {
    _dvzSetStatus("שגיאה: " + e.message, true);
  }
}

// 23.10.2026 (המלצה 8): "✏️ עריכה" - עורך רחב (רשימת הפרקים מתקפלת, ההגדרות מקבלות את רוב הרוחב והעורך נפתח); "👁 צפייה" - רק
// התצוגה החיה, ברוחב מלא וגבוהה יותר. לחיצה נוספת על אותו כפתור מחזירה לפריסה הרגילה. הבחירה נשמרת בדפדפן (17-dataviz.css)
const DVZ_LAYOUTS = ["edit", "view"];

function dvzSetLayout(layout) {
  const studio = document.querySelector(".dvz-studio");
  if (!studio) return;
  const next = DVZ_LAYOUTS.includes(layout) && studio.dataset.layout !== layout ? layout : "";
  _dvzApplyLayout(next);
  try { localStorage.setItem("dvzLayout", next); } catch (e) { /* רק לטעינה הזו */ }
  const editor = document.getElementById("dvzEditor");
  if (next === "edit" && dvzState.selected && editor && !editor.open) editor.open = true;   // ontoggle טוען את העורך
}

function _dvzApplyLayout(layout) {
  const studio = document.querySelector(".dvz-studio");
  if (!studio) return;
  if (layout) studio.dataset.layout = layout;
  else delete studio.dataset.layout;
  for (const [key, id] of [["edit", "dvzLayoutEditBtn"], ["view", "dvzLayoutViewBtn"]]) {
    const btn = document.getElementById(id);
    if (btn) btn.setAttribute("aria-pressed", String(key === layout));
  }
}

function _dvzRestoreLayout() {
  let layout = "";
  try { layout = localStorage.getItem("dvzLayout") || ""; } catch (e) { /* בלי אחסון - הפריסה הרגילה */ }
  _dvzApplyLayout(DVZ_LAYOUTS.includes(layout) ? layout : "");
}

_dvzRestoreLayout();

// 23.10.2026 (המלצה 7): גבולות נגררים בין העמודות - uiSplitter המשותף (35-ui-frame.js, uiLoadLazy("frame")). הרוחב נכתב
// למשתנה CSS על .dvz-studio ונשמר לכל עמודה (17-dataviz.css, 27-dataviz-pro.css): "normal" - העורך סגור, "editor" - העורך
// המלא או חלון הנתונים פתוחים. כאן רק המיקום: המפריד באמצע הרווח שבין העמודה לתצוגה החיה, ומוסתר כשהן לא זו לצד זו
const DVZ_SPLITTERS = [
  {when: "any", pane: ".dvz-episodes-pane", cssVar: "--dvz-episodes-w", key: "dvzEpisodesW", min: 200, max: 480, edge: "start", label: "רוחב רשימת הפרקים"},
  {when: "normal", pane: ".dvz-settings-pane", cssVar: "--dvz-settings-w", key: "dvzSettingsW", min: 260, max: 720, edge: "end", label: "רוחב עמודת ההגדרות"},
  {when: "editor", pane: ".dvz-settings-pane", cssVar: "--dvz-editor-w", key: "dvzEditorW", min: 420, max: 1100, edge: "end", label: "רוחב העורך"},
];

async function _dvzSetupSplitters() {
  const studio = document.querySelector(".dvz-studio");
  if (!studio || studio.dataset.splitters) return;
  studio.dataset.splitters = "1";
  try {
    await uiLoadLazy("frame");
  } catch (e) {
    delete studio.dataset.splitters;   // בכניסה הבאה למסך
    return;
  }
  for (const s of DVZ_SPLITTERS) {
    const handle = document.createElement("div");
    handle.className = "dvz-splitter";
    Object.assign(handle.dataset, {when: s.when, pane: s.pane});
    studio.appendChild(handle);
    uiSplitter(handle, {...s, panel: studio.querySelector(s.pane), target: studio, onChange: _dvzPlaceSplitters});
  }
  const observer = new ResizeObserver(_dvzPlaceSplitters);
  for (const el of [studio, ...studio.querySelectorAll(":scope > .dvz-pane")]) observer.observe(el);
}

function _dvzPlaceSplitters() {
  const studio = document.querySelector(".dvz-studio");
  const middle = document.getElementById("dvzPreviewPane").getBoundingClientRect();
  const box = studio.getBoundingClientRect();
  for (const handle of studio.querySelectorAll(":scope > .dvz-splitter")) {
    const pane = studio.querySelector(handle.dataset.pane).getBoundingClientRect();
    handle.hidden = !pane.width || !middle.width || Math.abs(pane.top - middle.top) > 2;   // מסך צר: אחת מתחת לשנייה
    if (!handle.hidden) handle.style.left = `${(pane.left > middle.left ? pane.left + middle.right : pane.right + middle.left) / 2 - box.left - 6}px`;
  }
}

// --- פרק חדש מ-CSV (נוצר רק בשם חדש - פרק קיים לא נדרס) ---
let _dvzCsvText = "";
let _dvzCsvName = "";   // 19.10.2026: השם המקורי של הקובץ - כך הוא נשמר בתיקיית הפרק
let _dvzExtraFiles = [];   // 18.10.2026: קבצים נוספים לפרק חדש - כל אחד מקור משלו: [{name, csv, columns, mapping}]

async function dvzCsvChosen(input) {
  const files = [...(input.files || [])];
  await dvzTableFile(files[0]);
  if (_dvzCsvText && files.length > 1) await _dvzAddExtraFiles(files.slice(1));
  await _dvzSmartGuess();
}

// 23.10.2026 (המלצה 5 מסיור השימושיות): הניחוש של העורך החכם - כמות / רמה וציר לכל קובץ, סוג התרשים וכותרת - בטופס
// "מקבצים" (קודם: 6 תיקונים ביד, כשהעורך החכם כבר ידע). רק בשדות שהמשתמש לא נגע בהם; בלי ניחוש - הטופס כמו קודם
function _dvzWatchTouched() {
  const dialog = document.getElementById("dvzNewDialog");
  if (!dialog || dialog.dataset.touchWatch) return;
  dialog.dataset.touchWatch = "1";
  const mark = (e) => { if (e.target.matches("input, select, textarea")) e.target.dataset.touched = "1"; };   // השמה מהקוד (el.value =) לא שולחת אירוע
  dialog.addEventListener("input", mark);
  dialog.addEventListener("change", mark);
}

async function _dvzSmartGuess() {
  _dvzWatchTouched();
  if (!_dvzCsvText) return;
  const files = [{filename: _dvzCsvName, csv_text: _dvzCsvText}, ..._dvzExtraFiles.map(extra => ({filename: extra.name, csv_text: extra.csv}))];
  const latest = uiLatest("dvz:smart-guess");
  let guess;
  try {
    const resp = await fetch("/api/dataviz/episodes/smart_guess", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({files}), signal: latest.signal});
    guess = await _dvzJson(resp);
    if (!resp.ok) return;
  } catch (e) {
    return;   // ניחוש הוא תוספת
  }
  if (!latest.current() || files[0].csv_text !== _dvzCsvText) return;
  const put = (el, value) => { if (el && value && !el.dataset.touched) el.value = value; };
  const main = (guess.files || [])[0];
  if (main) put(document.getElementById("dvzNewKind"), main.kind);
  put(document.getElementById("dvzNewChart"), guess.chart);
  put(document.getElementById("dvzNewTitle"), guess.title);   // במקום שם הקובץ
  (guess.files || []).slice(1).forEach((g, i) => {
    const extra = _dvzExtraFiles[i];
    if (!g || !extra) return;
    extra.guess = {...extra.guess, kind: g.kind, axis: g.axis, fill: g.fill};
    for (const key of ["kind", "axis", "fill"]) put(extra.mapping && extra.mapping.querySelector(`[data-field="${key}"]`), g[key]);
  });
  const msg = document.getElementById("dvzNewMsg");
  if (msg && !msg.classList.contains("bad")) msg.textContent += " 🤖 העורך החכם מילא את סוג הערכים, הציר, התרשים והכותרת - אפשר לשנות.";
}

async function _dvzAddExtraFiles(files) {
  const msg = document.getElementById("dvzNewMsg");
  for (const file of files) {
    try {
      const csv = await _dvzFileAsCsv(file);
      const resp = await fetch("/api/dataviz/episodes/csv_columns", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ csv_text: csv }) });
      const data = await _dvzJson(resp);
      if (!resp.ok) throw new Error(data.error || "קריאת ה-CSV נכשלה");
      _dvzExtraFiles.push({ name: file.name, csv, columns: data.columns, guess: _dvzGuessMapping(csv, data.columns) });
    } catch (e) {
      msg.classList.add("bad");
      msg.textContent = `שגיאה בקובץ ${file.name}: ${e.message}`;
    }
  }
  _dvzRenderExtraFiles();
}

// כל קובץ נוסף עם מיפוי משלו; ברירת המחדל - העמודות שנבחרו לקובץ הראשון, אם יש כאלה בקובץ
function _dvzRenderExtraFiles() {
  const box = document.getElementById("dvzNewExtra");
  if (!box) return;
  const val = (id) => document.getElementById(id).value;
  const primary = { time_column: val("dvzNewTime"), period: val("dvzNewPeriod"), value_column: val("dvzNewValue"), group_column: val("dvzNewGroup"), kind: val("dvzNewKind") };
  box.replaceChildren(..._dvzExtraFiles.map((extra, i) => {
    const card = _dvzEdEl("div", "dvz-source");
    extra.mapping = _dvzSourceMapping(extra.columns, { ...primary, ...extra.guess });   // 19.10.2026: ניחוש לכל קובץ, ואז הראשון
    card.append(_dvzEdEl("strong", "", `קובץ ${i + 2}: ${extra.name}`), extra.mapping);
    return card;
  }));
}

// גל 40: גם Excel ו-JSON (מומרים ל-CSV בשרת), וגם קובץ שנגרר למסך
async function dvzTableFile(file) {
  const msg = document.getElementById("dvzNewMsg");
  _dvzCsvText = "";
  _dvzCsvName = file ? file.name : "";
  _dvzExtraFiles = [];
  _dvzRenderExtraFiles();
  if (!file) return;
  try {
    _dvzCsvText = await _dvzFileAsCsv(file);
    const resp = await fetch("/api/dataviz/episodes/csv_columns", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ csv_text: _dvzCsvText }) });
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "קריאת ה-CSV נכשלה");
    _dvzFillColumns("dvzNewTime", data.columns, false);
    _dvzFillColumns("dvzNewValue", data.columns, true);
    _dvzFillColumns("dvzNewGroup", data.columns, true);
    _dvzGuessColumns(_dvzCsvText, data.columns);   // גל 41: ערך וקבוצה מנוחשים - פחות לחיצות
    msg.classList.remove("bad");
    msg.textContent = `נקראו ${data.columns.length} עמודות.`;
    const nameInput = document.getElementById("dvzNewName");
    if (!nameInput.value) nameInput.value = file.name.replace(/\.[^.]+$/, "").replace(/[^\w\-]+/g, "_").slice(0, 40);
    const titleInput = document.getElementById("dvzNewTitle");   // גל 41 (תקציב לחיצות): כותרת זמנית משם הקובץ
    if (!titleInput.value) titleInput.value = file.name.replace(/\.[^.]+$/, "").slice(0, 120);
  } catch (e) {
    msg.classList.add("bad");
    msg.textContent = "שגיאה: " + e.message;
  }
}

function _dvzFillColumns(id, columns, optional) {
  const select = document.getElementById(id);
  const keep = select.querySelector("option[value='']");
  select.innerHTML = "";
  if (keep) select.appendChild(keep);
  for (const col of columns) {
    const opt = document.createElement("option");
    opt.value = col;
    opt.textContent = col;
    select.appendChild(opt);
  }
  if (!optional && columns.length) select.value = columns[0];
}

async function dvzCreateEpisode() {
  const msg = document.getElementById("dvzNewMsg");
  const val = (id) => document.getElementById(id).value;
  const body = {
    name: val("dvzNewName"), title: val("dvzNewTitle"), subtitle: val("dvzNewSubtitle"), chart: val("dvzNewChart"),
    theme: val("dvzNewTheme"), period: val("dvzNewPeriod"), time_column: val("dvzNewTime"), value_column: val("dvzNewValue"),
    group_column: val("dvzNewGroup"), csv_text: _dvzCsvText, template: val("dvzNewTemplate"), kind: val("dvzNewKind"), filename: _dvzCsvName,
  };
  if (_dvzExtraFiles.length) body.extra_sources = _dvzExtraFiles.map(extra => ({ ..._dvzMappingValues(extra.mapping), csv_text: extra.csv, filename: extra.name }));
  document.getElementById("dvzCreateBtn").disabled = true;
  try {
    const resp = await fetch("/api/dataviz/episodes/create", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({...body, lang: _uiLang}) });
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "היצירה נכשלה");
    msg.classList.remove("bad");
    msg.textContent = "✅ הפרק נוצר.";
    dvzState.selected = data.name;
    await loadDataviz();
    // 23.10.2026: הטופס מתאפס - קודם השם, הכותרת והקובץ של הפרק הקודם נשארו (יצירה שנייה נכשלה או קיבלה את הכותרת הישנה)
    for (const id of ["dvzNewName", "dvzNewTitle", "dvzNewSubtitle", "dvzNewCsv"]) document.getElementById(id).value = "";
    for (const el of document.querySelectorAll("#dvzNewDialog [data-touched]")) delete el.dataset.touched;   // הניחוש של הפרק הבא
    _dvzCsvText = "";
    _dvzCsvName = "";
    _dvzExtraFiles = [];
    _dvzRenderExtraFiles();
    document.getElementById("dvzNewDialog").close();   // גל 59
    uiToast("✅ הפרק נוצר", "ok");
  } catch (e) {
    msg.classList.add("bad");
    msg.textContent = "שגיאה: " + e.message;
  } finally {
    document.getElementById("dvzCreateBtn").disabled = false;
  }
}