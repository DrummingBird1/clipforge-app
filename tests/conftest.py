# tests/conftest.py
#
# יצירת/הריסת ctk.CTk() (Tk root) חוזרת בתוך אותו תהליך פייתון - כל קובץ
# טסט שיוצר root משלו - יכולה לגרום ל-TclError חולף שלא קשור בכלל להתקנת Tk
# בפועל (אומת בפועל: "tk wasn't installed properly", "invalid command name
# tcl_findLibrary" - שתי שגיאות שונות על אותה תופעה, תלוית-תזמון). root אחד
# משותף ל-session שלם (לא מוצג - withdraw) מסיר את זה מהשורש: כל טסט שצריך
# widget אמיתי מקבל אותו כ-parent ובונה/הורס רק את ה-widget שלו, לא root חדש.
import os
import re
import shutil
import sys
import tempfile

# סבב ייצוב: גם workspace/ - תיקייה זמנית אחת לכל הריצה, כמו data/ למטה. בלי זה ריצות מלאות השאירו ב-workspace/ של
# המשתמש מאות קבצים (.run_manifests, .previews, .layers, canary.mp4, _sig...). web_app, utils/workspace_dir והסקריפטים
# (video_editor, dataviz_maker - תתי-תהליכים שיורשים את הסביבה) קוראים את CLIPFORGE_WORKSPACE_DIR בייבוא. נקבע כאן, לפני
# שקובץ טסט כלשהו מייבא מ-src/, תמיד מחדש בתהליך הראשי (גם משתנה שנשאר מהרצה ידנית מוחלף), ו-workers של xdist יורשים
# אותו - כך השרת והסקריפטים תמיד באותה תיקייה. טסט שצריך workspace משלו מגדיר אותו בעצמו (monkeypatch).
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REAL_WORKSPACE_DIR = os.path.join(_PROJECT_DIR, "workspace")
_OWNED_TEST_WORKSPACE_DIR = None
if not (os.environ.get("PYTEST_XDIST_WORKER") and os.environ.get("CLIPFORGE_WORKSPACE_DIR")):
    _OWNED_TEST_WORKSPACE_DIR = tempfile.mkdtemp(prefix="clipforge_test_workspace_")
    os.environ["CLIPFORGE_WORKSPACE_DIR"] = _OWNED_TEST_WORKSPACE_DIR


def _real_workspace_snapshot():
    """{נתיב יחסי: (גודל, mtime)} של כל קובץ ב-workspace/ האמיתי - בלי לקרוא תוכן (שם יש סרטונים גדולים)."""
    snapshot = {}
    for dirpath, _dirnames, filenames in os.walk(_REAL_WORKSPACE_DIR):
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            snapshot[os.path.relpath(path, _REAL_WORKSPACE_DIR)] = (st.st_size, st.st_mtime_ns)
    return snapshot


# שמירה: התהליך הראשי מצלם את workspace/ האמיתי לפני הריצה ובודק בסוף שאף טסט לא יצר, שינה או מחק שם קובץ
_REAL_WORKSPACE_BEFORE = _real_workspace_snapshot() if _OWNED_TEST_WORKSPACE_DIR else None

# data/ היא נתוני-משתמש אמיתיים בלי גיבוי (מונה Rocket, scheduler_state, ה-DB, מטמון ffprobe,
# לוגים...) - וכל הנתיבים אליה נגזרים מ-utils/shared/data_dir.py, שמכבד CLIPFORGE_DATA_DIR. מוגדר כאן,
# ברמת המודול - לפני שקובץ טסט כלשהו מייבא מודול מ-src/ - לתיקייה זמנית אחת לכל הריצה: גם קוד
# שרץ בתוך תהליך הטסט וגם תתי-תהליכים שטסטים מריצים (video_editor.py, סקריפטים דרך worker -
# יורשים את הסביבה) כותבים לשם, לעולם לא ל-data/ האמיתית (קודם הם כתבו: טסטי הקנרית דרסו את
# scheduler_state.json, טסטי טאב Rocket את counter.txt, ועוד). worker של xdist יורש את התיקייה
# מהתהליך הראשי (שיצר אותה לפני שהפעיל אותו) - תיקייה אחת משותפת לכל ה-workers, בדיוק כמו
# data/ עצמה (מנעול הרינדור חוצה-התהליכים, data/render.lock, ממשיך לתאם ביניהם).
_OWNED_TEST_DATA_DIR = None
if not (os.environ.get("PYTEST_XDIST_WORKER") and os.environ.get("CLIPFORGE_DATA_DIR")):
    _OWNED_TEST_DATA_DIR = tempfile.mkdtemp(prefix="clipforge_test_data_")
    os.environ["CLIPFORGE_DATA_DIR"] = _OWNED_TEST_DATA_DIR
