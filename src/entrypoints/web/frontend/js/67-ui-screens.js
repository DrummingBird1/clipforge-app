// ============================================================================
// גל 19 - שאר המסכים בעיצוב החדש: עבודות (תמונה ממוזערת, סינון, הרצה מהכרטיס),
// תוצאות (אריחי מספרים), גלריה (תצוגה בריחוף), אישור קליפים (A/R במקלדת),
// טפסי הגדרות (תווית קבועה + אימות), סטטיסטיקות (אריחים וגרפים מה-tokens),
// ודיאלוגים (כפתור סגירה, Esc, מלכודת פוקוס והחזרת פוקוס).
// ============================================================================

function _uiCssVar(name, fallback) {
  const value = getComputedStyle(document.body).getPropertyValue(name).trim();
  return value || fallback || "";
}

function _uiTile(label, value, tone) {
  const tile = document.createElement("div");
  tile.className = "stat-tile";
  if (tone) tile.dataset.tone = tone;
  const v = document.createElement("span");
  v.className = "stat-tile-value";
  v.textContent = value;
  const l = document.createElement("span");
  l.className = "stat-tile-label";
  l.textContent = label;
  tile.append(v, l);
  return tile;
}

// --- 📋 עבודות ---
let _veJobsStatus = "all";
let _veJobsTargets = new Set();

function _veJobStatusKey(badge) {
  return badge.cls === "running" ? "running" : (badge.cls === "ok" ? "ok" : (badge.cls === "bad" ? "bad" : "never"));
}

function setVeJobsStatusFilter(status) {
  _veJobsStatus = status;
  for (const btn of document.querySelectorAll("#veJobsStatusFilter button")) btn.setAttribute("aria-pressed", String(btn.dataset.status === status));
  filterVeJobs();
}

function filterVeJobs() {
  const q = (_veEl("veJobsSearch").value || "").trim().toLowerCase();
  let shown = 0, total = 0;
  for (const card of document.querySelectorAll("#veJobsList .ve-job-card")) {
    total++;
    const targets = (card.dataset.targets || "").split(" ").filter(Boolean);
    const visible = (!q || (card.dataset.search || "").includes(q))
      && (_veJobsStatus === "all" || card.dataset.status === _veJobsStatus)
      && (!_veJobsTargets.size || targets.some(t => _veJobsTargets.has(t)));
    card.hidden = !visible;
    if (visible) shown++;
  }
  _veEl("veJobsCount").textContent = total ? (shown === total ? `${total} פרויקטים` : `${shown} מתוך ${total}`) : "";
}

function _veRenderJobsTargetFilter(schema, projects) {
  const box = _veEl("veJobsTargetFilter");
  const used = new Set(projects.flatMap(p => p.targets || []));
  box.replaceChildren(...[...used].filter(id => schema.targets[id]).map(id => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.target = id;
    btn.setAttribute("aria-checked", String(_veJobsTargets.has(id)));
    btn.textContent = `${schema.targets[id].icon} ${schema.targets[id].label}`;
    btn.onclick = () => {
      if (_veJobsTargets.has(id)) _veJobsTargets.delete(id); else _veJobsTargets.add(id);
      btn.setAttribute("aria-checked", String(_veJobsTargets.has(id)));
      filterVeJobs();
    };
    return btn;
  }));
}

