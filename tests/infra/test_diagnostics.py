# tests/infra/test_diagnostics.py
#
# רגרסיה: _check_disk_space() (וכמה בדיקות אחרות) מחזיר שם-בדיקה עברי טהור
# ("שטח פנוי בכונן הפרויקט") שמוצג ביחד עם אייקון ✅/❌ ב-gui_manager.pyw
# (open_diagnostics_dialog) - לא לבד. אם t() היה הופך את השם כבר כאן (כמו
# שהיה), הרכבתו מחדש עם אייקון+fix_hebrew_word_order בגוי מנפח הופכת אותו
# פעמיים (=מבטלת) במקום פעם אחת - בדיוק כמו הבאג שתוקן ב-get_script_metadata().
import os
import sys


import utils.shared.diagnostics as diagnostics_module
from tests.media_support import needs_ffmpeg
from utils.shared.i18n import fix_hebrew_word_order
from utils.shared.state import state


def test_pure_hebrew_check_name_is_not_pre_reversed(monkeypatch):
    # סבב ייצוב: רק השם - קודם הטסט הריץ את כל הבדיקות האמיתיות (41 שניות) בשביל לבדוק שם אחד
    monkeypatch.setattr(state, "language", "he")
    assert diagnostics_module._check_disk_space()[0] == "שטח פנוי בכונן הפרויקט"  # לא הפוך


def test_combining_check_name_with_icon_displays_correctly(monkeypatch):
    # מדמה בדיוק את gui_manager.pyw's open_diagnostics_dialog: icon + name,
    # ואז fix_hebrew_word_order *פעם אחת* על המחרוזת המורכבת.
    monkeypatch.setattr(state, "language", "he")
    name = "שטח פנוי בכונן הפרויקט"
    icon = "✅"

    stored_for_tk = fix_hebrew_word_order(f"{icon} {name}")
    # מדמה את הבאג של Tk (הופך שוב את סדר המילים בזמן רינדור) כדי לוודא
    # שהתוצאה הסופית-על-המסך נכונה
    displayed_on_screen = " ".join(reversed(stored_for_tk.split(" ")))

    assert displayed_on_screen == f"{icon} {name}"


def test_check_workspace_ok_when_writable(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics_module, "WORKSPACE_DIR", str(tmp_path / "workspace"))
    _name, ok, _detail = diagnostics_module._check_workspace()
    assert ok is True
    assert os.path.isdir(tmp_path / "workspace")


def test_check_workspace_fails_when_path_is_a_file_not_a_directory(tmp_path, monkeypatch):
    # os.makedirs(exist_ok=True) על נתיב שכבר תפוס ע"י קובץ (לא תיקייה) חייב
    # להיכשל בבירור, לא ליצור בטעות תיקייה עם שם אחר/להתעלם מהבעיה.
    blocked_path = tmp_path / "workspace"
    blocked_path.write_text("not a directory")
    monkeypatch.setattr(diagnostics_module, "WORKSPACE_DIR", str(blocked_path))
    _name, ok, _detail = diagnostics_module._check_workspace()
    assert ok is False


def test_check_render_lock_ok_when_free(monkeypatch):
    monkeypatch.setattr(diagnostics_module, "get_render_lock_status", lambda: None)
    _name, ok, _detail = diagnostics_module._check_render_lock()
    assert ok is True


def test_check_render_lock_ok_when_held_but_healthy(monkeypatch):
    monkeypatch.setattr(diagnostics_module, "get_render_lock_status", lambda: {"pid": 1234, "age_seconds": 30, "is_stale": False})
    _name, ok, _detail = diagnostics_module._check_render_lock()
    assert ok is True


def test_check_render_lock_fails_when_stale(monkeypatch):
    monkeypatch.setattr(diagnostics_module, "get_render_lock_status", lambda: {"pid": 1234, "age_seconds": 99999, "is_stale": True})
    _name, ok, detail = diagnostics_module._check_render_lock()
    assert ok is False
    assert "1234" in detail


# --- _check_orphaned_ffmpeg_processes (item: system health dashboard) ---

class _FakeProcess:
    ppid_calls: list = []

    def __init__(self, pid, name, ppid):
        self.pid = pid
        self.info = {"name": name}
        self._ppid = ppid

    def ppid(self):
        _FakeProcess.ppid_calls.append(self.pid)
        if isinstance(self._ppid, Exception):
            raise self._ppid
        return self._ppid


