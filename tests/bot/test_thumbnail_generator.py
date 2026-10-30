# tests/bot/test_thumbnail_generator.py
#
# בודק _motion_score (בחירת הפריים עם הכי הרבה "תזוזה" בין תמונות מועמדות) עם
# תמונות בדיקה סינתטיות אמיתיות (PIL, לא mock) - קובץ תמונה אמיתי עם cv2.imread
# אמיתי, בלי צורך בקובץ וידאו/ffmpeg בכלל, כי הפונקציה הזו עצמה עובדת רק על
# פריימים שכבר חולצו כתמונות.


from PIL import Image

import utils.media.thumbnail_generator as thumbnail_generator
from utils.media.thumbnail_generator import _motion_score
from utils.video.video_editor import HDR_TONEMAP_FILTER


def _make_solid_image(path, color):
    Image.new("RGB", (64, 64), color).save(path)


def test_motion_score_picks_frame_with_biggest_change(tmp_path):
    # שלושה פריימים: שני ראשונים כמעט זהים (הפרש קטן), השלישי שונה לגמרי
    # (הפרש גדול) - צריך לבחור באינדקס 2 (הכי הרבה "תזוזה" מהפריים שלפניו).
    p0 = tmp_path / "f0.png"
    p1 = tmp_path / "f1.png"
    p2 = tmp_path / "f2.png"
    _make_solid_image(p0, (10, 10, 10))
    _make_solid_image(p1, (12, 12, 12))
    _make_solid_image(p2, (250, 250, 250))

    assert _motion_score([str(p0), str(p1), str(p2)]) == 2


def test_motion_score_with_identical_frames_picks_second(tmp_path):
    # best_score מתחיל מ--1 (סנטינל) - ההשוואה הראשונה (i=1) תמיד "מנצחת" עם
    # score=0.0 (0.0 > -1), גם כששני הפריימים זהים לגמרי; רק השוואות מאוחרות
    # יותר עם אותו score=0.0 בדיוק לא "מנצחות" (0.0 > 0.0 הוא False). לא משנה
    # בפועל (כל פריים זהה תקף באותה מידה כתמונה ממוזערת), אבל זו ההתנהגות
    # האמיתית שכדאי לתעד במקום להניח שהיא "אינדקס 0".
    p0 = tmp_path / "f0.png"
    p1 = tmp_path / "f1.png"
    _make_solid_image(p0, (100, 100, 100))
    _make_solid_image(p1, (100, 100, 100))

    assert _motion_score([str(p0), str(p1)]) == 1


def test_motion_score_skips_unreadable_frames(tmp_path):
    good = tmp_path / "good.png"
    _make_solid_image(good, (50, 50, 50))
    missing = tmp_path / "does_not_exist.png"

    # לא אמור לזרוק חריגה על פריים שלא ניתן לקריאה (cv2.imread מחזיר None) -
    # פשוט מדלג עליו.
    assert _motion_score([str(missing), str(good)]) == 0


# --- tonemap_hdr (item: שימור הגדרות HDR - תמונה ממוזערת תמיד ב-SDR) ---

def test_extract_frame_at_timestamp_adds_tonemap_filter_when_requested(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(thumbnail_generator.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    out_path = str(tmp_path / "out.jpg")
    thumbnail_generator.extract_frame_at_timestamp("in.mp4", 1.0, out_path, "ffmpeg", tonemap_hdr=True)

    assert len(calls) == 1
    cmd = calls[0]
    assert "-vf" in cmd
    assert cmd[cmd.index("-vf") + 1] == HDR_TONEMAP_FILTER


def test_extract_frame_at_timestamp_no_tonemap_filter_by_default(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(thumbnail_generator.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    out_path = str(tmp_path / "out.jpg")
    thumbnail_generator.extract_frame_at_timestamp("in.mp4", 1.0, out_path, "ffmpeg")

    assert "-vf" not in calls[0]


# ---------- הכותרת על התמונה (_draw_title_text) ----------
# Pillow בלי libraqm (כך ב-Windows) צייר עברית עם האותיות בסדר הפוך, וכותרת ארוכה נחתכה בשני הצדדים - פוגע
# בתמונות הממוזערות של Rocket ושל הסטודיו. בודקים על פריים אפור סינתטי, בלי וידאו ובלי ffmpeg.
LONG_HEBREW_TITLE = "25 שנות ירי מעזה: איזו שנה הייתה הקשה ביותר?"


def _gray_frame(tmp_path, size=(800, 450)):
    path = tmp_path / "frame.png"
    Image.new("RGB", size, (120, 130, 140)).save(path)
    return str(path)


def _white_mask(path, band_from=0.55):
    """פיקסלי המילוי הלבן של הכותרת ברצועה התחתונה (קו המתאר שחור, הרקע אפור)."""
    import numpy as np
    pixels = np.asarray(Image.open(path).convert("RGB")).astype(int)
    return pixels[int(pixels.shape[0] * band_from):].min(axis=2) > 225


def _runs(indices):
    """רצפים של אינדקסים עוקבים: [(התחלה, סוף), ...]."""
    import numpy as np
    assert len(indices), "לא צוירה כותרת"
    breaks = np.flatnonzero(np.diff(indices) > 1)
    starts = [indices[0]] + [indices[b + 1] for b in breaks]
    ends = [indices[b] for b in breaks] + [indices[-1]]
    return list(zip(starts, ends))


def _column_runs(path):
    import numpy as np
    return _runs(np.flatnonzero(_white_mask(path).any(axis=0)))


def _row_runs(path, min_gap=4):
    import numpy as np
    rows = np.flatnonzero(_white_mask(path).any(axis=1))
    merged = []
    for start, end in _runs(rows):
        if merged and start - merged[-1][1] <= min_gap:   # חורים קטנים בתוך אותה שורה (נקודות, ניקוד)
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def test_hebrew_title_reads_right_to_left(tmp_path):
    out = str(tmp_path / "thumb.jpg")
    thumbnail_generator._draw_title_text(_gray_frame(tmp_path), "1 שששש", out)
    runs = _column_runs(out)
    gaps = [runs[i + 1][0] - runs[i][1] for i in range(len(runs) - 1)]
    space = gaps.index(max(gaps))
    # "1" (תחילת המשפט) מימין, ארבע האותיות משמאל לרווח
    assert (space + 1, len(runs) - space - 1) == (4, 1), runs


def test_hebrew_letters_keep_their_order_inside_a_word(tmp_path):
    out = str(tmp_path / "thumb.jpg")
    thumbnail_generator._draw_title_text(_gray_frame(tmp_path), "וששש", out)
    runs = _column_runs(out)
    widths = [end - start for start, end in runs]
    assert len(runs) == 4, runs
    # ו (האות הראשונה, הצרה) בקצה הימני
    assert widths.index(min(widths)) == 3, runs


def test_long_hebrew_title_is_not_clipped_and_breaks_into_two_lines(tmp_path):
    out = str(tmp_path / "thumb.jpg")
    thumbnail_generator._draw_title_text(_gray_frame(tmp_path), LONG_HEBREW_TITLE, out)
    runs = _column_runs(out)
    assert runs[0][0] >= 800 * 0.03 and runs[-1][1] <= 800 * 0.97, runs
    assert len(_row_runs(out)) == 2
    assert Image.open(out).size == (800, 450)


def test_short_title_stays_on_one_line(tmp_path):
    out = str(tmp_path / "thumb.jpg")
    thumbnail_generator._draw_title_text(_gray_frame(tmp_path), "Shorts #7", out)
    assert len(_row_runs(out)) == 1
