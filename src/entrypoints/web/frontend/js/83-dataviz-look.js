// ============================================================================
// גל 43: המראה בעורך הגרפים - גופן לפרק (מהגופנים המותקנים, GET /api/dataviz/fonts), ובדיקת ניגודיות
// של הטקסט, צבע ההדגשה, הפלטה והצבעים הקבועים מול הרקע (טקסט 4.5:1, הדגשה 3:1, עמודות 2:1) - מתעדכנת עם כל
// שינוי צבע, לפני ששומרים.
// ============================================================================

const DVZ_FONT_FALLBACK = ["Segoe UI", "Arial", "DejaVu Sans"];
let dvzFonts = null;

function _dvzLuminance(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return null;
  const channels = [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16) / 255)
    .map(c => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)));
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function dvzContrast(a, b) {
  const la = _dvzLuminance(a), lb = _dvzLuminance(b);
  if (la === null || lb === null) return null;
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

// הצבעים כרגע - הטיוטה מעל מה שבפרק
function _dvzCurrentLook() {
  const theme = dvzEd.data.theme;
  const pick = (key) => dvzEd.draft["theme_overrides." + key] || theme[key];
  return {bg: pick("bg"), ink: pick("ink"), accent: pick("accent"), palette: pick("categorical") || [],
          colors: "colors" in dvzEd.draft ? dvzEd.draft.colors : dvzEd.data.colors};
}

function dvzContrastIssues(look) {
  const issues = [];
  const check = (color, label, min) => {
    const ratio = dvzContrast(color, look.bg);
    if (ratio !== null && ratio < min) issues.push({label, color, ratio, min});
  };
  check(look.ink, "הטקסט", 4.5);
  check(look.accent, "צבע ההדגשה", 3);
  look.palette.forEach((color, i) => check(color, `צבע ${i + 1} בפלטה`, 2));   // עמודות ושטחים גדולים - 2:1 מספיק
  for (const [entity, color] of Object.entries(look.colors || {})) check(color, `הצבע של ${entity}`, 2);
  return issues;
}

function _dvzRenderContrast(box) {
  const issues = dvzContrastIssues(_dvzCurrentLook());
  if (!issues.length) {
    box.replaceChildren(_dvzEdEl("p", "dvz-check-ok", "✅ כל הצבעים קריאים מול הרקע."));
    return;
  }
  const list = _dvzEdEl("ul", "dvz-contrast-list");
  for (const issue of issues) {
    const li = _dvzEdEl("li", "");
    const dot = _dvzEdEl("span", "dvz-kit-dot");
    dot.style.background = issue.color;
    li.append(dot, document.createTextNode(`${issue.label}: ${issue.ratio.toFixed(1)}:1 (צריך לפחות ${issue.min}:1)`));
    list.append(li);
  }
  box.replaceChildren(_dvzEdEl("p", "dvz-finding is-warn", `⚠️ ${issues.length} צבעים חלשים מול הרקע - קשה לראות אותם בסרטון:`), list);
}

async function _dvzFontRow() {
  const row = _dvzEdEl("label", "dvz-color-row dvz-font-row", "🔤 גופן: ");
  const select = _dvzEdEl("select");
  select.setAttribute("aria-label", "גופן הפרק");
  const current = (dvzEd.draft["theme_overrides.fonts"] || dvzEd.data.theme.fonts || DVZ_FONT_FALLBACK)[0];
  select.append(new Option(`ברירת מחדל (${DVZ_FONT_FALLBACK[0]})`, ""));
  try {
    if (!dvzFonts) dvzFonts = (await _dvzJson(await fetch("/api/dataviz/fonts"))).fonts || [];
  } catch (e) {
    dvzFonts = [];
  }
  for (const name of dvzFonts) select.append(new Option(name, name));
  select.value = current === DVZ_FONT_FALLBACK[0] && !dvzEd.draft["theme_overrides.fonts"] ? "" : current;
  select.onchange = () => {
    if (select.value) _dvzStage("theme_overrides.fonts", [select.value, ...DVZ_FONT_FALLBACK.filter(f => f !== select.value)]);
    else _dvzStageUnset("theme_overrides.fonts");
  };
  row.append(select);
  uiBus.emit("dvz:font-row", row);
  return row;
}

// נקרא מ-_dvzColorsTab (44-dataviz-editor.js)
function _dvzLookExtras(box) {
  const fontSlot = _dvzEdEl("div", "");
  const contrast = _dvzEdEl("div", "dvz-contrast");
  contrast.setAttribute("aria-live", "polite");
  box.prepend(fontSlot);
  box.append(_dvzEdEl("h4", "", "בדיקת ניגודיות"), contrast);
  _dvzRenderContrast(contrast);
  box.addEventListener("input", () => uiDebounce("dvz:contrast", () => _dvzRenderContrast(contrast), 120));
  box.addEventListener("click", () => setTimeout(() => _dvzRenderContrast(contrast), 0));
  _dvzFontRow().then(row => fontSlot.replaceChildren(row));
}

// ============================================================================
// גל 51: המראה בעורך הגרפים - "מראות מוכנים" (מינימלי, חדשותי, בולט) שמוחלים כטיוטה, עיוורון צבעים (הדמיה על
// התצוגה החיה ובדיקה של הפלטה בשלושת הסוגים), ותמונה לכל ישות בלשונית הישויות (קובץ חדש בכל העלאה, תחת
// data/dataviz_overrides/<פרק>/images - תיקיית הפרק לא משתנה).
// ============================================================================

// --- מראות מוכנים ---
function _dvzApplyLook(look) {
  _dvzRecordUndo("");   // גל 53: אפשר לבטל מראה
  const saved = new Set((dvzEd.data.changes || []).map(c => c.path));
  for (const path of dvzEd.data.look_paths || []) {
    if (path in look.set) {
      dvzEd.draft[path] = look.set[path];
      dvzEd.unset.delete(path);
    } else {   // מה שמראה אחר שינה - חוזר לקובץ הפרק
      delete dvzEd.draft[path];
      if (saved.has(path)) dvzEd.unset.add(path);
    }
  }
  dvzEd.look = look.id;
  _dvzSyncDraftBar();
  _dvzRenderEditor();
  dvzPreviewSoon();
}

function _dvzLooksRow() {
  const row = _dvzEdEl("div", "dvz-looks");
  row.append(_dvzEdEl("strong", "", "✨ מראות מוכנים:"));
  for (const look of dvzEd.data.looks || []) {
    const btn = _dvzEdEl("button", "btn-sm" + (dvzEd.look === look.id ? " is-active" : ""), look.title);
    btn.type = "button";
    btn.title = look.about;
    btn.dataset.look = look.id;
    btn.onclick = () => _dvzApplyLook(look);
    row.append(btn);
  }
  row.append(_dvzEdEl("span", "hint", "המראה מוחל כטיוטה - \"שמור\" כדי שיישאר."));
  uiBus.emit("dvz:looks-row", row);
  return row;
}

// --- עיוורון צבעים: מטריצות Machado (2009) בעוצמה מלאה, על RGB לינארי ---
const DVZ_VISION = {
  protan: {label: "פרוטנופיה (אדום)", m: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]]},
  deutan: {label: "דויטרנופיה (ירוק)", m: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]]},
  tritan: {label: "טריטנופיה (כחול)", m: [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]]},
};
const DVZ_VISION_MIN_DELTA = 12;   // ΔE מתחת לזה - שני צבעים שקשה להבדיל ביניהם

