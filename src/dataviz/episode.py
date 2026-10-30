# dataviz/episode.py
#
# פרק = תיקייה עם config.yaml, קובצי נתונים, אירועים ומוזיקה. load_episode() קורא את
# ההגדרות ואת כל המקורות ומחזיר Episode: מטריצה יומית (יום x ישות), המצטבר שלה, מתי כל
# ישות "נכנסת" לתמונה, מי הישות הנוכחית בכל יום (שנה), ואירועים. זה כל מה שהתכנון
# (plan.py) והציור (charts/) צריכים - בלי לגעת שוב בקבצים.

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd

from dataviz.cleaning import apply_fixes
from dataviz.config import load_config
from dataviz.sources import daily_matrix, read_table, resolved_sources


@dataclass
class Episode:
    config: Dict[str, Any]
    dates: pd.DatetimeIndex
    entities: List[Any]
    daily: np.ndarray          # [יום, ישות] - כמה נוסף באותו יום
    cum: np.ndarray            # [יום, ישות] - מצטבר
    start_idx: np.ndarray      # [ישות] - היום שממנו הישות פעילה (נכנסת לדירוג)
    current: np.ndarray        # [יום] - אינדקס הישות הנוכחית (השנה של היום), -1 = אין
    events: List[Tuple[str, str, int]] = field(default_factory=list)  # (YYYY-MM-DD, תווית, אינדקס יום)
    textures: Dict[Any, str] = field(default_factory=dict)            # ישות -> stripes/solid
    legend: List[Tuple[str, str]] = field(default_factory=list)       # (תווית, stripes/solid) לפי סדר המקורות
    levels: List[Any] = field(default_factory=list)                   # 18.10.2026: ישויות ממקור kind: level
    level_fractions: bool = False                                     # 19.10.2026: יש ברמות ערך לא שלם (18.3) - ספרה עשרונית
    right_axis: List[Any] = field(default_factory=list)               # 20.10.2026: ישויות ממקור axis: right (line_race)
    shared: List[Dict[str, Any]] = field(default_factory=list)        # 23.10.2026 (ק4): ישויות שהופרדו - ישות לכל מקור

    @property
    def n_days(self) -> int:
        return len(self.dates)


def _current_mode(config: Mapping[str, Any]) -> str:
    mode = config.get("current_entity", "auto")
    if mode != "auto":
        return str(mode)
    by_year = all((s.get("entity") or {"from_time": "year"}) == {"from_time": "year"} for s in config["sources"])
    return "year" if by_year else "none"


def load_events(config: Mapping[str, Any]) -> List[Tuple[str, str]]:
    """אירועים מההגדרות (רשימה) או מקובץ CSV עם עמודות date,label - ממוינים לפי תאריך."""
    raw = config.get("events") or []
    if isinstance(raw, str):
        table = pd.read_csv(os.path.join(config["base_dir"], raw), encoding="utf-8-sig")
        table.columns = [str(c).strip().lower() for c in table.columns]   # 23.10.2026: "Date,Label" (KeyError 'date')
        items = [(str(row["date"]), str(row["label"])) for _, row in table.iterrows()]
    else:
        items = [(str(e["date"]), str(e["label"])) for e in raw]
    return sorted((pd.Timestamp(d).strftime("%Y-%m-%d"), label) for d, label in items)


