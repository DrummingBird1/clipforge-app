# tests/bot/test_weekly_digest.py
import datetime


import pytest

from utils.shared import job_history
from utils.bot import weekly_digest
from utils.shared.state import state


@pytest.fixture(autouse=True)
def _restore_state():
    snapshot = dict(state.__dict__)
    yield
    state.__dict__.clear()
    state.__dict__.update(snapshot)


def test_no_webhook_configured_never_sends(monkeypatch):
    monkeypatch.setattr(state, "discord_webhook_url", "")
    monkeypatch.setattr(state, "last_digest_sent_at", "")
    assert weekly_digest.maybe_send_weekly_digest() is False


def test_sends_on_first_run_when_never_sent_before(monkeypatch, tmp_path):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(state, "discord_webhook_url", "https://discord.example/webhook")
    monkeypatch.setattr(state, "last_digest_sent_at", "")
    monkeypatch.setattr(weekly_digest, "send_webhook_notification", lambda url, msg: None)
    monkeypatch.setattr(state, "save_config", lambda: None)

    assert weekly_digest.maybe_send_weekly_digest() is True
    assert state.last_digest_sent_at  # got stamped with a timestamp


def test_does_not_send_again_within_7_days(monkeypatch):
    monkeypatch.setattr(state, "discord_webhook_url", "https://discord.example/webhook")
    recent = (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat(timespec="seconds")
    monkeypatch.setattr(state, "last_digest_sent_at", recent)

    assert weekly_digest.maybe_send_weekly_digest() is False


def test_sends_again_after_7_days(monkeypatch, tmp_path):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(state, "discord_webhook_url", "https://discord.example/webhook")
    old = (datetime.datetime.now() - datetime.timedelta(days=8)).isoformat(timespec="seconds")
    monkeypatch.setattr(state, "last_digest_sent_at", old)
    monkeypatch.setattr(weekly_digest, "send_webhook_notification", lambda url, msg: None)
    monkeypatch.setattr(state, "save_config", lambda: None)

    assert weekly_digest.maybe_send_weekly_digest() is True


def test_build_digest_message_summarizes_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    now = datetime.datetime.now()
    job_history.record_job("disk_scanner.py", "success", now.isoformat(timespec="seconds"),
                            now.isoformat(timespec="seconds"), 10.0, result={"files_scanned": 5})
    job_history.record_job("file_renamer.py", "failed", now.isoformat(timespec="seconds"),
                            now.isoformat(timespec="seconds"), 1.0)

    message = weekly_digest.build_digest_message(now)

    assert "2 ריצות" in message
    assert "disk_scanner.py" in message
    assert "files_scanned: 5" in message
    assert "file_renamer.py" in message


def test_build_digest_message_empty_history(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    message = weekly_digest.build_digest_message()
    assert "לא בוצעו ריצות" in message
