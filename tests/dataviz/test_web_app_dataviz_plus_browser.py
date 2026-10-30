# tests/dataviz/test_web_app_dataviz_plus_browser.py
#
# 27.10.2026: 25 ההצעות לעורך הגרפים בדפדפן אמיתי (js/85-dataviz-plus.js, bundle dataviz_plus): לחיצה על הכותרת בתצוגה
# עורכת אותה במקום, לחיצה על ישות פותחת צבע, גרירת תיבת הסיום, מצב במאי (M) וטווח לרינדור, בלוקי הסיפור מתחת לסליידר,
# לאורך לצד הרגילה עם אזורים בטוחים, לפני / אחרי, sparkline ומראות עם תמונות, ציון, גרסאות עם תמונה, שמירה כתבנית,
# וידאו בהנפשה וכרטיס המסך בזמן רינדור.
# xdist-group: workspace
import pytest

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

SMALL = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}
ROWS = [("2024-01-%02d" % d, e, v) for d in range(1, 31) for e, v in (("ישראל", 3), ("USA", 5), ("France", 2))]


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    import yaml
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    folder = data / "dataviz_episodes" / "countries"
    folder.mkdir(parents=True)
    workspace.mkdir()
    (folder / "d.csv").write_text("date,entity,v\n" + "".join(f"{d},{e},{v}\n" for d, e, v in ROWS), encoding="utf-8")
    config = {"title": "מדינות", "subtitle": "בדיקה", "ranking": {"top_n": 5}, **SMALL,
              "outro": {"title": "המובילות", "places": ["ראשון", "שני"]},
              "sources": [{"path": "d.csv", "time": {"column": "date"}, "entity": {"column": "entity"}, "value": {"column": "v"}}]}
    (folder / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))


def _open(page, pos=500):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.wait_for_function("() => window.__uiLazyLoaded && window.__uiLazyLoaded.dataviz_plus")
    page.evaluate("(p) => { document.getElementById('dvzPreviewPos').value = String(p); dvzLoadPreview(); }", pos)
    page.wait_for_function("() => dvzPlus.meta && dvzPlus.meta.hits.length && document.querySelector('#dvzHitLayer .dvz-hit')", timeout=30000)


def _hit(page, target):
    return page.locator(f'#dvzHitLayer .dvz-hit[data-target="{target}"]').first


def test_click_the_title_edits_it_in_place(editor_page, screen):
    page = editor_page
    _open(page)
    _hit(page, "path:title").click()
    page.wait_for_selector(".dvz-inline-edit")
    assert page.input_value(".dvz-inline-edit") == "מדינות"
    page.fill(".dvz-inline-edit", "מדינות העולם")
    page.press(".dvz-inline-edit", "Enter")
    page.wait_for_function("() => dvzEd.draft.title === 'מדינות העולם'")
    assert page.locator(".dvz-inline-edit").count() == 0


def test_click_an_entity_opens_its_color(editor_page, screen):
    page = editor_page
    _open(page)
    _hit(page, "entity:USA").click()
    page.wait_for_selector(".dvz-entity-pop input[type=color]")
    page.evaluate("() => { const c = document.querySelector('.dvz-entity-pop input[type=color]'); c.value = '#123456'; c.dispatchEvent(new Event('input')); }")
    assert page.evaluate("() => dvzEd.draft.colors.USA") == "#123456"


def test_drag_the_outro_box(editor_page, screen):
    page = editor_page
    _open(page, pos=1000)
    page.wait_for_function("() => dvzPlus.meta.hits.some(h => h.target === 'outro')", timeout=30000)
    box = _hit(page, "outro").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 - 80, box["y"] + box["height"] / 2 - 30, steps=6)
    page.mouse.up()
    page.wait_for_function("() => Array.isArray(dvzEd.draft['outro.position'])")
    x, y = page.evaluate("() => dvzEd.draft['outro.position']")
    assert -0.5 <= x <= 1.5 and -0.5 <= y <= 1.5


def test_a_dropped_callout_gets_an_offset(editor_page, screen):
    page = editor_page
    _open(page)
    page.evaluate("async () => { await dvzLoadEditor(); _dvzStage('story.callouts', [{date: '2024-01-05', entity: 'USA', text: 'x'}]); }")
    page.evaluate("() => _dvzDropCallout('callout:0:28:-30', 0.1, 0.05)")
    item = page.evaluate("() => dvzEd.draft['story.callouts'][0]")
    assert item["dx"] > 28 and item["dy"] < -30


def test_director_mode_adds_a_chapter_and_a_render_range(editor_page, screen):
    page = editor_page
    _open(page)
    page.keyboard.press("m")
    page.wait_for_selector(".dvz-director")
    page.click(".dvz-director >> text=פרק כאן")
    page.fill(".dvz-director-form input[type=text]", "ההתחלה")
    page.click(".dvz-director-form >> text=הוסף")
    page.wait_for_function("() => (dvzEd.draft['story.chapters'] || []).length === 1")
    chapter = page.evaluate("() => dvzEd.draft['story.chapters'][0]")
    assert chapter["title"] == "ההתחלה" and chapter["date"].startswith("2024-01")
    page.wait_for_selector("#dvzStoryTrack .dvz-story-block.is-point")
    # טווח: שני הקצוות מתפריט הבמאי, ואז "הרץ" שולח אותו בסרטון בדיקה
    for label in ("תחילת טווח לרינדור", "סוף טווח לרינדור"):
        page.keyboard.press("m")
        page.click(f".dvz-director >> text={label}")
    page.wait_for_selector("#dvzRangeChip:not([hidden])")
    page.select_option("#dvzMode", "test")
    assert page.evaluate("() => _dvzRunOptions().range") == page.evaluate("() => `${dvzPlus.range.start},${dvzPlus.range.end}`")


