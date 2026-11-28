# tests/infra/test_build_portable.py
#
# dev/build_portable.py ו-dev/portable/launcher.pyw: מה נכנס לחבילה הניידת ומה לא, הבדיקה ש-ffmpeg כולל את מה שהקוד צריך,
# והסביבה המבודדת של ה-launcher. בלי לבנות zip אמיתי (מאות MB) - על תיקיות מזויפות ב-tmp_path.
import importlib.machinery
import importlib.util
import os
import socket
import threading
import time

from tests import PROJECT_ROOT


def _load(name, rel):
    path = os.path.join(PROJECT_ROOT, *rel.split("/"))
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


bp = _load("build_portable", "dev/build_portable.py")
launcher = _load("portable_launcher", "dev/portable/launcher.pyw")


def _touch(path, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_only_the_app_goes_in_without_the_internal_and_developer_files():
    for rel in ("src/entrypoints/web_app.py", "my_scripts/video/video_editor.py", "assets/fonts/OFL-Heebo.txt",
                "docs/web_ui.md", "README.md", "README.he.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md"):
        assert bp.wanted_app_file(rel), rel
    for rel in ("AGENTS.md", "docs/handoff/2026-10-30-x.md", "docs/history/old.md", "tests/conftest.py", "dev/build_portable.py",
                "my_scripts/tools/check_pos.py", "data/config.example.json", "uv.lock", ".github/workflows/ci.yml", "pyproject.toml"):
        assert not bp.wanted_app_file(rel), rel


def test_the_python_runtime_is_copied_without_the_developers_packages(tmp_path):
    home = tmp_path / "python"
    for rel in ("python.exe", "pythonw.exe", "py.exe", "python314.dll", "vcruntime140.dll", "LICENSE.txt", "DLLs/_ssl.pyd",
                "Lib/os.py", "Lib/json/__init__.py", "Lib/site-packages/requests/__init__.py", "Lib/test/test_os.py",
                "Lib/__pycache__/os.cpython-314.pyc", "Lib/idlelib/idle.py", "Scripts/pip.exe", "tcl/tcl8.6/init.tcl"):
        _touch(home / rel)
    got = sorted(rel.replace(os.sep, "/") for _src, rel in bp.runtime_entries(str(home)))
    assert got == ["DLLs/_ssl.pyd", "LICENSE.txt", "Lib/json/__init__.py", "Lib/os.py", "python.exe", "python314.dll",
                   "pythonw.exe", "tcl/tcl8.6/init.tcl", "vcruntime140.dll"]


def test_pyautogui_and_its_gpl_dependencies_stay_out_of_site_packages(tmp_path):
    env, dest = tmp_path / "env", tmp_path / "dest"
    _touch(env / "pyautogui" / "__init__.py")
    _touch(env / "pyautogui-0.9.54.dist-info" / "RECORD", "pyautogui/__init__.py,sha256=x,1\npyautogui-0.9.54.dist-info/RECORD,,\n")
    _touch(env / "pymsgbox" / "__init__.py")
    _touch(env / "PyMsgBox-2.0.1.dist-info" / "RECORD", "pymsgbox/__init__.py,sha256=x,1\n")
    _touch(env / "numpy" / "__init__.py")
    _touch(env / "numpy" / "__pycache__" / "x.pyc")
    _touch(env / "numpy-2.4.6.dist-info" / "RECORD", "numpy/__init__.py,sha256=x,1\n")
    _touch(env / "_virtualenv.pth", "import _virtualenv")
    bp.copy_site_packages(str(env), str(dest))
    got = sorted(str(p.relative_to(dest)).replace(os.sep, "/") for p in dest.rglob("*") if p.is_file())
    assert got == ["numpy-2.4.6.dist-info/RECORD", "numpy/__init__.py"]


def test_ffmpeg_must_have_what_the_code_uses():
    encoders = " V....D libx264              libx264 H.264\n V....D h264_nvenc           NVIDIA NVENC H.264 encoder\n"
    filters = " ... drawtext   V->V  Draw text\n ... zscale  V->V  zimg\n ... vidstabdetect V->V x\n ... vidstabtransform V->V x\n"
    assert bp.missing_ffmpeg_features(encoders, filters) == []
    lgpl_encoders = " V....D h264_nvenc           NVIDIA NVENC H.264 encoder\n"
    lgpl_filters = " ... drawtext   V->V  Draw text\n ... zscale  V->V  zimg\n"
    assert bp.missing_ffmpeg_features(lgpl_encoders, lgpl_filters) == ["libx264", "vidstabdetect", "vidstabtransform"]


def test_without_ffmpeg_the_pinned_zip_is_found_above_the_repo(tmp_path):
    pinned = tmp_path / "media" / "ffmpeg" / bp.FFMPEG_DIR / bp.FFMPEG_ZIP
    _touch(pinned)
    repo = tmp_path / "projects" / "clipforge"
    repo.mkdir(parents=True)
    assert bp.default_ffmpeg(str(repo), environ={}) == str(pinned)
    assert bp.default_ffmpeg(str(repo), environ={"CLIPFORGE_FFMPEG": "C:/builds/ffmpeg"}) == "C:/builds/ffmpeg"
    pinned.unlink()
    assert bp.default_ffmpeg(str(repo), environ={}) is None


def test_the_tools_folder_is_searched_before_the_older_media_folder(tmp_path):
    older = tmp_path / "media" / "ffmpeg" / bp.FFMPEG_DIR / bp.FFMPEG_ZIP
    tools = tmp_path / "media" / "tools" / "ffmpeg" / bp.FFMPEG_DIR / bp.FFMPEG_ZIP
    _touch(older)
    _touch(tools)
    repo = tmp_path / "projects" / "clipforge"
    repo.mkdir(parents=True)
    assert bp.default_ffmpeg(str(repo), environ={}) == str(tools)
    tools.unlink()
    assert bp.default_ffmpeg(str(repo), environ={}) == str(older)


def test_the_default_zip_must_be_the_exact_file_release_yml_pins(tmp_path, monkeypatch):
    import hashlib
    import pytest
    import yaml
    with open(os.path.join(PROJECT_ROOT, ".github", "workflows", "release.yml"), encoding="utf-8") as f:
        env = yaml.safe_load(f)["env"]
    assert env["FFMPEG_SHA256"] == bp.FFMPEG_SHA256
    assert env["FFMPEG_URL"].endswith("/" + bp.FFMPEG_ZIP)
    other = tmp_path / bp.FFMPEG_ZIP
    other.write_bytes(b"not the pinned build")
    with pytest.raises(SystemExit, match="SHA-256"):
        bp.check_pinned_zip(str(other))
    monkeypatch.setattr(bp, "FFMPEG_SHA256", hashlib.sha256(b"not the pinned build").hexdigest())
    bp.check_pinned_zip(str(other))


def test_the_version_comes_from_version_py():
    from utils.shared.version import APP_VERSION
    assert bp.read_version() == APP_VERSION


def _imports_outside_the_standard_library(path, seen):
    """כל מה ש-path מייבא (גם בתוך פונקציות), ומה שהמודולים של utils שהוא מייבא מייבאים בעצמם, שאינו מהספרייה הסטנדרטית."""
    import ast
    import sys
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)   # "from utils.shared import x" - x עשוי להיות מודול
    outside = set()
    for name in sorted(names):
        top = name.split(".")[0]
        if top in sys.stdlib_module_names:
            continue
        if top != "utils":
            outside.add(f"{os.path.relpath(path, PROJECT_ROOT)}: {name}")
            continue
        parts = name.split(".")
        # ייבוא של utils.a.b מריץ גם את utils/__init__.py ו-utils/a/__init__.py, ואז את המודול עצמו
        for end in range(1, len(parts) + 1):
            base = os.path.join(PROJECT_ROOT, "src", *parts[:end])
            for candidate in (base + ".py", os.path.join(base, "__init__.py")):
                if os.path.isfile(candidate) and candidate not in seen:
                    seen.add(candidate)
                    outside |= _imports_outside_the_standard_library(candidate, seen)
    return outside


