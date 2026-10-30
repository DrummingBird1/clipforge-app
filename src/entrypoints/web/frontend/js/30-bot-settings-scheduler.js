// --- ניהול בוט ---
async function loadBotStatus() {
  try {
    const res = await fetch("/api/bot/status");
    const data = await res.json();
    const btn = document.getElementById("botToggleBtn");
    const text = document.getElementById("botStatusText");
    // גל 23: המצב נשמר כנתון - טקסט הכפתור מתורגם בממשק האנגלי
    btn.dataset.running = data.running ? "1" : "0";
    if (data.running) {
      text.textContent = "🟢 סטטוס בוט: מחובר ורץ";
      btn.textContent = "🛑 כבה בוט";
    } else if (data.config_error) {
      // קוד היציאה של main.py לשגיאת הגדרה - לא הופעל מחדש (הפעלה מחדש לא תעזור)
      text.textContent = "🔴 סטטוס בוט: שגיאת הגדרה - בדוק את הטוקן";
      btn.textContent = "🚀 הפעל בוט";
    } else if (data.gave_up) {
      text.textContent = "🔴 סטטוס בוט: קרס - נדרשת הפעלה ידנית";
      btn.textContent = "🚀 הפעל בוט";
    } else {
      text.textContent = "🔴 סטטוס בוט: כבוי";
      btn.textContent = "🚀 הפעל בוט";
    }
  } catch (e) { /* לא קריטי - רק תצוגה */ }
}

async function toggleBot() {
  const running = document.getElementById("botToggleBtn").dataset.running === "1";
  try {
    const resp = await fetch(running ? "/api/bot/stop" : "/api/bot/start", { method: "POST" });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "פעולה נכשלה");
  } catch (e) {
    alert("שגיאה: " + e.message);
  }
  loadBotStatus();
}
pollWhenVisible(loadBotStatus, 3000);

// item: log spam - אותו עיקרון בדיוק כמו appendLogBatch/_pruneConsoleLog
// למעלה (קונסולת הסקריפטים), על קונסולת הבוט: תקרת-זמן+מספר-שורות ו-DOM
// operation אחת לכל batch, לא תלוי מה הבוט עצמו מדפיס.
let _botConsoleEntries = [];

function _pruneBotConsoleLog() {
  // ראו _pruneConsoleLog למעלה - אותו תיקון O(n²)->O(n) בדיוק, splice() יחיד
  // במקום shift() בלולאה.
  const cutoff = Date.now() - CONSOLE_LOG_RETENTION_MS;
  const excess = _botConsoleEntries.length - CONSOLE_LOG_MAX_LINES;
  let removeCount = 0;
  while (removeCount < _botConsoleEntries.length && (_botConsoleEntries[removeCount].time < cutoff || removeCount < excess)) {
    removeCount++;
  }
  if (removeCount === 0) return;
  for (const entry of _botConsoleEntries.splice(0, removeCount)) entry.el.remove();
}

function appendBotLogBatch(lines) {
  if (!lines.length) return;
  const c = document.getElementById("botConsole");
  const frag = document.createDocumentFragment();
  const now = Date.now();
  for (const {line} of lines) {
    const node = document.createTextNode(line);
    frag.appendChild(node);
    _botConsoleEntries.push({el: node, time: now});
  }
  c.appendChild(frag);
  c.scrollTop = c.scrollHeight;
  _pruneBotConsoleLog();
}

function connectBotWs() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/bot");
  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === "log_batch") appendBotLogBatch(msg.lines);
  };
  ws.onclose = () => setTimeout(connectBotWs, 1500);
}

async function refreshRssList() {
  const res = await fetch("/api/bot/rss");
  const feeds = await res.json();
  const container = document.getElementById("rssList");
  container.innerHTML = "";
  for (const feed of feeds) {
    const row = document.createElement("div");
    row.className = "tc-list-row";
    const label = document.createElement("span");
    label.textContent = `📰 ${feed.name} | ערוץ: ${feed.channel_id}`;
    const btn = document.createElement("button");
    btn.textContent = "מחיקה";
    btn.onclick = () => deleteRssFeed(feed.id);
    row.appendChild(btn);
    row.appendChild(label);
    container.appendChild(row);
  }
}

