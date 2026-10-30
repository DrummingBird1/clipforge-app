# dataviz/web/publish.py (עד 19.10.2026: utils/dataviz_publish.py)
#
# צעדי הפרסום של סרטון נתונים (dataviz): כותרת/SEO, תמונה ממוזערת ואישור - אותם שלבים שיש
# ל-Rocket Shorts (utils/title_generator, seo_generator, thumbnail_generator), אבל בלי להניח
# שהסרטון הוא קליפ גיימינג: הכותרת באה מ-config.yaml של הפרק (publish.title, אחרת title),
# ו-Gemini (publish.seo_ai) אופציונלי וכבוי כברירת מחדל כדי לא לצרוך מכסה בלי שביקשו.
#
# "אישור" כאן = קובץ <שם>.publish.json ליד הסרטון עם status: pending_approval. שום דבר לא
# מועלה אוטומטית - רק אחרי set_decision(..., "approved") (דרך dataviz_maker.py --decide) אפשר
# להעלות. בכוונה לא משתמשים בטבלת pending_approvals של הבוט: אישור שם מעביר את הקובץ
# לתיקיית הקלט של Rocket Shorts, שזה לא מה שרוצים לסרטון נתונים מוגמר.
#
# כל צעד נכשל בנפרד (נרשם ב-steps) ולא מפיל את הרינדור - הסרטון כבר נוצר.

import json
import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Mapping, Optional

PENDING = "pending_approval"
APPROVED = "approved"
REJECTED = "rejected"
DECISIONS = (APPROVED, REJECTED)

YOUTUBE_TITLE_MAX = 100
TIKTOK_CAPTION_MAX = 2200
MAX_HASHTAGS = 8
SIDECAR_SUFFIX = ".publish.json"
DEFAULT_TAGS = ("#dataviz", "#DataIsBeautiful")


def sidecar_path(video_path: str) -> str:
    return os.path.splitext(video_path)[0] + SIDECAR_SUFFIX


def clean_hashtags(tags: Any) -> List[str]:
    """תגיות עם #, בלי רווחים/סימנים, בלי כפילויות, עד MAX_HASHTAGS."""
    result: List[str] = []
    seen = set()
    for tag in tags if isinstance(tags, (list, tuple)) else []:
        word = "".join(ch for ch in str(tag).lstrip("#") if ch.isalnum() or ch == "_")
        if word and word.lower() not in seen:
            seen.add(word.lower())
            result.append("#" + word)
    return result[:MAX_HASHTAGS]


