# utils/video/editor_field_schema.py
#
# גל 37: סכימת שדות אחת לעורך-העל. עד עכשיו כל שדה הוגדר בכמה מקומות: הדגל ב-CLI
# (utils/video/video_editor_cli.py), האזור והתלויות (utils/video/editor_model.py), המונח וההסבר
# (utils/video/video_editor_field_help.py), השמירה בסגנון (PROFILE_FIELDS) והרישום בממשק (JS).
# כאן הם מתאחדים לרשומה אחת לכל שדה: אזור, דגל, טיפוס, ברירת מחדל, אפשרויות, מונח, הסבר והאם
# נשמר בסגנון. הממשק קורא אותה מ-GET /api/video_editor/field_schema (הדגל לקישור לתיעוד,
# ההסבר לשדות בלי tooltip), ו-tests/studio/test_editor_field_schema.py בודק שכל שדה שרשום בממשק
# קיים כאן - כך ששדה חדש שנשכח באחד המקומות נתפס בטסט ולא בריצה.

import argparse
from functools import lru_cache
from typing import Any, Dict, List, Optional

from utils.video.editor_model import field_area
from utils.video.video_editor_cli import build_parser
from utils.video.video_editor_field_help import FIELD_HELP
from utils.video.video_editor_profiles import PROFILE_FIELDS


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _cli_type(action: argparse.Action) -> str:
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return "bool"
    kind = getattr(action.type, "__name__", None)
    return {"str": "str", "int": "int", "float": "float"}.get(kind or "", "str")


def cli_fields() -> Dict[str, Dict[str, Any]]:
    """כל דגל ב-parser של video_editor.py לפי ה-dest שלו: הדגלים, טיפוס, ברירת מחדל ואפשרויות."""
    fields: Dict[str, Dict[str, Any]] = {}
    for action in build_parser()._actions:
        if isinstance(action, argparse._HelpAction) or not action.option_strings:
            continue
        fields[action.dest] = {
            "flags": list(action.option_strings),
            "type": _cli_type(action),
            "default": _json_safe(action.default),
            "choices": _json_safe(list(action.choices)) if action.choices else None,
        }
    return fields


# שדה בממשק שהדגל שלו נקרא אחרת (הבונה ב-entrypoints/web/script_args.py מתרגם ביניהם)
CLI_DEST_ALIASES = {"lut_path": "lut", "replace_audio_path": "replace_audio", "concat_mode": "concat_files", "include_subfolders": "no_subfolders"}


@lru_cache(maxsize=1)
def field_schema() -> Dict[str, Dict[str, Any]]:
    """רשומה אחת לכל שדה שמופיע באחד המקורות (CLI, הסבר, סגנון)."""
    cli = cli_fields()
    profile = set(PROFILE_FIELDS)
    aliased = set(CLI_DEST_ALIASES.values())
    keys = sorted((set(cli) - aliased) | set(FIELD_HELP) | profile | set(CLI_DEST_ALIASES))
    schema: Dict[str, Dict[str, Any]] = {}
    for key in keys:
        flag_info = cli.get(CLI_DEST_ALIASES.get(key, key))
        help_entry = FIELD_HELP.get(key)
        schema[key] = {
            "area": field_area(key),
            "flag": flag_info["flags"][0] if flag_info else None,
            "flags": flag_info["flags"] if flag_info else [],
            "type": flag_info["type"] if flag_info else None,
            "default": flag_info["default"] if flag_info else None,
            "choices": flag_info["choices"] if flag_info else None,
            "term": help_entry.term if help_entry else None,
            "help": help_entry.tooltip if help_entry else None,
            "profile": key in profile,
        }
    return schema


def field_flag(key: str) -> Optional[str]:
    entry = field_schema().get(key)
    return entry["flag"] if entry else None


def fields_missing(keys: List[str]) -> List[str]:
    """המפתחות (למשל מהרישום בממשק) שאין להם רשומה בסכימה."""
    schema = field_schema()
    return sorted(key for key in keys if key not in schema)
