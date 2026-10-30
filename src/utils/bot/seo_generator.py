# utils/bot/seo_generator.py
#
# גל 32: כותרת, תיאור ותגיות מ-Gemini (utils/title_generator - אותו מפתח ואותה קריאה כמו
# Rocket Shorts) במקום משפט קבוע לפי מילת-מפתח בשם הקובץ. בלי מפתח, כשההגדרה "seo_ai"
# כבויה או בכל כשל - נשארים עם התבנית הקבועה, כך שיצוא לא נכשל בגלל AI.
import json
import os
import re
import shutil
from datetime import datetime

from utils.shared.workspace_dir import WORKSPACE_DIR
from utils.shared import data_paths, ui_language

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# יומן ה-SEO המרכזי - עם שאר הלוגים ב-data/logs/ (עד 19.10.2026 ישב בשורש הפרויקט). הקובץ הישן בשורש לא זז
# ולא נמחק: בכתיבה הראשונה, כשאין עדיין יומן חדש, תוכנו מועתק אליו כדי שההיסטוריה תישאר במקום אחד.
HISTORY_LOG_FILE = data_paths.path(data_paths.SEO_HISTORY_LOG)
LEGACY_HISTORY_LOG_FILE = os.path.join(BASE_DIR, "seo_history_log.txt")
ROCKET_SETTINGS_PATH = data_paths.path(data_paths.ROCKET_SETTINGS)
# ספריית הקליפים הממוינת כשאין כונן גיבוי - תחת WORKSPACE_DIR (CLIPFORGE_WORKSPACE_DIR), לא קבוע ל-<שורש>/workspace
EXPORTS_DIR = os.path.join(WORKSPACE_DIR, "exports")

GAME_TAGS = {
    "Rocket League": "#rocketleague #rl #rocketleagueclips #rlclips #gaming #gamertok",
    "Minecraft": "#minecraft #minecraftclips #minecraftmemes #gamingontiktok #מיינקראפט",
    "FiveM": "#fivem #gtav #gta5 #gtarp #fivemclips #גטא",
    "Gameplay": "#gaming #gamingclips #gamertok #shorts",
}

# קיצורים (rl/mc/gta) רק כמילה בפני עצמה - "rl" בתוך world/girl ו-"mc" בתוך שם אחר זיהו
# בעבר את המשחק הלא נכון. "_" ו-"-" נחשבים מפריד, ספרות מותרות אחרי (gta5).
GAME_PATTERNS = (
    ("Rocket League", re.compile(r"rocket|rlshorts|(?<![a-z])rl(?![a-z])")),
    ("Minecraft", re.compile(r"minecraft|(?<![a-z])mc(?![a-z])")),
    ("FiveM", re.compile(r"fivem|(?<![a-z])gta(?:v|rp)?(?![a-z])")),
)

YOUTUBE_TITLE_MAX = 100
TIKTOK_CAPTION_MAX = 2200
MAX_HASHTAGS = 8


def detect_game_title(text):
    """מזהה שם משחק לפי מילות מפתח - קודם בשם הקובץ, ואז בכל הנתיב (תיקיית "Rocket League")."""
    text = str(text or "")
    for candidate in (os.path.basename(text), text):
        lower = candidate.lower()
        for game, pattern in GAME_PATTERNS:
            if pattern.search(lower):
                return game
    return "Gameplay"


def ai_enabled():
    """"seo_ai" ב-rocket_settings.json - ברירת מחדל פעיל (בלי מפתח Gemini ממילא נופלים לתבנית)."""
    try:
        with open(ROCKET_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return True
    return not isinstance(data, dict) or data.get("seo_ai", True) is not False


def _read_cached_ai_metadata(clip_path):
    """Rocket Shorts (enable_ai_titles) כבר כותב <שם>_ai_metadata.txt ליד הפלט - לא קוראים ל-Gemini פעמיים."""
    path = os.path.splitext(clip_path)[0] + "_ai_metadata.txt"
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    fields = {}
    for line in lines:
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip().lower()] = value.strip()
    if not fields.get("title"):
        return None
    return {"title": fields["title"], "description": fields.get("description", ""), "hashtags": fields.get("hashtags", "").split()}


def _ai_metadata(clip_path, game_title):
    """{"title", "description", "hashtags"} מ-Gemini (או מהקובץ ש-Rocket Shorts כבר כתב), או None."""
    cached = _read_cached_ai_metadata(clip_path)
    if cached:
        return cached
    if not ai_enabled():
        return None
    try:
        from utils.bot.title_generator import generate_metadata
        meta = generate_metadata(clip_path, game_title if game_title != "Gameplay" else "gaming")
    except Exception as e:  # בלי מפתח/בלי רשת/תגובה לא תקינה - התבנית מספיקה
        print(f"[seo_generator] Gemini לא זמין, משתמש בתבנית: {e}")
        return None
    return meta if isinstance(meta, dict) and str(meta.get("title") or "").strip() else None


def _clean_hashtags(tags, game_title):
    """התגיות של Gemini ואחריהן של המשחק - עם #, בלי רווחים/סימנים, בלי כפילויות, עד MAX_HASHTAGS."""
    result, seen = [], set()
    for tag in [*(tags if isinstance(tags, list) else []), *GAME_TAGS[game_title].split()]:
        word = re.sub(r"[^\w]", "", str(tag).lstrip("#"))
        if word and word.lower() not in seen:
            seen.add(word.lower())
            result.append("#" + word)
    return result[:MAX_HASHTAGS]


