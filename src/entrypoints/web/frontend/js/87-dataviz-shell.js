// ============================================================================
// גל 56: עורך הגרפים והסטודיו - שני כלים נפרדים עם מסגרת משותפת:
//  * "🎬 פתח בסטודיו" על כל סרטון מוכן (_dvzOutputExtras ב-86-dataviz-publish.js): השרת מכין לו תיקייה משלו
//    (utils/dataviz_handoff.py - קישור, לא עותק) והסטודיו נפתח עליה - לוגו, חיתוך, כתוביות או חיבור לקליפים
//    אחרים. התוצר כאן לא זז ולא משתנה.
//  * המסך המלא, הסרגל העליון וה-☰: html/31-dataviz.html ו-65-ui-shell.js (חייבים לפני שה-bundle הזה נטען).
// ============================================================================

async function dvzOpenInStudio(out) {
  try {
    const resp = await fetch("/api/dataviz/outputs/studio", {method: "POST", headers: {"Content-Type": "application/json"},
                                                            body: JSON.stringify({orientation: out.orientation, name: out.name})});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "הפתיחה בסטודיו נכשלה");
    openProject(data.folder);
    uiToast("🎬 נפתח בסטודיו - בתיקייה משלו; התוצר בעורך הגרפים לא השתנה", "ok");
  } catch (e) {
    uiToast("שגיאה: " + e.message, "warn");
  }
}

function _dvzStudioButton(out, actions) {
  if (out.kind !== "video") return;
  const btn = _dvzEdEl("button", "btn-sm btn-outline dvz-to-studio", "🎬 פתח בסטודיו");
  btn.type = "button";
  btn.title = "עריכה בסטודיו: לוגו, חיתוך, כתוביות או חיבור לקליפים אחרים. הסרטון מקבל תיקייה משלו, והתוצר כאן לא משתנה";
  btn.onclick = () => dvzOpenInStudio(out);
  const link = actions.querySelector(".dvz-link");
  if (link) link.after(btn); else actions.prepend(btn);
}

// גל 57: בזמן עריכה (העורך המלא או חלון הנתונים פתוחים) רשימת הפרקים מתקפלת ועמודת ההגדרות מקבלת חצי רוחב
// (27-dataviz-pro.css); "📋 פרקים" בסרגל העליון מחזיר אותה בלי לסגור את העורך
function dvzToggleEpisodes() {
  const on = document.querySelector(".dvz-studio").classList.toggle("dvz-show-episodes");
  document.querySelector(".dvz-episodes-toggle").setAttribute("aria-pressed", on ? "true" : "false");
}

// 21.10.2026 (סבב הפישוט): "➕ פרק חדש" - כניסה אחת עם שלוש דרכים (html/31-dataviz.html). "מתיקייה" היא ברירת המחדל: תיקייה עם
// config.yaml מיובאת כמו שהיא (מה שהיה "📂 ייבא תיקייה"), אחרת טיוטה חכמה (מה שהיה "📂→🎬 מתיקייה") ואחריה מסך הסקירה
// (_dvzShowSmart ב-86-dataviz-publish.js). "מקבצים" - הטופס של גל 59; "בלי קבצים" - הקטלוג
const DVZ_IMPORT_RECENT = "dvzImportRecent";

function _dvzImportRecent() {
  try { return JSON.parse(localStorage.getItem(DVZ_IMPORT_RECENT) || "[]").filter(p => typeof p === "string").slice(0, 6); } catch (e) { return []; }
}

function dvzOpenNew(way) {
  const dialog = document.getElementById("dvzNewDialog");
  if (!dialog.open) document.getElementById("dvzUseConfig").checked = true;   // ברירת המחדל בכל פתיחה (ההיכרות מכבה אותו לדוגמה)
  dvzNewWay(way || "folder");
  _dvzWatchTouched();   // המלצה 5: שדה ששינית לפני שבחרת קבצים - הניחוש של העורך החכם לא דורס אותו
  if (!dialog.open) dialog.showModal();
}

function dvzCloseNew() {
  document.getElementById("dvzNewDialog").close();
}

function dvzNewWay(way) {
  for (const tab of document.querySelectorAll("#dvzNewDialog [data-new-way]")) {
    const on = tab.dataset.newWay === way;
    tab.classList.toggle("active", on);
    tab.setAttribute("aria-selected", String(on));
  }
  document.getElementById("dvzNewFolder").hidden = way !== "folder";
  document.getElementById("dvzNewFiles").hidden = way !== "files";
  document.getElementById("dvzNewCatalog").hidden = way !== "catalog";
  if (way === "folder") _dvzPrepareFolder();
}

