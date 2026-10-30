# entrypoints/web/frontend_assembly.py
#
# גל 11 (סידור הארכיטקטורה): הדף של ממשק הדפדפן היה מחרוזת אחת של ~10,700 שורות
# בתוך web_app.py. עכשיו הוא יושב בקבצים אמיתיים תחת frontend/ - HTML לפי אזור,
# CSS, ו-JS לפי תחום - והקובץ הזה מדביק אותם בסדר שב-frontend/parts.txt: ה-HTML לדף
# אחד, וה-CSS וה-JS (גל 24) לשני bundles שהדף מפנה אליהם.
#
# בכוונה בלי build step ובלי ES modules: כל ה-HTML קורא לפונקציות גלובליות
# (onclick="..."), וקבצי ה-JS הם סקריפטים קלאסיים שחולקים scope גלובלי אחד - ה-bundle
# הוא פשוט ההדבקה שלהם לפי הסדר, והפיצול לא משנה שום התנהגות.
# ההרכבה קורית פעם אחת בטעינה; CLIPFORGE_DEV_RELOAD_PAGE=1 מרכיב מחדש בכל בקשה
# (עריכת קובץ JS/CSS ורענון הדפדפן, בלי להפעיל מחדש את השרת).

import gzip
import hashlib
import json
import os
import re
from typing import Dict, List, Tuple

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
PARTS_FILE = os.path.join(FRONTEND_DIR, "parts.txt")
STYLEGUIDE_BODY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "styleguide_body.html")


def page_parts() -> List[str]:
    """הקבצים של הדף, בסדר ההרכבה (שורות ריקות והערות # מדולגות)."""
    with open(PARTS_FILE, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.lstrip().startswith("#")]


def read_part(relative_path: str) -> str:
    with open(os.path.join(FRONTEND_DIR, *relative_path.split("/")), encoding="utf-8") as f:
        return f.read()  # universal newlines - CRLF מ-git בווינדוס הופך ל-\n, זהה בכל מערכת


# גל 24: ה-CSS וה-JS לא בתוך הדף אלא כשני קבצים סטטיים עם hash של התוכן בשם
# (/static/app.<hash>.css|js), שנשמרים ב-cache של הדפדפן לתמיד (immutable) ונשלחים
# דחוסים. קודם כל טעינה שלחה דף של כ-1MB; עכשיו טעינה חוזרת מביאה רק את ה-HTML
# (כ-34KB דחוס), וכל שינוי בקוד מייצר שם חדש - אין מצב של JS ישן מול HTML חדש.
ASSET_PLACEHOLDERS = {"css": "{{APP_CSS}}", "js": "{{APP_JS}}"}
ASSET_MEDIA_TYPES = {"css": "text/css; charset=utf-8", "js": "application/javascript; charset=utf-8"}
_BUNDLE_PREFIX = {"css": "styles/", "js": "js/"}
_INLINE_TAGS = {
    "css": ('<link rel="stylesheet" href="{{APP_CSS}}">\n', "<style>\n", "</style>\n"),
    "js": ('<script src="{{APP_JS}}"></script>\n', "<script>\n", "</script>\n"),
}