refreshVeJobs = async function () {
  const list = _veEl("veJobsList");
  uiSkeleton(list, 3, "card");
  const request = uiLatest("ui:jobs");
  let projects = [], runs = [], queue = {pending: 0};
  try {
    [projects, runs, queue] = await Promise.all([
      fetch("/api/editor_projects", {signal: request.signal}).then(r => r.json()).then(d => d.projects || []),
      fetch("/api/video_editor/runs", {signal: request.signal}).then(r => r.json()).then(d => Array.isArray(d) ? d : (d.runs || [])).catch(() => []),
      fetch("/api/queue_status", {signal: request.signal}).then(r => r.json()).catch(() => ({pending: 0})),
    ]);
  } catch (e) {
    if (!uiIsAbort(e) && request.current()) list.innerHTML = '<div class="empty-msg bad">⚠️ טעינת הפרויקטים נכשלה</div>';
    return;
  }
  if (!request.current()) return;
  const running = runs.find(r => r.status === "running");
  _veEl("veJobsQueue").textContent = running
    ? `🎬 רץ עכשיו: ${running.folder ? running.folder.split(/[\\/]/).pop() : ""}${queue.pending ? ` · ${queue.pending} ממתינות בתור` : ""}`
    : (queue.pending ? `🎬 ${queue.pending} ממתינות בתור` : "🎬 אין ריצה פעילה");
  if (!projects.length) {
    const empty = _uiEmpty("📋", "עוד אין פרויקטים", "בחר תיקייה - כל מה שתעשה בה נשמר אוטומטית כפרויקט.");
    empty.classList.add("ve-jobs-empty");
    list.replaceChildren(empty);
    _veEl("veJobsCount").textContent = "";
    return;
  }
  const schema = await _veLoadSchema();
  _veRenderJobsTargetFilter(schema, projects);
  list.replaceChildren(...projects.map(project => _veJobCard(project, runs, schema)));
  filterVeJobs();
};

function _veJobCard(project, runs, schema) {
  const lastRun = runs.find(r => r.folder && project.folder && r.folder.toLowerCase() === project.folder.toLowerCase());
  const badge = _veJobStatusBadge(lastRun);
  const card = document.createElement("article");
  card.className = "ve-job-card" + (project.folder === state.folder ? " ve-job-current" : "") + (project.folder_exists ? "" : " ve-job-missing");
  card.dataset.folder = project.folder;
  card.dataset.status = _veJobStatusKey(badge);
  card.dataset.targets = (project.targets || []).join(" ");
  card.dataset.search = `${project.name || ""} ${project.folder || ""} ${project.profile_name || ""}`.toLowerCase();

  const thumb = document.createElement("div");
  thumb.className = "ve-job-thumb";
  if (project.first_file) {
    const img = document.createElement("img");
    img.loading = "lazy";
    img.alt = "";
    img.src = "/api/video_editor/file_thumbnail?path=" + encodeURIComponent(project.first_file);
    img.onerror = () => img.remove();
    thumb.appendChild(img);
  } else {
    const empty = document.createElement("div");
    empty.className = "ve-job-thumb-empty";
    empty.textContent = "🎬";
    thumb.appendChild(empty);
  }
  const status = document.createElement("span");
  status.className = "ve-job-status status-pill " + badge.cls;
  status.dataset.status = card.dataset.status === "never" ? "cancelled" : card.dataset.status;
  status.textContent = badge.text.replace(/^[✅❌⏳]️?\s*/u, "");
  thumb.appendChild(status);

  const body = document.createElement("div");
  body.className = "ve-job-body";
  const title = document.createElement("div");
  title.className = "ve-job-title";
  title.textContent = "📁 " + (project.name || project.folder);
  title.title = project.folder;
  const meta = document.createElement("div");
  meta.className = "ve-job-meta";
  const bits = [project.folder];
  if (project.profile_name) bits.push("🗂️ " + project.profile_name);
  if (project.brand_kit) bits.push("🎨 " + project.brand_kit);
  if (project.clip_edit_count) bits.push(`✂️ ${project.clip_edit_count} קליפים עם עריכה`);
  if (project.updated_at) bits.push("עודכן " + uiRelativeTime(project.updated_at));
  meta.textContent = bits.join(" · ");
  const chips = document.createElement("div");
  chips.className = "ve-chips";
  for (const id of project.targets || []) {
    const t = schema.targets[id];
    if (!t) continue;
    const chip = document.createElement("span");
    chip.className = "ve-chip";
    chip.textContent = `${t.icon} ${t.label}`;
    chips.appendChild(chip);
  }
  const actions = document.createElement("div");
  actions.className = "ve-job-actions";
  const open = document.createElement("button");
  open.type = "button"; open.className = "btn-sm"; open.textContent = "📂 פתח"; open.disabled = !project.folder_exists;
  open.onclick = () => openVeJob(project.folder);
  const run = document.createElement("button");
  run.type = "button"; run.className = "btn-sm btn-run"; run.textContent = "▶ הרץ"; run.disabled = !project.folder_exists || !!state.running;
  run.title = "טוען את הפרויקט (הגדרות, יעדים, עריכות ותור) ומריץ אותו";
  run.onclick = () => runVeJob(project.folder, project.name || project.folder);
  const remove = document.createElement("button");
  remove.type = "button"; remove.className = "btn-sm btn-ghost ve-job-del"; remove.textContent = "🗑️";
  remove.title = "מחק את הפרויקט השמור (הקבצים עצמם לא נמחקים)";
  remove.setAttribute("aria-label", "מחק פרויקט");
  remove.onclick = async () => {
    if (!await veConfirm(`למחוק את הפרויקט השמור של "${project.name}"? (עריכות הקליפים והיעדים שלו - לא הסרטונים)`, {okLabel: "🗑️ מחק", danger: true})) return;
    await fetch("/api/editor_projects?folder=" + encodeURIComponent(project.folder), {method: "DELETE"});
    refreshVeJobs();
  };
  actions.append(open, run, remove);
  body.append(title, meta, chips, actions);
  card.append(thumb, body);
  return card;
}