def generate_seo(clip_path):
    """כותרת/תיאור/תגיות לקליפ, לכל פלטפורמה: dict עם source ("ai"/"template")."""
    game_title = detect_game_title(clip_path)
    meta = _ai_metadata(clip_path, game_title)
    if meta:
        title = " ".join(str(meta["title"]).split())
        description = " ".join(str(meta.get("description") or "").split())
        hashtags = _clean_hashtags(meta.get("hashtags"), game_title)
    else:
        # 30.10.2026: הכותרת בלי AI בשפת ההתקנה (utils/shared/ui_language.py)
        title = f"My craziest {game_title} clip! 🔥" if ui_language.current() == "en" else f"הקליפ הכי מטורף שלי ב-{game_title}! 🔥"
        description = ""
        hashtags = GAME_TAGS[game_title].split()
    return {
        "source": "ai" if meta else "template",
        "game": game_title,
        "title": title,
        "description": description,
        "hashtags": hashtags,
        "youtube_title": title[:YOUTUBE_TITLE_MAX],
        "youtube_tags": [tag.lstrip("#") for tag in hashtags],
        "tiktok_caption": f"{title} {' '.join(hashtags)}"[:TIKTOK_CAPTION_MAX],
    }


def _seo_sheet(base_name, seo):
    source = "🤖 Gemini" if seo["source"] == "ai" else "📝 תבנית (אין Gemini)"
    description = f"{seo['description']}\n" if seo["description"] else ""
    return (
        f"==================================================\n"
        f"🚀 SEO SHEET - {base_name} ({datetime.now().strftime('%Y-%m-%d %H:%M')}) - {source}\n"
        f"==================================================\n\n"
        f"📱 [TIKTOK CAPTION]:\n{seo['tiktok_caption']}\n\n"
        f"▶️ [YOUTUBE TITLE]:\n{seo['youtube_title']}\n\n"
        f"📝 [YOUTUBE DESCRIPTION]:\n{description}{' '.join(seo['hashtags'])}\n\n"
    )


def generate_seo_with_sheet(clip_path):
    """generate_seo + כתיבת <שם>_metadata_seo.txt ליד הקליפ ושורה ביומן ההיסטוריה המרכזי."""
    base_name = os.path.basename(clip_path)
    meta_file_path = os.path.join(os.path.dirname(clip_path), os.path.splitext(base_name)[0] + "_metadata_seo.txt")
    seo = generate_seo(clip_path)
    sheet = _seo_sheet(base_name, seo)
    with open(meta_file_path, "w", encoding="utf-8") as f:
        f.write(sheet)
    _append_history(sheet + "\n\n")
    return {**seo, "sheet": sheet}


def _append_history(text):
    """שורה ביומן ההיסטוריה. יומן חדש שעוד לא קיים מתחיל מעותק של הישן מהשורש (אם יש) - הישן לא משתנה."""
    os.makedirs(os.path.dirname(os.path.abspath(HISTORY_LOG_FILE)), exist_ok=True)
    if not os.path.exists(HISTORY_LOG_FILE) and os.path.isfile(LEGACY_HISTORY_LOG_FILE):
        shutil.copyfile(LEGACY_HISTORY_LOG_FILE, HISTORY_LOG_FILE)
    with open(HISTORY_LOG_FILE, "a", encoding="utf-8") as hist_f:
        hist_f.write(text)


def generate_seo_metadata(clip_path):
    """מחולל קובץ טקסט עם כותרות ותגיות SEO, ושומר עותק בלוג ההיסטוריה המרכזי - מחזיר את הטקסט"""
    try:
        return generate_seo_with_sheet(clip_path)["sheet"]
    except Exception as e:
        return f"Failed to generate SEO metadata: {e}"

def sort_clip_to_smart_library(clip_path, base_backup_dir=None):
    """ממיין קליפים ומאחד את כלל תיקיות המדיה תחת תיקיית 'exports' אחת מרכזית"""
    try:
        game_title = detect_game_title(clip_path)
        game_folder = "Other_Gameplay" if game_title == "Gameplay" else game_title.replace(" ", "_")

        month_str = datetime.now().strftime("%Y-%m")
        
        # אם המשתמש הגדיר כונן חיצוני - נשמור שם, אחרת נייצר תיקיית exports מקומית בפרויקט
        if base_backup_dir and os.path.exists(base_backup_dir):
            root_output = base_backup_dir
        else:
            root_output = EXPORTS_DIR
            
        target_folder = os.path.join(root_output, game_folder, month_str)
        os.makedirs(target_folder, exist_ok=True)
        
        target_path = os.path.join(target_folder, os.path.basename(clip_path))
        shutil.copy2(clip_path, target_path)
        return target_path
    except Exception as e:
        print(f"[seo_generator] שגיאה במיון קליפ לספרייה: {e}")
        return clip_path

def get_encoder_args(encoder_type):
    # substring, לא match מדויק - ה-dropdown בפועל משתמש ב"AV1 (NVIDIA RTX Next-Gen)"
    # ו"HEVC (H.265 Ultra)", לא בטקסט המקוצר; match מדויק/צר מדי לא היה תופס אותם
    # אף פעם ותמיד היה נופל בשקט לברירת המחדל של libx264 (קידוד תוכנה במקום חומרה).
    if "AV1" in encoder_type: return ["-c:v", "av1_nvenc", "-preset", "p4", "-b:v", "12M"]
    elif "HEVC" in encoder_type: return ["-c:v", "hevc_nvenc", "-preset", "fast", "-b:v", "15M"]
    return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "22"]

def get_confetti_particles():
    return ["✨", "🎉", "🔥", "👑", "🚀", "⭐", "💥"]