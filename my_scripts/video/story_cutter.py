# Name: ✂️ צייד הקליפים האוטומטי
# Name (EN): ✂️ Auto Clip Hunter
# Description: מזהה אוטומטית סרטוני גיימפליי ארוכים, מסנן את הקליפים בעזרת AI וממיין אותם אוטומטית לתיקיות לפי שם המשחק שזוהה. אפשר גם --use-ocr לזיהוי נוסף לפי טקסט-על-מסך.
# Description (EN): Automatically detects long gameplay recordings, filters clips using AI, and sorts them into folders by detected game name. Optional --use-ocr adds on-screen-text based detection.
# Safety: modifies

import os
import glob
import shutil
import subprocess
import sys
import time
import json
import argparse

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure") and sys.stderr.encoding != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import cv2
from PIL import Image
from pydub import AudioSegment
from pydub.utils import make_chunks
from dotenv import load_dotenv

# ====================================================================
# 🔑 הגדרות API ו-AI (Windows Credential Manager קודם, .env כגיבוי)
# ====================================================================
_BASE_DIR_FOR_SECRETS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SRC_DIR_FOR_SECRETS = os.path.join(_BASE_DIR_FOR_SECRETS, "src")
if _SRC_DIR_FOR_SECRETS not in sys.path:
    sys.path.insert(0, _SRC_DIR_FOR_SECRETS)

load_dotenv(os.path.join(_BASE_DIR_FOR_SECRETS, ".env"))
from utils.shared.workspace_dir import WORKSPACE_DIR  # CLIPFORGE_WORKSPACE_DIR (טסטים, שרת בדיקה) - ברירת המחדל workspace/ כמו קודם
from utils.shared.secrets_vault import get_secret
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.media.tesseract_locator import get_tesseract_exe, is_tesseract_available
from utils.media.ocr_highlights import find_ocr_highlight_timestamps, merge_peaks_with_gap
from utils.media.local_vision_judge import judge_clip_locally, is_ollama_available, DEFAULT_LOCAL_MODEL
from utils.shared.retry import compute_backoff_delay
from utils.media.gemini_quota import QuotaWatch
GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
# היה משתמש קודם ב-"ffmpeg"/"ffprobe" גלובליים בלבד (בניגוד לכל שאר my_scripts) -
# מה שהפיל אותו ספציפית כשרק העותק המצורף בפרויקט קיים ואין ffmpeg מותקן ב-PATH
FFMPEG_EXE = get_ffmpeg_exe()
FFPROBE_EXE = get_ffprobe_exe()
# ====================================================================

# קריאת פרמטרים דינמיים מה-GUI (תומך לחלוטין ב-gui_manager המשודרג)
parser = argparse.ArgumentParser()
parser.add_argument("--input_dir", type=str, default="")
parser.add_argument("--before", type=int, default=20)
parser.add_argument("--after", type=int, default=5)
parser.add_argument("--model", type=str, default="gemini-flash-latest")
parser.add_argument("--threshold", type=int, default=18)
parser.add_argument("--use-ocr", action="store_true",
                     help="מפעיל זיהוי נוסף מבוסס OCR (טקסט על המסך כמו Victory/Eliminated) לצד זיהוי שיאי שמע - "
                          "שימושי כשאין קומנטרי/דיבור בסרטון ורגעי שיא עלולים להיות שקטים אקוסטית. דורש התקנת Tesseract-OCR.")
parser.add_argument("--ocr-keywords", type=str, default="",
                     help="מילות מפתח נוספות ל-OCR, מופרדות בפסיק, שמצטרפות לרשימה הגנרית (victory/kill/headshot וכו') - "
                          "לשימוש במשחקים בלי HUD של קילפיד, כמו משחקי סיפור מבוססי דיאלוג/כתוביות "
                          "(למשל: 'wheatley,glados,explosion,alarm').")
parser.add_argument("--local-fallback-model", type=str, default=DEFAULT_LOCAL_MODEL,
                     help="מודל Ollama מקומי שמשמש כ-fallback חינמי כש-Gemini נכשל/נגמרה המכסה, במקום לאשר קליפים "
                          "אוטומטית בלי שיפוט אמיתי. דורש Ollama רץ מקומית עם המודל הזה מורד (ollama pull <model>).")