// הפרקים המוכנים בתיקיית הטיוטה (workspace/dataviz/staging) ככפתורים - לחיצה ממלאת את התיקייה; מה שכבר יובא מסומן
async function _dvzPrepareFolder() {
  document.getElementById("dvzImportRecent").replaceChildren(..._dvzImportRecent().map(path => new Option(path, path)));
  const box = document.getElementById("dvzImportReady");
  try {
    const [ready, settings] = await Promise.all([fetch("/api/dataviz/episodes/import_suggestions").then(_dvzJson), fetch("/api/dataviz/smart/settings").then(_dvzJson)]);
    const kit = document.getElementById("dvzSmartKit");
    const current = kit.value;
    kit.replaceChildren(new Option("בלי", ""), ...(settings.kits || []).map(k => new Option(k, k)));
    kit.value = current;
    box.replaceChildren();
    if (!ready.episodes || !ready.episodes.length) return;
    const head = _dvzEdEl("div", "hint", "📂 מוכנים בתיקיית הטיוטה:");
    head.title = ready.folder;
    box.append(head);
    for (const ep of ready.episodes) {
      const chip = _dvzEdEl("button", "btn-xs" + (ep.imported ? " is-imported" : ""), (ep.imported ? "✓ " : "") + (ep.title || ep.name));
      chip.type = "button";
      chip.setAttribute("role", "listitem");
      chip.title = ep.imported ? "כבר בפרקים - ייבוא שוב צריך שם אחר" : ep.name;
      chip.onclick = () => { document.getElementById("dvzSmartPath").value = ep.path; };
      box.append(chip);
    }
  } catch (e) {
    box.replaceChildren();   // רק הצעות - היצירה עובדת גם בלעדיהן
  }
}

// חלון הדפדוף של האפליקציה (#modalBg) - החלון שלנו נסגר בזמן הבחירה (dialog מודאלי חוסם את מה שמתחתיו) ונפתח שוב עם התיקייה
async function dvzBrowseNewFolder() {
  dvzCloseNew();
  state.browseMode = "folder";
  state.browseTarget = (path) => { document.getElementById("dvzSmartPath").value = path; dvzOpenNew("folder"); };
  await browseTo(document.getElementById("dvzSmartPath").value.trim());
  document.getElementById("modalBg").classList.add("show");
}

async function dvzRunSmart() {
  const msg = document.getElementById("dvzSmartMsg");
  const button = document.getElementById("dvzSmartGoBtn");
  const path = document.getElementById("dvzSmartPath").value.trim();
  if (!path) { msg.textContent = "בחר תיקייה."; return; }
  button.disabled = true;
  msg.textContent = "⏳ קורא את התיקייה, בוחר ומנסח...";
  try {
    const resp = await fetch("/api/dataviz/smart/draft", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({path, name: document.getElementById("dvzSmartName").value.trim(), kit: document.getElementById("dvzSmartKit").value,
                            use_config: document.getElementById("dvzUseConfig").checked})});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "הפרק לא נוצר");
    try { localStorage.setItem(DVZ_IMPORT_RECENT, JSON.stringify([path, ..._dvzImportRecent().filter(p => p !== path)].slice(0, 6))); } catch (e) { /* רק נוחות */ }
    msg.textContent = "";
    document.getElementById("dvzSmartName").value = "";
    dvzCloseNew();
    dvzState.selected = data.episode;
    await loadDataviz();
    if (data.imported) {   // פרק מוכן - בלי בחירות אוטומטיות לסקור
      uiToast(`📂 הפרק "${data.episode}" יובא (${data.files} קבצים)`, "ok");
      return;
    }
    await dvzLoadEditor();
    dvzPreviewSoon();
    dvzOnboardNext(2);
    _dvzShowSmart(data);
  } catch (e) {
    msg.textContent = "שגיאה: " + e.message;
  } finally {
    button.disabled = false;
  }
}

// "✏️ שנה" במסך הסקירה: פותח את העורך המלא בלשונית ובשדה של הבחירה (שדה שלא בהגדרות - הלשונית שלו)
const DVZ_PATH_TABS = [["events", "events"], ["story.", "story"], ["colors", "colors"], ["entities", "entities"], ["translations", "langs"], ["narration", "voice"], ["map.", "map"]];

async function dvzEditField(path) {
  const editor = document.getElementById("dvzEditor");
  editor.open = true;
  await dvzLoadEditor();
  const inFields = (dvzEd.data.groups || []).some(g => g.fields.some(f => f.path === path));
  const tab = inFields ? "fields" : ((DVZ_PATH_TABS.find(([prefix]) => path.startsWith(prefix)) || [])[1] || "fields");
  dvzEd.tab = tab;
  dvzEd.search = "";
  _dvzRenderEditor();
  const row = document.querySelector(`#dvzEditorBody .dvz-field[data-path="${CSS.escape(path)}"]`);
  const target = row || document.getElementById("dvzEditorBody");
  const group = row && row.closest("details");
  if (group) { group.hidden = false; group.open = true; }
  if (row) {
    row.hidden = false;
    row.classList.add("dvz-field-focus");
    const input = row.querySelector("input, select, textarea");
    if (input) input.focus({preventScroll: true});
  }
  target.scrollIntoView({block: "center"});
}

