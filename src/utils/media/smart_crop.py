# utils/media/smart_crop.py
#
# מחשב היסט קרופ אופטימלי לפורמט האנכי (9:16) לפי מרכז המסה של התזוזה בסרטון,
# במקום קרופ קבוע במרכז שחותך פעולה שקורית בצדדים. גרסה סטטית (היסט אחד לכל
# סרטון, לא פאן דינמי לאורך זמן) - יציבה, קלה לאימות, ועדיין שיפור אמיתי מול
# קרופ מרכזי נאיבי.
#
# שני מצבי-חישוב עם אותו חוזה-החזרה בדיוק (offset ב--1.0..1.0, נופל ל-0.0 בכל
# כשל): compute_horizontal_crop_offset (תזוזה) ו-compute_horizontal_crop_offset_face
# (פנים, item: קרופ חכם לפי זיהוי-פנים). opencv-python 5.x שמותקן בפרויקט הזה
# הסיר לגמרי את cv2.CascadeClassifier/haarcascade הישן - זיהוי הפנים כאן משתמש
# ב-API החדש מבוסס-DNN (cv2.FaceDetectorYN) עם מודל YuNet שמצורף ל-assets/
# (לא מגיע מובנה בשום מקום, בניגוד ל-Haar הישן).

import os

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FACE_MODEL_PATH = os.path.join(BASE_DIR, "assets", "face_detection_yunet_2023mar.onnx")


def compute_horizontal_crop_offset(video_path, sample_frames=40):
    """
    מחזיר ערך בין -1.0 (הכי שמאלה) ל-1.0 (הכי ימינה) שמייצג לאן להזיז את חלון
    הקרופ האנכי ממרכז הפריים, לפי איפה שרוב התזוזה בווידאו מתרחשת.
    מחזיר 0.0 (מרכז, זהה להתנהגות הקודמת) אם הניתוח נכשל מכל סיבה שהיא.
    """
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return 0.0

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        if total_frames <= 1 or width <= 0:
            cap.release()
            return 0.0

        step = max(1, total_frames // sample_frames)

        prev_gray = None
        weighted_x_sum = 0.0
        weight_sum = 0.0

        frame_idx = 0
        while frame_idx < total_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok, frame = cap.read()
            if not ok:
                break

            small = cv2.resize(frame, (160, 90))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
                ys, xs = np.nonzero(thresh)
                if len(xs) > 20:  # מספיק פיקסלים "זזים" כדי שזה יהיה משמעותי, לא רעש
                    motion_center_x = xs.mean() / thresh.shape[1]  # 0..1
                    frame_motion_amount = len(xs)
                    weighted_x_sum += motion_center_x * frame_motion_amount
                    weight_sum += frame_motion_amount

            prev_gray = gray
            frame_idx += step

        cap.release()

        if weight_sum == 0:
            return 0.0

        avg_center_x = weighted_x_sum / weight_sum  # 0..1, 0.5 = מרכז
        offset = (avg_center_x - 0.5) * 2  # ממיר ל--1..1
        return max(-1.0, min(1.0, offset))
    except Exception:
        return 0.0


def compute_horizontal_crop_offset_face(video_path, sample_frames=15):
    """
    כמו compute_horizontal_crop_offset, אבל לפי מיקום פנים שזוהו (cv2.FaceDetectorYN
    + מודל YuNet) במקום תזוזה כללית - שימושי בעיקר לראיונות/טוקינג-הד שבהם
    הפעולה החשובה היא תמיד הפנים, גם כשאין תזוזה גדולה בפריים. דוגם פחות פריימים
    מהגרסה מבוססת-התזוזה (15 מול 40) כי זיהוי-פנים DNN יקר משמעותית מ-diff פשוט
    בין שני פריימים. נופל ל-0.0 (מרכז) גם אם המודל חסר/לא נטען, לא רק על שגיאת
    ניתוח - קרש חכם שלא אמור להפיל batch שלם.
    """
    try:
        if not os.path.isfile(FACE_MODEL_PATH):
            return 0.0

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return 0.0

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if total_frames <= 0 or width <= 0 or height <= 0:
            cap.release()
            return 0.0

        detector = cv2.FaceDetectorYN_create(FACE_MODEL_PATH, "", (width, height))
        step = max(1, total_frames // sample_frames)

        weighted_x_sum = 0.0
        weight_sum = 0.0

        frame_idx = 0
        while frame_idx < total_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok, frame = cap.read()
            if not ok:
                break

            _, faces = detector.detect(frame)
            if faces is not None:
                for face in faces:
                    x, w, confidence = face[0], face[2], face[-1]
                    face_center_x = (x + w / 2) / width  # 0..1
                    weighted_x_sum += face_center_x * confidence
                    weight_sum += confidence

            frame_idx += step

        cap.release()

        if weight_sum == 0:
            return 0.0

        avg_center_x = weighted_x_sum / weight_sum  # 0..1, 0.5 = מרכז
        offset = (avg_center_x - 0.5) * 2  # ממיר ל--1..1
        return max(-1.0, min(1.0, offset))
    except Exception:
        return 0.0


def offset_to_crop_x_expr(offset, crop_width):
    """
    בונה ביטוי x= לפילטר crop של ffmpeg (המשתנים הזמינים שם הם in_w/in_h/out_w/out_h,
    לא iw/ih כמו בפילטרים אחרים), שמזיז את חלון הקרופ לפי offset (-1..1) בלי לצאת
    מגבולות הפריים. offset=0 שקול בדיוק להתנהגות הקודמת (קרופ מרכזי).
    """
    return f"min(max((in_w-{crop_width})/2+({offset:.3f})*(in_w-{crop_width})/2,0),in_w-{crop_width})"