parser.add_argument("--ai-provider", type=str, default="gemini", choices=["gemini", "local"],
                     help="'gemini' (ברירת מחדל): שופט דרך Gemini, עם נפילה ל-Ollama המקומי כש-Gemini נכשל/נגמרה "
                          "המכסה. 'local': מדלג על Gemini לגמרי ושופט כל קליפ ישירות דרך Ollama - אפס קריאות ל-API.")
parser.add_argument("--gemini-daily-limit", type=int, default=0,
                    help="תקרת בקשות Gemini ליום שאתה מכיר (0 = לא ידוע). ב-80 אחוז ממנה יודפס [WARNING] מוקדם, במקום לגלות "
                         "שהמכסה נגמרה רק כשקליפים כבר מאושרים אוטומטית בלי שיפוט.")
args = parser.parse_args()

# החלת הגדרות
INPUT_DIR = args.input_dir
CLIP_DURATION_BEFORE = args.before
CLIP_DURATION_AFTER = args.after
MIN_GAP_BETWEEN_CLIPS = 60
SELECTED_AI_MODEL = args.model
DYNAMIC_THRESHOLD_OFFSET = args.threshold
USE_OCR = args.use_ocr
EXTRA_OCR_KEYWORDS = [k.strip().lower() for k in args.ocr_keywords.split(",") if k.strip()]
LOCAL_FALLBACK_MODEL = args.local_fallback_model
AI_PROVIDER = args.ai_provider

if USE_OCR and not is_tesseract_available():
    print("[ERROR] --use-ocr הופעל אבל Tesseract-OCR לא נמצא. התקן מ-https://github.com/UB-Mannheim/tesseract/wiki ונסה שוב.")
    sys.stdout.flush()
    exit()

LOCAL_JUDGE_AVAILABLE = False
if SELECTED_AI_MODEL != "ללא AI (חיתוך סאונד בלבד)":
    if AI_PROVIDER == "local":
        if is_ollama_available():
            print(f"[INFO] מצב מקומי (--ai-provider local): כל קליפ יישפט ישירות דרך Ollama ('{LOCAL_FALLBACK_MODEL}'), בלי לפנות ל-Gemini בכלל.")
        else:
            print(f"[ERROR] --ai-provider local נבחר אבל Ollama לא נמצא. הפעל את Ollama עם המודל '{LOCAL_FALLBACK_MODEL}' מורד, או עבור למצב gemini.")
            sys.stdout.flush()
            exit()
    elif is_ollama_available():
        LOCAL_JUDGE_AVAILABLE = True
        print(f"[INFO] נמצא Ollama מקומי - כשמכסת Gemini תיגמר, קליפים ישפטו אמיתית דרך '{LOCAL_FALLBACK_MODEL}' במקום להתאשר אוטומטית.")
    else:
        print("[WARNING] Ollama לא נמצא - קליפים שנכשלים ב-Gemini יתאשרו אוטומטית בלי שיפוט (כמו קודם).")
    sys.stdout.flush()

QUOTA_WATCH = QuotaWatch(daily_limit=args.gemini_daily_limit, local_judge_available=LOCAL_JUDGE_AVAILABLE or AI_PROVIDER == "local")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# workspace/ מרכז את כל תיקיות העבודה/פלט (clips, Processed_Gameplay, imports,
# exports וכו') תחת תיקייה אחת, במקום מפוזרות בשורש הפרויקט לצד קוד המקור.
OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "clips")
PROCESSED_DIR = os.path.join(WORKSPACE_DIR, "Processed_Gameplay")
TEMP_DIR = os.path.join(BASE_DIR, "temp_analysis")
TEMP_AUDIO = os.path.join(TEMP_DIR, "temp_audio_analysis.wav")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# אתחול ה-AI רק אם נבחר מודל לסינון
ai_client = None
if SELECTED_AI_MODEL != "ללא AI (חיתוך סאונד בלבד)":
    from google import genai
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
        print("[ERROR] נא להגדיר מפתח Gemini API תקין!")
        sys.stdout.flush()
        exit()
    # אתחול נקי ללא v1 מגביל שגורם לשגיאות 404 בדגמים חדשים
    ai_client = genai.Client(api_key=GEMINI_API_KEY)

