# tests/bot/test_remote_execution.py
#
# בודק cogs/remote_execution.py - bot.db הוא aiosqlite אמיתי (audit_log),
# run_script מריץ subprocess אמיתי (sys.executable על סקריפט זמני שנוצר
# ב-tmp_path - לא ניחוש/mock לתת-תהליך), אבל acquire_render_lock/
# release_render_lock מדומים (call-recorder בלבד) - render_lock.py עצמו כבר
# נבדק לעומק ב-tests/infra/test_render_lock.py, כאן רק מוודאים את סדר הקריאות
# (acquire לפני התהליך, release גם על כישלון) בלי לגעת בקובץ המנעול האמיתי.
import asyncio
import subprocess
from unittest.mock import AsyncMock, MagicMock

import aiosqlite


import cogs.remote_execution as remote_execution_module
from cogs.remote_execution import RemoteExecution


def _run(coro):
    return asyncio.run(coro)


class FakeMessage:
    def __init__(self):
        self.edit = AsyncMock()


class FakeChannel:
    def __init__(self):
        self.messages = []

    async def send(self, content=None, **kwargs):
        msg = FakeMessage()
        self.messages.append((content, msg))
        return msg


class FakeBot:
    def __init__(self, db, is_owner=True):
        self.db = db
        self.is_owner = AsyncMock(return_value=is_owner)


def _make_cog(bot, scripts_dir):
    cog = RemoteExecution.__new__(RemoteExecution)
    cog.bot = bot
    cog.scripts_dir = str(scripts_dir)
    return cog


def _make_interaction(user_id=1, username="tester"):
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.user.__str__.return_value = username
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.channel = FakeChannel()
    return interaction


async def _open_db(tmp_path):
    return await aiosqlite.connect(str(tmp_path / "test.db"))


def _write_script(dir_path, name, body):
    sub = dir_path / "video"
    sub.mkdir(exist_ok=True)
    path = sub / name
    path.write_text(body, encoding="utf-8")
    return path


def _patch_render_lock(monkeypatch):
    calls = []
    monkeypatch.setattr(remote_execution_module, "acquire_render_lock", lambda **kw: calls.append(("acquire", kw)))
    monkeypatch.setattr(remote_execution_module, "release_render_lock", lambda: calls.append(("release", {})))
    return calls


# --- owner_only / log_action ---

def test_owner_only_blocks_non_owner(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db, is_owner=False), tmp_path)
            interaction = _make_interaction()

            assert await cog.owner_only(interaction) is False
            assert "בעל הבוט" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_owner_only_allows_the_owner(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db, is_owner=True), tmp_path)
            interaction = _make_interaction()

            assert await cog.owner_only(interaction) is True
            interaction.response.send_message.assert_not_awaited()
        finally:
            await db.close()

    _run(scenario())