def test_side_by_side_safe_zones_and_before_after(editor_page, screen):
    page = editor_page
    _open(page)
    page.click("#dvzSideBtn")
    page.wait_for_function("() => document.getElementById('dvzPreviewImg2') && document.getElementById('dvzPreviewImg2').naturalHeight > 0", timeout=30000)
    size = page.evaluate("() => { const i = document.getElementById('dvzPreviewImg2'); return [i.naturalWidth, i.naturalHeight]; }")
    assert size[1] > size[0]
    page.click("#dvzSafeBtn")
    page.wait_for_selector("#dvzPreviewSide .dvz-safe-zones rect")
    assert page.is_disabled("#dvzBeforeAfterBtn")
    page.evaluate("async () => { await dvzLoadEditor(); _dvzStage('subtitle', 'אחרת'); await dvzLoadPreview(); }")
    page.wait_for_function("() => !document.getElementById('dvzBeforeAfterBtn').disabled")
    page.click("#dvzBeforeAfterBtn")
    page.wait_for_function("() => document.getElementById('dvzBeforeImg') && document.getElementById('dvzBeforeImg').naturalWidth > 0", timeout=30000)


def test_entities_tab_sparklines_and_flags_bar(editor_page, screen):
    page = editor_page
    _open(page)
    page.evaluate("async () => { const e = document.getElementById('dvzEditor'); e.open = true; await dvzLoadEditor(); dvzEd.tab = 'entities'; _dvzRenderEditor(); }")
    page.wait_for_selector(".dvz-entity-table .dvz-spark polyline", state="attached")   # ערך קבוע - קו שטוח, בלי גובה
    page.wait_for_selector(".dvz-flags-bar")
    assert page.locator(".dvz-flags-bar >> text=הורד דגלים").count() == 1


def test_looks_have_thumbnails_and_the_font_has_a_sample(editor_page, screen):
    page = editor_page
    _open(page)
    page.evaluate("async () => { const e = document.getElementById('dvzEditor'); e.open = true; await dvzLoadEditor(); dvzEd.tab = 'colors'; _dvzRenderEditor(); }")
    page.wait_for_selector(".dvz-looks button[data-look] img.dvz-look-thumb")
    page.wait_for_selector(".dvz-font-row .dvz-font-sample")


def test_score_chip_in_the_prerender_summary(editor_page, screen):
    page = editor_page
    _open(page)
    text = page.evaluate("""() => { _dvzPrerenderDialog(); _dvzPre = {data: 1, facts: 0, read: 2}; _dvzPreSummary();
        return document.querySelector('#dvzPreSummary .dvz-score').textContent; }""")
    assert "72/100" in text   # 100 - 12 - 2*8


def test_history_rows_have_thumbnails(editor_page, screen):
    page = editor_page
    _open(page)
    page.evaluate("async () => { await dvzLoadEditor(); _dvzStage('subtitle', 'גרסה'); await dvzSaveDraft(); await dvzOpenHistory(); }")
    page.wait_for_selector("#dvzHistList tr[data-version] img.dvz-history-thumb")
    src = page.get_attribute("#dvzHistList tr[data-version] img.dvz-history-thumb", "src")
    assert "version=" in src


def test_save_as_template_shows_up_for_new_episodes(editor_page, screen):
    page = editor_page
    _open(page)
    assert page.locator("#dvzSaveTemplateBtn").count() == 1
    page.evaluate("() => dvzSaveTemplate()")
    page.fill(".dvz-template-form input", "התבנית שלי")
    page.click(".dvz-template-form >> text=שמור תבנית")
    page.wait_for_function("() => !document.querySelector('.dvz-template-form')")
    page.evaluate("() => _dvzFillTemplates()")
    page.wait_for_selector("#dvzNewTemplate optgroup.dvz-saved-templates option", state="attached")   # רשימה סגורה
    assert page.evaluate("() => document.querySelector('#dvzNewTemplate optgroup.dvz-saved-templates option').value").startswith("tpl:")


def test_animation_asks_for_video_and_running_polls_the_gpu(editor_page, screen):
    page = editor_page
    _open(page)
    page.evaluate("""() => { window.__urls = []; const f = window.fetch; window.fetch = (u, o) => { window.__urls.push(String(u)); return f(u, o); }; }""")
    page.evaluate("() => dvzToggleAnimation(true)")
    page.wait_for_selector("#dvzPreviewVideo", state="attached", timeout=30000)
    assert any("preview_clip" in u and "format=mp4" in u for u in page.evaluate("() => window.__urls"))
    page.evaluate("() => { dvzToggleAnimation(false); _dvzSetRunning(true); }")
    page.wait_for_function("() => window.__urls.some(u => u.includes('/api/dataviz/gpu'))")
    page.evaluate("() => _dvzSetRunning(false)")
    assert page.locator("#dvzPreviewVideo").count() == 0


def test_annotate_mode_turns_the_hit_layer_off(editor_page, screen):
    page = editor_page
    _open(page)
    page.evaluate("() => dvzToggleAnnotate(true)")
    assert page.evaluate("() => document.getElementById('dvzHitLayer').classList.contains('is-off')")
    page.evaluate("() => dvzToggleAnnotate(false)")
    assert not page.evaluate("() => document.getElementById('dvzHitLayer').classList.contains('is-off')")
