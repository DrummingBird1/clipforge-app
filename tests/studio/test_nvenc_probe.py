# tests/studio/test_nvenc_probe.py
#
# item: מודעות למגבלת סשנים אמיתית של NVENC - כל קריאה ל-subprocess.run
# ממופתחת (לא נוגע בפועל ב-ffmpeg/GPU אמיתי בטסטים), אבל בודק את לוגיקת
# הספירה/הריכוז עם בו-זמניות אמיתית (ThreadPoolExecutor אמיתי, לא ממופתח).
import threading


from utils.media import nvenc_probe


class _FakeResult:
    def __init__(self, returncode):
        self.returncode = returncode


def test_probe_returns_zero_when_all_encodes_fail(monkeypatch):
    monkeypatch.setattr(nvenc_probe.subprocess, "run", lambda *a, **kw: _FakeResult(1))
    assert nvenc_probe.probe_max_concurrent_nvenc_sessions("ffmpeg", max_to_try=4) == 0


def test_probe_returns_max_to_try_when_all_encodes_succeed(monkeypatch):
    monkeypatch.setattr(nvenc_probe.subprocess, "run", lambda *a, **kw: _FakeResult(0))
    assert nvenc_probe.probe_max_concurrent_nvenc_sessions("ffmpeg", max_to_try=5) == 5


def test_probe_counts_only_the_encodes_that_actually_succeeded(monkeypatch):
    # מדמה כרטיס עם מגבלה אמיתית של 3 סשנים מקבילים - קריאות 1-3 מצליחות,
    # 4+ נכשלות (בדיוק איך NVENC בפועל מסרב לפתוח סשן נוסף מעבר למגבלה).
    call_count = {"n": 0}
    lock = threading.Lock()

    def fake_run(*args, **kwargs):
        with lock:
            call_count["n"] += 1
            n = call_count["n"]
        return _FakeResult(0 if n <= 3 else 1)

    monkeypatch.setattr(nvenc_probe.subprocess, "run", fake_run)
    result = nvenc_probe.probe_max_concurrent_nvenc_sessions("ffmpeg", max_to_try=8)
    assert result == 3


def test_probe_treats_exception_as_failure_not_crash(monkeypatch):
    def _raise(*a, **kw):
        raise OSError("ffmpeg not found")
    monkeypatch.setattr(nvenc_probe.subprocess, "run", _raise)
    assert nvenc_probe.probe_max_concurrent_nvenc_sessions("ffmpeg", max_to_try=4) == 0


def test_probe_treats_timeout_as_failure(monkeypatch):
    import subprocess as real_subprocess

    def _timeout(*a, **kw):
        raise real_subprocess.TimeoutExpired(cmd="ffmpeg", timeout=30)
    monkeypatch.setattr(nvenc_probe.subprocess, "run", _timeout)
    assert nvenc_probe.probe_max_concurrent_nvenc_sessions("ffmpeg", max_to_try=3) == 0


def test_probe_with_zero_max_to_try_does_not_call_subprocess(monkeypatch):
    monkeypatch.setattr(nvenc_probe.subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not be called")))
    assert nvenc_probe.probe_max_concurrent_nvenc_sessions("ffmpeg", max_to_try=0) == 0


def test_probe_uses_the_requested_codec(monkeypatch):
    seen_cmds = []

    def fake_run(cmd, **kwargs):
        seen_cmds.append(cmd)
        return _FakeResult(0)

    monkeypatch.setattr(nvenc_probe.subprocess, "run", fake_run)
    nvenc_probe.probe_max_concurrent_nvenc_sessions("ffmpeg", codec="av1_nvenc", max_to_try=2)
    assert all("av1_nvenc" in cmd for cmd in seen_cmds)


def test_probe_frame_is_above_the_nvenc_minimum_size(monkeypatch):
    """25.10.2026: הבדיקה קודדה 64x64 - NVENC דוחה 128x128 ומטה ("Frame Dimension less than the minimum"), אז היא
    החזירה 0 גם על RTX 4070 SUPER תקין, ומגבלת הסשנים ב---parallel לא הופעלה אף פעם."""
    seen_cmds = []

    def fake_run(cmd, **kwargs):
        seen_cmds.append(cmd)
        return _FakeResult(0)

    monkeypatch.setattr(nvenc_probe.subprocess, "run", fake_run)
    nvenc_probe.probe_max_concurrent_nvenc_sessions("ffmpeg", max_to_try=1)
    source = seen_cmds[0][seen_cmds[0].index("-i") + 1]
    width, height = (int(n) for n in source.split("size=")[1].split(":")[0].split("x"))
    assert width >= 145 and height >= 49     # המינימום שנמדד ל-h264_nvenc ול-hevc_nvenc


def test_probe_finds_a_real_nvenc_session_when_the_card_has_one():
    """על מכונה עם NVENC אמיתי (dataviz.render.nvenc_available - קידוד 256x256) הבדיקה צריכה למצוא לפחות סשן אחד."""
    import shutil

    import pytest

    from dataviz.render import nvenc_available
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not nvenc_available(ffmpeg):
        pytest.skip("אין NVENC במכונה הזו")
    assert nvenc_probe.probe_max_concurrent_nvenc_sessions(ffmpeg, codec="h264_nvenc", max_to_try=1) == 1
