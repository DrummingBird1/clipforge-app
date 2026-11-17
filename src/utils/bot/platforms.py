# utils/bot/platforms.py
#
# 16.11.2026 (ClipForge 2.0): רישום אחד של הפלטפורמות - מה כל אחת מקבלת (יחס, אורך, גודל, אורך כיתוב), לאן מעלים, ואיזה
# יעד של הסטודיו (editor_model.TARGET_PRESETS) מכין קובץ בשבילה. חבילת ההעלאה (upload_package.py) בודקת קובץ מול הרשומה.
# YouTube בלבד עולה ישירות (youtube_uploader.py, API). לשאר - חבילה מוכנה ופתיחת דף ההעלאה (TikTok / Instagram דורשים
# אפליקציה מאושרת אצלם, ול-Twitch ול-Kick אין API להעלאת וידאו); Discord - דרך הבוט (clip_share).
# המגבלות נכונות לנובמבר 2026 ומשמשות לאזהרות, לא לחסימה: פלטפורמה שינתה מגבלה - מעדכנים כאן בלבד.
from typing import Any, Dict, List, NamedTuple, Optional


class Platform(NamedTuple):
    id: str
    label: str
    target: str              # יעד בסטודיו (editor_model.TARGET_PRESETS)
    orientation: str         # vertical / horizontal / any
    max_seconds: Optional[int]
    max_mb: Optional[float]
    caption_limit: int       # תווים בכיתוב / בתיאור
    title_limit: int         # 0 = אין שדה כותרת נפרד
    upload_url: str
    how: str                 # api / package / bot


PLATFORMS: Dict[str, Platform] = {p.id: p for p in (
    Platform("youtube", "YouTube", "youtube", "horizontal", None, None, 5000, 100, "https://studio.youtube.com", "api"),
    Platform("shorts", "YouTube Shorts", "shorts", "vertical", 180, None, 5000, 100, "https://studio.youtube.com", "api"),
    Platform("tiktok", "TikTok", "tiktok", "vertical", 3600, 4096, 4000, 0, "https://www.tiktok.com/tiktokstudio/upload", "package"),
    Platform("reels", "Instagram Reels", "reels", "vertical", 180, 4096, 2200, 0, "https://www.instagram.com/", "package"),
    Platform("twitch", "Twitch", "twitch", "horizontal", None, 10240, 5000, 140, "https://dashboard.twitch.tv/content/video-producer", "package"),
    Platform("kick", "Kick", "kick", "horizontal", None, None, 5000, 140, "https://kick.com/dashboard", "package"),
    Platform("discord", "Discord (10MB)", "discord", "any", None, 10, 2000, 0, "", "bot"),
    Platform("discord_50", "Discord (50MB)", "discord_50", "any", None, 50, 2000, 0, "", "bot"),
)}


def get(platform_id: str) -> Optional[Platform]:
    return PLATFORMS.get(platform_id)


def check(platform: Platform, probe: Dict[str, Any], size_bytes: int) -> List[str]:
    """אזהרות: הקובץ לא מתאים לפלטפורמה (כיוון, אורך, גודל). ריק = מתאים."""
    warnings: List[str] = []
    width, height = int(probe.get("width") or 0), int(probe.get("height") or 0)
    duration = float(probe.get("duration") or 0)
    if width and height:
        if platform.orientation == "vertical" and width >= height:
            warnings.append(f"{platform.label} מצפה לסרטון אנכי (9:16), והקובץ {width}x{height}")
        elif platform.orientation == "horizontal" and height > width:
            warnings.append(f"{platform.label} מצפה לסרטון אופקי (16:9), והקובץ {width}x{height}")
    if platform.max_seconds and duration > platform.max_seconds:
        warnings.append(f"ארוך מדי ל-{platform.label}: {duration:.0f} שניות מתוך {platform.max_seconds}")
    if platform.max_mb and size_bytes > platform.max_mb * 1024 * 1024:
        warnings.append(f"גדול מדי ל-{platform.label}: {size_bytes / 1024 / 1024:.1f}MB מתוך {platform.max_mb:g}MB")
    return warnings


def as_dicts() -> List[Dict[str, Any]]:
    return [p._asdict() for p in PLATFORMS.values()]
