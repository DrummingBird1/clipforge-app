# tests/web/test_web_lazy_html_browser.py
#
# סבב ייצוב בדפדפן: ה-HTML של עורך הגרפים (גוף המסך ושני החלונות שלו - frontend_assembly lazy-html) לא בדף
# שהשרת מגיש. הוא נטען כשפותחים את המסך, לפני ה-JS שלו: כל ה-id במקום, באותו מקום בדף, לא נשאר <template>,
# החלונות מקבלים את מה שחלונות מקבלים בטעינת הדף (✕, role, aria-modal, aria-labelledby, Esc), והתרגום לאנגלית
# חל גם עליו.
# xdist-group: workspace
import re


import pytest

from entrypoints.web import frontend_assembly as fa
from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

LAZY_IDS = [element_id for fragment in fa.lazy_html_fragments("dataviz") for element_id in re.findall(r'\bid="([^"]+)"', fragment)]
# 23.10.2026: לפי שם - לכל מסך עצל ה-template שלו, והוא נעלם רק כשהמסך שלו נטען (מסך "תוצרים" הוסיף אחד)
TEMPLATES = "name => document.querySelectorAll(`template[data-lazy-html=\"${name}\"]`).length"


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה"}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))


def _open(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")


def test_the_graph_editor_html_arrives_with_the_screen(editor_page, screen):
    page = editor_page
    assert len(LAZY_IDS) > 60
    assert page.evaluate("ids => ids.filter(id => document.getElementById(id))", LAZY_IDS) == []
    before = {name: page.evaluate(TEMPLATES, name) for name in fa.lazy_html_names()}
    assert before["dataviz"] == 2 and all(count >= 1 for count in before.values()), before
    assert page.evaluate("() => document.querySelectorAll('template[data-lazy-html]').length") == sum(before.values())
    _open(page)
    assert page.evaluate("ids => ids.filter(id => !document.getElementById(id))", LAZY_IDS) == []
    assert page.evaluate(TEMPLATES, "dataviz") == 0
    assert {name: page.evaluate(TEMPLATES, name) for name in before if name != "dataviz"} == {
        name: count for name, count in before.items() if name != "dataviz"}   # של מסכים אחרים - עד שהם נפתחים
    # אותו מקום כמו קודם: גוף המסך בלשונית שלו אחרי הסרגל העליון, החלונות לפני חלון השוואת הריצות
    assert page.evaluate("() => document.querySelector('.dvz-topbar').nextElementSibling.className") == "dvz-studio"
    assert page.evaluate("() => document.getElementById('dvzNewDialog').closest('[data-tab-panel]').dataset.tabPanel") == "dataviz"
    assert page.evaluate("() => document.getElementById('dvzWizardBg').nextElementSibling.id") == "veRunCompareModalBg"
    for bg, title in (("dvzHelpBg", "dvzHelpTitle"), ("dvzWizardBg", "dvzWizardTitle")):
        attrs = page.evaluate("""bg => {
            const m = document.querySelector(`#${bg} > .modal`);
            return [m.getAttribute('role'), m.getAttribute('aria-modal'), m.getAttribute('aria-labelledby'), m.querySelectorAll(':scope > .modal-close').length];
        }""", bg)
        assert attrs == ["dialog", "true", title, 1], bg
    page.click("#dvzToolsBtn")   # 21.10.2026: ב"🧰 כלים"
    page.click("#dvzToolHelp")
    page.wait_for_selector("#dvzHelpBg.show")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('dvzHelpBg').classList.contains('show')")
    # פתיחה שנייה של המסך לא טוענת שוב ולא מכפילה
    page.evaluate("() => { switchTab('scripts'); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    assert page.evaluate("() => [document.querySelectorAll('.dvz-studio').length, document.querySelectorAll('#dvzHelpBg .modal-close').length]") == [1, 1]


def test_the_lazy_html_is_translated_like_the_rest_of_the_page(editor_page, screen):
    page = editor_page
    page.evaluate("async () => { await setUiLanguage('en'); }")
    page.wait_for_function("() => document.documentElement.lang === 'en'")
    _open(page)
    texts = page.evaluate("() => [document.getElementById('dvzCreateBtn').textContent, document.getElementById('dvzWizardTitle').textContent]")
    assert all(text.strip() and not re.search("[֐-׿]", text) for text in texts), texts
