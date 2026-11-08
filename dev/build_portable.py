# dev/build_portable.py
#
# 30.10.2026 (הכנה להפצה ציבורית, פריט 3): בונה dist/ClipForge-<גרסה>-win64.zip - חבילה ניידת ל-Windows שלא צריכה Python,
# uv או git אצל המשתמש. פותחים את ה-zip ולוחצים על ClipForge.vbs.
#
# מה בפנים (ClipForge-<גרסה>-win64/):
#   ClipForge.vbs, launcher.pyw   - מפעילים את אפליקציית הדפדפן ופותחים אותה (dev/portable/)
#   python/                       - CPython מההתקנה שמריצה את הסקריפט (sys.base_prefix), עם ספריות זמן הריצה מ-uv.lock
#                                   (בלי קבוצת dev, ובלי pyautogui ותלויות ה-GPL שלו - רק כלי פיתוח משתמש בהם)
#   ffmpeg/                       - ffmpeg.exe + ffprobe.exe + הרישיון שלהם, מ---ffmpeg (תיקייה או zip של build). בלי --ffmpeg:
#                                   ה-build שמוצמד ב-release.yml (FFMPEG_ZIP), מ-CLIPFORGE_FFMPEG או מ-media/ffmpeg/ מעל הריפו
#   src/, my_scripts/, assets/, docs/, README.md, LICENSE, THIRD_PARTY_NOTICES.md, CHANGELOG.md - הקבצים שבמעקב ב-HEAD
#   portable.json                 - הסימן: "יש גרסה חדשה" מציג קישור ל-Release במקום git pull (utils/shared/update_checker)
# ליד ה-zip: SHA256SUMS.txt בפורמט של sha256sum - release.yml מצרף אותו ל-Release, ומי שהוריד בודק איתו את ה-zip.
# ‏data/ ו-workspace/ לא בחבילה - הם נוצרים בהפעלה הראשונה, ליד ClipForge.vbs. בלי .venv, ‏AGENTS.md, ‏docs/handoff ו-docs/history.
#
#   uv run python dev/build_portable.py                    # ffmpeg: ה-zip המוצמד, אחרי בדיקת SHA-256
#   uv run python dev/build_portable.py --ffmpeg C:\Downloads\ffmpeg-build --offline   # build אחר; בלי רשת: הכל מ-cache של uv
import argparse
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTABLE_SRC = os.path.join(ROOT, "dev", "portable")

# מה נכנס מהקבצים שבמעקב (תיקייה עם "/" בסוף), ומה לא - גם אם נמצא בתוך מה שנכנס
APP_INCLUDE = ("src/", "my_scripts/", "assets/", "docs/", "README.md", "README.he.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md",
               ".env.example")
APP_EXCLUDE = ("docs/handoff/", "docs/history/", "my_scripts/tools/check_pos.py")
# הספריות שלא נכנסות: pyautogui ותלויותיו (MouseInfo ו-PyMsgBox הן GPLv3+) - רק my_scripts/tools/check_pos.py משתמש בהן
EXCLUDED_DISTS = ("pyautogui", "mouseinfo", "pymsgbox", "pyscreeze", "pytweening", "pygetwindow", "pyrect")
# 30.10.2026: מה שזמן הריצה לא צריך מתוך site-packages (החבילה ירדה מ-280MB): מסמכי ה-discovery של שירותי Google שהקוד לא
# בונה - רק youtube v3 ו-youtubeAnalytics v2 (utils/bot/youtube_uploader, youtube_analytics); build() קורא אותם מהחבילה
# (static discovery), בלי רשת - תיקיות הטסטים של הספריות עצמן (tests/, test/), וקובצי .pyi (טיפוסים לעורכי קוד)
GOOGLE_DISCOVERY_DIR = os.path.join("googleapiclient", "discovery_cache", "documents")
GOOGLE_DISCOVERY_KEEP = ("youtube.v3.json", "youtubeAnalytics.v2.json")
LIBRARY_TEST_DIRS = ("tests", "test")
# מההתקנה של Python: רק זמן הריצה. site-packages מגיע מ-uv sync, לא מההתקנה של המפתח
RUNTIME_SKIP_DIRS = {"site-packages", "test", "tests", "idlelib", "ensurepip", "turtledemo", "__pycache__", "Scripts", "Tools",
                     "Doc", "include", "libs"}