def test_the_build_script_needs_nothing_outside_the_standard_library():
    # 8.11.2026: release.yml מריץ אותו עם הפייתון של ה-runner, בלי ספריות הפרויקט (test_release_workflow: בלי uv run). הוא ייבא
    # את update_checker בשביל שני קבועים, שמייבא requests - וה-Release הראשון בריפו הציבורי נפל על ModuleNotFoundError.
    outside = _imports_outside_the_standard_library(os.path.join(PROJECT_ROOT, "dev", "build_portable.py"), set())
    assert outside == set(), f"dev/build_portable.py needs packages the CI runner doesn't have: {sorted(outside)}"


def test_the_portable_marker_constants_live_in_a_module_without_dependencies():
    from utils.shared import release_info, update_checker
    assert (release_info.PORTABLE_MARKER, release_info.REPO) == ("portable.json", "DrummingBird1/clipforge-app")
    assert release_info.RELEASES_PAGE_URL == "https://github.com/DrummingBird1/clipforge-app/releases/latest"
    # הקוד הקיים (web_app, הטסטים) קורא אותם דרך update_checker - אותם ערכים בדיוק
    assert update_checker.PORTABLE_MARKER == release_info.PORTABLE_MARKER
    assert update_checker.RELEASES_PAGE_URL == release_info.RELEASES_PAGE_URL and update_checker.REPO == release_info.REPO
    assert update_checker._RELEASES_API_URL == "https://api.github.com/repos/DrummingBird1/clipforge-app/releases/latest"