async function runVeJob(folder, name) {
  if (!await veConfirm(`להריץ את "${name}" עם ההגדרות, היעדים, עריכות הקליפים והתור השמורים שלו?`, {okLabel: "▶ הרץ"})) return;
  openVeJob(folder);
  const started = Date.now();
  while (Date.now() - started < 10000) {
    if (state.folder === folder && _veProjectLoadedFor === folder && !document.getElementById("runBtn").disabled) break;
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  if (state.folder !== folder || document.getElementById("runBtn").disabled) {
    uiToast("טעינת הפרויקט להרצה לא הסתיימה - נסה ▶ הרץ מהעורך", "bad");
    return;
  }
  // אם ההגדרות שנשמרו בפרויקט שונות מהנוכחיות - מחילים אותן לפני ההרצה
  const banner = _veEl("veProjectBanner");
  if (banner && !banner.hidden && typeof applyVeProjectRecipe === "function") applyVeProjectRecipe();
  await runScript();
}

// --- 📋 תוצאות הריצה: אריחי מספרים ---
uiBus.on("ve:results-shown", (manifest) => {
  const counts = manifest.counts || {};
  const files = manifest.files || [];
  const sizeMb = files.reduce((sum, f) => sum + (Number(f.output_size_mb) || 0), 0);
  const renderSeconds = files.filter(f => f.render_seconds).map(f => Number(f.render_seconds));
  const tiles = [
    _uiTile("נוצרו", String(counts.files_created || 0), counts.files_created ? "ok" : ""),
    _uiTile("נכשלו", String(counts.errors || 0), counts.errors ? "bad" : ""),
    _uiTile("דולגו", String(counts.skipped || 0), counts.skipped ? "warn" : ""),
  ];
  if (manifest.elapsed_seconds) tiles.push(_uiTile("זמן כולל", uiFormatDuration(manifest.elapsed_seconds), "accent"));
  if (renderSeconds.length) tiles.push(_uiTile("ממוצע לקובץ", uiFormatDuration(renderSeconds.reduce((a, b) => a + b, 0) / renderSeconds.length)));
  if (sizeMb) tiles.push(_uiTile("גודל הפלט", sizeMb >= 1024 ? `${(sizeMb / 1024).toFixed(2)} GB` : `${sizeMb.toFixed(1)} MB`));
  _veEl("veResultsTiles").replaceChildren(...tiles);
});

// --- 🖼️ גלריה: תצוגה מקדימה בריחוף + מקלדת ---
let _uiGalleryHoverTimer = null;

function _uiGalleryStopPreview(card) {
  clearTimeout(_uiGalleryHoverTimer);
  if (!card) return;
  card.classList.remove("previewing");
  const video = card.querySelector(".gallery-hover-video");
  if (video) { video.pause(); video.removeAttribute("src"); video.load(); video.remove(); }
}

function _uiSetupGalleryHover() {
  const list = document.getElementById("galleryList");
  list.addEventListener("pointerover", (e) => {
    const card = e.target.closest(".gallery-card");
    if (!card || card.querySelector(".gallery-hover-video") || e.pointerType === "touch") return;
    clearTimeout(_uiGalleryHoverTimer);
    _uiGalleryHoverTimer = setTimeout(() => {
      if (!card.matches(":hover")) return;
      const video = document.createElement("video");
      video.className = "gallery-hover-video";
      video.muted = true; video.loop = true; video.playsInline = true; video.preload = "auto";
      video.src = "/api/clips/stream?path=" + encodeURIComponent(card.dataset.path);
      video.addEventListener("canplay", () => card.classList.add("previewing"), {once: true});
      card.prepend(video);
      video.play().catch(() => {});
    }, 380);
  });
  list.addEventListener("pointerout", (e) => {
    const card = e.target.closest(".gallery-card");
    if (card && !card.contains(e.relatedTarget)) _uiGalleryStopPreview(card);
  });
}

const _loadGalleryBeforeScreens = loadGallery;
loadGallery = async function (...args) {
  const result = await _loadGalleryBeforeScreens(...args);
  for (const card of document.querySelectorAll("#galleryList .gallery-card")) {
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", card.querySelector(".gallery-card-name")?.textContent || "קליפ");
    card.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); card.click(); } });
  }
  return result;
};

