// ============================================================================
// גל 31 - ריצה ותוצאות:
//  * גיליון "לפני הרצה": מה ירונדר (קבצים × יעדים), זמן וגודל משוערים והאזהרות - ואז "הרץ".
//    קודם האזהרות היו פזורות ליד שדות באזורים סגורים, והריצה יצאה בלי סיכום.
//  * התוצאות בתוך הסטודיו: כרטיס לכל קובץ פלט עם נגן, השוואה למקור ו"פתח תיקייה" - במקום הדיאלוג.
// ============================================================================

// --- גיליון "לפני הרצה" ---
const VE_RUN_MODE_NOTES = {force: "🔁 גם קבצים שכבר יש להם פלט", validate: "🧪 בדיקה בלבד - בלי רינדור", contact: "🖼️ contact-sheet בלבד - בלי רינדור"};

function _veRunFileCount() {
  if (_veEl("veConcatMode").checked && _veQueueState.length) return 1;
  if (_veQueueDirty && _veQueueState.length) return _veQueueState.filter(f => f.selected).length;
  return _veFolderCounts ? _veFolderCounts.files : _veQueueState.length;
}

// כל כפתורי "הרץ" של העורך (הפס העליון, צעד 4, Ctrl+Enter, לוח הפקודות) עוברים כאן
function requestVeRun() {
  if (_veEl("runBtn").disabled) return;
  if (!_veIsActive() || !_veLoadPref("veRunSheet", true)) { runScript(); return; }
  openVeRunSheet();
}

function openVeRunSheet() {
  const opts = _collectRunOptions();
  const mode = (document.querySelector('input[name="veRunMode"]:checked') || {}).value || "normal";
  const targets = _veTargets();
  const files = _veRunFileCount();
  const outputs = files * Math.max(1, targets.length);
  _veEl("veRunSheetWhat").textContent = _veEl("veConcatMode").checked ? `🔗 סרטון אחד מאיחוד ${_veConcatFiles().length} קטעים`
    : targets.length > 1 ? `${files} קבצים × ${targets.length} יעדים = ${outputs} סרטונים` : `${files} קבצים = ${outputs} סרטונים`;
  const notes = [];
  if (VE_RUN_MODE_NOTES[mode]) notes.push(VE_RUN_MODE_NOTES[mode]);
  const clipCount = Object.keys(opts.clip_edits || {}).length;
  if (clipCount) notes.push(`✏️ ${clipCount} קבצים עם עריכה משלהם`);
  _veEl("veRunSheetNotes").textContent = notes.join(" · ");
  const schema = _veSchema || {targets: {}};
  _veEl("veRunSheetTargets").replaceChildren(...targets.map(id => {
    const chip = document.createElement("span");
    chip.className = "ve-chip";
    const target = schema.targets[id];
    chip.textContent = target ? `${target.icon} ${target.label}` : id;
    return chip;
  }));
  _veEl("veRunSheetFolder").textContent = state.folder || "";
  _veRenderRunSheetWarnings(_veEvaluateRules(opts));
  _veEl("veRunSheetAlways").checked = _veLoadPref("veRunSheet", true);
  _veEl("veRunSheetTime").textContent = "⏳";
  _veEl("veRunSheetSize").textContent = "⏳";
  _veEl("veRunSheetBg").classList.add("show");
  _veEl("veRunSheetGo").focus();
  _veFillRunSheetEstimates(opts, files, Math.max(1, targets.length), mode);
}

function _veRenderRunSheetWarnings(rules) {
  const box = _veEl("veRunSheetWarnings");
  box.replaceChildren(...rules.map(rule => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "ve-warning " + (rule.level === "info" ? "info" : "warn");
    row.textContent = (rule.level === "info" ? "ℹ️ " : "⚠️ ") + rule.msg;
    row.title = "לחץ כדי לתקן - קפיצה להגדרה";
    row.onclick = () => { closeVeRunSheet(); veScrollToField(rule.field); };
    return row;
  }));
  const warnCount = rules.filter(rule => rule.level !== "info").length;
  _veEl("veRunSheetWarnTitle").textContent = warnCount ? `⚠️ ${warnCount} אזהרות - אפשר להריץ בכל זאת` : rules.length ? "ℹ️ לתשומת לב" : "✓ אין אזהרות";
}

async function _veFillRunSheetEstimates(opts, files, targetCount, mode) {
  const request = uiLatest("ve:run-sheet");
  const timeEl = _veEl("veRunSheetTime"), sizeEl = _veEl("veRunSheetSize");
  if (mode === "validate" || mode === "contact") { timeEl.textContent = "שניות"; sizeEl.textContent = "—"; return; }
  try {
    const codec = _veEl("veCodec").value;
    const params = new URLSearchParams({codec, hwaccel: _veEl("veHwaccel").checked && codec !== "h264" ? "true" : "false", file_count: String(files * targetCount)});
    const eta = await (await fetch("/api/video_editor/eta?" + params.toString(), {signal: request.signal})).json();
    if (!request.current()) return;
    timeEl.textContent = eta ? `~${_veFormatSeconds(eta.estimated_total_seconds)}` : "אין עדיין ריצות קודמות להשוואה";
  } catch (e) { if (!uiIsAbort(e)) timeEl.textContent = "—"; }
  if (!state.folder) { sizeEl.textContent = "—"; return; }
  try {
    const res = await fetch("/api/video_editor/estimate", {method: "POST", headers: {"Content-Type": "application/json"}, signal: request.signal,
      body: JSON.stringify({...opts, folder: state.folder, only_files: _veQueueSelectedFiles()})});
    const data = await res.json();
    if (!request.current()) return;
    sizeEl.textContent = res.ok && data.total_output_mb ? `≈ ${_veFormatMb(data.total_output_mb * targetCount)}` : "—";
  } catch (e) { if (!uiIsAbort(e)) sizeEl.textContent = "—"; }
}

