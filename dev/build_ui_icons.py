# dev/build_ui_icons.py
#
# גל 16 - מערכת האייקונים של ממשק הדפדפן. האימוג'י שהממשק השתמש בהם כאייקונים
# (כ-860 מופעים, 144 שונים) מוצגים עכשיו כאייקוני SVG חד-צבעיים מסט אחד
# (Lucide, רישיון ISC) שמקבלים את צבע הטקסט. האימוג'י עצמו נשאר בטקסט (חיפוש,
# טסטים, העתקה) - frontend/js/06-ui-core.js עוטף אותו ב-<span class="ei"> והאייקון
# מצויר כ-CSS mask.
#
# הסקריפט קורא את קבצי האייקונים של חבילת lucide-react (אין הורדה - החבילה כבר
# קיימת מקומית בפרויקט אחר, או בנתיב שמועבר ב---lucide-dir / CLIPFORGE_LUCIDE_DIR)
# וכותב שני קבצים שנוצרים אוטומטית ונכנסים ל-git:
#   frontend/styles/02-icons.css   - מסכה לכל אייקון (data URI)
#   frontend/js/05-ui-icon-map.js  - מיפוי אימוג'י -> [אייקון, גוון]
# ומעתיק את רישיון Lucide ל-assets/icons/LICENSE-lucide.txt.
#
#   uv run python dev/build_ui_icons.py [--lucide-dir <node_modules/lucide-react>]

import argparse
import json
import os
import re
import shutil
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(ROOT, "src", "entrypoints", "web", "frontend")
CSS_OUT = os.path.join(FRONTEND, "styles", "02-icons.css")
JS_OUT = os.path.join(FRONTEND, "js", "05-ui-icon-map.js")
LICENSE_OUT = os.path.join(ROOT, "assets", "icons", "LICENSE-lucide.txt")

# 30.10.2026: בלי נתיבים של מחשב מסוים - node_modules/lucide-react בריפו (pnpm add -D lucide-react), או --lucide-dir /
# CLIPFORGE_LUCIDE_DIR לחבילה שכבר מותקנת במקום אחר
DEFAULT_LUCIDE_DIRS = [os.path.join(ROOT, "node_modules", "lucide-react")]

