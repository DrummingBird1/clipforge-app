# tests/web/test_web_app_ux_polish.py
#
# עשרת פריטי העיצוב/UX לעורך-העל בממשק הווב (item: שינויים לא-שמורים, אישור-
# מעבר, תקציר-קטגוריה, קידוד-צבע, פס פעולות צף, סידור מועדפים, איפוס לברירת
# מחדל, מספרים חיים לגרירת watermark, מקראה, טור הכרות, רספונסיביות מובייל) +
# מונחים קצרים/tooltip (title=) שמחליפים את תוויות-המשפט הישנות - אותם items
# בדיוק כמו tests/gui/test_settings_tab_ux_polish.py בדסקטופ, כאן דרך HTML/JS
# מוגש (FastAPI TestClient, בלי דפדפן אמיתי - זה לא יכול להריץ JS בפועל, רק
# לוודא שהמרקאפ/הפונקציות קיימים).


from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.video.video_editor_field_help import FIELD_HELP
from tests.page_source import served_page_text

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _index_html():
    return served_page_text(client)  # גל 24: ה-HTML + ה-bundles של CSS/JS


# --- מונחים קצרים + tooltip ---

def test_field_help_endpoint_matches_python_source_of_truth():
    resp = client.get("/api/video_editor/field_help")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trim_start"] == {"term": FIELD_HELP["trim_start"].term, "tooltip": FIELD_HELP["trim_start"].tooltip}
    assert len(data) == len(FIELD_HELP)


def test_trim_start_label_is_short_term_with_tooltip_not_old_sentence():
    html = _index_html()
    assert f'title="{FIELD_HELP["trim_start"].tooltip}">{FIELD_HELP["trim_start"].term}:</label>' in html
    assert "ריק=עד הסוף" not in html  # ההסבר המלא עבר ל-title=, לא בתווית הגלויה


def test_blur_background_checkbox_shows_short_term():
    html = _index_html()
    # סידור מחדש: רקע מטושטש הוא אפשרות בבורר "מילוי" המאוחד (הצ'קבוקס נשאר מוסתר)
    assert '<option value="blur">' in html[html.index('id="veFillMode"'):]
    assert "בלי לחתוך ממנו" not in html


# --- מקראה ---

def test_glossary_modal_and_button_present():
    html = _index_html()
    assert 'id="glossaryModalBg"' in html
    assert 'id="glossaryList"' in html
    assert 'onclick="openGlossaryDialog()"' in html


# --- תקציר-מצב + קידוד-צבע לקטגוריה ---

def test_category_summary_spans_and_color_coded_data_cat_present():
    html = _index_html()
    # גל 2: watermark/pip/text אוחדו ל-"🧩 שכבות" (layers) - הצבע הוורוד עבר איתם.
    # גל 10: אזורים מאוחדים (פלט/זמן/מראה/שמע וכתוביות/ביצועים).
    for key in ("output", "layers", "time", "perf"):
        assert f'id="veCatSummary-{key}"' in html
    # גל 18: צבע-הזיהוי של כל אזור הוא --cat-color מהפלטה (tokens), לכל 7 האזורים
    for key in ("output", "time", "look", "layers", "sound", "export", "perf"):
        assert f'.ve-category[data-cat="{key}"] {{ --cat-color: var(--hue-' in html
    assert '.ve-category[data-cat="layers"] { --cat-color: var(--hue-pink); }' in html


# --- פס פעולות צף + שינויים לא-שמורים + איפוס ---

def test_sticky_bar_unsaved_indicator_and_reset_button_present():
    html = _index_html()
    assert 'id="veStickyBar"' in html
    assert 'id="veSaveState"' in html  # גל 30: אינדיקטור שמירה אחד (פרויקט + "הסגנון שונה")
    assert 'onclick="resetVideoEditorToDefaults()"' in html


# --- סידור-ידני של המועדפים ---

def test_move_favorite_function_defined_in_js():
    html = _index_html()
    assert "function moveFavorite(fieldKey, direction)" in html
    assert "ve-favorite-reorder" in html


# --- מספרים חיים לגרירת watermark ---

def test_watermark_drag_coords_span_present():
    html = _index_html()
    assert 'id="veWmDragCoords"' in html
    assert "veWmDragCoords" in html and "centerXFraction" in html


# --- טור הכרות ראשוני ---

def test_onboarding_banner_and_dismiss_function_present():
    html = _index_html()
    assert 'id="veOnboardingBanner"' in html
    assert "function dismissVideoEditorOnboarding()" in html
    assert "veOnboardingSeen" in html


# --- רספונסיביות מובייל ---

def test_mobile_media_query_covers_video_editor_panel():
    html = _index_html()
    assert "#videoEditorOptions .ve-row { flex-wrap: wrap; }" in html
    assert ".ve-sticky-bar { flex-direction: column" in html


# --- שינויים לא-שמורים + אישור-מעבר (פונקציות JS) ---

def test_confirm_discard_and_baseline_functions_defined():
    html = _index_html()
    assert "function confirmDiscardUnsavedIfNeeded()" in html
    assert "function captureVideoEditorBaseline()" in html
    assert "function updateUnsavedIndicator()" in html
