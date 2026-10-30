# tests/web/test_web_accessibility.py
#
# גל 21 (שדרוג העיצוב): ערכות נושא, ניגודיות, ממשק באנגלית ותקציב ביצועים -
# בלי דפדפן. ניגודיות WCAG AA מחושבת ישירות מה-tokens בכל ערכה (כהה/בהירה/
# ניגודיות גבוהה/Pro Dark וכל צבעי ההדגשה); המילון האנגלי מכסה כל טקסט עברי
# סטטי ב-HTML; ה-CSS נשאר בתוך תקציב גודל.
import html
import json
import os
import re


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web import frontend_assembly as fa

client = TestClient(web_app.app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)

I18N_PATH = os.path.join(os.path.dirname(fa.FRONTEND_DIR), "i18n", "en.json")
HEBREW = re.compile("[%s-%s]" % (chr(0x0590), chr(0x05FF)))
# אימוג'י/סמלים בתחילת טקסט - אותם טווחים כמו _UI_LEAD ב-69-ui-prefs.js
_EMOJI_RANGES = [(0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0x2300, 0x23FF), (0x2190, 0x21FF), (0x25A0, 0x25FF)]
LEADING_EMOJI = re.compile("^[%s%s%s ]+" % ("".join(f"{chr(a)}-{chr(b)}" for a, b in _EMOJI_RANGES), chr(0xFE0F), chr(0x200D)))


# --- ממשק באנגלית ---

def _static_hebrew_strings():
    """אותו חילוץ כמו בזמן ריצה (69-ui-prefs.js): טקסט בין תגיות (שורה-שורה) ו-title/placeholder/aria-label,
    בלי אימוג'י מוביל (האימוג'י נעטף ב-span נפרד ונשאר כמו שהוא)."""
    found = set()

    def add(text):
        key = LEADING_EMOJI.sub("", text.strip()).strip()
        if key and HEBREW.search(key):
            found.add(key)

    for part in fa.page_parts():
        if not part.endswith(".html"):
            continue
        source = re.sub(r"<script.*?</script>|<style.*?</style>", "", fa.read_part(part), flags=re.S)
        for match in re.finditer(r">([^<>]+)<", source):
            for line in re.split(r"\n\s*", html.unescape(match.group(1))):
                add(line)
        for match in re.finditer(r'(title|placeholder|aria-label)="([^"]+)"', source):
            add(html.unescape(match.group(2)))
    return found


