# tests/bot/test_batch_approval_cog.py
#
# בודק cogs/batch_approval_cog.py (item 24) - קוד "דבק" בלבד, שקורא ל-
# resolve_pending() של ApprovalCog דרך bot.get_cog(). לא נוגע ב-
# cogs/approval_cog.py או ביבא אותו בכלל - הכל כאן עם fake app approval cog,
# כדי לא להתערב בעבודה המקבילה על test_approval_cog.py.
import asyncio
from unittest.mock import AsyncMock, MagicMock


from cogs.batch_approval_cog import BatchApprovalCog


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    async def fetchall(self):
        return self._rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeApprovalCog:
    def __init__(self):
        self.ensure_table_calls = 0
        self.resolved = []

    async def _ensure_table(self):
        self.ensure_table_calls += 1

    async def resolve_pending(self, pending_id, video_path, approved):
        self.resolved.append((pending_id, video_path, approved))


def _make_bot(pending_rows, approval_cog=None, is_owner=True):
    bot = MagicMock()
    bot.is_owner = AsyncMock(return_value=is_owner)
    bot.get_cog = MagicMock(return_value=approval_cog)
    bot.db.execute = MagicMock(return_value=_FakeCursor(pending_rows))
    return bot


def _make_interaction(user_id=1, username="tester"):
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.user.__str__.return_value = username
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _run(coro):
    return asyncio.run(coro)


def test_approve_all_pending_resolves_every_row_as_approved(monkeypatch):
    fake_approval = _FakeApprovalCog()
    bot = _make_bot([(1, "/clips/a.mp4"), (2, "/clips/b.mp4")], approval_cog=fake_approval)
    monkeypatch.setattr("utils.bot.audit_log.record_action", lambda *a, **k: None)
    cog = BatchApprovalCog(bot)
    interaction = _make_interaction()

    _run(cog.approve_all_pending.callback(cog, interaction))

    assert fake_approval.resolved == [(1, "/clips/a.mp4", True), (2, "/clips/b.mp4", True)]
    interaction.followup.send.assert_awaited_once()
    assert "2" in interaction.followup.send.call_args.args[0]


def test_reject_all_pending_resolves_every_row_as_rejected(monkeypatch):
    fake_approval = _FakeApprovalCog()
    bot = _make_bot([(5, "/clips/c.mp4")], approval_cog=fake_approval)
    monkeypatch.setattr("utils.bot.audit_log.record_action", lambda *a, **k: None)
    cog = BatchApprovalCog(bot)
    interaction = _make_interaction()

    _run(cog.reject_all_pending.callback(cog, interaction))

    assert fake_approval.resolved == [(5, "/clips/c.mp4", False)]


def test_batch_approval_requires_bot_owner():
    fake_approval = _FakeApprovalCog()
    bot = _make_bot([(1, "/clips/a.mp4")], approval_cog=fake_approval, is_owner=False)
    cog = BatchApprovalCog(bot)
    interaction = _make_interaction()

    _run(cog.approve_all_pending.callback(cog, interaction))

    assert fake_approval.resolved == []
    interaction.response.send_message.assert_awaited_once()
    assert "בעל הבוט" in interaction.response.send_message.call_args.args[0]


def test_batch_approval_handles_no_pending_clips(monkeypatch):
    fake_approval = _FakeApprovalCog()
    bot = _make_bot([], approval_cog=fake_approval)
    cog = BatchApprovalCog(bot)
    interaction = _make_interaction()

    _run(cog.approve_all_pending.callback(cog, interaction))

    assert fake_approval.resolved == []
    interaction.response.send_message.assert_awaited_once()
    assert "אין קליפים" in interaction.response.send_message.call_args.args[0]


def test_batch_approval_handles_approval_cog_not_loaded():
    bot = _make_bot([(1, "/clips/a.mp4")], approval_cog=None)
    cog = BatchApprovalCog(bot)
    interaction = _make_interaction()

    _run(cog.approve_all_pending.callback(cog, interaction))

    interaction.response.send_message.assert_awaited_once()
    assert "לא נטען" in interaction.response.send_message.call_args.args[0]


def test_batch_approval_calls_ensure_table_before_querying(monkeypatch):
    fake_approval = _FakeApprovalCog()
    bot = _make_bot([(1, "/clips/a.mp4")], approval_cog=fake_approval)
    monkeypatch.setattr("utils.bot.audit_log.record_action", lambda *a, **k: None)
    cog = BatchApprovalCog(bot)
    interaction = _make_interaction()

    _run(cog.approve_all_pending.callback(cog, interaction))

    assert fake_approval.ensure_table_calls == 1