def build_episode(config: Dict[str, Any]) -> Episode:
    base_dir = config["base_dir"]
    specs = resolved_sources(config)   # גל 52: מקור מכתובת נקרא מהעותק שהורד
    data = config.get("data") or {}
    tables = [read_table(spec, base_dir, str(data.get("missing") or "zero")) for spec in specs]
    timeline = config.get("timeline") or {}
    matrix, origins = daily_matrix(tables, specs, base_dir, timeline.get("start") or None, timeline.get("end") or None,
                                   missing=str(data.get("missing") or "zero"))
    shared = list(matrix.attrs.get("shared") or [])   # ק4: לאזהרה ב"לפני רינדור"
    matrix, origins = apply_entity_rules(matrix, origins, config.get("entities") or {})
    matrix = apply_fixes(matrix, data.get("fixes") or [])   # גל 52: תיקוני קפיצות חשודות
    values = config.get("values") or {}
    if (values.get("per_capita") or {}).get("enabled"):
        matrix = per_capita(matrix, values["per_capita"], base_dir)
    dates = pd.DatetimeIndex(matrix.index)
    entities = [e.item() if hasattr(e, "item") else e for e in matrix.columns]   # np.int64 -> int
    daily = matrix.to_numpy(dtype=float)
    total = matrix.cumsum().to_numpy(dtype=float)
    levels = [e for e in entities if e in origins and specs[origins[e]].get("kind") == "level"]   # 18.10.2026
    cum = shown_values(matrix, values, total, [e in levels for e in entities])
    right_axis = [e for e in entities if e in origins and specs[origins[e]].get("axis") == "right"]   # 20.10.2026
    mode = _current_mode(config)
    if mode == "year" and not all(isinstance(e, int) for e in entities):
        mode = "none"   # גל 39: שם חלופי שאינו שנה - אין "השנה הנוכחית"
    if mode == "year":
        # ישות-שנה פעילה מה-1 בינואר שלה (גם אם עוד לא נוסף לה כלום - מופיעה כשהשנה מתחילה)
        start_idx = np.array([int(np.searchsorted(dates.values, np.datetime64(f"{int(e)}-01-01"))) for e in entities])
        column = {e: i for i, e in enumerate(entities)}
        current = np.array([column.get(int(y), -1) for y in dates.year])
    else:
        # מתי ישות נכנסת לתמונה - מהיום הראשון שבו נוסף לה משהו (גם בחלון מתגלגל, שם הערך יכול לחזור לאפס). 23.10.2026:
        # קודם total > 0 - ישות שהסכום שלה שלילי לא נכנסה למרוץ בכלל והופיעה רק בסיום
        nonzero = np.cumsum(daily != 0, axis=0) > 0
        first_days = _level_first_days(tables, specs, levels)
        for c, e in enumerate(entities):
            if e in first_days:   # 19.10.2026: רמה נכנסת ביום הראשון שלה במקור - גם כשהערך הראשון 0 (אין "תוספת" שתסמן אותו)
                nonzero[:, c] = dates >= first_days[e]
            elif e in levels:     # 18.10.2026: רמה נכנסת ביום הראשון שלה, גם כשהערך שלילי
                nonzero[:, c] = np.cumsum(daily[:, c] != 0) > 0
        start_idx = np.where(nonzero.any(axis=0), nonzero.argmax(axis=0), len(dates))
        current = np.full(len(dates), -1)

    events = []
    for date, label in load_events(config):
        if dates[0] <= pd.Timestamp(date) <= dates[-1]:
            events.append((date, label, int(np.searchsorted(dates.values, np.datetime64(date)))))

    textures = {e: str(specs[origins[e]].get("texture") or "solid") for e in entities}
    legend = [(str(s["legend"]), str(s.get("texture") or "solid")) for s in specs if s.get("legend")]
    level_values = [t["value"].to_numpy(dtype=float) for t, spec in zip(tables, specs) if spec.get("kind") == "level"]
    fractions = any(bool((np.abs(v - np.round(v)) > 1e-9).any()) for v in level_values)
    return Episode(config=config, dates=dates, entities=entities, daily=daily, cum=cum, start_idx=start_idx,
                   current=current, events=events, textures=textures, legend=legend, levels=levels, level_fractions=fractions,
                   right_axis=right_axis, shared=shared)


def _level_first_days(tables: Sequence[pd.DataFrame], specs: Sequence[Mapping[str, Any]], levels: List[Any]) -> Dict[Any, pd.Timestamp]:
    """19.10.2026: היום הראשון של כל ישות-רמה במקור שלה (תחילת התקופה הראשונה, כמו ב-_level_daily). ישות ששמה השתנה
    בדרך (שם חלופי, מיזוג) לא כאן - והכניסה שלה לפי הערך כמו קודם."""
    from dataviz.sources import _plain
    first: Dict[Any, pd.Timestamp] = {}
    for table, spec in zip(tables, specs):
        if spec.get("kind") != "level" or not len(table):
            continue
        for entity, when in table.groupby("entity", sort=False)["time"].min().items():
            key = _plain(entity)
            if key in levels:
                first[key] = min(first.get(key, pd.Timestamp(when)), pd.Timestamp(when))
    return first