# 24.10.2026 (זמן הטסטים): workspace ו-data/ לכל worker של xdist - תת-תיקייה של התיקייה של הריצה (התהליך הראשי מוחק את
# שתיהן בסוף). כך קבצי רינדור עם אותו שם (good_edited_horizontal.mp4) ומנעול הרינדור (data/render.lock) לא משותפים בין
# workers, וקבצי הרינדור לא צריכים לרוץ בזה אחר זה בקבוצת xdist אחת (623 מתוך ~670 שניות של ריצת unit). רק בטסטים: האפליקציה
# כבר מכבדת את שני המשתנים, והמנעול בה לא משתנה. טסטי utils/shared/render_lock בודקים מנעול משותף בתוך הטסט (tmp_path).
_XDIST_WORKER = os.environ.get("PYTEST_XDIST_WORKER")
if _XDIST_WORKER:
    for _env in ("CLIPFORGE_WORKSPACE_DIR", "CLIPFORGE_DATA_DIR"):
        if os.path.basename(os.path.normpath(os.environ[_env])) != _XDIST_WORKER:
            os.environ[_env] = os.path.join(os.environ[_env], _XDIST_WORKER)
            os.makedirs(os.environ[_env], exist_ok=True)
# תיקיית הייצוא (utils/shared/export_dir.py): ההגדרה יושבת ב-data/ הזמנית, ומשתנה שנשאר בסביבה מהרצה ידנית לא נכנס -
# אף טסט לא כותב לתיקייה שהמשתמש בחר; התוצרים בטסטים ב-workspace הזמני, כמו קודם
os.environ.pop("CLIPFORGE_EXPORT_DIR", None)
# utils/bot/wake_timer: אף פעם לא משימה אמיתית ב-Task Scheduler מטסט (גם בתתי-תהליכים, שיורשים את הסביבה)
os.environ["CLIPFORGE_NO_SCHTASKS"] = "1"

# 23.10.2026: טסט לא יוצא לרשת - רק loopback (tests/network_guard/clipforge_test_network_guard.py). כאן, לפני שקובץ טסט כלשהו
# מייבא מ-src/: השמירה בתהליך הזה, והתיקייה ב-PYTHONPATH כדי ש-sitecustomize שלה יתקין אותה בכל תהליך פייתון שיורש את
# הסביבה (workers של xdist, השרת והסקריפטים שטסטים מריצים). הדפדפן - edge_browser למטה.
_NETWORK_GUARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "network_guard")
if _NETWORK_GUARD_DIR not in sys.path:
    sys.path.insert(0, _NETWORK_GUARD_DIR)
import clipforge_test_network_guard as network_guard

os.environ[network_guard.ENV_FLAG] = "1"
if _NETWORK_GUARD_DIR not in os.environ.get("PYTHONPATH", "").split(os.pathsep):
    os.environ["PYTHONPATH"] = os.pathsep.join(p for p in (_NETWORK_GUARD_DIR, os.environ.get("PYTHONPATH")) if p)
network_guard.install()


