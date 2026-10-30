// 08-ui-frame.js - "נפתחו לאחרונה" (23.10.2026): אזור רושם מה נפתח בו (remember) ואיך לפתוח אותו שוב (register: {icon, open(id)}).
// רק סוגים רשומים מוצגים. החלונית בסרגל העליון והמפריד הנגרר (uiSplitter) - ב-35-ui-frame.js, שנטען לפי דרישה
const uiRecent = {
  _openers: {},
  register(kind, opener) { this._openers[kind] = opener; },
  remember(kind, id, label) {
    if (!id) return;
    const items = [{kind, id, label: label || id, at: Date.now()}, ...this._read().filter((item) => !(item.kind === kind && item.id === id))];
    try { localStorage.setItem("uiRecent", JSON.stringify(items.slice(0, 12))); } catch (e) { /* לא קריטי */ }
  },
  list() { return this._read().filter((item) => this._openers[item.kind]).map((item) => ({...item, icon: this._openers[item.kind].icon})); },
  open(item) { this._openers[item.kind].open(item.id); this.remember(item.kind, item.id, item.label); },
  _read() {
    try {
      const items = JSON.parse(localStorage.getItem("uiRecent") || "[]");
      return Array.isArray(items) ? items.filter((item) => item && item.kind && item.id) : [];
    } catch (e) { return []; }
  },
};