# גל 38: קוד של מסך שלם שנטען רק כשפותחים אותו. הקבצים נשארים ב-parts.txt (סדר, טסטים, תרגום) אבל
# לא נכנסים ל-bundle הראשי - הם bundle משלהם (/static/<שם>.<hash>.js), והדף טוען אותו ב-uiLoadLazy
# (06-ui-core.js) כשעוברים למסך. ה-bundle הראשי מתחיל במפה של הכתובות (UI_LAZY_BUNDLES).
LAZY_JS: Dict[str, Tuple[str, ...]] = {
    "dataviz": ("js/41-dataviz-packages.js", "js/42-dataviz-screen.js", "js/43-dataviz-studio.js", "js/44-dataviz-editor.js"),
    # גל 50: הכלים הנוספים של עורך הגרפים - bundle שני (הראשון קרוב לתקרה), נטען מיד אחריו (20-app-shell.js).
    # סבב הייצוב (16.10): גם המדריך, המפות והקריינות (47) - נפתחים לעתים רחוקות, ומפנים מקום ב-bundle הראשון.
    # 19.10.2026: לפי נושא - כל נושא בקובץ אחד וב-bundle אחד: העורך (44) בראשון; המראה (83), הנתונים (84) והפרסום (86) בשני
    "dataviz_pro": ("js/82-dataviz-story.js", "js/83-dataviz-look.js", "js/84-dataviz-data.js", "js/87-dataviz-shell.js"),
    # 20.10.2026: bundle שלישי - ההפקה: המדריך, המפות והקריינות (47), תור הפרקים והצפיות (49) והפרסום (86). נטען מיד אחרי
    # dataviz_pro, וכך לכל bundle יש מקום לפיצ'רים חדשים בלי להעלות תקרה
    # 21.10.2026: גם הכלים, רמת הפירוט וההיכרות של סבב הפישוט (88) - dataviz_pro הגיע לרווח שהטסט שומר
    "dataviz_tools": ("js/47-dataviz-engine.js", "js/49-dataviz-queue-stats.js", "js/86-dataviz-publish.js", "js/88-dataviz-simple.js"),
    # 27.10.2026: bundle רביעי - 25 ההצעות מהבדיקה הטכנית (עריכה על התצוגה, מצב במאי, דגלים, ציון ועוד). עוטף את שלושת
    # הקודמים, אז נטען אחריהם
    "dataviz_plus": ("js/85-dataviz-plus.js",),
    # 23.10.2026: ההגדרות הכלליות (הגדרות, גישה מהטלפון, צימוד מכשיר, תיקיית ייצוא) - נטען כשפותחים את המסך (switchTab)
    "settings": ("js/31-global-settings.js",),
    # 23.10.2026: מסך "תוצרים" - כל הסרטונים שהכלים ייצרו (גם ה-HTML שלו, lazy-html:outputs)
    "outputs": ("js/33-outputs-screen.js",),
    # 23.10.2026: מרכז ההתראות - הרשימה נטענת בלחיצה על 📥 (גם ה-HTML שלה, lazy-html:notifications). בראשי רק המונה
    "notifications": ("js/34-notification-center.js",),
    # 23.10.2026: רכיבי מסגרת משותפים - המפריד הנגרר (uiSplitter) וחלונית "נפתחו לאחרונה" (uiRecent עצמו בראשי)
    "frame": ("js/35-ui-frame.js",),
    # 23.10.2026: מסך "📱 בטלפון" - מה רץ, התור, אישור קליפים והרצה חוזרת (גם ה-HTML שלו, lazy-html:phone)
    "phone": ("js/36-phone-screen.js",),
    # 24.10.2026: תוספות לסטודיו מסיור השימושיות (בחירת תיקייה ועוד) - נטען כשהסטודיו נפתח (setVeFocus), כדי לא להגדיל את הראשי
    "studio_more": ("js/89-studio-more.js",),
}
# גל 39: גם ה-CSS של המסך - נכנס ל-bundle של ה-JS שלו, ונוסף לדף (<style>) כשהוא נטען
LAZY_CSS: Dict[str, Tuple[str, ...]] = {
    "dataviz": ("styles/17-dataviz.css",),
    "dataviz_pro": ("styles/27-dataviz-pro.css",),
    "dataviz_plus": ("styles/28-dataviz-plus.css",),
    "outputs": ("styles/33-outputs.css",),
    "notifications": ("styles/34-notifications.css",),
    "frame": ("styles/35-ui-frame.css",),
    "phone": ("styles/36-phone.css",),
    "studio_more": ("styles/89-studio-more.css",),
}


