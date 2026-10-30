// ============================================================================
// גל 38: עורך הגרפים בשלושה אזורים - פרקים (כרטיסים עם תמונה, ריצה אחרונה וסטטוס פרסום, חיפוש,
// מיון וסינון) | תצוגה חיה (פריים בכל רגע עם סליידר, רצועת 10 פריימים, השוואת סוגי תרשים
// ובהיר מול כהה) | הגדרות (עם אורך הסרטון וזמן הרינדור המשוערים). הפריימים מצוירים בשרת בלי
// לרנדר סרטון (GET /api/dataviz/preview_frame, utils/dataviz_preview.py).
// ============================================================================

const DVZ_PUBLISH_LABELS = {pending_approval: "📦 ממתין לאישור", approved: "✅ אושר לפרסום", rejected: "✋ נדחה"};
const DVZ_KIND_LABELS = {intro: "פתיח", main: "הסרטון", outro: "סיום"};

function _dvzMatchesEpisode(name, episode) {
  return name === episode || name.startsWith(episode + "_") || name.startsWith(episode + ".");
}

// ריצה אחרונה (התוצר החדש ביותר) וסטטוס חבילת הפרסום האחרונה - לכל פרק
async function _dvzLoadEpisodeMeta() {
  const meta = {};
  const [outputs, packages] = await Promise.all([
    fetch("/api/dataviz/outputs").then(_dvzJson).catch(() => ({})),
    fetch("/api/dataviz/packages").then(_dvzJson).catch(() => ({})),
  ]);
  for (const ep of dvzState.episodes) {
    const last = (outputs.outputs || []).find(out => _dvzMatchesEpisode(out.name, ep.name));
    const pack = (Array.isArray(packages) ? packages : []).find(p => _dvzMatchesEpisode(p.name, ep.name));
    const views = (Array.isArray(packages) ? packages : []).filter(p => _dvzMatchesEpisode(p.name, ep.name) && p.stats)
      .reduce((sum, p) => sum + (p.stats.views || 0), 0);   // גל 44: הצפיות שנמשכו לאחרונה
    meta[ep.name] = {lastRun: last ? last.mtime : 0, lastMode: last ? last.mode : "", publish: pack ? pack.status : "", views};
  }
  dvzState.meta = meta;
}

function _dvzThumbUrl(name, pos, scale, extra) {
  return "/api/dataviz/preview_frame?" + new URLSearchParams({episode: name, pos: String(pos), scale: String(scale), ...(extra || {})}).toString();
}

function _dvzCardThumb(ep) {
  const img = document.createElement("img");
  img.className = "dvz-card-thumb";
  img.loading = "lazy";
  img.alt = "";
  img.src = _dvzThumbUrl(ep.name, 0.75, 0.2);
  img.onerror = () => { img.hidden = true; };
  return img;
}

function _dvzRelativeDate(seconds) {
  if (!seconds) return "";
  const days = Math.floor((Date.now() / 1000 - seconds) / 86400);
  return days <= 0 ? "היום" : days === 1 ? "אתמול" : `לפני ${days} ימים`;
}

function _dvzCardBadges(ep) {
  const box = document.createElement("div");
  box.className = "dvz-card-badges";
  const badge = (text, cls) => { const b = document.createElement("span"); b.className = "dvz-badge" + (cls ? " " + cls : ""); b.textContent = text; box.appendChild(b); };
  const meta = dvzState.meta[ep.name] || {};
  if (ep.hidden) badge("🗄️ מוסתר", "is-hidden-badge");
  if (meta.lastRun) badge(`🕘 ${_dvzRelativeDate(meta.lastRun)} · ${DVZ_MODE_LABELS[meta.lastMode] || meta.lastMode}`);
  else if (ep.valid) badge("🆕 עוד לא הורץ");
  if (meta.publish) badge(DVZ_PUBLISH_LABELS[meta.publish] || meta.publish);
  if (meta.views) badge(`👁 ${Number(meta.views).toLocaleString("he-IL")}`);
  if (ep.edited) badge("✏️ הגדרות ששונו");
  if (ep.series && ep.series.name) badge(`📚 ${ep.series.name}` + (ep.series.number ? ` #${ep.series.number}` : ""), "is-series");   // גל 41
  _dvzTagChips(ep, box);   // גל 53 (44-dataviz-editor.js)
  return box;
}