def test_log_action_writes_a_row_with_details(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction(user_id=42, username="tester#0001")

            await cog.log_action(interaction, "run_script", "video_editor.py")

            async with db.execute("SELECT user_id, username, command, details FROM audit_log") as cur:
                row = await cur.fetchone()
            assert row == (42, "tester#0001", "run_script", "video_editor.py")
        finally:
            await db.close()

    _run(scenario())


def test_log_action_second_call_tolerates_column_already_added(tmp_path):
    # ALTER TABLE ADD COLUMN source על טבלה שכבר עברה את המיגרציה הזו נכשל
    # עם sqlite3.OperationalError ("duplicate column") - נתפס ומדולג, לא
    # מפיל את הפעולה השנייה.
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()

            await cog.log_action(interaction, "run_script", "first")
            await cog.log_action(interaction, "run_script", "second")

            async with db.execute("SELECT COUNT(*) FROM audit_log") as cur:
                (count,) = await cur.fetchone()
            assert count == 2
        finally:
            await db.close()

    _run(scenario())


def test_log_action_swallows_db_errors():
    class _FailingDb:
        async def execute(self, *a, **k):
            raise RuntimeError("db is closed")

    async def scenario():
        cog = _make_cog(FakeBot(_FailingDb()), "/tmp")
        interaction = _make_interaction()

        await cog.log_action(interaction, "run_script")  # לא אמור לזרוק

    _run(scenario())


# --- _script_name_autocomplete ---

def test_autocomplete_filters_case_insensitively(tmp_path):
    _write_script(tmp_path, "video_editor.py", "")
    _write_script(tmp_path, "story_cutter.py", "")

    async def scenario():
        cog = _make_cog(FakeBot(None), tmp_path)
        choices = await cog._script_name_autocomplete(None, "VIDEO")
        assert [c.value for c in choices] == ["video_editor.py"]

    _run(scenario())


def test_autocomplete_caps_at_25_results(tmp_path):
    for i in range(30):
        _write_script(tmp_path, f"script_{i:02d}.py", "")

    async def scenario():
        cog = _make_cog(FakeBot(None), tmp_path)
        choices = await cog._script_name_autocomplete(None, "script")
        assert len(choices) == 25

    _run(scenario())


# --- /run_script ---

def test_run_script_requires_owner(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db, is_owner=False), tmp_path)
            interaction = _make_interaction()

            await cog.run_script.callback(cog, interaction, "video_editor.py")

            assert "בעל הבוט" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_run_script_rejects_a_non_py_extension(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()

            await cog.run_script.callback(cog, interaction, "not_a_script.txt")

            assert "לא חוקי" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_run_script_rejects_a_script_that_does_not_exist(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()

            await cog.run_script.callback(cog, interaction, "does_not_exist.py")

            assert "לא נמצא" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_run_script_runs_successfully_and_edits_the_final_message(tmp_path, monkeypatch):
    lock_calls = _patch_render_lock(monkeypatch)
    monkeypatch.setattr(remote_execution_module, "STATUS_EDIT_INTERVAL_SECONDS", 0)
    _write_script(tmp_path, "success.py", "print('line one')\nprint('line two')\n")

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()

            await cog.run_script.callback(cog, interaction, "success.py")

            interaction.response.send_message.assert_awaited_once()
            assert len(interaction.channel.messages) == 1
            status_msg = interaction.channel.messages[0][1]
            assert status_msg.edit.await_count >= 1
            final_content = status_msg.edit.call_args.kwargs.get("content") or status_msg.edit.call_args.args[0]
            assert "הסתיים בהצלחה" in final_content
            assert lock_calls[0][0] == "acquire"
            assert lock_calls[-1] == ("release", {})
        finally:
            await db.close()

    _run(scenario())


def test_run_script_reports_a_failure_embed_on_nonzero_exit_code(tmp_path, monkeypatch):
    lock_calls = _patch_render_lock(monkeypatch)
    monkeypatch.setattr(remote_execution_module, "STATUS_EDIT_INTERVAL_SECONDS", 0)
    _write_script(tmp_path, "failing.py", "print('about to fail')\nimport sys; sys.exit(7)\n")

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()

            await cog.run_script.callback(cog, interaction, "failing.py")

            status_msg = interaction.channel.messages[0][1]
            embed = status_msg.edit.call_args.kwargs["embed"]
            assert "קריסת סקריפט" in embed.title
            assert "7" in embed.description
            assert lock_calls[-1] == ("release", {})
        finally:
            await db.close()

    _run(scenario())


def test_run_script_reports_lock_acquisition_failure_and_does_not_start_a_process(tmp_path, monkeypatch):
    def _failing_acquire(**kw):
        raise TimeoutError("still locked")

    monkeypatch.setattr(remote_execution_module, "acquire_render_lock", _failing_acquire)
    release_calls = []
    monkeypatch.setattr(remote_execution_module, "release_render_lock", lambda: release_calls.append(1))
    _write_script(tmp_path, "never_runs.py", "print('should not run')\n")

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()

            await cog.run_script.callback(cog, interaction, "never_runs.py")

            status_msg = interaction.channel.messages[0][1]
            content = status_msg.edit.call_args.kwargs.get("content") or status_msg.edit.call_args.args[0]
            assert "שגיאה בתפיסת מנעול" in content
            assert release_calls == []  # אף פעם לא תפסנו - אין מה לשחרר
        finally:
            await db.close()

    _run(scenario())


def test_run_script_releases_lock_even_when_process_creation_fails(tmp_path, monkeypatch):
    lock_calls = _patch_render_lock(monkeypatch)

    async def _failing_create_subprocess_exec(*a, **k):
        raise OSError("no such executable")

    monkeypatch.setattr(remote_execution_module.asyncio, "create_subprocess_exec", _failing_create_subprocess_exec)
    _write_script(tmp_path, "unreachable.py", "print('irrelevant')\n")

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()

            await cog.run_script.callback(cog, interaction, "unreachable.py")

            status_msg = interaction.channel.messages[0][1]
            content = status_msg.edit.call_args.kwargs.get("content") or status_msg.edit.call_args.args[0]
            assert "שגיאה בלתי צפויה" in content
            assert lock_calls == [("acquire", {"priority": 10, "label": "unreachable.py"}), ("release", {})]
        finally:
            await db.close()

    _run(scenario())


# --- /docker_status ---

def test_docker_status_requires_owner(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db, is_owner=False), tmp_path)
            interaction = _make_interaction()

            await cog.docker_status.callback(cog, interaction)

            assert "בעל הבוט" in interaction.response.send_message.call_args.args[0]
            interaction.response.defer.assert_not_awaited()
        finally:
            await db.close()

    _run(scenario())


def test_docker_status_shows_running_containers(tmp_path, monkeypatch):
    monkeypatch.setattr(
        remote_execution_module.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="app  Up 2 hours\n", stderr=""),
    )

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()

            await cog.docker_status.callback(cog, interaction)

            assert "app" in interaction.followup.send.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_docker_status_not_installed_message(tmp_path, monkeypatch):
    monkeypatch.setattr(
        remote_execution_module.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout="", stderr="not found"),
    )

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()

            await cog.docker_status.callback(cog, interaction)

            assert "לא מותקן" in interaction.followup.send.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_docker_status_reports_an_unexpected_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(remote_execution_module.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("docker")))

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()

            await cog.docker_status.callback(cog, interaction)

            assert "נכשל" in interaction.followup.send.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


