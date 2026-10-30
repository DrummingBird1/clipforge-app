# dataviz/shorts.py
#
# גל 55: Shorts אוטומטיים - הרגעים הדרמטיים של הפרק (הקפיצה הגדולה ביחס למה שכבר על המסך, ויום שבו המוביל
# מתחלף) כסרטונים קצרים לאורך: פתיח קצר, shorts.seconds שניות סביב הרגע (הוא ב-40% מהקטע, כך שרואים מה הוביל
# אליו), ופריים אחרון קפוא עם הזמנה לסרטון המלא (shorts.cta). הכל מאותה תכנית של הסרטון המלא - בגודל לאורך.

from typing import Any, Dict, List, Mapping, Sequence

import numpy as np

from dataviz.plan import plan_intro

Frame = Dict[str, Any]
LEAD_CHANGE_BONUS = 0.5


def dramatic_days(episode: Any, count: int = 3) -> List[int]:
    """הימים הדרמטיים, מהחזק לחלש: קפיצה יחסית לגובה הציר באותו יום, ובונוס ליום שבו המוביל מתחלף. ימים קרובים
    מדי לרגע שכבר נבחר (פחות מעשירית מהפרק חלקי count) לא נבחרים - כל Short מספר משהו אחר."""
    daily, cum = np.asarray(episode.daily, dtype=float), np.asarray(episode.cum, dtype=float)
    if not len(daily):
        return []
    axis = np.maximum(np.maximum.accumulate(cum.max(axis=1)), 1.0)
    score = daily.max(axis=1) / axis
    leaders = cum.argmax(axis=1)
    score[1:] += (leaders[1:] != leaders[:-1]) * LEAD_CHANGE_BONUS * (cum.max(axis=1)[1:] > 0)
    gap = max(7, len(daily) // max(count * 3, 1))
    chosen: List[int] = []
    for day in np.argsort(-score, kind="stable"):
        if score[day] <= 0:
            break
        if all(abs(int(day) - other) >= gap for other in chosen):
            chosen.append(int(day))
        if len(chosen) == count:
            break
    return chosen


def plan_short(main: Sequence[Frame], day: int, length: int, fps: int, cta: str) -> List[Frame]:
    """Short אחד: פתיח של שנייה וחצי, length פריימים מהקטע הראשי סביב היום, ושנייה וחצי קפואה עם ההזמנה."""
    moving = [f for f in main if "hold" not in f and "teaser" not in f]
    if not moving:
        return []
    center = next((i for i, f in enumerate(moving) if f["x"] >= day), len(moving) - 1)
    length = min(length, len(moving))
    start = max(0, min(center - int(length * 0.4), len(moving) - length))
    frames = list(moving[start:start + length])
    ending = int(fps * 1.5)
    # סבב הייצוב: "invite" ולא "pause" - כרטיס סיום במרכז (העצירה למעלה כיסתה את עמודת המוביל)
    closing = [{**frames[-1], "card": None, "toast": None, "hold": {"kind": "invite", "text": cta, "t": j / max(ending - 1, 1)}}
               for j in range(ending)] if cta else []
    return plan_intro(int(fps * 1.5)) + frames + closing


def build_shorts(episode: Any, plan: Sequence[Frame]) -> List[List[Frame]]:
    """התכניות של כל ה-Shorts של הפרק, מהרגע החזק לחלש (plan = התכנית המלאה של הפרק, כבר בגודל לאורך)."""
    settings: Mapping[str, Any] = episode.config.get("shorts") or {}
    fps = int(episode.config["video"]["fps"])
    main = [f for f in plan if f.get("k") == "main"]
    length = int(float(settings.get("seconds") or 20) * fps)
    days = dramatic_days(episode, int(settings.get("count") or 3))
    return [short for short in (plan_short(main, day, length, fps, str(settings.get("cta") or "")) for day in days) if short]
