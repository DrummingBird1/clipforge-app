# tests/web/test_web_i18n_dynamic.py
#
# גל 23: כיסוי התרגום לאנגלית גם לטקסט ש-JS כותב בזמן ריצה (הודעות, תוויות, אישורים),
# לא רק ל-HTML הסטטי (test_web_accessibility.py). הטסט מחלץ כל מחרוזת/תבנית מקוד ה-JS,
# מריץ עליה את אותה לוגיקת תרגום כמו 69-ui-prefs.js (מדויק / נקודתיים / מפרידים /
# תבניות), ונכשל על כל טקסט עברי שנשאר בלי תרגום. ${...} מוחלף ב-"7" לצורך הבדיקה.
#
# ובנוסף: שום לוגיקה לא נשענת על טקסט UI עברי (title/aria-label/textContent) - בממשק
# האנגלי הטקסט הזה מתורגם, ושכבות/בוט/השהיה הפסיקו לעבוד (נמצא בגל 23).
import json
import os
import re


from entrypoints.web import frontend_assembly as fa

I18N_PATH = os.path.join(os.path.dirname(fa.FRONTEND_DIR), "i18n", "en.json")
HEBREW = re.compile("[%s-%s]" % (chr(0x0590), chr(0x05FF)))
_SYMBOL_RANGES = [(0x1F000, 0x1FAFF), (0x2190, 0x21FF), (0x2300, 0x23FF), (0x25A0, 0x25FF), (0x2600, 0x27BF), (0x27F0, 0x27FF), (0x2B00, 0x2BFF)]
_SYMBOLS = "".join(f"{chr(a)}-{chr(b)}" for a, b in _SYMBOL_RANGES) + chr(0xFE0F) + chr(0x200D)
LEAD = re.compile(r"^[\s" + chr(0xB7) + _SYMBOLS + "]*")
TRAIL = re.compile(r"[\s" + _SYMBOLS + "]*$")
SPLITTERS = [re.compile(r"(\s*\n\s*)"), re.compile("( " + chr(0xB7) + " )"), re.compile("( - )"), re.compile("( / )"),
             re.compile(r"(\s*[" + _SYMBOLS + r"]+\s*)")]


# --- חילוץ מחרוזות מ-JS (הערות ו-regex מדולגים, תבניות מקוננות נקראות נכון) ---

_REGEX_BEFORE = set("(,=:[!&|?{};+-*%<>~^")


def _read_string(src, i):
    quote, j, n = src[i], i + 1, len(src)
    buf = []
    while j < n and src[j] != quote and src[j] != "\n":
        if src[j] == "\\":
            buf.append(src[j:j + 2])
            j += 2
            continue
        buf.append(src[j])
        j += 1
    return j + 1, "".join(buf)


def _skip_regex(src, i):
    j, n, in_class = i + 1, len(src), False
    while j < n and src[j] != "\n":
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            break
        j += 1
    j += 1
    while j < n and src[j].isalpha():
        j += 1
    return j


def _read_template(src, i, out):
    n, j = len(src), i + 1
    text = []
    while j < n:
        ch = src[j]
        if ch == "\\":
            text.append(src[j:j + 2])
            j += 2
            continue
        if ch == "`":
            return j + 1, "".join(text)
        if src.startswith("${", j):
            j = _scan(src, j + 2, out, stop_at_brace=True)
            text.append("7")
            continue
        text.append(ch)
        j += 1
    return n, "".join(text)


def _scan(src, i, out, stop_at_brace=False):
    n, prev, depth = len(src), "", 0
    while i < n:
        ch = src[i]
        if src.startswith("//", i):
            end = src.find("\n", i)
            i = n if end < 0 else end
            continue
        if src.startswith("/*", i):
            end = src.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if ch in "'\"":
            i, text = _read_string(src, i)
            out.append(text)
            prev = ch
            continue
        if ch == "`":
            i, text = _read_template(src, i, out)
            out.append(text)
            prev = "`"
            continue
        if ch == "/" and (prev == "" or prev in _REGEX_BEFORE):
            i = _skip_regex(src, i)
            prev = "/"
            continue
        if stop_at_brace:
            if ch == "{":
                depth += 1
            elif ch == "}":
                if depth == 0:
                    return i + 1
                depth -= 1
        if not ch.isspace():
            prev = ch
        i += 1
    return n


def js_literals(src):
    out = []
    _scan(src, 0, out)
    return out


# --- אותה לוגיקת תרגום כמו uiTranslate ב-69-ui-prefs.js ---

