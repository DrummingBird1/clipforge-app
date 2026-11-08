# utils/video/video_editor_profiles.py
#
# פרופילים אישיים ל-video_editor.py ("עורך-העל") - להבדיל מ-VIDEO_EDITOR_PRESETS
# הקבועים (utils/video/video_editor.py, מובנים בקוד ולא כוללים watermark_path בכוונה
# כי הוא ספציפי-למשתמש), אלה פרופילים שהמשתמש עצמו יוצר/שומר/מוחק: snapshot
# מלא של כל שדות הטופס - כולל נתיבים (watermark_path), ערכי סליידר (opacity)
# וכל שאר ההגדרות/הצ'קבוקסים. נשמר כ-JSON תחת data/, אותו דפוס בדיוק כמו
# data/rocket_settings.json - קובץ הגדרות פשוט, לא DB.
#
# מקור אמת יחיד: גם ה-GUI השולחני (ui/settings_tab.py) וגם ה-web app
# (web_app.py, דרך /api/video_editor_profiles) קוראים/כותבים מכאן, לא משכפלים -
# כלומר כתיבה מקבילה משני תהליכים נפרדים כן אפשרית בפועל (item: בדיקת באגים
# מקיפה - התיעוד הישן כאן טען ההפך). _write_profiles כותבת אטומית (ראו
# utils/shared/atomic_write.py) כדי שקריסה/הריגה באמצע כתיבה לא תשחית את כל קובץ
# הפרופילים - זה עדיין לא מונע "העדכון האחרון מנצח" בין שני כותבים בו-זמנית
# (TOCTOU), שדורש מנעול חוצה-תהליכים אמיתי (כמו utils/shared/render_lock.py) אם
# יתברר שזה בעיה מעשית בפועל, לא רק תיאורטית.

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utils.shared.atomic_write import atomic_write_json
from utils.shared import data_paths

PROFILES_PATH = data_paths.path(data_paths.EDITOR_PROFILES)

# מטא-דאטת שימוש (item: חותמת "בשימוש לאחרונה" + גרסת-סכימה) והיסטוריית-שינויים
# (item: היסטוריית-שינויים/undo לפרופיל) נשמרות בקבצים נפרדים לגמרי מ-
# PROFILES_PATH במתכוון - profiles[name] נשאר snapshot נקי של PROFILE_FIELDS
# בדיוק (שני הממשקים כבר קוראים אותו ככה, וטסט קיים אוכף set(keys)==PROFILE_FIELDS),
# לא מעורבב עם שדות-בקרה שהם לא הגדרת-רינדור אמיתית.
META_PATH = data_paths.path(data_paths.EDITOR_PROFILE_META)
HISTORY_PATH = data_paths.path(data_paths.EDITOR_PROFILE_HISTORY)
MAX_HISTORY_PER_PROFILE = 5
PROFILE_SCHEMA_VERSION = 1

# כל השדות שפרופיל שומר - snapshot מלא של טופס video_editor.py (זהה לרשימת
# ה-payload ב-web_app.py's _collectRunOptions/_build_extra_args). שדה שלא
# נמסר ב-settings שנשמר מקבל None, כדי שטעינה עתידית תמיד תמצא את כל המפתחות
# ולא תיכשל על KeyError בצד הקורא. "folder" (item: תיקיית קלט בפרופיל) חורג
# בכוונה מהמוסכמה "video_editor_<field>" (state.selected_gameplay_folder,
# לא state.video_editor_folder) - זו תיקיית הקלט המשותפת לכל הסקריפטים
# באפליקציה, לא הגדרה ספציפית לעורך-העל - הקוראים (settings_tab.py/web_app.py)
# אוספים אותה בנפרד מלולאת ה-PROFILE_FIELDS הגנרית, לא דרך getattr אוטומטי.
PROFILE_FIELDS = (
    "watermark_path", "watermark_position", "watermark_opacity", "watermark_scale", "watermark_x", "watermark_y",
    "remove_watermark_position", "pip_path", "pip_position", "pip_scale", "pip_opacity", "pip_x", "pip_y",
    "vertical", "smart_crop", "smart_crop_face", "blur_background",
    "trim_start", "trim_duration", "trim_silence", "target_seconds",
    "keep_audio", "captions", "captions_translate", "loudnorm", "loudnorm_target", "denoise", "sharpen",
    "thumbnail", "codec",
    "fps", "lut_path", "auto_levels", "noise_gate", "remove_mid_silence", "stabilize",
    "chromakey", "chromakey_color", "chromakey_bg_color",
    "caption_font", "caption_font_size", "caption_color", "caption_position", "caption_max_chars",
    "fade_in_seconds", "fade_out_seconds", "text", "text_position", "text_font", "text_font_size", "text_color",
    "replace_audio_path", "remove_ranges",
    "preserve_resolution", "no_suffix", "parallel", "max_concurrent_nvenc", "effort",
    "container", "output_template", "validate_only", "notify_per_file", "export_report",
    "number_videos", "number_prefix", "number_start",
    "folder", "favorite_fields",
    # item: פער CLI→Web - דגלים שהיו קיימים בסקריפט בלי שום שדה בווב
    "hwaccel", "hwaccel_decode", "smooth_fps", "target_size_mb", "force", "preview_only",
    "nvenc_cq", "nvenc_preset", "chromakey_similarity", "chromakey_blend",
    "remove_watermark_width_fraction", "remove_watermark_height_fraction",
    "concat_mode", "concat_transition", "concat_transition_duration", "concat_output_name",
    # גל 4: תצוגה מקדימה ומשוב
    "silence_threshold_db", "silence_min_duration", "remove_watermark_region",
    # גל 5: תור העיבוד
    "include_subfolders", "queue_files",
    # גל 7א: עריכה ותוכן
    "aspect", "custom_width", "custom_height", "fit", "dual_output", "watermark_position_vertical",
    "speed", "crf", "resolution", "scale_algo", "lut_intensity",
    "eq_brightness", "eq_contrast", "eq_saturation", "eq_gamma", "denoise_level", "sharpen_level", "tonemap",
    "rotate", "flip", "deinterlace", "pad_color", "audio_track",
    "caption_style", "captions_language", "captions_model", "captions_export", "captions_no_burn",
    # גל 7ב: שכבות, קישוטים ועיבוד-אחרי
    "layers", "timestamp_overlay", "progress_bar", "progress_bar_color", "progress_bar_position", "progress_bar_height",
    "frame_thickness", "frame_color", "vignette", "ken_burns", "watermark_move_seconds", "pip_audio", "pip_duck",
    "intro_path", "outro_path", "boomerang", "loop_count", "meta_title", "meta_comment", "chapters",
    "export_gif", "gif_width", "gif_fps", "export_audio",
    # גל 12: מודל v2 - יעדי הריצה וערכת המותג המקושרת (ראו utils/video/editor_model.py)
    "targets", "brand_kit",
    # גל 25: תיקון צבע (גלגלים ועקומות) ועיבוד שמע (utils/video/color_audio.py)
    "grade_shadows", "grade_midtones", "grade_highlights", "curves_preset", "curves_master", "curves_red", "curves_green", "curves_blue",
    "audio_highpass", "audio_eq_low", "audio_eq_mid", "audio_eq_mid_freq", "audio_eq_high", "audio_compressor", "audio_denoise",
    "audio_denoise_model",
)


