# tests/infra/test_hardware_history.py
#
# בודק utils/shared/hardware.py's מעקב ההיסטוריה (item 17: גרף ניצולת לאורך זמן) -
# בלי nvidia-smi אמיתי (לא זמין/לא נחוץ בסביבת CI), רק את מבנה הנתונים
# עצמו וההגנה מפני mutation דרך get_gpu_performance_history().


import utils.shared.hardware as hardware


def test_history_arrays_start_at_configured_length():
    assert len(hardware.cpu_history) == hardware.HISTORY_LENGTH
    assert len(hardware.ram_history) == hardware.HISTORY_LENGTH
    assert len(hardware.gpu_history) == hardware.HISTORY_LENGTH
    assert len(hardware.vram_history) == hardware.HISTORY_LENGTH


def test_get_gpu_performance_history_returns_copies_not_originals():
    # מוטציה על הרשימה שהוחזרה לא אמורה "לדלוף" למצב הפנימי של המודול - קורא
    # (כמו ui/sidebar.py's _draw_history_graph) לא אמור להיות מסוגל לשבש בטעות
    # את ההיסטוריה המשותפת שנצפית על ידי כל שאר הקוד.
    gpu_hist, vram_hist = hardware.get_gpu_performance_history()
    gpu_hist.append(999)
    vram_hist.append(999)
    assert 999 not in hardware.gpu_history
    assert 999 not in hardware.vram_history


def test_get_gpu_performance_history_reflects_current_state(monkeypatch):
    monkeypatch.setattr(hardware, "gpu_history", [1, 2, 3])
    monkeypatch.setattr(hardware, "vram_history", [4, 5, 6])
    gpu_hist, vram_hist = hardware.get_gpu_performance_history()
    assert gpu_hist == [1, 2, 3]
    assert vram_hist == [4, 5, 6]


class _StopPollLoop(Exception):
    """מפסיקה את ה-while True של _gpu_poll_loop אחרי איטרציה אחת - מוקפצת
    דרך time.sleep המזויף במקום להריץ את הלולאה האינסופית האמיתית."""


def test_gpu_poll_loop_parses_encoder_utilization_from_nvidia_smi(monkeypatch):
    # utilization.encoder (מנוע ה-NVENC הייעודי) - עמודה רביעית חדשה ב-CSV
    # שnvidia-smi מחזיר, נפרדת מ-utilization.gpu (CUDA/shader כללי) - וידוא
    # שהפרסינג שם אותה במקום הנכון ב-_gpu_cache, לא רק את שלוש העמודות הישנות.
    fake_result = type("FakeResult", (), {"returncode": 0, "stdout": "15, 87, 2048, 8192\n"})()
    monkeypatch.setattr(hardware.subprocess, "run", lambda *a, **k: fake_result)
    monkeypatch.setattr(hardware.time, "sleep", lambda *_a: (_ for _ in ()).throw(_StopPollLoop()))
    monkeypatch.setattr(hardware, "gpu_history", [0] * hardware.HISTORY_LENGTH)
    monkeypatch.setattr(hardware, "vram_history", [0] * hardware.HISTORY_LENGTH)
    monkeypatch.setattr(hardware, "_gpu_cache", {"util": None, "vram_pct": None, "encoder_pct": None})

    try:
        hardware._gpu_poll_loop()
    except _StopPollLoop:
        pass

    assert hardware._gpu_cache["util"] == 15.0
    assert hardware._gpu_cache["encoder_pct"] == 87.0
    assert hardware._gpu_cache["vram_pct"] == (2048 / 8192) * 100


# --- get_system_stats() -> utils/shared/hardware_history.py wiring (item: historical hardware usage graph) ---

def test_get_system_stats_records_a_sample(monkeypatch):
    if hardware.psutil is None:
        return  # psutil לא מותקן בסביבה הזו - get_system_stats() מחזיר (0, 0) בלי לגעת בהיסטוריה בכלל
    monkeypatch.setattr(hardware.psutil, "cpu_percent", lambda: 42.0)
    monkeypatch.setattr(hardware.psutil, "virtual_memory", lambda: type("M", (), {"percent": 55.0})())
    monkeypatch.setattr(hardware, "get_gpu_stats", lambda: (None, None, None))
    recorded = []
    monkeypatch.setattr("utils.shared.hardware_history.record_sample", lambda *a, **kw: recorded.append((a, kw)))

    cpu, ram = hardware.get_system_stats()

    assert (cpu, ram) == (42.0, 55.0)
    assert len(recorded) == 1
    assert recorded[0][0] == (42.0, 55.0, None, None, None)


def test_get_system_stats_does_not_raise_if_history_recording_fails(monkeypatch):
    if hardware.psutil is None:
        return
    monkeypatch.setattr(hardware.psutil, "cpu_percent", lambda: 10.0)
    monkeypatch.setattr(hardware.psutil, "virtual_memory", lambda: type("M", (), {"percent": 20.0})())
    monkeypatch.setattr(hardware, "get_gpu_stats", lambda: (None, None, None))

    def _boom(*a, **kw):
        raise RuntimeError("DB is on fire")
    monkeypatch.setattr("utils.shared.hardware_history.record_sample", _boom)

    cpu, ram = hardware.get_system_stats()  # לא אמור לזרוק - רישום היסטוריה הוא תוספת אופציונלית

    assert (cpu, ram) == (10.0, 20.0)