// --- חיפוש, מיון וסינון ---
function dvzRenderEpisodes() {
  const list = document.getElementById("dvzEpisodes");
  const query = document.getElementById("dvzSearch").value.trim().toLowerCase();
  const chart = document.getElementById("dvzChartFilter").value;
  const sort = document.getElementById("dvzSort").value;
  // 21.10.2026 (סבב הפישוט): בלי פרקים - רק כפתור גדול אחד (שאר הכלים של הרשימה מוסתרים, 27-dataviz-pro.css)
  document.querySelector(".dvz-episodes-pane").classList.toggle("dvz-empty", !dvzState.episodes.length);
  if (!dvzState.episodes.length) {
    const big = _dvzEdEl("button", "btn-primary dvz-new-big", "➕ פרק חדש");
    big.type = "button";
    big.id = "dvzNewBigBtn";
    big.onclick = () => dvzOpenNew();
    const box = _dvzEdEl("div", "empty-msg dvz-empty-box");
    box.append(big, _dvzEdEl("p", "hint", "מתיקייה עם קובצי נתונים - העורך בוחר הכל ומסביר כל בחירה."));
    const hidden = document.getElementById("dvzHiddenCount").textContent;
    if (hidden) {
      const show = _dvzEdEl("button", "btn-xs btn-ghost", `🗄️ הצג מוסתרים ${hidden}`);
      show.type = "button";
      show.onclick = () => { document.getElementById("dvzShowHidden").checked = true; dvzToggleHidden(true); };
      box.append(show);
    }
    list.replaceChildren(box);
    return;
  }
  const shown = dvzState.episodes.filter(ep => (!chart || ep.chart === chart)
    && (!query || _dvzEpisodeSearchText(ep).includes(query)));   // גל 53: גם #תגית ותיקייה
  const lastRun = (ep) => (dvzState.meta[ep.name] || {}).lastRun || 0;
  shown.sort((a, b) => sort === "name" ? a.name.localeCompare(b.name)
    : sort === "title" ? (a.title || a.name).localeCompare(b.title || b.name, "he")
    : lastRun(b) - lastRun(a) || (a.title || a.name).localeCompare(b.title || b.name, "he"));
  if (!shown.length) {
    list.innerHTML = '<div class="empty-msg">אין פרקים שמתאימים לחיפוש.</div>';
    return;
  }
  list.replaceChildren(...shown.map(_dvzEpisodeWrap));
  _dvzGroupByFolder(list);   // גל 53
  for (const card of list.querySelectorAll(".dvz-card")) {
    const on = card.dataset.episode === dvzState.selected;
    card.classList.toggle("selected", on);
    card.setAttribute("aria-pressed", on ? "true" : "false");
  }
}

// --- תצוגה חיה ---
let _dvzPreviewUrl = null;

// שינויים שעוד לא נשמרו מוצגים בתצוגה - מהעורך המלא (גל 59: גם הכותרת, התרשים והערכה - הטופס הנפרד יצא)
function _dvzPreviewParams() {
  const params = {};
  const runChart = document.getElementById("dvzChart").value;
  if (runChart) params.chart = runChart;
  const draft = _dvzDraftParam();   // גל 39: שינויים מהעורך המלא שעוד לא נשמרו
  if (draft) params.draft = draft;
  return params;
}

function _dvzPosition() {
  return parseInt(document.getElementById("dvzPreviewPos").value, 10) / 1000;
}

function dvzPreviewSoon() {
  uiDebounce("dvz:preview", dvzLoadPreview, dvzState.animate ? 600 : 220);   // 20.10.2026: בתצוגה החיה - אחרי שמפסיקים להקליד
}

