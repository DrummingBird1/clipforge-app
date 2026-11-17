# utils/bot/upload_package.py
#
# 16.11.2026 (ClipForge 2.0): "חבילת העלאה" לפלטפורמה שאין לה העלאה ישירה (TikTok, Reels, Twitch, Kick): תיקייה אחת עם
# הסרטון, caption.txt (כותרת, תיאור ותגיות - בתוך מגבלת התווים של הפלטפורמה), תמונה ממוזערת אם יש, ו-package.json
# עם הבדיקות (כיוון, אורך, גודל). הממשק מעתיק את הכיתוב ופותח את דף ההעלאה. הסרטון מקושר (hardlink) כשאפשר - בלי עותק כפול.
import json
import os
import re
import shutil
import time
from typing import Any, Dict, List, Optional

from utils.bot import platforms
from utils.shared import path_safety


def _new_folder(path: str) -> str:
    """תיקייה חדשה בשם path, או path_2, path_3... - שתי חבילות באותה שנייה לא חולקות תיקייה (17.11.2026: בתיקייה משותפת
    סרטון שני באותו שם נכתב על הקישור של הראשון ודרס את סרטון המקור שלו)."""
    candidate, n = path, 2
    while True:
        try:
            os.makedirs(candidate)
            return candidate
        except FileExistsError:
            candidate, n = f"{path}_{n}", n + 1


def hashtags(tags: List[str]) -> str:
    out = []
    for tag in tags or []:
        clean = re.sub(r"[\s#]+", "", str(tag))
        if clean and ("#" + clean) not in out:
            out.append("#" + clean)
    return " ".join(out)


def caption(platform: platforms.Platform, title: str, description: str, tags: List[str]) -> Dict[str, str]:
    """{"title", "caption"} בגבולות הפלטפורמה. בלי שדה כותרת נפרד (TikTok, Reels) - הכותרת היא השורה הראשונה בכיתוב.
    קיצור - קודם התיאור, אחר כך התגיות; הכותרת והתגיות נשארות כשאפשר."""
    title = " ".join(str(title or "").split())
    description = str(description or "").strip()
    tag_line = hashtags(tags)
    head = title if not platform.title_limit else ""
    parts = [p for p in (head, description, tag_line) if p]
    text = "\n\n".join(parts)
    if len(text) > platform.caption_limit:
        fixed = "\n\n".join(p for p in (head, tag_line) if p)
        room = platform.caption_limit - len(fixed) - (4 if fixed else 0)
        short = (description[:max(0, room - 1)].rstrip() + "…") if room > 1 and description else ""
        text = "\n\n".join(p for p in (head, short, tag_line) if p)[:platform.caption_limit]
    return {"title": title[:platform.title_limit] if platform.title_limit else "", "caption": text}


def build(video_path: str, platform_id: str, out_root: str, title: str = "", description: str = "",
          tags: Optional[List[str]] = None, thumbnail: Optional[str] = None, probe: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    platform = platforms.get(platform_id)
    if platform is None or platform.how != "package":
        raise ValueError(f"אין חבילת העלאה ל-{platform_id!r}")
    if not os.path.isfile(video_path):
        raise FileNotFoundError(video_path)
    stem = os.path.splitext(os.path.basename(video_path))[0]
    os.makedirs(os.path.join(out_root, platform.id), exist_ok=True)
    folder = _new_folder(os.path.join(out_root, platform.id, f"{stem}_{time.strftime('%Y%m%d_%H%M%S')}"))
    video = path_safety.link_or_copy_new(video_path, os.path.join(folder, os.path.basename(video_path)))
    text = caption(platform, title or stem, description, tags or [])
    with open(os.path.join(folder, "caption.txt"), "w", encoding="utf-8") as f:
        f.write((text["title"] + "\n\n" if text["title"] else "") + text["caption"] + "\n")
    thumb = None
    if thumbnail and os.path.isfile(thumbnail):
        thumb = os.path.join(folder, "thumbnail" + os.path.splitext(thumbnail)[1].lower())
        shutil.copy2(thumbnail, thumb)
    warnings = platforms.check(platform, probe or {}, os.path.getsize(video_path))
    info = {"platform": platform.id, "label": platform.label, "video": video, "folder": folder, "thumbnail": thumb,
            "title": text["title"], "caption": text["caption"], "upload_url": platform.upload_url, "warnings": warnings,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(folder, "package.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    return info
