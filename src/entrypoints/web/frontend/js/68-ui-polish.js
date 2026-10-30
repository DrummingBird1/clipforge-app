// ============================================================================
// גל 20 - תנועה, משוב וליטוש: skeleton loaders, פס התקדמות גלובלי, סטטוס אחיד,
// צפיפות (נוח/צפוף) לכל האפליקציה, פאנל היסטוריית שינויים וסיור מודרך.
// ============================================================================

// --- skeleton במקום "טוען..." ---
function uiSkeleton(container, count = 3, kind = "row") {
  if (!container) return;
  const box = document.createElement("div");
  box.className = "skeleton" + (kind === "card" ? " cards" : "");
  box.setAttribute("aria-busy", "true");
  box.setAttribute("aria-label", "טוען");
  for (let i = 0; i < count; i++) {
    const item = document.createElement("div");
    item.className = "sk sk-" + kind;
    box.appendChild(item);
  }
  container.replaceChildren(box);
}

// --- פס התקדמות גלובלי: משקף את פס ההתקדמות של הריצה, בכל מסך ---
function _uiSetupGlobalProgress() {
  const bar = document.createElement("div");
  bar.className = "global-progress";
  bar.hidden = true;
  bar.setAttribute("role", "progressbar");
  bar.setAttribute("aria-label", "התקדמות הריצה");
  bar.setAttribute("aria-valuemin", "0");
  bar.setAttribute("aria-valuemax", "100");
  const fill = document.createElement("i");
  bar.appendChild(fill);
  document.body.appendChild(bar);
  const source = document.getElementById("progressBar");
  const wrap = source.closest(".progress-wrap");
  const sync = () => {
    const pct = parseFloat(source.style.width) || 0;
    const running = !!state.running;
    bar.hidden = !running;
    bar.classList.toggle("indeterminate", running && pct <= 0);
    fill.style.width = Math.min(100, pct) + "%";
    bar.setAttribute("aria-valuenow", String(Math.round(pct)));
    if (wrap) wrap.classList.toggle("running", running && pct > 0 && pct < 100);
  };
  new MutationObserver(sync).observe(source, {attributes: true, attributeFilter: ["style"]});
  // state.running משתנה בלי שינוי-סגנון (התחלה/סיום) - בדיקה קלה ברקע
  setInterval(sync, 700);
  sync();
}

// --- סטטוס אחיד בשורות הריצות האחרונות ---
const _renderVeRunsBeforePolish = _renderVeRuns;
_renderVeRuns = function (...args) {
  const result = _renderVeRunsBeforePolish(...args);
  for (const row of document.querySelectorAll("#veRunsList .ve-run-row")) {
    const run = (_veRunsCache || []).find(r => String(r.id) === row.dataset.runId);
    if (!run) continue;
    row.dataset.status = run.status === "success" ? (run.errors ? "bad" : "ok") : (run.status === "running" ? "running" : (run.status === "failed" ? "bad" : "cancelled"));
  }
  return result;
};

// --- צפיפות לכל האפליקציה ---
function _uiLoadDensity() {
  try { return localStorage.getItem("uiDensity") === "compact" ? "compact" : "comfortable"; } catch (e) { return "comfortable"; }
}

function setUiDensity(density) {
  const compact = density === "compact";
  if (compact) document.documentElement.dataset.density = "compact";
  else delete document.documentElement.dataset.density;
  try { localStorage.setItem("uiDensity", compact ? "compact" : "comfortable"); } catch (e) { /* לא קריטי */ }
  const btn = document.getElementById("densityBtn");
  if (btn) {
    btn.setAttribute("aria-pressed", String(compact));
    btn.title = compact ? "צפיפות: צפופה (לחיצה - נוחה)" : "צפיפות: נוחה (לחיצה - צפופה)";
  }
}

function toggleUiDensity() { setUiDensity(document.documentElement.dataset.density === "compact" ? "comfortable" : "compact"); }

// --- פאנל היסטוריית שינויים (במקום Ctrl+Z עיוור) ---
const _uiUndoTimes = new Map();
const _pushVeUndoSnapshotBeforePolish = _pushVeUndoSnapshot;
_pushVeUndoSnapshot = function (...args) {
  const result = _pushVeUndoSnapshotBeforePolish(...args);
  const top = _veUndoStack[_veUndoStack.length - 1];
  if (top && !_uiUndoTimes.has(top)) _uiUndoTimes.set(top, Date.now());
  if (!_veEl("veUndoPanel").hidden) renderVeUndoPanel();
  return result;
};

function _uiFieldLabel(key) {
  const meta = (typeof VE_FAVORITABLE_FIELDS !== "undefined" && VE_FAVORITABLE_FIELDS[key]) || null;
  return meta ? meta.label.replace(/[:：]\s*$/, "") : key;
}

