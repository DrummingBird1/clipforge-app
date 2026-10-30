// 31-global-settings.js - הגדרות כלליות: נטען רק כשפותחים את המסך (frontend_assembly.LAZY_JS["settings"],
// switchTab ב-20-app-shell.js). _infoLine ו"עיצוב" נשארו ב-30 (גם מסך התזמון וה-header משתמשים בהם).
// --- הגדרות כלליות (webhook/גיבוי/מצב לילה/טורבו) ---
async function loadGlobalSettings() {
  loadRemoteAccess();
  loadPairedDevices();
  loadExportDir();
  const res = await fetch("/api/settings/global");
  const data = await res.json();
  document.getElementById("gsWebhook").value = data.webhook;
  document.getElementById("gsNasFolder").value = data.nas_folder;
  document.getElementById("gsAutoBackup").checked = data.auto_backup_active;
  document.getElementById("gsTurbo").checked = data.turbo_active;
  document.getElementById("gsNightMode").checked = data.night_active;
}

async function saveGlobalSettings() {
  const payload = {
    webhook: document.getElementById("gsWebhook").value,
    nas_folder: document.getElementById("gsNasFolder").value,
    auto_backup_active: document.getElementById("gsAutoBackup").checked,
    turbo_active: document.getElementById("gsTurbo").checked,
    night_active: document.getElementById("gsNightMode").checked,
  };
  try {
    const resp = await fetch("/api/settings/global", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!resp.ok) throw new Error((await resp.json()).error || "שמירה נכשלה");
    alert("ההגדרות נשמרו.");
  } catch (e) {
    alert("שגיאה: " + e.message);
  }
}

async function resetAllSettings() {
  if (!(await veConfirm("לאפס את כל ההגדרות לברירת מחדל? הגדרות נוכחיות יגובו ל-config.json.bak.\nיידרש הפעלה מחדש של ה-GUI/הבוט כדי שהשינוי ייכנס לתוקף אצלם.", {danger: true, okLabel: "אפס הכל"}))) return;
  try {
    const resp = await fetch("/api/settings/reset", { method: "POST" });
    if (!resp.ok) throw new Error((await resp.json()).error || "האיפוס נכשל");
    alert("ההגדרות אופסו. הפעל מחדש את ה-GUI/הבוט כדי שהשינוי ייכנס לתוקף אצלם.");
    loadGlobalSettings();
    loadStyleSettings();
  } catch (e) {
    alert("שגיאה: " + e.message);
  }
}

// --- עיצוב: ערכת נושא, צבע מותאם, שפת ה-GUI השולחני (_applyAccentLive והמשתנים שלו ב-30 - 69-ui-prefs.js עוטף אותו בטעינה)
async function loadStyleSettings() {
  const [themesRes, styleRes] = await Promise.all([fetch("/api/settings/themes"), fetch("/api/settings/style")]);
  _themesCache = await themesRes.json();
  const style = await styleRes.json();
  _selectedThemeName = style.theme;
  document.getElementById("gsCustomColor").value = style.custom_accent_hex;
  document.getElementById("gsLanguage").value = style.language;
  renderThemeSwatches();
  _applyAccentLive();
}

function renderThemeSwatches() {
  const container = document.getElementById("themeSwatches");
  container.innerHTML = "";
  for (const [name, colors] of Object.entries(_themesCache)) {
    if (name === "Custom") continue;
    const swatch = document.createElement("button");
    swatch.title = colors.label || name;   // label מהשרת (api_settings_themes) - השם המוצג, לא המפתח השמור
    swatch.style.cssText = `width:28px;height:28px;border-radius:50%;cursor:pointer;background:${colors.accent};border:2px solid ${name === _selectedThemeName ? "#fff" : "transparent"}`;
    swatch.onclick = () => { _selectedThemeName = name; saveStyleSettings(); };
    container.appendChild(swatch);
  }
}

async function saveStyleSettings() {
  try {
    const resp = await fetch("/api/settings/style", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        theme: _selectedThemeName,
        custom_accent_hex: document.getElementById("gsCustomColor").value,
        language: document.getElementById("gsLanguage").value,
      }),
    });
    if (!resp.ok) throw new Error((await resp.json()).error || "שמירה נכשלה");
  } catch (e) {
    alert("שגיאה: " + e.message);
  }
  loadStyleSettings();
}

document.getElementById("gsCustomColor").addEventListener("change", () => { _selectedThemeName = "Custom"; saveStyleSettings(); });
document.getElementById("gsLanguage").addEventListener("change", () => saveStyleSettings());