async function addRssFeed() {
  const name = document.getElementById("rssName").value.trim();
  const url = document.getElementById("rssUrl").value.trim();
  const channel_id = document.getElementById("rssChannel").value.trim();
  if (!name || !url || !channel_id) return;
  const resp = await fetch("/api/bot/rss", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, url, channel_id }),
  });
  if (resp.ok) {
    document.getElementById("rssName").value = "";
    document.getElementById("rssUrl").value = "";
    document.getElementById("rssChannel").value = "";
    refreshRssList();
  } else {
    const data = await resp.json();
    alert("שגיאה: " + (data.error || "הוספה נכשלה"));
  }
}

async function deleteRssFeed(id) {
  await fetch(`/api/bot/rss/${id}`, { method: "DELETE" });
  refreshRssList();
}

async function refreshSteamList() {
  const res = await fetch("/api/bot/steam");
  const games = await res.json();
  const container = document.getElementById("steamList");
  container.innerHTML = "";
  for (const game of games) {
    const row = document.createElement("div");
    row.className = "tc-list-row";
    const label = document.createElement("span");
    label.textContent = `🎮 ${game.name} (${game.app_id}) | ערוץ: ${game.channel_id}`;
    const btn = document.createElement("button");
    btn.textContent = "מחיקה";
    btn.onclick = () => deleteSteamGame(game.id);
    row.appendChild(btn);
    row.appendChild(label);
    container.appendChild(row);
  }
}

async function addSteamGame() {
  const name = document.getElementById("steamName").value.trim();
  const app_id = document.getElementById("steamAppId").value.trim();
  const channel_id = document.getElementById("steamChannel").value.trim();
  if (!name || !app_id || !channel_id) return;
  const resp = await fetch("/api/bot/steam", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, app_id, channel_id }),
  });
  if (resp.ok) {
    document.getElementById("steamName").value = "";
    document.getElementById("steamAppId").value = "";
    document.getElementById("steamChannel").value = "";
    refreshSteamList();
  } else {
    const data = await resp.json();
    alert("שגיאה: " + (data.error || "הוספה נכשלה"));
  }
}

async function deleteSteamGame(id) {
  await fetch(`/api/bot/steam/${id}`, { method: "DELETE" });
  refreshSteamList();
}

// 21.10.2026: "📊 הגדרות עורך הגרפים" - החלון של עורך הגרפים (86-dataviz-publish.js), גם מכאן; ה-bundles שלו נטענים לפי דרישה
async function openDatavizSettings() {
  try {
    await uiLoadLazy("dataviz");
    await uiLoadLazy("dataviz_pro");
    await uiLoadLazy("dataviz_tools");
    await uiLoadLazy("dataviz_plus");
    await dvzOpenSettings();
  } catch (e) {
    uiToast(e.message, "warn");
  }
}

// --- עיצוב (ערכת נושא/צבע מותאם/שפת ה-GUI השולחני) ---
let _themesCache = {};
let _selectedThemeName = "Green";

function _applyAccentLive() {
  // בונוס - עמוד הדפדפן עצמו (בניגוד ל-GUI השולחני) לא צריך הפעלה מחדש כדי
  // להחיל צבע חדש, זה רק משתנה CSS. לא חובה לתכונה הזו, אבל חינם כמעט.
  const colors = _themesCache[_selectedThemeName];
  // גל 15: --brand הוא המקור - --color-accent וכל הגוונים הנגזרים (רך/קו/טבעת) מחושבים ממנו
  if (colors) {
    document.documentElement.style.setProperty("--brand", colors.accent);
    document.documentElement.style.setProperty("--brand-strong", `color-mix(in srgb, ${colors.accent} 72%, white)`);
  }
}

