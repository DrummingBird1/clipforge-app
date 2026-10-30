# tests/bot/test_status_cog.py
#
# בודק cogs/status_cog.py - /status המרוכז, /render_stats, /help. bot.db
# הוא aiosqlite אמיתי (tmp_path) עם טבלת audit_log אמיתית, בדיוק כמו
# tests/bot/test_approval_cog.py - לא מוק ל-db.execute עצמו. is_owner/
# interaction.response הם MagicMock/AsyncMock, כמו בכל שאר טסטי ה-cogs
# בפרויקט (discord.py gateway עצמו לא נבדק בכלל).
import asyncio
import datetime
import json
import subprocess
from unittest.mock import AsyncMock, MagicMock

import aiosqlite


import cogs.status_cog as status_cog_module
from cogs.status_cog import StatusCog, _get_disk_free_gb, _get_docker_status_text, _load_scheduler_state


def _run(coro):
    return asyncio.run(coro)


def _make_bot(is_owner=True, db=None, started_at=None):
    bot = MagicMock()
    bot.is_owner = AsyncMock(return_value=is_owner)
    bot.db = db
    bot.started_at = started_at
    return bot


def _make_interaction(user_id=1):
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def _open_db_with_audit_log(tmp_path, rows=()):
    db = await aiosqlite.connect(str(tmp_path / "test.db"))
    await db.execute("""
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, command TEXT, details TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP, source TEXT DEFAULT 'discord'
        )
    """)
    for username, command, details, source in rows:
        await db.execute(
            "INSERT INTO audit_log (username, command, details, source) VALUES (?, ?, ?, ?)",
            (username, command, details, source),
        )
    await db.commit()
    return db


# --- helpers ---

def test_get_disk_free_gb_rounds_to_one_decimal(monkeypatch):
    monkeypatch.setattr(status_cog_module.shutil, "disk_usage", lambda path: (1000, 500, 5_368_709_120))  # 5 GiB פנוי

    assert _get_disk_free_gb() == 5.0


def test_get_disk_free_gb_returns_none_on_error(monkeypatch):
    monkeypatch.setattr(status_cog_module.shutil, "disk_usage", lambda path: (_ for _ in ()).throw(OSError("no such disk")))

    assert _get_disk_free_gb() is None


def test_get_docker_status_text_lists_running_containers(monkeypatch):
    monkeypatch.setattr(status_cog_module.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="app: Up 2 hours\n", stderr=""))

    assert _get_docker_status_text() == "app: Up 2 hours"


def test_get_docker_status_text_no_containers_message(monkeypatch):
    monkeypatch.setattr(status_cog_module.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="", stderr=""))

    assert _get_docker_status_text() == "אין קונטיינרים פעילים"


def test_get_docker_status_text_not_installed_when_command_fails(monkeypatch):
    monkeypatch.setattr(status_cog_module.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout="", stderr="not found"))

    assert _get_docker_status_text() == "לא מותקן/לא נגיש"


def test_get_docker_status_text_not_installed_on_exception(monkeypatch):
    monkeypatch.setattr(status_cog_module.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))

    assert _get_docker_status_text() == "לא מותקן/לא נגיש"


def test_load_scheduler_state_reads_existing_file(tmp_path, monkeypatch):
    state_path = tmp_path / "scheduler_state.json"
    state_path.write_text(json.dumps({"last_db_backup_date": "2026-09-01"}), encoding="utf-8")
    monkeypatch.setattr(status_cog_module, "SCHEDULER_STATE_PATH", str(state_path))

    assert _load_scheduler_state() == {"last_db_backup_date": "2026-09-01"}


def test_load_scheduler_state_missing_file_returns_empty_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(status_cog_module, "SCHEDULER_STATE_PATH", str(tmp_path / "does_not_exist.json"))

    assert _load_scheduler_state() == {}


def test_load_scheduler_state_corrupt_json_returns_empty_dict(tmp_path, monkeypatch):
    state_path = tmp_path / "scheduler_state.json"
    state_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(status_cog_module, "SCHEDULER_STATE_PATH", str(state_path))

    assert _load_scheduler_state() == {}


# --- /status ---