async function dvzLoadPreview() {
  if (!dvzState.selected) return;
  const img = document.getElementById("dvzPreviewImg");
  const busy = document.getElementById("dvzPreviewBusy");
  const info = document.getElementById("dvzPreviewInfo");
  const request = uiLatest("dvz:preview");
  busy.hidden = false;
  try {
    const url = dvzState.animate ? _dvzClipUrl(dvzState.selected, _dvzPosition().toFixed(3), {..._dvzPreviewParams(), live: "1"})   // גל 53; 20.10: חי
      : _dvzThumbUrl(dvzState.selected, _dvzPosition().toFixed(3), 0.5, _dvzPreviewParams());
    const resp = await fetch(url, {signal: request.signal});
    if (resp.status === 409 && !request.current()) return;   // 20.10.2026: הוחלפה בבקשה חדשה יותר
    if (!resp.ok) throw new Error((await _dvzJson(resp)).error || "התצוגה נכשלה");
    const blob = await resp.blob();
    if (!request.current()) return;
    if (_dvzPreviewUrl) URL.revokeObjectURL(_dvzPreviewUrl);
    _dvzPreviewUrl = URL.createObjectURL(blob);
    img.src = _dvzPreviewUrl;
    dvzState.previewAxes = dvzState.animate ? null : JSON.parse(decodeURIComponent(resp.headers.get("X-Frame-Axes") || "null"));   // 20.10.2026
    const index = parseInt(resp.headers.get("X-Frame-Index") || "0", 10);
    const count = parseInt(resp.headers.get("X-Frame-Count") || "0", 10);
    // גל 59: התאריך והזמן בסרטון (בהם חושבים); מספר הפריים בריחוף
    const fps = parseFloat(resp.headers.get("X-Frame-Fps") || "0");
    const date = decodeURIComponent(resp.headers.get("X-Frame-Date") || "");
    const kind = DVZ_KIND_LABELS[resp.headers.get("X-Frame-Kind")] || "";
    const frame = `פריים ${index + 1} מתוך ${count}`;
    info.title = frame;
    info.textContent = dvzState.animate ? "▶ 3 שניות סביב הרגע הזה"
      : fps ? [date && "📅 " + date, `⏱ ${_dvzClock(index / fps)} / ${_dvzClock(count / fps)}`, kind].filter(Boolean).join(" · ")
      : `${frame} · ${kind}`;
    info.classList.remove("bad");
  } catch (e) {
    if (uiIsAbort(e)) return;
    info.textContent = "⚠️ " + e.message;
    info.classList.add("bad");
  } finally {
    if (request.current()) busy.hidden = true;
  }
  _dvzMarkStrip();
  _dvzMaybeReloadMarkers();   // גל 53
  uiBus.emit("dvz:preview-loaded");   // 27.10.2026: עריכה על התצוגה, לאורך, לפני / אחרי (85-dataviz-plus.js)
}

// --- רצועת 10 פריימים לאורך הסרטון ---
const DVZ_STRIP_POSITIONS = [0.02, 0.12, 0.22, 0.33, 0.44, 0.55, 0.66, 0.77, 0.88, 0.98];

function _dvzRenderStrip() {
  const strip = document.getElementById("dvzStrip");
  strip.replaceChildren(...DVZ_STRIP_POSITIONS.map(pos => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("role", "listitem");
    btn.dataset.pos = String(pos);
    btn.title = `הרגע ב-${Math.round(pos * 100)}% מהסרטון`;
    btn.setAttribute("aria-label", btn.title);
    const img = document.createElement("img");
    img.alt = "";
    img.dataset.src = _dvzThumbUrl(dvzState.selected, pos, 0.2);
    btn.appendChild(img);
    btn.onclick = () => { document.getElementById("dvzPreviewPos").value = String(Math.round(pos * 1000)); dvzLoadPreview(); };
    return btn;
  }));
  _dvzMarkStrip();
  _dvzLoadOneByOne([...strip.querySelectorAll("img[data-src]")]);
}

