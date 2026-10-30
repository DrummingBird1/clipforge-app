# tests/dataviz/test_dataviz_fix_i18n.py
#
# 23.10.2026, סריקת הבאגים - מנה 7, ב32: בממשק באנגלית שורות השגיאה של עורך הגרפים נשארו בעברית - ההודעות שהשרת מחזיר
# (EpisodeError, {"error": ...}) לא היו ב-en.json, ו-"שגיאה: " + ההודעה לא תורגם בכלל (טסט ה-JS מחליף ${...} ב-"7", אז
# לא ראה את זה). כאן: כל הודעה עברית בשרת של עורך הגרפים מתורגמת עד הסוף, לבד ואחרי "שגיאה: ", באותה לוגיקה כמו בדפדפן.
import ast
import glob
import os

from tests import PROJECT_ROOT
from tests.web.test_web_i18n_dynamic import HEBREW, _translator

SOURCES = ("src/dataviz/web/*.py", "src/dataviz/smart/*.py", "src/entrypoints/web/routes/dataviz.py")


def _text(node):
    """המחרוזת שהשרת מחזיר, עם "7" במקום כל חלק משתנה (כמו בטסט ה-JS), או None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "7" for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _text(node.left), _text(node.right)
        return (left if left is not None else "7") + (right if right is not None else "7") if left or right else None
    return None


def server_messages():
    found = set()
    for pattern in SOURCES:
        for path in glob.glob(os.path.join(PROJECT_ROOT, pattern)):
            for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
                values = []
                if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in ("EpisodeError", "HTTPException") and node.args:
                    values.append(node.args[0])
                if isinstance(node, ast.Dict):
                    values += [v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant) and k.value == "error"]
                for value in values:
                    text = _text(value)
                    if text and HEBREW.search(text):
                        found.add(text)
    return sorted(found)


def test_every_dataviz_server_message_translates_alone_and_after_the_error_prefix():
    messages = server_messages()
    assert len(messages) > 150                                                 # החילוץ באמת מצא את ההודעות
    translator = _translator()
    missing = []
    for message in messages:
        for text in (message, "שגיאה: " + message):
            out = translator.translate(text)
            if out is None or HEBREW.search(out):
                missing.append(f"{text!r} -> {out!r}")
    assert missing == [], f"{len(missing)} בלי תרגום:\n" + "\n".join(missing[:20])   # קודם: מאות


def test_the_error_prefix_and_a_known_message():
    translator = _translator()
    assert translator.translate("שגיאה: הפרק לא נמצא.") == "Error: The episode was not found."
    assert translator.translate("כבר קיים פרק בשם 'medals' - בחר שם אחר.") == "An episode named 'medals' already exists - choose another name."
    assert translator.translate("⚠️ שגיאה: ההורדה נכשלה: timeout") == "⚠️ Error: The download failed: timeout"