# סבב ייצוב (16.10.2026): גם ה-HTML של מסך או חלון שנפתחים רק לפעמים. האזור מסומן בקובץ ה-HTML עצמו
# (<!-- lazy-html:<שם> --> ... <!-- /lazy-html:<שם> -->), כך שהתוכן, הסדר וה-id לא זזים: הדף המלא של הטסטים
# כולל אותו כמו שהוא, ובדף שהשרת מגיש במקומו יש רק <template data-lazy-html="<שם>"> ריק. התוכן הוא bundle
# משלו (<שם>_html.<hash>.js), ו-uiLoadLazy(<שם>) טוען אותו לפני ה-JS של המסך - ה-JS מוצא את האלמנטים כמו קודם.
# השם הוא של מסך מ-LAZY_JS (שם נטען ה-HTML), ומי שמשפר חלונות בטעינת הדף מאזין ל-"ui:lazy-html".
_LAZY_HTML_RE = re.compile(r"[ \t]*<!-- lazy-html:([a-z_]+) -->\n(.*?)[ \t]*<!-- /lazy-html:\1 -->\n", re.S)


def _lazy_parts() -> set:
    return {part for group in (LAZY_JS, LAZY_CSS) for parts in group.values() for part in parts}


def lazy_html_fragments(name: str) -> List[str]:
    """הקטעים המסומנים של מסך, בסדר שלהם בדף."""
    return [m.group(2) for m in _LAZY_HTML_RE.finditer(_html_shell()) if m.group(1) == name]


def lazy_html_names() -> List[str]:
    return sorted({m.group(1) for m in _LAZY_HTML_RE.finditer(_html_shell())})


def lazy_html_bundle(name: str) -> str:
    """JS ששם כל קטע במקום ה-<template> שלו (לפי הסדר), ומודיע למי שמשפר חלונות וטפסים בטעינת הדף."""
    return (
        "(() => {\n"
        "  const html = " + json.dumps(lazy_html_fragments(name), ensure_ascii=False) + ";\n"
        "  const nodes = [];\n"
        "  document.querySelectorAll(" + json.dumps(f'template[data-lazy-html="{name}"]') + ").forEach((slot, i) => {\n"
        "    const t = document.createElement(\"template\");\n"
        "    t.innerHTML = html[i];\n"
        "    nodes.push(...t.content.children);\n"
        "    slot.replaceWith(t.content);\n"
        "  });\n"
        "  uiBus.emit(\"ui:lazy-html\", {name: " + json.dumps(name) + ", nodes});\n"
        "})();\n"
    )


def lazy_css(name: str) -> str:
    return "".join(read_part(part) for part in page_parts() if part in LAZY_CSS.get(name, ()))


def lazy_bundle(name: str) -> str:
    """הקבצים של מסך שנטען לפי דרישה, בסדר של parts.txt: קודם ה-CSS שלו (כ-<style>), אחר כך ה-JS,
    ובסוף סימון שהוא נטען (לא לטעון פעמיים)."""
    css = lazy_css(name)
    style = ("(() => { const s = document.createElement('style'); s.dataset.lazy = " + json.dumps(name)
             + "; s.textContent = " + json.dumps(css, ensure_ascii=False) + "; document.head.appendChild(s); })();\n") if css else ""
    body = "".join(read_part(part) for part in page_parts() if part in LAZY_JS[name])
    return style + body + f"window.__uiLazyLoaded = Object.assign(window.__uiLazyLoaded || {{}}, {{{json.dumps(name)}: true}});\n"


def lazy_asset_name(name: str, content: str) -> str:
    return f"{name}.{hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]}.js"


def _lazy_manifest() -> str:
    urls = {name: "/static/" + lazy_asset_name(name, lazy_bundle(name)) for name in LAZY_JS}
    for name in lazy_html_names():
        urls[name + ":html"] = "/static/" + lazy_asset_name(name + "_html", lazy_html_bundle(name))
    return "// גל 38: bundles שנטענים לפי דרישה (uiLoadLazy)\nconst UI_LAZY_BUNDLES = " + json.dumps(urls) + ";\n"


def bundle(kind: str) -> str:
    """כל קבצי ה-CSS (kind="css") או ה-JS (kind="js") של הדף, בסדר של parts.txt - בלי המסכים שנטענים לפי דרישה."""
    lazy = _lazy_parts()
    content = "".join(read_part(part) for part in page_parts() if part.startswith(_BUNDLE_PREFIX[kind]) and part not in lazy)
    return _lazy_manifest() + content if kind == "js" else content


