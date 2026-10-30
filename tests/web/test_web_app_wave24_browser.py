# tests/web/test_web_app_wave24_browser.py
#
# גל 24 (ביצועים) בדפדפן אמיתי: שורות התור לא נבנות מחדש בכל לחיצה (רק מה שהשתנה),
# וה-CSS/JS מגיעים כקבצים סטטיים שנשמרים ב-cache - טעינה חוזרת לא מורידה אותם שוב.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

FILL_QUEUE = """(count) => {
  _veQueueState = Array.from({length: count}, (_, i) => ({name: `clip_${String(i).padStart(3, "0")}.mp4`, selected: true, overrides: {}}));
  _veQueueDirty = true;
  _renderVeQueue();
  return document.querySelectorAll("#veQueueList .ve-queue-row").length;
}"""
ROW = "(i) => document.querySelectorAll('#veQueueList .ve-queue-row')[i]"


def test_toggling_one_queue_row_keeps_every_other_row(editor_page, tmp_path):
    page = editor_page
    page.evaluate("(folder) => { state.folder = folder; }", str(tmp_path))
    assert page.evaluate(FILL_QUEUE, 300) == 300
    page.evaluate(f"() => {{ window.__row0 = ({ROW})(0); window.__row150 = ({ROW})(150); window.__thumb0 = window.__row0.querySelector('img'); }}")

    page.evaluate(f"() => ({ROW})(0).querySelector('input[type=checkbox]').click()")
    assert page.evaluate("() => _veQueueState[0].selected") is False
    assert page.evaluate(f"() => ({ROW})(150) === window.__row150"), "שורה שלא השתנתה נבנתה מחדש"
    assert page.evaluate(f"() => ({ROW})(0) !== window.__row0 && ({ROW})(0).classList.contains('ve-queue-excluded')")
    assert page.evaluate(f"() => ({ROW})(0).querySelector('img') === window.__thumb0"), "התמונה של השורה נטענה מחדש"
    assert page.evaluate("() => document.querySelectorAll('#veQueueList .ve-queue-row').length") == 300

    # בחירה (Ctrl) והזזה לראש התור: השורות אחרי המקום של הפריט שזז לא נבנות מחדש
    page.evaluate(f"() => {{ window.__row200 = ({ROW})(200); }}")
    page.evaluate(f"() => ({ROW})(150).dispatchEvent(new MouseEvent('click', {{bubbles: true, ctrlKey: true}}))")
    page.evaluate("() => veQueueBulk('top')")
    names = page.evaluate("() => [...document.querySelectorAll('#veQueueList .ve-queue-name')].slice(0, 2).map(e => e.textContent)")
    assert names == ["1. clip_150.mp4", "2. clip_000.mp4"]
    assert page.evaluate(f"() => ({ROW})(200) === window.__row200")
    assert page.evaluate("() => _veQueueState.map(f => f.name).join() === [...document.querySelectorAll('#veQueueList .ve-queue-row')].map(r => r.querySelector('.ve-queue-name').textContent.replace(/^\\d+\\. /, '')).join()")


def test_a_new_queue_list_replaces_the_rows_and_the_old_ones_are_gone(editor_page, tmp_path):
    page = editor_page
    page.evaluate("(folder) => { state.folder = folder; }", str(tmp_path))
    page.evaluate(FILL_QUEUE, 5)
    assert page.evaluate(FILL_QUEUE, 3) == 3  # פריטים חדשים (אובייקטים חדשים) - שורות חדשות, בלי שאריות
    page.evaluate("() => { _veQueueState = []; _renderVeQueue(); }")
    assert page.evaluate("() => document.querySelectorAll('#veQueueList .ve-queue-row').length") == 0
    # גל 31: בלי קבצים - מצב ריק עם פעולה (במקום שורת הרמז)
    assert page.evaluate("() => document.querySelector('#veQueueList').children.length === 1 && !!document.querySelector('#veQueueList .ve-empty')")


def test_css_and_js_come_from_the_cache_on_the_next_load(editor_server, edge_browser):
    context = edge_browser.new_context(viewport={"width": 1280, "height": 800}, locale="he-IL")
    try:
        page = context.new_page()
        url = f"{editor_server['base_url']}/?token={editor_server['web_app'].ACCESS_TOKEN}"
        page.goto(url)
        page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)
        first = page.evaluate("() => performance.getEntriesByType('resource').filter(e => /\\/static\\/app\\.[0-9a-f]{12}\\.(css|js)$/.test(e.name)).map(e => e.transferSize)")
        assert len(first) == 2 and all(size > 0 for size in first)
        page.goto(url)
        page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)
        second = page.evaluate("() => performance.getEntriesByType('resource').filter(e => /\\/static\\/app\\.[0-9a-f]{12}\\.(css|js)$/.test(e.name)).map(e => e.transferSize)")
        assert second == [0, 0], f"ה-bundles הורדו שוב: {second}"
    finally:
        context.close()
