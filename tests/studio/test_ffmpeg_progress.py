# tests/studio/test_ffmpeg_progress.py
#
# run_ffmpeg_with_progress הופיע כמעט זהה בשלושה סקריפטים נפרדים (עותק-הדבק) -
# אוחד ל-utils/media/ffmpeg_progress.py. לא נבדק ביחידה באף אחד מהם קודם (משלב
# ffmpeg אמיתי) - כאן מריצים פקודת פייתון מזויפת (בלי ffmpeg בכלל) שמדפיסה
# שורות "frame=N" ל-stderr, כדי לבדוק את פרסור ההתקדמות וקוד היציאה בבידוד.
import sys
import threading


import utils.media.ffmpeg_progress as ffmpeg_progress
from utils.media.ffmpeg_progress import run_ffmpeg_with_progress, run_ffmpeg_with_progress_and_nvenc_retry


def _record_sleeps(monkeypatch):
    """time.sleep הוא גלובלי - רושם רק קריאות מה-thread של הטסט; thread-ים ברקע
    (למשל דוגם ה-GPU של utils.shared.hardware שהתחיל בטסט קודם) ממשיכים לישון באמת."""
    sleeps, real_sleep, test_thread = [], ffmpeg_progress.time.sleep, threading.current_thread()
    monkeypatch.setattr(ffmpeg_progress.time, "sleep",
                        lambda s: sleeps.append(s) if threading.current_thread() is test_thread else real_sleep(s))
    return sleeps


def _fake_ffmpeg_cmd(exit_code):
    script = (
        "import sys\n"
        "for frame in (10, 20, 30):\n"
        "    print('frame=' + str(frame), file=sys.stderr)\n"
        f"sys.exit({exit_code})\n"
    )
    return [sys.executable, "-c", script]


def test_run_ffmpeg_with_progress_success():
    ok = run_ffmpeg_with_progress(_fake_ffmpeg_cmd(0), total_frames=30, description="test")
    assert ok is True


def test_run_ffmpeg_with_progress_failure_returns_false():
    ok = run_ffmpeg_with_progress(_fake_ffmpeg_cmd(1), total_frames=30, description="test")
    assert ok is False


def test_run_ffmpeg_with_progress_accepts_position_param():
    # rocket_shorts_publisher.py משתמש ב-position>0 לפסים מקבילים - וידוא
    # שהפרמטר עדיין מתקבל אחרי האיחוד, לא רק ברירת המחדל 0.
    ok = run_ffmpeg_with_progress(_fake_ffmpeg_cmd(0), total_frames=30, description="test", position=2)
    assert ok is True


# --- NVENC session-limit retry (item) ---

def _fake_ffmpeg_cmd_with_stderr(exit_code, stderr_text):
    script = (
        "import sys\n"
        f"sys.stderr.write({stderr_text!r} + '\\n')\n"
        "print('frame=10', file=sys.stderr)\n"
        f"sys.exit({exit_code})\n"
    )
    return [sys.executable, "-c", script]


def _fake_ffmpeg_cmd_counting(counter_path, fail_stderr_text, fail_times):
    # נכשל (עם fail_stderr_text) ב-fail_times הפעמים הראשונות (סופר דרך
    # counter_path, כי כל קריאה היא תת-תהליך חדש-לגמרי בלי זיכרון משותף),
    # מצליח מהפעם הבאה והלאה - מדמה "session התפנה אחרי כמה ניסיונות".
    script = (
        "import sys\n"
        f"path = {counter_path!r}\n"
        "try:\n"
        "    with open(path) as f: n = int(f.read().strip() or '0')\n"
        "except FileNotFoundError:\n"
        "    n = 0\n"
        "n += 1\n"
        "with open(path, 'w') as f: f.write(str(n))\n"
        f"if n <= {fail_times}:\n"
        f"    sys.stderr.write({fail_stderr_text!r} + '\\n')\n"
        "    sys.exit(1)\n"
        "print('frame=10', file=sys.stderr)\n"
        "sys.exit(0)\n"
    )
    return [sys.executable, "-c", script]


def test_nvenc_retry_not_triggered_when_is_nvenc_false():
    # is_nvenc=False (h264) - נכשל פעם אחת ומחזיר מיד, בלי לנסות שוב, גם אם
    # ה-stderr היה מכיל את אחד הסימנים (לא רלוונטי - h264 לא יכול בכלל
    # להיכשל מהסיבה הזו).
    cmd = _fake_ffmpeg_cmd_with_stderr(1, "OpenEncodeSessionEx failed: out of memory (10)")
    ok = run_ffmpeg_with_progress_and_nvenc_retry(cmd, total_frames=10, description="test", is_nvenc=False)
    assert ok is False