def test_check_orphaned_ffmpeg_processes_asks_the_parent_only_of_ffmpeg(monkeypatch):
    # סבב ייצוב: ב-Windows כל ppid() בונה מפה של כל התהליכים (~16ms) - ppid לכל ~700 תהליכים לקח 11-17 שניות
    _FakeProcess.ppid_calls = []
    procs = [_FakeProcess(1, "notepad.exe", 9), _FakeProcess(100, "FFmpeg.exe", 50), _FakeProcess(2, "explorer.exe", 9)]
    seen_attrs = []
    monkeypatch.setattr(diagnostics_module.psutil, "process_iter", lambda attrs: (seen_attrs.append(attrs), iter(procs))[1])
    monkeypatch.setattr(diagnostics_module.psutil, "pid_exists", lambda pid: False)
    _name, ok, detail = diagnostics_module._check_orphaned_ffmpeg_processes()
    assert seen_attrs == [["name"]] and _FakeProcess.ppid_calls == [100]
    assert ok is False and "100" in detail


def test_check_orphaned_ffmpeg_processes_skips_a_process_that_ended_or_is_denied(monkeypatch):
    psutil = diagnostics_module.psutil
    procs = [_FakeProcess(100, "ffmpeg.exe", psutil.NoSuchProcess(100)), _FakeProcess(101, "ffprobe.exe", psutil.AccessDenied(101))]
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: iter(procs))
    assert diagnostics_module._check_orphaned_ffmpeg_processes()[1] is True


@needs_ffmpeg
def test_a_real_orphaned_ffmpeg_is_still_found(monkeypatch):
    # ffmpeg אמיתי שההורה שלו יצא (תהליך ביניים שמפעיל אותו ויוצא מיד) - בלי mock של psutil
    import subprocess
    import psutil
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    starter = "import subprocess, sys\np = subprocess.Popen(sys.argv[1:], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\nprint(p.pid)"
    cmd = [get_ffmpeg_exe(), "-v", "quiet", "-re", "-f", "lavfi", "-i", "anullsrc", "-t", "60", "-f", "null", "-"]   # -re: רץ בזמן אמת, לא נגמר מיד
    launched = subprocess.run([sys.executable, "-c", starter, *cmd], capture_output=True, text=True, timeout=60, check=True)
    orphan = psutil.Process(int(launched.stdout.strip()))
    try:
        assert orphan.is_running() and not psutil.pid_exists(orphan.ppid())
        _name, ok, detail = diagnostics_module._check_orphaned_ffmpeg_processes()
        assert ok is False and str(orphan.pid) in detail
    finally:
        orphan.kill()


def test_check_orphaned_ffmpeg_processes_ok_when_none_running(monkeypatch):
    monkeypatch.setattr(diagnostics_module.psutil, "process_iter", lambda attrs: iter([]))
    _name, ok, _detail = diagnostics_module._check_orphaned_ffmpeg_processes()
    assert ok is True


def test_check_orphaned_ffmpeg_processes_ok_when_parent_alive(monkeypatch):
    procs = [_FakeProcess(100, "ffmpeg.exe", 50)]
    monkeypatch.setattr(diagnostics_module.psutil, "process_iter", lambda attrs: iter(procs))
    monkeypatch.setattr(diagnostics_module.psutil, "pid_exists", lambda pid: True)
    _name, ok, _detail = diagnostics_module._check_orphaned_ffmpeg_processes()
    assert ok is True


def test_check_orphaned_ffmpeg_processes_fails_when_parent_dead(monkeypatch):
    procs = [_FakeProcess(100, "ffmpeg.exe", 50)]
    monkeypatch.setattr(diagnostics_module.psutil, "process_iter", lambda attrs: iter(procs))
    monkeypatch.setattr(diagnostics_module.psutil, "pid_exists", lambda pid: False)
    _name, ok, detail = diagnostics_module._check_orphaned_ffmpeg_processes()
    assert ok is False
    assert "100" in detail


def test_check_orphaned_ffmpeg_processes_also_checks_ffprobe(monkeypatch):
    procs = [_FakeProcess(101, "ffprobe.exe", 50)]
    monkeypatch.setattr(diagnostics_module.psutil, "process_iter", lambda attrs: iter(procs))
    monkeypatch.setattr(diagnostics_module.psutil, "pid_exists", lambda pid: False)
    _name, ok, detail = diagnostics_module._check_orphaned_ffmpeg_processes()
    assert ok is False
    assert "101" in detail


def test_check_orphaned_ffmpeg_processes_ignores_unrelated_processes(monkeypatch):
    procs = [_FakeProcess(200, "notepad.exe", 1)]
    monkeypatch.setattr(diagnostics_module.psutil, "process_iter", lambda attrs: iter(procs))
    monkeypatch.setattr(diagnostics_module.psutil, "pid_exists", lambda pid: False)
    _name, ok, _detail = diagnostics_module._check_orphaned_ffmpeg_processes()
    assert ok is True


def test_check_orphaned_ffmpeg_processes_skipped_without_psutil(monkeypatch):
    monkeypatch.setattr(diagnostics_module, "psutil", None)
    _name, ok, _detail = diagnostics_module._check_orphaned_ffmpeg_processes()
    assert ok is True


