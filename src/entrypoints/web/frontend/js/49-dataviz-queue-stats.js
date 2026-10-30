// ============================================================================
// גל 44: פרסום ותור בעורך הגרפים - באשף הפרסום הצעת כותרת / תיאור / תגיות מ-Gemini ובחירה מבין שלוש תמונות
// ממוזערות; צפיות, לייקים ותגובות של סרטון שהועלה (בלחיצה, נשמר בחבילה ומוצג גם על כרטיס הפרק); ותור
// הפרקים עם התקדמות לכל פרק ו"הסר מהתור" - גם לפרק שרץ עכשיו (הוא נעצר, והתור ממשיך).
// ============================================================================

// --- אשף הפרסום: הצעה מ-Gemini (שלב הטקסטים) ---
function _dvzSuggestButton() {
  const btn = _dvzEdEl("button", "btn-sm", "✨ הצעה מ-Gemini");
  btn.type = "button";
  btn.title = "Gemini רואה כמה פריימים מהסרטון ומציע כותרת, תיאור ותגיות - אפשר לערוך לפני שממשיכים";
  btn.disabled = !!(dvzWizard.pkg.sent && dvzWizard.pkg.sent.length);
  btn.onclick = async () => {
    const status = document.getElementById("dvzWizardStatus");
    btn.disabled = true;
    status.textContent = "⏳ Gemini חושב...";
    try {
      const resp = await fetch(_datavizPackageUrl(dvzWizard.pkg, "/suggest"), {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
      const data = await _dvzJson(resp);
      if (!resp.ok) throw new Error(data.error || "ההצעה נכשלה");
      const s = data.suggestion;
      if (s.title) document.getElementById("dvzWzTitle").value = s.title;
      if (s.description) document.getElementById("dvzWzDesc").value = s.description;
      if (s.hashtags && s.hashtags.length) document.getElementById("dvzWzTags").value = s.hashtags.join(" ");
      status.textContent = "✨ ההצעה הוכנסה לשדות - עדיין לא נשמרה (\"הבא\" שומר).";
    } catch (e) {
      status.textContent = "שגיאה: " + e.message;
    } finally {
      btn.disabled = false;
    }
  };
  return btn;
}

// --- אשף הפרסום: שלוש תמונות ממוזערות לבחירה (שלב התמונה) ---
function _dvzCandidatesBox(pkg) {
  const box = _dvzEdEl("div", "dvz-thumb-candidates");
  const make = _dvzEdEl("button", "btn-sm", "🖼️ עוד 3 אפשרויות מהסרטון");
  make.type = "button";
  make.disabled = !!(pkg.sent && pkg.sent.length);
  const grid = _dvzEdEl("div", "dvz-thumb-grid");
  make.onclick = async () => {
    const status = document.getElementById("dvzWizardStatus");
    make.disabled = true;
    status.textContent = "⏳ מחלץ פריימים...";
    try {
      const resp = await fetch(_datavizPackageUrl(pkg, "/thumbnail_candidates"), {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
      const data = await _dvzJson(resp);
      if (!resp.ok) throw new Error(data.error || "יצירת האפשרויות נכשלה");
      status.textContent = "בחר תמונה - היא תחליף את הנוכחית (המקורית נשמרת בצד).";
      grid.replaceChildren(...data.candidates.map(k => {
        const pick = _dvzEdEl("button", "dvz-thumb-pick");
        pick.type = "button";
        pick.setAttribute("aria-label", `תמונה ${k}`);
        const img = _dvzEdEl("img");
        img.alt = "";
        img.src = _datavizPackageUrl(pkg, `/thumbnail_candidate/${k}`) + "?t=" + Date.now();
        pick.append(img);
        pick.onclick = () => _dvzChooseCandidate(pkg, k);
        return pick;
      }));
    } catch (e) {
      status.textContent = "שגיאה: " + e.message;
    } finally {
      make.disabled = false;
    }
  };
  box.append(make, grid);
  return box;
}

async function _dvzChooseCandidate(pkg, k) {
  const status = document.getElementById("dvzWizardStatus");
  try {
    const resp = await fetch(_datavizPackageUrl(pkg, "/thumbnail_choose"), {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({candidate: k})});
    if (!resp.ok) throw new Error((await _dvzJson(resp)).error || "הבחירה נכשלה");
    pkg.has_thumbnail = true;
    pkg.thumbVersion = Date.now();
    _dvzRenderWizard();
    document.getElementById("dvzWizardStatus").textContent = `✅ תמונה ${k} נבחרה.`;
  } catch (e) {
    status.textContent = "שגיאה: " + e.message;
  }
}

// --- צפיות של סרטון שהועלה (כרטיס החבילה) ---
function _dvzStatsText(stats) {
  if (!stats) return "";
  const n = (v) => Number(v || 0).toLocaleString("he-IL");
  return `👁 ${n(stats.views)} · 👍 ${n(stats.likes)} · 💬 ${n(stats.comments)}`;
}

// נקרא מ-_datavizCard (41-dataviz-packages.js) כשהסרטון הועלה ליוטיוב
function _dvzStatsLine(pkg, line) {
  const text = _dvzEdEl("span", "dvz-stats", pkg.stats ? " · " + _dvzStatsText(pkg.stats) : "");
  const btn = _dvzEdEl("button", "btn-xs", pkg.stats ? "🔄" : "👁 צפיות");
  btn.type = "button";
  btn.title = "משוך עכשיו את הצפיות, הלייקים והתגובות מיוטיוב";
  btn.onclick = async () => {
    btn.disabled = true;
    try {
      const resp = await fetch(_datavizPackageUrl(pkg, "/stats"), {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
      const data = await _dvzJson(resp);
      if (!resp.ok) throw new Error(data.error || "הנתונים לא התקבלו");
      pkg.stats = data.stats;
      text.textContent = " · " + _dvzStatsText(data.stats);
      btn.textContent = "🔄";
      if (dvzState.meta) _dvzLoadEpisodeMeta().then(dvzRenderEpisodes);
    } catch (e) {
      uiToast("שגיאה: " + e.message, "warn");
    } finally {
      btn.disabled = false;
    }
  };
  line.append(text, " ", btn);
}

// --- תור הפרקים: התקדמות לכל פרק, והסרה מהתור ---
const DVZ_QUEUE_STATES = {pending: "⏳ ממתין", running: "▶ רץ", done: "✅ הסתיים", skipped: "⏭ הוסר מהתור", failed: "❌ נכשל"};
let dvzQueueTimer = null;

async function dvzRefreshQueue() {
  const box = document.getElementById("dvzQueueProgress");
  if (!box) return;
  let data;
  try {
    data = await _dvzJson(await fetch("/api/dataviz/queue"));
  } catch (e) {
    return;
  }
  const episodes = data.episodes || [];
  box.hidden = !episodes.length;
  const skip = new Set(data.skip || []);
  box.replaceChildren(_dvzEdEl("strong", "", "תור הפרקים"), ...episodes.map(ep => {
    const row = _dvzEdEl("div", "dvz-queue-row");
    row.dataset.state = ep.state;
    const state = skip.has(ep.name) && (ep.state === "pending" || ep.state === "running") ? "⏭ יוסר מהתור" : DVZ_QUEUE_STATES[ep.state] || ep.state;
    const bar = _dvzEdEl("span", "dvz-queue-bar-fill");
    bar.style.inlineSize = `${ep.state === "done" ? 100 : ep.pct || 0}%`;
    const track = _dvzEdEl("span", "dvz-queue-track");
    track.append(bar);
    row.append(_dvzEdEl("span", "dvz-queue-name", ep.name), _dvzEdEl("span", "hint", state), track);
    if ((ep.state === "pending" || ep.state === "running") && !skip.has(ep.name) && dvzState.running) {
      const remove = _dvzEdEl("button", "btn-xs", "✕");
      remove.type = "button";
      remove.title = ep.state === "running" ? "עצור את הפרק הזה והמשך לבא אחריו" : "אל תרנדר את הפרק הזה";
      remove.setAttribute("aria-label", `הסר מהתור: ${ep.name}`);
      remove.onclick = async () => {
        remove.disabled = true;
        await fetch("/api/dataviz/queue/skip", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({episode: ep.name})});
        dvzRefreshQueue();
      };
      row.append(remove);
    }
    return row;
  }));
}

function dvzWatchQueue() {
  clearTimeout(dvzQueueTimer);
  const tick = async () => {
    await dvzRefreshQueue();
    if (dvzState.running) dvzQueueTimer = setTimeout(tick, 1500);
  };
  tick();
}

document.addEventListener("cf-finished", () => {
  clearTimeout(dvzQueueTimer);
  if (!document.getElementById("dvzQueueProgress").hidden) setTimeout(dvzRefreshQueue, 300);
});