// גל 59: סוג התרשים, היעד, השפה וחבילת הפרסום להרצה אחת - מקופלים ל"שינויים להרצה הזו", והתקציר אומר מה שונה.
// חלקים נפרדים (תווית וערך) כדי שהממשק באנגלית יתרגם כל אחד
function _dvzRunOverridesSummary() {
  const box = document.getElementById("dvzRunOverridesSummary");
  if (!box) return;
  const parts = [];
  for (const [id, label] of [["dvzChart", "תרשים:"], ["dvzTarget", "יעד:"], ["dvzRunLang", "שפה:"]]) {
    const select = document.getElementById(id);
    if (select && select.value) parts.push([label, select.selectedOptions[0].textContent.trim()]);
  }
  const publish = document.getElementById("dvzPublish").value;
  if (publish !== "default") parts.push([publish === "on" ? "עם חבילת פרסום" : "בלי חבילת פרסום"]);
  const nodes = [];
  for (const [i, part] of (parts.length ? parts : [["לפי הגדרות הפרק"]]).entries()) {
    nodes.push(_dvzEdEl("span", "", i ? " · " : "· "));
    for (const text of part) nodes.push(_dvzEdEl("span", "", text), document.createTextNode(" "));
  }
  box.replaceChildren(...nodes);
}

function _dvzInitRunOverrides() {
  const box = document.getElementById("dvzRunOverrides");
  if (!box || box.dataset.ready) return;
  box.dataset.ready = "1";
  box.addEventListener("change", _dvzRunOverridesSummary);
  _dvzRunOverridesSummary();
}

_dvzInitRunOverrides();

// גל 59: "אפס לברירת המקור" של הטופס הנפרד שיצא - עכשיו בסרגל של העורך המלא: מוחק את קובץ השינויים של הפרק
async function dvzResetAllOverrides() {
  if (!dvzState.selected) return;
  if (!(await veConfirm("לאפס את כל השינויים של הפרק? config.yaml של הפרק לא משתנה.", {danger: true, okLabel: "↩️ אפס הכל"}))) return;
  const status = document.getElementById("dvzEditorStatus");
  try {
    await _dvzKitPost("/api/dataviz/episodes/settings", {episode: dvzState.selected, settings: null}, "");
    dvzEd.draft = {};
    dvzEd.unset = new Set();
    _dvzResetUndo();
    delete dvzState.estimates[dvzState.selected];
    _dvzSyncDraftBar();
    await loadDataviz();
    await dvzLoadEditor();
    status.textContent = "↩️ כל השינויים אופסו - הפרק כמו בקובץ שלו.";
  } catch (e) {
    status.textContent = "שגיאה: " + e.message;
  }
}

// --- 20.10.2026: "🗑️ מחק פרק" - לסל של עורך הגרפים (data/dataviz_trash), עם שחזור. שום דבר לא נמחק באמת עד "רוקן סל" ---
function _dvzDeleteButton(ep) {
  const button = _dvzEdEl("button", "btn-xs btn-ghost dvz-delete-btn", "🗑️");
  button.type = "button";
  button.dataset.deleteFor = ep.name;
  button.title = "מחק פרק - עובר לסל, אפשר לשחזר";
  button.setAttribute("aria-label", button.title);
  button.onclick = () => dvzDeleteEpisode(ep.name);
  return button;
}

async function dvzDeleteEpisode(name) {
  if (!name) return;
  const ep = dvzState.episodes.find(e => e.name === name) || {name};
  const message = "🗑️ " + (ep.title || name) + " (" + name + ")\n\n" +
    "עוברים לסל של עורך הגרפים (data/dataviz_trash): תיקיית הפרק, השינויים שלו מהדפדפן (data/dataviz_overrides) והרשומות שלו - תגיות, הסתרה ותור. התוצרים המרונדרים לא זזים, ואפשר לשחזר מ\"♻️ שנמחקו\".";
  if (!await veConfirm(message, {danger: true, okLabel: "🗑️ מחק"})) return;
  try {
    const resp = await fetch("/api/dataviz/episodes/delete", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({episode: name})});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "המחיקה נכשלה");
    if (dvzState.selected === name) dvzState.selected = null;
    await loadDataviz();
    uiToast("🗑️ הפרק עבר לסל - אפשר לשחזר מ\"♻️ שנמחקו\"", "ok");
  } catch (e) {
    _dvzSetStatus("שגיאה: " + e.message, true);
  }
}

