# tests/web/test_web_app_auto_favorites_and_archive.py
#
# שני שינויים בעקבות בקשה מפורשת: מועדפים אוטומטיים בעורך-העל (מחליפים
# לגמרי את הבחירה הידנית "⭐ הגדר מועדפים..." - שדה checkbox מצטרף כשהוא
# מסומן/יוצא כשהוא מבוטל, כל שדה אחר מצטרף כשהוא שונה מברירת המחדל/יוצא
# כשהוא חוזר אליה), וטאב "🗄️ ארכיון" לסקריפטים ש-video_editor.py מייתר
# לגמרי (לא רק חופפים חלקית). TestClient בלבד - בדיקת ההתנהגות החיה (JS
# אמיתי בדפדפן) בוצעה ידנית, ראו סיכום השיחה.


from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from tests.page_source import served_page_text

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _index_html():
    return served_page_text(client)  # גל 24: ה-HTML + ה-bundles של CSS/JS


# --- מועדפים אוטומטיים (item) ---

def test_manual_favorites_picker_fully_removed():
    html = _index_html()
    assert 'id="favoritesModalBg"' not in html
    assert "openFavoritesDialog" not in html
    assert "applyFavoritesSelection" not in html
    assert "הגדר מועדפים" not in html


def test_auto_favorites_functions_present():
    html = _index_html()
    assert "function _computeAutoFavoriteKeys()" in html
    assert "function syncAutoFavorites()" in html


def test_auto_favorites_checkbox_rule_uses_checked_state():
    html = _index_html()
    assert 'el.type === "checkbox" ? el.checked :' in html


def test_auto_favorites_non_checkbox_rule_compares_to_default():
    html = _index_html()
    assert "String(el.value) !== String(_veFieldDefaults[el.id])" in html


def test_auto_favorites_preserves_existing_manual_order():
    html = _index_html()
    assert "existingOrder" in html and "newlyAdded" in html


def test_auto_favorites_dependent_watermark_and_pip_fields_gated_by_their_path():
    # item: מחיקת נתיב Watermark/PiP מוציאה גם את השדות התלויים בו (מיקום/
    # שקיפות/גודל) מהמועדפים, גם אם ערכם שלהם עדיין שונה מברירת המחדל -
    # אין להם שום השפעה בלי נתיב מוגדר, אז אין טעם שיישארו מסומנים "מועדף".
    html = _index_html()
    assert "const VE_FAVORITE_DEPENDS_ON = {" in html
    assert 'watermark_position: "veWatermarkPath"' in html
    assert 'watermark_opacity: "veWatermarkPath"' in html
    assert 'watermark_scale: "veWatermarkPath"' in html
    assert 'pip_position: "vePipPath"' in html
    assert 'pip_opacity: "vePipPath"' in html
    assert 'pip_scale: "vePipPath"' in html
    assert "const dependsOnId = VE_FAVORITE_DEPENDS_ON[fieldKey];" in html
    assert "if (!dependsOnEl || !dependsOnEl.value.trim()) isFavorite = false;" in html


def test_auto_favorites_wired_into_profile_apply_and_reset():
    html = _index_html()
    # _applyVideoEditorFields (טעינת פרופיל/איפוס לברירת מחדל, ששניהם עוברים
    # דרכה) קוראת ל-syncAutoFavorites אחרי שכל השדות כבר הוחלו.
    assert 'document.getElementById("veFavoriteFields").value = fields.favorite_fields || "";\n  syncAutoFavorites();' in html


def test_auto_favorites_wired_into_live_input_and_change_events():
    html = _index_html()
    # גל 9 (item 101): דרך debounce - חישוב המועדפים לא רץ בכל הקשה/גרירת סליידר
    assert 'if (!e.target.closest(".ve-favorite-row")) _veScheduleFavoritesSync();' in html
    assert "_veFavoritesSyncTimer = setTimeout(syncAutoFavorites, 200);" in html


def test_empty_favorites_hint_no_longer_references_removed_button():
    html = _index_html()
    assert "אין מועדפים כרגע" in html
    assert 'לחץ "⭐ הגדר מועדפים' not in html


# --- ארכיון (item) ---

def test_timelapse_maker_marked_archived_and_excluded_from_main_list_only():
    resp = client.get("/api/scripts")
    assert resp.status_code == 200
    scripts = {s["id"]: s for s in resp.json()}
    timelapse_id = next(sid for sid in scripts if sid.endswith("timelapse_maker.py"))
    assert scripts[timelapse_id]["archived"] is True
    # וידאו-אדיטור עצמו (וכל השאר) לא אמור להיות מסומן ארכיון
    video_editor_id = next(sid for sid in scripts if sid.endswith("video_editor.py"))
    assert scripts[video_editor_id]["archived"] is False


def test_archive_tab_and_panel_present_in_html():
    html = _index_html()
    assert 'data-tab="archive"' in html
    assert 'data-tab-panel="archive"' in html
    assert 'id="archiveList"' in html


def test_render_scripts_excludes_archived_from_main_list_js():
    html = _index_html()
    assert "const visibleScripts = state.scripts.filter(s => !_scIsArchived(s));" in html


def test_render_archive_list_function_present_and_switches_back_to_scripts_tab():
    html = _index_html()
    assert "function renderArchiveList()" in html
    assert 'switchTab("scripts"); selectScript(s.id);' in html


def test_switch_tab_calls_render_archive_list():
    html = _index_html()
    assert 'else if (name === "archive") {\n    renderArchiveList();' in html