def _paragraphs(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def build_metadata(config: Mapping[str, Any], ai_meta: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """כותרת/תיאור/תגיות לפרק. עדיפות: publish.* מההגדרות, אחר כך Gemini (אם ניתן), אחר כך title/subtitle של הפרק."""
    publish = config.get("publish") or {}
    ai_meta = ai_meta or {}
    title = " ".join(str(publish.get("title") or ai_meta.get("title") or config.get("title") or config.get("name") or "").split())
    # סבב הייצוב: ירידות שורה בתיאור נשמרות (פסקאות ביוטיוב); רווחים כפולים בתוך שורה ושורות ריקות רצופות מתכווצים
    description = _paragraphs(str(publish.get("description") or ai_meta.get("description") or config.get("subtitle") or ""))
    tags = clean_hashtags([*(publish.get("hashtags") or []), *(ai_meta.get("hashtags") or []), *DEFAULT_TAGS])
    return {
        "source": "ai" if ai_meta and not (publish.get("title") and publish.get("description")) else "config",
        "title": title,
        "description": description,
        "hashtags": tags,
        "youtube_title": title[:YOUTUBE_TITLE_MAX],
        "youtube_tags": [t.lstrip("#") for t in tags],
        "tiktok_caption": f"{title} {' '.join(tags)}"[:TIKTOK_CAPTION_MAX],
        # גל 50: מקורות הנתונים (outro.credits) - נוספים לתיאור כבלוק משלהם, גם אחרי עריכת התיאור באשף
        "credits": [str(line).strip() for line in (config.get("outro") or {}).get("credits") or [] if str(line).strip()],
    }


def chapters_block(meta: Mapping[str, Any]) -> str:
    """גל 55: הפרקים ליוטיוב ("0:00 פתיח" ...) - יוטיוב מזהה אותם מהתיאור."""
    return "\n".join(str(line) for line in meta.get("chapters") or [])


def read_chapters(video_path: str) -> List[str]:
    """השורות מ-<שם>.chapters.txt שהרינדור כתב ליד הסרטון (ריק כשאין)."""
    try:
        with open(os.path.splitext(video_path)[0] + ".chapters.txt", "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()][:100]
    except OSError:
        return []


def credits_block(meta: Mapping[str, Any]) -> str:
    lines = list(meta.get("credits") or [])
    return "מקורות הנתונים:\n" + "\n".join(f"- {line}" for line in lines) if lines else ""


def seo_sheet(video_name: str, meta: Mapping[str, Any]) -> str:
    source = "🤖 Gemini" if meta["source"] == "ai" else "📝 מהגדרות הפרק"
    description = "".join(f"{part}\n" for part in (meta["description"], chapters_block(meta), credits_block(meta)) if part)
    return (
        f"==================================================\n"
        f"🚀 SEO SHEET - {video_name} ({datetime.now().strftime('%Y-%m-%d %H:%M')}) - {source}\n"
        f"==================================================\n\n"
        f"📱 [TIKTOK CAPTION]:\n{meta['tiktok_caption']}\n\n"
        f"▶️ [YOUTUBE TITLE]:\n{meta['youtube_title']}\n\n"
        f"📝 [YOUTUBE DESCRIPTION]:\n{description}{' '.join(meta['hashtags'])}\n\n"
    )


def _write_json(path: str, data: Mapping[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def prepare_publish(video_path: str, config: Mapping[str, Any], ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe",
                    ai_metadata: Optional[Callable[[str], Mapping[str, Any]]] = None,
                    make_thumbnail: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    """יוצר ליד video_path: _thumb.jpg, _metadata_seo.txt ו-.publish.json. מחזיר את תוכן ה-.publish.json.

    ai_metadata/make_thumbnail ניתנים להחלפה (בדיקות, ובלי תלות ב-Gemini/ffmpeg כשלא צריך)."""
    publish = config.get("publish") or {}
    base = os.path.splitext(video_path)[0]
    steps: Dict[str, str] = {}

    ai_meta: Optional[Mapping[str, Any]] = None
    if publish.get("seo_ai"):
        try:
            if ai_metadata is None:
                from utils.title_generator import generate_metadata
                ai_metadata = lambda path: generate_metadata(path, "data visualization")  # noqa: E731
            ai_meta = ai_metadata(video_path)
            steps["ai"] = "ok"
        except Exception as e:  # בלי מפתח/מכסה/רשת - ההגדרות מספיקות
            steps["ai"] = f"failed: {e}"
    meta = build_metadata(config, ai_meta)
    meta["chapters"] = read_chapters(video_path)   # גל 55: נכתב בסוף הרינדור (dataviz/captions.write_chapters)

    sheet_path = base + "_metadata_seo.txt"
    try:
        with open(sheet_path, "w", encoding="utf-8") as f:
            f.write(seo_sheet(os.path.basename(video_path), meta))
        steps["seo"] = "ok"
    except OSError as e:
        steps["seo"] = f"failed: {e}"
        sheet_path = ""

    thumb_path = ""
    if publish.get("thumbnail", True):
        try:
            if make_thumbnail is None:
                from dataviz.web.thumbnail import make_thumbnail as default_thumbnail   # סבב הייצוב: כותרת בעברית מימין לשמאל, שנכנסת ברוחב
                make_thumbnail = default_thumbnail
            thumb_path = base + "_thumb.jpg"
            make_thumbnail(video_path, thumb_path, ffmpeg_exe=ffmpeg, ffprobe_exe=ffprobe, title_text=meta["title"])
            steps["thumbnail"] = "ok" if os.path.isfile(thumb_path) else "failed: הקובץ לא נוצר"
            if steps["thumbnail"] != "ok":
                thumb_path = ""
        except Exception as e:
            steps["thumbnail"] = f"failed: {e}"
            thumb_path = ""
    else:
        steps["thumbnail"] = "skipped"

    needs_approval = bool(publish.get("approval", True))
    package = {
        "status": PENDING if needs_approval else APPROVED,
        "video": os.path.basename(video_path),
        "thumbnail": os.path.basename(thumb_path),
        "seo_sheet": os.path.basename(sheet_path),
        "metadata": meta,
        "steps": steps,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "decided_at": "",
    }
    _write_json(sidecar_path(video_path), package)
    return package


def load_package(path: str) -> Dict[str, Any]:
    """path = קובץ .publish.json או נתיב הסרטון עצמו."""
    if not path.endswith(SIDECAR_SUFFIX):
        path = sidecar_path(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or data.get("status") not in (PENDING, *DECISIONS):
        raise ValueError(f"קובץ פרסום לא תקין: {path}")
    return data


def set_decision(path: str, decision: str) -> Dict[str, Any]:
    """מעדכן את הסטטוס ל-approved/rejected. רק מ-pending_approval - החלטה שכבר התקבלה לא נדרסת בשקט."""
    if decision not in DECISIONS:
        raise ValueError(f"החלטה לא מוכרת: {decision!r} (קיימות: {', '.join(DECISIONS)}).")
    sidecar = path if path.endswith(SIDECAR_SUFFIX) else sidecar_path(path)
    package = load_package(sidecar)
    if package["status"] != PENDING:
        raise ValueError(f"כבר התקבלה החלטה ({package['status']}) - לא משנים אותה בשקט.")
    package["status"] = decision
    package["decided_at"] = datetime.now().isoformat(timespec="seconds")
    _write_json(sidecar, package)
    return package


SEND_TARGETS = ("dry_run", "rocket", "youtube")


def send_plan(package: Mapping[str, Any], folder: str, target: str) -> Dict[str, Any]:
    """מה *היה* נשלח (בלי שום תופעת לוואי): קובץ, כותרת, תיאור, תגיות, פרטיות. ValueError אם החבילה לא ניתנת לשליחה.
    רק חבילה שאושרה ידנית, עם קובץ וידאו קיים, ושלא נשלחה כבר ליעד הזה."""
    if target not in SEND_TARGETS:
        raise ValueError(f"יעד לא מוכר: {target!r} (מותר: {', '.join(SEND_TARGETS)}).")
    if package.get("status") != APPROVED:
        raise ValueError("אפשר לשלוח רק חבילה שאושרה.")
    video = os.path.join(folder, os.path.basename(package.get("video", "")))
    if not package.get("video") or not os.path.isfile(video):
        raise ValueError("קובץ הסרטון של החבילה לא נמצא.")
    if target != "dry_run" and target in (package.get("sent") or {}):
        raise ValueError("החבילה כבר נשלחה ליעד הזה.")
    meta = package.get("metadata") or {}
    title = (meta.get("youtube_title") or meta.get("title") or os.path.splitext(os.path.basename(video))[0])[:YOUTUBE_TITLE_MAX]
    tags = clean_hashtags(meta.get("hashtags", []))
    description = "\n\n".join(part for part in (meta.get("description", ""), chapters_block(meta), credits_block(meta), " ".join(tags)) if part)
    thumb = os.path.join(folder, os.path.basename(str(package.get("thumbnail") or "")))
    return {"target": target, "video": video, "title": title, "description": description,
            "thumbnail": thumb if package.get("thumbnail") and os.path.isfile(thumb) else "",
            "tags": [t.lstrip("#") for t in tags], "privacy": "private"}


METADATA_LIMITS = {"title": 200, "youtube_title": YOUTUBE_TITLE_MAX, "description": 5000, "tiktok_caption": TIKTOK_CAPTION_MAX}


def update_metadata(sidecar: str, changes: Mapping[str, Any]) -> Dict[str, Any]:
    """גל 41 (אשף הפרסום): עריכת הכותרת, התיאור והתגיות של חבילה שעוד לא נשלחה. ValueError על ערך לא תקין."""
    package = load_package(sidecar)
    if package.get("sent"):
        raise ValueError("החבילה כבר נשלחה - אי אפשר לשנות את הטקסטים שלה.")
    meta = dict(package.get("metadata") or {})
    for key, limit in METADATA_LIMITS.items():
        if key in changes:
            value = changes[key]
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError(f"{key}: טקסט עד {limit} תווים.")
            meta[key] = value.strip()
    if "hashtags" in changes:
        meta["hashtags"] = clean_hashtags(changes["hashtags"])
    package["metadata"] = meta
    _write_json(sidecar, package)
    return package


def record_send(sidecar: str, target: str, info: Mapping[str, Any]) -> Dict[str, Any]:
    """רושם בקובץ החבילה שנשלחה ליעד (מונע שליחה כפולה בטעות)."""
    package = load_package(sidecar)
    sent = dict(package.get("sent") or {})
    sent[target] = {"at": datetime.now().isoformat(timespec="seconds"), **info}
    package["sent"] = sent
    _write_json(sidecar, package)
    return package


def list_packages(folder: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """כל קובצי .publish.json בתיקייה (לא רקורסיבי), עם 'path'; status=None = הכל."""
    result: List[Dict[str, Any]] = []
    if not os.path.isdir(folder):
        return result
    for name in sorted(os.listdir(folder)):
        if not name.endswith(SIDECAR_SUFFIX):
            continue
        try:
            package = load_package(os.path.join(folder, name))
        except (OSError, ValueError):
            continue
        if status is None or package["status"] == status:
            result.append({**package, "path": os.path.join(folder, name)})
    return result


# ---------- גל 44: שלוש תמונות ממוזערות לבחירה, הצעת טקסטים מ-Gemini, וצפיות ----------
CANDIDATE_POINTS = (0.3, 0.6, 0.9)


def candidate_name(base_name: str, k: int) -> str:
    return f"{base_name}_thumb_c{k}.jpg"


def thumbnail_candidates(sidecar: str, *, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe",
                         extract: Optional[Callable[..., Any]] = None, draw: Optional[Callable[..., Any]] = None,
                         duration: Optional[float] = None) -> List[str]:
    """שלוש תמונות מועמדות (30% / 60% / 90% מהסרטון, עם הכותרת) ליד הסרטון: <שם>_thumb_c1..3.jpg."""
    import tempfile
    package = load_package(sidecar)
    folder = os.path.dirname(sidecar)
    video = os.path.join(folder, os.path.basename(package.get("video", "")))
    if not os.path.isfile(video):
        raise ValueError("קובץ הסרטון לא נמצא ליד החבילה.")
    if extract is None or draw is None or duration is None:
        from utils import thumbnail_generator as tg
        from dataviz.web.thumbnail import draw_title
        extract = extract or tg.extract_frame_at_timestamp
        draw = draw or draw_title
        if duration is None:
            duration = tg.get_video_duration_via_ffprobe(video, ffprobe)
    meta = package.get("metadata") or {}
    title = meta.get("youtube_title") or meta.get("title") or os.path.splitext(os.path.basename(video))[0]
    base = os.path.basename(sidecar)[: -len(SIDECAR_SUFFIX)]
    names = []
    with tempfile.TemporaryDirectory() as tmp:
        for k, point in enumerate(CANDIDATE_POINTS, start=1):
            frame = os.path.join(tmp, f"frame_{k}.jpg")
            if extract(video, max(0.1, float(duration) * point), frame, ffmpeg):
                name = candidate_name(base, k)
                draw(frame, title, os.path.join(folder, name))
                names.append(name)
    if not names:
        raise ValueError("לא הצלחתי לחלץ פריימים מהסרטון.")
    return names


def choose_thumbnail(sidecar: str, k: int) -> Dict[str, Any]:
    """המועמדת k הופכת לתמונה הממוזערת של החבילה. התמונה הקודמת נשמרת פעם אחת כ-<שם>_thumb_original.jpg."""
    import shutil
    package = load_package(sidecar)
    if package.get("sent"):
        raise ValueError("החבילה כבר נשלחה - אי אפשר להחליף את התמונה.")
    folder = os.path.dirname(sidecar)
    base = os.path.basename(sidecar)[: -len(SIDECAR_SUFFIX)]
    candidate = os.path.join(folder, candidate_name(base, int(k)))
    if int(k) not in range(1, len(CANDIDATE_POINTS) + 1) or not os.path.isfile(candidate):
        raise ValueError("התמונה המועמדת לא נמצאה - צור קודם את שלוש האפשרויות.")
    thumb = os.path.join(folder, base + "_thumb.jpg")
    original = os.path.join(folder, base + "_thumb_original.jpg")
    if os.path.isfile(thumb) and not os.path.exists(original):
        shutil.copy2(thumb, original)
    shutil.copy2(candidate, thumb)
    package["thumbnail"] = os.path.basename(thumb)
    package.setdefault("steps", {})["thumbnail"] = f"ok (candidate {int(k)})"
    _write_json(sidecar, package)
    return package


def suggest_metadata(sidecar: str, generate: Optional[Callable[[str], Mapping[str, Any]]] = None) -> Dict[str, Any]:
    """כותרת, תיאור ותגיות מ-Gemini לסרטון של החבילה - הצעה בלבד, לא נשמרת."""
    package = load_package(sidecar)
    video = os.path.join(os.path.dirname(sidecar), os.path.basename(package.get("video", "")))
    if not os.path.isfile(video):
        raise ValueError("קובץ הסרטון לא נמצא ליד החבילה.")
    if generate is None:
        from utils.title_generator import generate_metadata
        generate = lambda path: generate_metadata(path, "data visualization")  # noqa: E731
    meta = dict(generate(video) or {})
    return {"title": str(meta.get("title") or "")[:METADATA_LIMITS["youtube_title"]],
            "description": str(meta.get("description") or "")[:METADATA_LIMITS["description"]],
            "hashtags": clean_hashtags(meta.get("hashtags") or [])}


def record_stats(sidecar: str, stats: Mapping[str, Any]) -> Dict[str, Any]:
    """הצפיות / לייקים / תגובות האחרונים שנמשכו מיוטיוב - נשמרים בחבילה (כרטיס הפרק מציג בלי לפנות שוב)."""
    package = load_package(sidecar)
    package["stats"] = {**{k: int(stats.get(k) or 0) for k in ("views", "likes", "comments")}, "at": datetime.now().isoformat(timespec="seconds")}
    # גל 55: היסטוריה - לגרף הצפיות של הסדרה (עד 200 מדידות)
    package["stats_history"] = (list(package.get("stats_history") or []) + [dict(package["stats"])])[-200:]
    _write_json(sidecar, package)
    return package
