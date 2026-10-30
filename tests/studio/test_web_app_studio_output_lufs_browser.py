# tests/studio/test_web_app_studio_output_lufs_browser.py
#
# 24.10.2026, מנה 7: בתוצאות הריצה, שורת הקובץ מראה את עוצמת השמע של הפלט כשהנרמול היה דלוק ("-14.1 LUFS ✓", או ⚠️ כשהיא
# רחוקה מהיעד ביותר מ-1 LU), מתוך output_lufs ב-run manifest. בלי נרמול - השורה כמו קודם (89-studio-more.js).
import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

LOADED = "() => !!(window.__uiLazyLoaded && window.__uiLazyLoaded.studio_more)"
SHOW = """(files) => _veShowResults({counts: {files_created: files.length}, output_dir: 'C:\\\\out', files: files.map((f, i) =>
  Object.assign({source: `clip_${i}.mp4`, status: 'created', output: `C:\\\\out\\\\clip_${i}_edited.mp4`, render_seconds: 3}, f))})"""
LINES = "() => [...document.querySelectorAll('#veResultsList .ve-result-main .ve-field-msg')].map(e => e.textContent)"


def test_the_result_line_shows_the_output_loudness_when_normalized(editor_page):
    page = editor_page
    page.evaluate("() => setVeFocus(true)")
    page.wait_for_function(LOADED)
    page.evaluate(SHOW, [{"output_lufs": -14.1, "lufs_target": -14}, {"output_lufs": -18.3, "lufs_target": -14}, {}])
    near, far, plain = page.evaluate(LINES)
    assert near.endswith("-14.1 LUFS ✓")                                                   # קודם: בלי עוצמה
    assert far.endswith("-18.3 LUFS ⚠️")
    assert "LUFS" not in plain
