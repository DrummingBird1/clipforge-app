# tests/web/test_web_ui_terms.py
#
# גל 34: מילים ואיקונים אחידים בממשק. גל 30 צמצם את המושגים (פרויקט, סגנון, מיתוג, יעד, שכבה מוכנה)
# והחליף מונחים ישנים; הטסט הזה שומר שלא יחזרו, ושלכל מושג יש איקון אחד (VE_CONCEPT_ICONS ב-
# js/78-editor-modes.js). נבדק רק טקסט שהמשתמש רואה: HTML (טקסט, title, placeholder, aria-label)
# ומחרוזות ב-JS - לא הערות ולא מזהים.
import html
import re

from entrypoints.web import frontend_assembly as fa
from tests.web.test_web_i18n_dynamic import HEBREW, js_literals

# מונח ישן -> המונח של היום
OLD_TERMS = {
    "פרופיל": "סגנון",
    "ערכת מותג": "מיתוג",
    "ערכות מותג": "מיתוג",
    "תבנית שכבה": "שכבה מוכנה",
    "תבניות שכבה": "שכבות מוכנות",
    "מתכון": "כל הקבצים",
    "ג'וב": "פרויקט",
}
# שימושים אחרים לגמרי של אותה מילה (לא המושג הישן)
ALLOWED = (
    "פרופיל איכות",           # profile של H.264 - מונח טכני
    "פרופיל / לייק / שיתוף",  # הכפתורים בצד המסך של טיקטוק (אזור בטוח)
)

CONCEPTS = {
    "project": r"פרויקט|הפרויקט|פרויקטים|הפרויקטים",
    "style": r"סגנון|הסגנון|סגנונות|הסגנונות",
    "brand": r"מיתוג|המיתוג",
    "target": r"יעדים|היעדים",
    "ready": r"שכבה מוכנה|שכבות מוכנות",
}
ICONS = {"project": "📁", "style": "🗂️", "brand": "🏷️", "target": "🎯", "ready": "📑"}
# איקון של פעולה או מצב לפני מושג (➕ פרויקט חדש, ⚠️ המיתוג לא קיים) - לא איקון המושג
ACTION_ICONS = {"➕", "⚠️", "●", "✓", "✕", "💾", "🔄", "🗑️", "✏️", "📌", "↺", "⏳", "❌", "✅", "ℹ️", "🔗", "📥", "📤"}
_EMOJI = "\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿←-⇿■-◿"
LEAD = re.compile(f"^((?:[{_EMOJI}]️?)+)\\s*(.*)$", re.S)


def _ui_texts():
    texts = []
    for part in fa.page_parts():
        if part.endswith(".html"):
            source = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", fa.read_part(part), flags=re.S)
            for match in re.finditer(r">([^<>]+)<", source):
                texts += [(part, line.strip()) for line in re.split(r"\n\s*", html.unescape(match.group(1)))]
            texts += [(part, html.unescape(m.group(2))) for m in re.finditer(r'(title|placeholder|aria-label)="([^"]+)"', source)]
        elif part.endswith(".js"):
            texts += [(part, literal) for literal in js_literals(fa.read_part(part))]
    return [(part, text) for part, text in texts if HEBREW.search(text)]


def test_old_terms_do_not_come_back():
    found = []
    for part, text in _ui_texts():
        cleaned = text
        for allowed in ALLOWED:
            cleaned = cleaned.replace(allowed, "")
        found += [f"{part}: {text[:80]!r} - '{old}' -> '{new}'" for old, new in OLD_TERMS.items() if old in cleaned]
    assert found == [], "מונחים ישנים בממשק:\n" + "\n".join(found)


def test_each_concept_has_one_icon():
    wrong = []
    for part, text in _ui_texts():
        match = LEAD.match(text)
        if not match:
            continue
        icon, rest = match.group(1), match.group(2)
        for concept, words in CONCEPTS.items():
            if re.match(rf"(?:{words})(?=$|[\s:.,·])", rest) and icon not in ACTION_ICONS and icon != ICONS[concept]:
                wrong.append(f"{part}: {text[:60]!r} - {concept} צריך {ICONS[concept]}")
    assert wrong == [], "איקון לא אחיד למושג:\n" + "\n".join(wrong)


def test_the_icons_in_the_code_are_the_tested_ones():
    source = fa.read_part("js/78-editor-modes.js")
    declared = dict(re.findall(r'(\w+): "([^"]+)"', re.search(r"const VE_CONCEPT_ICONS = \{([^}]*)\}", source).group(1)))
    assert declared == ICONS