# אימוג'י (בלי FE0F) -> (שם אייקון ב-Lucide או custom:*, גוון או None)
EMOJI_ICONS = {
    "⚠": ("triangle-alert", "warn"), "✅": ("circle-check", "ok"), "❌": ("circle-x", "bad"),
    "▶": ("play", None), "⏸": ("pause", None), "⏺": ("circle-dot", "bad"), "⏭": ("skip-forward", None),
    "⏮": ("skip-back", None), "⏩": ("fast-forward", None), "⏬": ("chevrons-down", None), "⏫": ("chevrons-up", None),
    "🛑": ("circle-stop", "bad"), "⚡": ("zap", None), "🔥": ("flame", "hot"), "⭐": ("star", "star"), "☆": ("star", None),
    "⬇": ("arrow-down", None), "⬆": ("arrow-up", None), "⬅": ("arrow-left", None), "➡": ("arrow-right", None),
    "🖼": ("image", None), "📋": ("clipboard-list", None), "🎬": ("clapperboard", None), "📂": ("folder-open", None),
    "📁": ("folder", None), "🗂": ("folders", None), "🗄": ("archive", None), "↺": ("rotate-ccw", None), "↻": ("rotate-cw", None),
    "⏳": ("hourglass", None), "🔄": ("refresh-cw", None), "🔁": ("repeat", None), "🔂": ("repeat-1", None),
    "🔍": ("search", None), "🔎": ("scan-search", None), "✕": ("x", None), "✖": ("x", None), "✗": ("x", None), "✓": ("check", None),
    "🔊": ("volume-2", None), "🔇": ("volume-x", None), "🎙": ("mic", None), "🎵": ("music", None), "🎚": ("sliders-vertical", None),
    "🎛": ("sliders-horizontal", None), "🌊": ("audio-waveform", None),
    "🏷": ("tag", None), "🧪": ("flask-conical", None), "➕": ("plus", None), "➖": ("minus", None), "🔗": ("link", None),
    "💾": ("save", None), "🗑": ("trash-2", None), "🎯": ("crosshair", None), "✂": ("scissors", None), "📺": ("tv", None),
    "🎨": ("palette", None), "⌨": ("keyboard", None), "🎮": ("gamepad-2", None), "✏": ("pencil", None), "✎": ("pencil", None),
    "↩": ("undo-2", None), "🚀": ("rocket", None), "ℹ": ("info", "info"), "⚙": ("settings", None), "🌙": ("moon", None),
    "☀": ("sun", None), "🌓": ("sun-moon", None), "⏰": ("alarm-clock", None), "📱": ("smartphone", None), "🕒": ("clock-3", None),
    "🕐": ("clock", None), "🕘": ("history", None), "⏱": ("timer", None), "📅": ("calendar", None), "💤": ("bed", None),
    "🔔": ("bell", None), "🔕": ("bell-off", None), "📥": ("import", None), "📤": ("upload", None), "💬": ("message-square", None),
    "📊": ("chart-column", None), "📈": ("trending-up", None), "🌐": ("globe", None), "👤": ("user", None), "👥": ("users", None),
    "📖": ("book-open", None), "📚": ("library", None), "📜": ("scroll-text", None), "📰": ("newspaper", None), "📄": ("file-text", None),
    "📑": ("panels-top-left", None), "📝": ("notebook-pen", None), "💡": ("lightbulb", "star"), "✋": ("hand", None), "👋": ("hand", None),
    "🖥": ("monitor", None), "💻": ("laptop", None), "🖴": ("hard-drive", None), "🖱": ("mouse-pointer-2", None),
    "🔀": ("git-compare", None), "🧬": ("git-fork", None), "🧽": ("eraser", None), "🧹": ("brush-cleaning", None),
    "⛶": ("maximize", None), "🗗": ("minimize-2", None), "☰": ("menu", None), "👁": ("eye", None), "🎞": ("film", None),
    "🎥": ("video", None), "📼": ("cassette-tape", None), "📐": ("ratio", None), "📏": ("ruler", None), "🧩": ("puzzle", None),
    "🔤": ("type", None), "🛟": ("life-buoy", None), "📍": ("map-pin", None), "📌": ("pin", None), "🩺": ("stethoscope", None),
    "🤖": ("bot", None), "🧰": ("wrench", None), "🧲": ("magnet", None), "🌫": ("cloud-fog", None), "☁": ("cloud", None),
    "🌘": ("aperture", None), "📦": ("package", None), "🔐": ("lock-keyhole", None), "🔒": ("lock", None), "🔑": ("key-round", None),
    "♻": ("recycle", None), "🆕": ("badge-plus", None), "🙂": ("smile", None), "👍": ("thumbs-up", None), "✨": ("sparkles", None),
    "🔢": ("list-ordered", None), "🚨": ("siren", "bad"), "💥": ("bomb", "hot"),
    "🏆": ("trophy", "star"), "📡": ("satellite-dish", None), "🛠": ("hammer", None), "🕵": ("scan-eye", None),
    "🎁": ("gift", None), "📸": ("camera", None), "☑": ("square-check", None), "☐": ("square", None),
    # נקודות צבע (צבעי פרופיל, סטטוסים) - נקודה מלאה בצבע המקורי
    "🟢": ("custom:dot", "ok"), "🔴": ("custom:dot", "bad"), "🟠": ("custom:dot", "hot"), "🟡": ("custom:dot", "star"),
    "🔵": ("custom:dot", "info"), "🟣": ("custom:dot", "violet"), "⚪": ("custom:dot", "light"), "⚫": ("custom:dot", "dark"),
    "🟩": ("custom:square", "ok"), "⬛": ("custom:square", "dark"),
}

CUSTOM_SVG = {
    "custom:dot": "<circle cx='12' cy='12' r='6.5' fill='black' stroke='none'/>",
    "custom:square": "<rect x='5' y='5' width='14' height='14' rx='3' fill='black' stroke='none'/>",
}

