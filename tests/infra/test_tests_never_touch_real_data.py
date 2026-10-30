# tests/infra/test_tests_never_touch_real_data.py
#
# data/ היא נתוני-משתמש אמיתיים בלי גיבוי. ריצת הטסטים המלאה שינתה בה בפועל את counter.txt
# (מונה Rocket), scheduler_state.json (נדרס בתוכן של טסט הקנרית), render_waiters.json,
# ffprobe_cache.json, clipforge_data.db ו-logs/script_runs.log. מאז כל נתיב תחת data/ נגזר
# מ-utils/shared/data_dir.py, ו-tests/conftest.py מפנה אותו (CLIPFORGE_DATA_DIR) לתיקייה זמנית.
#
# טסט הרגרסיה מריץ את הטסטים שכתבו לשם בפועל על *עותק* של הפרויקט, עם data/ משלו שמכילה
# קבצי-פיתיון באותם שמות - ובודק שאף אחד מהם לא השתנה (תוכן/mtime) ושלא נוצר שם קובץ חדש.
# עותק ולא data/ האמיתית: נסיגה בתיקון לא תפגע בנתוני המשתמש עצמם, ואפליקציה אמיתית שרצה
# במקביל (שכותבת ל-data/ כרגיל) לא תכשיל את הטסט סתם.
import hashlib
from tests import TESTS_DIR
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys

from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

BASE_DIR = os.path.dirname(TESTS_DIR)
REAL_DATA_DIR = os.path.join(BASE_DIR, "data")

# טסט אחד שכתב בפועל לכל קובץ (נמצא בריצה מלאה מול data/ ריקה) - מהירים, בלי דפדפן
LEAKY_TESTS = [
    "tests/bot/test_scheduler_canary_render.py::test_runs_when_not_yet_run_today_and_succeeds",  # scheduler_state.json
    "tests/gui/test_rocket_settings_clip_hotkey.py::test_save_persists_the_hotkey_stripped_of_whitespace",  # counter.txt
    "tests/gui/test_dashboard_worker_integration.py::test_heavy_task_fires_start_and_50pct_toast_milestones",  # script_runs.log, render_waiters.json
    "tests/web/test_web_app_clips.py::test_api_clips_youtube_export_starts_upload_when_configured",  # clipforge_data.db
    "tests/studio/test_web_app_editor_wave3.py::test_probe_endpoint_returns_duration_and_dimensions",  # ffprobe_cache.json (מדולג בלי ffmpeg)
]
DECOY_FILES = {
    "counter.txt": "571",
    "scheduler_state.json": json.dumps({"last_db_backup_date": "2026-01-01", "last_canary_render_date": "2026-01-01"}),
    "render_waiters.json": "{}",
    "ffprobe_cache.json": "{}",
    os.path.join("logs", "script_runs.log"): "2026-01-01 00:00:00 | decoy\n",
    os.path.join("logs", "script_runs.jsonl"): "",
}


def _norm(path):
    return os.path.normcase(os.path.realpath(path))


def _is_under(path, directory):
    path, directory = _norm(path), _norm(directory)
    return path == directory or path.startswith(directory + os.sep)


def test_this_test_run_points_every_data_path_at_a_temporary_dir():
    import cogs.scheduler_cog as scheduler_cog
    from entrypoints import web_app
    from ui import rocket_settings_tab
    from utils.shared import data_dir, job_history, logging_setup, render_lock
    from utils.media import ffprobe_cache
    from utils.bot import youtube_publish_log

    assert _norm(data_dir.DATA_DIR) == _norm(os.environ["CLIPFORGE_DATA_DIR"])
    assert not _is_under(data_dir.DATA_DIR, REAL_DATA_DIR)
    for path in (web_app.ROCKET_COUNTER_PATH, rocket_settings_tab.COUNTER_FILE_PATH, scheduler_cog.SCHEDULER_STATE_PATH,
                 render_lock.WAITERS_PATH, ffprobe_cache.CACHE_PATH, job_history.DB_PATH, youtube_publish_log.DB_PATH,
                 web_app.BOT_DB_PATH, logging_setup.LOGS_DIR):
        assert _is_under(path, data_dir.DATA_DIR), path