def test_check_orphaned_ffmpeg_processes_handles_scan_failure(monkeypatch):
    def _boom(attrs):
        raise RuntimeError("access denied")
    monkeypatch.setattr(diagnostics_module.psutil, "process_iter", _boom)
    _name, ok, detail = diagnostics_module._check_orphaned_ffmpeg_processes()
    assert ok is False
    assert "access denied" in detail


# --- _check_credentials_configured (item: credential vault health-check) ---

def test_check_credentials_configured_is_always_ok(monkeypatch):
    # "לא מוגדר" הוא מצב לגיטימי (למשל אף פעם לא הפעילו סקריפט שדורש Twitch) -
    # לא כשל, לכן ok=True תמיד, בלי קשר למה בפועל מוגדר.
    monkeypatch.setattr(diagnostics_module, "check_credentials_configured", lambda: {"GEMINI_API_KEY": False, "TWITCH_CLIENT_ID": False, "TWITCH_CLIENT_SECRET": False, "DISCORD_TOKEN": False})
    _name, ok, _detail = diagnostics_module._check_credentials_configured()
    assert ok is True


def test_check_credentials_configured_shows_which_are_set(monkeypatch):
    monkeypatch.setattr(diagnostics_module, "check_credentials_configured", lambda: {"GEMINI_API_KEY": True, "TWITCH_CLIENT_ID": False, "TWITCH_CLIENT_SECRET": False, "DISCORD_TOKEN": True})
    _name, _ok, detail = diagnostics_module._check_credentials_configured()
    assert "✅ GEMINI_API_KEY" in detail
    assert "➖ TWITCH_CLIENT_ID" in detail
    assert "✅ DISCORD_TOKEN" in detail


def test_check_data_json_files_reports_corrupt_files_read_only(tmp_path, monkeypatch):
    (tmp_path / "ok.json").write_text('{"a": 1}', encoding="utf-8")
    monkeypatch.setattr(diagnostics_module, "DATA_DIR", str(tmp_path))
    assert diagnostics_module._check_data_json_files()[1:] == (True, "1 קבצים תקינים")

    broken = tmp_path / "settings.json"
    broken.write_text('{"a": ', encoding="utf-8")
    _name, ok, detail = diagnostics_module._check_data_json_files()

    assert ok is False and "settings.json" in detail and "לא שונו" in detail
    assert broken.read_text(encoding="utf-8") == '{"a": '          # לא תוקן ולא נמחק


def test_check_data_json_files_ok_when_folder_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics_module, "DATA_DIR", str(tmp_path / "nope"))
    assert diagnostics_module._check_data_json_files()[1] is True


def test_gemini_key_check_gives_a_clear_hebrew_message(monkeypatch):
    monkeypatch.setattr(diagnostics_module, "check_credentials_configured", lambda: {"GEMINI_API_KEY": False})
    _name, ok, detail = diagnostics_module._check_gemini_key()
    assert ok is False and "GEMINI_API_KEY" in detail and "חסר" in detail

    monkeypatch.setattr(diagnostics_module, "check_credentials_configured", lambda: {"GEMINI_API_KEY": True})
    assert diagnostics_module._check_gemini_key()[1] is True


def test_startup_problems_lists_failures_and_survives_a_crashing_check(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(diagnostics_module, "WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setattr(diagnostics_module, "check_credentials_configured", lambda: {"GEMINI_API_KEY": False})
    monkeypatch.setattr(diagnostics_module, "_check_ffmpeg", lambda: ("FFmpeg", False, "לא נמצא (חיפש: ffmpeg)"))
    monkeypatch.setattr(diagnostics_module, "_check_ffprobe", lambda: 1 / 0)

    problems = diagnostics_module.startup_problems()

    assert any("FFmpeg" in p and "לא נמצא" in p for p in problems)
    assert any("_check_ffprobe" in p and "הבדיקה עצמה נכשלה" in p for p in problems)
    assert any("GEMINI_API_KEY" in p for p in problems)
    assert all(p.startswith("⚠️") for p in problems)


def test_print_startup_health_prints_ok_line_or_each_problem(monkeypatch):
    lines = []
    monkeypatch.setattr(diagnostics_module, "startup_problems", lambda: [])
    assert diagnostics_module.print_startup_health(lines.append) == [] and "✅" in lines[0]

    lines.clear()
    monkeypatch.setattr(diagnostics_module, "startup_problems", lambda: ["⚠️ a: b", "⚠️ c: d"])
    diagnostics_module.print_startup_health(lines.append)
    assert "2" in lines[0] and lines[1:] == ["   ⚠️ a: b", "   ⚠️ c: d"]


def test_startup_checks_never_write_to_the_data_folder():
    assert "_check_database" not in diagnostics_module.STARTUP_CHECKS