# utils/bot/youtube_extras.py
#
# 16.11.2026 (ClipForge 2.0): מה שנוסף להעלאה ליוטיוב, בלי לגעת בהעלאה עצמה (youtube_uploader.upload_video):
# - פרקים: מהפרקים שהסטודיו כבר כותב לתוך הקובץ (metadata chapters, ffprobe -show_chapters), בפורמט שיוטיוב מזהה בתיאור.
#   הכללים של יוטיוב: הראשון ב-00:00, לפחות 3, וכל אחד לפחות 10 שניות - אחרת הוא מתעלם מכולם. פרק קצר מתמזג לקודם.
# - כתוביות: קובץ SRT ליד הסרטון (<שם>.srt - מה שהסטודיו מייצא) עולה כמסלול כתוביות (captions.insert).
# - Shorts: אנכי ועד 3 דקות - #Shorts בתיאור, כמו שיוטיוב ממליץ.
# - תזמון: publishAt ב-ISO 8601 (UTC). זמן שעבר או לא תקין - נדחה לפני ההעלאה.
import datetime
import json
import os
import subprocess
from typing import List, Optional, Tuple

MIN_CHAPTERS = 3
MIN_CHAPTER_SECONDS = 10


def stamp(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def chapters_text(chapters: List[Tuple[float, str]], duration: Optional[float] = None, first_title: str = "פתיחה") -> str:
    """שורות "00:00 כותרת" ליוטיוב, או "" כשאין מספיק פרקים תקינים."""
    points = sorted((max(0.0, float(t)), str(title or "").strip() or f"חלק {i + 1}") for i, (t, title) in enumerate(chapters))
    if not points:
        return ""
    if points[0][0] > 0:
        points.insert(0, (0.0, first_title))
    else:
        points[0] = (0.0, points[0][1])
    merged: List[Tuple[float, str]] = []
    for start, title in points:
        if merged and start - merged[-1][0] < MIN_CHAPTER_SECONDS:
            continue   # קצר מדי - נבלע בקודם
        merged.append((start, title))
    if duration and merged and duration - merged[-1][0] < MIN_CHAPTER_SECONDS and len(merged) > 1:
        merged.pop()
    if len(merged) < MIN_CHAPTERS:
        return ""
    return "\n".join(f"{stamp(start)} {title}" for start, title in merged)


def read_chapters(path: str, ffprobe_exe: str, creationflags: int = 0) -> List[Tuple[float, str]]:
    try:
        result = subprocess.run([ffprobe_exe, "-v", "error", "-show_chapters", "-of", "json", path], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=30, creationflags=creationflags)
        data = json.loads(result.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    out = []
    for chapter in data.get("chapters", []):
        try:
            out.append((float(chapter.get("start_time", 0)), str((chapter.get("tags") or {}).get("title") or "")))
        except (TypeError, ValueError):
            continue
    return out


def is_short(width: int, height: int, duration: float) -> bool:
    return bool(width and height and height > width and 0 < duration <= 180)


def with_extras(description: str, chapters: str = "", short: bool = False) -> str:
    parts = [description.strip()] if description and description.strip() else []
    if chapters:
        parts.append(chapters)
    if short and "#shorts" not in description.lower():
        parts.append("#Shorts")
    return "\n\n".join(parts)[:5000]


def parse_publish_at(value: str, now: Optional[datetime.datetime] = None) -> str:
    """'' -> '' (מיד). אחרת זמן עתידי ב-UTC בפורמט של יוטיוב ("2026-11-20T18:00:00Z"). ValueError על זמן שעבר / לא תקין.
    בלי אזור זמן - זמן מקומי של המחשב (זה מה ששדה datetime-local בדפדפן שולח)."""
    value = (value or "").strip()
    if not value:
        return ""
    when = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if when.tzinfo is None:
        when = when.astimezone()
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if when <= now + datetime.timedelta(minutes=1):
        raise ValueError("זמן הפרסום כבר עבר")
    return when.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sidecar_srt(video_path: str) -> Optional[str]:
    stem = os.path.splitext(video_path)[0]
    for candidate in (stem + ".srt", stem + ".he.srt", stem + ".en.srt"):
        if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
            return candidate
    return None


def srt_language(srt_path: str) -> str:
    """שפת הכתוביות: לפי השם (clip.en.srt / clip.he.srt), ואחרת לפי התוכן - אותיות עבריות = "he", בלעדיהן "en".
    ב-2.0.0 כל קובץ הועלה כ"עברית", גם כתוביות שתורגמו לאנגלית."""
    name = os.path.basename(srt_path).lower()
    for code in ("he", "en"):
        if name.endswith(f".{code}.srt"):
            return code
    try:
        with open(srt_path, encoding="utf-8-sig", errors="replace") as f:
            sample = f.read(20000)
    except OSError:
        return "en"
    return "he" if any("\u0590" <= ch <= "\u05ff" for ch in sample) else "en"


def upload_captions(video_id: str, srt_path: str, language: str = "", name: str = "") -> None:
    """מסלול כתוביות לסרטון שכבר עלה (YouTube Data API, captions.insert). זורק על כשל - הקורא רושם ולא מפיל את ההעלאה."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    from utils.bot.youtube_uploader import _get_credentials

    language = language or srt_language(srt_path)
    youtube = build("youtube", "v3", credentials=_get_credentials(need_captions=True))
    body = {"snippet": {"videoId": video_id, "language": language, "name": name or language, "isDraft": False}}
    youtube.captions().insert(part="snippet", body=body,
                              media_body=MediaFileUpload(srt_path, mimetype="application/octet-stream")).execute()
