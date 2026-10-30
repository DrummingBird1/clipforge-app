# utils/video/editor_errors.py
#
# גל 14 - שגיאות עם פתרון בלחיצה: סיבת כשל גולמית (מה-run manifest, מהתצוגה
# המקדימה או מהבדיקה - לרוב זנב stderr של ffmpeg או הודעת [ERROR] של הרנדרר)
# מתורגמת להסבר אנושי קצר ולפעולות מוכרות שהממשק יודע לבצע:
#   retry        - הרץ שוב רק את הקובץ/הקבצים שנכשלו
#   retry_cpu    - הרץ שוב בלי GPU (H.264, בלי --hwaccel/--hwaccel-decode)
#   retry_serial - הרץ שוב בלי קידוד מקבילי
#   skip         - הוצא את הקובץ מהתור
#   clear_field  - אפס שדה מסוים (field) - LUT/גופן/לוגו/אודיו חסרים
#   validate     - הרץ "🧪 בדוק הגדרות"
#   open_folder  - פתח את תיקיית הפלט (דיסק מלא/הרשאות)
# טהור (בלי I/O) - נבדק ישירות.

import re
from typing import Any, Dict, List, Optional

_RULES: List[Dict[str, Any]] = [
    {
        "id": "nvenc_busy",
        "match": [r"OpenEncodeSessionEx failed", r"incompatible client key", r"out of memory.*nvenc", r"No capable devices found",
                  r"Cannot load nvcuda", r"session limit", r"nvenc.*(busy|unavailable)"],
        "title": "כרטיס המסך לא זמין לקידוד",
        "detail": "ה-GPU תפוס (OBS/משחק/קידוד מקבילי אחר) או הגיע למגבלת הקידודים המקבילים של NVENC.",
        "actions": ["retry_serial", "retry_cpu", "retry"],
    },
    {
        "id": "cuda_filter",
        "match": [r"hwupload_cuda|scale_cuda|transpose_cuda|bwdif_cuda|overlay_cuda", r"Impossible to convert between the formats.*cuda",
                  r"cuda.*(error|failed)"],
        "title": "שלב GPU בשרשרת נכשל",
        "detail": "שילוב הפילטרים לא עבר על ה-GPU בקובץ הזה (לרוב מקור 10-bit או פורמט פיקסלים חריג).",
        "actions": ["retry_cpu", "validate"],
    },
    {
        "id": "disk_full",
        "match": [r"No space left on device", r"There is not enough space on the disk", r"WinError 112", r"disk full"],
        "title": "הדיסק מלא",
        "detail": "אין מספיק מקום בכונן של תיקיית הפלט.",
        "actions": ["open_folder", "retry"],
    },
    {
        "id": "file_locked",
        "match": [r"Permission denied", r"WinError 32", r"being used by another process", r"Access is denied"],
        "title": "הקובץ נעול או חסום",
        "detail": "תוכנה אחרת מחזיקה את הקובץ (נגן, OBS, סנכרון ענן) או שאין הרשאת כתיבה לתיקייה.",
        "actions": ["retry", "skip", "open_folder"],
    },
    {
        "id": "missing_input",
        "match": [r"No such file or directory", r"does not exist", r"לא נמצא", r"FileNotFoundError"],
        "title": "קובץ חסר",
        "detail": "קובץ שהריצה צריכה (המקור, לוגו, LUT, אודיו חלופי או PiP) לא נמצא בנתיב שהוגדר.",
        "actions": ["skip", "validate"],
    },
    {
        "id": "bad_lut",
        "match": [r"lut3d", r"\.cube", r"Invalid LUT"],
        "title": "קובץ ה-LUT לא תקין",
        "detail": "ffmpeg לא הצליח לקרוא את קובץ ה-LUT (.cube) שנבחר.",
        "actions": ["clear_field:lut_path", "retry"],
    },
    {
        "id": "font",
        "match": [r"Cannot find a valid font", r"fontconfig", r"Could not load font"],
        "title": "גופן לא נמצא",
        "detail": "הגופן שנבחר לטקסט/כתוביות לא מותקן במחשב.",
        "actions": ["clear_field:caption_font", "retry"],
    },
    {
        "id": "corrupt_input",
        "match": [r"Invalid data found when processing input", r"moov atom not found", r"End of file", r"corrupt", r"Error while decoding"],
        "title": "קובץ המקור פגום או לא הושלם",
        "detail": "הקובץ לא נקרא עד הסוף - לרוב הקלטה שנקטעה או קובץ שעוד מועתק.",
        "actions": ["skip", "retry"],
    },
    {
        "id": "no_audio",
        "match": [r"matches no streams", r"Stream specifier ':a", r"does not contain any stream", r"Output file #0 does not contain any stream"],
        "title": "אין פס-קול בקובץ",
        "detail": "ההגדרות מבקשות שמע (שמירת אודיו/נרמול/כתוביות) אבל לקובץ הזה אין ערוץ שמע.",
        "actions": ["clear_field:keep_audio", "retry"],
    },
    {
        "id": "filter_graph",
        "match": [r"Error initializing complex filters", r"Invalid argument", r"Error reinitializing filters", r"Failed to configure output pad",
                  r"Error parsing a filter description"],
        "title": "שילוב הגדרות שלא עובד יחד",
        "detail": "ffmpeg דחה את שרשרת הפילטרים שנבנתה מההגדרות - הבדיקה תסמן איזה שדה אחראי.",
        "actions": ["validate", "retry_cpu"],
    },
    {
        "id": "trim_empty",
        "match": [r"טווח החיתוך לא משאיר תוכן", r"trim.*(empty|no content)"],
        "title": "החיתוך לא משאיר כלום",
        "detail": "התחלת החיתוך/הטווחים שהוסרו מכסים את כל הקובץ.",
        "actions": ["clear_field:trim_start", "skip"],
    },
    {
        "id": "cancelled",
        "match": [r"cancelled", r"בוטל"],
        "title": "בוטל",
        "detail": "הקובץ בוטל ידנית בזמן הריצה.",
        "actions": ["retry"],
    },
]