function _dvzEnsureVisionFilters() {
  if (document.getElementById("dvzVisionDefs")) return;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.id = "dvzVisionDefs";
  svg.setAttribute("width", "0");
  svg.setAttribute("height", "0");
  svg.setAttribute("aria-hidden", "true");
  svg.style.position = "absolute";
  for (const [key, vision] of Object.entries(DVZ_VISION)) {
    const filter = document.createElementNS(ns, "filter");
    filter.id = "dvzVision-" + key;
    const matrix = document.createElementNS(ns, "feColorMatrix");   // פועל ב-linearRGB, כמו המטריצות
    matrix.setAttribute("type", "matrix");
    matrix.setAttribute("values", [...vision.m[0], 0, 0, ...vision.m[1], 0, 0, ...vision.m[2], 0, 0, 0, 0, 0, 1, 0].join(" "));
    filter.append(matrix);
    svg.append(filter);
  }
  document.body.append(svg);
}

function dvzSetVision(kind) {
  _dvzEnsureVisionFilters();
  dvzState.vision = kind || "";
  const img = document.getElementById("dvzPreviewImg");
  if (img) img.style.filter = kind ? `url(#dvzVision-${kind})` : "";
}

function _dvzLinear(channel) {
  const c = channel / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function _dvzLab([r, g, b]) {
  const f = (t) => t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116;
  const x = f((0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047);
  const y = f(0.2126 * r + 0.7152 * g + 0.0722 * b);
  const z = f((0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883);
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)];
}

function _dvzSeen(hex, matrix) {
  const rgb = [1, 3, 5].map(i => _dvzLinear(parseInt(hex.slice(i, i + 2), 16)));
  return matrix.map(row => Math.min(1, Math.max(0, row[0] * rgb[0] + row[1] * rgb[1] + row[2] * rgb[2])));
}

// זוגות צבעים שנראים כמעט אותו דבר בסוג מסוים של עיוורון צבעים
function dvzVisionIssues(colors) {
  const valid = colors.filter(c => /^#[0-9a-f]{6}$/i.test(c));
  const issues = [];
  for (const [kind, vision] of Object.entries(DVZ_VISION)) {
    const labs = valid.map(c => _dvzLab(_dvzSeen(c, vision.m)));
    for (let i = 0; i < valid.length; i++) {
      for (let j = i + 1; j < valid.length; j++) {
        const delta = Math.hypot(labs[i][0] - labs[j][0], labs[i][1] - labs[j][1], labs[i][2] - labs[j][2]);
        if (delta < DVZ_VISION_MIN_DELTA) issues.push({kind, a: valid[i], b: valid[j], delta});
      }
    }
  }
  return issues;
}

function _dvzSwatch(color) {
  const swatch = _dvzEdEl("span", "dvz-swatch");
  swatch.style.background = color;
  swatch.title = color;
  return swatch;
}

function _dvzVisionBox() {
  const box = _dvzEdEl("div", "dvz-vision");
  box.append(_dvzEdEl("h4", "", "👁 עיוורון צבעים"));
  const label = _dvzEdEl("label", "", "הדמיה בתצוגה החיה: ");
  const select = _dvzEdEl("select");
  select.id = "dvzVisionSelect";
  select.appendChild(new Option("בלי הדמיה", ""));
  for (const [key, vision] of Object.entries(DVZ_VISION)) select.appendChild(new Option(vision.label, key));
  select.value = dvzState.vision || "";
  select.onchange = () => dvzSetVision(select.value);
  label.append(select);
  box.append(label);
  const palette = (dvzEd.draft["theme_overrides.categorical"] || dvzEd.data.theme.categorical || []).slice(0, 10);
  const fixed = Object.values("colors" in dvzEd.draft ? dvzEd.draft.colors : dvzEd.data.colors || {});
  const issues = dvzVisionIssues([...new Set([...palette, ...fixed].map(c => String(c).toLowerCase()))]);
  if (!issues.length) {
    box.append(_dvzEdEl("p", "dvz-vision-ok", "✅ כל צבעי הפלטה נבדלים גם בשלושת הסוגים של עיוורון צבעים."));
    return box;
  }
  const list = _dvzEdEl("ul", "dvz-vision-issues");
  for (const issue of issues.slice(0, 8)) {
    const li = _dvzEdEl("li");
    li.append(_dvzSwatch(issue.a), _dvzSwatch(issue.b), _dvzEdEl("span", "", ` ${DVZ_VISION[issue.kind].label} - קשה להבדיל`));
    list.append(li);
  }
  box.append(_dvzEdEl("p", "hint", `⚠️ ${issues.length} זוגות צבעים שכמעט לא נבדלים - כדאי לשנות אחד מכל זוג בפלטה:`), list);
  return box;
}

// נקרא מסוף לשונית הצבעים (44-dataviz-editor.js)
function _dvzLookTools(box) {
  box.prepend(_dvzLooksRow());
  box.append(_dvzVisionBox());
}

// --- תמונה לכל ישות ---
let dvzImages = {episode: "", list: null, loading: false};

function _dvzImageKey(name) {
  return String(name).replace(/[\\/:*?"<>|]/g, "-").trim();
}

async function _dvzLoadImages() {
  const episode = dvzState.selected;
  try {
    const resp = await fetch("/api/dataviz/episodes/images?episode=" + encodeURIComponent(episode));
    const data = await _dvzJson(resp);
    dvzImages = {episode, list: resp.ok ? data.images : {}, loading: false};
  } catch (e) {
    dvzImages = {episode, list: {}, loading: false};
  }
}

async function _dvzImagesChanged() {
  await _dvzLoadImages();
  if (dvzEd.tab === "entities") _dvzRenderEditor();
  dvzPreviewSoon();
}

async function _dvzUploadImage(name, file) {
  const status = document.getElementById("dvzEditorStatus");
  try {
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    const resp = await fetch("/api/dataviz/episodes/images", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({episode: dvzState.selected, entity: name, ext, data_base64: await _dvzBase64(file)})});
    const data = await _dvzJson(resp);
    if (!resp.ok) throw new Error(data.error || "ההעלאה נכשלה");
    status.textContent = `✅ התמונה של ${name} נשמרה`;
    await _dvzImagesChanged();
  } catch (e) {
    status.textContent = "שגיאה: " + e.message;
  }
}

async function _dvzTrashImage(file) {
  const resp = await fetch("/api/dataviz/episodes/images/trash", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({episode: dvzState.selected, name: file})});
  if (resp.ok) await _dvzImagesChanged();
}

// נקרא מלשונית הישויות (44-dataviz-editor.js) - תא לכל ישות
function _dvzEntityImageCell(name) {
  const cell = _dvzEdEl("span", "dvz-entity-image");
  if (dvzImages.episode !== dvzState.selected || !dvzImages.list) {
    if (!dvzImages.loading) {
      dvzImages.loading = true;
      _dvzLoadImages().then(() => { if (dvzEd.tab === "entities") _dvzRenderEditor(); });
    }
    return cell;
  }
  const file = dvzImages.list[_dvzImageKey(name)];
  if (file) {
    const img = _dvzEdEl("img");
    img.alt = name;
    img.src = "/api/dataviz/episodes/image?" + new URLSearchParams({episode: dvzState.selected, name: file});
    const trash = _dvzEdEl("button", "btn-xs", "🗑");
    trash.type = "button";
    trash.title = "התמונה עוברת לסל המיחזור";
    trash.setAttribute("aria-label", `הסר את התמונה של ${name}`);
    trash.onclick = () => _dvzTrashImage(file);
    cell.append(img, trash);
  }
  const pick = _dvzEdEl("label", "btn-xs dvz-image-pick", file ? "🔄" : "🖼");
  pick.title = file ? "החלף תמונה" : "הוסף תמונה (png / jpg / webp)";
  const input = _dvzEdEl("input");
  input.type = "file";
  input.accept = "image/png,image/jpeg,image/webp";
  input.hidden = true;
  input.setAttribute("aria-label", `תמונה ל-${name}`);
  input.onchange = () => { if (input.files[0]) _dvzUploadImage(name, input.files[0]); };
  pick.append(input);
  cell.append(pick);
  return cell;
}
