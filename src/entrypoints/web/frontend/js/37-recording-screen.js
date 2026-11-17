// 37-recording-screen.js - מסך "🔴 הקלטה" (16.11.2026, ClipForge 2.0): replay buffer ("שמור את X השניות האחרונות"),
// הקלטה מלאה, מסך / משחק במחשב או קונסולה דרך כרטיס לכידה, ושליטה ב-OBS. נטען רק כשפותחים את המסך
// (LAZY_JS["recording"], lazy-html:recording). הכול דרך /api/recording/* (routes/recording.py). מתרענן כל 2 שניות כשגלוי.
let _recTimer = null;
let _recSettings = null;
let _recConsoles = [];

async function loadRecordingScreen() {
  if (!_recTimer) {
    _recTimer = setInterval(() => { if (_recVisible()) refreshRecStatus(); }, 2000);
  }
  const data = await _recGet("/api/recording/settings");
  if (data) {
    _recSettings = data.settings;
    _recConsoles = data.consoles || [];
    document.getElementById("recLoopbackHint").hidden = !!data.loopback;
    _fillRecConsoles();
    _fillRecForm(_recSettings);
  }
  await Promise.all([loadRecDevices(), refreshRecStatus(), loadRecImportSources()]);
}

function _recVisible() {
  const panel = document.querySelector('[data-tab-panel="recording"]');
  return !document.hidden && panel && !panel.hidden;
}

async function _recGet(url) {
  try {
    const res = await fetch(url);
    return res.ok ? await res.json() : null;
  } catch (e) {
    return null;
  }
}

async function _recPost(url, body) {
  const res = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "הפעולה נכשלה");
  return data;
}

function _recOptions(select, items, selected, emptyLabel) {
  const options = [new Option(emptyLabel, "")];
  for (const item of items) options.push(new Option(item.label || item.name, item.id || item.name, false, (item.id || item.name) === selected));
  select.replaceChildren(...options);
  if (selected && !items.some((i) => (i.id || i.name) === selected)) {
    select.appendChild(new Option(selected + " (לא מחובר)", selected, false, true));
  }
}

function _fillRecConsoles() {
  _recOptions(document.getElementById("recConsole"), _recConsoles, _recSettings ? _recSettings.console : "", "כרטיס בלי קונסולה מוגדרת");
  recShowConsoleNote();
}

function recShowConsoleNote() {
  const id = document.getElementById("recConsole").value;
  const profile = _recConsoles.find((c) => c.id === id);
  document.getElementById("recConsoleNote").textContent = profile ? profile.note : "";
}

async function loadRecDevices(refresh) {
  const devices = await _recGet("/api/recording/devices" + (refresh ? "?refresh=1" : ""));   // refresh: גם מודדים את הכרטיס מחדש
  if (!devices || !_recSettings) return;
  _recOptions(document.getElementById("recDeviceVideo"), devices.video, _recSettings.device_video, "בחר כרטיס");
  _recOptions(document.getElementById("recDeviceAudio"), devices.audio, _recSettings.device_audio, "בלי שמע מהכרטיס");
  _recOptions(document.getElementById("recMic"), devices.audio, _recSettings.mic, "בלי מיקרופון");
  _recOptions(document.getElementById("recFacecam"), devices.video, _recSettings.facecam, "בלי מצלמה");
}

function _fillRecForm(s) {
  document.getElementById("recEngine").value = s.engine;
  document.getElementById("recSource").value = s.source;
  document.getElementById("recScreen").value = s.screen_index;
  document.getElementById("recGameAudio").checked = s.game_audio;
  document.getElementById("recCardPrefer").value = s.card_prefer;
  document.getElementById("recCodec").value = s.codec;
  document.getElementById("recFps").value = s.fps;
  document.getElementById("recQuality").value = s.quality;
  document.getElementById("recReplaySeconds").value = s.replay_seconds;
  document.getElementById("recHotkeySave").value = s.hotkey_save_replay;
  document.getElementById("recHotkeyRecord").value = s.hotkey_toggle_record;
  recFormChanged();
}

function recFormChanged() {
  const obs = document.getElementById("recEngine").value === "obs";
  const device = document.getElementById("recSource").value === "device";
  document.getElementById("recFfmpegFields").hidden = obs;
  document.getElementById("recScreenFields").hidden = device;
  document.getElementById("recDeviceFields").hidden = !device;
  document.getElementById("recObsSection").hidden = !obs;
  if (obs) loadRecScenes();
}

