# dataviz/themes/__init__.py
#
# ערכות עיצוב: צבעי רקע/טקסט/רשת/הדגשה, פלטה סדורה (ישויות עם סדר טבעי - שנים: בהיר=ישן,
# כהה=חדש) ופלטה קטגורית (ישויות בלי סדר - מדינות, ערים), וגופנים. Segoe UI ראשון כי
# הוא מציג עברית היטב ב-Windows; matplotlib 3.11 מטפל בכיוון RTL בעצמו, אז אין כאן
# bidi.get_display (הוא היה הופך את הטקסט פעם שנייה).

import functools
from dataclasses import dataclass, field, fields, replace
from typing import Any, Dict, List, Mapping, Sequence, Tuple


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    ink: str
    muted: str
    grid: str
    accent: str
    # רקע כרטיס אירוע/תיבת סיום, וצבע טקסט על רקע ההדגשה (התראת "שיא חדש") או על מילוי בהיר
    card: str
    on_accent: str
    on_light: str
    ordinal: Tuple[str, ...]
    categorical: Tuple[str, ...]
    # גוון הדוגמית במקרא (מיקום על הפלטה הסדורה, 0-1)
    swatch_shade: float = 0.4
    # מרקם פסים (נתונים ברמת דיוק אחרת) - צבע הקווים ושקיפותם
    hatch_rgb: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    hatch_alpha: float = 0.5
    fonts: Tuple[str, ...] = ("Segoe UI", "Arial", "Tahoma", "DejaVu Sans")
    rc: Dict[str, Any] = field(default_factory=lambda: {"axes.unicode_minus": False, "hatch.linewidth": 1.1})


LIGHT = Theme(
    name="light",
    bg="#fbfaf6",
    ink="#1f2933",
    muted="#6b7280",
    grid="#e7e4da",
    accent="#d1495b",
    card="white",
    on_accent="white",
    on_light="#1f2933",
    ordinal=("#bcd0e6", "#7aa0c9", "#3f6a9e", "#1d3a63"),
    categorical=("#3f6a9e", "#e0a458", "#5b9279", "#9a6fb0", "#c06c84", "#4f8fba", "#8c8c3e", "#d9895b", "#6d7fcc", "#7a9e9f"),
)

DARK = Theme(
    name="dark",
    bg="#14171c",
    ink="#e8eaed",
    muted="#9aa3ad",
    grid="#2a3038",
    accent="#ef5b6c",
    card="#1d2228",
    on_accent="white",
    on_light="#14171c",
    # בכהה ההיגיון מתהפך: ישן=כהה (נבלע ברקע), חדש=בהיר
    ordinal=("#2c4566", "#3f6a9e", "#7aa0c9", "#cfe0f2"),
    categorical=("#7aa0c9", "#f0b46a", "#7cc29c", "#c39be0", "#e88aa6", "#6fb3e0", "#c9c96a", "#f2a37a", "#97a6f0", "#9cc7c8"),
    hatch_rgb=(0.0, 0.0, 0.0),
    hatch_alpha=0.45,
)

THEMES: Dict[str, Theme] = {LIGHT.name: LIGHT, DARK.name: DARK}
_COLOR_FIELDS = {"bg", "ink", "muted", "grid", "accent", "card", "on_accent", "on_light"}


def get_theme(name: str = "light", overrides: Mapping[str, Any] | None = None) -> Theme:
    """ערכה לפי שם, עם דריסות מההגדרות (צבע בודד או פלטה). שם לא מוכר -> ValueError."""
    if name not in THEMES:
        raise ValueError(f"ערכת עיצוב לא מוכרת: {name!r} (קיימות: {', '.join(sorted(THEMES))})")
    theme = THEMES[name]
    if not overrides:
        return theme
    known = {f.name for f in fields(Theme)}
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise ValueError(f"שדות עיצוב לא מוכרים: {', '.join(unknown)}")
    clean: Dict[str, Any] = {}
    for key, value in overrides.items():
        if key in ("ordinal", "categorical", "fonts"):
            clean[key] = tuple(str(v) for v in _as_list(value))
        elif key == "hatch_rgb":
            clean[key] = tuple(float(v) for v in _as_list(value))
        elif key in ("swatch_shade", "hatch_alpha"):
            clean[key] = float(value)
        elif key in _COLOR_FIELDS:
            clean[key] = str(value)
        else:
            clean[key] = value
    return replace(theme, **clean)


def theme_to_dict(theme: Theme) -> Dict[str, Any]:
    """לשליחה לתהליכי הרינדור (spawn) - dict פשוט במקום להסתמך על pickle של dataclass."""
    return {f.name: getattr(theme, f.name) for f in fields(Theme)}


def theme_from_dict(data: Mapping[str, Any]) -> Theme:
    return Theme(**dict(data))


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


# 25.10.2026: אימוג'י בשם ישות ("USA 🇺🇸", "⚽") יצא ריבועים ריקים - אין אותו באף גופן של הערכות. גופן האימוג'י
# של Windows בסוף הרשימה: matplotlib משלים ממנו רק תווים שחסרים בכל השאר (דגל - שתי האותיות שלו, "US"; ⚽ - הסמל)
EMOJI_FONT = "Segoe UI Emoji"


@functools.lru_cache(maxsize=1)
def _emoji_font_installed() -> bool:
    from matplotlib import font_manager
    return any(f.name == EMOJI_FONT for f in font_manager.fontManager.ttflist)


def apply_rc(theme: Theme, rc_params: Any) -> None:
    """מחיל גופנים והגדרות rc על matplotlib.rcParams (בכל תהליך רינדור מחדש)."""
    fonts = list(theme.fonts)
    if EMOJI_FONT not in fonts and _emoji_font_installed():
        fonts.append(EMOJI_FONT)
    rc_params["font.sans-serif"] = fonts
    for key, value in theme.rc.items():
        rc_params[key] = value


def palette_positions(entities: Sequence[Any]) -> Dict[Any, float]:
    """מיקום כל ישות על הפלטה הסדורה (0-1). מספרים (שנים) - לפי הערך עצמו, כך ששנה חסרה
    לא מזיזה את הצבעים של השאר; אחרת - לפי הסדר ברשימה."""
    if not entities:
        return {}
    if all(isinstance(e, (int, float)) and not isinstance(e, bool) for e in entities):
        lo, hi = min(entities), max(entities)
        span = (hi - lo) or 1
        return {e: (e - lo) / span for e in entities}
    span = max(len(entities) - 1, 1)
    return {e: i / span for i, e in enumerate(entities)}
