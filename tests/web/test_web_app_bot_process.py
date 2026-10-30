# tests/web/test_web_app_bot_process.py
#
# סבב ייצוב: _run_bot_process_loop ב-web_app.py מול תהליך אמיתי (main.py מזויף ב-tmp, לא הבוט): פלט שאינו UTF-8
# לא מפיל את הקורא, קוד היציאה של שגיאת הגדרה (CONFIG_ERROR_EXIT_CODE מ-main.py) עוצר בלי הפעלה מחדש, וקורא
# שנפל בזמן שהבוט עוד חי לא מפעיל עותק נוסף (שני בוטים על אותו טוקן - כך נמצא הבאג).
import os
import sys


from tests.web_app_support import _reset_bot_state, client, web_app  # noqa: E402


def _fake_main(tmp_path, monkeypatch, body):
    script = tmp_path / "fake_main.py"
    script.write_text("import os, sys, time\nrecord = open(sys.argv[0] + '.runs', 'a')\n" + body, encoding="utf-8")
    monkeypatch.setattr(web_app, "MAIN_PY_PATH", str(script))
    monkeypatch.setattr(web_app, "get_python_executable", lambda: sys.executable)
    return tmp_path / "fake_main.py.runs"


def _start_loop():
    _reset_bot_state()
    with web_app._bot_state_lock:
        web_app._bot_state["is_running"] = True
    web_app._run_bot_process_loop()


def test_the_config_error_exit_code_is_read_from_main_py(tmp_path, monkeypatch):
    code = web_app.BOT_CONFIG_ERROR_EXIT_CODE
    assert isinstance(code, int) and code not in (0, 1)       # לא הצלחה ולא קריסה רגילה
    with open(os.path.join(web_app.BASE_DIR, "src", "entrypoints", "main.py"), encoding="utf-8") as f:
        assert "sys.exit(CONFIG_ERROR_EXIT_CODE)" in f.read()
    (tmp_path / "main.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setattr(web_app, "MAIN_PY_PATH", str(tmp_path / "main.py"))
    assert web_app._read_bot_config_error_exit_code() is None  # השם נעלם - כל יציאה היא קריסה, כמו קודם


def test_non_utf8_output_and_a_config_error_stop_without_a_restart(tmp_path, monkeypatch):
    runs = _fake_main(tmp_path, monkeypatch, (
        "record.write('start\\n'); record.flush()\n"
        "sys.stdout.buffer.write('שורה ב-cp1255\\n'.encode('cp1255')); sys.stdout.buffer.flush()\n"
        "sys.stdout.buffer.write('אין טוקן\\n'.encode('utf-8')); sys.stdout.buffer.flush()\n"
        f"sys.exit({web_app.BOT_CONFIG_ERROR_EXIT_CODE})\n"
    ))
    _start_loop()
    log = "".join(web_app._bot_log_buffer)
    assert "אין טוקן" in log                                   # הקורא שרד את השורה שאינה UTF-8
    assert "[שגיאת הגדרה]" in log
    assert runs.read_text().count("start") == 1                 # בלי הפעלה מחדש
    assert client.get("/api/bot/status").json() == {"running": False, "gave_up": False, "config_error": True}
    _reset_bot_state()


def test_a_reader_failure_waits_for_the_live_bot_instead_of_starting_another(tmp_path, monkeypatch):
    # הבוט ממשיך לרוץ ולכתוב (יותר ממה שנכנס בצינור) אחרי שהקורא נפל - הלולאה מרוקנת את הפלט ומחכה שייצא בעצמו
    runs = _fake_main(tmp_path, monkeypatch, (
        "record.write('start\\n'); record.flush()\n"
        "for i in range(3000):\n"
        "    sys.stdout.buffer.write(b'x' * 100 + b'\\n')\n"
        "sys.stdout.buffer.flush(); time.sleep(0.5)\n"
        "record.write('end\\n'); record.flush()\n"
        "sys.exit(1)\n"
    ))
    calls = {"n": 0}
    original = web_app._bot_write_to_log

    def failing_log(line):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("הקורא נפל")
        original(line)
    monkeypatch.setattr(web_app, "_bot_write_to_log", failing_log)
    monkeypatch.setattr(web_app, "record_crash_and_check_giveup", lambda stamps, now, window, limit: (stamps + [now], True))
    _start_loop()
    # כשהלולאה חזרה (אחרי "קריסה" - קוד 1) התהליך כבר סיים בעצמו, ואף עותק נוסף לא הופעל בזמן שהוא חי
    assert runs.read_text().split() == ["start", "end"]
    assert "[שגיאה בקריאת הלוג של הבוט]" in "".join(web_app._bot_log_buffer)
    assert web_app._bot_state["gave_up"] is True and web_app._bot_state["process"] is None
    _reset_bot_state()