def asset_name(kind: str, content: str) -> str:
    return f"app.{hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]}.{kind}"


def _html_shell() -> str:
    return "".join(read_part(part) for part in page_parts() if part.startswith("html/"))


def assemble_page() -> str:
    """ה-HTML שהשרת מגיש: הדף עם קישורים ל-bundles של ה-CSS וה-JS, ובלי הקטעים שנטענים לפי דרישה."""
    html = _LAZY_HTML_RE.sub(lambda m: f'<template data-lazy-html="{m.group(1)}"></template>\n', _html_shell())
    for kind, placeholder in ASSET_PLACEHOLDERS.items():
        html = html.replace(placeholder, "/static/" + asset_name(kind, bundle(kind)))
    return html


def assemble_inline_page() -> str:
    """הדף כמסמך אחד, עם ה-CSS וה-JS בפנים (כמו לפני גל 24) - לבדיקות על התוכן כולו."""
    html = _html_shell()
    for kind, (tag, open_tag, close_tag) in _INLINE_TAGS.items():
        lazy = LAZY_JS if kind == "js" else LAZY_CSS
        content = bundle(kind) + "".join((lazy_bundle if kind == "js" else lazy_css)(name) for name in lazy)
        html = html.replace(tag, open_tag + content + close_tag)
    return html


def build_assets() -> Dict[str, Dict[str, object]]:
    """{שם-קובץ: {body, gzip, media_type}} לשני ה-bundles - נבנה פעם אחת בטעינה (הדחיסה
    מראש, לא בכל בקשה). mtime=0 בדחיסה - אותו תוכן, אותם בייטים."""
    assets: Dict[str, Dict[str, object]] = {}
    for kind in ASSET_PLACEHOLDERS:
        content = bundle(kind)
        body = content.encode("utf-8")
        assets[asset_name(kind, content)] = {"body": body, "gzip": gzip.compress(body, 9, mtime=0), "media_type": ASSET_MEDIA_TYPES[kind]}
    lazy = [(name, lazy_bundle(name)) for name in LAZY_JS] + [(name + "_html", lazy_html_bundle(name)) for name in lazy_html_names()]
    for name, content in lazy:
        body = content.encode("utf-8")
        assets[lazy_asset_name(name, content)] = {"body": body, "gzip": gzip.compress(body, 9, mtime=0), "media_type": ASSET_MEDIA_TYPES["js"], "lazy": True}
    return assets


def js_parts() -> List[Tuple[str, str]]:
    """(נתיב, תוכן) של כל קובץ JS בדף - לבדיקות תחביר ולכלי פיתוח."""
    return [(part, read_part(part)) for part in page_parts() if part.endswith(".js")]


def dev_reload_enabled() -> bool:
    return os.environ.get("CLIPFORGE_DEV_RELOAD_PAGE") == "1"


def assemble_styleguide() -> str:
    """גל 15: עמוד /styleguide - אותו CSS בדיוק כמו הדף (כל קבצי styles/ לפי הסדר),
    ליבת האייקונים/ההודעות, ותצוגה של כל רכיב ו-token. רפרנס חי למערכת העיצוב."""
    css = "".join(read_part(part) for part in page_parts() if part.startswith("styles/"))
    core_js = read_part("js/05-ui-icon-map.js") + read_part("js/06-ui-core.js")
    with open(STYLEGUIDE_BODY, encoding="utf-8") as f:
        body = f.read()
    parts = [
        '<!doctype html>\n<html lang="he" dir="rtl">\n<head>\n<meta charset="utf-8">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>ClipForge - Styleguide</title>\n<style>\n',
        css,
        '</style>\n</head>\n<body class="styleguide">\n<script>\n',
        core_js,
        '</script>\n',
        body,
        '</body>\n</html>\n',
    ]
    return "".join(parts)
