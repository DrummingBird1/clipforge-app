# tests/dataviz/test_web_app_dataviz_dogfood_browser.py
#
# סבב הייצוב (16.10.2026) - מה שנמצא בהרצה אמיתית מקצה לקצה של עורך הגרפים בדפדפן:
#  * העורך המלא נטען פעם אחת גם כש-open = true מפעיל את ontoggle וגם יש קריאה מפורשת (טעינה כפולה ציירה את העורך
#    פעמיים, וקבוצה שנפתחה בין שתיהן נסגרה - הטסט של גל 53 רטט על זה)
#  * "בהיר מול כהה" ו"השווה סוגי תרשים" מציגים גם את מה שעוד לא נשמר, כמו התצוגה החיה
#  * אחרי "💾 שמור שינויים" האומדן (אורך וזמן רינדור) חוזר - לפני כן נעלם עד שבחרו את הפרק שוב
# config.yaml של הפרקים לא משתנה (השמירה כותבת לקובץ השינויים בתיקייה הזמנית).
# xdist-group: workspace
import hashlib
import json
from urllib.parse import parse_qs, urlparse


import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    config = data / "dataviz_episodes" / "alarms" / "config.yaml"
    return {"config": config, "md5": hashlib.md5(config.read_bytes()).hexdigest()}


def _open(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click(".dvz-card[data-episode=alarms]")


def test_opening_the_editor_from_code_loads_it_once(editor_page, screen):
    page = editor_page
    _open(page)
    loads = []
    page.on("request", lambda r: loads.append(r.url) if "/api/dataviz/episodes/editor" in r.url else None)
    # open = true מפעיל את ontoggle (dvzLoadEditor) - ועוד קריאה מפורשת, כמו ב-_dvzPickCompared ובטסטים. המאזין של הטסט
    # נרשם אחרי ontoggle שבתוך ה-HTML, אז כשהדגל שלו עולה - הטעינה השנייה (בקוד הישן) כבר נשלחה; ⏳ יורד כשטעינה הסתיימה
    page.evaluate("() => document.getElementById('dvzEditor').addEventListener('toggle', () => { window.__dvzToggled = true; }, {once: true})")
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; return dvzLoadEditor(); }")
    page.wait_for_function("() => window.__dvzToggled && !document.getElementById('dvzEditorStatus').textContent.includes('⏳')")
    page.wait_for_selector("#dvzEditorBody .dvz-group")
    assert len(loads) == 1, loads
    group = "document.querySelector('[data-path=\"ranking.log_scale\"]').closest('details')"
    page.evaluate(f"() => {{ setDvzMode('advanced'); {group}.open = true; }}")   # קבוצת הדירוג - במצב מומחה (19.10)
    assert page.evaluate(f"() => {group}.open")                  # הקבוצה שנפתחה לא נסגרה מתחת לידיים
    page.check("#dvzF-ranking-log_scale")
    assert page.evaluate("() => dvzEd.draft['ranking.log_scale']") is True
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]


def test_the_estimate_comes_back_after_saving(editor_page, screen):
    page = editor_page
    _open(page)
    page.select_option("#dvzMode", "full")
    page.wait_for_function("() => document.getElementById('dvzEstimate').textContent.includes('⏱')")
    page.click("#dvzEditor > summary")
    page.wait_for_selector("#dvzEditorBody .dvz-group")
    page.fill("#dvzF-ranking-top_n", "4")
    # התיאור לפרסום בכמה שורות - textarea, וירידות השורה נשמרות בטיוטה
    assert page.evaluate("() => document.getElementById('dvzF-publish-description').tagName") == "TEXTAREA"
    page.fill("#dvzF-publish-description", "שורה ראשונה\nשורה שנייה")
    assert page.evaluate("() => dvzEd.draft['publish.description']") == "שורה ראשונה\nשורה שנייה"
    page.click("#dvzDraftSave")
    page.wait_for_function("() => document.getElementById('dvzEditorStatus').textContent.includes('נשמר')")
    # השמירה מוחקת את האומדן הישן (ההגדרות השתנו) - הוא נטען מחדש ולא נעלם עד שבוחרים את הפרק שוב
    page.wait_for_function("() => document.getElementById('dvzEstimate').textContent.includes('⏱')", timeout=20000)
    page.select_option("#dvzMode", "test")
    assert "⏱" in page.inner_text("#dvzEstimate")


def test_compare_shows_what_is_not_saved_yet(editor_page, screen):
    page = editor_page
    _open(page)
    page.click("#dvzEditor > summary")
    page.wait_for_selector("#dvzEditorBody .dvz-group")
    page.fill("#dvzF-subtitle", "תת-כותרת שעוד לא נשמרה")
    page.select_option("#dvzF-theme", "dark")
    page.click("button:has-text('בהיר מול כהה')")
    srcs = page.eval_on_selector_all("#dvzCompareBox img", "imgs => imgs.map(i => i.getAttribute('src'))")
    assert len(srcs) == 2
    for src in srcs:
        query = parse_qs(urlparse(src).query)
        assert json.loads(query["draft"][0])["subtitle"] == "תת-כותרת שעוד לא נשמרה"
    captions = page.eval_on_selector_all("#dvzCompareBox figcaption", "els => els.map(e => e.textContent)")
    assert captions == ["בהיר", "כהה ✓"]                          # הערכה שבטיוטה, לא זו שבקובץ
    page.click("button:has-text('בהיר מול כהה')")                # סוגר
    page.click("#dvzRunOverrides > summary")
    page.select_option("#dvzChart", "line_race")
    page.click("button:has-text('השווה סוגי תרשים')")
    srcs = page.eval_on_selector_all("#dvzCompareBox img", "imgs => imgs.map(i => i.getAttribute('src'))")
    charts = [parse_qs(urlparse(src).query)["chart"][0] for src in srcs]
    assert "bar_race" in charts and "line_race" in charts and len(set(charts)) == len(charts)
    assert all("draft" in parse_qs(urlparse(src).query) for src in srcs)
    assert page.inner_text("#dvzCompareBox button.is-current + figcaption") == "מרוץ קווים ✓"
    page.wait_for_function("() => [...document.querySelectorAll('#dvzCompareBox img')].every(i => i.complete && i.naturalWidth > 0)", timeout=60000)
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]
