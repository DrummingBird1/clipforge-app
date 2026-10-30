// ============================================================================
// 21.10.2026 (סבב הפישוט של עורך הגרפים): מה שמחבר את המסך לזרימה אחת - "🧰 כלים" (כל הכלים הנפרדים בתפריט אחד בסרגל
// העליון), רמת הפירוט לכל המסך (פשוט / רגיל / מומחה, 44-dataviz-editor.js) וההיכרות בפעם הראשונה. ב-bundle השלישי
// (dataviz_tools), שנטען אחרי dataviz_pro - שם הקוד של "➕ פרק חדש" (87) ושל הסקירה והרשימה "✅ לפני רינדור" (86).
// ============================================================================

// --- 21.10.2026 (סבב הפישוט): "🧰 כלים" - תפריט אחד בסרגל העליון לכל הכלים הנפרדים, במקום כפתורים פזורים בכותרת, בשורת
// הכלים של הרשימה ובתפריט ⋯. כלי של פרק מושבת כשאין פרק נבחר. בסוף - "⚙️ הגדרות עורך הגרפים" (ההגדרות החד-פעמיות) ---
const DVZ_TOOLS = [
  ["הפרק", [
    ["dvzToolHistory", "🕘 היסטוריית גרסאות", () => dvzOpenHistory(), true],
    ["dvzToolVariants", "🧬 גרסאות של הפרק", () => dvzOpenVariants(), true],
    ["dvzToolGrid", "✏️ טבלת הנתונים", () => dvzOpenSourcesTab(), true],
    ["dvzToolFinal", "📜 ההגדרות הסופיות", () => { document.getElementById("dvzEditor").open = true; dvzShowFinalConfig(); }, true],
  ]],
  ["כל הפרקים", [
    ["dvzToolCatalog", "📚 קטלוג נתונים", () => dvzOpenCatalog(), false],
    ["dvzToolBatch", "🖼 דוח תמונות", () => dvzOpenBatch(), false],
    ["dvzToolBoard", "📈 לוח צפיות", () => dvzOpenBoard(), false],
    ["dvzToolTrash", "♻️ שנמחקו", () => dvzOpenTrash(), false],
    ["dvzToolHelp", "📖 מדריך המנוע", () => dvzOpenHelp(), false],
  ]],
  ["", [["dvzToolSettings", "⚙️ הגדרות עורך הגרפים", () => dvzOpenSettings(), false]]],
];

function _dvzInitTools() {
  if (document.getElementById("dvzToolsBtn")) return;
  const wrap = _dvzEdEl("div", "ve-menu-wrap");
  const button = _dvzEdEl("button", "btn-sm", "🧰 כלים");
  button.type = "button";
  button.id = "dvzToolsBtn";
  button.title = "היסטוריה, גרסאות, טבלת הנתונים, קטלוג, דוח תמונות, לוח צפיות, שנמחקו, מדריך והגדרות";
  button.setAttribute("aria-haspopup", "true");
  button.setAttribute("aria-expanded", "false");
  const menu = _dvzEdEl("div", "ve-menu");
  menu.id = "dvzToolsMenu";
  menu.hidden = true;
  menu.setAttribute("role", "menu");
  for (const [title, items] of DVZ_TOOLS) {
    if (title) menu.append(_dvzEdEl("div", "ve-menu-title", title));
    else menu.append(document.createElement("hr"));
    for (const [id, label, run, needsEpisode] of items) {
      const item = _dvzEdEl("button", "", label);
      item.type = "button";
      item.id = id;
      item.setAttribute("role", "menuitem");
      if (needsEpisode) item.dataset.needsEpisode = "1";
      item.onclick = run;
      menu.append(item);
    }
  }
  button.onclick = (event) => {
    for (const item of menu.querySelectorAll("[data-needs-episode]")) item.disabled = !dvzState.selected;
    toggleVeMenu("dvzToolsMenu", event);
  };
  wrap.append(button, menu);
  document.getElementById("dvzSearchAllBtn").before(wrap);
}

// "✏️ טבלת הנתונים": חלון הנתונים בלשונית המקורות - שם "✏️ נתונים" לכל מקור
function dvzOpenSourcesTab() {
  dvzData.tab = "sources";
  const details = document.getElementById("dvzData");
  details.open = true;
  dvzLoadData();
  details.scrollIntoView({block: "nearest"});
}

_dvzInitTools();
_dvzApplyMode();   // הרמה (פשוט / רגיל / מומחה) לכל המסך - גם לפני שהעורך המלא נפתח