# item: גיבוי אוטומטי מסתובב - פרופילים הם מידע שנוצר ידנית ובלתי-ניתן-לשחזור,
# ואבדו פעם אחת בפועל (20.9.2026). לפני *כל* כתיבה לאחד מקובצי הפרופילים
# (פרופילים/מטא/היסטוריה/סל-מחזור) העותק הקיים מועתק לתיקיית גיבוי, כך שגם
# כתיבה שגויה/קובץ שנמחק בטעות ניתנים לשחזור. הנתיבים נגזרים בזמן-ריצה מהתיקייה
# של הקובץ עצמו (לא קבועים נפרדים) - כדי שטסטים שמפנים את PROFILES_PATH/
# META_PATH/HISTORY_PATH ל-tmp_path יפנו אוטומטית גם את הגיבויים וסל-המחזור,
# ולעולם לא ייגעו בתיקיית data/ האמיתית.
BACKUP_SUBDIR = os.path.join("backups", "video_editor_profiles")
MAX_RECENT_BACKUPS_PER_FILE = 30
KEEP_DAILY_BACKUPS_DAYS = 30


def _backup_dir_for(path: str) -> str:
    return os.path.join(os.path.dirname(path), BACKUP_SUBDIR)


def _trash_path() -> str:
    """item: מחיקה רכה - סל-מחזור לפרופילים, ליד קובץ הפרופילים עצמו."""
    return os.path.join(os.path.dirname(PROFILES_PATH), "video_editor_profiles_trash.json")