def pytest_sessionfinish(session, exitstatus):
    if _REAL_WORKSPACE_BEFORE is None:
        return
    after = _real_workspace_snapshot()
    changed = sorted(rel for rel in _REAL_WORKSPACE_BEFORE.keys() | after.keys() if _REAL_WORKSPACE_BEFORE.get(rel) != after.get(rel))
    if not changed:
        return
    # הריצה נכשלת גם כשכל הטסטים עברו: מישהו כתב ל-workspace/ של המשתמש (נתיב שלא נגזר מ-CLIPFORGE_WORKSPACE_DIR)
    session.exitstatus = pytest.ExitCode.TESTS_FAILED
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    lines = [f"טסטים שינו {len(changed)} קבצים ב-workspace/ האמיתי ({_REAL_WORKSPACE_DIR}) - נתיב שלא עובר דרך CLIPFORGE_WORKSPACE_DIR:"]
    lines += [f"  {rel}" for rel in changed[:40]] + ([f"  ... ועוד {len(changed) - 40}"] if len(changed) > 40 else [])
    if reporter is not None:
        reporter.write_line("\n".join(lines), red=True, bold=True)


def pytest_unconfigure(config):
    if _OWNED_TEST_WORKSPACE_DIR:
        shutil.rmtree(_OWNED_TEST_WORKSPACE_DIR, ignore_errors=True)
    if not _OWNED_TEST_DATA_DIR:
        return
    # Windows לא מוחק קובץ פתוח: לוגי ה-RotatingFileHandler (utils/shared/logging_setup.py) פתוחים עד סוף
    # התהליך, וחיבור sqlite3 (utils/shared/db.py - "with" רק עושה commit) נסגר רק באיסוף-זבל.
    import gc
    import logging
    gc.collect()
    owned = os.path.normcase(_OWNED_TEST_DATA_DIR)
    for logger in list(logging.Logger.manager.loggerDict.values()):
        for handler in list(getattr(logger, "handlers", ())):
            if os.path.normcase(getattr(handler, "baseFilename", "")).startswith(owned):
                logger.removeHandler(handler)
                handler.close()
    shutil.rmtree(_OWNED_TEST_DATA_DIR, ignore_errors=True)


# קוד המקור הראשוני (cogs/ui/utils/entrypoints/scripts) יושב תחת src/, לא בשורש הפרויקט עצמו. pythonpath
# ב-pyproject.toml כבר מכניס את השורש ואת src/ ל-sys.path; כאן שוב, למקרה של pytest שמורץ עם קובץ הגדרות אחר.
# קובץ טסט לא מוסיף נתיבים בעצמו - נתיבים לקבצים בריפו דרך tests.PROJECT_ROOT / tests.TESTS_DIR (tests/__init__.py).
_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import customtkinter as ctk
import pytest
from hypothesis import configuration as _hypothesis_configuration

# בלי זה hypothesis יוצר .hypothesis/ בשורש הפרויקט - מאחד אותו עם שאר
# תיקיות המטמון (pytest/ruff/mypy/coverage) תחת .cache/, אותו עיקרון בדיוק.
_hypothesis_configuration.set_hypothesis_home_dir(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "hypothesis")
)


# גל 23: טסט שמשתמש בדפדפן אמיתי (edge_browser, ישירות או דרך editor_page/home_page) מסומן
# אוטומטית browser. ב-CI הם רצים ב-job נפרד, וכל השאר רצים במקביל (pytest-xdist): לולאת
# ה-asyncio של Playwright נשארת פעילה כל ה-session, ו-asyncio.run() בטסטי הבוט נכשל אם
# שניהם רצים באותו worker.
#
# קבוצות xdist (--dist loadgroup): כל קובץ טסט רץ ב-worker אחד (טסטים באותו קובץ שומרים על הסדר שלהם). עד 24.10.2026
# כל הקבצים שמרנדרים ל-workspace המשותף, או תופסים את מנעול הרינדור (data/render.lock), נכנסו לקבוצה "workspace" אחת
# ורצו בזה אחר זה - עכשיו לכל worker workspace ו-data/ משלו (למעלה), ולכן כל קובץ בקבוצה משלו. קובץ שבאמת צריך לרוץ
# יחד עם קבצים אחרים על משאב משותף מכריז על זה בהערה "xdist-group: <שם>"; השם "workspace" (מהשיטה הקודמת) כבר לא קבוצה.
_GROUP_COMMENT = re.compile(r"xdist-group: ([\w-]+)")
_group_cache = {}