function closeVeRunSheet() { _veEl("veRunSheetBg").classList.remove("show"); }

function confirmVeRunSheet() {
  closeVeRunSheet();
  runScript();
}

// --- התוצאות בתוך הסטודיו ---
function _veShowResultsPanel(on) {
  _veEl("veResultsPanel").hidden = !on;
  _veEl("veViewer").classList.toggle("ve-showing-results", on);
  if (!on) for (const video of _veEl("veResultsList").querySelectorAll("video")) video.pause();
}

function closeVeResults() { _veShowResultsPanel(false); }

function _veResultSourceUrl(manifest, file) {
  return "/api/video_editor/source_stream?folder=" + encodeURIComponent(manifest.input_dir || state.folder || "") + "&file=" + encodeURIComponent(file.source);
}

// ▶ על התמונה - הסרטון מתנגן במקום; ⇆ - מקור ופלט זה לצד זה, מסונכרנים
function _veResultMedia(manifest, file) {
  const media = document.createElement("div");
  media.className = "ve-result-media";
  const thumb = document.createElement("img");
  thumb.alt = "";
  thumb.loading = "lazy";
  if (file.output && file.status !== "error") thumb.src = "/api/video_editor/output_thumbnail?path=" + encodeURIComponent(file.output);
  else thumb.classList.add("ve-no-thumb");
  media.appendChild(thumb);
  if (file.output && file.status === "created") {
    media.classList.add("ve-result-playable");
    media.title = "נגן כאן";
    media.onclick = () => _veResultPlay(media, file);
  }
  return media;
}

function _veResultVideo(src, label) {
  const video = document.createElement("video");
  video.controls = true;
  video.playsInline = true;
  video.preload = "metadata";
  video.src = src;
  video.setAttribute("aria-label", label);
  return video;
}

function _veResultPlay(media, file) {
  if (media.querySelector("video")) return;
  const video = _veResultVideo("/api/video_editor/stream?path=" + encodeURIComponent(file.output), "הפלט");
  media.replaceChildren(video);
  media.onclick = null;
  video.play().catch(() => {});
}

function _veResultCompare(card, manifest, file) {
  const existing = card.querySelector(".ve-result-compare");
  if (existing) { existing.remove(); return; }
  const box = document.createElement("div");
  box.className = "ve-result-compare";
  const source = _veResultVideo(_veResultSourceUrl(manifest, file), "המקור");
  const output = _veResultVideo("/api/video_editor/stream?path=" + encodeURIComponent(file.output), "הפלט");
  source.muted = true;
  // הפלט מוביל; המקור הולך אחריו (בלי שמע כפול)
  const follow = () => { if (Math.abs(source.currentTime - output.currentTime) > 0.25) source.currentTime = output.currentTime; };
  output.addEventListener("play", () => { follow(); source.play().catch(() => {}); });
  output.addEventListener("pause", () => source.pause());
  output.addEventListener("seeked", follow);
  for (const [video, title] of [[source, "מקור"], [output, "פלט"]]) {
    const figure = document.createElement("figure");
    const caption = document.createElement("figcaption");
    caption.textContent = title;
    figure.append(video, caption);
    box.appendChild(figure);
  }
  card.appendChild(box);
}

function _veResultCard(manifest, file) {
  const card = document.createElement("article");
  card.className = "ve-result-card";
  card.dataset.status = file.status;
  card.dataset.source = file.source || "";  // גל 35: ✅ בשורת התור מוביל לכרטיס הזה
  const main = document.createElement("div");
  main.className = "ve-result-main";
  const title = document.createElement("div");
  title.className = "ve-result-title";
  title.textContent = `${VE_STATUS_ICONS[file.status] || "•"} ${file.source}`;
  const detail = document.createElement("div");
  detail.className = "ve-field-msg";
  const bits = [];
  if (file.output) bits.push("→ " + file.output.split(/[\\/]/).pop());
  if (file.render_seconds) bits.push(`${_veFormatTime(file.render_seconds)} רינדור`);
  if (file.output_size_mb) bits.push(_veFormatMb(file.output_size_mb));
  if (file.duration_seconds) bits.push(`${_veFormatTime(file.duration_seconds)} פלט`);
  if (file.reason) bits.push(file.reason);
  detail.textContent = bits.join(" · ");
  detail.title = file.reason || "";
  main.append(title, detail);
  const actions = document.createElement("div");
  actions.className = "ve-result-actions";
  if (file.output && file.status === "created") {
    const tool = (text, label, action) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "btn-sm";
      b.textContent = text;
      b.title = label;
      b.onclick = action;
      return b;
    };
    actions.append(tool("⇆ מול המקור", "המקור והפלט זה לצד זה, מסונכרנים", () => _veResultCompare(card, manifest, file)),
      tool("📂", "פתח את תיקיית הקובץ", () => _veOpenFolder(file.output)));
  }
  card.append(_veResultMedia(manifest, file), main, actions);
  return card;
}