def _backup_file_before_write(path: str) -> None:
    """מעתיק את path (אם קיים ולא ריק) לתיקיית הגיבוי עם חותמת-זמן, ואז מסבב:
    נשמרים MAX_RECENT_BACKUPS_PER_FILE האחרונים, *ובנוסף* הגיבוי האחרון של כל
    יום ב-KEEP_DAILY_BACKUPS_DAYS הימים האחרונים - כך שגם הרבה שמירות ברצף
    (למשל מטא-דאטת שימוש שמתעדכנת בכל ריצה) לא דוחקות החוצה את הגרסה של
    אתמול/שלשום. כשל בגיבוי לא עוצר את הכתיבה עצמה (לא מסכן את מה שהמשתמש
    בדיוק שמר), רק מדפיס אזהרה."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            return
        backup_dir = _backup_dir_for(path)
        os.makedirs(backup_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(path))[0]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        shutil.copy2(path, os.path.join(backup_dir, f"{stem}__{stamp}.json"))
        _rotate_backups(backup_dir, stem)
    except OSError as e:
        print(f"[video_editor_profiles] ⚠️ גיבוי לפני כתיבה נכשל ({e}) - ממשיך בכתיבה עצמה.")


def _rotate_backups(backup_dir: str, stem: str) -> None:
    prefix = f"{stem}__"
    names = sorted((n for n in os.listdir(backup_dir) if n.startswith(prefix) and n.endswith(".json")), reverse=True)
    keep = set(names[:MAX_RECENT_BACKUPS_PER_FILE])
    cutoff = datetime.now().timestamp() - KEEP_DAILY_BACKUPS_DAYS * 86400
    seen_days = set()
    for name in names:  # מהחדש לישן - הראשון שנראה בכל יום הוא האחרון של אותו יום
        day = name[len(prefix):len(prefix) + 8]
        if day in seen_days:
            continue
        seen_days.add(day)
        try:
            if datetime.strptime(day, "%Y%m%d").timestamp() >= cutoff:
                keep.add(name)
        except ValueError:
            keep.add(name)  # שם לא-צפוי - לא מוחקים מה שלא מבינים
    for name in names:
        if name not in keep:
            try:
                os.remove(os.path.join(backup_dir, name))  # safe: only this module's own rotating backup copies under backups/video_editor_profiles/, never a live data file
            except OSError:
                pass


def _write_json(path: str, data: Any) -> None:
    _backup_file_before_write(path)
    atomic_write_json(path, data, ensure_ascii=False, indent=2)


def load_profiles() -> Dict[str, Dict[str, Any]]:
    """מחזיר dict {שם פרופיל: הגדרות} - {} אם הקובץ לא קיים/פגום, אף פעם לא
    נכשל (אותו עיקרון כמו כל קובץ data/*.json אחר בפרויקט)."""
    try:
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_profiles(profiles: Dict[str, Dict[str, Any]]) -> None:
    _write_json(PROFILES_PATH, profiles)


def list_profile_backups() -> List[Dict[str, Any]]:
    """רשימת גיבויי קובץ הפרופילים (לא מטא/היסטוריה - אלה משניים), מהחדש לישן,
    עם שמות הפרופילים שבכל גיבוי - כדי שהמשתמש יראה *מה* ישוחזר לפני שהוא
    משחזר, לא רק חותמת-זמן."""
    backup_dir = _backup_dir_for(PROFILES_PATH)
    stem = os.path.splitext(os.path.basename(PROFILES_PATH))[0]
    prefix = f"{stem}__"
    if not os.path.isdir(backup_dir):
        return []
    result = []
    for name in sorted((n for n in os.listdir(backup_dir) if n.startswith(prefix) and n.endswith(".json")), reverse=True):
        full = os.path.join(backup_dir, name)
        data = _load_json_dict(full)
        try:
            created_at = datetime.strptime(name[len(prefix):-len(".json")], "%Y%m%d_%H%M%S_%f").isoformat(timespec="seconds")
        except ValueError:
            created_at = None
        result.append({
            "id": name, "created_at": created_at, "size": os.path.getsize(full),
            "profile_count": len(data), "profile_names": sorted(data.keys()),
        })
    return result


def restore_profile_backup(backup_id: str, mode: str = "merge_missing") -> Dict[str, Any]:
    """משחזר מגיבוי. mode="merge_missing" (ברירת מחדל, לא-הרסני) מוסיף רק
    פרופילים שלא קיימים כרגע - אף פרופיל קיים לא נדרס. mode="replace" מחליף את
    כל קובץ הפרופילים בגיבוי (המצב הנוכחי עצמו מגובה קודם דרך _write_json, אז
    גם שחזור מלא הפיך). ValueError על מזהה לא תקין (כולל ניסיון path traversal)."""
    if mode not in ("merge_missing", "replace"):
        raise ValueError(f"מצב שחזור לא מוכר: {mode!r}")
    valid_ids = {b["id"] for b in list_profile_backups()}
    if backup_id not in valid_ids or os.path.basename(backup_id) != backup_id:
        raise ValueError("גיבוי לא נמצא")
    backup_data = _load_json_dict(os.path.join(_backup_dir_for(PROFILES_PATH), backup_id))
    current = load_profiles()
    if mode == "replace":
        restored_names = sorted(backup_data.keys())
        new_profiles = {name: {field: settings.get(field) for field in PROFILE_FIELDS} for name, settings in backup_data.items() if isinstance(settings, dict)}
    else:
        restored_names = sorted(name for name in backup_data if name not in current)
        new_profiles = dict(current)
        for name in restored_names:
            if isinstance(backup_data[name], dict):
                new_profiles[name] = {field: backup_data[name].get(field) for field in PROFILE_FIELDS}
    _write_profiles(new_profiles)
    return {"restored": restored_names, "mode": mode, "total_profiles": len(new_profiles)}


def backup_profiles_now() -> None:
    """גיבוי יזום (למשל בהפעלת השרת) - אותו מנגנון/סיבוב בדיוק, בלי כתיבה."""
    _backup_file_before_write(PROFILES_PATH)


def _load_json_dict(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _push_profile_history(name: str, previous_snapshot: Dict[str, Any]) -> None:
    """שומר snapshot (רק PROFILE_FIELDS) של המצב *לפני* דריסה/שחזור, עד
    MAX_HISTORY_PER_PROFILE אחרונים לכל פרופיל (הישן ביותר נופל ראשון)."""
    history = _load_json_dict(HISTORY_PATH)
    entries = history.get(name)
    entries = list(entries) if isinstance(entries, list) else []
    entry = {field: previous_snapshot.get(field) for field in PROFILE_FIELDS}
    # item: "saved_at" בכוונה בלי קידומת "_" - FastAPI's jsonable_encoder
    # (web_app.py) מוחק בשקט מפתחות עם "_" בהתחלה מתוך dict מקונן (בתוך list/
    # dict אחר, לא ברמה העליונה) - נמצא בפועל תוך כדי בדיקה חיה בדפדפן: מפתח
    # ברמה העליונה כן שרד, אבל זה בדיוק ה-entry הזה, שמקונן בתוך רשימה.
    entry["saved_at"] = datetime.now(timezone.utc).isoformat()
    entries.append(entry)
    history[name] = entries[-MAX_HISTORY_PER_PROFILE:]
    _write_json(HISTORY_PATH, history)


def _stamp_profile_meta(name: str, **updates: Any) -> None:
    all_meta = _load_json_dict(META_PATH)
    entry = all_meta.get(name)
    entry = dict(entry) if isinstance(entry, dict) else {}
    entry.update(updates)
    all_meta[name] = entry
    _write_json(META_PATH, all_meta)


def save_profile(name: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    """שומר/דורס (אם השם כבר קיים) פרופיל בשם name. רק שדות מ-PROFILE_FIELDS
    נשמרים בפועל - קלט זר לא מוחדר לקובץ. ValueError על שם ריק - עדיף כישלון
    ברור מיד מאשר פרופיל בשם '' שאי אפשר יהיה לבחור אחר כך מרשימה. דריסת
    פרופיל קיים (לא יצירה ראשונה) דוחפת את המצב הקודם להיסטוריה קודם (item:
    היסטוריית-שינויים/undo), ומחתימה את הפרופיל בגרסת-הסכימה הנוכחית (item:
    גרסת-סכימה מפורשת)."""
    name = (name or "").strip()
    if not name:
        raise ValueError("שם פרופיל לא יכול להיות ריק")
    profiles = load_profiles()
    if name in profiles:
        _push_profile_history(name, profiles[name])
    previous = profiles.get(name)
    profiles[name] = {field: settings.get(field) for field in PROFILE_FIELDS}
    _write_profiles(profiles)
    meta_updates: Dict[str, Any] = {"schema_version": PROFILE_SCHEMA_VERSION}
    if previous is None and not load_profile_meta(name)["created_at"]:
        meta_updates["created_at"] = datetime.now(timezone.utc).isoformat()
    # item 68 (ירושה): שדה נחשב "נדרס" בפרופיל-ילד רק אם המשתמש שינה אותו בילד
    # (בשמירה הזו או קודם) *וגם* הוא עדיין שונה מההורה - כך שינוי שנעשה אחר כך
    # בהורה ימשיך "לזרום" לילד ב-pull_from_parent, ולא ייחשב בטעות כדריסה.
    parent = load_profile_meta(name)["parent"]
    if parent and parent in profiles and parent != name:
        changed_now = set(_differing_fields(previous or {}, profiles[name])) if previous is not None else set()
        differ = set(_differing_fields(profiles[name], profiles[parent]))
        previous_overrides = set(load_profile_meta(name)["overridden_fields"])
        meta_updates["overridden_fields"] = sorted((previous_overrides | changed_now) & differ)
    _stamp_profile_meta(name, **meta_updates)
    return profiles[name]


# 24.10.2026 (סיור הסטודיו, החלטה 12/13): השדות ששייכים לתיקייה מסוימת - לא נכנסים לתבנית
TEMPLATE_EXCLUDED_FIELDS = ("queue_files",)


def save_template(name: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    """"שמור את הפרויקט כתבנית": סגנון מורחב - ההגדרות, השכבות, המיתוג והיעדים (כולם כבר ב-PROFILE_FIELDS), בלי הקבצים של
    התיקייה. נשמר כסגנון רגיל ב-video_editor_profiles.json (הפורמט לא משתנה, והדסקטופ ממשיך לקרוא אותו כמו שהוא), ומסומן
    kind=template בקובץ המטא."""
    saved = save_profile(name, {k: v for k, v in settings.items() if k not in TEMPLATE_EXCLUDED_FIELDS})
    _stamp_profile_meta(name.strip(), kind="template")
    return saved


def delete_profile(name: str) -> bool:
    """מוחק פרופיל אם קיים - True אם נמחק בפועל, False אם לא היה קיים מלכתחילה
    (לא זורק - מחיקת פרופיל שכבר נמחק/מעולם לא נשמר היא no-op תקין, לא שגיאה).

    item: מחיקה רכה - הפרופיל (יחד עם ההיסטוריה והמטא-דאטה שלו) עובר לסל-
    המחזור (_trash_path) במקום להימחק לצמיתות, ואפשר לשחזר אותו משם
    (restore_from_trash). מקובצי הפרופילים/היסטוריה/מטא עצמם הוא כן מוסר - לא
    משאיר שאריות יתומות שם."""
    profiles = load_profiles()
    if name not in profiles:
        return False
    history = _load_json_dict(HISTORY_PATH)
    meta = _load_json_dict(META_PATH)
    trash = _load_trash()
    trash.append({
        "id": uuid.uuid4().hex, "name": name, "deleted_at": datetime.now(timezone.utc).isoformat(),
        "settings": profiles[name], "meta": meta.get(name) if isinstance(meta.get(name), dict) else {},
        "history": history.get(name) if isinstance(history.get(name), list) else [],
    })
    _write_json(_trash_path(), {"entries": trash})
    del profiles[name]
    _write_profiles(profiles)
    if name in history:
        del history[name]
        _write_json(HISTORY_PATH, history)
    if name in meta:
        del meta[name]
        _write_json(META_PATH, meta)
    return True


def _load_trash() -> List[Dict[str, Any]]:
    entries = _load_json_dict(_trash_path()).get("entries")
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def list_trash() -> List[Dict[str, Any]]:
    """סל-המחזור, מהנמחק-אחרון לראשון - בלי snapshot-ים ההיסטוריים המלאים
    (רק מספרם), כדי שהרשימה תישאר קלה גם עם הרבה פריטים."""
    return [
        {"id": e.get("id"), "name": e.get("name"), "deleted_at": e.get("deleted_at"),
         "codec": (e.get("settings") or {}).get("codec"), "history_count": len(e.get("history") or [])}
        for e in reversed(_load_trash())
    ]


def restore_from_trash(entry_id: str, new_name: Optional[str] = None) -> Dict[str, Any]:
    """מחזיר פרופיל מסל-המחזור (כולל היסטוריה/מטא-דאטה). ValueError אם השם
    (המקורי או new_name) כבר תפוס - שחזור לא אמור לדרוס בשקט פרופיל חי שנוצר
    בינתיים באותו שם."""
    trash = _load_trash()
    entry = next((e for e in trash if e.get("id") == entry_id), None)
    if entry is None:
        raise ValueError("הפריט לא נמצא בסל המחזור")
    name = (new_name or entry.get("name") or "").strip()
    if not name:
        raise ValueError("שם פרופיל לא יכול להיות ריק")
    profiles = load_profiles()
    if name in profiles:
        raise ValueError(f"פרופיל בשם {name!r} כבר קיים - בחר שם אחר לשחזור")
    raw_settings = entry.get("settings")
    settings: Dict[str, Any] = raw_settings if isinstance(raw_settings, dict) else {}
    profiles[name] = {field: settings.get(field) for field in PROFILE_FIELDS}
    _write_profiles(profiles)
    if entry.get("history"):
        history = _load_json_dict(HISTORY_PATH)
        history[name] = entry["history"][-MAX_HISTORY_PER_PROFILE:]
        _write_json(HISTORY_PATH, history)
    if entry.get("meta"):
        meta = _load_json_dict(META_PATH)
        meta[name] = entry["meta"]
        _write_json(META_PATH, meta)
    _write_json(_trash_path(), {"entries": [e for e in trash if e.get("id") != entry_id]})
    return {"name": name, "settings": profiles[name]}


def purge_trash_entry(entry_id: str) -> bool:
    """מחיקה סופית של פריט אחד מסל-המחזור (פעולה מפורשת של המשתמש, אחרי
    אישור בממשק). גם זו עוברת דרך _write_json - כלומר קובץ סל-המחזור הקודם
    עדיין מגובה, כך שאפילו מחיקה "סופית" ניתנת לשחזור ידני מתיקיית הגיבויים."""
    trash = _load_trash()
    remaining = [e for e in trash if e.get("id") != entry_id]
    if len(remaining) == len(trash):
        return False
    _write_json(_trash_path(), {"entries": remaining})
    return True


def rename_profile(old_name: str, new_name: str) -> Dict[str, Any]:
    """משנה שם לפרופיל קיים (item: שינוי שם לפרופיל) - בניגוד ל-save_profile
    (שדורס בשקט אם השם כבר קיים, item: עדכון פרופיל קיים), שינוי-שם *לתוך*
    שם שכבר תפוס ע"י פרופיל *אחר* הוא הרבה יותר מפתיע/מסוכן בשקט (שני
    פרופילים לא-קשורים מתמזגים לאחד בטעות) - כאן זה תמיד ValueError מוחלט,
    לא דריסה. ValueError גם אם old_name לא קיים בכלל, או ששני השמות (אחרי
    strip) ריקים/זהים."""
    old_name = (old_name or "").strip()
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("שם פרופיל חדש לא יכול להיות ריק")
    profiles = load_profiles()
    if old_name not in profiles:
        raise ValueError(f"פרופיל בשם {old_name!r} לא נמצא")
    if new_name != old_name and new_name in profiles:
        raise ValueError(f"פרופיל בשם {new_name!r} כבר קיים")
    profiles[new_name] = profiles.pop(old_name)
    _write_profiles(profiles)
    if new_name != old_name:
        history = _load_json_dict(HISTORY_PATH)
        if old_name in history:
            history[new_name] = history.pop(old_name)
            _write_json(HISTORY_PATH, history)
        meta = _load_json_dict(META_PATH)
        if old_name in meta:
            meta[new_name] = meta.pop(old_name)
        # item 68: ילדים שיורשים מהשם הישן ממשיכים לרשת מהשם החדש.
        for entry in meta.values():
            if isinstance(entry, dict) and entry.get("parent") == old_name:
                entry["parent"] = new_name
        _write_json(META_PATH, meta)
    return profiles[new_name]


def duplicate_profile(source_name: str, new_name: str) -> Dict[str, Any]:
    """שכפול פרופיל קיים לשם חדש (item: שכפול פרופיל / "שמור בשם...") - בניגוד
    ל-save_profile (דורס בשקט לפי שם), זו תמיד יצירת-עותק חדש; ValueError אם
    המקור לא קיים או השם החדש כבר תפוס. העותק מתחיל עם מטא-דאטת שימוש נקייה
    (run_count=0) - זו הרצה-אפס של הפרופיל החדש, לא המשך של המקור."""
    source_name = (source_name or "").strip()
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("שם פרופיל חדש לא יכול להיות ריק")
    profiles = load_profiles()
    if source_name not in profiles:
        raise ValueError(f"פרופיל בשם {source_name!r} לא נמצא")
    if new_name in profiles:
        raise ValueError(f"פרופיל בשם {new_name!r} כבר קיים")
    profiles[new_name] = {field: profiles[source_name].get(field) for field in PROFILE_FIELDS}
    _write_profiles(profiles)
    _stamp_profile_meta(new_name, schema_version=PROFILE_SCHEMA_VERSION, run_count=0, last_used_at=None)
    return profiles[new_name]


def export_profile(name: str) -> Dict[str, Any]:
    """snapshot נקי (רק PROFILE_FIELDS, בלי מטא-דאטת שימוש שלא רלוונטית
    למכונה/משתמש אחר) לייצוא כקובץ JSON (item: ייצוא/ייבוא פרופיל)."""
    profiles = load_profiles()
    if name not in profiles:
        raise ValueError(f"פרופיל בשם {name!r} לא נמצא")
    return {field: profiles[name].get(field) for field in PROFILE_FIELDS}


def import_profile(name: str, settings: Dict[str, Any], overwrite: bool = False) -> Dict[str, Any]:
    """מייבא פרופיל מ-JSON חיצוני (item: ייצוא/ייבוא פרופיל) - שדות לא-מוכרים
    מסוננים בדיוק כמו save_profile הרגיל. דורס פרופיל קיים באותו שם רק אם
    overwrite=True במפורש - ייבוא עיוור לא אמור לדרוס בשקט פרופיל מקומי קיים."""
    name = (name or "").strip()
    if not name:
        raise ValueError("שם פרופיל לא יכול להיות ריק")
    if name in load_profiles() and not overwrite:
        raise ValueError(f"פרופיל בשם {name!r} כבר קיים - יש לאשר דריסה")
    return save_profile(name, settings)


def diff_profiles(name_a: str, name_b: str) -> Dict[str, List[Any]]:
    """שדות שערכם שונה בין שני פרופילים שמורים (item: השוואת שני פרופילים) -
    {field: [value_a, value_b]} רק לשדות שבאמת שונים מתוך כל PROFILE_FIELDS,
    לא dump מלא של שניהם."""
    profiles = load_profiles()
    if name_a not in profiles:
        raise ValueError(f"פרופיל בשם {name_a!r} לא נמצא")
    if name_b not in profiles:
        raise ValueError(f"פרופיל בשם {name_b!r} לא נמצא")
    a, b = profiles[name_a], profiles[name_b]
    return {field: [a.get(field), b.get(field)] for field in PROFILE_FIELDS if a.get(field) != b.get(field)}


PROFILE_COLORS = ("", "red", "orange", "yellow", "green", "blue", "purple", "gray")


def _normalized_meta(meta: Any) -> Dict[str, Any]:
    meta = meta if isinstance(meta, dict) else {}
    tags = meta.get("tags")
    return {
        "schema_version": meta.get("schema_version"), "last_used_at": meta.get("last_used_at"),
        "run_count": int(meta.get("run_count") or 0),
        # גל 6 של 102-ההצעות (items 60/63/68): תגיות/צבע/הערות, ברירת-מחדל, ירושה
        "tags": [str(t) for t in tags] if isinstance(tags, list) else [],
        "color": meta.get("color") if meta.get("color") in PROFILE_COLORS else "",
        "notes": str(meta.get("notes") or ""),
        "is_default": bool(meta.get("is_default")),
        "parent": meta.get("parent") if isinstance(meta.get("parent"), str) else None,
        "overridden_fields": [f for f in (meta.get("overridden_fields") or []) if f in PROFILE_FIELDS],
        "created_at": meta.get("created_at"),
        # 24.10.2026: "template" - נשמר מ"שמור את הפרויקט כתבנית" (save_template); כל השאר, כולל מטא ישן - סגנון רגיל
        "kind": "template" if meta.get("kind") == "template" else "style",
    }


def load_profile_meta(name: str) -> Dict[str, Any]:
    """מטא-דאטת שימוש (item: חותמת "בשימוש לאחרונה" + גרסת-סכימה) - ברירת מחדל
    תקינה (לא None/שגיאה) לפרופיל שעדיין לא נשמר עם המנגנון הזה."""
    return _normalized_meta(_load_json_dict(META_PATH).get(name))


def load_all_profile_meta() -> Dict[str, Dict[str, Any]]:
    """מטא-דאטה לכל הפרופילים הקיימים בבקשה אחת (מיון/צ'יפים/תגיות בממשק -
    בלי N בקשות נפרדות). פרופיל בלי רשומת-מטא מקבל ברירות מחדל תקינות."""
    all_meta = _load_json_dict(META_PATH)
    return {name: _normalized_meta(all_meta.get(name)) for name in load_profiles()}


def annotate_profile(name: str, tags: Optional[List[str]] = None, color: Optional[str] = None, notes: Optional[str] = None) -> Dict[str, Any]:
    """item 60: תגיות/צבע/הערות לפרופיל - נשמרים במטא-דאטה, לא בהגדרות הרינדור."""
    if name not in load_profiles():
        raise ValueError(f"פרופיל בשם {name!r} לא נמצא")
    updates: Dict[str, Any] = {}
    if tags is not None:
        clean_tags = []
        for tag in tags:
            text = str(tag).strip().lstrip("#").strip()
            if text and text not in clean_tags:
                clean_tags.append(text[:30])
        updates["tags"] = clean_tags[:12]
    if color is not None:
        if color not in PROFILE_COLORS:
            raise ValueError(f"צבע לא מוכר: {color!r}")
        updates["color"] = color
    if notes is not None:
        updates["notes"] = str(notes)[:2000]
    _stamp_profile_meta(name, **updates)
    return load_profile_meta(name)


def set_default_profile(name: Optional[str]) -> None:
    """item 63: פרופיל ברירת-מחדל מפורש - לכל היותר אחד. None מבטל."""
    if name is not None and name not in load_profiles():
        raise ValueError(f"פרופיל בשם {name!r} לא נמצא")
    all_meta = _load_json_dict(META_PATH)
    for other, entry in all_meta.items():
        if isinstance(entry, dict) and entry.get("is_default") and other != name:
            entry["is_default"] = False
    if name is not None:
        raw_entry = all_meta.get(name)
        default_entry: Dict[str, Any] = raw_entry if isinstance(raw_entry, dict) else {}
        default_entry["is_default"] = True
        all_meta[name] = default_entry
    _write_json(META_PATH, all_meta)


def get_default_profile_name() -> Optional[str]:
    for name, meta in load_all_profile_meta().items():
        if meta["is_default"]:
            return name
    return None


def set_profile_field(name: str, field: str, value: Any) -> Dict[str, Any]:
    """item 65: "מזג שדה" מתצוגת ההשוואה - משנה שדה בודד בפרופיל שמור (המצב
    הקודם נדחף להיסטוריה, בדיוק כמו שמירה רגילה, כך שזה הפיך)."""
    if field not in PROFILE_FIELDS:
        raise ValueError(f"שדה לא מוכר: {field!r}")
    profiles = load_profiles()
    if name not in profiles:
        raise ValueError(f"פרופיל בשם {name!r} לא נמצא")
    updated = dict(profiles[name])
    updated[field] = value
    return save_profile(name, updated)


EXPORT_FORMAT = "clipforge-video-editor-profiles"


def export_all_profiles() -> Dict[str, Any]:
    """item 66: ייצוא כל הפרופילים (+ תגיות/צבע/הערות/ירושה) לקובץ אחד."""
    profiles = load_profiles()
    all_meta = load_all_profile_meta()
    return {
        "format": EXPORT_FORMAT, "version": 1, "exported_at": datetime.now(timezone.utc).isoformat(),
        "profiles": {name: {field: settings.get(field) for field in PROFILE_FIELDS} for name, settings in profiles.items()},
        "meta": {name: {k: all_meta[name][k] for k in ("tags", "color", "notes", "parent")} for name in profiles},
    }


def import_all_profiles(data: Dict[str, Any], strategy: str = "skip") -> Dict[str, List[str]]:
    """item 66: ייבוא קובץ של export_all_profiles. strategy לפרופיל שכבר קיים:
    "skip" (ברירת מחדל - לא נוגע), "overwrite" (דורס, הקודם נשמר בהיסטוריה),
    "rename" (נשמר בשם חדש "<שם> (מיובא)")."""
    if strategy not in ("skip", "overwrite", "rename"):
        raise ValueError(f"אסטרטגיה לא מוכרת: {strategy!r}")
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), dict):
        raise ValueError("קובץ לא תקין - חסר מפתח profiles")
    existing = load_profiles()
    result: Dict[str, List[str]] = {"imported": [], "skipped": [], "renamed": []}
    raw_meta_in = data.get("meta")
    meta_in: Dict[str, Any] = raw_meta_in if isinstance(raw_meta_in, dict) else {}
    for name, settings in data["profiles"].items():
        if not isinstance(settings, dict) or not str(name).strip():
            continue
        target = str(name).strip()
        if target in existing:
            if strategy == "skip":
                result["skipped"].append(target)
                continue
            if strategy == "rename":
                base, counter = f"{target} (מיובא)", 2
                candidate = base
                while candidate in existing:
                    candidate = f"{base} {counter}"
                    counter += 1
                result["renamed"].append(candidate)
                target = candidate
        save_profile(target, settings)
        existing[target] = settings
        raw_meta = meta_in.get(name)
        meta: Dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
        if meta:
            annotate_profile(target, tags=meta.get("tags") or [], color=meta.get("color") if meta.get("color") in PROFILE_COLORS else "", notes=meta.get("notes") or "")
        if target == str(name).strip():
            result["imported"].append(target)
    return result


# --- item 68: ירושה - "מבוסס על X, שונה ב-Y" ---

def _differing_fields(a: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    return [field for field in PROFILE_FIELDS if field not in ("favorite_fields",) and a.get(field) != b.get(field)]


def set_profile_parent(name: str, parent: Optional[str]) -> Dict[str, Any]:
    profiles = load_profiles()
    if name not in profiles:
        raise ValueError(f"פרופיל בשם {name!r} לא נמצא")
    if parent is not None:
        if parent not in profiles:
            raise ValueError(f"פרופיל-ההורה {parent!r} לא נמצא")
        if parent == name:
            raise ValueError("פרופיל לא יכול לרשת מעצמו")
        ancestor: Optional[str] = parent
        seen = set()
        while ancestor and ancestor not in seen:  # מונע מעגל ירושה (A->B->A)
            if ancestor == name:
                raise ValueError("זה היה יוצר מעגל ירושה")
            seen.add(ancestor)
            ancestor = load_profile_meta(ancestor)["parent"]
    _stamp_profile_meta(name, parent=parent)
    refresh_profile_overrides(name)
    return load_profile_meta(name)


def refresh_profile_overrides(name: str) -> List[str]:
    """מחשב ושומר אילו שדות הפרופיל "דורס" ביחס להורה שלו כרגע - נקרא אחרי כל
    שמירה של פרופיל-ילד, כדי ש"משוך שינויים מההורה" ידע מה לא לגעת בו."""
    meta = load_profile_meta(name)
    profiles = load_profiles()
    parent = meta["parent"]
    if not parent or parent not in profiles or name not in profiles:
        return []
    overridden = _differing_fields(profiles[name], profiles[parent])
    _stamp_profile_meta(name, overridden_fields=overridden)
    return overridden


def pull_from_parent(name: str) -> Dict[str, Any]:
    """מעדכן בפרופיל-הילד את כל השדות שהוא *לא* דורס לערכים הנוכחיים של ההורה
    (שינויים שנעשו בהורה מאז "זורמים" לילד), ומחזיר {settings, pulled_fields}.
    שדות שהילד דורס (overridden_fields מהשמירה האחרונה שלו) לא משתנים."""
    meta = load_profile_meta(name)
    profiles = load_profiles()
    parent = meta["parent"]
    if not parent or parent not in profiles:
        raise ValueError("לפרופיל הזה אין הורה קיים למשוך ממנו")
    child = dict(profiles[name])
    overridden = set(meta["overridden_fields"])
    pulled = []
    for field in PROFILE_FIELDS:
        if field in overridden or field in ("favorite_fields",):
            continue
        if child.get(field) != profiles[parent].get(field):
            child[field] = profiles[parent].get(field)
            pulled.append(field)
    if pulled:
        save_profile(name, child)
    return {"settings": load_profiles()[name], "pulled_fields": pulled}


def record_profile_used(name: str) -> None:
    """מעדכן last_used_at/run_count כשפרופיל בפועל משמש להרצה (item: חותמת
    "בשימוש לאחרונה" + מספר הרצות) - no-op שקט אם הפרופיל כבר לא קיים (יכול
    היה להימחק בין הבחירה בטופס לריצה עצמה)."""
    if name not in load_profiles():
        return
    current = load_profile_meta(name)
    _stamp_profile_meta(name, run_count=current["run_count"] + 1, last_used_at=datetime.now(timezone.utc).isoformat())


def get_profile_history(name: str) -> List[Dict[str, Any]]:
    """רשימת snapshot-ים קודמים לפרופיל, הישן ביותר ראשון, עד
    MAX_HISTORY_PER_PROFILE (item: היסטוריית-שינויים/undo לפרופיל) - רשימה
    ריקה אם מעולם לא נדרס/שוחזר."""
    entries = _load_json_dict(HISTORY_PATH).get(name)
    return entries if isinstance(entries, list) else []


def revert_profile(name: str, index: int) -> Dict[str, Any]:
    """משחזר פרופיל name לגרסה בהיסטוריה באינדקס index (0=הישנה ביותר השמורה,
    -1=האחרונה השמורה, לפני הדריסה הכי אחרונה) - item: היסטוריית-שינויים/undo.
    המצב הנוכחי (לפני השחזור) נדחף להיסטוריה קודם, כדי שהשחזור עצמו יהיה הפיך.
    ValueError אם הפרופיל לא קיים או שאין גרסה כזו בהיסטוריה."""
    profiles = load_profiles()
    if name not in profiles:
        raise ValueError(f"פרופיל בשם {name!r} לא נמצא")
    entries = get_profile_history(name)
    try:
        target = entries[index]
    except IndexError:
        raise ValueError("אין גרסה כזו בהיסטוריה של הפרופיל") from None
    _push_profile_history(name, profiles[name])
    profiles[name] = {field: target.get(field) for field in PROFILE_FIELDS}
    _write_profiles(profiles)
    return profiles[name]