_NODE_RE = re.compile(r"const __iconNode = (\[.*?\]);\s*const ", re.S)


def find_lucide_dir(cli_value):
    for candidate in [cli_value, os.environ.get("CLIPFORGE_LUCIDE_DIR"), *DEFAULT_LUCIDE_DIRS]:
        if candidate and os.path.isdir(os.path.join(candidate, "dist", "esm", "icons")):
            return candidate
    raise SystemExit("לא נמצאה חבילת lucide-react - העבר --lucide-dir <נתיב ל-node_modules/lucide-react>")


def read_icon_node(lucide_dir, name):
    path = os.path.join(lucide_dir, "dist", "esm", "icons", f"{name}.mjs")
    if not os.path.isfile(path):
        raise SystemExit(f"אייקון לא קיים ב-Lucide: {name}")
    with open(path, encoding="utf-8") as f:
        source = f.read()
    match = _NODE_RE.search(source)
    if not match:
        raise SystemExit(f"פורמט לא צפוי בקובץ האייקון: {path}")
    js_array = match.group(1)
    # מפתחות JS ללא מרכאות -> JSON
    json_text = re.sub(r"([{,]\s*)([A-Za-z][A-Za-z0-9-]*)\s*:", r'\1"\2":', js_array)
    return json.loads(json_text)


def node_to_svg(node):
    parts = []
    for tag, attrs in node:
        attr_text = " ".join(f"{k}='{v}'" for k, v in attrs.items() if k != "key")
        parts.append(f"<{tag} {attr_text}/>")
    return "".join(parts)


def svg_data_uri(inner):
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' "
           "stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>" + inner + "</svg>")
    return "data:image/svg+xml," + urllib.parse.quote(svg, safe=" '=:/.,-")


def build(lucide_dir):
    icon_svgs = {}
    for name, _tone in EMOJI_ICONS.values():
        if name in icon_svgs:
            continue
        icon_svgs[name] = CUSTOM_SVG[name] if name.startswith("custom:") else node_to_svg(read_icon_node(lucide_dir, name))

    css = [
        "  /* נוצר אוטומטית ע\"י dev/build_ui_icons.py - לא לערוך ידנית.",
        "     אייקונים: Lucide (ISC, ראו assets/icons/LICENSE-lucide.txt). */",
        "  @layer components {",
    ]
    for name in sorted(icon_svgs):
        key = name.replace("custom:", "_")
        css.append(f"    .ei[data-i=\"{key}\"] {{ --i: url(\"{svg_data_uri(icon_svgs[name])}\"); }}")
    css.append("  }")

    mapping = {emoji: [name.replace("custom:", "_"), tone] for emoji, (name, tone) in EMOJI_ICONS.items()}
    js = [
        "// נוצר אוטומטית ע\"י dev/build_ui_icons.py - לא לערוך ידנית.",
        "// אימוג'י (בלי FE0F) -> [שם אייקון (data-i), גוון או null]. ראו 06-ui-core.js.",
        "const UI_EMOJI_ICONS = " + json.dumps(mapping, ensure_ascii=False, indent=0).replace("\n", " ") + ";",
        "",
    ]
    with open(CSS_OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(css) + "\n")
    with open(JS_OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(js))
    os.makedirs(os.path.dirname(LICENSE_OUT), exist_ok=True)
    shutil.copyfile(os.path.join(lucide_dir, "LICENSE"), LICENSE_OUT)
    return len(icon_svgs), len(mapping)


def main(argv=None):
    parser = argparse.ArgumentParser(description="בונה את האייקונים של ממשק הדפדפן מ-Lucide")
    parser.add_argument("--lucide-dir", help="נתיב ל-node_modules/lucide-react")
    args = parser.parse_args(argv)
    icons, emoji = build(find_lucide_dir(args.lucide_dir))
    print(f"{icons} אייקונים, {emoji} אימוג'י ממופים -> {os.path.relpath(CSS_OUT, ROOT)}, {os.path.relpath(JS_OUT, ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
