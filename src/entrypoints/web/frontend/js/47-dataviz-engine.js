// ============================================================================
// גל 42: המנוע של עורך הגרפים - מדריך המנוע (תרשימים, מצבים, יעדים, כתוביות, קריינות, מפה, כל
// ההגדרות ושורת הפקודה - GET /api/dataviz/help, נבנה מהקוד), רשימת הקולות של Windows לקריינות,
// והורדת כתוביות SRT לפרק בלי לרנדר (GET /api/dataviz/episodes/captions).
// ============================================================================

let dvzHelp = {sections: null, voices: null};

async function dvzOpenHelp() {
  document.getElementById("dvzHelpBg").classList.add("show");
  const search = document.getElementById("dvzHelpSearch");
  if (!dvzHelp.sections || dvzHelp.lang !== _uiLang) {   // גל 47: המדריך בשפת הממשק
    document.getElementById("dvzHelpBody").replaceChildren(_dvzEdEl("p", "hint", "⏳"));
    dvzHelp.lang = _uiLang;
    try {
      dvzHelp.sections = (await _dvzJson(await fetch("/api/dataviz/help?lang=" + encodeURIComponent(_uiLang)))).sections || [];
    } catch (e) {
      dvzHelp.sections = [];
    }
  }
  dvzRenderHelp();
  search.focus();
  if (!dvzHelp.voices) _dvzLoadVoices();
}

function dvzCloseHelp() {
  document.getElementById("dvzHelpBg").classList.remove("show");
}

async function _dvzLoadVoices() {
  try {
    dvzHelp.voices = (await _dvzJson(await fetch("/api/dataviz/voices"))).voices || [];
  } catch (e) {
    dvzHelp.voices = [];
  }
  dvzRenderHelp();
}

function _dvzHelpSections() {
  const sections = [...(dvzHelp.sections || [])];
  if (dvzHelp.voices) {
    sections.push({id: "voices", title: "🔊 הקולות במחשב הזה (לקריינות)",
      items: dvzHelp.voices.length
        ? dvzHelp.voices.map(v => ({title: v.name, code: v.name, text: `${v.culture} · ${v.gender}`}))
        : [{title: "אין קולות", text: "לא נמצאו קולות של Windows. אפשר להוסיף קול (גם בעברית) בהגדרות של Windows: זמן ושפה - דיבור."}]});
  }
  return sections;
}

function dvzRenderHelp() {
  const query = document.getElementById("dvzHelpSearch").value.trim().toLowerCase();
  const toc = document.getElementById("dvzHelpToc");
  const body = document.getElementById("dvzHelpBody");
  const matches = (item) => !query || `${item.title} ${item.code || ""} ${item.text}`.toLowerCase().includes(query);
  const shown = _dvzHelpSections().map(s => ({...s, items: s.items.filter(matches)})).filter(s => s.items.length);
  toc.replaceChildren(...shown.map(section => {
    const link = _dvzEdEl("button", "btn-xs btn-ghost", section.title);
    link.type = "button";
    link.onclick = () => document.getElementById("dvzHelp-" + section.id).scrollIntoView({block: "start"});
    return link;
  }));
  if (!shown.length) {
    body.replaceChildren(_dvzEdEl("p", "empty-msg", "אין הסבר שמתאים לחיפוש."));
    return;
  }
  body.replaceChildren(...shown.map(section => {
    const box = _dvzEdEl("section", "dvz-help-section");
    box.id = "dvzHelp-" + section.id;
    box.append(_dvzEdEl("h4", "", section.title));
    if (section.about) box.append(_dvzEdEl("p", "hint", section.about));
    const list = _dvzEdEl("dl", "dvz-help-list");
    for (const item of section.items) {
      const term = _dvzEdEl("dt", "", item.title);
      if (item.code && item.code !== item.title) {
        const code = _dvzEdEl("code", "", item.code);
        code.dir = "ltr";
        term.append(" ", code);
      }
      const dd = _dvzEdEl("dd", "", item.text);
      if (item.field && dvzState.selected && _dvzAltValue(item.field) !== undefined) dd.append(" ", _dvzBeforeAfterButton(item, dd));   // גל 45
      list.append(term, dd);
    }
    box.append(list);
    return box;
  }));
}