def test_the_launcher_isolates_the_packages_python_from_the_users_settings():
    env = launcher.isolated_env({"PYTHONPATH": r"C:\mine", "PythonHome": r"C:\py", "PYTHONSTARTUP": "s.py", "PATH": r"C:\Windows"})
    assert env == {"PATH": r"C:\Windows", "PYTHONNOUSERSITE": "1", "PYTHONIOENCODING": "utf-8"}


def test_the_launcher_waits_for_a_fresh_token_not_the_one_left_from_last_time(tmp_path):
    token = tmp_path / "web_app_token.txt"
    _touch(token, "old")
    before = os.path.getmtime(token)
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    port = server.getsockname()[1]
    try:
        assert launcher.wait_for_server(str(token), before, timeout=1, port=port) is False   # הטוקן הישן - עוד לא עלה

        def rewrite():
            time.sleep(0.3)
            token.write_text("new", encoding="utf-8")
            os.utime(token, (before + 5, before + 5))

        threading.Thread(target=rewrite).start()
        assert launcher.wait_for_server(str(token), before, timeout=10, port=port) is True
    finally:
        server.close()


def test_the_zip_gets_a_sha256sums_file_that_sha256sum_can_check(tmp_path):
    """30.10.2026: dist/SHA256SUMS.txt ליד ה-zip - "<hash>  <שם>" ו-LF, כמו sha256sum; release.yml מצרף אותו ל-Release."""
    import hashlib
    zip_path = tmp_path / "ClipForge-9.9.9-win64.zip"
    zip_path.write_bytes(b"not really a zip")
    digest = bp.write_checksums(str(zip_path))
    assert digest == hashlib.sha256(b"not really a zip").hexdigest()
    assert (tmp_path / "SHA256SUMS.txt").read_bytes() == f"{digest}  ClipForge-9.9.9-win64.zip\n".encode("utf-8")