// --- ✅ אישור קליפים: A אשר · R דחה · ↑/↓ מעבר ---
function _uiApprovalCards() { return [...document.querySelectorAll("#approvalsList .approval-card")]; }

function _uiSetActiveApproval(card) {
  for (const c of _uiApprovalCards()) c.classList.toggle("active", c === card);
  if (card) { card.scrollIntoView({block: "nearest", behavior: "smooth"}); }
}

const _loadApprovalsBeforeScreens = loadApprovals;
loadApprovals = async function (...args) {
  const result = await _loadApprovalsBeforeScreens(...args);
  const list = document.getElementById("approvalsList");
  let keys = document.getElementById("approvalKeys");
  if (!keys) {
    keys = document.createElement("div");
    keys.id = "approvalKeys";
    keys.className = "approval-keys";
    keys.innerHTML = '<span><kbd>A</kbd> אשר</span><span><kbd>R</kbd> דחה</span><span><kbd>↑</kbd> <kbd>↓</kbd> מעבר בין קליפים</span>';
    list.before(keys);
  }
  const cards = _uiApprovalCards();
  keys.hidden = !cards.length;
  for (const card of cards) card.addEventListener("click", () => _uiSetActiveApproval(card));
  _uiSetActiveApproval(cards[0]);
  return result;
};

const _decideApprovalBeforeScreens = decideApproval;
decideApproval = async function (pendingId, approved) {
  const card = document.getElementById("approvalCard" + pendingId);
  const cards = _uiApprovalCards();
  const next = cards[cards.indexOf(card) + 1] || cards[cards.indexOf(card) - 1];
  const result = await _decideApprovalBeforeScreens(pendingId, approved);
  if (!document.getElementById("approvalCard" + pendingId)) {
    _uiSetActiveApproval(next && next.isConnected ? next : _uiApprovalCards()[0]);
    uiToast(approved ? "✅ הקליפ אושר לרינדור" : "הקליפ נדחה", approved ? "ok" : "");
  }
  return result;
};