class _Translator:
    def __init__(self, data):
        self.exact = data["exact"]
        self.patterns = [(re.compile(src), re.sub(r"\$(\d)", r"\\\1", rep)) for src, rep in data["patterns"]]

    def translate(self, text):
        if not HEBREW.search(text):
            return None
        lead = LEAD.match(text).group(0)
        rest = text[len(lead):]
        trail = TRAIL.search(rest).group(0)
        core = rest[:len(rest) - len(trail)] if trail else rest
        out = self._core(core)
        return None if out is None else lead + out + trail

    def _parts(self, text):
        for splitter in SPLITTERS:
            parts = splitter.split(text)
            if len(parts) < 3:
                continue
            done = [p if (i % 2 or not HEBREW.search(p)) else self.translate(p) for i, p in enumerate(parts)]
            if all(p is not None for p in done):
                return "".join(done)
        return None

    def _core(self, core):
        if not core:
            return None
        if core in self.exact:
            return self.exact[core]
        if core + ":" in self.exact:
            return re.sub(r":\s*$", "", self.exact[core + ":"])
        parts = self._parts(core)
        if parts is not None:
            return parts
        out = core
        for pattern, replacement in self.patterns:
            out = pattern.sub(replacement, out)
        if out == core:
            return None
        if HEBREW.search(out):
            again = self._parts(out)
            return again if again is not None else out
        return out


def _translator():
    with open(I18N_PATH, encoding="utf-8") as f:
        return _Translator(json.load(f))


def _js_parts():
    return [(part, fa.read_part(part)) for part in fa.page_parts() if part.endswith(".js")]


def test_the_extractor_reads_nested_templates_regexes_and_comments():
    src = 'a = `x ${b ? "שלום" : `y ${c}`} z`; // "הערה"\nd = s.replace(/"/g, ""); e = "טקסט";'
    assert js_literals(src) == ["שלום", "y 7", "x 7 z", "", "טקסט"]


def test_the_translator_mirrors_the_runtime_logic():
    t = _Translator({"exact": {"שלום": "Hello", "שם:": "Name:"}, "patterns": [[r"^(.*?) קבצים$", "$1 files"]]})
    assert t.translate("👋 שלום") == "👋 Hello"
    assert t.translate("שם") == "Name"
    assert t.translate("שלום · 3 קבצים") == "Hello · 3 files"
    assert t.translate("לא ידוע") is None


def test_the_open_end_of_a_layer_time_range_is_translated():
    # 8.11.2026: שורת שכבה בלי זמן סיום מציגה "0:00–סוף" - טקסט מורכב שאין לו מפתח, והעברית נשארה בממשק האנגלי
    t = _translator()
    assert t.translate("0:00–סוף") == "0:00–End"
    assert t.translate("0:02.5–סוף") == "0:02.5–End"
    assert t.translate("0:02–0:04.5") is None   # טווח סגור - אין בו עברית בכלל


def test_every_hebrew_string_in_the_js_translates_to_english():
    translator = _translator()
    missing = []
    for part, source in _js_parts():
        for literal in js_literals(source):
            if not HEBREW.search(literal):
                continue
            for segment in re.split(r"<[^>]*>", literal):  # HTML בתוך מחרוזת: הטקסט בין התגיות
                sample = segment.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
                if not HEBREW.search(sample):
                    continue
                out = translator.translate(sample)
                if out is None or HEBREW.search(out):
                    missing.append(f"{part}: {sample[:90]!r} -> {out!r}")
    assert missing == [], f"{len(missing)} מחרוזות בלי תרגום ב-web/i18n/en.json (exact או תבנית):\n" + "\n".join(missing[:25])


def test_no_logic_depends_on_hebrew_ui_text():
    he = "[" + chr(0x0590) + "-" + chr(0x05FF) + "]"
    rules = [
        r"\[(title|aria-label|placeholder)[*^$~|]?=['\"][^'\"]*" + he,
        r"\.(title|placeholder|textContent|innerText)\s*={2,3}\s*[\"'`][^\"'`]*" + he,
        r"getAttribute\([\"'](title|aria-label|placeholder)[\"']\)\s*={2,3}\s*[\"'`][^\"'`]*" + he,
        r"(textContent|innerText|title)(\.trim\(\))?\.(includes|startsWith|endsWith)\([\"'`][^\"'`]*" + he,
        r"/[^/\n]*" + he + r"[^/\n]*/[gimsuy]*\.test\([\w.]*(textContent|innerText|title)",
    ]
    offenders = []
    for part, source in _js_parts():
        for number, line in enumerate(source.splitlines(), 1):
            if line.lstrip().startswith("//"):
                continue
            for rule in rules:
                if re.search(rule, line) and "Close|Cancel" not in line:
                    offenders.append(f"{part}:{number}: {line.strip()[:100]}")
                    break
    assert offenders == [], "לוגיקה שנשענת על טקסט UI עברי - בממשק האנגלי הוא מתורגם; השתמש ב-data-* או במצב:\n" + "\n".join(offenders)