# os.path.join(..., "data", ...) / Path(...) / "data" - נתיב data/ שנבנה ידנית עוקף את CLIPFORGE_DATA_DIR
_OWN_DATA_PATH = re.compile(r"""os\.path\.join\([^)\n]*["']data["']|/\s*["']data["']""")
# build_exe.py אורז את קבצי ה-*.example.json מהריפו עצמו - לא נתוני-משתמש
_ALLOWED = {os.path.join("src", "utils", "shared", "data_dir.py"), os.path.join("dev", "build_exe.py")}


def test_every_data_path_goes_through_utils_data_dir():
    offenders = []
    for top in ("src", "my_scripts"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(BASE_DIR, top)):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                rel = os.path.relpath(os.path.join(dirpath, name), BASE_DIR)
                if not name.endswith((".py", ".pyw")) or rel in _ALLOWED:
                    continue
                with open(os.path.join(BASE_DIR, rel), encoding="utf-8") as f:
                    offenders += [f"{rel}:{n}" for n, line in enumerate(f, 1)
                                  if _OWN_DATA_PATH.search(line) and not line.lstrip().startswith("#")]
    assert offenders == [], f"נתיב data/ שנבנה ידנית - השתמשו ב-utils.shared.data_dir.DATA_DIR (אחרת טסטים כותבים לנתונים האמיתיים): {offenders}"


def _copy_project(dest):
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for name in ("src", "my_scripts", "assets"):
        shutil.copytree(os.path.join(BASE_DIR, name), os.path.join(dest, name), ignore=ignore)
    shutil.copy2(os.path.join(BASE_DIR, "pyproject.toml"), dest)
    test_files = {node.split("::")[0].split("/", 1)[1] for node in LEAKY_TESTS}   # "<אזור>/test_x.py"
    areas = {f"{rel.split('/')[0]}/__init__.py" for rel in test_files}
    for rel in {"__init__.py", "conftest.py", "page_source.py", "web_app_support.py", *areas, *test_files}:
        os.makedirs(os.path.dirname(os.path.join(dest, "tests", rel)), exist_ok=True)
        shutil.copy2(os.path.join(TESTS_DIR, rel), os.path.join(dest, "tests", rel))


def _seed_decoy_data_dir(data_dir):
    for rel, content in DECOY_FILES.items():
        os.makedirs(os.path.dirname(os.path.join(data_dir, rel)), exist_ok=True)
        with open(os.path.join(data_dir, rel), "w", encoding="utf-8") as f:
            f.write(content)
    conn = sqlite3.connect(os.path.join(data_dir, "clipforge_data.db"))
    try:
        conn.execute("CREATE TABLE decoy (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()


def _snapshot(data_dir):
    snapshot = {}
    for dirpath, _dirnames, filenames in os.walk(data_dir):
        for name in filenames:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            snapshot[os.path.relpath(path, data_dir)] = (os.stat(path).st_mtime_ns, digest)
    return snapshot


def test_the_tests_that_used_to_write_to_data_leave_it_untouched(tmp_path):
    project = tmp_path / "project"
    _copy_project(str(project))
    data_dir = str(project / "data")
    _seed_decoy_data_dir(data_dir)
    before = _snapshot(data_dir)

    # ריצת pytest עצמאית לגמרי: בלי תיקיית ה-data הזמנית של הריצה הזו ובלי משתני ה-worker של xdist
    # (אחרת ה-conftest של העותק היה "יורש" אותם) - ובלי כיסוי, שהיה מערבב את קבצי העותק לדוח.
    env = {key: value for key, value in os.environ.items()
           if key != "CLIPFORGE_DATA_DIR" and not key.startswith(("PYTEST_", "COV_CORE_", "COVERAGE_"))}
    result = subprocess.run([sys.executable, "-m", "pytest", *LEAKY_TESTS, "-q", "-p", "no:cacheprovider"],
                            cwd=str(project), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=300, creationflags=NO_WINDOW_FLAGS)

    after = _snapshot(data_dir)
    changed = sorted(rel for rel in before.keys() | after.keys() if before.get(rel) != after.get(rel))
    assert changed == [], f"טסטים שינו קבצים תחת data/ (נתוני-משתמש אמיתיים): {changed}\n{result.stdout[-3000:]}"
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]