def test_status_requires_bot_owner(tmp_path):
    async def scenario():
        db = await _open_db_with_audit_log(tmp_path)
        try:
            cog = StatusCog(_make_bot(is_owner=False, db=db))
            interaction = _make_interaction()
            await cog.status.callback(cog, interaction)
            interaction.response.send_message.assert_awaited_once()
            assert "בעל הבוט" in interaction.response.send_message.call_args.args[0]
            interaction.response.defer.assert_not_awaited()
        finally:
            await db.close()

    _run(scenario())


def test_status_shows_full_embed_with_last_action_and_free_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(status_cog_module, "_get_disk_free_gb", lambda: 42.5)
    monkeypatch.setattr(status_cog_module, "_get_docker_status_text", lambda: "app: Up")
    monkeypatch.setattr(status_cog_module, "get_render_lock_status", lambda: None)

    async def scenario():
        db = await _open_db_with_audit_log(tmp_path, rows=[("tester", "run_script", "video_editor.py", "web")])
        try:
            started_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
            cog = StatusCog(_make_bot(db=db, started_at=started_at))
            interaction = _make_interaction()

            await cog.status.callback(cog, interaction)

            interaction.response.defer.assert_awaited_once_with(ephemeral=True)
            interaction.followup.send.assert_awaited_once()
            embed = interaction.followup.send.call_args.kwargs["embed"]
            field_names = [f.name for f in embed.fields]
            assert "⏱️ זמן פעילות" in field_names
            assert "💾 שטח פנוי בדיסק" in field_names
            assert "🔒 מנעול רינדור" in field_names
            lock_field = next(f for f in embed.fields if f.name == "🔒 מנעול רינדור")
            assert lock_field.value == "פנוי"
            last_action_field = next(f for f in embed.fields if "פעולה אחרונה" in f.name)
            assert "run_script" in last_action_field.value
            assert "video_editor.py" in last_action_field.value
            assert "tester" in last_action_field.value
        finally:
            await db.close()

    _run(scenario())


def test_status_shows_unknown_uptime_when_started_at_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(status_cog_module, "get_render_lock_status", lambda: None)

    async def scenario():
        db = await _open_db_with_audit_log(tmp_path)
        try:
            cog = StatusCog(_make_bot(db=db, started_at=None))
            interaction = _make_interaction()

            await cog.status.callback(cog, interaction)

            embed = interaction.followup.send.call_args.kwargs["embed"]
            uptime_field = next(f for f in embed.fields if "זמן פעילות" in f.name)
            assert uptime_field.value == "לא ידוע"
        finally:
            await db.close()

    _run(scenario())


def test_status_shows_busy_lock_with_queue_length(tmp_path, monkeypatch):
    monkeypatch.setattr(status_cog_module, "get_render_lock_status", lambda: {
        "pid": 4321, "acquired_at": 0.0, "age_seconds": 90.0, "is_stale": False, "queue_length": 2,
    })

    async def scenario():
        db = await _open_db_with_audit_log(tmp_path)
        try:
            cog = StatusCog(_make_bot(db=db))
            interaction = _make_interaction()

            await cog.status.callback(cog, interaction)

            embed = interaction.followup.send.call_args.kwargs["embed"]
            lock_field = next(f for f in embed.fields if f.name == "🔒 מנעול רינדור")
            assert "4321" in lock_field.value
            assert "עוד 2 בתור" in lock_field.value
            assert "תקוע" not in lock_field.value
        finally:
            await db.close()

    _run(scenario())


def test_status_flags_a_stale_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(status_cog_module, "get_render_lock_status", lambda: {
        "pid": 999, "acquired_at": 0.0, "age_seconds": 99999.0, "is_stale": True, "queue_length": 0,
    })

    async def scenario():
        db = await _open_db_with_audit_log(tmp_path)
        try:
            cog = StatusCog(_make_bot(db=db))
            interaction = _make_interaction()

            await cog.status.callback(cog, interaction)

            embed = interaction.followup.send.call_args.kwargs["embed"]
            lock_field = next(f for f in embed.fields if f.name == "🔒 מנעול רינדור")
            assert "תקוע" in lock_field.value
        finally:
            await db.close()

    _run(scenario())