// item: מספור סרטונים - עריכה בפועל של "מספר התחלתי" (לא רק שדה שנטען מחדש
// עם אותו ערך) היא "שינוי ידני" מפורש - מאפסת את המונה בפועל על הדיסק
// *עכשיו*, זהה בעיקרון ל-ui/settings_tab.py's _on_number_start_changed
// (דסקטופ). dataset.lastValue (מתעדכן גם בטעינת פרופיל, ראו למעלה) מונע
// איפוס בטעות בכל "change" שלא שינה בפועל שום דבר.
document.getElementById("veNumberStart").addEventListener("change", async (e) => {
  const input = e.target;
  const typed = input.value.trim();
  if (!typed || typed === input.dataset.lastValue) return;
  const value = parseInt(typed, 10);
  if (!Number.isFinite(value) || value < 1) return;
  input.dataset.lastValue = typed;
  try {
    await fetch("/api/video_editor/reset_counter", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    });
  } catch (e) { /* לא קריטי - הריצה הבאה עדיין תעבוד, רק בלי האיפוס הידני הזה */ }
});

// --- תזמון (⏰) ---
const WEEKDAY_LABELS_HE = { sun: "ראשון", mon: "שני", tue: "שלישי", wed: "רביעי", thu: "חמישי", fri: "שישי", sat: "שבת" };

function populateSchedulerScriptDropdown() {
  const select = document.getElementById("schScript");
  select.innerHTML = "";
  for (const s of state.scripts) {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = s.name;
    select.appendChild(opt);
  }
}

function updateSchedulerFieldVisibility() {
  const type = document.getElementById("schType").value;
  document.getElementById("schWeekdayRow").hidden = type !== "weekly";
  document.getElementById("schIntervalRow").hidden = type !== "interval_hours";
}

function _describeSchedule(task) {
  if (task.schedule_type === "daily") return `כל יום ב-${task.time}`;
  if (task.schedule_type === "weekly") return `כל ${WEEKDAY_LABELS_HE[task.weekday] || task.weekday} ב-${task.time}`;
  return `כל ${task.interval_hours} שעות`;
}

// הודעה עם ערך: הטקסט הקבוע (מתורגם ב-en.json) ואחריו הערך ב-<code> נפרד
function _infoLine(container, text, value) {
  const line = document.createElement("div");
  const label = document.createElement("span");
  label.textContent = text;
  line.appendChild(label);
  if (value) {
    const code = document.createElement("code");
    code.textContent = value;
    // ערך בלי עברית (תאריך, נתיב): ltr, אחרת מוצג הפוך
    code.dir = /[֐-׿]/.test(value) ? "auto" : "ltr";
    line.append(" ", code);
  }
  container.appendChild(line);
}

// 19.10.2026: טיימר התעוררות של Windows למשימה המתוזמנת הבאה (utils/bot/wake_timer.py) - כבוי כברירת מחדל
async function loadWakeTimer() {
  if (!document.getElementById("schWakeTimer")) return;
  try {
    _renderWakeTimer(await (await fetch("/api/scheduler/wake_timer")).json());
  } catch (e) {
    console.warn(e);
  }
}

function _renderWakeTimer(data) {
  document.getElementById("schWakeTimer").checked = !!data.enabled;
  const info = document.getElementById("schWakeInfo");
  info.replaceChildren();
  if (data.enabled && data.wake_at) _infoLine(info, "המחשב יתעורר ב:", data.wake_at.replace("T", " "));
  else if (data.enabled) _infoLine(info, "אין כרגע משימה קרובה להעיר אליה.");
  if (data.error) _infoLine(info, "הרישום ב-Task Scheduler נכשל:", data.error);
  if (data.enabled && data.windows_allows === false) _infoLine(info, "שים לב: 'Allow wake timers' כבוי בתוכנית החשמל של Windows - המחשב לא יתעורר.");
}

async function saveWakeTimer() {
  const resp = await fetch("/api/scheduler/wake_timer", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: document.getElementById("schWakeTimer").checked }) });
  _renderWakeTimer(await resp.json());
}

async function refreshSchedulerTaskList() {
  loadWakeTimer();
  const res = await fetch("/api/scheduler/tasks");
  const tasks = await res.json();
  const container = document.getElementById("schedulerList");
  container.innerHTML = "";
  if (!tasks.length) {
    container.innerHTML = '<div class="empty-msg">אין משימות מתוזמנות עדיין.</div>';
    return;
  }
  for (const task of tasks) {
    const row = document.createElement("div");
    row.className = "tc-list-row";

    const label = document.createElement("span");
    label.textContent = `${task.script_name} - ${_describeSchedule(task)}`;

    const actions = document.createElement("span");
    const toggleBtn = document.createElement("button");
    toggleBtn.textContent = task.enabled ? "🟢 פעיל" : "⚪ כבוי";
    toggleBtn.style.marginLeft = "6px";
    toggleBtn.onclick = () => toggleScheduledTask(task.id, !task.enabled);
    const delBtn = document.createElement("button");
    delBtn.textContent = "🗑️ מחק";
    delBtn.onclick = () => deleteScheduledTask(task.id);
    actions.appendChild(delBtn);
    actions.appendChild(toggleBtn);

    row.appendChild(actions);
    row.appendChild(label);
    container.appendChild(row);
  }
}

