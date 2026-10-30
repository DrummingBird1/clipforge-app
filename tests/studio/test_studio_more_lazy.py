# tests/studio/test_studio_more_lazy.py
#
# 24.10.2026: התוספות לסטודיו מסיור השימושיות נטענות לפי דרישה (LAZY_JS["studio_more"], 89-studio-more.js) כשהסטודיו נפתח
# (setVeFocus), ולא בדף הראשי - שם נשארו כ-1,000 בתים דחוסים מתחת לתקרה.
from entrypoints.web import frontend_assembly as fa


def test_the_studio_extras_are_not_in_the_main_page_and_load_when_the_studio_opens():
    main_js, lazy = fa.bundle("js"), fa.lazy_bundle("studio_more")
    for name in ("_veRenderBrowseExtras", "_veBrowseIfExists", "_veParentPath"):
        assert f"function {name}(" in lazy and f"function {name}(" not in main_js, name
    studio = fa.read_part("js/62-editor-studio.js")
    assert 'uiLoadLazy("studio_more")' in studio.split("function setVeFocus")[1].split("\n}\n")[0]
    assert main_js.count('uiLoadLazy("studio_more")') == 1


def test_the_studio_extras_bring_their_own_css():
    # 24.10.2026, מנה 6: ציר הזמן הצמוד לתחתית - העיצוב שלו ב-LAZY_CSS["studio_more"], לא ב-CSS הראשי
    lazy = fa.lazy_bundle("studio_more")
    assert ".ve-tl-docked" in lazy and ".ve-tl-docked" not in fa.bundle("css")
