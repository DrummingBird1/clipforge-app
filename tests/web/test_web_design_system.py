# tests/web/test_web_design_system.py
#
# גלים 15-18 (שדרוג העיצוב): שומרים על מערכת העיצוב של ממשק הדפדפן -
# צבעים רק מה-tokens, כל var(--x) מוגדר, מאפיינים לוגיים (RTL), כל קובץ CSS
# בשכבה (cascade layer), תקרה על style="..." ב-HTML, הפונטים והאייקונים המקומיים,
# ועמוד /styleguide.
import json
import os
import re


from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web import frontend_assembly as fa

STYLES_DIR = os.path.join(fa.FRONTEND_DIR, "styles")
TOKEN_FILES = {"00-tokens.css"}
GENERATED_FILES = {"02-icons.css"}
LAYERS = ["reset", "tokens", "components", "shell", "editor", "studio", "utilities"]

client = TestClient(web_app.app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)


def _css_parts():
    return [(part, fa.read_part(part)) for part in fa.page_parts() if part.startswith("styles/")]


def _strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def test_colors_come_only_from_tokens():
    raw = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
    for part, css in _css_parts():
        name = part.split("/")[-1]
        if name in TOKEN_FILES or name in GENERATED_FILES:
            continue
        for number, line in enumerate(_strip_comments(css).splitlines(), 1):
            assert not raw.search(line), f"{part}:{number} צבע גולמי - השתמש ב-token מ-00-tokens.css: {line.strip()}"


def test_every_css_variable_used_is_defined_or_has_a_fallback():
    sources = [fa.read_part(part) for part in fa.page_parts()]
    joined = "\n".join(sources)
    defined = set(re.findall(r"(--[\w-]+)\s*:", joined))
    defined |= set(re.findall(r"setProperty\(\s*[\"'`](--[\w-]+)", joined))
    without_fallback = {}
    for source in sources:
        for match in re.finditer(r"var\(\s*(--[\w-]+)\s*([,)])", _strip_comments(source)):
            if match.group(2) == ")":
                without_fallback.setdefault(match.group(1), 0)
    missing = sorted(name for name in without_fallback if name not in defined)
    assert missing == [], f"משתנים בלי הגדרה ובלי ערך חלופי: {missing}"


def test_every_css_part_lives_in_a_declared_layer():
    tokens = fa.read_part("styles/00-tokens.css")
    order = re.search(r"@layer\s+([\w\s,]+);", tokens).group(1)
    assert [name.strip() for name in order.split(",")] == LAYERS
    for part, css in _css_parts():
        blocks = re.findall(r"@layer\s+([\w-]+)\s*\{", css)
        assert blocks, f"{part} לא עטוף ב-@layer"
        assert all(block in LAYERS for block in blocks), f"{part}: שכבה לא מוכרת {blocks}"


def test_css_uses_logical_properties_except_marked_ltr_lines():
    physical = re.compile(r"(?<![-\w])(left|right)\s*:|(margin|padding|border)-(left|right)\b|text-align\s*:\s*(left|right)")
    for part, css in _css_parts():
        for number, line in enumerate(css.splitlines(), 1):
            code = re.sub(r"/\*.*?\*/", "", line)
            if physical.search(code) and "/* ltr" not in line:
                assert False, f"{part}:{number} מאפיין פיזי (left/right) בלי סימון /* ltr - השתמש ב-inline-start/end: {line.strip()}"


def test_inline_style_budget_in_html_and_js():
    html = "".join(fa.read_part(part) for part in fa.page_parts() if part.endswith(".html"))
    assert html.count('style="') <= 1, "style=\"...\" חדש ב-HTML - השתמש במחלקה (90-utilities.css / רכיב)"
    js = "".join(content for _part, content in fa.js_parts())
    # גל 22: שורות הגיבויים וה-credentials נבנות ב-DOM עם מחלקות - התקרה ירדה
    assert js.count("style=") <= 6
    assert js.count(".cssText") <= 13


def test_type_scale_is_the_only_source_of_font_sizes():
    for part, css in _css_parts():
        name = part.split("/")[-1]
        if name in TOKEN_FILES:
            continue
        for number, line in enumerate(_strip_comments(css).splitlines(), 1):
            assert not re.search(r"font-size\s*:\s*[0-9.]+px", line), f"{part}:{number} גודל טקסט בפיקסלים - השתמש ב---fs-*: {line.strip()}"