document.addEventListener("keydown", (e) => {
  const panel = document.querySelector('[data-tab-panel="approvals"]');
  if (!panel || panel.hidden || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.target.closest("input, textarea, select, [contenteditable='true']") || document.querySelector(".modal-bg.show")) return;
  const cards = _uiApprovalCards();
  if (!cards.length) return;
  const active = cards.find(c => c.classList.contains("active")) || cards[0];
  const index = cards.indexOf(active);
  if (e.code === "KeyA" || e.code === "KeyR") {
    e.preventDefault();
    const btn = active.querySelector(e.code === "KeyA" ? ".approval-approve-btn" : ".approval-reject-btn");
    if (btn && !btn.disabled) btn.click();
  } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    _uiSetActiveApproval(cards[Math.max(0, Math.min(cards.length - 1, index + (e.key === "ArrowDown" ? 1 : -1)))]);
  }
});

// --- טפסי הגדרות: תווית קבועה במקום placeholder, ואימות בזמן הקלדה ---
const UI_FIELD_RULES = {
  gsWebhook: {test: v => !v || /^https:\/\/(discord|discordapp)\.com\/api\/webhooks\//.test(v), message: "כתובת Webhook של דיסקורד מתחילה ב-https://discord.com/api/webhooks/"},
  rssUrl: {test: v => !v || /^https?:\/\/\S+\.\S+/.test(v), message: "כתובת מלאה, למשל https://example.com/feed"},
  rssChannel: {test: v => !v || /^\d{15,21}$/.test(v), message: "מזהה ערוץ דיסקורד הוא מספר של 15-21 ספרות"},
  steamChannel: {test: v => !v || /^\d{15,21}$/.test(v), message: "מזהה ערוץ דיסקורד הוא מספר של 15-21 ספרות"},
  steamAppId: {test: v => !v || /^\d{1,10}$/.test(v), message: "App ID הוא מספר (מופיע בכתובת של המשחק בחנות)"},
  schTime: {test: v => /^([01]?\d|2[0-3]):[0-5]\d$/.test(v), message: "שעה בפורמט HH:MM, למשל 03:00"},
  schInterval: {test: v => Number(v) >= 1, message: "לפחות שעה אחת"},
  rsCaptureVoiceChannelId: {test: v => !v || /^\d{15,21}$/.test(v), message: "מזהה ערוץ קול הוא מספר של 15-21 ספרות"},
  rsClipHotkey: {test: v => !v || /^([a-z]+\+)*[a-z0-9]+$/i.test(v.replace(/\s/g, "")), message: "צירוף מקשים כמו ctrl+alt+c"},
};
const UI_REQUIRED_ON_ADD = {addRssFeed: ["rssName", "rssUrl", "rssChannel"], addSteamGame: ["steamName", "steamAppId", "steamChannel"], addScheduledTask: ["schTime"]};

function _uiValidateField(input, {required = false} = {}) {
  const field = input.closest(".form-field");
  const rule = UI_FIELD_RULES[input.id];
  const value = input.value.trim();
  let message = "";
  if (required && !value) message = "שדה חובה";
  else if (rule && (value || required) && !rule.test(value)) message = rule.message;
  if (field) {
    field.classList.toggle("is-invalid", !!message);
    field.classList.toggle("is-valid", !message && !!value && !!rule);
    const error = field.querySelector(".form-error");
    if (error) error.textContent = message;
  }
  input.setAttribute("aria-invalid", String(!!message));
  return !message;
}

function _uiEnhanceForms() {
  for (const input of document.querySelectorAll(".tab-content .tc-row > input[placeholder]:not([type=checkbox]):not([type=color]):not([type=search])")) {
    if (input.closest(".form-field") || /^🔍/.test(input.getAttribute("placeholder"))) continue;
    const field = document.createElement("label");
    field.className = "form-field";
    const label = document.createElement("span");
    label.className = "form-label";
    const text = input.getAttribute("placeholder").replace(/^🔍\s*/, "");
    label.textContent = text;
    const error = document.createElement("span");
    error.className = "form-error";
    error.id = input.id ? input.id + "Error" : "";
    if (error.id) input.setAttribute("aria-describedby", error.id);
    input.before(field);
    field.append(label, input, error);
    // נשאר רק רמז-פורמט בתוך השדה (למשל HH:MM), לא כפילות של התווית
    const example = text.match(/\(([^)]*[:0-9][^)]*)\)/);
    input.setAttribute("placeholder", example ? example[1] : "");
    if (UI_FIELD_RULES[input.id]) {
      input.addEventListener("input", () => { if (field.classList.contains("is-invalid")) _uiValidateField(input); });
      input.addEventListener("blur", () => _uiValidateField(input));
    }
  }
  for (const [fnName, ids] of Object.entries(UI_REQUIRED_ON_ADD)) {
    const original = window[fnName];
    if (typeof original !== "function") continue;
    window[fnName] = function (...args) {
      const inputs = ids.map(id => document.getElementById(id)).filter(Boolean);
      const invalid = inputs.filter(input => !_uiValidateField(input, {required: true}));
      if (invalid.length) {
        invalid[0].focus();
        uiToast("יש שדות שצריך לתקן לפני ההוספה", "warn");
        return undefined;
      }
      return original.apply(this, args);
    };
  }
}