// --- 21.10.2026 (סבב הפישוט): היכרות בפעם הראשונה - פרק לדוגמה מאחד הפרקים בתיקיית הטיוטה, צעד אחר צעד: תיקייה -> סקירה ->
// רינדור. מוצעת פעם אחת (localStorage, מסומן כשהיא מוצגת - כמו הסיור הכללי), אפשר לדלג, ואף פעם לא ל-Playwright
// (navigator.webdriver). כל צעד מוסיף שורת הסבר בחלון של אותו צעד; בלי חלונות חדשים ---
const DVZ_ONBOARD_SEEN = "dvzOnboardSeen";
const DVZ_ONBOARD_STEPS = {
  1: ["dvzNewFolder", "צעד 1 מתוך 3: התיקייה כבר נבחרה - פרק מוכן מתיקיית הטיוטה. לחץ \"✅ צור פרק\": העורך קורא את הקבצים ובוחר הכל לבד."],
  2: ["dvzSmartSummary", "צעד 2 מתוך 3: אלה הבחירות של העורך, כל אחת עם הסיבה. \"✓ מאשר\", \"✏️ שנה\" או \"↺ בטל\" - ואז \"▶ לרינדור\"."],
  3: ["dvzPreSummary", "צעד 3 מתוך 3: בדיקה אחרונה לפני רינדור. \"▶ הרץ\" מפיק תצוגה מקדימה מהירה - ואחר כך אפשר סרטון מלא."],
};
let dvzOnboard = {step: 0};

// נקרא מ-loadDataviz (42-dataviz-screen.js) - כשהמסך נפתח
async function dvzMaybeOnboard(force) {
  let seen = false;
  try { seen = localStorage.getItem(DVZ_ONBOARD_SEEN) === "1"; } catch (e) { seen = true; }   // בלי אחסון - לא להציק בכל טעינה
  if (!force && (seen || navigator.webdriver)) return;
  if (document.getElementById("dvzOnboard") || document.querySelector('[data-tab-panel="dataviz"]').hidden) return;   // רק על המסך עצמו
  try { localStorage.setItem(DVZ_ONBOARD_SEEN, "1"); } catch (e) { /* לא קריטי */ }
  const ready = await fetch("/api/dataviz/episodes/import_suggestions").then(_dvzJson).catch(() => ({}));
  const example = (ready.episodes || []).find(ep => !ep.imported) || (ready.episodes || [])[0];
  const card = _dvzEdEl("div", "dvz-onboard");
  card.id = "dvzOnboard";
  card.setAttribute("role", "region");
  card.setAttribute("aria-label", "היכרות");
  card.append(_dvzEdEl("strong", "", "👋 פעם ראשונה כאן?"),
    _dvzEdEl("p", "hint", example ? `נבנה יחד פרק לדוגמה מ"${example.title || example.name}" בשלושה צעדים: תיקייה -> סקירה -> רינדור.`
      : "פרק נבנה בשלושה צעדים: תיקייה עם קובצי נתונים -> סקירה של מה שהעורך בחר -> רינדור. מתחילים ב\"➕ פרק חדש\"."));
  const start = _dvzEdEl("button", "btn-sm btn-primary", "▶ בוא נתחיל");
  start.type = "button";
  start.id = "dvzOnboardStart";
  start.hidden = !example;
  start.onclick = () => _dvzOnboardStart(example);
  const skip = _dvzEdEl("button", "btn-sm", "דלג");
  skip.type = "button";
  skip.onclick = () => dvzOnboardEnd();
  card.append(start, skip);
  document.getElementById("dvzOnboard")?.remove();
  document.querySelector(".dvz-episodes-pane").prepend(card);
}

function _dvzOnboardStart(example) {
  dvzOnboard.step = 1;
  document.getElementById("dvzOnboardStart").hidden = true;
  dvzOpenNew("folder");
  document.getElementById("dvzSmartPath").value = example.path;
  document.getElementById("dvzUseConfig").checked = false;   // הטיוטה החכמה - כדי לראות את מסך הסקירה
  document.getElementById("dvzSmartName").value = ("example_" + example.name).slice(0, 40);
  _dvzOnboardHint(1);
}

// שורת ההסבר של הצעד, בראש החלון שלו (רק כשההיכרות באותו צעד)
function _dvzOnboardHint(step) {
  if (dvzOnboard.step !== step) return;
  const [anchorId, text] = DVZ_ONBOARD_STEPS[step];
  const anchor = document.getElementById(anchorId);
  if (!anchor) return;
  const old = anchor.parentNode.querySelector(":scope > .dvz-onboard-hint");
  if (old) old.remove();
  const hint = _dvzEdEl("div", "dvz-onboard-hint", text);
  hint.setAttribute("role", "status");
  anchor.before(hint);
}

function dvzOnboardNext(step) {
  if (!dvzOnboard.step) return;
  dvzOnboard.step = step;
  if (step === 3) document.getElementById("dvzMode").value = "preview";   // הדוגמה - תצוגה מקדימה מהירה
}

function dvzOnboardEnd(done) {
  dvzOnboard.step = 0;
  document.getElementById("dvzOnboard")?.remove();
  for (const hint of document.querySelectorAll(".dvz-onboard-hint")) hint.remove();
  if (done) uiToast("🎉 הפרק לדוגמה בדרך - הוא ברשימה, ואפשר להמשיך ממנו או למחוק אותו", "ok");
}
