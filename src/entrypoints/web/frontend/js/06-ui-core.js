// ============================================================================
// גל 16-17 - ליבת הממשק: אייקונים, הודעות קופצות ועזרי תצוגה.
//
// אייקונים: כל אימוג'י ממופה (UI_EMOJI_ICONS, נוצר מ-dev/build_ui_icons.py)
// בטקסט של הדף נעטף ב-<span class="ei" data-i="..."> - האימוג'י נשאר בתוך ה-span
// (textContent/innerText/חיפוש/העתקה/טסטים לא משתנים), מוסתר, ובמקומו מצויר
// אייקון SVG חד-צבעי (CSS mask, 02-icons.css) בצבע הטקסט. MutationObserver מטפל
// גם בכל טקסט ש-JS מוסיף אחר כך, כך שאין צורך לגעת באף מקום שכותב textContent.
// ============================================================================

const _UI_ICON_SKIP = "script, style, textarea, option, select, pre, code, .console, .ei, [data-no-icons], [contenteditable='true']";
const _UI_ICON_KEYS = Object.keys(UI_EMOJI_ICONS).sort((a, b) => b.length - a.length);
const _UI_ICON_RE = new RegExp("(" + _UI_ICON_KEYS.map(k => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")️?", "g");
const _UI_ICON_TEST = new RegExp(_UI_ICON_RE.source);

function uiIconSpan(emoji, name, tone) {
  const span = document.createElement("span");
  span.className = "ei";
  span.dataset.i = name;
  if (tone) span.dataset.tone = tone;
  span.setAttribute("aria-hidden", "true");
  span.textContent = emoji;
  return span;
}

// אייקון לקוד חדש (בלי אימוג'י מקורי): <span class="ei" data-i="play">
function uiIcon(name, tone) {
  const span = uiIconSpan("", name, tone);
  return span;
}

function _uiIconizeTextNode(node) {
  const text = node.nodeValue;
  if (!text || !_UI_ICON_TEST.test(text)) return;
  const parent = node.parentElement;
  if (!parent || parent.closest(_UI_ICON_SKIP)) return;
  const frag = document.createDocumentFragment();
  let last = 0;
  _UI_ICON_RE.lastIndex = 0;
  let match;
  while ((match = _UI_ICON_RE.exec(text))) {
    if (match.index > last) frag.appendChild(document.createTextNode(text.slice(last, match.index)));
    const entry = UI_EMOJI_ICONS[match[1]];
    frag.appendChild(uiIconSpan(match[0], entry[0], entry[1]));
    last = match.index + match[0].length;
  }
  if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
  parent.replaceChild(frag, node);
}

function uiIconize(root) {
  if (!root) return;
  if (root.nodeType === Node.TEXT_NODE) { _uiIconizeTextNode(root); return; }
  if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) return;
  if (root.nodeType === Node.ELEMENT_NODE && root.closest(_UI_ICON_SKIP)) return;
  if (!_UI_ICON_TEST.test(root.textContent || "")) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => _UI_ICON_TEST.test(n.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT,
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(_uiIconizeTextNode);
}

const _uiIconObserver = new MutationObserver((records) => {
  for (const record of records) {
    if (record.type === "characterData") { _uiIconizeTextNode(record.target); continue; }
    record.addedNodes.forEach(uiIconize);
  }
});

function uiStartIcons() {
  uiIconize(document.body);
  _uiIconObserver.observe(document.body, {childList: true, subtree: true, characterData: true});
}

// --- חלונות מעל <dialog> מודאלי ---
// <dialog> שנפתח ב-showModal (בעורך הגרפים) נמצא ב-top layer - מעל כל z-index - ושאר הדף inert: חלון, לוח פקודות או
// הודעה קופצת שנפתחו בזמן שהוא פתוח הוסתרו מאחוריו ולא קיבלו לחיצות. uiOverModal מעביר את האלמנט לתוך ה-dialog
// המודאלי העליון ומחזיר פונקציה שמחזירה אותו למקומו; גם כשה-dialog נסגר קודם הוא חוזר, ונשאר גלוי (20.10.2026 -
// veConfirm/vePrompt, 22.10.2026 - כל חלון .modal-bg ב-67-ui-screens.js וההודעות הקופצות).
function uiTopModalDialog() {
  const modals = [...document.querySelectorAll("dialog[open]")].filter(d => d.matches(":modal"));
  return modals[modals.length - 1] || null;
}

function uiOverModal(el) {
  const host = uiTopModalDialog();
  if (!host || host.contains(el)) return () => {};
  const parent = el.parentNode, next = el.nextSibling;
  const restore = () => {
    host.removeEventListener("close", restore);
    if (el.parentNode === host) parent.insertBefore(el, next && next.parentNode === parent ? next : null);
  };
  host.appendChild(el);
  host.addEventListener("close", restore);
  return restore;
}

// --- הודעות קופצות (toast) ---
function uiToast(message, tone = "", {timeout} = {}) {
  let host = document.getElementById("toastHost");
  if (!host) {
    host = document.createElement("div");
    host.id = "toastHost";
    host.className = "toast-host";
    host.setAttribute("role", "status");
    host.setAttribute("aria-live", "polite");
    document.body.appendChild(host);
  }
  uiOverModal(host);   // חוזר ל-body כשה-dialog נסגר
  const toast = document.createElement("div");
  toast.className = "toast";
  if (tone) toast.dataset.tone = tone;
  const icon = {ok: "✅", bad: "❌", warn: "⚠️"}[tone];
  const msg = document.createElement("span");
  msg.className = "toast-msg";
  msg.textContent = (icon && !String(message).startsWith(icon) ? icon + " " : "") + message;
  const close = document.createElement("button");
  close.type = "button";
  close.className = "toast-close";
  close.setAttribute("aria-label", "סגור");
  close.textContent = "✕";
  const dismiss = () => {
    toast.classList.add("leaving");
    setTimeout(() => toast.remove(), 260);
  };
  close.onclick = dismiss;
  toast.append(msg, close);
  host.appendChild(toast);
  setTimeout(dismiss, timeout || (tone === "bad" ? 9000 : 4500));
  return toast;
}

// --- עזרי תצוגה ---
function uiFormatDuration(seconds) {
  if (seconds == null || !isFinite(seconds)) return "";
  seconds = Math.max(0, Math.round(seconds));
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}

function uiRelativeTime(value) {
  const date = value instanceof Date ? value : new Date(String(value).replace(" ", "T"));
  if (isNaN(date)) return "";
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 45) return "עכשיו";
  const minutes = Math.round(diff / 60), hours = Math.round(diff / 3600), days = Math.round(diff / 86400);
  // גל 23: "לפני שעה"/"אתמול" במקום "לפני 1 שע׳"/"לפני 1 ימים"
  if (diff < 3600) return minutes <= 1 ? "לפני דקה" : `לפני ${minutes} דק׳`;
  if (diff < 86400) return hours === 1 ? "לפני שעה" : (hours === 2 ? "לפני שעתיים" : `לפני ${hours} שע׳`);
  if (diff < 7 * 86400) return days === 1 ? "אתמול" : (days === 2 ? "לפני יומיים" : `לפני ${days} ימים`);
  return date.toLocaleDateString("he-IL", {day: "numeric", month: "numeric"});
}