// 21.10.2026: נבנה בפתיחה הראשונה (לא ב-HTML של המסך - תקציב ה-HTML של dataviz הוא 30K)
function _dvzTrashDialog() {
  if (!document.getElementById("dvzTrashDialog")) document.getElementById("dvzNewDialog").insertAdjacentHTML("afterend", `<dialog id="dvzTrashDialog" class="dvz-dialog" aria-labelledby="dvzTrashHeading">
    <div class="tc-row dvz-dialog-head">
      <h3 id="dvzTrashHeading">♻️ פרקים שנמחקו</h3>
      <button type="button" class="btn-sm" onclick="document.getElementById('dvzTrashDialog').close()">✕ סגור</button>
    </div>
    <div class="hint u-block u-margin-bottom-8px">פרק שנמחק עובר לכאן עם השינויים שלו מהדפדפן, התגיות וההסתרה - שום דבר לא נמחק באמת עד "רוקן סל". התוצרים המרונדרים לא זזים.</div>
    <div id="dvzTrashList"></div>
    <div class="tc-row"><button type="button" class="btn-sm" id="dvzTrashEmptyBtn" onclick="dvzEmptyTrash()" title="מחיקה סופית של כל מה שבסל - אי אפשר לשחזר">🗑️ רוקן סל</button></div>
    <div class="hint u-block" id="dvzTrashMsg" role="status" aria-live="polite"></div>
</dialog>`);
  return document.getElementById("dvzTrashDialog");
}

async function dvzOpenTrash() {
  const dialog = _dvzTrashDialog();
  document.getElementById("dvzTrashMsg").textContent = "";
  if (!dialog.open) dialog.showModal();
  await _dvzRenderTrash();
}

async function _dvzRenderTrash() {
  const list = document.getElementById("dvzTrashList");
  let items;
  try {   // 23.10.2026: שגיאת שרת הוצגה כ"הסל ריק."
    items = (await _dvzJsonOk(await fetch("/api/dataviz/trash"))).items || [];
  } catch (e) {
    list.replaceChildren(_dvzEdEl("p", "empty-msg bad", "שגיאה: " + e.message));
    return;
  }
  document.getElementById("dvzTrashEmptyBtn").disabled = !items.length;
  if (!items.length) { list.replaceChildren(_dvzEdEl("p", "empty-msg", "הסל ריק.")); return; }
  list.replaceChildren(...items.map(item => {
    const row = _dvzEdEl("div", "tc-row dvz-trash-row");
    row.dataset.trashId = item.id;
    const restore = _dvzEdEl("button", "btn-sm", "♻️ שחזר");
    restore.type = "button";
    restore.disabled = item.taken;
    restore.title = item.taken ? "כבר יש פרק בשם הזה - שנה את שמו או מחק אותו קודם" : "הפרק חוזר לרשימה עם השינויים, התגיות וההסתרה שלו";
    restore.onclick = () => dvzRestoreEpisode(item.id);
    row.append(_dvzEdEl("strong", "", item.title), _dvzEdEl("span", "hint", item.name), _dvzEdEl("span", "hint", item.deleted_at), restore);
    return row;
  }));
}

async function dvzRestoreEpisode(id) {
  const msg = document.getElementById("dvzTrashMsg");
  try {
    const resp = await fetch("/api/dataviz/trash/restore", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id})});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "השחזור נכשל");
    dvzState.selected = data.name;
    await loadDataviz();
    await _dvzRenderTrash();
    msg.textContent = "♻️ הפרק חזר לרשימה.";
  } catch (e) {
    msg.textContent = "שגיאה: " + e.message;
  }
}

// שני אישורים. 20.10.2026: חלון האישור נפתח עכשיו מעל ה-dialog (10-editor-core.js) - לא סוגרים ופותחים אותו בזמן האישור
async function dvzEmptyTrash() {
  const sure = await veConfirm("לרוקן את הסל? כל הפרקים שבו יימחקו לגמרי.", {danger: true, okLabel: "המשך"})
    && await veConfirm("בטוח? אי אפשר לשחזר אחרי זה.", {danger: true, okLabel: "🗑️ רוקן לגמרי"});
  if (!sure) return;
  const msg = document.getElementById("dvzTrashMsg");
  try {
    const resp = await fetch("/api/dataviz/trash/empty", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({confirm: "empty"})});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "הריקון נכשל");
    await _dvzRenderTrash();
    msg.textContent = "הסל רוקן.";
  } catch (e) {
    msg.textContent = "שגיאה: " + e.message;
  }
}