function _uiDescribeChange(before, after) {
  if (!before) return "המצב ההתחלתי";
  const a = JSON.parse(before), b = JSON.parse(after);
  const keys = [...new Set([...Object.keys(a), ...Object.keys(b)])].filter(k => JSON.stringify(a[k]) !== JSON.stringify(b[k]));
  if (!keys.length) return "ללא שינוי";
  const first = keys.slice(0, 2).map(k => {
    const value = b[k];
    const shown = typeof value === "boolean" ? (value ? "הופעל" : "כובה") : (value === "" || value === null || value === undefined ? "נוקה" : String(value).slice(0, 24));
    return `${_uiFieldLabel(k)}: ${shown}`;
  });
  return first.join(" · ") + (keys.length > 2 ? ` · +${keys.length - 2}` : "");
}

function renderVeUndoPanel() {
  const list = _veEl("veUndoList");
  const past = _veUndoStack.slice();
  const future = _veRedoStack.slice().reverse();
  const entries = [...past.map((snap, i) => ({snap, prev: past[i - 1], kind: i === past.length - 1 ? "current" : "past", index: i})),
    ...future.map((snap, i) => ({snap, prev: i === 0 ? past[past.length - 1] : future[i - 1], kind: "future", index: past.length + i}))];
  if (entries.length <= 1) {
    const empty = document.createElement("div");
    empty.className = "empty-msg";
    empty.textContent = "עוד אין שינויים בסשן הזה. כל שינוי הגדרה יופיע כאן.";
    list.replaceChildren(empty);
    return;
  }
  list.replaceChildren(...entries.reverse().map(entry => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "undo-item " + entry.kind;
    const dot = document.createElement("span");
    dot.className = "undo-dot";
    const what = document.createElement("span");
    what.className = "undo-what";
    what.textContent = _uiDescribeChange(entry.prev, entry.snap);
    const time = document.createElement("span");
    time.className = "undo-time";
    const at = _uiUndoTimes.get(entry.snap);
    time.textContent = at ? new Date(at).toLocaleTimeString("he-IL", {hour: "2-digit", minute: "2-digit", second: "2-digit"}) : "";
    btn.append(dot, what, time);
    btn.title = entry.kind === "current" ? "המצב הנוכחי" : "חזרה לנקודה הזו";
    btn.onclick = () => veUndoTo(entry.index);
    return btn;
  }));
}

function veUndoTo(index) {
  while (_veUndoStack.length - 1 > index && _veUndoStack.length > 1) veUndo();
  while (_veUndoStack.length - 1 < index && _veRedoStack.length) veRedo();
  renderVeUndoPanel();
}

function toggleVeUndoPanel(force) {
  const panel = _veEl("veUndoPanel");
  const show = force === undefined ? panel.hidden : !!force;
  panel.hidden = !show;
  if (show) renderVeUndoPanel();
}

for (const name of ["veUndo", "veRedo"]) {
  const original = window[name];
  window[name] = function (...args) {
    const result = original.apply(this, args);
    if (!_veEl("veUndoPanel").hidden) renderVeUndoPanel();
    return result;
  };
}

// --- סיור מודרך קצר (פעם אחת, או מ-Ctrl+K) ---
const UI_TOUR_STEPS = [
  {target: ".nav-rail", title: "כל המסכים במקום אחד", text: "הפס בצד מחליף את הלשוניות: סטודיו, סקריפטים, גלריה, אישור קליפים, פרסום, תזמון, בוט והגדרות."},
  {target: ".topbar-search", title: "Ctrl+K מוצא הכל", text: "סקריפט, הגדרה בעורך, פרויקט, מסך או פעולה - מתחילים להקליד ו-Enter."},
  {target: ".home-actions", title: "מסך הבית", text: "פעולות מהירות, הפרויקטים האחרונים והריצות האחרונות - בלחיצה אחת."},
  {target: ".nav-rail .rail-studio", title: "הסטודיו", text: "עורך-העל במסך מלא: נגן חי, ציר-זמן עם מסלולים, סביבות עבודה ומפרידים נגררים. Esc או ⛶ יוצאים."},
];
let _uiTourIndex = -1;

function _uiTourEls() {
  let spot = document.getElementById("tourSpot");
  let card = document.getElementById("tourCard");
  if (!spot) {
    spot = document.createElement("div"); spot.id = "tourSpot"; spot.className = "tour-spot";
    card = document.createElement("div"); card.id = "tourCard"; card.className = "tour-card";
    card.setAttribute("role", "dialog"); card.setAttribute("aria-modal", "true"); card.setAttribute("aria-labelledby", "tourTitle");
    document.body.append(spot, card);
  }
  return {spot, card};
}