def test_nvenc_retry_not_triggered_for_unrelated_failure(monkeypatch):
    # is_nvenc=True אבל השגיאה לא תואמת אף סימן מוכר - לא מנסה שוב (לא רוצים
    # להסתיר כשל אמיתי, למשל פרמטר שגוי, מאחורי ניסיונות-חוזרים מיותרים).
    sleeps = _record_sleeps(monkeypatch)
    cmd = _fake_ffmpeg_cmd_with_stderr(1, "Unknown encoder option")
    ok = run_ffmpeg_with_progress_and_nvenc_retry(cmd, total_frames=10, description="test", is_nvenc=True)
    assert ok is False
    assert sleeps == []


def test_nvenc_retry_succeeds_after_session_frees_up(tmp_path, monkeypatch):
    sleeps = _record_sleeps(monkeypatch)
    counter_path = str(tmp_path / "attempts.txt")
    cmd = _fake_ffmpeg_cmd_counting(counter_path, "OpenEncodeSessionEx failed: out of memory (10)", fail_times=2)
    ok = run_ffmpeg_with_progress_and_nvenc_retry(
        cmd, total_frames=10, description="test", is_nvenc=True, max_retries=3, retry_delay_seconds=0.01,
    )
    assert ok is True
    assert len(sleeps) == 2  # שני ניסיונות כושלים לפני ההצלחה בשלישי


def test_nvenc_retry_gives_up_after_max_retries(tmp_path, monkeypatch):
    sleeps = _record_sleeps(monkeypatch)
    counter_path = str(tmp_path / "attempts.txt")
    # נכשל תמיד (fail_times גדול מכל ניסיון סביר) - עם max_retries=2, אמור
    # להתייאש אחרי 3 ניסיונות כוללים (הראשון + 2 חוזרים).
    cmd = _fake_ffmpeg_cmd_counting(counter_path, "encoder busy", fail_times=999)
    ok = run_ffmpeg_with_progress_and_nvenc_retry(
        cmd, total_frames=10, description="test", is_nvenc=True, max_retries=2, retry_delay_seconds=0.01,
    )
    assert ok is False
    assert len(sleeps) == 2
    with open(counter_path) as f:
        assert int(f.read().strip()) == 3  # 3 ניסיונות בפועל (1 + max_retries)


def test_nvenc_retry_default_backoff_grows_exponentially(tmp_path, monkeypatch):
    # item: תוקן אחרי כשל אמיתי בפרודקשן - ברירת המחדל (בלי override) צריכה
    # לתת budget של כמה דקות (session תפוס אחר הוא בד"כ קידוד 4K מלא, לא רגע
    # חולף), לא רק 3 ניסיונות של 10s קבועים כמו קודם. jitter מבוטל כאן (מוקבע
    # ל-1.0) כדי לבדוק רק את צורת הצמיחה המעריכית עצמה, לא את הרעש האקראי.
    sleeps = _record_sleeps(monkeypatch)
    monkeypatch.setattr(ffmpeg_progress.random, "uniform", lambda a, b: 1.0)
    counter_path = str(tmp_path / "attempts.txt")
    cmd = _fake_ffmpeg_cmd_counting(counter_path, "no capacity for new encoding session", fail_times=999)
    ok = run_ffmpeg_with_progress_and_nvenc_retry(cmd, total_frames=10, description="test", is_nvenc=True)
    assert ok is False
    assert len(sleeps) == 6  # ברירת המחדל החדשה: max_retries=6, לא 3
    assert sleeps == sorted(sleeps) and sleeps[0] < sleeps[-1]  # גדל מעריכית, לא קבוע
    assert sum(sleeps) > 120  # budget כולל של כמה דקות, לא עשרות שניות בודדות


def test_nvenc_retry_applies_jitter_to_delay(tmp_path, monkeypatch):
    sleeps = _record_sleeps(monkeypatch)
    monkeypatch.setattr(ffmpeg_progress.random, "uniform", lambda a, b: 1.15)
    counter_path = str(tmp_path / "attempts.txt")
    cmd = _fake_ffmpeg_cmd_counting(counter_path, "encoder busy", fail_times=1)
    ok = run_ffmpeg_with_progress_and_nvenc_retry(
        cmd, total_frames=10, description="test", is_nvenc=True, retry_delay_seconds=10.0,
    )
    assert ok is True
    assert sleeps == [10.0 * 1.15]