function _readRecForm() {
  const value = (id) => document.getElementById(id).value;
  return {
    engine: value("recEngine"), source: value("recSource"), screen_index: Number(value("recScreen")),
    game_audio: document.getElementById("recGameAudio").checked, console: value("recConsole"), card_prefer: value("recCardPrefer"),
    device_video: value("recDeviceVideo"), device_audio: value("recDeviceAudio"), mic: value("recMic"),
    facecam: value("recFacecam"), codec: value("recCodec"), fps: Number(value("recFps")), quality: Number(value("recQuality")),
    replay_seconds: Number(value("recReplaySeconds")), hotkey_save_replay: value("recHotkeySave"),
    hotkey_toggle_record: value("recHotkeyRecord"),
  };
}

async function saveRecSettings() {
  try {
    const data = await _recPost("/api/recording/settings", _readRecForm());
    _recSettings = data.settings;
    _fillRecForm(_recSettings);
    uiToast("הגדרות ההקלטה נשמרו", "ok");
  } catch (e) {
    uiToast(e.message, "warn");
  }
}

async function recAction(action) {
  try {
    _renderRecStatus(await _recPost(`/api/recording/${action}`));
    if (action === "replay/save") uiToast("הקליפ נשמר", "ok");
  } catch (e) {
    uiToast(e.message, "warn");
    refreshRecStatus();
  }
}

async function refreshRecStatus() {
  const status = await _recGet("/api/recording/status");
  if (status) _renderRecStatus(status);
}

function _renderRecStatus(s) {
  const box = document.getElementById("recStatus");
  if (!box) return;
  box.replaceChildren();
  const line = (text, className) => {
    const div = document.createElement("div");
    div.textContent = text;
    if (className) div.className = className;
    box.appendChild(div);
  };
  if (s.recording) line("🔴 מקליט עכשיו", "rec-live");
  if (s.replay) line(s.replay_buffered_seconds == null ? "⏺ Replay פועל" : `⏺ Replay פועל - ${s.replay_buffered_seconds} שניות בזיכרון`, "rec-live");
  if (!s.recording && !s.replay) line("לא מקליט");
  if (s.hotkeys) line("⌨️ מקשי הקיצור פעילים");
  if (s.last_saved) line("💾 נשמר אחרון: " + s.last_saved);
  if (s.notice) line("ℹ️ " + s.notice);
  if (s.error) line("⚠️ " + s.error, "rec-error");
  _renderRecImport(s.import || {});
  document.getElementById("recReplayStart").disabled = !!s.replay;
  document.getElementById("recReplaySave").disabled = !s.replay;
  document.getElementById("recReplayStop").disabled = !s.replay;
  document.getElementById("recRecordStart").disabled = !!s.recording;
  document.getElementById("recRecordStop").disabled = !s.recording;
}

async function loadRecScenes() {
  const box = document.getElementById("recScenes");
  const res = await fetch("/api/recording/obs/scenes").catch(() => null);
  const data = res ? await res.json().catch(() => ({})) : {};
  box.replaceChildren();
  if (!res || !res.ok) {
    box.textContent = data.error || "אין חיבור ל-OBS";
    return;
  }
  for (const scene of data.scenes || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = scene;
    button.className = scene === data.current ? "rec-scene active" : "rec-scene";
    button.onclick = async () => {
      try {
        await _recPost("/api/recording/obs/scene", {scene});
        loadRecScenes();
      } catch (e) {
        uiToast(e.message, "warn");
      }
    };
    box.appendChild(button);
  }
}

// 16.11.2026: ייבוא מקונסולה / תוכנת הקלטה (utils/capture/import_presets.py, importer.py)
async function loadRecImportSources() {
  const data = await _recGet("/api/recording/import/sources");
  const select = document.getElementById("recImportSource");
  if (!data || !select) return;
  const sources = data.sources || [];
  select.replaceChildren(...sources.map((s) => new Option(`${s.label} - ${s.new} חדשים`, s.id)));
  document.getElementById("recImportBtn").disabled = !sources.length;
  if (!sources.length) document.getElementById("recImportStatus").textContent = "לא נמצאו קליפים של תוכנת הקלטה או קונסולה. חבר את הכונן ונסה שוב.";
}

async function startRecImport() {
  try {
    _renderRecStatus(await _recPost("/api/recording/import", {source: document.getElementById("recImportSource").value}));
  } catch (e) {
    uiToast(e.message, "warn");
  }
}

function _renderRecImport(state) {
  const box = document.getElementById("recImportStatus");
  if (!box || !state.label) return;
  if (state.error) box.textContent = "⚠️ " + state.error;
  else if (state.running) box.textContent = `📥 מייבא מ-${state.label}: ${state.done}/${state.total}`;
  else box.textContent = `✅ יובאו ${state.done} קליפים מ-${state.label} לתיקיית ה-Import`;
  document.getElementById("recImportBtn").disabled = !!state.running;
}
