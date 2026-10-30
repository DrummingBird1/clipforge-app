# dataviz/smart/thumb.py
#
# 20.10.2026: תמונה ממוזערת לטיוטה - הפריים של הרגע החזק ביותר (מנוע התצוגה החיה, בלי רינדור) עם הכותרת שנבחרה
# (dataviz/web/thumbnail.draw_title). הפלט קובץ חדש בנתיב שהקורא נותן; שום קובץ של הפרק לא משתנה.
import os
from typing import Any, Dict, Mapping, Sequence

import pandas as pd


def strongest(moments: Sequence[Mapping[str, Any]]) -> str:
    """התאריך של הרגע החזק ביותר (הראשון מבין השווים) - או "" כשאין."""
    if not moments:
        return ""
    best = max(m["strength"] for m in moments)
    return min(m["date"] for m in moments if m["strength"] == best)


def make(folder: str, overrides: Mapping[str, Any], date: str, title: str, out_path: str, cache_dir: str) -> Dict[str, Any]:
    """{path, position, date}: PNG של הפריים בתאריך (או באמצע כשאין תאריך) עם הכותרת."""
    from dataviz.web import preview
    from dataviz.web.thumbnail import draw_title
    with preview._lock:
        _key, episode, plan = preview._episode(folder, dict(overrides), 0.5, "full")
    main = [i for i, f in enumerate(plan) if f.get("k") == "main"]
    index = main[len(main) // 2] if main else 0
    if date and main:
        target = pd.Timestamp(date)
        index = next((i for i in main if episode.dates[min(int(plan[i]["x"]), len(episode.dates) - 1)] >= target), main[-1])
    position = index / max(len(plan) - 1, 1)
    frame = preview.preview_frame(folder, dict(overrides), cache_dir, position, scale=0.5)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with preview._lock:   # matplotlib - רק תחת המנעול של התצוגה
        draw_title(frame["path"], title, out_path)
    return {"path": out_path, "position": round(position, 4), "date": frame.get("date", "")}
