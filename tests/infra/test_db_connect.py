# tests/infra/test_db_connect.py
#
# utils/db.connect: הקובץ עובר ל-WAL פעם אחת, וחיבורים שנפתחים בבת אחת (הבוט, ה-GUI, התזמון - או 14 תהליכי טסטים
# על אותו DB, שם זה נמצא ב-16.10.2026) לא זורקים "database is locked" על המעבר ל-WAL.
import sqlite3
import threading


from utils.shared import db


def _mode(path):
    with sqlite3.connect(path) as conn:
        return conn.execute("PRAGMA journal_mode").fetchone()[0].lower()


def test_the_file_becomes_wal_once(tmp_path):
    path = str(tmp_path / "x.db")
    conn = db.connect(path)
    conn.execute("CREATE TABLE t (v INTEGER)")
    conn.commit()
    conn.close()
    assert _mode(path) == "wal"
    assert db.connect(path).execute("PRAGMA busy_timeout").fetchone()[0] == db.BUSY_TIMEOUT_MS


def test_a_failed_switch_still_returns_a_working_connection(tmp_path, monkeypatch):
    real_connect = sqlite3.connect

    class Busy:
        def __init__(self, conn):
            self.conn = conn

        def execute(self, sql, *args):
            if sql.replace(" ", "").lower() == "pragmajournal_mode=wal":
                raise sqlite3.OperationalError("database is locked")
            return self.conn.execute(sql, *args)

    monkeypatch.setattr(db.sqlite3, "connect", lambda *a, **k: Busy(real_connect(*a, **k)))
    conn = db.connect(str(tmp_path / "x.db"))
    conn.execute("CREATE TABLE t (v INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    assert conn.execute("SELECT v FROM t").fetchone() == (1,)


def test_many_connections_at_once(tmp_path):
    path = str(tmp_path / "x.db")
    barrier, errors = threading.Barrier(12), []

    def worker():
        barrier.wait()
        try:
            for _ in range(5):
                conn = db.connect(path)
                conn.execute("CREATE TABLE IF NOT EXISTS t (v INTEGER)")
                conn.execute("INSERT INTO t VALUES (1)")
                conn.commit()
                conn.close()
        except sqlite3.OperationalError as e:
            errors.append(str(e))

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert _mode(path) == "wal"
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 60
