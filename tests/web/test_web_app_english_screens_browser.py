# tests/web/test_web_app_english_screens_browser.py
#
# 30.10.2026 (לפני ההפצה הציבורית, ClipForge מתחיל באנגלית): במסכים הראשיים בממשק האנגלי לא נשאר טקסט עברי גלוי - לא
# בטקסט, לא ב-placeholder, ב-title או ב-aria-label. מה שנמצא בסיור: כותרות הקטגוריות ברשימת הסקריפטים ("פייפליין וידאו (9)"),
# ה-aria-label של הכוכב והארכיון ("הוסף למועדפים: <שם>") ותיאור אחד של סקריפט. test_web_i18n_dynamic בודק את המחרוזות שבקוד;
# כאן - מה שבאמת מוצג אחרי ההרכבה בזמן ריצה.
import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

HEBREW_SHOWN = r"""() => {
  const he = /[֐-׿]/, out = new Set();
  const shown = (el) => el && el.checkVisibility();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) if (he.test(n.nodeValue) && shown(n.parentElement)) out.add(n.nodeValue.trim());
  for (const el of document.querySelectorAll('[placeholder], [title], [aria-label]')) {
    if (!shown(el)) continue;
    for (const attr of ['placeholder', 'title', 'aria-label']) if (he.test(el.getAttribute(attr) || '')) out.add(`${attr}: ${el.getAttribute(attr)}`);
  }
  return [...out].slice(0, 20);
}"""


def _english(page):
    page.evaluate("() => setUiLanguage('en')")
    page.wait_for_function("() => _uiLang === 'en' && document.documentElement.dir === 'ltr'")


def test_the_main_screens_show_no_hebrew_in_english(editor_page):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); localStorage.removeItem('clipforgeCollapsedCategories'); switchTab('scripts'); renderScripts(); }")
    _english(page)
    page.wait_for_selector("#scriptList .category-toggle")
    assert page.evaluate(HEBREW_SHOWN) == []                                              # קודם: "פייפליין וידאו (9)" ועוד
    for tab in ("outputs", "globalsettings"):
        page.evaluate("(t) => switchTab(t)", tab)
        page.wait_for_load_state("networkidle")
        assert page.evaluate(HEBREW_SHOWN) == [], tab
