# tests/bot/test_audit_log.py
#
# בודק utils/bot/audit_log.py (הלוג המשותף לפעולות מ-web_app.py, בנפרד מ-
# cogs/remote_execution.py's אותה טבלה בדיוק דרך aiosqlite הא-סינכרוני) עם
# DB זמני אמיתי - לא mock, כדי לוודא את המיגרציה האידמפוטנטית וההוספה בפועל.


import utils.bot.audit_log as audit_log


def test_record_action_writes_a_row(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_log, "DB_PATH", str(tmp_path / "test.db"))

    audit_log.record_action("web", "run_script", details="video_editor.py", username="127.0.0.1")

    rows = audit_log.get_recent_actions()
    assert len(rows) == 1
    username, command, details, _ts, source = rows[0]
    assert username == "127.0.0.1"
    assert command == "run_script"
    assert details == "video_editor.py"
    assert source == "web"


def test_get_recent_actions_orders_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_log, "DB_PATH", str(tmp_path / "test.db"))

    audit_log.record_action("web", "run_script", details="first.py")
    audit_log.record_action("web", "run_script", details="second.py")

    rows = audit_log.get_recent_actions()
    assert rows[0][2] == "second.py"
    assert rows[1][2] == "first.py"


def test_get_recent_actions_respects_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_log, "DB_PATH", str(tmp_path / "test.db"))
    for i in range(5):
        audit_log.record_action("web", "run_script", details=f"clip_{i}.py")

    rows = audit_log.get_recent_actions(limit=2)
    assert len(rows) == 2


def test_record_action_never_raises_on_db_error(monkeypatch):
    # נתיב DB לא תקין (תיקייה שלא ניתן ליצור בה קובץ) - record_action אמור
    # לתפוס ולהדפיס, לא להפיל את הקורא (endpoint של FastAPI וכו').
    monkeypatch.setattr(audit_log, "DB_PATH", "Z:/does/not/exist/nested/deep/test.db")
    audit_log.record_action("web", "run_script")  # לא אמור לזרוק


def test_ensure_table_migration_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(audit_log, "DB_PATH", str(db_path))

    audit_log._ensure_table()
    audit_log._ensure_table()  # קריאה שנייה - לא אמורה לזרוק על "column already exists"

    audit_log.record_action("discord", "run_script")
    rows = audit_log.get_recent_actions()
    assert len(rows) == 1
