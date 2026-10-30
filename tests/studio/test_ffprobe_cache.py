# tests/studio/test_ffprobe_cache.py
#
# בודק utils/media/ffprobe_cache.py (item 20) - קריאת ffprobe אחת בלבד לכל קובץ
# (במקום כמה נפרדות), עם מטמון בזיכרון+דיסק. subprocess.run עצמו ממוק
# (לא ffprobe אמיתי) כדי לספור קריאות בפועל בלי תלות בקובץ וידאו אמיתי -
# my_scripts/video/*_e2e.py הקיימים כבר מכסים אינטגרציה מול ffprobe אמיתי.
import json
import os
import threading


import utils.media.ffprobe_cache as ffprobe_cache


class _FakeCompletedProcess:
    def __init__(self, stdout):
        self.stdout = stdout


_FAKE_FFPROBE_JSON = json.dumps({
    "streams": [
        {"codec_type": "video", "width": 1920, "height": 1080},
        {"codec_type": "audio"},
    ],
    "format": {"duration": "12.5"},
})

_BASE_EXPECTED = {
    "duration": 12.5, "width": 1920, "height": 1080, "has_audio": True,
    "fps": None, "color_transfer": None, "color_primaries": None,
    "color_space": None, "pix_fmt": None,
}


def _reset_module_state(monkeypatch, cache_path):
    monkeypatch.setattr(ffprobe_cache, "CACHE_PATH", cache_path)
    ffprobe_cache._memory_cache.clear()
    ffprobe_cache._disk_cache_loaded = False


def test_probe_video_parses_duration_width_height_and_audio(tmp_path, monkeypatch):
    _reset_module_state(monkeypatch, str(tmp_path / "cache.json"))
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _FakeCompletedProcess(_FAKE_FFPROBE_JSON)

    monkeypatch.setattr(ffprobe_cache.subprocess, "run", fake_run)

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake video bytes")

    result = ffprobe_cache.probe_video(str(video_path))

    assert result == _BASE_EXPECTED
    assert len(calls) == 1


def test_probe_video_uses_memory_cache_on_second_call(tmp_path, monkeypatch):
    _reset_module_state(monkeypatch, str(tmp_path / "cache.json"))
    calls = []
    monkeypatch.setattr(ffprobe_cache.subprocess, "run", lambda cmd, **kw: (calls.append(cmd), _FakeCompletedProcess(_FAKE_FFPROBE_JSON))[1])

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake video bytes")

    ffprobe_cache.probe_video(str(video_path))
    ffprobe_cache.probe_video(str(video_path))

    assert len(calls) == 1, "הקריאה השנייה הייתה אמורה להיפגע ממטמון הזיכרון, לא לקרוא ל-ffprobe שוב"


def test_probe_video_uses_disk_cache_across_fresh_module_state(tmp_path, monkeypatch):
    # מדמה "תהליך חדש" (למשל שלב הבא בפייפליין, item 15) - מנקה את מטמון
    # הזיכרון אבל לא את קובץ המטמון על הדיסק, ומוודא שהוא עדיין נחסך מקריאה חדשה.
    cache_path = str(tmp_path / "cache.json")
    _reset_module_state(monkeypatch, cache_path)
    calls = []
    monkeypatch.setattr(ffprobe_cache.subprocess, "run", lambda cmd, **kw: (calls.append(cmd), _FakeCompletedProcess(_FAKE_FFPROBE_JSON))[1])

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake video bytes")

    ffprobe_cache.probe_video(str(video_path))
    assert len(calls) == 1

    # "תהליך חדש" - נקה זיכרון בלבד, קובץ הדיסק נשאר
    ffprobe_cache._memory_cache.clear()
    ffprobe_cache._disk_cache_loaded = False

    ffprobe_cache.probe_video(str(video_path))
    assert len(calls) == 1, "מטמון הדיסק היה אמור למנוע קריאת ffprobe נוספת גם אחרי ניקוי הזיכרון"


def test_probe_video_recomputes_when_file_changes(tmp_path, monkeypatch):
    # שינוי בקובץ (mtime/size שונה, כאילו נרנדר מחדש) חייב "לשבור" את המטמון -
    # תוצאה ישנה על קובץ שהשתנה בפועל גרועה בהרבה מקריאת ffprobe מיותרת.
    _reset_module_state(monkeypatch, str(tmp_path / "cache.json"))
    calls = []
    monkeypatch.setattr(ffprobe_cache.subprocess, "run", lambda cmd, **kw: (calls.append(cmd), _FakeCompletedProcess(_FAKE_FFPROBE_JSON))[1])

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"version one")
    ffprobe_cache.probe_video(str(video_path))
    assert len(calls) == 1

    video_path.write_bytes(b"version two - different size")
    ffprobe_cache.probe_video(str(video_path))
    assert len(calls) == 2, "קובץ שהשתנה (גודל/mtime שונה) היה אמור להיחשב כמפתח מטמון חדש"


