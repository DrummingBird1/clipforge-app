# utils/media/ocr_highlights.py
#
# זיהוי רגעי שיא לפי טקסט-על-מסך (OCR), כתוסף לזיהוי שיאי-שמע הקיים ב-
# story_cutter.py. שיאי שמע לא תופסים רגעים ששקטים אקוסטית (אין קומנטרי/צעקה)
# אבל מוצג בהם טקסט HUD משמעותי (קילפיד, מסך ניצחון/הפסד וכו') - הפונקציות כאן
# סורקות את הסרטון כולו בדגימה קבועה בלי תלות בשיאי השמע בכלל.

import cv2
import pytesseract
from PIL import Image

OCR_SAMPLE_INTERVAL_SECONDS = 3

# מילות מפתח גנריות שמופיעות ב-HUD של רוב משחקי הגיימפליי ברגעי שיא - לא
# ספציפי למשחק אחד, כי בשלב הזה אין מידע על אילו משחקים בדיוק מוקלטים.
# כולל גם מילות מפתח בעברית (משחקים מלוקלזים לעברית, או כתוביות/מסכי-סיום
# בעברית שסטרימרים דוברי עברית מוסיפים בעצמם) - לא רלוונטי לכל משחק, בדיוק
# כמו הרשימה האנגלית, אבל לא עולה כלום להשאיר בברירת המחדל.
OCR_HIGHLIGHT_KEYWORDS = [
    "victory", "defeat", "eliminated", "elimination", "headshot",
    "double kill", "triple kill", "multi kill", "you died", "game over",
    "winner winner", "mvp", "wasted", "you win", "you lose",
    "round win", "round lost", "flawless victory",
    "ניצחון", "הפסד", "תבוסה", "המשחק נגמר", "נוצחת", "אתה מת", "סיבוב הסתיים",
]


def text_matches_highlight_keywords(text, extra_keywords=None):
    """
    מחזיר את מילת המפתח הראשונה שנמצאה בטקסט (case-insensitive), או None.
    extra_keywords מצטרפות לרשימה הגנרית - למשחקים בלי HUD של קילפיד/ניצחון
    (למשל משחקי סיפור מבוססי דיאלוג/כתוביות, שם המילים הרלוונטיות משתנות לגמרי
    ממשחק למשחק ולא ניתן לקבוע רשימה גנרית אחת שתתאים לכולם).
    """
    lowered = (text or "").lower()
    for keyword in [*OCR_HIGHLIGHT_KEYWORDS, *(extra_keywords or [])]:
        if keyword in lowered:
            return keyword
    return None


def merge_peaks_with_gap(existing_peaks, candidate_peaks, min_gap_seconds):
    """
    ממזג שתי רשימות של (זמן, מקור) - מוסיף מ-candidate_peaks רק נקודות שרחוקות
    מספיק (min_gap_seconds) מכל נקודה שכבר התקבלה, כך שאותו רגע לא נספר פעמיים
    כשגם שיא-שמע וגם התאמת-OCR נופלים קרוב מדי אחד לשני.
    """
    merged = list(existing_peaks)
    accepted_times = [p[0] for p in merged]
    for time_point, label in sorted(candidate_peaks, key=lambda p: p[0]):
        if all(abs(time_point - t) >= min_gap_seconds for t in accepted_times):
            merged.append((time_point, label))
            accepted_times.append(time_point)
    merged.sort(key=lambda p: p[0])
    return merged


_ocr_lang_cache = None


def _resolve_ocr_lang():
    """מוסיף עברית (heb) לזיהוי ה-OCR רק אם ה-language pack שלה מותקן בפועל
    אצל המשתמש - pytesseract זורק חריגה על שפה לא מותקנת, וזו חריגה גורפת
    שהייתה שוברת גם את הזיהוי האנגלי הבסיסי (eng+heb נכשל כולו אם heb חסר, לא
    סתם מתעלם ממנה). נשמר ב-cache מודול (לא מחושב מחדש על כל פריים נדגם -
    get_languages() קורא ל-tesseract כתת-תהליך, לא משהו לחזור עליו כל 3 שניות)."""
    global _ocr_lang_cache
    if _ocr_lang_cache is None:
        try:
            available = pytesseract.get_languages(config="")
            _ocr_lang_cache = "eng+heb" if "heb" in available else "eng"
        except Exception:
            _ocr_lang_cache = "eng"
    return _ocr_lang_cache


def find_ocr_highlight_timestamps(video_path, duration, tesseract_cmd=None, sample_interval=OCR_SAMPLE_INTERVAL_SECONDS, extra_keywords=None):
    """
    סורק את כל הסרטון בדגימה קבועה (ברירת מחדל: כל 3 שניות) ומריץ OCR על כל
    פריים נדגם, מחפש מילות מפתח של רגעי שיא. מחזיר רשימת (זמן, "ocr:<מילה>").
    """
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    ocr_lang = _resolve_ocr_lang()

    hits = []
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return hits

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        t = 0.0
        while t < duration:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ok, frame = cap.read()
            if ok:
                try:
                    frame_rgb = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    text = pytesseract.image_to_string(frame_rgb, lang=ocr_lang)
                except Exception:
                    text = ""
                keyword = text_matches_highlight_keywords(text, extra_keywords)
                if keyword:
                    hits.append((t, f"ocr:{keyword}"))
            t += sample_interval
    finally:
        cap.release()

    return hits
