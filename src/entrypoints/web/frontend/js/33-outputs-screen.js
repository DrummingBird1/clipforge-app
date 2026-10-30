// 33-outputs-screen.js - מסך "תוצרים" (23.10.2026): כל הסרטונים שהכלים ייצרו (GET /api/outputs, utils/shared/outputs_index.py),
// עם סינון לפי שם, כלי ותאריך. נטען רק כשפותחים את המסך (frontend_assembly.LAZY_JS["outputs"], וה-HTML ב-lazy-html:outputs).
// הפעולות דרך routes קיימים: ניגון ותמונה ממוזערת של הסטודיו, /api/open_folder, /api/outputs/studio ואז openProject,
// ופרסום כמו בגלריה (/api/clips/tiktok_export ו-youtube_export).
const OUTPUT_TOOL_LABELS = {studio: "🎬 סטודיו", timelapses: "⏱️ טיימלאפס", highlight_reels: "✨ היילייטס", dataviz: "📊 סרטוני נתונים", rocket_shorts: "🚀 Shorts"};
const OUTPUTS_SHOWN = 120;
let _outputs = [];
let _selectedOutput = null;

async function loadOutputs() {
  const list = document.getElementById("outputsList");
  uiSkeleton(list, 3);
  try {
    const res = await fetch("/api/outputs");
    if (!res.ok) throw new Error("טעינת התוצרים נכשלה");
    const data = await res.json();
    _outputs = data.outputs;
    const select = document.getElementById("outputsFilterTool");
    const chosen = select.value;
    select.replaceChildren(new Option("כל הכלים", ""), ...data.tools.map((tool) => new Option(OUTPUT_TOOL_LABELS[tool] || tool, tool)));
    select.value = chosen;
  } catch (e) {
    _outputs = [];
    list.innerHTML = `<div class="empty-msg">${uiEscape(e.message)}</div>`;
    return;
  }
  renderOutputs();
}

function _outputsMatching() {
  const text = document.getElementById("outputsFilterName").value.trim().toLowerCase();
  const tool = document.getElementById("outputsFilterTool").value;
  const days = Number(document.getElementById("outputsFilterDate").value);
  const since = new Date();
  since.setHours(0, 0, 0, 0);
  if (days > 1) since.setDate(since.getDate() - (days - 1));
  return _outputs.filter((item) => (!text || item.name.toLowerCase().includes(text)) && (!tool || item.tool === tool)
    && (!days || item.mtime * 1000 >= since.getTime()));
}

function renderOutputs() {
  const list = document.getElementById("outputsList");
  const matching = _outputsMatching();
  const summary = document.getElementById("outputsSummary");
  summary.textContent = !_outputs.length ? "" : `${matching.length} סרטונים`
    + (matching.length > OUTPUTS_SHOWN ? " · מוצגים רק החדשים ביותר - אפשר לצמצם בסינון" : "");
  list.innerHTML = "";
  if (!matching.length) {
    const empty = document.createElement("div");
    empty.className = "empty-msg";
    empty.textContent = _outputs.length ? "אין תוצרים שמתאימים לסינון." : "אין עדיין תוצרים. סרטון שהסטודיו או כלי אחר ייצרו יופיע כאן.";
    list.appendChild(empty);
    return;
  }
  const grid = document.createElement("div");
  grid.className = "gallery-grid";
  for (const item of matching.slice(0, OUTPUTS_SHOWN)) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "gallery-card output-card";
    card.classList.toggle("selected", _selectedOutput?.path === item.path);
    card.dataset.path = item.path;
    const img = document.createElement("img");
    img.src = "/api/video_editor/output_thumbnail?path=" + encodeURIComponent(item.path);
    img.loading = "lazy";
    img.alt = "";
    img.onerror = () => { img.style.display = "none"; };
    const name = document.createElement("div");
    name.className = "gallery-card-name";
    name.textContent = item.name;
    name.title = item.path;
    const meta = document.createElement("div");
    meta.className = "gallery-card-name hint";
    meta.textContent = [OUTPUT_TOOL_LABELS[item.tool] || item.tool, _formatFileSize(item.size), uiRelativeTime(new Date(item.mtime * 1000))].join(" · ");
    card.append(img, name, meta);
    card.onclick = () => selectOutput(item, card);
    grid.appendChild(card);
  }
  list.appendChild(grid);
}

function selectOutput(item, card) {
  _selectedOutput = item;
  document.getElementById("outputsStatus").textContent = "נבחר: " + item.name;
  for (const btn of document.querySelectorAll(".output-action")) btn.disabled = false;
  const preview = document.getElementById("outputsPreview");
  preview.src = "/api/video_editor/stream?path=" + encodeURIComponent(item.path);
  preview.hidden = false;
  for (const el of document.querySelectorAll(".output-card.selected")) el.classList.remove("selected");
  card.classList.add("selected");
}

async function _postOutput(url) {
  const resp = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({path: _selectedOutput.path})});
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || "הפעולה נכשלה");
  return data;
}

async function openOutputFolder() {
  if (!_selectedOutput) return;
  try {
    await _postOutput("/api/open_folder");
  } catch (e) {
    uiToast(e.message, "warn");
  }
}

async function openOutputInStudio() {
  if (!_selectedOutput) return;
  try {
    const data = await _postOutput("/api/outputs/studio");
    openProject(data.folder);
  } catch (e) {
    uiToast(e.message, "warn");
  }
}

// כמו exportToTiktok / exportToYoutube בגלריה: TikTok - הכיתוב ללוח ועמוד ההעלאה; יוטיוב - העלאה פרטית כשמוגדר
// client_secret.json, אחרת עמוד ההעלאה הידני
async function publishOutput(target) {
  if (!_selectedOutput) return;
  const status = document.getElementById("outputsStatus");
  try {
    const data = await _postOutput(target === "tiktok" ? "/api/clips/tiktok_export" : "/api/clips/youtube_export");
    if (target === "tiktok") {
      if (data.caption) {
        await navigator.clipboard.writeText(data.caption).then(() => uiToast("📋 הכיתוב הועתק - הדבק אותו ב-TikTok", "ok"),
          () => uiToast(data.caption, "", {timeout: 20000}));
      }
      window.open(data.tiktok_url, "_blank");
    } else if (!data.configured) {
      window.open(data.fallback_url, "_blank");
    } else {
      status.textContent = "⏳ מעלה ליוטיוב (פרטי)...";
      _watchOutputUpload(status);
    }
  } catch (e) {
    uiToast(e.message, "warn");
  }
}

function _watchOutputUpload(status) {
  const timer = setInterval(async () => {
    const data = await fetch("/api/clips/youtube_status").then((r) => r.json()).catch(() => null);
    if (!data) return;
    if (data.in_progress) {
      status.textContent = `⏳ מעלה... ${data.percent}%`;
      return;
    }
    clearInterval(timer);
    status.textContent = data.success ? `✅ הועלה ל-YouTube! ID: ${data.video_id}` : `❌ העלאה נכשלה: ${data.error}`;   // כמו בגלריה
  }, 1500);
}