if not INPUT_DIR:
    # פעם ניסה לפתוח דיאלוג בחירת תיקייה אינטראקטיבי כ"נפילה חזרה" - אבל הסקריפט
    # הזה תמיד רץ כתת-תהליך ללא ראש מה-GUI (worker.py), אז דיאלוג כזה היה נתקע
    # לנצח מחכה ללחיצה שאף אחד לא יכול לתת לו. עדיף כישלון מיידי וברור.
    print("[ERROR] לא נבחרה תיקייה. ביטול פעולה.")
    sys.stdout.flush()
    exit()

# סריקה של קבצי הוידאו
video_extensions = ("*.mp4", "*.mkv", "*.mov", "*.avi")
raw_videos = []
for ext in video_extensions:
    raw_videos.extend(glob.glob(os.path.join(INPUT_DIR, ext)))

video_files = [
    v for v in raw_videos 
    if os.path.basename(v) != "overlay.png" 
    and "temp_" not in os.path.basename(v)
    and not os.path.basename(v).startswith("YT_")
    and not os.path.basename(v).startswith("TT_")
]

if not video_files:
    print(f"[ERROR] לא נמצאו סרטוני גיימפליי חדשים בתיקייה: {INPUT_DIR}")
    sys.stdout.flush()
    exit()

print(f"[INFO] נמצאו {len(video_files)} סרטונים חדשים לעיבוד בתיקיית המקור.")
sys.stdout.flush()

