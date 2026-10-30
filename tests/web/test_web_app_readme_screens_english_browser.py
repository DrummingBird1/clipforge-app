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
