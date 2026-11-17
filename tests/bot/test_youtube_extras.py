# tests/bot/test_youtube_extras.py
#
# 16.11.2026 (2.0): utils/bot/youtube_extras.py - פרקים לפי הכללים של יוטיוב, Shorts, תזמון וכתוביות ליד הקובץ.
# פרקים מתוך קובץ אמיתי (ffmpeg כותב פרקים) - @needs_ffmpeg. בלי שום העלאה.
import datetime
import subprocess

import pytest

from tests.media_support import needs_ffmpeg
from utils.bot import youtube_extras as yx
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe


def test_chapters_start_at_zero_and_follow_youtubes_rules():
    text = yx.chapters_text([(12, "גול ראשון"), (40, "הצלה"), (95.5, "ניצחון")])
    assert text.splitlines() == ["00:00 פתיחה", "00:12 גול ראשון", "00:40 הצלה", "01:35 ניצחון"]


def test_short_chapters_merge_and_too_few_means_none():
    assert yx.chapters_text([(0, "א"), (5, "קצר"), (30, "ב")]) == ""          # אחרי המיזוג נשארים 2
    assert yx.chapters_text([(0, "a"), (20, "b"), (40, "c"), (55, "d")], duration=60).splitlines()[-1] == "00:40 c"


def test_long_videos_get_hours():
    assert yx.stamp(3723) == "1:02:03"


def test_shorts_detection_and_description():
    assert yx.is_short(1080, 1920, 45) and not yx.is_short(1920, 1080, 45) and not yx.is_short(1080, 1920, 400)
    assert yx.with_extras("גול", "00:00 א", short=True) == "גול\n\n00:00 א\n\n#Shorts"
    assert yx.with_extras("already #shorts", short=True) == "already #shorts"


def test_schedule_must_be_in_the_future_and_becomes_utc():
    now = datetime.datetime(2026, 11, 16, 12, 0, tzinfo=datetime.timezone.utc)
    assert yx.parse_publish_at("") == ""
    assert yx.parse_publish_at("2026-11-20T18:00:00+02:00", now=now) == "2026-11-20T16:00:00Z"
    with pytest.raises(ValueError):
        yx.parse_publish_at("2026-11-01T10:00:00Z", now=now)
    with pytest.raises(ValueError):
        yx.parse_publish_at("tomorrow", now=now)


def test_a_sidecar_srt_is_found(tmp_path):
    video = tmp_path / "goal.mp4"
    video.write_bytes(b"v")
    assert yx.sidecar_srt(str(video)) is None
    (tmp_path / "goal.srt").write_text("1", encoding="utf-8")
    assert yx.sidecar_srt(str(video)).endswith("goal.srt")


@needs_ffmpeg
def test_chapters_are_read_from_the_file_the_studio_wrote(tmp_path):
    meta = tmp_path / "meta.txt"
    meta.write_text(";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=12000\ntitle=פתיחה\n"
                    "[CHAPTER]\nTIMEBASE=1/1000\nSTART=12000\nEND=30000\ntitle=גול\n", encoding="utf-8")
    out = tmp_path / "v.mp4"
    subprocess.run([get_ffmpeg_exe(), "-hide_banner", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=5:duration=30",
                    "-i", str(meta), "-map_metadata", "1", "-c:v", "libx264", "-preset", "ultrafast", str(out)],
                   check=True, capture_output=True, timeout=120)
    assert yx.read_chapters(str(out), get_ffprobe_exe()) == [(0.0, "פתיחה"), (12.0, "גול")]


def test_the_caption_language_comes_from_the_name_then_the_text(tmp_path):
    # 2.0.0: כל קובץ כתוביות הועלה כ"עברית", גם כתוביות באנגלית
    from utils.bot import youtube_extras as ye
    hebrew, english, named = tmp_path / "a.srt", tmp_path / "b.srt", tmp_path / "c.en.srt"
    hebrew.write_text("1\n00:00:00,000 --> 00:00:01,000\nשלום\n", encoding="utf-8")
    english.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    named.write_text("1\n00:00:00,000 --> 00:00:01,000\nשלום\n", encoding="utf-8")
    assert (ye.srt_language(str(hebrew)), ye.srt_language(str(english)), ye.srt_language(str(named))) == ("he", "en", "en")
    assert ye.srt_language(str(tmp_path / "missing.srt")) == "en"
    empty_video = tmp_path / "v.mp4"
    empty_video.write_bytes(b"x")
    (tmp_path / "v.srt").write_bytes(b"")
    assert ye.sidecar_srt(str(empty_video)) is None            # קובץ כתוביות ריק לא מועלה


def test_captions_need_their_own_permission_and_old_tokens_keep_working(tmp_path, monkeypatch):
    # 2.0.0: ההרשאה לכתוביות לא התבקשה בכלל - כל העלאת כתוביות נכשלה ב-403, וההעלאה דווחה כהצלחה
    import json

    from utils.bot import youtube_uploader as yu
    assert yu.CAPTIONS_SCOPE not in yu.SCOPES                  # טוקן קיים לא נדרש להסכמה מחודשת בשביל העלאה רגילה
    token = tmp_path / "youtube_token.json"
    monkeypatch.setattr(yu, "TOKEN_FILE", str(token))
    assert yu.can_upload_captions() is False
    token.write_text(json.dumps({"scopes": yu.SCOPES}), encoding="utf-8")
    assert yu.can_upload_captions() is False
    token.write_text(json.dumps({"scopes": yu.SCOPES + [yu.CAPTIONS_SCOPE]}), encoding="utf-8")
    assert yu.can_upload_captions() is True