def test_site_packages_leave_out_unused_google_discovery_docs_library_tests_and_stubs(tmp_path):
    """30.10.2026: ה-zip ירד מ-280MB - מסמכי discovery רק ל-youtube v3 ו-youtubeAnalytics v2 (מה שהקוד בונה), בלי tests/ של
    ספריות ובלי .pyi."""
    env, dest = tmp_path / "env", tmp_path / "dest"
    docs = env / "googleapiclient" / "discovery_cache" / "documents"
    for name in ("youtube.v3.json", "youtubeAnalytics.v2.json", "drive.v3.json", "youtubeAnalytics.v1.json"):
        _touch(docs / name, "{}")
    _touch(env / "googleapiclient" / "discovery_cache" / "__init__.py")
    _touch(env / "pandas" / "tests" / "test_frame.py")
    _touch(env / "numpy" / "_core" / "tests" / "test_x.py")
    _touch(env / "numpy" / "testing" / "__init__.py")   # numpy.testing הוא קוד, לא tests/
    _touch(env / "numpy" / "__init__.pyi")
    _touch(env / "numpy" / "__init__.py")
    bp.copy_site_packages(str(env), str(dest))
    got = sorted(str(p.relative_to(dest)).replace(os.sep, "/") for p in dest.rglob("*") if p.is_file())
    assert got == ["googleapiclient/discovery_cache/__init__.py", "googleapiclient/discovery_cache/documents/youtube.v3.json",
                   "googleapiclient/discovery_cache/documents/youtubeAnalytics.v2.json", "numpy/__init__.py",
                   "numpy/testing/__init__.py"]


def test_the_kept_discovery_docs_are_the_clients_the_code_builds():
    import re
    builds = set()
    for root in ("src", "my_scripts"):
        for current, _dirs, files in os.walk(os.path.join(PROJECT_ROOT, root)):
            for name in files:
                if name.endswith(".py"):
                    text = open(os.path.join(current, name), encoding="utf-8").read()
                    builds |= set(re.findall(r'\bbuild\("(\w+)", "(v\d+)"', text))
    assert {f"{service}.{version}.json" for service, version in builds} == set(bp.GOOGLE_DISCOVERY_KEEP)


def test_the_launcher_error_follows_the_install_language():
    """30.10.2026: חלון השגיאה של הלאנצ'ר בשפת ההתקנה, כמו תפריט המגש."""
    assert launcher.start_failed_text("en", "C:/x/log.txt").startswith("ClipForge did not start within")
    assert launcher.start_failed_text("he", "C:/x/log.txt").startswith("ClipForge לא עלה תוך")
    assert "C:/x/log.txt" in launcher.start_failed_text("he", "C:/x/log.txt")

# --- 16.11.2026 (2.0): winget ---

def test_a_winget_install_keeps_its_data_outside_the_install_folder():
    root = r"C:\Users\me\AppData\Local\Microsoft\WinGet\Packages\DrummingBird1.ClipForge_Microsoft.Winget.Source_8wekyb3d8bbwe\ClipForge-2.0.0-win64"
    dirs = launcher.managed_data_dirs(root, {"LOCALAPPDATA": r"C:\Users\me\AppData\Local"})
    assert dirs == {"CLIPFORGE_DATA_DIR": r"C:\Users\me\AppData\Local\ClipForge\data",
                    "CLIPFORGE_WORKSPACE_DIR": r"C:\Users\me\AppData\Local\ClipForge\workspace"}
    assert launcher.managed_data_dirs(root, {"LOCALAPPDATA": "x", "CLIPFORGE_DATA_DIR": "D:/mine"}) == {
        "CLIPFORGE_WORKSPACE_DIR": "x\\ClipForge\\workspace"}                       # מה שהמשתמש קבע גובר
    assert launcher.managed_data_dirs(r"D:\Apps\ClipForge-2.0.0-win64", {"LOCALAPPDATA": "x"}) == {}   # zip רגיל - ליד


def test_the_exe_runs_the_launcher_with_the_packages_pythonw():
    exe = _load("clipforge_exe", "dev/portable/clipforge_exe.py")
    assert exe.command("C:\\CF") == ["C:\\CF\\python\\pythonw.exe", "C:\\CF\\launcher.pyw"]


