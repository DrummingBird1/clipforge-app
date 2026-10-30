# utils/media/thumbnail_generator.py
#
# מחלץ כמה פריימים מועמדים מהסרטון המרונדר, בוחר את זה עם הכי הרבה "תזוזה"
# (proxy סביר לרגע דרמטי/פעולה) לפי הפרש בין פריימים ב-OpenCV, ומרכיב עליו
# כותרת מודגשת בסגנון thumbnail של ערוצי גיימינג.

import os
import subprocess
import tempfile

import cv2

from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.video.video_editor import HDR_TONEMAP_FILTER

CANDIDATE_TIMESTAMPS_PCT = [0.15, 0.35, 0.55, 0.75, 0.9]


def get_video_duration_via_ffprobe(video_path, ffprobe_exe):
    cmd = [ffprobe_exe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_path]
    try:
        out = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, timeout=15, creationflags=NO_WINDOW_FLAGS).stdout.strip()
        return float(out)
    except Exception:
        return 10.0


def extract_frame_at_timestamp(video_path, timestamp, out_path, ffmpeg_exe, tonemap_hdr=False):
    """tonemap_hdr (item: שימור הגדרות HDR - תמונה ממוזערת תמיד ב-SDR) - כש-
    video_path עצמו הוא קובץ HDR (10-bit + PQ/HLG metadata), חילוץ פריים
    ל-JPEG רגיל בלי tone-mapping מפיק תמונה שטופה/דהויה (אותו באג שה-HDR
    pass-through בפלט הווידאו נועד למנוע, פשוט מועתק לתמונה הממוזערת) -
    HDR_TONEMAP_FILTER (utils/video/video_editor.py) ממיר ל-SDR נכון קודם."""
    cmd = [ffmpeg_exe, "-y", "-ss", str(timestamp), "-i", video_path]
    if tonemap_hdr:
        cmd += ["-vf", HDR_TONEMAP_FILTER]
    cmd += ["-vframes", "1", "-q:v", "2", out_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, creationflags=NO_WINDOW_FLAGS)
    return os.path.exists(out_path)


def _motion_score(frame_paths):
    """מחזיר את האינדקס עם ההפרש הכי גדול מהפריים שלפניו - proxy לפעולה/דרמה."""
    best_idx = 0
    best_score = -1
    prev_gray = None
    for i, path in enumerate(frame_paths):
        img = cv2.imread(path)
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            score = diff.mean()
            if score > best_score:
                best_score = score
                best_idx = i
        prev_gray = gray
    return best_idx


def _draw_title_text(image_path, text, out_path):
    """כותרת לבנה עם קו מתאר על רצועה כהה בתחתית - דרך utils/dataviz_thumbnail.draw_title (matplotlib), אותה
    פונקציה של התמונות הממוזערות של סרטוני הנתונים. קודם צוירה כאן ב-Pillow, ובלי libraqm (כך ב-Windows) כותרת
    בעברית יצאה עם האותיות בסדר הפוך וכותרת ארוכה נחתכה בשני הצדדים - ב-Rocket ובסטודיו. עכשיו גם מוקטנת או
    נשברת לשתי שורות עד שהיא נכנסת ברוחב."""
    from utils.dataviz_thumbnail import draw_title

    draw_title(image_path, text, out_path)


def generate_thumbnail(video_path, out_path, ffmpeg_exe="ffmpeg", ffprobe_exe="ffprobe", title_text=None, tonemap_hdr=False):
    """
    יוצר תמונה ממוזערת מתוך video_path ושומר אותה ל-out_path.
    זורק חריגה אם נכשל - האחראי מטפל בזה (התכונה אופציונלית ולא אמורה לעצור פייפליין רינדור).
    tonemap_hdr - ראו extract_frame_at_timestamp.
    """
    duration = get_video_duration_via_ffprobe(video_path, ffprobe_exe)

    with tempfile.TemporaryDirectory() as tmp_dir:
        frame_paths = []
        for i, pct in enumerate(CANDIDATE_TIMESTAMPS_PCT):
            ts = max(0.1, duration * pct)
            frame_path = os.path.join(tmp_dir, f"cand_{i}.jpg")
            if extract_frame_at_timestamp(video_path, ts, frame_path, ffmpeg_exe, tonemap_hdr=tonemap_hdr):
                frame_paths.append(frame_path)

        if not frame_paths:
            raise RuntimeError("לא הצליח לחלץ אף פריים מועמד מהסרטון")

        best_idx = _motion_score(frame_paths) if len(frame_paths) > 1 else 0
        chosen_frame = frame_paths[best_idx]

        text = title_text or os.path.splitext(os.path.basename(video_path))[0]
        _draw_title_text(chosen_frame, text, out_path)

    return out_path
