# tests/dataviz/conftest.py
#
# 21.10.2026 (סבב הפישוט): עורך הגרפים נפתח עכשיו במצב "פשוט" אמיתי (תיקייה -> סקירה -> רינדור, והשאר מוסתר). טסטי הדפדפן
# הקיימים בודקים את כל הכלים, אז הם מתחילים ב"רגיל" - הגישה של לפני הסבב (כמו veMode של עורך-העל ב-tests/conftest.py).
# טסט של המצב הפשוט מוחק את ההגדרה (localStorage.removeItem('dvzMode')) לפני שהוא פותח את המסך.
import pytest


@pytest.fixture
def editor_page(editor_page):
    editor_page.evaluate("() => { if (localStorage.getItem('dvzMode') === null) localStorage.setItem('dvzMode', 'regular'); }")
    return editor_page
