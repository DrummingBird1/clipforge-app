# utils/media/auto_chain.py
#
# גל 32: שרשור מלא מ-OBS (או מתיקיית לכידה) ועד פרסום. המאזין מעתיק קליפ ל-Import ומדפיס
# שורת אירוע (clip_ready_line למטה, worker.py's EVENT:); השרת מחליט כאן מה לעשות איתו לפי
# rocket_settings.json - לערוך בסגנון שמור, לערוך ואז לפרסם, או לפרסם ישר ב-Rocket Shorts -
# ומבצע ב-web_app.py דרך אותו תור רינדור של כל ריצה אחרת. לוגיקה טהורה, בלי worker/שרת.

import json
import os

from utils.media.timelapse import VIDEO_EXTENSIONS

MODES = ("off", "edit", "edit_publish", "publish")

# רק המאזינים האלה מפעילים שרשור - שורת EVENT מסקריפט אחר לא מריצה כלום בטעות
SOURCE_SCRIPTS = ("super_streamer.py", "obs_replay_watcher.py", "capture_folder_watcher.py")

# שדות של ריצה/קובץ מסוימים (ושל קובץ הסגנונות), לא של הסגנון - לא נלקחים לקליפ חדש
_RUN_ONLY_KEYS = (
    "schema_version", "only_files", "clip_edits", "batch_overrides", "concat_mode", "concat_files", "queue_files",
    "ve_profile_name", "finish_actions", "publish_after", "publish_dry_run", "priority", "run_label",
)


def clip_ready_line(path, source):
    """השורה שמאזין מדפיס אחרי שהעתיק קליפ ל-Import (source: "obs"/"folder")."""
    return "EVENT: " + json.dumps({"type": "clip_ready", "path": os.path.abspath(path), "source": source}, ensure_ascii=False)


def settings_from(rocket_settings):
    raw = rocket_settings if isinstance(rocket_settings, dict) else {}
    mode = raw.get("auto_chain")
    return {
        "mode": mode if mode in MODES else "off",
        "profile": str(raw.get("auto_chain_profile") or "").strip(),
        "dry_run": bool(raw.get("auto_chain_dry_run")),
    }


def plan(rocket_settings, clip_path, profiles):
    """מה לעשות עם קליפ שנכנס. {"action": "edit"|"publish", ...}, או {"action": None, "reason": ...}
    (off - ההתנהגות הקודמת, רק העתקה; missing - אין קובץ וידאו; no_style - הסגנון לא נמצא)."""
    cfg = settings_from(rocket_settings)
    clip_path = str(clip_path or "")
    name = os.path.basename(clip_path)
    if cfg["mode"] == "off":
        return {"action": None, "reason": "off"}
    if not os.path.isfile(clip_path) or os.path.splitext(name)[1].lower() not in VIDEO_EXTENSIONS:
        return {"action": None, "reason": "missing"}
    if cfg["mode"] == "publish":
        return {"action": "publish", "clip": clip_path, "dry_run": cfg["dry_run"]}
    style = (profiles or {}).get(cfg["profile"]) if cfg["profile"] else None
    if not isinstance(style, dict):
        return {"action": None, "reason": "no_style", "profile": cfg["profile"]}
    publish = cfg["mode"] == "edit_publish"
    payload = {key: value for key, value in style.items() if key not in _RUN_ONLY_KEYS}
    payload.update({
        "only_files": [name],
        "ve_profile_name": cfg["profile"],
        "publish_after": publish,
        "publish_dry_run": cfg["dry_run"],
        "run_label": f"📼 {name}",
    })
    return {"action": "edit", "clip": clip_path, "folder": os.path.dirname(clip_path), "payload": payload,
            "profile": cfg["profile"], "publish": publish, "dry_run": cfg["dry_run"]}


def describe(plan_result, name):
    """שורה אחת למשתמש (לוג + "מה קרה לאחרונים" בהגדרות)."""
    dry = " (סימולציה, בלי העלאה)" if plan_result.get("dry_run") else ""
    if plan_result.get("action") == "publish":
        return f"{name} נשלח ישר לפרסום Shorts{dry}"
    if plan_result.get("action") == "edit":
        then = f" ואז לפרסום{dry}" if plan_result.get("publish") else ""
        return f"{name} נכנס לתור - עריכה בסגנון \"{plan_result['profile']}\"{then}"
    if plan_result.get("reason") == "no_style":
        wanted = plan_result.get("profile")
        return f"{name} נכנס, אבל " + (f"הסגנון \"{wanted}\" לא נמצא" if wanted else "לא נבחר סגנון") + " - לא נערך. בחר סגנון בהגדרות Rocket"
    return ""