async function addScheduledTask() {
  const payload = {
    script_id: document.getElementById("schScript").value,
    schedule_type: document.getElementById("schType").value,
    time_str: document.getElementById("schTime").value,
    weekday: document.getElementById("schWeekday").value,
    interval_hours: parseInt(document.getElementById("schInterval").value || "24", 10),
  };
  try {
    const resp = await fetch("/api/scheduler/tasks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!resp.ok) throw new Error((await resp.json()).error || "הוספה נכשלה");
    refreshSchedulerTaskList();
  } catch (e) {
    alert("שגיאה: " + e.message);
  }
}

async function toggleScheduledTask(id, enabled) {
  await fetch(`/api/scheduler/tasks/${id}/toggle`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled }) });
  refreshSchedulerTaskList();
}

async function deleteScheduledTask(id) {
  await fetch(`/api/scheduler/tasks/${id}`, { method: "DELETE" });
  refreshSchedulerTaskList();
}

// --- Rocket Shorts (תיקיות/Overlay/מונה/פרופיל איכות/ריקאפ שבועי/כתוביות) ---
const ROCKET_RECAP_DAYS_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"];

function _populateRocketRecapDaySelect() {
  const select = document.getElementById("rsRecapDay");
  if (select.options.length) return;
  ROCKET_RECAP_DAYS_HE.forEach((label, idx) => {
    const opt = document.createElement("option");
    opt.value = idx;
    opt.textContent = label;
    select.appendChild(opt);
  });
}

async function loadRocketSettings() {
  _populateRocketRecapDaySelect();
  const [presetsRes, settingsRes] = await Promise.all([fetch("/api/rocket_settings/presets"), fetch("/api/rocket_settings")]);
  const presetsData = await presetsRes.json();
  const settings = await settingsRes.json();

  const presetSelect = document.getElementById("rsPreset");
  presetSelect.innerHTML = "";
  for (const name of presetsData.presets) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    presetSelect.appendChild(opt);
  }
  if (settings.preset) presetSelect.value = settings.preset;

  document.getElementById("rsInputDir").value = settings.input_dir;
  document.getElementById("rsOutputDir").value = settings.output_dir;
  document.getElementById("rsOverlayPath").value = settings.watermark_image_path;
  document.getElementById("rsCounter").value = settings.counter;
  document.getElementById("rsTitlePrefix").value = settings.title_prefix;
  document.getElementById("rsGameName").value = settings.game_name;
  document.getElementById("rsOutputResolution").value = settings.output_resolution;
  document.getElementById("rsRecapEnabled").checked = settings.enable_weekly_recap;
  document.getElementById("rsRecapPeriod").value = settings.weekly_recap_period;
  document.getElementById("rsRecapDay").value = settings.weekly_recap_day;
  document.getElementById("rsCaptionsEnabled").checked = settings.enable_captions;
  document.getElementById("rsCaptionsTranslateEnabled").checked = settings.enable_captions_translate;
  document.getElementById("rsClipHotkey").value = settings.clip_hotkey;
  document.getElementById("rsCaptureVoiceChannelId").value = settings.capture_voice_channel_id;
  document.getElementById("rsCaptureWatchDir").value = settings.capture_watch_dir;
  document.getElementById("rsMaxConcurrentRenders").value = settings.max_concurrent_renders;
  await _loadRocketAutoChain(settings);
}

