# tests/bot/test_scheduler_low_disk_warning.py
#
# בודק את _get_free_disk_gb() (מבודד מ-shutil.disk_usage האמיתי דרך monkeypatch)
# ואת ה-threshold LOW_DISK_SPACE_WARNING_GB - בלי לגעת בפועל בכונן האמיתי.


from cogs import scheduler_cog


def _fake_disk_usage(free_gb):
    free_bytes = int(free_gb * (1024 ** 3))
    return lambda _path: (100 * (1024 ** 3), 100 * (1024 ** 3) - free_bytes, free_bytes)


def test_get_free_disk_gb_reports_free_space_in_gb(monkeypatch):
    monkeypatch.setattr(scheduler_cog.shutil, "disk_usage", _fake_disk_usage(5.0))
    assert scheduler_cog._get_free_disk_gb() == 5.0


def test_low_disk_threshold_triggers_below_warning_gb(monkeypatch):
    monkeypatch.setattr(scheduler_cog.shutil, "disk_usage", _fake_disk_usage(1.0))
    free_gb = scheduler_cog._get_free_disk_gb()
    assert free_gb < scheduler_cog.LOW_DISK_SPACE_WARNING_GB


def test_low_disk_threshold_does_not_trigger_above_warning_gb(monkeypatch):
    monkeypatch.setattr(scheduler_cog.shutil, "disk_usage", _fake_disk_usage(50.0))
    free_gb = scheduler_cog._get_free_disk_gb()
    assert free_gb >= scheduler_cog.LOW_DISK_SPACE_WARNING_GB