// --- 📊 סטטיסטיקות: אריחים, פסים יחסיים וגרפים מה-tokens (חדים גם במסך Retina) ---
function _uiPrepCanvas(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || canvas.width;
  const height = canvas.clientHeight || canvas.height;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  return {ctx, width, height};
}

function _uiGridLines(ctx, width, height, rows) {
  ctx.strokeStyle = _uiCssVar("--color-border");
  ctx.lineWidth = 1;
  for (let i = 1; i < rows; i++) {
    const y = Math.round(height / rows * i) + 0.5;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
  }
}

loadHardwareHistoryGraph = async function () {
  const canvas = document.getElementById("hwHistoryCanvas");
  const {ctx, width, height} = _uiPrepCanvas(canvas);
  const series = [["CPU", "--color-accent"], ["RAM", "--hue-pink"], ["GPU", "--hue-violet"]];
  document.getElementById("hwHistoryLegend").replaceChildren(...series.map(([name, token]) => {
    const item = document.createElement("span");
    const dot = document.createElement("i");
    dot.style.background = `var(${token})`;
    item.append(dot, name);
    return item;
  }));
  _uiGridLines(ctx, width, height, 4);
  try {
    const data = await (await fetch("/api/hardware_history?hours=24")).json();
    const plot = (history, token) => {
      const n = history.length;
      if (n < 2) return;
      const step = width / (n - 1);
      ctx.beginPath();
      ctx.strokeStyle = _uiCssVar(token);
      ctx.lineWidth = 1.6;
      ctx.lineJoin = "round";
      history.forEach((v, i) => {
        const x = i * step, y = height - 2 - (Math.min(100, Math.max(0, v)) / 100 * (height - 4));
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
    };
    plot(data.cpu, "--color-accent");
    plot(data.ram, "--hue-pink");
    if (data.gpu.length && data.gpu.every(v => v !== null)) plot(data.gpu, "--hue-violet");
  } catch (e) { /* לא קריטי - רק תצוגה */ }
};

let _uiClipsLast30 = null;
loadClipsHistoryGraph = async function () {
  const canvas = document.getElementById("clipsHistoryCanvas");
  const {ctx, width, height} = _uiPrepCanvas(canvas);
  _uiGridLines(ctx, width, height, 3);
  try {
    const data = await (await fetch("/api/clips_captured_by_day?days=30")).json();
    const counts = data.counts || [];
    _uiClipsLast30 = counts.reduce((a, b) => a + b, 0);
    _uiRenderStatsTiles();
    if (!counts.length) return;
    const maxCount = Math.max(...counts, 1);
    const barWidth = width / counts.length;
    ctx.fillStyle = _uiCssVar("--color-accent");
    counts.forEach((count, i) => {
      const barHeight = Math.max(count ? 2 : 0, (count / maxCount) * (height - 4));
      const x = i * barWidth + 1.5, w = Math.max(1, barWidth - 3);
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(x, height - barHeight, w, barHeight, [2, 2, 0, 0]); else ctx.rect(x, height - barHeight, w, barHeight);
      ctx.fill();
    });
  } catch (e) { /* לא קריטי */ }
};

let _uiStatsRows = [];
function _uiRenderStatsTiles() {
  const box = document.getElementById("statsTiles");
  if (!box) return;
  const runs = _uiStatsRows.reduce((sum, row) => sum + (row.run_count || 0), 0);
  const avg = runs ? _uiStatsRows.reduce((sum, row) => sum + (row.avg_seconds || 0) * (row.run_count || 0), 0) / runs : 0;
  const recent = _uiLastHistoryRows.filter(r => r.status !== "running");
  const rate = recent.length ? Math.round(recent.filter(r => r.status === "success").length / recent.length * 100) : null;
  const tiles = [_uiTile("ריצות מוצלחות", String(runs), "accent"), _uiTile("זמן ממוצע לריצה", avg ? uiFormatDuration(avg) : "-")];
  if (rate !== null) tiles.push(_uiTile(`הצלחה (${recent.length} אחרונות)`, rate + "%", rate >= 80 ? "ok" : (rate >= 50 ? "warn" : "bad")));
  if (_uiClipsLast30 !== null) tiles.push(_uiTile("קליפים ב-30 יום", String(_uiClipsLast30)));
  box.replaceChildren(...tiles);
}

const _openStatsBeforeScreens = openStats;
openStats = async function (...args) {
  document.getElementById("statsTiles").replaceChildren();
  const statsPromise = fetch("/api/render_stats").then(r => r.json()).catch(() => []);
  const result = await _openStatsBeforeScreens(...args);
  _uiStatsRows = await statsPromise;
  const max = Math.max(1, ..._uiStatsRows.map(r => r.avg_seconds || 0));
  document.querySelectorAll("#statsList .stats-row").forEach((row, i) => {
    const stat = _uiStatsRows[i];
    if (!stat) return;
    const script = row.querySelector(".script");
    if (script) { script.title = stat.script; script.textContent = _uiScriptLabel(String(stat.script).split("/").pop()); }
    const bar = document.createElement("span");
    bar.className = "stats-bar";
    bar.style.width = Math.max(2, (stat.avg_seconds || 0) / max * 100) + "%";
    row.prepend(bar);
  });
  _uiRenderStatsTiles();
  return result;
};

// --- דיאלוגים: ✕ בכותרת, Esc, מלכודת פוקוס, והחזרת הפוקוס למי שפתח ---
const _uiDialogReturnFocus = new WeakMap();
const UI_FOCUSABLE = "button:not([disabled]), [href], input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";

function _uiTopDialog() {
  const open = [...document.querySelectorAll(".modal-bg.show")].filter(bg => bg.querySelector(".modal"));
  return open.sort((a, b) => (parseInt(getComputedStyle(b).zIndex, 10) || 0) - (parseInt(getComputedStyle(a).zIndex, 10) || 0))[0] || null;
}

function _uiCloseDialog(bg) {
  const buttons = [...bg.querySelectorAll(".actions button, .modal-close")];
  const closer = buttons.find(b => !b.classList.contains("modal-close") && /^(סגור|ביטול|✕|חזרה|Close|Cancel|Back)/.test(b.textContent.trim()));
  if (closer) closer.click();
  else bg.classList.remove("show");
}

function _uiEnhanceDialog(bg) {
  const modal = bg.querySelector(":scope > .modal");
  if (!modal) return;
  modal.setAttribute("role", modal.getAttribute("role") || "dialog");
  modal.setAttribute("aria-modal", "true");
  if (!modal.querySelector(":scope > .modal-close")) {
    const close = document.createElement("button");
    close.type = "button";
    close.className = "modal-close";
    close.setAttribute("aria-label", "סגור");
    close.title = "סגור (Esc)";
    close.textContent = "✕";
    close.onclick = () => _uiCloseDialog(bg);
    modal.prepend(close);
  }
  let restoreOverModal = null;   // 22.10.2026: מעל <dialog> מודאלי פתוח (uiOverModal) - הפוקוס עובר אליו ב-rAF שלמטה
  new MutationObserver(() => {
    if (bg.classList.contains("show")) {
      if (!restoreOverModal) restoreOverModal = uiOverModal(bg);
      if (!_uiDialogReturnFocus.has(bg)) _uiDialogReturnFocus.set(bg, document.activeElement);
      requestAnimationFrame(() => {
        if (!modal.contains(document.activeElement)) {
          const first = [...modal.querySelectorAll(UI_FOCUSABLE)].find(el => !el.classList.contains("modal-close") && el.offsetParent);
          (first || modal.querySelector(".modal-close")).focus({preventScroll: true});
        }
      });
      return;
    }
    if (restoreOverModal) {
      restoreOverModal();
      restoreOverModal = null;
    }
    if (_uiDialogReturnFocus.has(bg)) {
      const back = _uiDialogReturnFocus.get(bg);
      _uiDialogReturnFocus.delete(bg);
      if (back && back.isConnected && typeof back.focus === "function") back.focus({preventScroll: true});
    }
  }).observe(bg, {attributes: true, attributeFilter: ["class"]});
}

// סבב ייצוב: חלון שה-HTML שלו נטען עם המסך (frontend_assembly lazy-html) מקבל את מה שחלונות מקבלים
// בטעינת הדף - גם aria-labelledby מהכותרת, כמו ב-_veApplyDialogRoles
uiBus.on("ui:lazy-html", ({nodes}) => {
  for (const bg of nodes.filter(node => node.matches(".modal-bg"))) {
    _uiEnhanceDialog(bg);
    const modal = bg.querySelector(":scope > .modal");
    const title = modal && modal.querySelector("h3[id]");
    if (title && !modal.hasAttribute("aria-labelledby")) modal.setAttribute("aria-labelledby", title.id);
  }
});

function _uiEnhanceDialogs() {
  for (const bg of document.querySelectorAll(".modal-bg")) _uiEnhanceDialog(bg);
  // 22.10.2026: חלון שעבר לתוך <dialog> מודאלי - Escape סוגר רק אותו. ב-capture, לפני המטפל של החלון עצמו (לוח
  // הפקודות נסגר כבר ב-onkeydown של השדה); בלי preventDefault הדפדפן סוגר גם את ה-dialog
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && _uiTopDialog()?.closest("dialog")) e.preventDefault();
  }, true);
  document.addEventListener("keydown", (e) => {
    const bg = _uiTopDialog();
    if (!bg) return;
    if (e.key === "Escape") {
      // מטפלים קיימים (למשל לוח הפקודות) קודם; אם הדיאלוג עדיין פתוח - סוגרים אותו
      setTimeout(() => { if (bg.classList.contains("show")) _uiCloseDialog(bg); }, 0);
    } else if (e.key === "Tab") {
      const items = [...bg.querySelectorAll(UI_FOCUSABLE)].filter(el => el.offsetParent || el === document.activeElement);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      else if (!bg.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
    }
  });
}

function _uiInitScreens() {
  _uiSetupGalleryHover();
  _uiEnhanceForms();
  _uiEnhanceDialogs();
}