def _xdist_group_for(path):
    key = str(path)
    if key not in _group_cache:
        try:
            match = _GROUP_COMMENT.search(path.read_text(encoding="utf-8"))
        except OSError:
            match = None
        _group_cache[key] = match.group(1) if match and match.group(1) != "workspace" else path.stem
    return _group_cache[key]


# Tk/GUI tests (tkinter / customtkinter / src/ui) are the slowest in the suite (60-140s per file). They get the `tk` marker
# automatically so CI can run them as a separate parallel job (`-m tk`) and keep them out of the main unit job
# (`-m "not browser and not tk"`). Locally, `-m "not browser"` still runs them all.
_TK_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+(?:tkinter|customtkinter|ui(?:\.|\s))", re.MULTILINE)
_tk_cache = {}


def _uses_tk(path):
    key = str(path)
    if key not in _tk_cache:
        try:
            _tk_cache[key] = bool(_TK_IMPORT_RE.search(path.read_text(encoding="utf-8")))
        except OSError:
            _tk_cache[key] = False
    return _tk_cache[key]


# tryfirst: ה-hook של xdist עצמו (ב-worker) הופך את הסימון לסיומת "@קבוצה" ב-nodeid, ורץ
# לפני hooks של conftest - בלי זה הסימון מגיע מאוחר מדי והקבוצות פשוט לא חלות.
@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    for item in items:
        if "edge_browser" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.browser)
        path = getattr(item, "path", None)
        if path is not None:
            item.add_marker(pytest.mark.xdist_group(_xdist_group_for(path)))
            if _uses_tk(path):
                item.add_marker(pytest.mark.tk)


@pytest.fixture(autouse=True)
def _network_guard_opt_out(request, monkeypatch):
    """@pytest.mark.allow_network: חסימת הרשת יורדת לזמן הטסט הזה - בתהליך ובתתי-תהליכים שלו (הדפדפן נשאר מאחורי ה-proxy)."""
    if request.node.get_closest_marker("allow_network") is None:
        yield
        return
    network_guard.uninstall()
    monkeypatch.delenv(network_guard.ENV_FLAG, raising=False)
    try:
        yield
    finally:
        network_guard.install()


@pytest.fixture(scope="session")
def network_proxy():
    """ה-proxy של edge_browser: רושם כל בקשה של הדפדפן שאינה ל-loopback (גם של service worker) וסוגר אותה בלי תשובה."""
    proxy = network_guard.BlockingProxy()
    yield proxy
    proxy.shutdown()
    proxy.server_close()


@pytest.fixture(scope="session")
def shared_tk_root():
    root = ctk.CTk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture(autouse=True)
def _collect_tk_cycles_after_gui_tests(request):
    """אחרי טסט GUI (widget אמיתי על shared_tk_root): איסוף-זבל מיד, על ה-thread הראשי. אחרת
    מעגלי-הפניות עם Font של CTk נאספים מאוחר יותר ב-thread של TestClient/uvicorn, ו-Font.__del__
    נתקע שם על Tcl עד שה-thread הראשי משחרר אותו - ב-CI זה הקפיא בקשת /api/scripts ל-3-11 דקות
    (אותה תופעה כמו _collect_tk_garbage_on_main_thread למטה, בטסטי הדפדפן)."""
    yield
    if "shared_tk_root" in request.fixturenames:
        import gc
        gc.collect()


