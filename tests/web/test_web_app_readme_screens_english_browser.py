# tests/web/test_web_app_readme_screens_english_browser.py
#
# 30.10.2026, צילומי המסך של ה-README (dev/make_screenshots.py): שני טקסטים נשארו בעברית בממשק האנגלי ונראו הפוכים בתמונה -
# "🎥 תצוגה חיה (מקורבת) - <קובץ>" בנגן החי של הסטודיו (חסר המפתח בלי " -"), ו"מרוץ עמודות · כהה" בכרטיס של עורך הגרפים
# (צומת טקסט אחד שהמתרגם לא פירק - עכשיו כל תווית בצומת משלה, 42-dataviz-screen.js).
import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

CARD = """() => {
  const card = _dvzEpisodeCard({name: 'demo', title: 'Demo', valid: true, chart: 'bar_race', theme: 'dark', width: 1080, height: 1920});
  document.body.append(card);
  return new Promise(resolve => requestAnimationFrame(() => resolve(card.querySelector('.dvz-card-meta').textContent)));
}"""


def test_the_live_view_label_and_the_episode_card_are_in_english(editor_page):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_function("() => typeof _dvzEpisodeCard === 'function'", timeout=30000)
    page.evaluate("() => setUiLanguage('en')")
    page.wait_for_function("() => _uiLang === 'en' && !!_uiDict")
    assert page.evaluate("() => uiTranslate('🎥 תצוגה חיה (מקורבת) - match_01.mp4')") == "🎥 Live view (approximate) - match_01.mp4"
    page.wait_for_function(f"async () => ({CARD})().then(text => text.includes('Bar race · Dark'))", timeout=10000)   # קודם: בעברית


# 8.11.2026: הכתובית לדוגמה בנגן החי מתורגמת רק כשהטקסט זהה למפתח במילון; אחרי שבירת שורות (caption_max_chars) הטקסט כבר
# לא היה זהה, והמשתמש באנגלית ראה עברית. עכשיו מתרגמים לפני השבירה.
SAMPLE_CAPTION = """(maxChars) => {
  _veLive = _veLive || {};
  _veLiveBuildOverlays({captions: true, caption_max_chars: maxChars, _layers: []}, {w: 1920, h: 1080}, {w: 640, h: 360}, 1 / 3);
  return document.querySelector('#veLiveOverlays .ve-live-caption').textContent;
}"""


def test_the_live_sample_caption_is_in_english_also_when_it_wraps(editor_page):
    page = editor_page
    page.evaluate("() => setUiLanguage('en')")
    page.wait_for_function("() => _uiLang === 'en' && !!_uiDict")
    assert page.evaluate(SAMPLE_CAPTION, 0) == "Sample caption"
    wrapped = page.evaluate(SAMPLE_CAPTION, 8)
    assert wrapped == "Sample\ncaption"
    page.evaluate("() => setUiLanguage('he')")
    page.wait_for_function("() => _uiLang === 'he'")
    assert page.evaluate(SAMPLE_CAPTION, 14) == "כתובית לדוגמה\n· Sample\ncaption"


# 8.11.2026: שכבת "שם הקובץ" (type=filename) הוצגה ברשימת השכבות כ"חותמת-זמן" - השם הברירת-מחדל נפל לענף האחרון
def test_the_file_name_layer_has_its_own_row_label(editor_page):
    page = editor_page
    assert page.evaluate("() => _veLayerDefaultName({type: 'filename'})") == "שם הקובץ"
    assert page.evaluate("() => _veLayerDefaultName({type: 'timestamp'})") == "חותמת-זמן"
    page.evaluate("() => setUiLanguage('en')")
    page.wait_for_function("() => _uiLang === 'en' && !!_uiDict")
    assert page.evaluate("() => uiTranslate(_veLayerDefaultName({type: 'filename'}))") == "File name"