// גל 48: הפריימים של הרצועה נטענים אחד אחרי השני ולא כל העשרה יחד - הדפדפן פותח עד 6 חיבורים לשרת,
// ועשר בקשות ציור תפסו את כולם: פעולה של המשתמש (שמירה, אשף, הרצה) חיכתה מאחוריהן במחשב איטי.
// כשהרצועה מצוירת מחדש (פרק אחר) השרשרת הישנה נעצרת - התמונות שלה כבר לא בדף.
function _dvzLoadOneByOne(images) {
  const next = () => {
    const img = images.shift();
    if (!img || !img.isConnected) return;
    img.onload = img.onerror = next;
    img.src = img.dataset.src;
  };
  next();
}

function _dvzMarkStrip() {
  const pos = _dvzPosition();
  const nearest = DVZ_STRIP_POSITIONS.reduce((best, p) => Math.abs(p - pos) < Math.abs(best - pos) ? p : best, DVZ_STRIP_POSITIONS[0]);
  for (const btn of document.querySelectorAll("#dvzStrip button")) btn.setAttribute("aria-current", String(Number(btn.dataset.pos) === nearest));
}

// --- השוואה: סוגי תרשים, או בהיר מול כהה, על אותו רגע ---
function dvzCompare(kind) {
  const box = document.getElementById("dvzCompareBox");
  if (!box.hidden && box.dataset.kind === kind) { box.hidden = true; return; }
  box.hidden = false;
  box.dataset.kind = kind;
  box.classList.toggle("dvz-compare-2", kind === "themes");
  const pos = _dvzPosition().toFixed(3);
  const ep = dvzState.episodes.find(e => e.name === dvzState.selected) || {};
  const base = _dvzPreviewParams();   // סבב הייצוב: גם מה שעוד לא נשמר (הטיוטה וסוג התרשים להרצה) - כמו התצוגה החיה
  const options = kind === "charts"
    ? Object.entries(DVZ_CHART_LABELS).filter(([value]) => value !== "map_race" || ep.has_map).map(([value, label]) => ({value, label, params: {...base, chart: value}, current: (base.chart || dvzEd.draft.chart || ep.chart) === value}))
    : [["light", "בהיר"], ["dark", "כהה"]].map(([value, label]) => ({value, label, params: {...base, theme: value}, current: (dvzEd.draft.theme || ep.theme) === value}));
  box.replaceChildren(...options.map(option => {
    const figure = document.createElement("figure");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = option.current ? "is-current" : "";
    btn.title = kind === "charts" ? `להריץ כ"${option.label}"` : `ערכה ${option.label} - לשמירה בהגדרות הפרק`;
    const img = document.createElement("img");
    img.loading = "lazy";
    img.alt = option.label;
    img.src = _dvzThumbUrl(dvzState.selected, pos, 0.2, option.params);
    btn.appendChild(img);
    btn.onclick = () => _dvzPickCompared(kind, option.value);
    const caption = document.createElement("figcaption");
    caption.textContent = option.label + (option.current ? " ✓" : "");
    figure.append(btn, caption);
    return figure;
  }));
}