uiStartIcons();

// גל 38: מסך שהקוד שלו נטען רק כשפותחים אותו (frontend_assembly.LAZY_JS). פעם אחת לכל מסך;
// אם הקוד כבר בדף (הדף המלא של הטסטים) - בלי טעינה.
// סבב ייצוב: קודם ה-HTML של המסך ("<שם>:html", frontend_assembly lazy-html) ורק אחריו ה-JS - שימצא את האלמנטים.
const _uiLazyPromises = {};
function _uiLoadScript(url) {
  return new Promise((resolve, reject) => {
    if (!url) { resolve(); return; }
    const script = document.createElement("script");
    script.src = url;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("טעינת המסך נכשלה"));
    document.head.appendChild(script);
  });
}

function uiLoadLazy(name) {
  if (window.__uiLazyLoaded && window.__uiLazyLoaded[name]) return Promise.resolve();
  if (!_uiLazyPromises[name]) {
    const urls = typeof UI_LAZY_BUNDLES !== "undefined" ? UI_LAZY_BUNDLES : {};
    _uiLazyPromises[name] = _uiLoadScript(urls[name + ":html"]).then(() => _uiLoadScript(urls[name]))
      .catch((e) => { delete _uiLazyPromises[name]; throw e; });
  }
  return _uiLazyPromises[name];
}