ACTION_LABELS: Dict[str, str] = {
    "retry": "🔁 נסה שוב",
    "retry_cpu": "🖥️ נסה שוב בלי GPU",
    "retry_serial": "⏭️ נסה שוב בלי מקבילות",
    "skip": "🚫 הוצא מהתור",
    "validate": "🧪 בדוק הגדרות",
    "open_folder": "📂 פתח את תיקיית הפלט",
}
FIELD_LABELS: Dict[str, str] = {
    "lut_path": "LUT", "caption_font": "גופן הכתוביות", "keep_audio": "שמירת אודיו", "trim_start": "החיתוך",
}


def _action(action_id: str) -> Dict[str, str]:
    if action_id.startswith("clear_field:"):
        field = action_id.split(":", 1)[1]
        return {"id": "clear_field", "field": field, "label": f"↺ אפס את {FIELD_LABELS.get(field, field)}"}
    return {"id": action_id, "label": ACTION_LABELS.get(action_id, action_id)}


def explain_error(reason: Optional[str]) -> Dict[str, Any]:
    """{id, title, detail, actions:[{id, label, field?}], raw} - תמיד מחזיר משהו:
    סיבה לא מוכרת מקבלת הסבר כללי + "נסה שוב" + "בדוק הגדרות"."""
    text = str(reason or "")
    for rule in _RULES:
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in rule["match"]):
            return {"id": rule["id"], "title": rule["title"], "detail": rule["detail"], "actions": [_action(a) for a in rule["actions"]], "raw": text[-400:]}
    return {"id": "unknown", "title": "הרינדור נכשל", "detail": "הסיבה לא זוהתה אוטומטית - הפירוט הטכני למטה.",
            "actions": [_action("retry"), _action("validate")], "raw": text[-400:]}


def annotate_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """מוסיף explanation לכל קובץ שנכשל/בוטל ב-run manifest (לפאנל התוצאות)."""
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if isinstance(files, list):
        for row in files:
            if isinstance(row, dict) and row.get("status") in ("error", "cancelled"):
                reason = row.get("reason") or ("cancelled" if row.get("status") == "cancelled" else "")
                row["explanation"] = explain_error(reason)
    return manifest
