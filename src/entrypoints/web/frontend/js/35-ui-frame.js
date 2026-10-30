// 35-ui-frame.js - רכיבי מסגרת משותפים שנטענים לפי דרישה (23.10.2026, LAZY_JS["frame"]): כל מסך מחבר אותם אליו אחרי
// uiLoadLazy("frame").
//  - uiSplitter: מפריד נגרר בין עמודות - גרירה, חיצים (Shift = צעד גדול), Home/End, ולחיצה כפולה לברירת המחדל. הרוחב
//    נשמר לכל מסך, במפתח משלו ב-localStorage.
//  - toggleRecentPanel: חלונית "נפתחו לאחרונה" בסרגל העליון (uiRecent, 08-ui-frame.js).

// handle: המפריד. panel: העמודה שהרוחב שלה משתנה. target ו-cssVar: איפה נכתב הרוחב (בפיקסלים). edge: הקצה הקבוע של
// העמודה, לפי כיוון הקריאה ("start" = ימין בעברית). onChange(width, done): בכל שינוי, done=true בסוף גרירה או מקש.
function uiSplitter(handle, {panel, target, cssVar, key, min, max, edge = "start", label, onChange}) {
  const clamp = (value) => Math.round(Math.max(min, Math.min(max, value)));
  const fixedAtRight = () => (edge === "start") === (getComputedStyle(panel).direction === "rtl");
  const set = (value, done) => {
    if (value) target.style.setProperty(cssVar, clamp(value) + "px");
    else target.style.removeProperty(cssVar);
    if (done) {
      try { localStorage.setItem(key, JSON.stringify(value ? clamp(value) : 0)); } catch (e) { /* פרטי/מוגבל - לא קריטי */ }
    }
    handle.setAttribute("aria-valuenow", String(Math.round(panel.getBoundingClientRect().width)));
    if (onChange) onChange(value ? clamp(value) : 0, done);
  };
  Object.assign(handle, {tabIndex: 0, title: "גרירה או חיצים משנים את הרוחב · לחיצה כפולה מחזירה לברירת המחדל"});
  for (const [name, value] of [["role", "separator"], ["aria-orientation", "vertical"], ["aria-valuemin", min], ["aria-valuemax", max], ["aria-label", label]]) {
    if (value !== undefined) handle.setAttribute(name, String(value));
  }
  handle.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    handle.setPointerCapture(e.pointerId);
    handle.classList.add("dragging");
    const startWidth = panel.getBoundingClientRect().width;
    const startX = e.clientX;
    const sign = fixedAtRight() ? -1 : 1;
    let last = startWidth;
    // לפי המרחק שגררו, לא לפי מיקום העכבר: מי שתפס את המפריד באמצע הרווח לא מקבל קפיצה בתזוזה הראשונה
    const move = (ev) => set(last = startWidth + (ev.clientX - startX) * sign, false);
    const up = () => {
      handle.classList.remove("dragging");
      handle.removeEventListener("pointermove", move);
      set(last, true);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up, {once: true});
    handle.addEventListener("pointercancel", up, {once: true});
  });
  handle.addEventListener("keydown", (e) => {
    const width = panel.getBoundingClientRect().width;
    const step = (e.shiftKey ? 64 : 16) * (fixedAtRight() ? -1 : 1);   // חץ ימינה מזיז את המפריד ימינה
    const next = {ArrowRight: width + step, ArrowLeft: width - step, Home: min, End: max}[e.key];
    if (next === undefined) return;
    e.preventDefault();
    set(next, true);
  });
  handle.addEventListener("dblclick", () => set(0, true));
  const saved = () => { try { return Number(JSON.parse(localStorage.getItem(key))) || 0; } catch (e) { return 0; } };
  set(saved(), false);
  return {apply: () => set(saved(), false), reset: () => set(0, true)};
}

// --- "נפתחו לאחרונה": החלונית נבנית בפעם הראשונה, ונראית כמו תפריט ההעדפות ---
function toggleRecentPanel(open) {
  let panel = document.getElementById("recentMenu");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "recentMenu";
    panel.className = "prefs-menu";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "נפתחו לאחרונה");
    panel.hidden = true;
    document.getElementById("uiPrefsMenu").after(panel);
  }
  const btn = document.getElementById("recentBtn");
  const show = open === undefined ? panel.hidden : !!open;
  panel.hidden = !show;
  btn.setAttribute("aria-expanded", String(show));
  if (!show) return;
  panel.style.setProperty("--prefs-top", `${Math.round(btn.getBoundingClientRect().bottom + 6)}px`);
  const title = document.createElement("div");
  title.className = "prefs-title";
  title.textContent = "🕘 נפתחו לאחרונה";
  const rows = uiRecent.list().map((item) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "recent-item";
    row.title = item.id;
    const label = document.createElement("span");
    label.textContent = `${item.icon} ${item.label}`;
    const when = document.createElement("span");
    when.className = "hint";
    when.textContent = uiRelativeTime(new Date(item.at));
    row.append(label, when);
    row.onclick = () => { toggleRecentPanel(false); uiRecent.open(item); };
    return row;
  });
  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "hint";
    empty.textContent = "עוד לא נפתח כלום. תיקייה בסטודיו או פרק בעורך הגרפים יופיעו כאן.";
    rows.push(empty);
  }
  panel.replaceChildren(title, ...rows);
  (panel.querySelector("button") || btn).focus();
}

document.addEventListener("click", (event) => {
  const panel = document.getElementById("recentMenu");
  if (!panel || panel.hidden || event.target.closest("#recentMenu, #recentBtn")) return;
  toggleRecentPanel(false);
});

document.addEventListener("keydown", (event) => {
  const panel = document.getElementById("recentMenu");
  if (event.key !== "Escape" || !panel || panel.hidden) return;
  toggleRecentPanel(false);
  document.getElementById("recentBtn").focus();
});