# --- /audit_log ---

async def _create_audit_log_table(db):
    await db.execute("""
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, command TEXT, details TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP, source TEXT DEFAULT 'discord'
        )
    """)
    await db.commit()


def test_audit_log_requires_owner(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db, is_owner=False), tmp_path)
            interaction = _make_interaction()

            await cog.audit_log.callback(cog, interaction)

            assert "בעל הבוט" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_audit_log_shows_recent_entries(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            await _create_audit_log_table(db)
            await db.execute(
                "INSERT INTO audit_log (username, command, details, source) VALUES (?, ?, ?, ?)",
                ("tester", "run_script", "video_editor.py", "web"),
            )
            await db.commit()
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()

            await cog.audit_log.callback(cog, interaction)

            embed = interaction.response.send_message.call_args.kwargs["embed"]
            assert len(embed.fields) == 1
            assert "🌐" in embed.fields[0].name
            assert "video_editor.py" in embed.fields[0].name
        finally:
            await db.close()

    _run(scenario())


def test_audit_log_defaults_to_bot_icon_when_source_is_none(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            await _create_audit_log_table(db)
            await db.execute("INSERT INTO audit_log (username, command, source) VALUES (?, ?, NULL)", ("tester", "docker_status"))
            await db.commit()
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()

            await cog.audit_log.callback(cog, interaction)

            embed = interaction.response.send_message.call_args.kwargs["embed"]
            assert "🤖" in embed.fields[0].name
        finally:
            await db.close()

    _run(scenario())


def test_audit_log_reports_when_empty(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            await _create_audit_log_table(db)
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()

            await cog.audit_log.callback(cog, interaction)

            assert "אין עדיין רשומות" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_audit_log_handles_a_missing_table_gracefully(tmp_path):
    # לא יוצרים בכלל את טבלת audit_log - השאילתה נכשלת, נתפסת ב-except,
    # ומטופלת כאילו אין רשומות (לא קורס).
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()

            await cog.audit_log.callback(cog, interaction)

            assert "אין עדיין רשומות" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_setup_adds_the_cog_to_the_bot(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            bot = FakeBot(db)
            bot.add_cog = AsyncMock()

            await remote_execution_module.setup(bot)

            bot.add_cog.assert_awaited_once()
            assert isinstance(bot.add_cog.call_args.args[0], RemoteExecution)
        finally:
            await db.close()

    _run(scenario())


def test_docker_status_does_not_block_the_bot_when_docker_hangs(tmp_path, monkeypatch):
    """25.10.2026: subprocess.run בלי timeout בתוך הלולאה של הבוט - Docker תקוע עצר את כל הבוט."""
    import threading
    calls = []

    def hanging_run(*a, **k):
        calls.append((threading.get_ident(), k.get("timeout")))
        raise subprocess.TimeoutExpired(cmd="docker", timeout=k.get("timeout"))

    monkeypatch.setattr(remote_execution_module.subprocess, "run", hanging_run)

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db), tmp_path)
            interaction = _make_interaction()
            await cog.docker_status.callback(cog, interaction)
            assert "לא ענה" in interaction.followup.send.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())
    (thread, timeout), = calls
    assert timeout and timeout <= 30
    assert thread != threading.get_ident()   # לא בתוך הלולאה של הבוט