# מה ש-ffmpeg חייב לכלול: הקוד מקודד ב-libx264 בלי NVENC, מייצב ב-vidstab, ממיר HDR ב-zscale וכותב טקסט ב-drawtext
REQUIRED_ENCODERS = ("libx264",)
REQUIRED_FILTERS = ("vidstabdetect", "vidstabtransform", "zscale", "drawtext")
# 30.10.2026: ברירת המחדל של --ffmpeg - אותו build ש-.github/workflows/release.yml מוריד ובודק (gyan essentials, ‏GPLv3).
# CLIPFORGE_FFMPEG גובר; אחרת media/ffmpeg/<FFMPEG_DIR>/<FFMPEG_ZIP> בתיקיית הריפו או באחת שמעליה
FFMPEG_ZIP = "ffmpeg-9.0.2-essentials_build.zip"
FFMPEG_DIR = "9.0.2-essentials"
FFMPEG_SHA256 = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"
SHA256SUMS = "SHA256SUMS.txt"


def read_version(root=ROOT):
    text = open(os.path.join(root, "src", "utils", "shared", "version.py"), encoding="utf-8").read()
    return re.search(r'^APP_VERSION = "([^"]+)"', text, re.M).group(1)


def _match(rel, patterns):
    return any(rel == p or (p.endswith("/") and rel.startswith(p)) for p in patterns)


def wanted_app_file(rel):
    return _match(rel, APP_INCLUDE) and not _match(rel, APP_EXCLUDE)


def copy_app(dest, ref="HEAD", repo=ROOT):
    """הקבצים שבמעקב ב-ref שנכנסים לחבילה. git archive - בלי קבצים לא-במעקב, בלי data/ ו-workspace/ אמיתיים."""
    archive = subprocess.run(["git", "-C", repo, "archive", "--format=tar", ref], capture_output=True, check=True).stdout
    count = 0
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if member.isfile() and wanted_app_file(member.name):
                target = os.path.join(dest, *member.name.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with tar.extractfile(member) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                count += 1
    return count


def runtime_entries(python_home):
    """(מקור, יחסי) לכל קובץ של זמן הריצה בהתקנת Python: הקבצים בשורש (exe, dll, LICENSE), ‏DLLs/, ‏Lib/ ו-tcl/."""
    for name in sorted(os.listdir(python_home)):
        path = os.path.join(python_home, name)
        if os.path.isfile(path) and (name.lower().endswith((".exe", ".dll")) or name.upper().startswith("LICENSE")):
            if name.lower().endswith(".exe") and name.lower() not in ("python.exe", "pythonw.exe"):
                continue
            yield path, name
    for top in ("DLLs", "Lib", "tcl"):
        base = os.path.join(python_home, top)
        for current, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in RUNTIME_SKIP_DIRS]
            for name in files:
                if not name.endswith((".pyc", ".pyo")):
                    full = os.path.join(current, name)
                    yield full, os.path.relpath(full, python_home)


def excluded_files(site_packages, dists=EXCLUDED_DISTS):
    """הנתיבים (יחסית ל-site-packages, באותיות קטנות) של הספריות שלא נכנסות - לפי ה-RECORD של כל אחת."""
    skip = set()
    for name in os.listdir(site_packages):
        if not name.endswith(".dist-info"):
            continue
        dist = re.sub(r"[-_.]+", "-", name[:-len(".dist-info")].rsplit("-", 1)[0]).lower()
        if dist not in dists:
            continue
        skip.add(os.path.normcase(name))
        record = os.path.join(site_packages, name, "RECORD")
        if os.path.isfile(record):
            for line in open(record, encoding="utf-8"):
                rel = line.split(",", 1)[0].strip()
                if rel and not rel.startswith(".."):
                    skip.add(os.path.normcase(os.path.normpath(rel)))
    return skip


