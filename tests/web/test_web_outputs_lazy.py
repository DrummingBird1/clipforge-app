# tests/web/test_web_outputs_lazy.py
#
# 23.10.2026: מסך "תוצרים" נטען רק כשפותחים אותו - ה-JS וה-CSS ב-LAZY_JS/LAZY_CSS["outputs"], וה-HTML באזור lazy-html.
# בדף הראשי נשארים רק כפתור הניווט ושורת ה-switchTab.
from entrypoints.web import frontend_assembly as fa


def test_the_outputs_screen_is_not_in_the_main_page():
    main_js, lazy = fa.bundle("js"), fa.lazy_bundle("outputs")
    for name in ("loadOutputs", "renderOutputs", "selectOutput", "openOutputInStudio", "publishOutput"):
        assert f"function {name}(" in lazy and f"function {name}(" not in main_js, name
    assert ".output-card" in lazy and ".output-card" not in fa.bundle("css")
    assert 'uiLoadLazy("outputs")' in main_js


def test_its_html_arrives_with_the_screen():
    page = fa.assemble_page()
    html = "".join(fa.lazy_html_fragments("outputs"))
    for element in ('id="outputsList"', 'id="outputsFilterTool"', 'id="outputsFilterDate"', 'id="outputsStudioBtn"', 'id="outputsTiktokBtn"'):
        assert element in html and element not in page, element
    assert 'data-tab="outputs"' in page and 'data-lazy-html="outputs"' in page