def test_the_release_builds_the_exe_and_puts_it_in_the_zip():
    workflow = open(os.path.join(PROJECT_ROOT, ".github", "workflows", "release.yml"), encoding="utf-8").read()
    assert "pyinstaller==" in workflow and "--launcher-exe build/launcher/ClipForge.exe" in workflow

def test_winget_manifests_point_at_the_release_zip_and_its_exe(tmp_path):
    wm = _load("make_winget_manifest", "dev/make_winget_manifest.py")
    assert wm.main(["--version", "2.0.0", "--sha256", "ab" * 32, "--out", str(tmp_path)]) == 0
    folder = tmp_path / "manifests" / "d" / "DrummingBird1" / "ClipForge" / "2.0.0"
    installer = (folder / "DrummingBird1.ClipForge.installer.yaml").read_text(encoding="utf-8")
    assert "InstallerSha256: " + "AB" * 32 in installer
    assert "releases/download/v2.0.0/ClipForge-2.0.0-win64.zip" in installer
    assert "RelativeFilePath: ClipForge-2.0.0-win64\\ClipForge.exe" in installer
    assert sorted(p.name for p in folder.iterdir()) == ["DrummingBird1.ClipForge.installer.yaml",
                                                        "DrummingBird1.ClipForge.locale.en-US.yaml", "DrummingBird1.ClipForge.yaml"]


# ---- 2.0.1: מהבדיקה המעמיקה ----

def test_winget_is_recognised_in_a_custom_location_too():
    from utils.shared import install_where
    default = r"C:\Users\me\AppData\Local\Microsoft\WinGet\Packages\DrummingBird1.ClipForge_Microsoft.Winget.Source_8wekyb3d8bbwe\ClipForge-2.0.1-win64"
    assert install_where.is_winget(default, locations=[])
    custom = r"D:\Apps\ClipForge\ClipForge-2.0.1-win64"
    assert not install_where.is_winget(custom, locations=[])
    assert install_where.is_winget(custom, locations=[r"D:\Apps\ClipForge"])       # מה ש-winget רשם ב-Uninstall
    assert not install_where.is_winget(r"D:\Apps\ClipForge2\x", locations=[r"D:\Apps\ClipForge"])
    env = {"LOCALAPPDATA": r"C:\Users\me\AppData\Local"}
    moved = launcher.managed_data_dirs(custom, env, is_winget=lambda root: True)
    assert moved["CLIPFORGE_DATA_DIR"] == r"C:\Users\me\AppData\Local\ClipForge\data"
    assert launcher.managed_data_dirs(custom, env, is_winget=lambda root: False) == {}
    assert launcher.managed_data_dirs(custom, {**env, "CLIPFORGE_DATA_DIR": "X:/mine"}, is_winget=lambda root: True) == {
        "CLIPFORGE_WORKSPACE_DIR": r"C:\Users\me\AppData\Local\ClipForge\workspace"}


def test_a_new_winget_data_folder_starts_in_the_layout_by_topic(tmp_path):
    """17.11.2026: data_paths לא מאמץ את המבנה לפי נושא כש-CLIPFORGE_DATA_DIR מוגדר, ובהתקנת winget הלאנצ'ר הוא שמגדיר אותו -
    התקנה חדשה התחילה במבנה השטוח. הלאנצ'ר מסמן את התיקייה שבחר; תיקייה שהמשתמש קבע, או אחת עם קבצים ישנים, לא משתנה."""
    from utils.shared import data_paths
    new = tmp_path / "ClipForge" / "data"
    assert launcher.adopt_managed_layout({"CLIPFORGE_DATA_DIR": str(new)}) is True
    assert data_paths.migrated(str(new)) and (new / "security").is_dir()
    assert launcher.adopt_managed_layout({"CLIPFORGE_DATA_DIR": str(new)}) is False          # כבר מסומנת
    assert launcher.adopt_managed_layout({"CLIPFORGE_WORKSPACE_DIR": str(tmp_path / "w")}) is False   # את data קבע המשתמש
    old = tmp_path / "old"
    old.mkdir()
    (old / "web_app_token.txt").write_text("t", encoding="utf-8")                           # קובץ במבנה השטוח הישן
    assert launcher.adopt_managed_layout({"CLIPFORGE_DATA_DIR": str(old)}) is False
    assert not data_paths.migrated(str(old))


