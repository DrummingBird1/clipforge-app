# tests/infra/test_test_hygiene.py
#
# גל 23: טסטים יציבים ומהירים. המתנה עיוורת (page.wait_for_timeout / time.sleep בלולאה)
# גם מאטה את החבילה וגם נכשלת כשמכונת ה-CI איטית - מחכים לתנאי (wait_for_function,
# expect(...), _until/_settle). המונה כאן רק יורד: טסט חדש לא מוסיף המתנות עיוורות.
import os
from tests import TESTS_DIR
import re

MAX_BLIND_BROWSER_WAITS = 8


def _test_sources():
    # כל קובצי ה-py תחת tests/, גם בתיקיות האזורים (tests/<אזור>/) - השם יחסי ל-tests/
    for dirpath, dirnames, filenames in os.walk(TESTS_DIR):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            if name.endswith(".py") and os.path.abspath(path) != os.path.abspath(__file__):
                with open(path, encoding="utf-8") as f:
                    yield os.path.relpath(path, TESTS_DIR).replace(os.sep, "/"), f.read()


def test_blind_browser_waits_only_go_down():
    found = [(name, len(re.findall(r"wait_for_timeout\(", src))) for name, src in _test_sources()]
    found = [(name, count) for name, count in found if count]
    total = sum(count for _name, count in found)
    assert total <= MAX_BLIND_BROWSER_WAITS, (
        f"{total} קריאות wait_for_timeout (מקסימום {MAX_BLIND_BROWSER_WAITS}) - חכה לתנאי במקום: {found}"
    )


def test_xdist_groups_really_apply(pytestconfig, request):
    # גל 23: הסימון נוסף ב-conftest, אבל xdist הופך אותו ל-"@קבוצה" ב-hook משלו - אם שלנו
    # רץ אחריו, הקבוצות לא חלות בשקט וטסטי הרינדור רצים במקביל (נפלו על timeout)
    conftests = [p for p in pytestconfig.pluginmanager.get_plugins()
                 if str(getattr(p, "__file__", "")).endswith(os.path.join("tests", "conftest.py"))]
    assert conftests and conftests[0].pytest_collection_modifyitems.pytest_impl.get("tryfirst")
    if os.environ.get("PYTEST_XDIST_WORKER") and pytestconfig.getvalue("loadgroup"):
        assert request.node.nodeid.endswith("@test_test_hygiene")


def test_every_browser_test_file_is_collected_with_the_browser_marker():
    # conftest מסמן אוטומטית טסט שמשתמש ב-edge_browser; קובץ שמריץ Playwright בעצמו
    # (sync_playwright) בלי הפיקסצ'ר היה רץ בג'וב ה-unit המקבילי ומתנגש בלולאת asyncio
    offenders = [name for name, src in _test_sources()
                 if "sync_playwright()" in src and "edge_browser" not in src and name != "conftest.py"]
    assert offenders == []