def apply_entity_rules(matrix: pd.DataFrame, origins: Dict[Any, int], rules: Mapping[str, Any]) -> Tuple[pd.DataFrame, Dict[Any, int]]:
    """גל 39: ישויות שלא מוצגות (exclude) ושמות חלופיים (aliases). שתי ישויות עם אותו שם חלופי
    מתמזגות - העמודות מסתכמות. השוואה לפי השם כטקסט (2020 ו-"2020" זה אותו דבר). בלי כללים - בלי שינוי."""
    exclude = {str(e) for e in rules.get("exclude") or []}
    aliases = {str(k): str(v).strip() for k, v in (rules.get("aliases") or {}).items() if str(v).strip()}
    if not exclude and not aliases:
        return matrix, origins
    keep = [e for e in matrix.columns if str(e) not in exclude]
    matrix = matrix[keep]
    if aliases:
        # 23.10.2026: שם חלופי מספרי ("2020") לישות טקסט, כשיש כבר ישות-שנה 2020 - מספר, כדי שיתמזגו (קודם: שתי ישויות)
        numeric = any(isinstance(e, int) for e in matrix.columns)

        def renamed(entity: Any) -> Any:
            target = aliases.get(str(entity))
            if target is None:
                return entity
            return int(target) if (isinstance(entity, int) or numeric) and target.lstrip("-").isdigit() else target
        names = [renamed(e) for e in matrix.columns]
        new_origins: Dict[Any, int] = {}
        for old, new in zip(matrix.columns, names):
            if old in origins:
                new_origins.setdefault(new, origins[old])
        matrix = matrix.T.groupby(names, sort=False).sum().T
        ordered = sorted(matrix.columns, key=lambda e: (isinstance(e, str), str(e) if isinstance(e, str) else e))
        matrix = matrix[ordered]
        origins = new_origins
    else:
        origins = {e: i for e, i in origins.items() if str(e) not in exclude}
    if matrix.shape[1] == 0:
        raise ValueError("כל הישויות הוחרגו - אין מה להציג.")
    return matrix, origins


def shown_values(matrix: pd.DataFrame, values: Mapping[str, Any], total: np.ndarray, levels: Sequence[bool] = ()) -> np.ndarray:
    """גל 49: הערך שכל תרשים מציג בכל יום - המצטבר (ברירת המחדל), או סכום window_days הימים האחרונים.
    23.10.2026: עמודת רמה (levels[c]) מציגה תמיד את הרמה - סכום מתגלגל של שינויי רמה הציג 0 לקו קבוע."""
    if values.get("mode") != "rolling":
        return total
    rolling = matrix.rolling(int(values.get("window_days") or 30), min_periods=1).sum().to_numpy(dtype=float, copy=True)
    rolling[np.abs(rolling) < 1e-9] = 0.0     # שאריות של חיבור וחיסור עשרוני - לא "ערך" קטן מאוד
    mask = np.array(list(levels), dtype=bool)
    if mask.any():
        rolling[:, mask] = total[:, mask]
    return rolling


def load_populations(settings: Mapping[str, Any], base_dir: str) -> Dict[str, float]:
    """ישות (כטקסט) -> אוכלוסייה: מקובץ CSV (העמודות entity,population, או שתי העמודות הראשונות) ומ-populations."""
    result: Dict[str, float] = {}
    if settings.get("file"):
        table = pd.read_csv(os.path.join(base_dir, str(settings["file"])), encoding="utf-8")
        columns = ["entity", "population"] if {"entity", "population"} <= set(table.columns) else list(table.columns[:2])
        if len(columns) < 2:
            raise ValueError("קובץ האוכלוסייה צריך שתי עמודות: ישות ואוכלוסייה.")
        for name, population in zip(table[columns[0]], pd.to_numeric(table[columns[1]], errors="coerce")):
            if pd.notna(population) and population > 0:
                result[str(name).strip()] = float(population)
    result.update({str(k): float(v) for k, v in (settings.get("populations") or {}).items()})
    return result


def per_capita(matrix: pd.DataFrame, settings: Mapping[str, Any], base_dir: str) -> pd.DataFrame:
    """גל 49: כל עמודה מחולקת באוכלוסייה של הישות, כפול per (למשל ל-100,000 תושבים). ישות בלי אוכלוסייה
    לא מוצגת - אי אפשר להשוות אותה."""
    populations = load_populations(settings, base_dir)
    keep = [e for e in matrix.columns if populations.get(str(e), 0) > 0]
    if not keep:
        raise ValueError("מצב לנפש: לאף ישות אין אוכלוסייה בקובץ - השמות צריכים להיות זהים לשמות הישויות.")
    per = float(settings.get("per") or 100000)
    return matrix[keep] / pd.Series({e: populations[str(e)] / per for e in keep})


def load_episode(path: str, overrides: Mapping[str, Any] | None = None) -> Episode:
    """path = תיקיית הפרק או קובץ config.yaml שלו."""
    config_path = path if os.path.isfile(path) else os.path.join(path, "config.yaml")
    return build_episode(load_config(config_path, overrides))