def test_probe_video_handles_ffprobe_failure_gracefully(tmp_path, monkeypatch):
    _reset_module_state(monkeypatch, str(tmp_path / "cache.json"))

    def fake_run(cmd, **kwargs):
        raise OSError("ffprobe not found")

    monkeypatch.setattr(ffprobe_cache.subprocess, "run", fake_run)

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake video bytes")

    result = ffprobe_cache.probe_video(str(video_path))
    assert result == {
        "duration": None, "width": None, "height": None, "has_audio": False,
        "fps": None, "color_transfer": None, "color_primaries": None,
        "color_space": None, "pix_fmt": None,
    }


def test_probe_video_handles_clip_with_no_audio_stream(tmp_path, monkeypatch):
    _reset_module_state(monkeypatch, str(tmp_path / "cache.json"))
    no_audio_json = json.dumps({
        "streams": [{"codec_type": "video", "width": 640, "height": 360}],
        "format": {"duration": "3.0"},
    })
    monkeypatch.setattr(ffprobe_cache.subprocess, "run", lambda cmd, **kw: _FakeCompletedProcess(no_audio_json))

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake video bytes")

    result = ffprobe_cache.probe_video(str(video_path))
    assert result == {
        "duration": 3.0, "width": 640, "height": 360, "has_audio": False,
        "fps": None, "color_transfer": None, "color_primaries": None,
        "color_space": None, "pix_fmt": None,
    }


