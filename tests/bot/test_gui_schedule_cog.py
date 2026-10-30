# tests/bot/test_gui_schedule_cog.py
#
# בודק cogs/gui_schedule_cog.py (item 25) - צפייה/עריכה מרחוק במשימות
# המתוזמנות של ה-GUI (utils/bot/scheduler_store.py, אותו קובץ JSON בדיוק
# ש-ui/scheduler_tab.py קורא/כותב). STORE_PATH מופנה ל-tmp_path בכל טסט,
# בדיוק כמו tests/bot/test_scheduler.py הקיים.
import asyncio
from unittest.mock import AsyncMock, MagicMock


from utils.bot import scheduler_store
from cogs.gui_schedule_cog import GuiScheduleCog


def _make_bot(is_owner=True):
    bot = MagicMock()
    bot.is_owner = AsyncMock(return_value=is_owner)
    return bot


def _make_interaction(user_id=1, username="tester"):
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.user.__str__.return_value = username
    interaction.response.send_message = AsyncMock()
    return interaction


def _run(coro):
    return asyncio.run(coro)


def test_schedule_list_shows_all_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    scheduler_store.add_task("my_scripts/tools/disk_scanner.py", "daily", time_str="04:00")
    scheduler_store.add_task("my_scripts/video/timelapse_maker.py", "weekly", time_str="06:00", weekday="fri")

    cog = GuiScheduleCog(_make_bot())
    interaction = _make_interaction()
    _run(cog.schedule_list.callback(cog, interaction))

    interaction.response.send_message.assert_awaited_once()
    embed = interaction.response.send_message.call_args.kwargs["embed"]
    assert len(embed.fields) == 2


def test_schedule_list_reports_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    cog = GuiScheduleCog(_make_bot())
    interaction = _make_interaction()

    _run(cog.schedule_list.callback(cog, interaction))

    interaction.response.send_message.assert_awaited_once()
    assert "אין משימות" in interaction.response.send_message.call_args.args[0]


def test_schedule_list_requires_bot_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    cog = GuiScheduleCog(_make_bot(is_owner=False))
    interaction = _make_interaction()

    _run(cog.schedule_list.callback(cog, interaction))

    assert "בעל הבוט" in interaction.response.send_message.call_args.args[0]


def test_schedule_toggle_flips_enabled_state(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    task = scheduler_store.add_task("my_scripts/tools/disk_scanner.py", "daily", time_str="04:00")
    assert task["enabled"] is True

    cog = GuiScheduleCog(_make_bot())
    interaction = _make_interaction()
    _run(cog.schedule_toggle.callback(cog, interaction, task["id"]))

    assert scheduler_store.load_tasks()[0]["enabled"] is False
    assert "כובתה" in interaction.response.send_message.call_args.args[0]

    interaction2 = _make_interaction()
    _run(cog.schedule_toggle.callback(cog, interaction2, task["id"]))
    assert scheduler_store.load_tasks()[0]["enabled"] is True
    assert "הופעלה" in interaction2.response.send_message.call_args.args[0]


def test_schedule_toggle_reports_missing_task(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    cog = GuiScheduleCog(_make_bot())
    interaction = _make_interaction()

    _run(cog.schedule_toggle.callback(cog, interaction, "nonexistent-id"))

    assert "לא נמצאה" in interaction.response.send_message.call_args.args[0]


def test_schedule_remove_deletes_task(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    task = scheduler_store.add_task("my_scripts/tools/disk_scanner.py", "daily", time_str="04:00")

    cog = GuiScheduleCog(_make_bot())
    interaction = _make_interaction()
    _run(cog.schedule_remove.callback(cog, interaction, task["id"]))

    assert scheduler_store.load_tasks() == []
    assert "נמחקה" in interaction.response.send_message.call_args.args[0]


def test_schedule_remove_reports_missing_task(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    cog = GuiScheduleCog(_make_bot())
    interaction = _make_interaction()

    _run(cog.schedule_remove.callback(cog, interaction, "nonexistent-id"))

    assert "לא נמצאה" in interaction.response.send_message.call_args.args[0]


def test_autocomplete_filters_by_script_name(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    # שם קובץ שלא קיים בפועל - get_script_metadata נופל חזרה לשם שנגזר מהקובץ
    # עצמו (prettify), נתון יציב וחזוי בלי תלות בתוכן/כותרת סקריפט אמיתי.
    scheduler_store.add_task("my_scripts/tools/nonexistent_alpha.py", "daily", time_str="04:00")
    scheduler_store.add_task("my_scripts/video/nonexistent_beta.py", "daily", time_str="05:00")

    cog = GuiScheduleCog(_make_bot())
    choices = _run(cog._task_autocomplete(None, "alpha"))

    assert len(choices) == 1
    assert "alpha" in choices[0].name.lower()


def test_autocomplete_returns_empty_when_no_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    cog = GuiScheduleCog(_make_bot())

    assert _run(cog._task_autocomplete(None, "")) == []