def test_light_theme_and_pro_dark_override_the_semantic_tokens():
    tokens = fa.read_part("styles/00-tokens.css")
    assert '[data-theme="light"]' in tokens
    # גל 21: Pro Dark לא חל גם על ניגודיות גבוהה
    assert ':root:not([data-theme="light"], [data-theme="contrast"]) body.ve-focus' in tokens
    assert '[data-theme="contrast"]' in tokens
    for name in ("--color-bg", "--color-surface-1", "--color-text", "--color-accent", "--color-danger", "--media-bg", "--fs-sm", "--r-md"):
        assert re.search(re.escape(name) + r"\s*:", tokens), name


def test_ui_fonts_are_served_locally_and_only_whitelisted():
    response = client.get("/assets/fonts/heebo-hebrew.woff2")
    assert response.status_code == 200
    assert response.headers["content-type"] == "font/woff2"
    assert "immutable" in response.headers["cache-control"]
    assert response.content[:4] == b"wOF2"
    for name in ("jetbrains-mono-latin.woff2", "heebo-latin.woff2"):
        assert client.get(f"/assets/fonts/{name}").status_code == 200
    assert client.get("/assets/fonts/other.woff2").status_code == 404
    assert client.get("/assets/fonts/..%2F..%2Fdata%2Fweb_app_token.txt").status_code == 404
    for license_file in ("OFL-Heebo.txt", "OFL-JetBrainsMono.txt"):
        assert os.path.isfile(os.path.join(web_app.BASE_DIR, "assets", "fonts", license_file))


def test_generated_icons_match_the_generator_mapping():
    from dev import build_ui_icons as icons
    js = fa.read_part("js/05-ui-icon-map.js")
    mapping = json.loads(js[js.index("{"):js.rindex("}") + 1])
    expected = {emoji: [name.replace("custom:", "_"), tone] for emoji, (name, tone) in icons.EMOJI_ICONS.items()}
    assert mapping == expected, "05-ui-icon-map.js לא מעודכן - הרץ dev/build_ui_icons.py"
    css = fa.read_part("styles/02-icons.css")
    for name in {value[0] for value in mapping.values()}:
        assert f'.ei[data-i="{name}"]' in css, name
    assert os.path.isfile(os.path.join(web_app.BASE_DIR, "assets", "icons", "LICENSE-lucide.txt"))


def test_every_pictographic_emoji_in_the_ui_chrome_has_an_icon():
    js = fa.read_part("js/05-ui-icon-map.js")
    mapping = json.loads(js[js.index("{"):js.rindex("}") + 1])
    pictographic = re.compile("[\U0001F300-\U0001FAFF☀-⛿✀-➿⭐⏩-⏺]")
    unmapped = set()
    for part in fa.page_parts():
        if not part.endswith(".html"):
            continue
        text = re.sub(r"<option[^>]*>.*?</option>", "", fa.read_part(part), flags=re.S)
        for char in pictographic.findall(text):
            if char not in mapping and char != "⭐":
                unmapped.add(char)
    assert not unmapped, f"אימוג'י בלי אייקון - הוסף ל-EMOJI_ICONS ב-dev/build_ui_icons.py: {sorted(unmapped)}"


def test_styleguide_page_uses_the_real_css_and_shows_every_component():
    html = client.get("/styleguide").text
    for part, css in _css_parts():
        assert css in html, part
    for marker in ("btn-primary", "btn-run", "status-pill", "empty-state", "badge", "kbd-combo", 'id="sgIcons"', "uiToast("):
        assert marker in html, marker


def test_history_api_includes_the_structured_result(monkeypatch):
    row = ("video_editor.py", "success", "2026-09-26T10:00:00", 245.0, json.dumps({"files_created": 24, "errors": 0}))
    monkeypatch.setattr(web_app.job_history, "get_recent_jobs", lambda limit=20: [row])
    data = client.get("/api/history").json()
    assert data[0]["result"] == {"files_created": 24, "errors": 0}
    assert data[0]["summary"] == "files_created: 24 | errors: 0"
    monkeypatch.setattr(web_app.job_history, "get_recent_jobs", lambda limit=20: [row[:4] + ("not json",)])
    assert client.get("/api/history").json()[0]["result"] == {}


def test_page_shell_has_rail_topbar_home_and_console_drawer():
    html = fa.assemble_inline_page()
    for marker in ('class="topbar"', 'class="tab-bar nav-rail"', 'id="homePanel"', 'id="consoleDrawer"',
                   'class="brand-mark"', 'onclick="openStudio()"', 'id="veStickyPauseBtn"', 'id="veCatTabs"',
                   'id="veStageEmpty"'):
        assert marker in html, marker
    assert "🎬 ClipForge - Web" not in html  # הכותרת היא הסמל + הטקסט, לא אימוג'י
