// ============================================================================
// גל 28: מפקח שאפשר להתמצא בו - בסטודיו ההגדרות בלשוניות (האזורים מהסכמה), כל
// תת-אזור מתקפל לשורת תקציר ("צבע: רוויה 1.5 · LUT film.cube"), שדות תלויים
// מהסכמה (utils/editor_model.py DEPENDS_ON), עמודת תוויות אחידה, ושדות זמן עם
// חיצים, גרירה ו"⌖ מהנגן". פלט כפול ישן מומר ליעדים.
// ============================================================================

// --- תתי-אזורים מתקפלים ---
const _veSubcatKey = (sub) => `${(sub.closest("details.ve-category") || {dataset: {}}).dataset.cat}/${sub.dataset.subcat}`;
const _veSubcatCollapsible = (sub) => !!sub.dataset.subcat && !sub.classList.contains("ve-layer-card") && sub.dataset.subcat !== "timed-layers";

function _veSubcatFields(sub) {
  const fields = [];
  for (const [key, meta] of Object.entries(VE_FAVORITABLE_FIELDS)) {
    const el = document.getElementById(meta.id);
    if (el && sub.contains(el) && !el.closest(".ve-favorite-row")) fields.push([key, meta, el]);
  }
  return fields;
}

function _veShortValue(el) {
  if (el.type === "checkbox") return el.checked ? "✓" : "✗";
  if (el.tagName === "SELECT") return el.selectedIndex >= 0 ? el.options[el.selectedIndex].textContent.trim() : el.value;
  if (el.type === "range") {
    const number = el.parentElement.querySelector(`.ve-range-number[data-for="${el.id}"]`);
    return number ? number.value + (el.dataset.veValueFormat === "percent" ? "%" : "") : el.value;
  }
  const text = String(el.value || "").split(/[\\/]/).pop();
  return text.length > 18 ? text.slice(0, 17) + "…" : text;
}

function _veSubcatSummary(sub) {
  const changed = _veSubcatFields(sub).filter(([, , el]) => _veFieldChanged(el));
  if (!changed.length) return {changed: 0, text: "ברירת מחדל"};
  const parts = changed.slice(0, 3).map(([, meta, el]) => `${meta.label} ${_veShortValue(el)}`);
  return {changed: changed.length, text: parts.join(" · ") + (changed.length > 3 ? ` · +${changed.length - 3}` : "")};
}

function _veSetSubcatOpen(sub, open, remember) {
  sub.classList.toggle("ve-subcat-collapsed", !open);
  const title = sub.querySelector(":scope > .ve-subcat-title");
  if (title) title.setAttribute("aria-expanded", String(open));
  if (remember) {
    const saved = _veLoadPref("veSubcatOpen", {});
    saved[_veSubcatKey(sub)] = open;
    _veSavePref("veSubcatOpen", saved);
  }
}

function _veSubcatDefaultOpen(sub) {
  if (_veLoadPref("veCollapseSubcats", true) === false) return true;
  const saved = _veLoadPref("veSubcatOpen", {})[_veSubcatKey(sub)];
  if (typeof saved === "boolean") return saved;
  return sub.hasAttribute("data-primary") || _veSubcatFields(sub).some(([, , el]) => _veFieldChanged(el));
}

function _veSetupSubcats() {
  for (const sub of document.querySelectorAll("#veCategories .ve-subcat")) {
    if (!_veSubcatCollapsible(sub)) continue;
    const title = sub.querySelector(":scope > .ve-subcat-title");
    if (!title || title.classList.contains("ve-subcat-toggle")) continue;
    title.classList.add("ve-subcat-toggle");
    title.setAttribute("role", "button");
    title.tabIndex = 0;
    const summary = document.createElement("span");
    summary.className = "ve-subcat-summary";
    title.appendChild(summary);
    const toggle = (e) => {
      if (e.target.closest("button, input, select, a")) return;
      _veSetSubcatOpen(sub, sub.classList.contains("ve-subcat-collapsed"), true);
    };
    title.addEventListener("click", toggle);
    title.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(e); }
    });
    _veSetSubcatOpen(sub, _veSubcatDefaultOpen(sub));
  }
  _veRefreshSubcatSummaries();
}

function _veRefreshSubcatSummaries() {
  for (const sub of document.querySelectorAll("#veCategories .ve-subcat > .ve-subcat-toggle")) {
    const box = sub.closest(".ve-subcat");
    const summary = sub.querySelector(".ve-subcat-summary");
    const {changed, text} = _veSubcatSummary(box);
    summary.textContent = text;
    summary.classList.toggle("ve-empty", !changed);
    box.classList.toggle("ve-subcat-changed", changed > 0);
  }
}

