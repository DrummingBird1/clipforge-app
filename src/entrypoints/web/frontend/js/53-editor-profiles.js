// ============================================================================
// גל 6 של 102-ההצעות: פרופילים - השלב הבא (items 60-68)
// ============================================================================

const VE_PROFILE_COLORS = {"": "", red: "🔴", orange: "🟠", yellow: "🟡", green: "🟢", blue: "🔵", purple: "🟣", gray: "⚫"};

function _veProfileMeta(name) {
  const meta = (state.videoEditorProfileMeta || {})[name] || {};
  return {tags: [], color: "", notes: "", run_count: 0, last_used_at: null, is_default: false, parent: null, created_at: null, ...meta};
}

function _veProfileOptionLabel(name) {
  const meta = _veProfileMeta(name);
  const color = VE_PROFILE_COLORS[meta.color] ? VE_PROFILE_COLORS[meta.color] + " " : "";
  return `${color}${name}${meta.is_default ? " ⭐" : ""}${meta.parent ? " 🧬" : ""}`;
}

function _veSortedProfileNames(mode) {
  const names = Object.keys(state.videoEditorProfiles || {});
  const meta = (n) => _veProfileMeta(n);
  const byName = (a, b) => a.localeCompare(b, "he");
  if (mode === "recent") return names.sort((a, b) => String(meta(b).last_used_at || "").localeCompare(String(meta(a).last_used_at || "")) || byName(a, b));
  if (mode === "count") return names.sort((a, b) => (meta(b).run_count - meta(a).run_count) || byName(a, b));
  if (mode === "created") return names.sort((a, b) => String(meta(b).created_at || "").localeCompare(String(meta(a).created_at || "")) || byName(a, b));
  return names.sort(byName);
}

function _veRenderProfileTagFilterOptions() {
  const select = document.getElementById("veProfileTagFilter");
  const current = select.value;
  const tags = new Set();
  for (const name of Object.keys(state.videoEditorProfiles || {})) for (const tag of _veProfileMeta(name).tags) tags.add(tag);
  select.innerHTML = '<option value="">כל התגיות</option>';
  for (const tag of Array.from(tags).sort((a, b) => a.localeCompare(b, "he"))) {
    const option = document.createElement("option");
    option.value = tag; option.textContent = "#" + tag;
    select.appendChild(option);
  }
  select.value = tags.has(current) ? current : "";
  select.hidden = !tags.size;
  select.previousElementSibling.hidden = !tags.size;
}

// item 62: פרופילים מהירים - 3-5 הנפוצים ביותר (לפי מספר הרצות). גל 58: בראש בורר הסגנון (קבוצה "⚡ הכי בשימוש")
// ולא כשבבים נפרדים בשורת הסטטוס - מקום אחד לבחירת סגנון. אותו סגנון מופיע גם ב"הסגנונות שלי" - _veStyleOptions מסנן כפילויות
function _veRenderProfileChips() {
  const select = document.getElementById("vePreset");
  const old = document.getElementById("veTopProfilesGroup");
  if (old) old.remove();
  const top = _veSortedProfileNames("count").filter(n => _veProfileMeta(n).run_count > 0).slice(0, 5);
  if (!top.length) return;
  const current = select.value;
  const group = document.createElement("optgroup");
  group.id = "veTopProfilesGroup";
  group.label = "⚡ הכי בשימוש";
  for (const name of top) {
    const opt = document.createElement("option");
    opt.value = "profile:" + name;
    opt.textContent = _veProfileOptionLabel(name);
    opt.title = `${_veProfileMeta(name).run_count} הרצות`;
    group.appendChild(opt);
  }
  select.insertBefore(group, select.querySelector(":scope > optgroup"));
  select.value = current;
}

// כל סגנון פעם אחת (בלי הכפילויות של "⚡ הכי בשימוש") - לשבבים של המצב הפשוט ולספרייה
function _veStyleOptions() {
  return [..._veEl("vePreset").options].filter(o => o.value && o.parentElement.id !== "veTopProfilesGroup");
}

// item 60: תגיות/צבע/הערות.
function openVeAnnotateDialog() {
  const name = _currentVeProfileName();
  if (!name) return;
  const meta = _veProfileMeta(name);
  document.getElementById("veAnnotateName").textContent = name;
  document.getElementById("veAnnotateTags").value = meta.tags.join(", ");
  document.getElementById("veAnnotateNotes").value = meta.notes;
  const colors = document.getElementById("veAnnotateColors");
  colors.innerHTML = "";
  colors.dataset.value = meta.color || "";
  for (const [key, emoji] of Object.entries(VE_PROFILE_COLORS)) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("role", "radio");
    btn.setAttribute("aria-checked", String(key === (meta.color || "")));
    btn.setAttribute("aria-label", key || "בלי צבע");
    btn.textContent = emoji || "∅";
    btn.onclick = () => {
      colors.dataset.value = key;
      for (const b of colors.children) b.setAttribute("aria-checked", String(b === btn));
    };
    colors.appendChild(btn);
  }
  document.getElementById("veAnnotateModalBg").classList.add("show");
}