def test_cache_persists_to_disk_file(tmp_path, monkeypatch):
    cache_path = str(tmp_path / "cache.json")
    _reset_module_state(monkeypatch, cache_path)
    monkeypatch.setattr(ffprobe_cache.subprocess, "run", lambda cmd, **kw: _FakeCompletedProcess(_FAKE_FFPROBE_JSON))

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake video bytes")
    ffprobe_cache.probe_video(str(video_path))

    assert os.path.exists(cache_path)
    with open(cache_path, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert len(saved) == 1
    assert list(saved.values())[0] == _BASE_EXPECTED


def test_cache_evicts_oldest_entries_beyond_max_size(tmp_path, monkeypatch):
    _reset_module_state(monkeypatch, str(tmp_path / "cache.json"))
    monkeypatch.setattr(ffprobe_cache, "MAX_CACHE_ENTRIES", 3)
    monkeypatch.setattr(ffprobe_cache.subprocess, "run", lambda cmd, **kw: _FakeCompletedProcess(_FAKE_FFPROBE_JSON))

    for i in range(5):
        path = tmp_path / f"clip_{i}.mp4"
        path.write_bytes(f"clip {i}".encode())
        ffprobe_cache.probe_video(str(path))

    assert len(ffprobe_cache._memory_cache) == 3


# --- fps (item: שימור FPS מקורי) ---

def test_probe_video_parses_fps_from_r_frame_rate(tmp_path, monkeypatch):
    _reset_module_state(monkeypatch, str(tmp_path / "cache.json"))
    fps_json = json.dumps({
        "streams": [{"codec_type": "video", "width": 1920, "height": 1080, "r_frame_rate": "30000/1001", "avg_frame_rate": "30000/1001"}],
        "format": {"duration": "5.0"},
    })
    monkeypatch.setattr(ffprobe_cache.subprocess, "run", lambda cmd, **kw: _FakeCompletedProcess(fps_json))

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake video bytes")
    result = ffprobe_cache.probe_video(str(video_path))

    assert result["fps"] == "30000/1001"


def test_probe_video_falls_back_to_avg_frame_rate_when_r_frame_rate_unusable(tmp_path, monkeypatch):
    # "0/0" - איך ש-ffprobe מדווח על זרם בלי קצב-פריימים נומינלי ידוע.
    _reset_module_state(monkeypatch, str(tmp_path / "cache.json"))
    fps_json = json.dumps({
        "streams": [{"codec_type": "video", "width": 1920, "height": 1080, "r_frame_rate": "0/0", "avg_frame_rate": "25/1"}],
        "format": {"duration": "5.0"},
    })
    monkeypatch.setattr(ffprobe_cache.subprocess, "run", lambda cmd, **kw: _FakeCompletedProcess(fps_json))

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake video bytes")
    result = ffprobe_cache.probe_video(str(video_path))

    assert result["fps"] == "25/1"


def test_probe_video_fps_none_when_both_rates_unusable(tmp_path, monkeypatch):
    _reset_module_state(monkeypatch, str(tmp_path / "cache.json"))
    fps_json = json.dumps({
        "streams": [{"codec_type": "video", "width": 1920, "height": 1080, "r_frame_rate": "0/0", "avg_frame_rate": "0/0"}],
        "format": {"duration": "5.0"},
    })
    monkeypatch.setattr(ffprobe_cache.subprocess, "run", lambda cmd, **kw: _FakeCompletedProcess(fps_json))

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake video bytes")
    result = ffprobe_cache.probe_video(str(video_path))

    assert result["fps"] is None


# --- HDR (item: שימור הגדרות HDR) ---

def test_probe_video_parses_hdr_color_metadata(tmp_path, monkeypatch):
    _reset_module_state(monkeypatch, str(tmp_path / "cache.json"))
    hdr_json = json.dumps({
        "streams": [{
            "codec_type": "video", "width": 3840, "height": 2160,
            "color_transfer": "smpte2084", "color_primaries": "bt2020", "color_space": "bt2020nc", "pix_fmt": "yuv420p10le",
        }],
        "format": {"duration": "5.0"},
    })
    monkeypatch.setattr(ffprobe_cache.subprocess, "run", lambda cmd, **kw: _FakeCompletedProcess(hdr_json))

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake video bytes")
    result = ffprobe_cache.probe_video(str(video_path))

    assert result["color_transfer"] == "smpte2084"
    assert result["color_primaries"] == "bt2020"
    assert result["color_space"] == "bt2020nc"
    assert result["pix_fmt"] == "yuv420p10le"


# --- בטיחות-thread תחת גישה בו-זמנית (item: בדיקת באגים מקיפה) ---

def test_probe_video_is_thread_safe_under_concurrent_calls_with_eviction(tmp_path, monkeypatch):
    # לפני התיקון: --parallel>1 יכול היה לגרום ל-RuntimeError ("dictionary
    # changed size during iteration") כש-thread אחד מפנה-מקום (eviction) בזמן
    # ש-thread אחר מכניס ערך חדש, ולשבש את קובץ המטמון על הדיסק מכתיבות
    # בו-זמניות לא-מוגנות. MAX_CACHE_ENTRIES קטן כדי לאלץ eviction אמיתי
    # במהלך הריצה, לא רק בסוף.
    cache_path = str(tmp_path / "cache.json")
    _reset_module_state(monkeypatch, cache_path)
    monkeypatch.setattr(ffprobe_cache, "MAX_CACHE_ENTRIES", 5)
    monkeypatch.setattr(ffprobe_cache.subprocess, "run", lambda cmd, **kw: _FakeCompletedProcess(_FAKE_FFPROBE_JSON))

    paths = []
    for i in range(30):
        p = tmp_path / f"clip_{i}.mp4"
        p.write_bytes(f"clip {i}".encode())
        paths.append(str(p))

    errors = []

    def _probe(path):
        try:
            ffprobe_cache.probe_video(path)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=_probe, args=(p,)) for p in paths]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert errors == [], f"probe_video קרס תחת גישה בו-זמנית: {errors}"
    assert len(ffprobe_cache._memory_cache) == 5  # התקרה עדיין נאכפת נכון
    with open(cache_path, "r", encoding="utf-8") as f:
        json.load(f)  # קובץ המטמון על הדיסק עדיין JSON תקין, לא משובש


# --- migration מרשומות מטמון-דיסק ישנות (בלי השדות החדשים) ---

def test_probe_video_reprobes_when_cached_entry_predates_new_fields(tmp_path, monkeypatch):
    cache_path = str(tmp_path / "cache.json")
    _reset_module_state(monkeypatch, cache_path)

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake video bytes")
    key = ffprobe_cache._cache_key(str(video_path))
    # מדמה רשומת-מטמון מגרסה קודמת של הפונקציה, בלי "fps"/שדות הצבע בכלל.
    ffprobe_cache._memory_cache[key] = {"duration": 12.5, "width": 1920, "height": 1080, "has_audio": True}

    calls = []
    monkeypatch.setattr(ffprobe_cache.subprocess, "run", lambda cmd, **kw: (calls.append(cmd), _FakeCompletedProcess(_FAKE_FFPROBE_JSON))[1])

    result = ffprobe_cache.probe_video(str(video_path))

    assert len(calls) == 1, "רשומת-מטמון ישנה (בלי 'fps') הייתה אמורה להיחשב כ-cache miss ולהריץ ffprobe מחדש"
    assert result == _BASE_EXPECTED