def test_status_omits_last_action_field_when_audit_log_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(status_cog_module, "get_render_lock_status", lambda: None)

    async def scenario():
        db = await _open_db_with_audit_log(tmp_path, rows=())
        try:
            cog = StatusCog(_make_bot(db=db))
            interaction = _make_interaction()

            await cog.status.callback(cog, interaction)

            embed = interaction.followup.send.call_args.kwargs["embed"]
            assert not any("פעולה אחרונה" in f.name for f in embed.fields)
        finally:
            await db.close()

    _run(scenario())


def test_status_handles_audit_log_query_failure_gracefully(monkeypatch):
    monkeypatch.setattr(status_cog_module, "get_render_lock_status", lambda: None)

    class _FailingDb:
        def execute(self, *a, **k):
            raise RuntimeError("db is closed")

    async def scenario():
        cog = StatusCog(_make_bot(db=_FailingDb()))
        interaction = _make_interaction()

        await cog.status.callback(cog, interaction)  # לא אמור לזרוק

        embed = interaction.followup.send.call_args.kwargs["embed"]
        assert not any("פעולה אחרונה" in f.name for f in embed.fields)

    _run(scenario())


# --- /render_stats ---

def test_render_stats_requires_bot_owner():
    async def scenario():
        cog = StatusCog(_make_bot(is_owner=False))
        interaction = _make_interaction()

        await cog.render_stats.callback(cog, interaction)

        assert "בעל הבוט" in interaction.response.send_message.call_args.args[0]

    _run(scenario())


def test_render_stats_shows_averages(monkeypatch):
    monkeypatch.setattr(status_cog_module, "get_average_render_durations", lambda: [("video_editor.py", 125.0, 4)])

    async def scenario():
        cog = StatusCog(_make_bot())
        interaction = _make_interaction()

        await cog.render_stats.callback(cog, interaction)

        embed = interaction.response.send_message.call_args.kwargs["embed"]
        assert len(embed.fields) == 1
        assert embed.fields[0].name == "video_editor.py"
        assert "4 ריצות" in embed.fields[0].value

    _run(scenario())


def test_render_stats_shows_empty_message_when_no_history(monkeypatch):
    monkeypatch.setattr(status_cog_module, "get_average_render_durations", lambda: [])

    async def scenario():
        cog = StatusCog(_make_bot())
        interaction = _make_interaction()

        await cog.render_stats.callback(cog, interaction)

        embed = interaction.response.send_message.call_args.kwargs["embed"]
        assert "אין עדיין היסטוריית ריצות" in embed.description

    _run(scenario())


# --- /help ---

def test_help_command_requires_bot_owner():
    async def scenario():
        cog = StatusCog(_make_bot(is_owner=False))
        interaction = _make_interaction()

        await cog.help_command.callback(cog, interaction)

        assert "בעל הבוט" in interaction.response.send_message.call_args.args[0]

    _run(scenario())


def test_help_command_lists_commands_sorted_by_name():
    fake_commands = [MagicMock(name="zzz_cmd", description="last"), MagicMock(name="aaa_cmd", description="first")]
    fake_commands[0].name, fake_commands[1].name = "zzz_cmd", "aaa_cmd"

    async def scenario():
        bot = _make_bot()
        bot.tree.get_commands = MagicMock(return_value=fake_commands)
        cog = StatusCog(bot)
        interaction = _make_interaction()

        await cog.help_command.callback(cog, interaction)

        embed = interaction.response.send_message.call_args.kwargs["embed"]
        assert [f.name for f in embed.fields] == ["/aaa_cmd", "/zzz_cmd"]

    _run(scenario())


def test_help_command_shows_placeholder_for_missing_description():
    async def scenario():
        cmd = MagicMock()
        cmd.name = "bare_cmd"
        cmd.description = ""
        bot = _make_bot()
        bot.tree.get_commands = MagicMock(return_value=[cmd])
        cog = StatusCog(bot)
        interaction = _make_interaction()

        await cog.help_command.callback(cog, interaction)

        embed = interaction.response.send_message.call_args.kwargs["embed"]
        assert embed.fields[0].value == "אין תיאור"

    _run(scenario())


def test_setup_adds_the_cog_to_the_bot():
    async def scenario():
        bot = _make_bot()
        bot.add_cog = AsyncMock()

        await status_cog_module.setup(bot)

        bot.add_cog.assert_awaited_once()
        assert isinstance(bot.add_cog.call_args.args[0], StatusCog)

    _run(scenario())