// גישה מהטלפון דרך Tailscale (data/remote_access.json), מההפעלה הבאה של השרת
async function loadRemoteAccess() {
  if (!document.getElementById("gsTailscale")) return;
  try {
    _renderRemoteAccess(await (await fetch("/api/remote_access")).json());
  } catch (e) {
    console.warn(e);
  }
}

function _renderRemoteAccess(data) {
  document.getElementById("gsTailscale").checked = !!data.tailscale;
  const info = document.getElementById("gsTailscaleInfo");
  info.replaceChildren();
  if (data.active_url) _infoLine(info, "פעיל עכשיו - לפתוח מהטלפון:", data.token_url || data.active_url);
  else if (data.tailscale) _infoLine(info, "נשמר - יחול בהפעלה הבאה של השרת.");
  if (!data.detected_ip) _infoLine(info, "לא נמצא כרגע ממשק Tailscale מחובר במחשב הזה.");
  else if (!data.active_url) _infoLine(info, "כתובת Tailscale שזוהתה:", data.detected_ip);
}

async function saveRemoteAccess() {
  const resp = await fetch("/api/remote_access", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tailscale: document.getElementById("gsTailscale").checked }) });
  _renderRemoteAccess(await resp.json());
}

// צימוד מכשיר (routes/devices.py); /api/devices עונה רק למחשב עצמו
let _gsPairPoll = null;

async function loadPairedDevices() {
  if (!document.getElementById("gsDevices")) return;
  try {
    const resp = await fetch("/api/devices");
    _renderPairedDevices(resp.ok ? await resp.json() : null);
  } catch (e) {
    console.warn(e);
  }
}

function _gsButton(text, onclick, className) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = text;
  btn.onclick = onclick;
  if (className) btn.className = className;
  return btn;
}

function _gsTime(seconds) {
  return seconds ? new Date(seconds * 1000).toLocaleString() : "";
}

function _renderPairedDevices(data) {
  const box = document.getElementById("gsDevices");
  box.replaceChildren();
  const title = document.createElement("h4");
  title.textContent = "מכשירים מצומדים";
  box.appendChild(title);
  if (!data) {
    _infoLine(box, "צימוד וביטול של מכשירים אפשריים רק מהמחשב עצמו (127.0.0.1).");
    return;
  }
  _infoLine(box, "טלפון או ZimaOS נשארים מחוברים גם אחרי הפעלה מחדש של השרת, עד שמבטלים אותם כאן.");
  const actions = document.createElement("div");
  actions.className = "tc-row";
  actions.appendChild(_gsButton("➕ צמד מכשיר", startDevicePairing));
  if (data.devices.length) actions.appendChild(_gsButton("בטל את כולם", revokeAllDevices, "u-bg-danger u-on-solid"));
  box.appendChild(actions);
  const pairBox = document.createElement("div");
  pairBox.id = "gsPairBox";
  box.appendChild(pairBox);

  const expire = document.createElement("label");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.id = "gsDevicesExpire";
  checkbox.checked = !!data.expire_unused;
  checkbox.onchange = saveDevicesExpire;
  const expireText = document.createElement("span");
  expireText.textContent = "לבטל לבד מכשיר שלא היה בשימוש 90 יום";
  expire.append(checkbox, expireText);
  box.appendChild(expire);

  if (!data.devices.length) _infoLine(box, "אין מכשירים מצומדים.");
  for (const device of data.devices) {
    const row = document.createElement("div");
    row.className = "tc-row";
    const name = document.createElement("b");
    name.textContent = device.name;
    const kind = document.createElement("span");
    kind.className = "hint";
    kind.textContent = device.kind === "script" ? "סקריפט" : "דפדפן";
    row.append(name, kind, _gsButton("בטל צימוד", () => revokeDevice(device.id)));
    box.appendChild(row);
    _infoLine(box, "צומד:", _gsTime(device.created_at));
    _infoLine(box, "נראה לאחרונה:", [_gsTime(device.last_seen), device.last_ip].filter(Boolean).join(" · "));
  }
}

async function _gsDevicesPost(url, body) {
  const resp = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || resp.status);
  return data;
}

async function startDevicePairing() {
  const name = await vePrompt("שם למכשיר (למשל טלפון או ZimaOS):", { okLabel: "צור קוד" });
  if (name === null) return;
  try {
    _showPairCode(await _gsDevicesPost("/api/devices/pair", { name }));
  } catch (e) {
    uiToast(e.message, "warn");
  }
}