// גל 32: שרשור מ-OBS/תיקיית לכידה - מה עושים עם קליפ שנכנס, באיזה סגנון, ומה קרה לאחרונים
async function _loadRocketAutoChain(settings) {
  const select = document.getElementById("rsAutoChainProfile");
  select.innerHTML = "";
  let names = [];
  try { names = Object.keys(await (await fetch("/api/video_editor_profiles")).json()).sort(); } catch (e) { /* בלי סגנונות - רק "לפרסם ישר" שימושי */ }
  const placeholder = new Option(names.length ? "בחר סגנון..." : "אין סגנונות שמורים - שמור אחד בעורך", "");
  select.appendChild(placeholder);
  for (const name of names) select.appendChild(new Option(name, name));
  if (settings.auto_chain_profile && !names.includes(settings.auto_chain_profile)) {
    select.appendChild(new Option(`${settings.auto_chain_profile} (לא נמצא)`, settings.auto_chain_profile));
  }
  select.value = settings.auto_chain_profile || "";
  document.getElementById("rsAutoChain").value = settings.auto_chain || "off";
  document.getElementById("rsAutoChainDryRun").checked = !!settings.auto_chain_dry_run;
  document.getElementById("rsSeoAi").checked = settings.seo_ai !== false;
  _syncRocketAutoChain();
  _renderRocketAutoChainRecent();
}

function _syncRocketAutoChain() {
  const mode = document.getElementById("rsAutoChain").value;
  document.getElementById("rsAutoChainProfile").hidden = !mode.startsWith("edit");
  document.getElementById("rsAutoChainDryRun").closest("label").hidden = mode === "off" || mode === "edit";
}

async function _renderRocketAutoChainRecent() {
  const box = document.getElementById("rsAutoChainRecent");
  try {
    const { recent } = await (await fetch("/api/auto_chain/recent")).json();
    box.replaceChildren(...recent.map(entry => {
      const row = document.createElement("div");
      const at = new Date(entry.at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      row.textContent = `${at} · ${entry.text}`;
      return row;
    }));
  } catch (e) { box.replaceChildren(); }
}

// item: מודעות למגבלת סשנים אמיתית של NVENC - בדיקה אמיתית (utils/nvenc_probe.py),
// לא אוטומטית (לוקחת כמה שניות ומעמיסה זמנית על ה-GPU) - רק על-פי-בקשה.
async function probeNvencLimit() {
  const status = document.getElementById("nvencProbeStatus");
  status.textContent = "בודק... (מריץ כמה קידודי NVENC זעירים בו-זמנית, עד כמה שניות)";
  try {
    const res = await fetch("/api/rocket_settings/probe_nvenc", { method: "POST" });
    const data = await res.json();
    if (!res.ok || data.error) { status.textContent = "⚠️ " + (data.error || "הבדיקה נכשלה."); return; }
    if (data.detected <= 0) {
      status.textContent = "לא זוהה NVENC פעיל (אין GPU של NVIDIA, או שהוא לא נתמך) - ההגדרה הידנית נשארת ללא שינוי.";
      return;
    }
    document.getElementById("rsMaxConcurrentRenders").value = data.detected;
    status.textContent = `✅ הכרטיס תומך ב-${data.detected} רינדורים מקבילים בפועל - הוחל אוטומטית (זכור/י ללחוץ "שמור הגדרות").`;
  } catch (e) {
    status.textContent = "⚠️ הבדיקה נכשלה: " + e.message;
  }
}

function adjustRocketCounter(delta) {
  const input = document.getElementById("rsCounter");
  input.value = Math.max(1, parseInt(input.value || "1", 10) + delta);
}

async function playSoundboardSound(sound) {
  try {
    const resp = await fetch("/api/soundboard/play", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sound }) });
    if (!resp.ok) throw new Error((await resp.json()).error || "השמעה נכשלה");
  } catch (e) {
    alert("שגיאה: " + e.message);
  }
}

// --- גלריית קליפים + אשף יצוא ל-TikTok/YouTube (זהה ל-ui/stats_tab.py) ---
let _selectedClipPath = null;
let _youtubeStatusPoll = null;
// תגיות שכבר נטענו לכל קליפ (path -> tags[]), למסנן "סנן לפי תגית" - נמלא
// אסינכרונית תוך כדי loadClipTags, אז filterGallery() נקרא שוב בכל פעם שתגית
// חדשה מגיעה (item: clip gallery search/filter by tag).
let _clipTagsByPath = {};