def remove_video_editor_output(output_path):
    """מוחק קובץ פלט של video_editor.py *וגם* את סייד-קאר ה-".sig.json" שלו
    (smart re-encode skip, my_scripts/video/video_editor.py) - שימוש משותף
    לכל טסטי ה-e2e שמנקים אחרי עצמם (test_video_editor_e2e.py וכו'), כדי
    שסייד-קאר לא יישאר כזבל תחת workspace/studio/vertical|horizontal/ אחרי טסט שרק ניקה
    את קובץ ה-mp4 עצמו ולא ידע על הסייד-קאר החדש. .sig.json יושב בתת-תיקיית
    _sig (item: תיקיית SIG נפרדת, utils/video/video_editor.py's resolve_sig_path)
    - לא ליד הפלט עצמו כמו קודם."""
    output_dir = os.path.dirname(output_path)
    sig_path = os.path.join(output_dir, "_sig", os.path.basename(output_path) + ".sig.json")
    for path in (output_path, sig_path):
        if os.path.exists(path):
            os.remove(path)


# --- טסטי דפדפן אמיתיים לעורך-העל (item 97: Playwright e2e לפאנל) ---
#
# שרת web_app אמיתי (uvicorn ב-thread) על פורט פנוי + Microsoft Edge אמיתי
# (channel="msedge" - מותקן מראש גם על Windows 11 וגם על ה-runner של CI, אז
# אין צורך להוריד דפדפן בנפרד). קובצי הפרופילים מופנים ל-tmp למשך כל ה-session
# - טסטי דפדפן לעולם לא נוגעים ב-data/ האמיתית. אם Playwright/Edge לא זמינים
# בסביבה, הטסטים מדולגים (לא נכשלים).
@pytest.fixture(autouse=True)
def _isolate_user_data_paths(tmp_path_factory, monkeypatch):
    """רשת-ביטחון לכל הטסטים: קובצי הפרופילים/היסטוריית-הריצות של עורך-העל, וקובצי
    הבקרה/אצוות-הפרסום של ריצות, מופנים לתיקייה זמנית של ה-session - גם בטסטים
    שלא מבודדים אותם בעצמם (למשל /api/run ב-test_web_app_runs.py). data/ האמיתית היא
    נתוני-משתמש שאין להם גיבוי - טסט לעולם לא כותב לשם. טסט שמפנה בעצמו לנתיב
    משלו (monkeypatch אחרי ה-fixture הזה) גובר, כרגיל."""
    import sys as _sys
    base = tmp_path_factory.getbasetemp() / "isolated_user_data"
    vep_module = _sys.modules.get("utils.video.video_editor_profiles")
    if vep_module is not None:
        for attr, name in (("PROFILES_PATH", "video_editor_profiles.json"), ("META_PATH", "video_editor_profile_meta.json"),
                           ("HISTORY_PATH", "video_editor_profile_history.json")):
            monkeypatch.setattr(vep_module, attr, str(base / name))
    web_module = _sys.modules.get("entrypoints.web_app")
    if web_module is not None:
        for attr in ("RUN_CONTROL_DIR", "PUBLISH_BATCHES_DIR"):
            if hasattr(web_module, attr):
                monkeypatch.setattr(web_module, attr, str(base / attr.lower()))
    # גל 32: יומן ה-SEO המרכזי לא בפרויקט, ו-Gemini אמיתי (מפתח מקומי) לא נקרא - טסט שבודק
    # את מסלול ה-AI מדליק אותו בעצמו (monkeypatch אחרי ה-fixture הזה גובר)
    seo_module = _sys.modules.get("utils.bot.seo_generator")
    if seo_module is not None:
        base.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(seo_module, "HISTORY_LOG_FILE", str(base / "seo_history_log.txt"))
        monkeypatch.setattr(seo_module, "LEGACY_HISTORY_LOG_FILE", str(base / "legacy_seo_history_log.txt"))
        monkeypatch.setattr(seo_module, "ai_enabled", lambda: False)