def test_scoop_is_recognised_in_a_custom_root_too(tmp_path):
    from utils.shared import install_where, update_checker
    app = tmp_path / "MyScoop" / "apps" / "clipforge" / "2.0.1"
    app.mkdir(parents=True)
    assert not install_where.is_scoop(str(app))
    for name in ("shims", "buckets"):
        (tmp_path / "MyScoop" / name).mkdir()
    assert install_where.is_scoop(str(app)) and update_checker.install_kind(str(app)) == "scoop"
    assert install_where.is_scoop(r"C:\Users\me\scoop\apps\clipforge\current")


def test_the_users_connection_files_survive_an_update(tmp_path):
    # .env והחיבור ליוטיוב יושבים בתיקיית ההתקנה. Scoop ו-winget מחליפים אותה בכל עדכון - וכל עדכון מחק את החיבורים.
    import json

    from utils.shared import install_files
    data = tmp_path / "data"
    old, new = tmp_path / "ClipForge-2.0.1-win64", tmp_path / "ClipForge-2.0.2-win64"
    for root, version in ((old, "2.0.1"), (new, "2.0.2")):
        root.mkdir()
        (root / "portable.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (old / ".env").write_text("DISCORD_TOKEN=abc", encoding="utf-8")
    (old / "youtube_token.json").write_text("{}", encoding="utf-8")
    assert install_files.sync(str(old), str(data)) == {".env": "saved", "youtube_token.json": "saved"}
    assert install_files.sync(str(old), str(data)) == {}                           # אין מה לעדכן
    assert install_files.sync(str(new), str(data)) == {".env": "restored", "youtube_token.json": "restored"}
    assert (new / ".env").read_text(encoding="utf-8") == "DISCORD_TOKEN=abc"
    (new / "youtube_token.json").unlink()                                          # המשתמש ניתק את יוטיוב
    assert install_files.sync(str(new), str(data)) == {"youtube_token.json": "dropped"}
    assert install_files.sync(str(new), str(data)) == {} and not (new / "youtube_token.json").exists()
    (new / ".env").write_text("DISCORD_TOKEN=changed", encoding="utf-8")
    os.utime(new / ".env", (time.time() + 5, time.time() + 5))
    assert install_files.sync(str(new), str(data)) == {".env": "saved"}
    checkout = tmp_path / "git_checkout"
    checkout.mkdir()
    (checkout / ".env").write_text("X=1", encoding="utf-8")
    assert install_files.sync(str(checkout), str(tmp_path / "data2")) == {} and not (tmp_path / "data2").exists()   # שכפול git: לא נוגעים
    from utils.shared import data_paths
    assert "install_files" in data_paths.BACKUP_SKIP_DIRS                           # הסודות לא נכנסים לקובץ הגיבוי


def test_the_launcher_does_not_open_something_that_is_not_this_version():
    # 2.0.0: ה-launcher פתח בדפדפן כל מה שענה בפורט - גם ClipForge ישן שנשאר לרוץ אחרי עדכון, והגרסה החדשה לא עלתה
    same = {"clipforge": True, "version": "2.0.1"}
    assert launcher.already_running_text("he", same, "2.0.1") is None
    assert launcher.already_running_text("he", same, "") is None                    # שכפול בלי portable.json
    older = launcher.already_running_text("he", {"clipforge": True, "version": "2.0.0"}, "2.0.1")
    assert "2.0.0" in older and "מגש" in older
    assert "earlier" in launcher.already_running_text("en", {"clipforge": True, "version": ""}, "2.0.1")   # 2.0.0 לא דיווח גרסה
    assert "8878" in launcher.already_running_text("en", {"clipforge": False, "version": ""}, "2.0.1")
    assert launcher.running_app(port=1, timeout=0.2) == {"clipforge": False, "version": ""}
