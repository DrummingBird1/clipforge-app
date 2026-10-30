# utils/bot/title_generator.py
#
# מייצר כותרת ותיאור משתנים לקליפ באמצעות Gemini, במקום "<קידומת> #N" חוזר.
# משתמש באותו מפתח/דפוס קריאה כמו my_scripts/story_cutter.py (google-genai, ללא v1).

import json
import os
import shutil
import subprocess
import tempfile

from dotenv import load_dotenv

from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
load_dotenv(os.path.join(BASE_DIR, ".env"))
from utils.shared.secrets_vault import get_secret
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
GEMINI_API_KEY = get_secret("GEMINI_API_KEY")

MODEL_NAME = "gemini-flash-latest"

PROMPT = """
You are a viral short-form gaming content editor. Look at these frames from a {game} gameplay clip
that's about to be posted as a YouTube Short / TikTok.

Write ONE punchy, curiosity-driving title (max 60 characters, can include emoji) and a short
one-line description with 3-5 relevant hashtags.

Output MUST be raw JSON only (no markdown fences), in this exact format:
{{
  "title": "short punchy title",
  "description": "one short line",
  "hashtags": ["#tag1", "#tag2", "#tag3"]
}}
"""

def _extract_frames(video_path, count=3):
    ffprobe_exe = get_ffprobe_exe()
    ffmpeg_exe = get_ffmpeg_exe()

    try:
        duration = float(subprocess.run(
            [ffprobe_exe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_path],
            stdout=subprocess.PIPE, text=True, timeout=15, creationflags=NO_WINDOW_FLAGS
        ).stdout.strip())
    except Exception:
        duration = 10.0

    frames = []
    tmp_dir = tempfile.mkdtemp()
    for i in range(count):
        ts = max(0.1, duration * (0.2 + i * 0.3))
        frame_path = os.path.join(tmp_dir, f"frame_{i}.jpg")
        subprocess.run(
            [ffmpeg_exe, "-y", "-ss", str(ts), "-i", video_path, "-vframes", "1", "-q:v", "3", frame_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, creationflags=NO_WINDOW_FLAGS
        )
        if os.path.exists(frame_path):
            frames.append(frame_path)
    return frames


def generate_metadata(video_path, game_name="gaming"):
    """
    מחזיר dict {"title", "description", "hashtags"} שנוצר ע"י Gemini לשימוש כתוכן
    ההעלאה בפועל (כותרת בפלטפורמה) - לא כשם הקובץ המקומי. שם הקובץ המקומי נשאר
    "<קידומת> #N" כי מערכת המונה בנויה סביב מספור יציב, לא סביב כותרות משתנות.
    זורק חריגה אם נכשל - הקורא אמור להתייחס לזה כתכונה אופציונלית שלא עוצרת פייפליין.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY לא מוגדר ב-.env")

    from google import genai
    from PIL import Image

    frame_paths = _extract_frames(video_path)
    if not frame_paths:
        raise RuntimeError("לא ניתן היה לחלץ פריימים מהסרטון לצורך יצירת כותרת")

    tmp_dir = os.path.dirname(frame_paths[0])
    try:
        # .copy() טוען את התמונה במלואה לזיכרון כך שאפשר למחוק את תיקיית הזמני
        # מיד אחרי - בלי זה היא הייתה נשארת בדיסק לצמיתות בכל קריאה (דליפת קבצים זמניים)
        images = [Image.open(p).copy() for p in frame_paths]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    prompt = PROMPT.format(game=game_name)

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model=MODEL_NAME, contents=[*images, prompt])
    return parse_gemini_json_response(response.text)


def parse_gemini_json_response(text):
    """מנקה code fences (```json ... ``` או ``` ... ```) מתגובת Gemini גולמית
    ומפרסר כ-JSON. מוחזר כ-dict עם 'title'/'description'/'hashtags' (ברירות
    מחדל ריקות לשדות חסרים) - חולץ מ-generate_metadata כדי שאפשר יהיה לבדוק
    את לוגיקת הפירסור בבידוד, בלי לקרוא בפועל ל-Gemini."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    data = json.loads(text)
    return {
        "title": data.get("title", "").strip(),
        "description": data.get("description", "").strip(),
        "hashtags": data.get("hashtags", []),
    }