function _showPairCode(data) {
  const box = document.getElementById("gsPairBox");
  box.replaceChildren();
  _infoLine(box, "סרוק מהמכשיר, או פתח בו את הקישור:", data.url);
  const qr = document.createElement("img");
  qr.className = "u-width-220px u-height-220px u-bg-white u-rounded u-padding-6px";
  qr.alt = "קוד QR לצימוד";
  qr.src = "/api/qr?data=" + encodeURIComponent(data.url);
  box.appendChild(qr);
  _infoLine(box, "לסקריפט בלי דפדפן (ZimaOS), POST עם הקוד אל:", data.token_url);
  _infoLine(box, "הקוד:", data.code);
  _infoLine(box, "תקף עד:", new Date(data.expires_at * 1000).toLocaleTimeString());
  const status = document.createElement("div");
  status.className = "hint";
  status.textContent = "ממתין למכשיר...";
  box.appendChild(status);
  clearInterval(_gsPairPoll);
  _gsPairPoll = setInterval(async () => {
    try {
      const result = await (await fetch("/api/devices/pair/status?code=" + encodeURIComponent(data.code))).json();
      if (result.state === "pending") return;
      clearInterval(_gsPairPoll);
      if (result.state === "paired") {
        uiToast("המכשיר צומד: " + ((result.device && result.device.name) || data.name), "ok");
        loadPairedDevices();
      } else {
        status.textContent = "הקוד פג, צור קוד חדש.";
      }
    } catch (e) {
      console.warn(e);
    }
  }, 2000);
}

async function revokeDevice(deviceId) {
  if (!(await veConfirm("לבטל את המכשיר? הוא מתנתק מיד, וכדי לחבר אותו שוב צריך לצמד מחדש.", { danger: true, okLabel: "בטל מכשיר" }))) return;
  try {
    _renderPairedDevices(await _gsDevicesPost("/api/devices/revoke", { id: deviceId }));
  } catch (e) {
    uiToast(e.message, "warn");
  }
}

async function revokeAllDevices() {
  if (!(await veConfirm("לבטל את כל המכשירים המצומדים? כולם מתנתקים מיד.", { danger: true, okLabel: "בטל את כולם" }))) return;
  try {
    _renderPairedDevices(await _gsDevicesPost("/api/devices/revoke_all"));
  } catch (e) {
    uiToast(e.message, "warn");
  }
}

async function saveDevicesExpire() {
  try {
    await _gsDevicesPost("/api/devices/settings", { expire_unused: document.getElementById("gsDevicesExpire").checked });
  } catch (e) {
    uiToast(e.message, "warn");
  }
}

let _gsExport = {};

function _exportInput(tool) {
  return tool ? document.querySelector(`[data-export-tool=${tool}] input`) : document.getElementById("gsExportDir");
}

async function loadExportDir() {
  if (!document.getElementById("gsExportDir")) return;
  try {
    _renderExportDir(await (await fetch("/api/export_dir")).json());
  } catch (e) {
    console.warn(e);
  }
}

function _renderExportDir(data) {
  _gsExport = data;
  document.getElementById("gsExportDir").value = data.root || "";
  const info = document.getElementById("gsExportInfo");
  info.replaceChildren();
  if (data.problem) _infoLine(info, "לא זמינה עכשיו, התוצרים יישמרו ב-workspace:", data.problem);
  else _infoLine(info, "התוצרים נשמרים ב:", data.effective);
  const tools = document.getElementById("gsExportTools");
  tools.replaceChildren();
  for (const t of data.tools || []) {
    _exportInput(t.tool).value = t.root || "";
    if (t.problem) _infoLine(tools, "לא זמינה עכשיו, התוצרים יישמרו ב-workspace:", t.root);
  }
}

async function saveExportDir(create = false, tool = "", root = _exportInput(tool).value.trim()) {
  const resp = await fetch("/api/export_dir", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ root, create, tool }) });
  const data = await resp.json();
  if (resp.ok) {
    _renderExportDir(data);
    uiToast("תיקיית הייצוא נשמרה", "ok");
  } else if (data.missing && !create && await veConfirm("התיקייה לא קיימת. ליצור אותה?", { okLabel: "צור תיקייה" })) {
    await saveExportDir(true, tool, root);
  } else {
    uiToast(data.error || "השמירה נכשלה", "warn");
  }
}

function openExportDir() {
  _gsDevicesPost("/api/open_folder", { path: _gsExport.effective }).catch((e) => uiToast(e.message, "warn"));
}

async function chooseExportFolder(tool = "") {
  state.browseTarget = (path) => { _exportInput(tool).value = path; };
  state.browseMode = "folder";
  await browseTo(_exportInput(tool).value || "");
  document.getElementById("modalBg").classList.add("show");
}