def _collect_tk_garbage_on_main_thread():
    """איסוף-זבל מלא *על ה-thread הראשי* לפני שהשרת/הדף רצים. טסטי ה-GUI השולחני
    משאירים מעגלי-הפניות עם אובייקטי tkinter (Font של CTk וכו'); אם ה-GC האוטומטי
    אוסף אותם דווקא על ה-thread של uvicorn, Font.__del__ קורא ל-Tcl מ-thread זר
    ונתקע עד שה-thread הראשי "משחרר" את Tcl - השרת כולו קפא לדקות (נמצא ב-CI
    דרך ה-dump של ה-threads למטה: uvicorn תקוע ב-tkinter/font.py __del__)."""
    import gc
    gc.collect()


@pytest.fixture(scope="session")
def editor_server(tmp_path_factory):
    import socket
    import threading
    import time

    uvicorn = pytest.importorskip("uvicorn")
    from utils.video import video_editor_profiles as vep
    from entrypoints import web_app

    data_dir = tmp_path_factory.mktemp("browser_e2e_data")
    patcher = pytest.MonkeyPatch()
    patcher.setattr(vep, "PROFILES_PATH", str(data_dir / "video_editor_profiles.json"))
    patcher.setattr(vep, "META_PATH", str(data_dir / "video_editor_profile_meta.json"))
    patcher.setattr(vep, "HISTORY_PATH", str(data_dir / "video_editor_profile_history.json"))
    patcher.setattr(web_app, "BATCH_OVERRIDES_DIR", str(data_dir / "batch_overrides"))
    patcher.setattr(web_app, "CAPTIONS_EDITS_DIR", str(data_dir / "captions_edits"))
    patcher.setattr(web_app.limiter, "enabled", False)
    # כל טעינת דף קוראת /api/update_check - בלי רשת אמיתית (GitHub API) בטסטים.
    patcher.setattr(web_app, "check_for_update", lambda *_args, **_kwargs: None)
    for name, value in getattr(web_app, "BROWSER_E2E_DATA_PATH_ATTRS", {}).items():
        patcher.setattr(web_app, name, str(data_dir / value))
    # 30.10.2026: התקנה חדשה נפתחת באנגלית (utils/shared/ui_language.py), וטסטי הדפדפן בודקים את הממשק העברי - שרת הבדיקה
    # הוא התקנה קיימת בעברית. טסט של התקנה חדשה מפנה את CONFIG_FILE לקובץ שלא קיים
    patcher.setattr(web_app, "CONFIG_FILE", str(data_dir / "config.json"))
    (data_dir / "config.json").write_text('{"language": "he"}', encoding="utf-8")

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    _collect_tk_garbage_on_main_thread()
    server = uvicorn.Server(uvicorn.Config(web_app.app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        patcher.undo()
        pytest.skip("שרת ה-web_app לא עלה בזמן לטסטי הדפדפן")
    # הטוקן *לא* מוחלף כאן (הוא גלובלי לכל ה-session - החלפה הייתה שוברת טסטי
    # TestClient שרצים אחרי זה עם העוגייה הישנה) - editor_page קורא אותו בכל פעם.
    yield {"base_url": f"http://127.0.0.1:{port}", "data_dir": data_dir, "web_app": web_app}
    server.should_exit = True
    thread.join(timeout=10)
    patcher.undo()


@pytest.fixture(scope="session")
def edge_browser(network_proxy):
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        manager = sync_api.sync_playwright().start()
    except Exception as e:  # pragma: no cover - סביבה בלי Playwright driver
        pytest.skip(f"Playwright לא זמין: {e}")
    try:
        # proxy: כל בקשה שאינה ל-loopback (דף, service worker, worker) הולכת ל-network_proxy ונכשלת - page.route לא רואה
        # בקשות של service worker (23.10.2026: טסט של הקטלוג יצא כך ל-api.worldbank.org). Playwright מוסיף לבד <-loopback>
        # (גם loopback דרך ה-proxy), אז שרתי הבדיקה על 127.0.0.1 / localhost עוקפים אותו במפורש.
        browser = manager.chromium.launch(channel="msedge", headless=True,
                                          proxy={"server": network_proxy.url, "bypass": "127.0.0.1,localhost,[::1]"})
    except Exception as e:  # pragma: no cover - סביבה בלי Edge
        manager.stop()
        pytest.skip(f"Microsoft Edge לא זמין לטסטי דפדפן: {e}")
    yield browser
    browser.close()
    manager.stop()


@pytest.fixture
def editor_page(editor_server, edge_browser):
    """דף חדש (context נקי - localStorage ריק) עם עורך-העל כבר נבחר."""
    _collect_tk_garbage_on_main_thread()
    context = edge_browser.new_context(viewport={"width": 1440, "height": 950}, locale="he-IL")
    try:
        # גל 10: עורך-העל נפתח במצב "פשוט" כברירת מחדל; הטסטים הקיימים בודקים כל
        # שדה ולכן מתחילים ב"מתקדם" (טסטי המצב הפשוט מחליפים אליו במפורש).
        context.add_init_script("try { if (localStorage.getItem('veMode') === null) localStorage.setItem('veMode', JSON.stringify('advanced')); } catch (e) {}")
        # גל 31: העורך תמיד בסטודיו. הטסטים הקיימים ממלאים שדות בכל האזורים, אז ההגדרות "הכל ברשימה"
        # (בלי לשוניות) - טסטי הלשוניות מחליפים אליהן במפורש
        context.add_init_script("try { if (localStorage.getItem('veLayout') === null) localStorage.setItem('veLayout', JSON.stringify('accordion')); } catch (e) {}")
        # גל 28: תתי-אזורים מתקפלים כברירת מחדל; הטסטים הקיימים ממלאים שדות בכל תת-אזור, אז פתוחים (טסטי גל 28 מקפלים)
        context.add_init_script("try { if (localStorage.getItem('veCollapseSubcats') === null) localStorage.setItem('veCollapseSubcats', 'false'); } catch (e) {}")
        # 31.10.2026: שרת הבדיקה הוא התקנה בעברית - נשמר מראש, כדי שהדף לא יוסתר עד ש-/api/settings/style עונה (00-head.html)
        context.add_init_script("try { if (localStorage.getItem('uiLang') === null) localStorage.setItem('uiLang', 'he'); } catch (e) {}")
        page = context.new_page()
        page.goto(f"{editor_server['base_url']}/?token={editor_server['web_app'].ACCESS_TOKEN}")
        # state מוגדר ב-let ברמה העליונה (לא window.state) - נגיש בשם ישיר בלבד.
        page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)
        page.evaluate("() => selectScript(state.scripts.find(s => s.id.endsWith('video_editor.py')).id)")
        page.wait_for_function("() => !document.getElementById('videoEditorOptions').hidden")
    except Exception:
        # setup שנכשל חייב לסגור את ה-context בעצמו: אחרת הדף נשאר חי עד סוף
        # ה-session, וה-WebSocket שלו (לשרת ה-uvicorn שממשיך לרוץ) "גונב" שורות
        # מתורי הלוג/התקדמות המשותפים מטסטים מאוחרים יותר (נמצא ב-CI). ה-dump של
        # כל ה-threads מראה מה השרת עשה כשלא הגיב - לאבחון תקיעה עתידית.
        import faulthandler
        import sys
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        context.close()
        raise
    yield page
    context.close()


def answer_ve_prompt(page, text, timeout=10000):
    """גל 22: prompt() של הדפדפן הוחלף בדיאלוג בתוך הדף (vePrompt) - הטסט עונה עליו כמו משתמש.
    קריאה לפונקציה שפותחת אותו צריכה לא לחכות להבטחה שלה: page.evaluate("() => { f(); }")."""
    page.wait_for_selector("#vePromptModalBg.show", timeout=timeout)
    page.fill("#vePromptInput", text)
    page.click("#vePromptOkBtn")


@pytest.fixture
def ve_prompt():
    """answer_ve_prompt כ-fixture - קבצי הטסטים לא מייבאים את conftest ישירות."""
    return answer_ve_prompt
