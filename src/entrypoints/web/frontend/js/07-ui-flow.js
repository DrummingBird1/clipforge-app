// ============================================================================
// גל 22 - יציבות ובטיחות: תשתית משותפת שכל שאר הקבצים נשענים עליה.
//
//  - uiBus: אירועים במקום עטיפת פונקציות. קובץ שרוצה "לעשות משהו אחרי X" נרשם
//    ל-uiBus.on("x", ...) - במקום להחליף את X בפונקציה שקוראת למקור ואז לעצמה.
//    עטיפות כאלה תלויות בסדר הטעינה, וכל מאזין DOM שהחזיק הפניה לפונקציה
//    המקורית דילג בשקט על כל מה שנוסף מעליה.
//  - uiLatest: "רק הבקשה האחרונה קובעת" - בקשה חדשה עם אותו מפתח מבטלת את
//    הקודמת, ותשובה ישנה שחוזרת באיחור לא דורסת חדשה.
//  - uiEscape: כל נתון שנכנס ל-innerHTML עובר דרכה (שמות קבצים, שגיאות מהשרת).
//  - veFlow: הבעלים היחיד של זרימת תיקייה ← פרויקט ← פרופיל ← תור.
// ============================================================================

// --- אירועים ---
const uiBus = {
  _handlers: new Map(),
  on(event, handler) {
    if (!this._handlers.has(event)) this._handlers.set(event, []);
    this._handlers.get(event).push(handler);
    return () => this.off(event, handler);
  },
  off(event, handler) {
    const list = this._handlers.get(event) || [];
    const index = list.indexOf(handler);
    if (index >= 0) list.splice(index, 1);
  },
  emit(event, detail) {
    // מאזין שנכשל לא עוצר את האחרים (עטיפה שנכשלה הייתה מפילה את כל השרשרת)
    for (const handler of [...(this._handlers.get(event) || [])]) {
      try { handler(detail); } catch (e) { console.error(`uiBus "${event}":`, e); }
    }
  },
};

// --- רק הבקשה האחרונה קובעת ---
const _uiLatestControllers = new Map();

function uiLatest(key) {
  const previous = _uiLatestControllers.get(key);
  if (previous) previous.abort();
  const controller = new AbortController();
  _uiLatestControllers.set(key, controller);
  return {
    signal: controller.signal,
    // false אחרי שבקשה חדשה יותר עם אותו מפתח יצאה - לא מציירים את התוצאה
    current: () => _uiLatestControllers.get(key) === controller && !controller.signal.aborted,
  };
}

function uiIsAbort(error) {
  return !!error && error.name === "AbortError";
}

// --- debounce עם מעקב (גל 23) ---
// רענון UI שמחכה לסוף ההקלדה. uiPendingWork() אומר כמה עוד ממתינים - טסטים מחכים ל-0
// במקום לזמן קבוע (runner איטי ב-CI הוא הסיבה שטסטים נפלו על "חכה 250ms").
const _uiDebounceTimers = new Map();

function uiDebounce(key, fn, ms) {
  clearTimeout(_uiDebounceTimers.get(key));
  _uiDebounceTimers.set(key, setTimeout(() => {
    _uiDebounceTimers.delete(key);
    fn();
  }, ms));
}

function uiPendingWork() {
  return _uiDebounceTimers.size;
}

// --- escape לכל נתון שנכנס ל-HTML ---
const _UI_HTML_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};

function uiEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => _UI_HTML_ESCAPES[ch]);
}

// --- זרימת העורך: תיקייה ← פרויקט ← פרופיל ← תור ---
// פרופיל שהמשתמש בחר (עם תור שמור) גובר על התור של פרויקט התיקייה שנטען ברקע,
// בכל סדר שהתשובות חוזרות, ורק רענון התור האחרון מחיל את רשימת הקבצים שלו.
const veFlow = {
  folderEpoch: 0,
  _queueSeq: 0,
  _pendingRestore: null,   // {files, source: "profile" | "project"}
  _restoredSource: null,   // מקור התור שכבר הוחל בתיקייה הנוכחית

  folderChanged() {
    this.folderEpoch++;
    this._pendingRestore = null;
    this._restoredSource = null;
  },

  requestQueueRestore(files, source) {
    if (source === "project" && this.profileQueueChosen()) return false;
    this._pendingRestore = {files, source};
    return true;
  },

  profileQueueChosen() {
    return (this._pendingRestore && this._pendingRestore.source === "profile") || this._restoredSource === "profile";
  },

  takeQueueRestore() {
    const restore = this._pendingRestore;
    this._pendingRestore = null;
    if (restore) this._restoredSource = restore.source;
    return restore;
  },

  hasPendingRestore() {
    return !!this._pendingRestore;
  },

  beginQueueRefresh() {
    return ++this._queueSeq;
  },

  isLatestQueueRefresh(seq) {
    return seq === this._queueSeq;
  },

  queueMark() {
    return this._queueSeq;
  },

  // המשתמש סידר/סימן את התור (או שוחזר תור מפרופיל) מאז הנקודה הזו
  queueChosenSince(mark, dirty) {
    return this.profileQueueChosen() || (this._queueSeq !== mark && !!dirty);
  },
};

// --- Ctrl+K: ספקי פעולות נוספות (במקום עטיפות של _vePaletteEntries) ---
// כל ספק מחזיר רשימת {section, label, run}; נוספות לפני רשימת הסקריפטים, לפי סדר הרישום.
const uiPaletteProviders = [];
