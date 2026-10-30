# utils/video/video_editor_settings.py
#
# גל 37, שלב 1 של "process_video לאובייקט הגדרות": my_scripts/video/video_editor.py מחזיק כ-150
# הגדרות כמשתנים גלובליים (כל אחד נגזר מ-args בשורה משלו), ו-process_video קורא אותם ישירות.
# כאן יש אובייקט אחד, קבוע (immutable), עם כל ההגדרות של ריצה לפי ה-dest של הדגל, ו-with_overrides
# לדריסות של קובץ אחד (עריכת קליפ) - בלי לגעת בגלובלים המשותפים (בטוח גם תחת --parallel).
# הסקריפט בונה אותו (SETTINGS) ליד args. גל 48 (שלב 2): process_video קורא את הערכים הנגזרים מהדגלים
# מ-RenderConfig (בסקריפט, עם SETTINGS בתוכו) ולא מהגלובלים - ונבדק מול "פקודות זהב" (tests/studio/test_video_editor_golden.py).

import argparse
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional

from utils.video.video_editor_cli import build_parser


class VideoEditorSettings(Mapping[str, Any]):
    """ההגדרות של ריצה אחת, לפי שם ה-dest של כל דגל (watermark_path, nvenc_cq, ...)."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, Any]):
        object.__setattr__(self, "_values", dict(values))

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "VideoEditorSettings":
        return cls(vars(args))

    @classmethod
    def from_argv(cls, argv: Optional[Iterable[str]] = None) -> "VideoEditorSettings":
        return cls.from_args(build_parser().parse_args(list(argv or [])))

    def __getattr__(self, name: str) -> Any:
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("VideoEditorSettings is read-only - use with_overrides()")

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def with_overrides(self, overrides: Optional[Mapping[str, Any]]) -> "VideoEditorSettings":
        """עותק עם הדריסות של קובץ אחד. מפתח שאינו הגדרה מוכרת לא נכנס (לא מתווספים שדות בטעות)."""
        merged = dict(self._values)
        for key, value in (overrides or {}).items():
            if key in merged:
                merged[key] = value
        return VideoEditorSettings(merged)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._values)

    def __repr__(self) -> str:
        return f"VideoEditorSettings({len(self._values)} settings)"