// --- כתוביות לפרק שנבחר: SRT מהתכנית של הסרטון המלא, בלי לרנדר ---
async function dvzDownloadCaptions() {
  if (!dvzState.selected) return;
  const url = "/api/dataviz/episodes/captions?" + new URLSearchParams({episode: dvzState.selected, mode: "full", download: "1"});
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error((await _dvzJson(resp)).error || "יצירת הכתוביות נכשלה");
    const text = await resp.text();
    if (!text.trim()) { uiToast("אין בפרק אירועים או שיאים לכתוביות.", "warn"); return; }
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([text], {type: "application/x-subrip"}));
    link.download = `${dvzState.selected}.srt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    uiToast(`💬 ${text.split("-->").length - 1} כתוביות`, "ok");
  } catch (e) {
    uiToast("שגיאה: " + e.message, "warn");
  }
}

// ============================================================================
// גל 45: לפני / אחרי במדריך (פריים בברירת המחדל מול ערך אחר, על הפרק שנבחר), ספריית מפות (העלאת GeoJSON
// פעם אחת, בחירת המאפיין, בדיקת התאמה לישויות ושימוש בפרק), והקלטת קריינות לכל אירוע מהמיקרופון.
// ============================================================================

// --- לפני / אחרי ---
function _dvzAltValue(field) {
  const d = field.default;
  if (field.type === "bool") return !d;
  if (field.type === "choice") {
    const choices = field.choices || [];
    return choices.length > 1 ? choices[(choices.indexOf(d) + 1) % choices.length] : undefined;
  }
  if (field.type === "int" || field.type === "number") {
    const lo = field.min ?? -Infinity, hi = field.max ?? Infinity;
    let alt = d ? d * 2 : (Number.isFinite(hi) ? Math.min(hi, 1) : 1);
    if (alt > hi) alt = d / 2;
    if (alt < lo) alt = lo;
    if (field.type === "int") alt = Math.round(alt);
    return alt === d ? undefined : alt;
  }
  return undefined;
}

function _dvzBeforeAfterButton(item, dd) {
  const btn = _dvzEdEl("button", "btn-xs", "👁 לפני / אחרי");
  btn.type = "button";
  btn.title = "אותו רגע בפרק שנבחר: בברירת המחדל מול ערך אחר";
  btn.onclick = () => {
    const open = dd.querySelector(".dvz-before-after");
    if (open) { open.remove(); return; }
    const alt = _dvzAltValue(item.field);
    const pos = (typeof _dvzPosition === "function" ? _dvzPosition() : 0.6).toFixed(3);
    const box = _dvzEdEl("div", "dvz-before-after");
    for (const [label, value] of [["לפני", item.field.default], ["אחרי", alt]]) {
      const figure = _dvzEdEl("figure");
      const img = _dvzEdEl("img");
      img.alt = `${item.title}: ${label}`;
      img.loading = "lazy";
      img.src = _dvzThumbUrl(dvzState.selected, pos, 0.25, {draft: JSON.stringify({[item.code]: value})});
      img.onerror = () => { figure.replaceChildren(_dvzEdEl("figcaption", "hint", "אין תצוגה להגדרה הזו בפרק הזה.")); };
      figure.append(img, _dvzEdEl("figcaption", "hint", `${label}: ${typeof value === "boolean" ? (value ? "כן" : "לא") : value}`));
      box.append(figure);
    }
    dd.append(box);
  };
  return btn;
}

// --- ספריית מפות (לשונית בעורך) ---
function _dvzMapTab() {
  const box = _dvzEdEl("div", "dvz-map-tab");
  box.append(_dvzEdEl("p", "hint", "מפה = קובץ GeoJSON של אזורים (מחוזות, ערים, מדינות). מעלים אותו פעם אחת לספרייה, בוחרים איזה מאפיין מחזיק את שם האזור, ובודקים שהשמות תואמים לישויות של הפרק."));
  const body = _dvzEdEl("div", "");
  box.append(body);
  _dvzRenderMapLibrary(body);
  return box;
}

async function _dvzRenderMapLibrary(body) {
  let maps = [];
  try { maps = (await _dvzJson(await fetch("/api/dataviz/maps"))).maps || []; } catch (e) { maps = []; }
  const nodes = [];
  if (maps.length) {
    const select = _dvzEdEl("select");
    select.id = "dvzMapPick";
    select.setAttribute("aria-label", "מפה מהספרייה");
    select.append(...maps.map(m => new Option(m.name, m.name)));
    const keySelect = _dvzEdEl("select");
    keySelect.id = "dvzMapKey";
    keySelect.setAttribute("aria-label", "המאפיין עם שם האזור");
    const fillKeys = () => {
      const map = maps.find(m => m.name === select.value) || {keys: {}};
      keySelect.replaceChildren(...Object.entries(map.keys).map(([key, samples]) => new Option(`${key} (${samples.join(", ")})`, key)));
      const preferred = ["name", "shapeName", "NAME"].find(k => map.keys[k]);   // גל 46: גם במפות המוכנות
      if (preferred) keySelect.value = preferred;
    };
    select.onchange = fillKeys;
    fillKeys();
    const report = _dvzEdEl("div", "dvz-map-report");
    report.setAttribute("aria-live", "polite");
    const check = _dvzEdEl("button", "btn-sm", "🔍 בדוק התאמה");
    check.type = "button";
    check.onclick = async () => {
      const data = await _dvzJson(await fetch("/api/dataviz/maps/match?" + new URLSearchParams({episode: dvzState.selected, name: select.value, key: keySelect.value})));
      if (data.error) { report.replaceChildren(_dvzEdEl("p", "bad", "שגיאה: " + data.error)); return; }
      const lines = [data.missing.length
        ? _dvzEdEl("p", "dvz-finding is-warn", `${data.found.length} ישויות נמצאו במפה ו-${data.missing.length} לא (יופיעו רק בדירוג): ${data.missing.slice(0, 10).join(", ")}`)
        : _dvzEdEl("p", "dvz-check-ok", `כל ${data.found.length} הישויות נמצאו במפה.`)];
      if (data.unused.length) lines.push(_dvzEdEl("p", "hint", `אזורים בלי ישות: ${data.unused.slice(0, 10).join(", ")}`));
      report.replaceChildren(...lines);
    };
    const use = _dvzEdEl("button", "btn-sm btn-primary", "🗺 השתמש במפה בפרק");
    use.type = "button";
    use.onclick = async () => {
      const resp = await fetch("/api/dataviz/maps/use", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({episode: dvzState.selected, name: select.value, key: keySelect.value})});
      const data = await _dvzJson(resp);
      if (!resp.ok) { uiToast("שגיאה: " + (data.error || "השמירה נכשלה"), "warn"); return; }
      uiToast("🗺 המפה נשמרה בפרק - בחר \"מפה\" בסוג התרשים", "ok");
      await loadDataviz();
    };
    const row = _dvzEdEl("div", "tc-row");
    row.append(select, keySelect, check, use);
    nodes.push(row, report);
  } else {
    nodes.push(_dvzEdEl("p", "empty-msg", "הספרייה ריקה - העלה קובץ GeoJSON."));
  }
  const upload = _dvzEdEl("input");
  upload.type = "file";
  upload.id = "dvzMapUpload";
  upload.accept = ".geojson,.json,.zip";
  upload.setAttribute("aria-label", "העלאת מפה לספרייה");
  upload.title = "GeoJSON, או shapefile דחוס (zip עם .shp ו-.dbf) - למשל גבולות שיפוט ממשרד הפנים";
  upload.onchange = async () => {
    const file = upload.files && upload.files[0];
    if (!file) return;
    // גל 47: shapefile דחוס נשלח כמו שהוא ומומר בשרת
    const isZip = /\.zip$/i.test(file.name);
    const resp = await fetch(isZip ? "/api/dataviz/maps/upload_shapefile" : "/api/dataviz/maps/upload", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(isZip ? {filename: file.name, data_base64: await _dvzBase64(file)} : {filename: file.name, text: await file.text()})});
    const data = await _dvzJson(resp);
    if (!resp.ok) { uiToast("שגיאה: " + (data.error || "ההעלאה נכשלה"), "warn"); return; }
    uiToast(`🗺 "${data.name}" נוסף לספרייה`, "ok");
    _dvzRenderMapLibrary(body);
  };
  const uploadRow = _dvzEdEl("label", "dvz-field-label", "📥 העלה מפה לספרייה: ");
  uploadRow.append(upload);
  nodes.push(uploadRow, await _dvzReadyMaps(body));
  body.replaceChildren(...nodes);
}

// גל 46: מפות מוכנות - קטלוג קבוע; הקובץ יורד לספרייה רק כשלוחצים
async function _dvzReadyMaps(body) {
  const box = _dvzEdEl("div", "dvz-ready-maps");
  box.append(_dvzEdEl("h4", "", "📚 מפות מוכנות"));
  let maps = [];
  try { maps = (await _dvzJson(await fetch("/api/dataviz/maps/ready"))).maps || []; } catch (e) { maps = []; }
  for (const map of maps) {
    const row = _dvzEdEl("div", "dvz-ready-map");
    row.dataset.map = map.id;
    row.append(_dvzEdEl("strong", "", map.title), _dvzEdEl("span", "hint", `${Math.ceil(map.size / 1024)}KB · ${map.license} · ${map.key}`));
    if (map.installed) {
      row.append(_dvzEdEl("span", "dvz-check-ok", "✓ בספרייה"));
    } else {
      const get = _dvzEdEl("button", "btn-xs", "⬇ הורד לספרייה");
      get.type = "button";
      get.onclick = async () => {
        get.disabled = true;
        const resp = await fetch("/api/dataviz/maps/ready", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: map.id})});
        const data = await _dvzJson(resp);
        if (!resp.ok) { get.disabled = false; uiToast("שגיאה: " + (data.error || "ההורדה נכשלה"), "warn"); return; }
        uiToast(`🗺 "${map.title}" נוסף לספרייה`, "ok");
        _dvzRenderMapLibrary(body);
      };
      row.append(get);
    }
    box.append(row);
  }
  box.append(_dvzEdEl("p", "hint", "שמות האזורים במפות המוכנות באנגלית - אם הישויות שלך בעברית, תן להן שם חלופי (לשונית \"ישויות\") בשם שבמפה."));
  return box;
}

// --- הקלטת קריינות לכל אירוע ---
let dvzRecorder = null;

function _dvzVoiceTab() {
  const box = _dvzEdEl("div", "dvz-voice-tab");
  box.append(_dvzEdEl("p", "hint", "הקלטה בקול שלך לכל אירוע - נשמעת כשהכרטיס של האירוע עולה (במקום הקול של Windows). כדי שיושמעו: \"קריינות\" בהגדרות (כתוביות וקריינות). ההקלטות נשמרות בנפרד מתיקיית הפרק."));
  const body = _dvzEdEl("div", "");
  box.append(body);
  _dvzRenderVoice(body);
  return box;
}

async function _dvzRenderVoice(body) {
  let recordings = {};
  try { recordings = (await _dvzJson(await fetch("/api/dataviz/episodes/recordings?episode=" + encodeURIComponent(dvzState.selected)))).recordings || {}; } catch (e) { recordings = {}; }
  const events = (dvzEd.data && dvzEd.data.events) || [];
  if (!events.length) { body.replaceChildren(_dvzEdEl("p", "empty-msg", "אין בפרק אירועים להקליט.")); return; }
  const table = _dvzEdEl("table", "dvz-data-table dvz-voice-table");
  const tbody = table.createTBody();
  for (const ev of events) {
    const tr = tbody.insertRow();
    tr.dataset.date = ev.date;
    tr.insertCell().textContent = ev.date;
    tr.insertCell().textContent = ev.label;
    const status = tr.insertCell();
    const actions = tr.insertCell();
    const name = recordings[ev.date];
    status.textContent = name ? "🎙 הוקלט" : "קול של Windows";
    const rec = _dvzEdEl("button", "btn-xs", "● הקלט");
    rec.type = "button";
    rec.onclick = () => _dvzToggleRecording(ev.date, rec, () => _dvzRenderVoice(body));
    actions.append(rec);
    if (name) {
      const url = "/api/dataviz/episodes/recording?" + new URLSearchParams({episode: dvzState.selected, name});
      const play = _dvzEdEl("button", "btn-xs", "▶");
      play.type = "button";
      play.setAttribute("aria-label", `השמע את ההקלטה של ${ev.label}`);
      play.onclick = () => new Audio(url).play().catch(() => {});
      const trash = _dvzEdEl("button", "btn-xs", "🗑");
      trash.type = "button";
      trash.setAttribute("aria-label", `מחק את ההקלטה של ${ev.label}`);
      trash.onclick = async () => {
        if (!(await veConfirm(`להעביר את ההקלטה של "${ev.label}" לסל המיחזור?`))) return;
        await fetch("/api/dataviz/episodes/recordings/trash", {method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({episode: dvzState.selected, name})});
        _dvzRenderVoice(body);
      };
      actions.append(play, trash);
    }
  }
  body.replaceChildren(table);
}

async function _dvzToggleRecording(date, button, done) {
  if (dvzRecorder && dvzRecorder.state === "recording") { dvzRecorder.stop(); return; }
  const episode = dvzState.selected;   // נ15: ההקלטה שייכת לפרק שבו התחילה - קודם נשמרה לפרק שנבחר כשהיא נעצרה
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    const chunks = [];
    const recorder = dvzRecorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    // מעבר לפרק אחר עוצר את ההקלטה (והיא נשמרת לפרק שלה)
    const watch = setInterval(() => { if (dvzState.selected !== episode && recorder.state === "recording") recorder.stop(); }, 500);
    recorder.onstop = async () => {
      clearInterval(watch);
      stream.getTracks().forEach(t => t.stop());
      button.textContent = "● הקלט";
      await dvzUploadRecording(date, new Blob(chunks, {type: recorder.mimeType || "audio/webm"}), episode);
      done();
    };
    recorder.start();
    button.textContent = "■ עצור";
  } catch (e) {
    uiToast("אין גישה למיקרופון: " + e.message, "warn");
  }
}

async function _dvzBase64(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

async function dvzUploadRecording(date, blob, episode = dvzState.selected) {
  const ext = /ogg/.test(blob.type) ? "ogg" : /mp4|aac/.test(blob.type) ? "m4a" : /wav/.test(blob.type) ? "wav" : "webm";
  const resp = await fetch("/api/dataviz/episodes/recordings", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({episode, date, ext, data_base64: await _dvzBase64(blob)})});
  const data = await _dvzJson(resp);
  if (!resp.ok) { uiToast("שגיאה: " + (data.error || "השמירה נכשלה"), "warn"); return false; }
  uiToast("🎙 ההקלטה נשמרה", "ok");
  return true;
}
