# tests/web/test_web_launcher_script.py
#
# dev/_web_launcher_impl.bat (WebLauncher.vbs): לחיצה כפולה לא מפעילה שני שרתים. מנעול mkdir (data\.web_launcher.lock,
# ישן אחרי 90 שניות), שרת שכבר מאזין על 8878 = פותחים אותו עם הטוקן הקיים, והטוקן נקרא רק אחרי שהפורט עונה - web_app.py כותב
# אותו אחרי שתפס את הפורט ולפני שהוא מאזין (tests/web/test_web_app_single_instance.py). בדיקה של הסקריפט עצמו, בלי להריץ אותו.
import os
import subprocess
import re

from tests import PROJECT_ROOT

LAUNCHER = os.path.join(PROJECT_ROOT, "dev", "_web_launcher_impl.bat")


def _code_lines():
    with open(LAUNCHER, encoding="utf-8", newline="") as f:
        raw = f.read()
    return raw, [line.strip() for line in raw.split("\r\n") if line.strip() and not line.strip().upper().startswith("REM")]


def test_the_launcher_keeps_crlf_line_endings():
    raw, _lines = _code_lines()
    assert raw.count("\n") == raw.count("\r\n") > 50   # cmd.exe וקפיצות goto שבורות עם LF בלבד


def test_lock_then_running_check_then_start_then_token_after_the_port():
    _raw, lines = _code_lines()
    index = {name: next(i for i, line in enumerate(lines) if re.search(pattern, line)) for name, pattern in {
        "lock": r'^mkdir "%LOCK_DIR%"', "running_check": r"TcpClient\('127\.0\.0\.1', 8878\)",
        "reuse_token": r'set /p EXISTING_TOKEN=<"%TOKEN_FILE%"', "start": r"pythonw\.exe\" src\\entrypoints\\web_app\.py",
        "port_ready": r"^:port_ready$", "read_token": r'^set /p TOKEN=<"%TOKEN_FILE%"'}.items()}
    assert index["lock"] < index["running_check"] < index["reuse_token"] < index["start"] < index["port_ready"] < index["read_token"]


def test_every_exit_after_taking_the_lock_releases_it():
    _raw, lines = _code_lines()
    start = lines.index(":lock_acquired")
    for i, line in enumerate(lines[start:], start):
        if line.lower().startswith("exit /b"):
            assert any(lines[j].startswith('rmdir "%LOCK_DIR%"') for j in range(max(start, i - 8), i)), lines[i - 3:i + 1]
    assert any(line.startswith('rmdir "%LOCK_DIR%"') for line in lines[lines.index(":port_ready"):])


def test_the_lock_folder_is_gitignored():
    # 30.10.2026: data/ כולה ב-.gitignore - בודקים את התוצאה (git check-ignore), לא שורה מסוימת בקובץ
    result = subprocess.run(["git", "check-ignore", "-q", "data/.web_launcher.lock/"], cwd=PROJECT_ROOT, capture_output=True)
    assert result.returncode == 0
