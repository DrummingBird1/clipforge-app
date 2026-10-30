# utils/media/clip_tagger.py
#
# תיוג תוכן אוטומטי לקליפים בגלריה (item: content-based auto-tagging) - אותה
# תשתית AI חזותית בדיוק כמו my_scripts/video/story_cutter.py (Gemini עם נפילה
# חזרה ל-Ollama מקומי, utils/media/local_vision_judge.py), אבל מבקש רשימת תגיות
# קצרות ("Goal", "Save", "Funny Moment") לחיפוש/סינון בגלריה - לא החלטת
# כן/לא בינארית של "האם לשמור את הקליפ בכלל" (זה כבר קיים ב-story_cutter.py).
#
# תיוג הוא שיפור-חוויה אופציונלי (על-פי-בקשה, item: gallery thumbnails),
# לא שער-איכות - לכן כשל בכל שלב מחזיר [] (רשימת תגיות ריקה) ולא "ברירת מחדל
# בטוחה", בניגוד ל-judge_clip_locally/ask_gemini_if_interesting.

import base64
import json
import os

import requests
from PIL import Image

from utils.media.local_vision_judge import OLLAMA_URL, is_ollama_available
from utils.shared.secrets_vault import get_secret

MAX_TAGS = 5
DEFAULT_LOCAL_MODEL = "llava:7b"
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"

TAG_PROMPT = """You are tagging a short gaming video clip for search/filtering in a clip library.
Look at these frames and output up to 5 short, specific tags describing what's happening
(e.g. "Goal", "Save", "Explosion", "Victory Screen", "Funny Moment", "Multi-kill", "Crash").
Output MUST be raw JSON only (no markdown fences), in this exact format:
{"tags": ["tag1", "tag2"]}"""


def _parse_tags_response(raw_text):
    """מנקה markdown fences (אם יש) ומחלץ עד MAX_TAGS תגיות non-empty. כל כשל
    (JSON לא תקין, "tags" חסר/לא רשימה) מחזיר [] - לא זורק, לא נופל לברירת מחדל."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        if len(parts) >= 2:
            cleaned = parts[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
    try:
        result = json.loads(cleaned.strip())
    except (ValueError, TypeError):
        return []
    tags = result.get("tags") if isinstance(result, dict) else None
    if not isinstance(tags, list):
        return []
    return [str(tag).strip() for tag in tags if str(tag).strip()][:MAX_TAGS]


def generate_tags_locally(frame_paths, model=DEFAULT_LOCAL_MODEL):
    """Ollama מקומי - אותו דפוס HTTP בדיוק כמו local_vision_judge.judge_clip_locally
    (base64 + /api/generate), prompt שונה (תגיות, לא כן/לא)."""
    images_b64 = []
    for path in frame_paths:
        try:
            with open(path, "rb") as f:
                images_b64.append(base64.b64encode(f.read()).decode("ascii"))
        except OSError:
            continue
    if not images_b64:
        return []
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": TAG_PROMPT, "images": images_b64, "stream": False, "format": "json"},
            timeout=120,
        )
        response.raise_for_status()
        return _parse_tags_response(response.json().get("response", ""))
    except Exception:
        return []


def generate_tags_with_gemini(frame_paths, model=DEFAULT_GEMINI_MODEL):
    gemini_api_key = get_secret("GEMINI_API_KEY")
    if not gemini_api_key:
        return []
    images = []
    for path in frame_paths:
        try:
            images.append(Image.open(path))
        except Exception:
            continue
    if not images:
        return []
    try:
        from google import genai
        client = genai.Client(api_key=gemini_api_key)
        response = client.models.generate_content(model=model, contents=[*images, TAG_PROMPT])
        return _parse_tags_response(response.text)
    except Exception:
        return []


def generate_clip_tags(frame_paths, provider="gemini"):
    """provider="gemini" (ברירת מחדל) מנסה Gemini קודם ונופל ל-Ollama מקומי אם
    זה נכשל/אין מפתח וOllama בכל זאת זמין - זהה לדפוס הנפילה-חזרה ב-
    story_cutter.py's ask_gemini_if_interesting. provider="local" מדלג ישר
    ל-Ollama (לשימוש כשלא רוצים לצרוך מכסת Gemini בכלל)."""
    if provider == "local":
        return generate_tags_locally(frame_paths)
    tags = generate_tags_with_gemini(frame_paths)
    if tags:
        return tags
    if is_ollama_available():
        return generate_tags_locally(frame_paths)
    return []


# --- קריאת מטמון תגיות (item: clip gallery search/filter by tag) - משותף בין
# web_app.py לדסקטופ (ui/stats_tab.py) כדי ששני הצדדים יקראו בדיוק את אותם
# קבצי מטמון, בלי לשכפל את לוגיקת נתיב-המטמון (basename+mtime) פעמיים. -
# לעולם לא קורא ל-AI מכאן, רק מטמון קיים שכבר נכתב על-ידי generate_clip_tags.

def tags_cache_path(clip_path, cache_dir):
    """נתיב קובץ המטמון עבור קליפ נתון - invalidation לפי mtime המקור בשם
    הקובץ עצמו (זהה ל-THUMBNAIL_CACHE_DIR ב-web_app.py)."""
    return os.path.join(cache_dir, f"{os.path.basename(clip_path)}.{int(os.path.getmtime(clip_path))}.json")


def read_cached_tags(clip_path, cache_dir):
    """מחזיר None אם הקליפ עוד לא תויג מעולם (שונה מ-[] - "תויג, בלי תגיות"),
    או [] אם קובץ המטמון פגום/לא ניתן לקריאה."""
    cache_path = tags_cache_path(clip_path, cache_dir)
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f).get("tags", [])
    except (OSError, ValueError):
        return []


def list_all_cached_tags(cache_dir):
    """כל התגיות הייחודיות שנוצרו אי-פעם על-פני כל הקליפים שתויגו, למילוי
    ה-dropdown של סינון-לפי-תגית בגלריה. תיקייה שעוד לא נוצרה (אף קליפ לא
    תויג) מחזירה רשימה ריקה, לא שגיאה."""
    if not os.path.isdir(cache_dir):
        return []
    all_tags = set()
    for name in os.listdir(cache_dir):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(cache_dir, name), "r", encoding="utf-8") as f:
                all_tags.update(json.load(f).get("tags", []))
        except (OSError, ValueError):
            continue
    return sorted(all_tags)