# פונקציה לחילוץ תמונות מפתח (Keyframes) לצורך ניתוח AI
def extract_keyframes(video_path, num_frames=3):
    frames = []
    duration_cmd = [FFPROBE_EXE, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    try:
        duration = float(subprocess.run(duration_cmd, stdout=subprocess.PIPE, text=True, creationflags=NO_WINDOW_FLAGS).stdout.strip())
    except:
        return frames

    for i in range(num_frames):
        time_pos = duration * (0.2 + (i * 0.3))
        frame_path = os.path.join(TEMP_DIR, f"frame_{i}.jpg")
        
        cmd = [
            FFMPEG_EXE, "-y", "-ss", str(time_pos), "-i", video_path,
            "-vframes", "1", "-q:v", "2", "-vf", "scale=854:480", frame_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW_FLAGS)
        
        if os.path.exists(frame_path):
            frames.append(frame_path)
    return frames

# סף מתחת אליו נקודת שיא נחשבת "ללא תזוזה חזותית" ונשמטת לפני שליחה ל-Gemini (חוסך
# קריאות API על נקודות שכנראה נבעו רק מרעש/דיבור ולא מרגע משחק אמיתי)
VISUAL_ACTIVATION_MIN_SCORE = 4.0

def compute_visual_activation(video_path, peak_time, window_seconds=3, num_samples=4):
    """
    בודק כמה 'תזוזה חזותית' יש בחלון קצר סביב נקודת שיא השמע (הפרש פריימים ב-OpenCV).
    רגע משחק אמיתי (גול, פיצוץ, מסך ניצחון) כמעט תמיד מלווה בשינוי חזותי משמעותי -
    נקודת שיא שמע בלי שום שינוי ויזואלי היא כנראה false positive (למשל צעקה/מוזיקה).
    מחזיר ציון (0 ומעלה, ככל שגדול יותר - יותר תזוזה). בכשל כלשהו מחזיר ציון גבוה
    כדי לא לפסול קליפ בטעות בגלל בעיה טכנית בניתוח.
    """
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return 999.0

        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        start_time = max(0, peak_time - window_seconds / 2)

        prev_gray = None
        scores = []
        for i in range(num_samples):
            t = start_time + (i * window_seconds / num_samples)
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ok, frame = cap.read()
            if not ok:
                continue
            small = cv2.resize(frame, (160, 90))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                scores.append(cv2.absdiff(gray, prev_gray).mean())
            prev_gray = gray

        cap.release()
        return max(scores) if scores else 999.0
    except Exception:
        return 999.0

# פונקציה שמנסה לזהות את המשחק לפי שם קובץ המקור כגיבוי
# 30.10.2026: אותו זיהוי כמו seo_generator (מילים שלמות) - קודם "rl"/"mc" כתת-מחרוזת הפכו כל "world" ו-"girl" ל-Rocket League
def detect_game_from_filename(filename):
    from utils.bot.seo_generator import detect_game_title
    game = detect_game_title(filename)
    return "General Gameplay" if game == "Gameplay" else game

def _emit_quota(message):
    """אזהרות המכסה (utils/gemini_quota) - מודפסות מיד וסומנות כך שיבלטו בפלט הארוך של הריצה."""
    if message:
        print(message)
        sys.stdout.flush()


# פונקציה השולחת את תמונות המפתח ל-Gemini ומקבלת החלטה וזיהוי משחק
def ask_gemini_if_interesting(frame_paths, fallback_game="General Gameplay"):
    if SELECTED_AI_MODEL == "ללא AI (חיתוך סאונד בלבד)":
        return True, fallback_game, "חיתוך סאונד בלבד (AI כבוי)"

    if AI_PROVIDER == "local":
        return judge_clip_locally(frame_paths, fallback_game, model=LOCAL_FALLBACK_MODEL)

    images = []
    for path in frame_paths:
        try:
            images.append(Image.open(path))
        except Exception as e:
            print(f"[WARNING] שגיאה בטעינת תמונה {path}: {e}")
            
    if not images:
        return False, fallback_game, "לא חולצו תמונות לניתוח"

    prompt = f"""
    You are an expert gaming video editor. Review these 3 frames extracted from a candidate video clip.
    1. Identify which video game is being played (e.g., 'Rocket League', 'Minecraft', 'GTA V', 'Counter-Strike', etc.). Be precise. If unsure, output '{fallback_game}'.
    2. Analyze if these frames represent an active, exciting, or meaningful gameplay moment (e.g. combat, building, action, dynamic gameplay, menus showing stats/victory).
    Reject clips that are just loading screens, black screens, static main menus, or long moments of empty/passive walking with zero action.

    Output MUST be in raw JSON format only (do NOT wrap it in ```json or markdown blocks).
    Use this exact format:
    {{
      "game_name": "Name of the Game",
      "interesting": true,
      "reason": "A brief explanation in English or Hebrew"
    }}
    """

    models_to_try = [SELECTED_AI_MODEL]
    if SELECTED_AI_MODEL != "gemini-flash-latest":
        models_to_try.append("gemini-flash-latest")

    for model_name in models_to_try:
        for attempt in range(3):
            if QUOTA_WATCH.should_skip_gemini():
                break          # מפסק מכסה: לא קוראים ל-Gemini (ולא מחכים backoff) - ישר לשיפוט המקומי
            _emit_quota(QUOTA_WATCH.gemini_called())
            try:
                response = ai_client.models.generate_content(
                    model=model_name,
                    contents=[*images, prompt]
                )

                QUOTA_WATCH.gemini_succeeded()
                clean_text = response.text.strip()
                if clean_text.startswith("```"):
                    clean_text = clean_text.split("```")[1]
                    if clean_text.startswith("json"):
                        clean_text = clean_text[4:]
                clean_text = clean_text.strip()

                result = json.loads(clean_text)
                detected_game = result.get("game_name", fallback_game).strip()
                # הגנה מפני תווים לא חוקיים בתיקיות מערכת ההפעלה
                for char in ['/', '\\', '?', '%', '*', ':', '|', '"', '<', '>']:
                    detected_game = detected_game.replace(char, '')

                return result.get("interesting", False), detected_game, f"({model_name}) {result.get('reason', 'No reason provided')}"

            except Exception as e:
                _emit_quota(QUOTA_WATCH.gemini_failed(e))
                if QUOTA_WATCH.tripped:
                    print("[WARNING] Gemini נכשל שוב ושוב על מכסה - מדלגים עליו זמנית ועוברים לשיפוט המקומי.")
                    sys.stdout.flush()
                    break
                if ("503" in str(e) or "429" in str(e)) and attempt < 2:
                    # exponential backoff (2s/4s) במקום המתנה קבועה - עומס API
                    # אמיתי (429) לרוב דורש יותר מ-1.5 שנייה קבועה כדי לחלוף.
                    delay = compute_backoff_delay(attempt, base_delay=2.0, factor=2.0, max_delay=15.0)
                    print(f"[WARNING] עומס זמני ב-API על המודל {model_name}. ממתין {delay:.0f} שניות ומנסה שוב...")
                    sys.stdout.flush()
                    time.sleep(delay)
                    continue
                print(f"[WARNING] המודל {model_name} נכשל או עמוס: {e}")
                sys.stdout.flush()
                break

    # Gemini נכשל/נגמרה המכסה (יומית, לא רק לדקה) - fallback לשיפוט מקומי חינמי
    # דרך Ollama במקום לאשר הכל אוטומטית בלי שום בדיקה אמיתית
    print(f"[INFO] Gemini לא זמין - עובר לשיפוט מקומי דרך Ollama ({LOCAL_FALLBACK_MODEL})...")
    sys.stdout.flush()
    return judge_clip_locally(frame_paths, fallback_game, model=LOCAL_FALLBACK_MODEL)

# --- סבב עיבוד סרטונים ---
for video_path in video_files:
    filename = os.path.basename(video_path)
    fallback_game_name = detect_game_from_filename(filename)
    
    print("=" * 60)
    print(f"[PROCESS] מתחיל לעבד את הסרטון: {filename}")
    print("=" * 60)
    sys.stdout.flush()
    
    # 1. חילוץ אודיו מהיר
    print("[INFO] 1. מחלץ אודיו לצורך ניתוח דינמי...")
    sys.stdout.flush()
    extract_cmd = [FFMPEG_EXE, "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", TEMP_AUDIO]
    result = subprocess.run(extract_cmd, capture_output=True, text=True, creationflags=NO_WINDOW_FLAGS)

    if result.returncode != 0:
        print(f"[ERROR] חילוץ האודיו עבור {filename} נכשל! מדלג...")
        sys.stdout.flush()
        continue

    # 2. ניתוח נקודות רעש
    print("[INFO] 2. מנתח את עוצמת השמע ומחפש נקודות שיא (Peaks)...")
    sys.stdout.flush()
    audio = AudioSegment.from_wav(TEMP_AUDIO)
    chunks = make_chunks(audio, 100)

    avg_db = audio.dBFS
    dynamic_threshold = avg_db + DYNAMIC_THRESHOLD_OFFSET
    sys.stdout.flush()

    peaks_in_seconds = []
    last_peak_time = -MIN_GAP_BETWEEN_CLIPS

    for i, chunk in enumerate(chunks):
        time_in_seconds = (i * 100) / 1000.0
        if chunk.max_dBFS > dynamic_threshold:
            if time_in_seconds - last_peak_time >= MIN_GAP_BETWEEN_CLIPS:
                peaks_in_seconds.append((time_in_seconds, "audio"))
                last_peak_time = time_in_seconds

    if os.path.exists(TEMP_AUDIO):
        os.remove(TEMP_AUDIO)

    print(f"   נמצאו {len(peaks_in_seconds)} נקודות עניין פוטנציאליות (לפי שמע).")
    sys.stdout.flush()

    # קבלת אורך הוידאו - מחושב לפני בדיקת "אין נקודות עניין" כי OCR (אם מופעל)
    # סורק את הסרטון כולו בלי תלות בשיאי שמע, ועלול למצוא נקודות גם כשהשמע ריק
    video_duration_cmd = [FFPROBE_EXE, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    video_duration = float(subprocess.run(video_duration_cmd, stdout=subprocess.PIPE, text=True, creationflags=NO_WINDOW_FLAGS).stdout.strip())

    if USE_OCR:
        print("[INFO] מריץ זיהוי OCR נוסף על פני כל הסרטון (מילות מפתח כמו Victory/Kill/Eliminated)...")
        sys.stdout.flush()
        ocr_hits = find_ocr_highlight_timestamps(video_path, video_duration, tesseract_cmd=get_tesseract_exe(), extra_keywords=EXTRA_OCR_KEYWORDS)
        before_count = len(peaks_in_seconds)
        peaks_in_seconds = merge_peaks_with_gap(peaks_in_seconds, ocr_hits, MIN_GAP_BETWEEN_CLIPS)
        added = len(peaks_in_seconds) - before_count
        print(f"   OCR מצא {len(ocr_hits)} התאמות טקסט, {added} מהן נוספו כנקודות עניין חדשות (לא חופפות לשיאי שמע קיימים).")
        sys.stdout.flush()

    if not peaks_in_seconds:
        print("[WARNING] לא נמצאו נקודות שיא חריגות בסרטון זה. מעביר לארכיון...")
        shutil.move(video_path, os.path.join(PROCESSED_DIR, filename))
        sys.stdout.flush()
        continue

    # 3. יצירת קליפים וסינון באמצעות Gemini AI
    print("\n[INFO] 3. מתחיל חיתוך זמני וסינון בעזרת בינה מלאכותית...")
    sys.stdout.flush()
    base_name = os.path.splitext(filename)[0]

    for idx, (peak_time, source) in enumerate(peaks_in_seconds, start=1):
        if source == "audio":
            # בדיקת תזוזה חזותית סביב נקודת השיא - חוסך קריאת Gemini על נקודות
            # שכנראה false positive (שיא שמע בלי שום שינוי בתמונה)
            visual_score = compute_visual_activation(video_path, peak_time)
            if visual_score < VISUAL_ACTIVATION_MIN_SCORE:
                print(f"   [SKIP-VISUAL] נקודה {idx} נשמטה - אין תזוזה חזותית משמעותית (ציון {visual_score:.1f})")
                sys.stdout.flush()
                continue
        else:
            print(f"   [OCR-MATCH] נקודה {idx} אושרה ישירות לפי טקסט שזוהה על המסך ({source}) - מדלג על סינון תזוזה חזותית.")
            sys.stdout.flush()

        start_time = max(0, peak_time - CLIP_DURATION_BEFORE)
        end_time = min(video_duration, peak_time + CLIP_DURATION_AFTER)
        duration = end_time - start_time

        # שלב א': יצירת קליפ זמני
        temp_output_filename = os.path.join(TEMP_DIR, f"temp_clip_{idx}.mp4")
        frames = []
        try:
            cut_cmd = [
                FFMPEG_EXE, "-y", "-ss", str(start_time), "-i", video_path,
                "-t", str(duration), "-c:v", "copy", "-c:a", "copy", temp_output_filename
            ]
            subprocess.run(cut_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW_FLAGS)

            # שלב ב': חילוץ תמונות מפתח
            frames = extract_keyframes(temp_output_filename, num_frames=3)

            # שלב ג': שליחה ל-Gemini להחלטה ולזיהוי משחק
            is_interesting, game_name, reason = ask_gemini_if_interesting(frames, fallback_game_name)
            _emit_quota(QUOTA_WATCH.verdict(reason))

            # שלב ד': שמירה סופית בתיקייה ייעודית למשחק או מחיקה
            if is_interesting:
                # יצירת תיקייה ייחודית למשחק בתוך תיקיית ה-clips
                game_folder_path = os.path.join(OUTPUT_DIR, game_name)
                os.makedirs(game_folder_path, exist_ok=True)

                final_output_filename = os.path.join(game_folder_path, f"{base_name}_clip_{idx}.mp4")
                shutil.move(temp_output_filename, final_output_filename)
                print(f"   [APPROVED] Saved to '{game_name}': {os.path.basename(final_output_filename)} - {reason}")
            else:
                print(f"   [REJECTED] קליפ פוטנציאלי {idx} נפסל על ידי ה-AI - {reason}")
        except Exception as e:
            print(f"   [ERROR] כשל בעיבוד קליפ פוטנציאלי {idx}: {e}")
        finally:
            # ניקוי פריימים זמניים וקליפ זמני - מובטח גם אם קרתה חריגה למעלה
            for f in frames:
                try: os.remove(f)
                except Exception: pass
            if os.path.exists(temp_output_filename):
                try: os.remove(temp_output_filename)
                except Exception: pass

        sys.stdout.flush()

    # העברת סרטון המקור לארכיון
    print(f"\n[INFO] מעביר את סרטון המקור לתיקיית הארכיון: '{PROCESSED_DIR}'...")
    shutil.move(video_path, os.path.join(PROCESSED_DIR, filename))
    sys.stdout.flush()

# ניקוי תיקיית temp
if os.path.exists(TEMP_DIR):
    # ב-Windows סורק קבצים/אינדקס יכול להחזיק קובץ זמני לרגע (WinError 32) - מנסים שוב, ואם נכשל זו רק תיקייה זמנית: לא מפילים ריצה שהסתיימה
    for _cleanup_try in range(4):
        try:
            shutil.rmtree(TEMP_DIR)
            break
        except OSError as cleanup_error:
            if _cleanup_try == 3:
                print(f"[WARNING] לא ניתן למחוק את תיקיית הניתוח הזמנית ({cleanup_error}) - אפשר למחוק אותה ידנית.")
            else:
                time.sleep(0.5)

_emit_quota(QUOTA_WATCH.summary())
print("\n==================================================")
print("[SUCCESS] עיבוד וסינון כל הסרטונים הסתיים בהצלחה!")
print("==================================================")
sys.stdout.flush()