def _dictionary():
    with open(I18N_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_every_static_hebrew_string_has_an_english_translation():
    exact = _dictionary()["exact"]
    missing = sorted(_static_hebrew_strings() - set(exact))
    assert missing == [], f"חסר תרגום ב-web/i18n/en.json ל-{len(missing)} מחרוזות, למשל: {missing[:5]}"


def test_translations_are_english_and_patterns_compile():
    data = _dictionary()
    assert len(data["exact"]) > 1000
    for source, target in data["exact"].items():
        assert target.strip(), f"תרגום ריק: {source}"
        assert not HEBREW.search(target), f"נשאר עברית בתרגום של {source!r}: {target!r}"
    for source, replacement in data["patterns"]:
        re.compile(source)
        assert not HEBREW.search(replacement), replacement


def test_no_key_appears_twice_in_the_dictionary():
    # 23.10.2026: json.load שומר רק את המופע האחרון - מפתח כפול דרס בשקט תרגום קודם ("Tags" הפך ל-"Hashtags")
    duplicates = []

    def collect(pairs):
        keys = [key for key, _value in pairs]
        duplicates.extend(sorted({key for key in keys if keys.count(key) > 1}))
        return dict(pairs)

    with open(I18N_PATH, encoding="utf-8") as f:
        json.load(f, object_pairs_hook=collect)
    assert duplicates == [], f"מפתחות כפולים ב-web/i18n/en.json: {duplicates}"


def test_ui_strings_api_serves_only_known_languages():
    response = client.get("/api/ui_strings/en")
    assert response.status_code == 200
    body = response.json()
    assert body["exact"]["מה נערוך היום?"] == "What are we editing today?"
    assert client.get("/api/ui_strings/fr").status_code == 404
    assert client.get("/api/ui_strings/..%2Fen").status_code == 404


def test_language_and_theme_controls_are_in_the_page():
    page = fa.assemble_page()
    for marker in ('id="uiPrefsMenu"', 'data-theme-opt="contrast"', 'data-theme-opt="auto"', 'data-accent-opt="rose"', 'data-lang-opt="en"'):
        assert marker in page, marker
    assert "js/69-ui-prefs.js" in fa.page_parts() and "styles/19-access.css" in fa.page_parts()


# --- ניגודיות WCAG ---

def _tokens_css():
    return re.sub(r"/\*.*?\*/", "", fa.read_part("styles/00-tokens.css"), flags=re.S)


def _block(css, selector):
    match = re.search(r"(?m)^\s*" + re.escape(selector) + r"\s*\{", css)
    assert match, f"לא נמצא בלוק {selector}"
    start, depth, i = match.end(), 1, match.end()
    while depth:
        depth += {"{": 1, "}": -1}.get(css[i], 0)
        i += 1
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", css[start:i - 1]))


def _themes():
    css = _tokens_css()
    dark_only = ':root:not([data-theme="light"], [data-theme="contrast"])'
    focus_off = f"{dark_only} body.ve-focus, {dark_only} body.dvz-focus"   # גל 56: גם עורך הגרפים במסך המלא
    base = {**_block(css, ":root"), **_block(css, ":root, " + focus_off)}
    themes = {
        "dark": base,
        "light": {**base, **_block(css, '[data-theme="light"]')},
        "contrast": {**base, **_block(css, '[data-theme="contrast"]')},
        "pro-dark": {**base, **_block(css, focus_off)},
    }
    for accent in ("emerald", "violet", "amber", "rose"):
        themes[f"dark+{accent}"] = {**themes["dark"], **_block(css, f':root[data-accent="{accent}"]')}
        themes[f"light+{accent}"] = {**themes["light"], **_block(css, f':root[data-accent="{accent}"]'),
                                     **_block(css, f':root[data-theme="light"][data-accent="{accent}"]')}
    return themes


def _resolve(tokens, name, depth=0):
    value = tokens[name].strip()
    match = re.fullmatch(r"var\(\s*(--[\w-]+)\s*(?:,[^)]*)?\)", value)
    if match and depth < 10:
        return _resolve(tokens, match.group(1), depth + 1)
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else None


def _luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _ratio(tokens, fg, bg):
    a, b = _resolve(tokens, fg), _resolve(tokens, bg)
    assert a and b, (fg, bg)
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


TEXT_TOKENS = ("--color-text", "--color-text-2", "--color-text-3", "--color-accent", "--color-success", "--color-warning", "--color-danger", "--color-info")
SURFACES = ("--color-bg", "--color-surface-1", "--color-surface-2", "--color-surface-3", "--color-sunken")


@pytest.mark.parametrize("theme", sorted(_themes()))
def test_text_colors_meet_wcag_aa_on_every_surface(theme):
    tokens = _themes()[theme]
    failures = [f"{fg} על {bg}: {_ratio(tokens, fg, bg):.2f}" for fg in TEXT_TOKENS for bg in SURFACES if _ratio(tokens, fg, bg) < 4.5]
    assert failures == [], f"{theme}: ניגודיות מתחת ל-4.5:1 - {failures}"
    assert _ratio(tokens, "--color-on-accent", "--color-accent") >= 4.5, theme
    assert _ratio(tokens, "--color-on-solid", "--color-danger-solid") >= 4.5, theme
    # טבעת הפוקוס היא רכיב ממשק - לפחות 3:1 מול הרקע (WCAG 1.4.11)
    assert _ratio(tokens, "--color-focus", "--color-bg") >= 3, theme


def test_high_contrast_theme_reaches_aaa_and_visible_borders():
    tokens = _themes()["contrast"]
    for fg in ("--color-text", "--color-text-2", "--color-text-3", "--color-accent"):
        for bg in SURFACES:
            assert _ratio(tokens, fg, bg) >= 7, (fg, bg)
    assert _ratio(tokens, "--color-border", "--color-bg") >= 3
    assert _ratio(tokens, "--color-border-strong", "--color-bg") >= 3


# --- נגישות ותקציב ביצועים ב-CSS ---

def test_focus_ring_and_minimum_hit_targets_are_defined():
    css = fa.read_part("styles/19-access.css")
    assert ":focus-visible" in css and "var(--ring)" in css
    assert re.search(r"\.icon-only\s*\{[^}]*min-inline-size:\s*34px[^}]*min-block-size:\s*34px", css)
    coarse = css[css.index("@media (pointer: coarse)"):]
    assert "min-block-size: 44px" in coarse[:coarse.index("\n    }\n")]


def test_long_lists_skip_offscreen_rendering():
    css = fa.read_part("styles/19-access.css")
    code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for selector in (".feed-item", ".gallery-card", ".ve-job-card", ".approval-card"):
        rule = re.search(r"(?m)^[^{\n]*" + re.escape(selector) + r"[^{\n]*\{([^}]*content-visibility: auto[^}]*)\}", code)
        assert rule and "contain-intrinsic-size" in rule.group(1), selector


def test_css_performance_budget():
    # גל 39: ה-CSS שנטען עם הדף - מסך שנטען לפי דרישה מביא את ה-CSS שלו איתו (frontend_assembly.LAZY_CSS)
    css = fa.bundle("css")
    code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    assert "@import" not in "".join(fa.lazy_css(name) for name in fa.LAZY_CSS)
    # גל 31: 230K->240K אחרי ניקוי של כ-2KB CSS מת (גיליון לפני הרצה, תוצאות בסטודיו, פסי אייקונים, היררכיה)
    # גל 33 (מפקח מסודר: מסלול ניווט, הערות ליד שדה, כלי קבוצה): 240K->245K; גל 35 (תור ברשת, סימנים, מיני-מפה): 245K->250K; גל 36 (קבוצות שכבות, מרכז ריצות): 250K->255K
    assert len(css.encode("utf-8")) <= 255_000, "ה-CSS חרג מהתקציב (255KB) - לנקות לפני שמוסיפים"
    assert "@import" not in code, "@import חוסם רינדור - כל ה-CSS הוא bundle אחד מ-parts.txt"
    assert code.count("!important") <= 32
    assert code.count("{") <= 1660  # גל 31: 1450->1500 (ראו התקציב למעלה); מסך סרטוני נתונים והסטודיו עם ☰: 1500->1520; גל 33: 1520->1560; גל 34: 1560->1600; גל 36: 1600->1660
    # גל 24: תקציב לכל מה שנשלח - ה-HTML וה-JS בנפרד, ודחוסים (ה-CSS נבדק למעלה)
    # גל 34 (ספרייה, מה חדש, סיור, רמה שלישית): 200K->210K; גל 39 (העורך המלא של עורך הגרפים): 210K->215K;
    # גלים 41-42 (אשף הפרסום ומדריך המנוע של עורך הגרפים): 215K->220K
    # סבב ייצוב: ה-HTML של עורך הגרפים נטען עם המסך (frontend_assembly lazy-html) - 219.6K->203K, התקרה לא זזה
    assert len(fa.assemble_page().encode("utf-8")) <= 220_000
    for name in fa.lazy_html_names():
        assert len(fa.lazy_html_bundle(name).encode("utf-8")) <= 30_000, name
    # גל 30: 750K->790K (מצב עריכת קליפ, מראות מוכנים וארבעת הצעדים); הדחוס - מה שבאמת נשלח - נשאר בתקציב
    # מסך סרטוני נתונים (42-dataviz-screen.js): 790K->815K; הדחוס נשאר בתקציב
    # גל 33 (77-editor-inspector-tools.js - רוב הגידול הוא טקסט עברי, 2 בייט לאות): 815K->840K; גל 34 (78-editor-modes.js): 840K->870K; גל 35 (79-editor-queue-timeline.js): 870K->890K; גל 36 (80-editor-layers-runs.js): 890K->910K
    assert len(fa.bundle("js").encode("utf-8")) <= 910_000
    # scripts catalog (categories/search/localStorage favorites+archive): 260K->263K gzipped
    # גל 38: מה שנשלח בטעינה הראשונה - בלי מסכים שנטענים לפי דרישה (frontend_assembly.LAZY_JS)
    assets = fa.build_assets()
    shipped = sum(len(asset["gzip"]) for asset in assets.values() if not asset.get("lazy"))
    # גל 33: 263K->270K; גל 34: 270K->278K; גל 35: 278K->284K; גל 36: 284K->292K
    # 23.10.2026, תיקיית ייצוא שלב 2 (תיקייה לכלי, 291,993->292,050): 292K->293K, פעם אחת באישור המפנה; מיד אחריו ההגדרות
    # הכלליות עברו ל-bundle עצל (LAZY_JS["settings"], 292,050->289,143) והתקרה חזרה ל-292K
    assert shipped <= 292_000, f"CSS+JS דחוסים: {shipped} בייט"
    # גל 38: כל מסך שנטען לפי דרישה (עורך הגרפים) - תקציב משלו, כדי שגם הוא לא יתנפח בלי לשים לב
    # גלים 41-42 (סדרות ופרסום, מדריך המנוע): 120K->130K; גלים 43-45 (שאריות עורך הגרפים: מראה, תור, קריינות ומפות): 130K->160K
    for name in fa.LAZY_JS:
        assert len(fa.lazy_bundle(name).encode("utf-8")) <= 160_000, name