function _dvzClock(seconds) {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

async function _dvzPickCompared(kind, value) {
  if (kind === "charts") {
    document.getElementById("dvzChart").value = value;
    if (typeof _dvzRunOverridesSummary === "function") _dvzRunOverridesSummary();
  } else {
    // גל 59: הערכה נבחרת כטיוטה בעורך המלא (שדה "ערכת צבעים" ב"⭐ בסיסי") - "שמור שינויים" כדי שתחול על כל הרצה
    const editor = document.getElementById("dvzEditor");
    if (!editor.open || !dvzEd.data) { editor.open = true; await dvzLoadEditor(); }
    _dvzStage("theme", value);
    _dvzRenderEditor();
    uiToast("הערכה נבחרה - \"שמור שינויים\" כדי שתחול על כל הרצה", "ok");
  }
  dvzCompare(kind);
  dvzCompare(kind);   // סוגר ופותח מחדש - הסימון ✓ זז לבחירה החדשה
  dvzLoadPreview();
}

// --- אורך הסרטון וזמן הרינדור המשוערים ---
function _dvzDuration(seconds) {
  return seconds >= 60 ? `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, "0")} דק'` : `${Math.round(seconds)} שנ'`;
}

async function _dvzLoadEstimate(name) {
  if (!name || dvzState.estimates[name]) return;
  try {
    const resp = await fetch("/api/dataviz/estimate?episode=" + encodeURIComponent(name));
    if (resp.ok) dvzState.estimates[name] = await resp.json();
  } catch (e) { /* בלי אומדן */ }
}

function _dvzRenderEstimate() {
  const box = document.getElementById("dvzEstimate");
  if (!box) return;
  const est = dvzState.estimates[dvzState.selected];
  if (!est && dvzState.selected) {   // סבב הייצוב: שמירה מוחקת את האומדן (ההגדרות השתנו) - נטען מחדש, לא נעלם עד בחירה חוזרת
    const name = dvzState.selected;
    _dvzLoadEstimate(name).then(() => { if (dvzState.estimates[name] && dvzState.selected === name) _dvzRenderEstimate(); });
  }
  const mode = document.getElementById("dvzMode").value;
  const info = est && est.modes && est.modes[mode === "stills" || mode === "share" ? "full" : mode];
  if (!info) { box.textContent = ""; return; }
  const runs = est.learned_runs === 1 ? " · לפי ריצה אחת" : est.learned_runs ? ` · לפי ${est.learned_runs} ריצות` : "";
  if (mode === "shorts") {   // 23.10.2026 (המלצה 10): כמה Shorts, האורך של כל אחד וזמן הרינדור (בגודל לאורך)
    box.textContent = info.count ? `📱 ${info.count} Shorts, כל אחד ${_dvzDuration(info.seconds)} · רינדור משוער: כ-${_dvzDuration(info.render_seconds)}` + runs
      : "📱 לא נמצאו רגעים דרמטיים לפרק הזה - בלי Shorts";
    return;
  }
  box.textContent = mode === "stills" || mode === "share"
    ? (mode === "share" ? "🖼️ תמונה אחת ו-GIF של כמה שניות · פחות מדקה" : `🖼️ כ-10 פריימים מתוך ${info.frames} · כמה שניות`)
    : `⏱ אורך: ${_dvzDuration(info.seconds)} (${info.frames} פריימים) · רינדור משוער: כ-${_dvzDuration(info.render_seconds)}`
      + runs;   // גל 54: האומדן לומד מריצות אמיתיות
}

// נקרא מ-_dvzApplySelection (42-dataviz-screen.js)
async function dvzSelectionChanged(ep) {
  uiBus.emit("dvz:selection-changed", ep);   // 27.10.2026: הטווח והשימור שייכים לפרק (85-dataviz-plus.js)
  document.getElementById("dvzCompareBox").hidden = true;
  if (dvzEd.data && dvzEd.data.episode !== dvzState.selected) {   // טיוטה שייכת לפרק שלה
    dvzEd = {data: null, tab: dvzEd.tab, draft: {}, unset: new Set()};
    _dvzResetUndo();   // גל 53: ההיסטוריה שייכת לפרק שלה
    _dvzSyncDraftBar();
    if (document.getElementById("dvzEditor").open) dvzLoadEditor(); else document.getElementById("dvzEditorBody").replaceChildren();
  }
  _dvzSyncRunLang(ep);   // גל 55: בחירת השפה רק לפרק שיש לו תרגום
  if (!ep || !ep.valid) return;
  _dvzDataSelectionChanged();   // גל 40: בדיקת הנתונים ברקע, וחלון הנתונים לפרק החדש
  _dvzRenderStrip();
  dvzLoadPreview();
  await _dvzLoadEstimate(ep.name);
  if (dvzState.selected === ep.name) _dvzRenderEstimate();
}

function _dvzInitStudio() {
  document.getElementById("dvzChart").addEventListener("change", dvzPreviewSoon);
}

// הקובץ נטען לפי דרישה (כשעוברים למסך) - מאתחל את עצמו
_dvzInitStudio();
