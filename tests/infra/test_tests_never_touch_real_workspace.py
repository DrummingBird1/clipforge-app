# tests/infra/test_tests_never_touch_real_workspace.py
#
# סבב ייצוב: workspace/ הוא תיקיית העבודה של המשתמש (קליפים, תוצרים). ריצות מלאות השאירו בו מאות קבצים -
# .run_manifests, .previews, .dataviz_previews, .layers, canary.mp4 וקובצי _sig, .thumbnail_candidates. מאז
# tests/conftest.py מפנה את CLIPFORGE_WORKSPACE_DIR לתיקייה זמנית לכל הריצה (כמו data/ בטסט האחות
# test_tests_never_touch_real_data.py), ובסוף הריצה בודק ש-workspace/ האמיתי לא השתנה - ואם כן, הריצה נכשלת.
import os
import re
import shutil
import subprocess
import sys

from tests import PROJECT_ROOT as BASE_DIR, TESTS_DIR
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

REAL_WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")


def _is_under(path, directory):
    path, directory = os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(directory))
    return path == directory or path.startswith(directory + os.sep)


def test_this_test_run_points_every_workspace_path_at_a_temporary_dir():
    from entrypoints import web_app
    from utils.bot import approval_store, seo_generator
    from utils.shared import diagnostics, workspace_dir

    temp = os.environ["CLIPFORGE_WORKSPACE_DIR"]
    assert not _is_under(temp, REAL_WORKSPACE_DIR)
    assert _is_under(web_app.WORKSPACE_DIR, temp) and _is_under(workspace_dir.WORKSPACE_DIR, temp)
    paths = [getattr(web_app, name) for name in web_app.WORKSPACE_SUBDIRS] + list(web_app.WEB_APP_EXPORT_DIRS)
    paths += [approval_store.CLIPS_REVIEW_DIR, approval_store.REJECTED_DIR, approval_store.FRIEND_TAGS_CACHE_DIR,
              seo_generator.EXPORTS_DIR, diagnostics.WORKSPACE_DIR]
    assert [p for p in paths if _is_under(p, REAL_WORKSPACE_DIR)] == []


# os.path.join(BASE_DIR, "workspace", ...) בטסט עוקף את CLIPFORGE_WORKSPACE_DIR - הסקריפטים כותבים לזמני, והטסט מחפש במקום אחר
_OWN_WORKSPACE_PATH = re.compile(r"""os\.path\.join\([^)\n]*(?:BASE_DIR|PROJECT_ROOT|ROOT),\s*["']workspace["']""")
# אלה בודקים במפורש את ברירת המחדל (בלי המשתנה) או שאין שם כלום
_ALLOWED = {"test_video_editor_workspace_env.py", "test_bot_workspace_env.py", "test_web_app_workspace_env.py",
            "test_tests_never_touch_real_workspace.py"}


def test_no_test_builds_the_real_workspace_path():
    offenders = []
    for dirpath, dirnames, filenames in os.walk(TESTS_DIR):   # גם תיקיות האזורים (tests/<אזור>/)
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in sorted(filenames):
            if not name.endswith(".py") or name in _ALLOWED:
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), TESTS_DIR)
            with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                offenders += [f"{rel}:{n}" for n, line in enumerate(f, 1) if _OWN_WORKSPACE_PATH.search(line)]
    assert offenders == [], f"נתיב workspace/ שנבנה ידנית בטסט - השתמשו ב-utils.shared.workspace_dir.WORKSPACE_DIR: {offenders}"


def test_the_code_builds_the_workspace_path_only_as_the_default_of_the_variable():
    # timelapse_maker, story_cutter, rocket_shorts_publisher ולשוניות ה-GUI כתבו ל-<שורש>/workspace גם בטסטים - עכשיו
    # utils.shared.workspace_dir; "<שורש>/workspace" מותר רק כברירת המחדל באותה שורה שקוראת את CLIPFORGE_WORKSPACE_DIR
    pattern = re.compile(r"""os\.path\.join\([^)\n]*["']workspace["']""")
    offenders = []
    for top in ("src", "my_scripts"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(BASE_DIR, top)):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if not name.endswith((".py", ".pyw")):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, name), BASE_DIR)
                with open(os.path.join(BASE_DIR, rel), encoding="utf-8") as f:
                    offenders += [f"{rel}:{n}" for n, line in enumerate(f, 1)
                                  if pattern.search(line) and "CLIPFORGE_WORKSPACE_DIR" not in line and not line.lstrip().startswith("#")]
    assert offenders == [], f"נתיב workspace/ קבוע בקוד - השתמשו ב-utils.shared.workspace_dir.WORKSPACE_DIR: {offenders}"


_LEAK_TEST = '''
import os

def test_writes_where_it_should_not():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(os.path.join(root, "workspace", ".run_manifests"), exist_ok=True)
    with open(os.path.join(root, "workspace", ".run_manifests", "leak.json"), "w") as f:
        f.write("{}")

def test_writes_to_the_temporary_workspace():
    with open(os.path.join(os.environ["CLIPFORGE_WORKSPACE_DIR"], "fine.json"), "w") as f:
        f.write("{}")
'''


def _run_copy(project, *node_ids):
    # ריצת pytest עצמאית על עותק: בלי המשתנים של הריצה הזו (אחרת ה-conftest של העותק "יורש" אותם) ובלי כיסוי
    env = {key: value for key, value in os.environ.items()
           if key not in ("CLIPFORGE_DATA_DIR", "CLIPFORGE_WORKSPACE_DIR") and not key.startswith(("PYTEST_", "COV_CORE_", "COVERAGE_"))}
    return subprocess.run([sys.executable, "-m", "pytest", *node_ids, "-q", "-p", "no:cacheprovider"], cwd=str(project), env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, creationflags=NO_WINDOW_FLAGS)


def test_a_run_that_writes_to_the_real_workspace_fails(tmp_path):
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    shutil.copy2(os.path.join(BASE_DIR, "pyproject.toml"), project)
    for name in ("__init__.py", "conftest.py"):
        shutil.copy2(os.path.join(TESTS_DIR, name), project / "tests" / name)
    (project / "tests" / "test_leak.py").write_text(_LEAK_TEST, encoding="utf-8")
    (project / "workspace").mkdir()
    (project / "workspace" / "users_clip.mp4").write_bytes(b"real")

    clean = _run_copy(project, "tests/test_leak.py::test_writes_to_the_temporary_workspace")
    assert clean.returncode == 0, clean.stdout[-3000:] + clean.stderr[-2000:]
    leaky = _run_copy(project, "tests/test_leak.py::test_writes_where_it_should_not")
    assert "1 passed" in leaky.stdout and leaky.returncode == 1, leaky.stdout[-3000:]   # הטסט עבר - הריצה נכשלה
    assert "leak.json" in leaky.stdout and "workspace" in leaky.stdout
    assert (project / "workspace" / "users_clip.mp4").read_bytes() == b"real"
