# tests/infra/test_hardware_history_persistence.py
#
# בודק utils/shared/hardware_history.py (item: historical hardware usage graph) -
# ה-DB האמיתי (sqlite על tmp_path), לא מוק - record_sample/get_recent_samples
# הם בעצם רק שכבת דיסק דקה, השווה יותר לבדוק אותה עם DB אמיתי מאשר לדמות אותה.
import time
from datetime import datetime, timedelta


import utils.shared.hardware_history as hardware_history


def _reset_throttle(monkeypatch):
    # record_sample throttles per _last_recorded_at (global משותף לכל תהליך
    # הטסטים) - בלי לאפס אותו, טסט שרץ אחרי טסט אחר תוך פחות מ-60 שניות
    # (המצב הרגיל) היה מדלג בשקט, גם עם force=False.
    monkeypatch.setattr(hardware_history, "_last_recorded_at", 0.0)


def test_record_sample_and_get_recent_samples_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    _reset_throttle(monkeypatch)

    hardware_history.record_sample(cpu=25.0, ram=60.0, gpu=10.0, vram=40.0, encoder=5.0)

    rows = hardware_history.get_recent_samples(hours=24)
    assert len(rows) == 1
    _recorded_at, cpu, ram, gpu, vram, encoder = rows[0]
    assert (cpu, ram, gpu, vram, encoder) == (25.0, 60.0, 10.0, 40.0, 5.0)


def test_record_sample_allows_none_gpu_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    _reset_throttle(monkeypatch)

    hardware_history.record_sample(cpu=25.0, ram=60.0)  # אין NVIDIA GPU

    rows = hardware_history.get_recent_samples(hours=24)
    assert len(rows) == 1
    _recorded_at, cpu, ram, gpu, vram, encoder = rows[0]
    assert (gpu, vram, encoder) == (None, None, None)


def test_record_sample_throttles_without_force(tmp_path, monkeypatch):
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    _reset_throttle(monkeypatch)

    hardware_history.record_sample(cpu=1.0, ram=1.0)
    hardware_history.record_sample(cpu=2.0, ram=2.0)  # מיד אחרי - אמור לדלג

    rows = hardware_history.get_recent_samples(hours=24)
    assert len(rows) == 1
    assert rows[0][1] == 1.0  # רק הדגימה הראשונה נכתבה


def test_record_sample_force_bypasses_throttle(tmp_path, monkeypatch):
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    _reset_throttle(monkeypatch)

    hardware_history.record_sample(cpu=1.0, ram=1.0, force=True)
    hardware_history.record_sample(cpu=2.0, ram=2.0, force=True)

    rows = hardware_history.get_recent_samples(hours=24)
    assert len(rows) == 2


def test_get_recent_samples_excludes_samples_older_than_window(tmp_path, monkeypatch):
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    _reset_throttle(monkeypatch)
    hardware_history._ensure_table()

    old_time = (datetime.now() - timedelta(hours=48)).isoformat(timespec="seconds")
    recent_time = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
    from utils.shared import db
    with db.connect(hardware_history.DB_PATH) as conn:
        conn.execute("INSERT INTO hardware_history (recorded_at, cpu, ram, gpu, vram, encoder) VALUES (?, ?, ?, ?, ?, ?)", (old_time, 1.0, 1.0, None, None, None))
        conn.execute("INSERT INTO hardware_history (recorded_at, cpu, ram, gpu, vram, encoder) VALUES (?, ?, ?, ?, ?, ?)", (recent_time, 2.0, 2.0, None, None, None))

    rows = hardware_history.get_recent_samples(hours=24)

    assert len(rows) == 1
    assert rows[0][1] == 2.0


def test_record_sample_prunes_samples_older_than_retention(tmp_path, monkeypatch):
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    _reset_throttle(monkeypatch)
    hardware_history._ensure_table()

    ancient_time = (datetime.now() - timedelta(days=hardware_history.RETENTION_DAYS + 1)).isoformat(timespec="seconds")
    from utils.shared import db
    with db.connect(hardware_history.DB_PATH) as conn:
        conn.execute("INSERT INTO hardware_history (recorded_at, cpu, ram, gpu, vram, encoder) VALUES (?, ?, ?, ?, ?, ?)", (ancient_time, 1.0, 1.0, None, None, None))

    hardware_history.record_sample(cpu=2.0, ram=2.0, force=True)  # מפעיל את הניקוי

    with db.connect(hardware_history.DB_PATH) as conn:
        remaining = conn.execute("SELECT COUNT(*) FROM hardware_history").fetchone()[0]
    assert remaining == 1  # רק הדגימה החדשה - הישנה נוקתה


def test_get_recent_samples_ordered_oldest_to_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    _reset_throttle(monkeypatch)

    hardware_history.record_sample(cpu=1.0, ram=1.0, force=True)
    time.sleep(1.1)  # recorded_at ב-timespec="seconds" - חייב לזוז לפחות שנייה שלמה כדי שהמיון יהיה משמעותי
    hardware_history.record_sample(cpu=2.0, ram=2.0, force=True)

    rows = hardware_history.get_recent_samples(hours=24)

    assert [row[1] for row in rows] == [1.0, 2.0]