async function saveVeAnnotations() {
  const name = _currentVeProfileName();
  const res = await fetch("/api/video_editor_profiles/" + encodeURIComponent(name) + "/annotate", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      tags: document.getElementById("veAnnotateTags").value,
      color: document.getElementById("veAnnotateColors").dataset.value || "",
      notes: document.getElementById("veAnnotateNotes").value,
    }),
  });
  if (!res.ok) { alert((await res.json()).error || "השמירה נכשלה."); return; }
  document.getElementById("veAnnotateModalBg").classList.remove("show");
  await loadVideoEditorProfiles();
  document.getElementById("vePreset").value = "profile:" + name;
  _loadAndShowProfileMeta(name);
}

// item 63: פרופיל ברירת מחדל מפורש.
async function toggleVeDefaultProfile() {
  const name = _currentVeProfileName();
  if (!name) return;
  const isDefault = _veProfileMeta(name).is_default;
  const res = await fetch("/api/video_editor_profile_default", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name: isDefault ? null : name})});
  if (!res.ok) { alert((await res.json()).error || "הפעולה נכשלה."); return; }
  await loadVideoEditorProfiles();
  document.getElementById("vePreset").value = "profile:" + name;
  _loadAndShowProfileMeta(name);
}

// item 66: ייצוא/ייבוא של כל הפרופילים בבת אחת.
async function exportAllVideoEditorProfiles() {
  const res = await fetch("/api/video_editor_profiles_export_all");
  if (!res.ok) { alert("הייצוא נכשל."); return; }
  const data = await res.json();
  const blob = new Blob([JSON.stringify(data, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `clipforge_video_editor_profiles_${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

function openVeImportAllDialog() {
  document.getElementById("veImportAllFile").value = "";
  document.getElementById("veImportAllResult").textContent = "";
  document.getElementById("veImportAllModalBg").classList.add("show");
}

async function runVeImportAll() {
  const file = document.getElementById("veImportAllFile").files[0];
  const out = document.getElementById("veImportAllResult");
  if (!file) { out.textContent = "⚠️ בחר קובץ קודם."; return; }
  let data;
  try { data = JSON.parse(await file.text()); } catch (e) { out.textContent = "⚠️ הקובץ אינו JSON תקין."; return; }
  const strategy = document.querySelector('input[name="veImportAllStrategy"]:checked').value;
  const res = await fetch("/api/video_editor_profiles_import_all", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({data, strategy})});
  const result = await res.json();
  if (!res.ok) { out.textContent = "⚠️ " + (result.error || "הייבוא נכשל."); return; }
  out.textContent = `✅ יובאו ${result.imported.length}` + (result.renamed.length ? ` · ${result.renamed.length} בשם חדש` : "") + (result.skipped.length ? ` · ${result.skipped.length} דולגו (כבר קיימים)` : "");
  await loadVideoEditorProfiles();
}

// item 68: ירושה.
async function createVeChildProfile() {
  const parent = _currentVeProfileName();
  if (!parent) return;
  const name = await vePrompt(`שם לסגנון שיורש מ-"${parent}":`, {value: parent + " - וריאציה"});
  if (name === null || !name.trim()) return;
  let res = await fetch("/api/video_editor_profiles/" + encodeURIComponent(parent) + "/duplicate", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({new_name: name})});
  if (!res.ok) { alert((await res.json()).error || "יצירת הסגנון נכשלה."); return; }
  const created = (await res.json()).name;
  res = await fetch("/api/video_editor_profiles/" + encodeURIComponent(created) + "/parent", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({parent})});
  if (!res.ok) { alert((await res.json()).error || "קביעת ההורה נכשלה."); return; }
  await loadVideoEditorProfiles();
  document.getElementById("vePreset").value = "profile:" + created;
  applyVideoEditorPreset();
}

async function pullVeProfileFromParent() {
  const name = _currentVeProfileName();
  if (!name) return;
  const parent = _veProfileMeta(name).parent;
  if (!(await veConfirm(`לעדכן את "${name}" לפי השינויים הנוכחיים ב-"${parent}"?\nשדות ש-"${name}" שינה בעצמו לא ייגעו.`))) return;
  const res = await fetch("/api/video_editor_profiles/" + encodeURIComponent(name) + "/pull_parent", {method: "POST"});
  const data = await res.json();
  if (!res.ok) { alert(data.error || "המשיכה נכשלה."); return; }
  await loadVideoEditorProfiles();
  document.getElementById("vePreset").value = "profile:" + name;
  applyVideoEditorPreset();
  alert(data.pulled_fields.length ? `עודכנו ${data.pulled_fields.length} שדות מההורה: ${data.pulled_fields.map(f => (VE_FAVORITABLE_FIELDS[f] || {}).label || f).join(", ")}` : "הסגנון כבר מעודכן - אין שינויים חדשים בהורה.");
}

// item 67: שיתוף בקישור/QR - רק שדות ששונו מברירת המחדל, דחוסים (deflate-raw)
// ומקודדים ל-base64url, כדי שהקישור יהיה קצר מספיק לקוד QR.
function _veBase64UrlEncode(bytes) {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function _veBase64UrlDecode(text) {
  const padded = text.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((text.length + 3) % 4);
  return Uint8Array.from(atob(padded), c => c.charCodeAt(0));
}

async function _veDeflate(text) {
  const stream = new Blob([text]).stream().pipeThrough(new CompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

async function _veInflate(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  return await new Response(stream).text();
}

function _veNonDefaultSettings(settings) {
  const out = {};
  for (const [key, value] of Object.entries(settings || {})) {
    if (value === null || value === undefined || key === "favorite_fields" || key === "queue_files" || key === "folder") continue;
    const meta = VE_FAVORITABLE_FIELDS[key];
    const el = meta && document.getElementById(meta.id);
    if (el && _veFieldDefaults && el.id in _veFieldDefaults) {
      const def = _veFieldDefaults[el.id];
      if (el.type === "checkbox" ? !!value === def : String(value) === String(def)) continue;
    } else if (value === false || value === "") continue;
    out[key] = value;
  }
  return out;
}

let _veShareState = null;

async function openVeShareDialog() {
  const name = _currentVeProfileName();
  if (!name) return;
  const settings = _veNonDefaultSettings((state.videoEditorProfiles || {})[name]);
  const packed = _veBase64UrlEncode(await _veDeflate(JSON.stringify({n: name, s: settings})));
  const lan = await (await fetch("/api/lan_info")).json();
  _veShareState = {name, packed, lan};
  document.getElementById("veShareName").textContent = name;
  document.getElementById("veShareLanHint").textContent = lan.lan
    ? "📱 הקישור משתמש בכתובת הרשת המקומית - נפתח מהטלפון כשהוא באותה רשת."
    : "ℹ️ השרת לא רץ במצב --lan, אז הקישור נפתח רק מהמחשב הזה (הפעל עם --lan כדי לפתוח מהטלפון).";
  renderVeShare();
  document.getElementById("veShareModalBg").classList.add("show");
}

async function renderVeShare() {
  if (!_veShareState) return;
  const base = _veShareState.lan.base_url || location.origin;
  const params = new URLSearchParams({import_profile: "z." + _veShareState.packed});
  if (document.getElementById("veShareIncludeToken").checked) {
    if (!_veShareState.token) {
      // מכשיר מצומד מקבל 403 - טוקן המחשב לא יוצא ממנו (22.10.2026); אז הקישור בלי token ולא "token=undefined"
      const resp = await fetch("/api/access_token");
      const data = resp.ok ? await resp.json() : {};
      if (typeof data.token === "string") _veShareState.token = data.token;
    }
    if (_veShareState.token) params.set("token", _veShareState.token);
  }
  const url = `${base}/?${params.toString()}`;
  document.getElementById("veShareUrl").value = url;
  const qr = document.getElementById("veShareQr");
  const error = document.getElementById("veShareQrError");
  if (url.length > 2800) { qr.hidden = true; error.textContent = "⚠️ הסגנון גדול מדי לקוד QR - העתק את הקישור במקום."; return; }
  error.textContent = "";
  qr.hidden = false;
  qr.src = "/api/qr?data=" + encodeURIComponent(url);
}

function copyVeShareUrl() {
  const input = document.getElementById("veShareUrl");
  input.select();
  navigator.clipboard.writeText(input.value).catch(() => { try { document.execCommand("copy"); } catch (e) {} });
}

// בפתיחת קישור-שיתוף (?import_profile=z.<...>) - מייבאים את הפרופיל אחרי אישור.
async function _veHandleImportProfileLink() {
  const params = new URLSearchParams(location.search);
  const packed = params.get("import_profile");
  if (!packed) return;
  params.delete("import_profile");
  history.replaceState(null, "", location.pathname + (params.toString() ? "?" + params : "") + location.hash);
  let payload;
  try { payload = JSON.parse(await _veInflate(_veBase64UrlDecode(packed.replace(/^z\./, "")))); }
  catch (e) { alert("קישור השיתוף פגום - לא ניתן לקרוא את הסגנון."); return; }
  const name = await vePrompt(`ייבוא סגנון משותף ("${payload.n}") - שם לשמירה:`, {value: payload.n});
  if (name === null || !name.trim()) return;
  let res = await fetch("/api/video_editor_profiles/import", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name, settings: payload.s})});
  if (res.status === 400 && await veConfirm(`סגנון בשם "${name}" כבר קיים - לדרוס אותו?`, {danger: true, okLabel: "דרוס"})) {
    res = await fetch("/api/video_editor_profiles/import", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name, settings: payload.s, overwrite: true})});
  }
  if (!res.ok) { alert("ייבוא הסגנון נכשל."); return; }
  await loadVideoEditorProfiles();
  const editor = (state.scripts || []).find(x => x.id.endsWith("video_editor.py"));
  if (editor) selectScript(editor.id);
  document.getElementById("vePreset").value = "profile:" + name.trim();
  applyVideoEditorPreset();
}