def copy_site_packages(env_site, dest_site):
    skip = excluded_files(env_site)
    discovery = os.path.normcase(GOOGLE_DISCOVERY_DIR)
    copied = 0
    for current, dirs, files in os.walk(env_site):
        rel_dir = os.path.relpath(current, env_site)
        # tests/ של ספרייה - רק בתוך חבילה (לא בשורש site-packages), אף פעם לא חלק מזמן הריצה
        dirs[:] = [d for d in dirs if d != "__pycache__" and not (rel_dir != "." and d in LIBRARY_TEST_DIRS)
                   and os.path.normcase(os.path.normpath(os.path.join(rel_dir, d))) not in skip]
        in_discovery = os.path.normcase(os.path.normpath(rel_dir)) == discovery
        for name in files:
            rel = os.path.normpath(os.path.join(rel_dir, name))
            if os.path.normcase(rel) in skip or name.startswith("_virtualenv") or name.endswith((".pyc", ".pyo", ".pyi")):
                continue
            if in_discovery and name not in GOOGLE_DISCOVERY_KEEP:
                continue
            target = os.path.join(dest_site, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(os.path.join(current, name), target)
            copied += 1
    return copied


def missing_ffmpeg_features(encoders_text, filters_text):
    """מה שחסר ב-ffmpeg מתוך REQUIRED_* - לפי הפלט של -encoders ושל -filters."""
    def names(text):
        return {parts[1] for parts in (line.split() for line in text.splitlines()) if len(parts) > 1}
    return sorted(set(REQUIRED_ENCODERS) - names(encoders_text)) + sorted(set(REQUIRED_FILTERS) - names(filters_text))


def default_ffmpeg(root=ROOT, environ=None):
    """ה-zip של ffmpeg כשאין --ffmpeg: CLIPFORGE_FFMPEG, או media/ffmpeg/<FFMPEG_DIR>/<FFMPEG_ZIP> מעל root. None = לא נמצא."""
    environ = os.environ if environ is None else environ
    if environ.get("CLIPFORGE_FFMPEG"):
        return environ["CLIPFORGE_FFMPEG"]
    current = os.path.abspath(root)
    while True:
        candidate = os.path.join(current, "media", "ffmpeg", FFMPEG_DIR, FFMPEG_ZIP)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_pinned_zip(path):
    """ה-zip של ברירת המחדל חייב להיות בדיוק הקובץ ש-release.yml מצמיד - אחרת החבילה המקומית שונה מזו של ה-Release."""
    if sha256_of(path) != FFMPEG_SHA256:
        raise SystemExit(f"ה-SHA-256 של {path} לא תואם ל-{FFMPEG_ZIP} המוצמד ({FFMPEG_SHA256[:12]}...). להוריד אותו מחדש.")


def _ffmpeg_source(path, work):
    """תיקייה שיש בה bin/ffmpeg.exe - מ-zip (נפתח לתיקייה זמנית) או מתיקייה קיימת."""
    if zipfile.is_zipfile(path):
        out = tempfile.mkdtemp(prefix="ffmpeg_", dir=work)
        with zipfile.ZipFile(path) as zf:
            zf.extractall(out)
        path = out
    for current, _dirs, files in os.walk(path):
        if "ffmpeg.exe" in files and os.path.basename(current) == "bin":
            return os.path.dirname(current)
    raise SystemExit(f"אין bin/ffmpeg.exe תחת {path}")


def copy_ffmpeg(source, dest, work):
    home = _ffmpeg_source(source, work)
    os.makedirs(os.path.join(dest, "bin"), exist_ok=True)
    for exe in ("ffmpeg.exe", "ffprobe.exe"):
        src = os.path.join(home, "bin", exe)
        if not os.path.isfile(src):
            raise SystemExit(f"חסר {exe} ב-{home}\\bin")
        shutil.copy2(src, os.path.join(dest, "bin", exe))
    notices = [n for n in os.listdir(home) if n.upper().startswith(("LICENSE", "COPYING", "README"))]
    if not any(n.upper().startswith(("LICENSE", "COPYING")) for n in notices):
        raise SystemExit(f"אין קובץ רישיון ל-ffmpeg ב-{home} - בנייה GPL חייבת לצאת עם הרישיון שלה")
    for name in notices:
        shutil.copy2(os.path.join(home, name), os.path.join(dest, name))
    exe = os.path.join(dest, "bin", "ffmpeg.exe")
    run = [exe, "-hide_banner"]
    encoders = subprocess.run(run + ["-encoders"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    filters = subprocess.run(run + ["-filters"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    missing = missing_ffmpeg_features(encoders, filters)
    if missing:
        raise SystemExit(f"ל-ffmpeg הזה חסר מה שהקוד צריך: {', '.join(missing)}. לבחור build עם libx264, vidstab ו-zscale.")
    return subprocess.run(run + ["-version"], capture_output=True, text=True).stdout.splitlines()[0]


def sync_runtime_env(env_dir, python_exe, offline):
    """סביבה נפרדת עם ספריות זמן הריצה מ-uv.lock בדיוק (--frozen), בלי dev ובלי הפרויקט עצמו."""
    cmd = ["uv", "sync", "--frozen", "--no-dev", "--no-install-project", "--python", python_exe]
    if offline:
        cmd.append("--offline")
    subprocess.run(cmd, cwd=ROOT, env={**os.environ, "UV_PROJECT_ENVIRONMENT": env_dir}, check=True)
    return os.path.join(env_dir, "Lib", "site-packages")


def smoke_check(stage):
    """הפייתון של החבילה, מבודד כמו ב-launcher.pyw, מייבא את האפליקציה - חסר מודול = נכשל כאן, לא אצל המשתמש.
    30.10.2026: כמו הפעלה ראשונה אמיתית - בלי CLIPFORGE_DATA_DIR, כך ש-data/ של החבילה נוצר ומאומץ למבנה לפי נושא, וכותבים
    את קובץ הטוקן (הקריסה של ה-zip הראשון: data/security לא נוצר). data/ שנוצר כאן נמחק לפני ה-zip."""
    base_env = {k: v for k, v in os.environ.items()
                if k.upper() not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CLIPFORGE_DATA_DIR")}
    data_dir = os.path.join(stage, "data")
    with tempfile.TemporaryDirectory() as tmp:
        env = {**base_env, "PYTHONNOUSERSITE": "1", "PYTHONIOENCODING": "utf-8", "CLIPFORGE_WORKSPACE_DIR": os.path.join(tmp, "workspace")}
        # גם: הלקוחות של YouTube נבנים מהמסמכים שנשארו בחבילה, בלי רשת (static discovery) - אם חסר מסמך, build נכשל כאן
        code = ("import sys, os; sys.path.insert(0, os.path.join(os.getcwd(), 'src')); import entrypoints.web_app as W; "
                "W._persist_token('smoke-check'); from utils.shared import data_paths as D; print('layout=' + str(D.migrated())); "
                "from googleapiclient.discovery import build; "
                "[build(s, v, developerKey='offline-check', static_discovery=True) for s, v in (('youtube', 'v3'), ('youtubeAnalytics', 'v2'))]; "
                "print('google=ok'); "
                "from utils.shared import update_checker as U; print('portable=' + str(U.is_portable(W.BASE_DIR)))")
        try:
            result = subprocess.run([os.path.join(stage, "python", "python.exe"), "-c", code], cwd=stage, env=env,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
            first_run_ok = "layout=True" in result.stdout   # data_paths.migrated() בתוך החבילה - data/ אומץ למבנה לפי נושא
        finally:
            shutil.rmtree(data_dir, ignore_errors=True)  # safe: the data/ this smoke run just created inside our own stage folder
    if result.returncode != 0 or "portable=True" not in result.stdout or "google=ok" not in result.stdout or not first_run_ok:
        raise SystemExit("בדיקת ההפעלה הראשונה בפייתון של החבילה נכשלה:\n" + (result.stderr or result.stdout)[-3000:])


def write_zip(stage, zip_path):
    base = os.path.basename(stage)
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    tmp = zip_path + ".partial"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for current, _dirs, files in os.walk(stage):
            for name in sorted(files):
                full = os.path.join(current, name)
                zf.write(full, os.path.join(base, os.path.relpath(full, stage)))
    os.replace(tmp, zip_path)  # safe: replaces only our own build output in dist/ with the zip just written


def write_checksums(zip_path):
    """SHA256SUMS.txt ליד ה-zip, בפורמט של sha256sum ("<hash>  <שם>", ‏LF) - `sha256sum -c SHA256SUMS.txt` בודק אותו.
    מחזיר את ה-hash."""
    digest = sha256_of(zip_path)
    with open(os.path.join(os.path.dirname(zip_path), SHA256SUMS), "wb") as f:
        f.write(f"{digest}  {os.path.basename(zip_path)}\n".encode("utf-8"))
    return digest


def main(argv=None):
    parser = argparse.ArgumentParser(description="בונה dist/ClipForge-<גרסה>-win64.zip - חבילה ניידת ל-Windows")
    parser.add_argument("--ffmpeg", help=f"תיקיית build של ffmpeg (עם bin/ffmpeg.exe) או ה-zip שלו. ברירת מחדל: {FFMPEG_ZIP}, "
                                         f"מ-CLIPFORGE_FFMPEG או מ-media/ffmpeg/{FFMPEG_DIR}/ מעל הריפו")
    parser.add_argument("--python-home", default=sys.base_prefix, help="התקנת CPython להעתקה (ברירת מחדל: זו שמריצה את הסקריפט)")
    parser.add_argument("--out", default=os.path.join(ROOT, "dist"), help="לאן לכתוב את ה-zip")
    parser.add_argument("--ref", default="HEAD", help="מאיזה commit לקחת את הקבצים (ברירת מחדל: HEAD)")
    parser.add_argument("--offline", action="store_true", help="uv sync בלי רשת - רק מה-cache")
    parser.add_argument("--keep-stage", action="store_true", help="להשאיר את תיקיית הבנייה ב-build/portable/")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ffmpeg = args.ffmpeg
    if not ffmpeg:
        ffmpeg = default_ffmpeg()
        if not ffmpeg:
            raise SystemExit(f"אין ffmpeg: להעביר --ffmpeg, או לשים את {FFMPEG_ZIP} ב-media/ffmpeg/{FFMPEG_DIR}/ מעל הריפו "
                             "(או להצביע עליו ב-CLIPFORGE_FFMPEG)")
        check_pinned_zip(ffmpeg)
    version = read_version()
    name = f"ClipForge-{version}-win64"
    work = os.path.join(ROOT, "build", "portable")
    stage = os.path.join(work, name)
    if os.path.exists(stage):
        shutil.rmtree(stage)  # safe: our own staging folder under build/ (gitignored), rebuilt from scratch every run
    os.makedirs(stage)

    python_exe = os.path.join(args.python_home, "python.exe")
    print(f"[1/6] קבצי האפליקציה מ-{args.ref}: {copy_app(stage, args.ref)} קבצים")
    runtime = 0
    for src, rel in runtime_entries(args.python_home):
        target = os.path.join(stage, "python", rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(src, target)
        runtime += 1
    print(f"[2/6] Python מ-{args.python_home}: {runtime} קבצים")
    env_site = sync_runtime_env(os.path.join(work, "env"), python_exe, args.offline)
    copied = copy_site_packages(env_site, os.path.join(stage, "python", "Lib", "site-packages"))
    print(f"[3/6] ספריות זמן הריצה (uv.lock, בלי dev ובלי {', '.join(EXCLUDED_DISTS[:1])}...): {copied} קבצים")
    print(f"[4/6] ffmpeg: {copy_ffmpeg(ffmpeg, os.path.join(stage, 'ffmpeg'), work)}")
    for launcher in ("ClipForge.vbs", "launcher.pyw"):
        shutil.copy2(os.path.join(PORTABLE_SRC, launcher), os.path.join(stage, launcher))
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from utils.shared import release_info   # לא update_checker: הוא מייבא requests, ופה רץ הפייתון של ה-runner בלי ספריות הפרויקט
    with open(os.path.join(stage, release_info.PORTABLE_MARKER), "w", encoding="utf-8") as f:
        json.dump({"version": version, "built": datetime.date.today().isoformat(), "releases_url": release_info.RELEASES_PAGE_URL},
                  f, indent=2)
    smoke_check(stage)
    print("[5/6] בדיקת ייבוא בפייתון של החבילה: עברה")
    zip_path = os.path.join(args.out, name + ".zip")
    write_zip(stage, zip_path)
    digest = write_checksums(zip_path)
    print(f"[6/6] {zip_path} - {os.path.getsize(zip_path) / 1024 / 1024:.0f}MB, SHA-256 {digest} ({SHA256SUMS})")
    if not args.keep_stage:
        shutil.rmtree(stage)  # safe: our own staging folder under build/ - the zip above is the result
    return 0


if __name__ == "__main__":
    sys.exit(main())