function setVeCollapseSubcats(on) {
  _veSavePref("veCollapseSubcats", !!on);
  _veSavePref("veSubcatOpen", {});
  for (const sub of document.querySelectorAll("#veCategories .ve-subcat")) {
    if (_veSubcatCollapsible(sub) && sub.querySelector(":scope > .ve-subcat-toggle")) _veSetSubcatOpen(sub, _veSubcatDefaultOpen(sub));
  }
}

// --- שדות תלויים מהסכמה ---
const _veSchemaFieldId = (key) => (VE_GENERIC_FIELDS[key] && VE_GENERIC_FIELDS[key].id) || ("ve" + key.split("_").map(p => p[0].toUpperCase() + p.slice(1)).join(""));

function _veDependsCheck(parentId, when) {
  return () => {
    const parent = document.getElementById(parentId);
    if (!parent) return true;
    if (when === "true") return parent.checked;
    if (when === "set") return !!String(parent.value).trim();
    if (when === ">1") return (parseInt(parent.value, 10) || 0) > 1;
    if (when.startsWith("!")) return parent.value !== when.slice(1) && !!String(parent.value).trim();
    return true;
  };
}

function _veApplySchemaDependents(schema) {
  for (const [field, rule] of Object.entries((schema && schema.depends_on) || {})) {
    const id = _veSchemaFieldId(field), parentId = _veSchemaFieldId(rule.on);
    if (!document.getElementById(id) || !document.getElementById(parentId)) continue;
    VE_DEPENDENT_FIELDS[id] = _veDependsCheck(parentId, rule.when);
    VE_DEPENDENT_PARENTS[id] = parentId;
  }
  _veUpdateDependentRows();
}

// --- שדות זמן: חיצים (עשירית / Shift שנייה), ו"⌖" שלוקח את הזמן מהנגן ---
function _vePlayerSourceTime() {
  if (_veInLiveMode()) return _veEl("veLiveVideo").currentTime;
  const frame = _veParseTime(_veEl("vePreviewTime").value);
  return Number.isFinite(frame) ? frame : NaN;
}

function _veStepTime(input, delta) {
  const current = _veParseTime(input.value);
  const next = Math.max(0, Math.round(((Number.isFinite(current) ? current : 0) + delta) * 10) / 10);
  _veSetFieldValue(input, input.value.includes(":") || next >= 60 ? _veFormatTime(next) : String(next));
}

function _veSetupTimeFields() {
  for (const input of document.querySelectorAll("#veCategories input.ve-time")) {
    if (input.dataset.veTimeReady) continue;
    input.dataset.veTimeReady = "1";
    input.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
      e.preventDefault();
      _veStepTime(input, (e.key === "ArrowUp" ? 1 : -1) * (e.shiftKey ? 1 : 0.1));
    });
    input.addEventListener("blur", () => {
      const seconds = _veParseTime(input.value);
      if (Number.isFinite(seconds) && seconds >= 60 && !input.value.includes(":")) _veSetFieldValue(input, _veFormatTime(seconds));
    });
    const now = document.createElement("button");
    now.type = "button";
    now.className = "ve-time-now";
    now.textContent = "⌖";
    now.title = "קח את הזמן הנוכחי מהנגן";
    now.setAttribute("aria-label", "קח את הזמן מהנגן");
    now.onclick = () => {
      const t = _vePlayerSourceTime();
      if (!Number.isFinite(t)) { uiToast("פתח קודם את הנגן (חי או פריים)", "warn"); return; }
      _veSetFieldValue(input, t >= 60 ? _veFormatTime(t) : String(Math.round(t * 10) / 10));
    };
    const hint = input.parentElement.querySelector(`.ve-time-hint[data-for="${input.id}"]`);
    (hint || input).after(now);
  }
}

// --- פלט כפול ישן -> יעדים ---
function convertVeDualToTargets() {
  const current = _veTargets();
  _veSetTargets([...new Set([...current, "youtube", "shorts"])]);
  _veSetComposite("format", "16:9");
  uiToast("🎯 הפלט הכפול הומר ליעדים YouTube + YouTube Shorts", "ok");
}

// --- פקדים אחידים: יעדים פעילים מכבים את בורר הפורמט (לא רק מעמעמים) ---
function _veSyncFormatLock() {
  const locked = _veTargets().length > 0;
  for (const btn of document.querySelectorAll("#veFormatChips button")) btn.disabled = locked;
}

function _veInitWave28() {
  _veSetupSubcats();
  _veSetupTimeFields();
  _veApplyLayout();
  uiBus.on("ve:derived-refresh", () => { _veRefreshSubcatSummaries(); _veRenderCategoryTabs(); _veSyncFormatLock(); });
  uiBus.on("ve:fields-applied", () => {
    for (const sub of document.querySelectorAll("#veCategories .ve-subcat.ve-subcat-collapsed")) {
      if (_veSubcatFields(sub).some(([, , el]) => _veFieldChanged(el))) _veSetSubcatOpen(sub, true);
    }
  });
  _veLoadSchema().then((schema) => {
    _veApplySchemaDependents(schema);
  });
}