function startUiTour() {
  goHome();
  _uiTourIndex = 0;
  // פעם אחת לדפדפן, גם בלי "דלג": קודם מי שעבר מסך או רענן באמצע קיבל את "1/4" מחדש בכל טעינה. חוזר מ-Ctrl+K
  try { localStorage.setItem("uiTourSeen", "1"); } catch (e) { /* לא קריטי */ }
  _uiShowTourStep();
}

function endUiTour() {
  _uiTourIndex = -1;
  document.getElementById("tourSpot")?.remove();
  document.getElementById("tourCard")?.remove();
  try { localStorage.setItem("uiTourSeen", "1"); } catch (e) { /* לא קריטי */ }
}

function _uiShowTourStep() {
  const step = UI_TOUR_STEPS[_uiTourIndex];
  if (!step) { endUiTour(); return; }
  const target = document.querySelector(step.target);
  if (!target || !target.offsetParent) { _uiTourIndex++; _uiShowTourStep(); return; }
  const {spot, card} = _uiTourEls();
  const rect = target.getBoundingClientRect();
  Object.assign(spot.style, {top: rect.top - 6 + "px", left: rect.left - 6 + "px", width: rect.width + 12 + "px", height: rect.height + 12 + "px"});
  card.innerHTML = "";
  const counter = document.createElement("div"); counter.className = "tour-step"; counter.textContent = `${_uiTourIndex + 1} / ${UI_TOUR_STEPS.length}`;
  const title = document.createElement("h3"); title.className = "tour-title"; title.id = "tourTitle"; title.textContent = step.title;
  const text = document.createElement("p"); text.className = "tour-text"; text.textContent = step.text;
  const actions = document.createElement("div"); actions.className = "tour-actions";
  const skip = document.createElement("button"); skip.type = "button"; skip.className = "btn-ghost"; skip.textContent = "דלג"; skip.onclick = endUiTour;
  const next = document.createElement("button"); next.type = "button"; next.className = "btn-primary";
  next.textContent = _uiTourIndex === UI_TOUR_STEPS.length - 1 ? "סיום" : "הבא";
  next.onclick = () => { _uiTourIndex++; _uiShowTourStep(); };
  actions.append(skip, next);
  card.append(counter, title, text, actions);
  // הכרטיס ליד היעד - מתחתיו אם יש מקום, אחרת מעליו; לא יוצא מהמסך
  const cardWidth = Math.min(window.innerWidth * 0.92, 340);
  const below = rect.bottom + 14 + 200 < window.innerHeight;
  const top = below ? rect.bottom + 14 : Math.max(12, rect.top - 214);
  const rtl = getComputedStyle(document.body).direction === "rtl";
  let left = rtl ? rect.right - cardWidth : rect.left;
  if (rect.width < 120) left = rtl ? rect.left - cardWidth - 16 : rect.right + 16;
  left = Math.max(12, Math.min(window.innerWidth - cardWidth - 12, left));
  Object.assign(card.style, {top: (rect.width < 120 ? Math.min(rect.top, window.innerHeight - 220) : top) + "px", left: left + "px"});
  next.focus();
}

document.addEventListener("keydown", (e) => {
  if (_uiTourIndex < 0) return;
  if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); endUiTour(); }
  else if (e.key === "ArrowLeft" || e.key === "Enter") { if (e.target.closest && e.target.closest(".tour-card button")) return; _uiTourIndex++; _uiShowTourStep(); }
}, true);

window.addEventListener("resize", () => { if (_uiTourIndex >= 0) _uiShowTourStep(); });

function _uiMaybeStartTour() {
  let seen = true;
  try { seen = localStorage.getItem("uiTourSeen") === "1"; } catch (e) { /* לא קריטי */ }
  // לא באוטומציה (טסטים) - navigator.webdriver
  if (!seen && !navigator.webdriver && !state.selectedId) setTimeout(startUiTour, 900);
}

// --- Ctrl+K: צפיפות, סיור והיסטוריית שינויים ---
uiPaletteProviders.push(() => {
  const extra = [
    {section: "🛠️ מערכת", label: "📏 צפיפות: נוחה/צפופה", run: toggleUiDensity},
    {section: "🛠️ מערכת", label: "🧭 סיור מודרך בממשק", run: startUiTour},
  ];
  if (_veIsActive()) extra.unshift({section: "⚡ פעולות", label: "🕘 היסטוריית שינויים (Undo)", run: () => toggleVeUndoPanel(true)});
  return extra;
});

function _uiInitPolish() {
  setUiDensity(_uiLoadDensity());
  _uiSetupGlobalProgress();
  _uiMaybeStartTour();
}
