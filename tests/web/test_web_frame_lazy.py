# tests/web/test_web_frame_lazy.py
#
# 23.10.2026: רכיבי המסגרת המשותפים - בדף הראשי רק uiRecent (כל אזור רושם אליו כשהדף נטען) והכפתור; המפריד הנגרר
# (uiSplitter) וחלונית "נפתחו לאחרונה" נטענים לפי דרישה (LAZY_JS/LAZY_CSS["frame"]).
from entrypoints.web import frontend_assembly as fa


def test_the_splitter_and_the_recent_panel_load_on_demand():
    main_js, lazy = fa.bundle("js"), fa.lazy_bundle("frame")
    for name in ("uiSplitter", "toggleRecentPanel"):
        assert f"function {name}(" in lazy and f"function {name}(" not in main_js, name
    assert "const uiRecent = {" in main_js and "const uiRecent = {" not in lazy
    assert main_js.count('uiLoadLazy("frame")') == 2   # הסטודיו (המפרידים) והכפתור בסרגל העליון
    assert ".recent-item" in lazy and ".recent-item" not in fa.bundle("css")
    assert 'id="recentBtn"' in fa.assemble_page()


def test_the_studio_resizers_use_the_shared_splitter():
    studio = fa.read_part("js/66-ui-studio.js")
    assert "uiSplitter(resizer" in studio and "pointerdown" not in studio.split("function _veSetupResizers")[1].split("\n}\n")[0]
