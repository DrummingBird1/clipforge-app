# utils/media/local_vision_judge.py
#
# Fallback חינמי ומקומי ל-ask_gemini_if_interesting ב-story_cutter.py. כשמכסת
# Gemini נגמרת (מכסה יומית, לא רק לדקה - ראה tests/bot/test_local_vision_judge.py
# להסבר) הקוד היה מאשר כל קליפ אוטומטית בלי שום שיפוט אמיתי. זה משתמש ב-Ollama
# (כבר מותקן מקומית, http://localhost:11434) כדי לשפוט באמת בלי לשלם ובלי
# מכסה - נמנע מלהוסיף תלות פייתון כבדה חדשה (torch/transformers) כי Ollama כבר
# מריץ את המודל בעצמו; כאן רק שולחים בקשת HTTP.

import base64
import json

import requests

OLLAMA_URL = "http://localhost:11434"
DEFAULT_LOCAL_MODEL = "llava:7b"

JUDGE_PROMPT_TEMPLATE = """You are an expert gaming video editor. Review these frames extracted from a candidate video clip.
1. Identify which video game is being played. Be precise. If unsure, output '{fallback_game}'.
2. Analyze if these frames represent an active, exciting, or meaningful gameplay moment (combat, puzzle-solving, building, dynamic action, or a notable story/dialogue moment).
Reject clips that are just loading screens, static menus, or long passive walking with zero action/dialogue.

Output MUST be raw JSON only (no markdown fences), in this exact format:
{{"game_name": "Name of the Game", "interesting": true, "reason": "brief explanation"}}"""


def is_ollama_available():
    try:
        requests.get(f"{OLLAMA_URL}/api/version", timeout=2)
        return True
    except requests.RequestException:
        return False


def _sanitize_game_name(name):
    for char in ['/', '\\', '?', '%', '*', ':', '|', '"', '<', '>']:
        name = name.replace(char, '')
    return name.strip()


def _parse_judge_response(raw_text, fallback_game):
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    result = json.loads(cleaned.strip())

    detected_game = _sanitize_game_name(str(result.get("game_name", fallback_game)))
    return bool(result.get("interesting", True)), detected_game or fallback_game, str(result.get("reason", "ללא הסבר"))


def judge_clip_locally(frame_paths, fallback_game="General Gameplay", model=DEFAULT_LOCAL_MODEL):
    """
    שיפוט מקומי דרך Ollama - אותה חתימה בדיוק כמו ask_gemini_if_interesting
    (is_interesting, game_name, reason), כדי שאפשר להחליף ביניהם. בכל כשל
    (Ollama לא רץ, המודל לא הורד וכו') מחזיר אישור-כברירת-מחדל שמרני, כדי לא
    לאבד תוכן טוב בגלל תקלה טכנית - בדיוק כמו ההתנהגות הקודמת שהוחלפה.
    """
    images_b64 = []
    for path in frame_paths:
        try:
            with open(path, "rb") as f:
                images_b64.append(base64.b64encode(f.read()).decode("ascii"))
        except OSError:
            continue

    if not images_b64:
        return True, fallback_game, "לא ניתן היה לקרוא פריימים לשיפוט מקומי (מאשר כברירת מחדל)"

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model,
                "prompt": JUDGE_PROMPT_TEMPLATE.format(fallback_game=fallback_game),
                "images": images_b64,
                "stream": False,
                "format": "json",
            },
            timeout=120,
        )
        response.raise_for_status()
        raw_text = response.json().get("response", "")
        is_interesting, game_name, reason = _parse_judge_response(raw_text, fallback_game)
        return is_interesting, game_name, f"(local:{model}) {reason}"
    except Exception as e:
        return True, fallback_game, f"שיפוט מקומי נכשל ({e}) - מאשר כברירת מחדל"
