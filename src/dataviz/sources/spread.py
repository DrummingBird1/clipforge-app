# dataviz/sources/spread.py
#
# פיזור סכום של תקופה (שנה/חודש) על הימים שלה. בלי מידע נוסף - שווה על פני כל הימים
# (per: day) או שווה בין החודשים ואז שווה בתוך כל חודש (per: month). עם טבלת משקלות
# (למשל סכומים חודשיים, או חלון של ימי שיא כמו 19-31.12.2008) - הסכום מתפזר לפיה
# ומנורמל חזרה לסכום התקופה, כך שהשנתי נשאר הנתון הקובע והפירוט רק קובע את הצורה.
#
# הגדרה (בתוך מקור):
#     spread:
#       per: day                     # day / month
#       weights:
#         path: alerts_monthly.csv
#         period_column: year        # עמודה שמזהה את התקופה (השנה) של כל שורת משקל
#         month_column: month        # חודש בתוך השנה (כשאין חלון)
#         value: total
#         window_start: window_start # חלון ימים מפורש (גובר על month_column)
#         window_end: window_end

from typing import Any, Mapping

import pandas as pd


def period_days(start: pd.Timestamp, period: str) -> pd.DatetimeIndex:
    start = pd.Timestamp(start)
    if period == "year":
        return pd.date_range(f"{start.year}-01-01", f"{start.year}-12-31", freq="D")
    if period == "month":
        return pd.date_range(start, start + pd.offsets.MonthEnd(0), freq="D")
    if period == "quarter":   # 20.10.2026
        return pd.date_range(start, start + pd.offsets.QuarterEnd(0), freq="D")
    return pd.DatetimeIndex([start.normalize()])


def spread_to_days(start: pd.Timestamp, period: str, total: Any, spread: Mapping[str, Any],
                   weights: pd.DataFrame | None = None) -> pd.Series:
    """סכום תקופה -> סדרה יומית (אינדקס = ימי התקופה) שסכומה הוא total."""
    days = period_days(start, period)
    s = pd.Series(0.0, index=days)
    rows = _weight_rows(weights, spread.get("weights") or {}, pd.Timestamp(start), period)
    if rows is not None and len(rows):
        w = spread["weights"]
        start_col, end_col = w.get("window_start", "window_start"), w.get("window_end", "window_end")
        value_col, month_col = w.get("value", "total"), w.get("month_column", "month")
        # 23.10.2026: חלון שחוצה את סוף התקופה (25.12-05.01) או נופל ברבעון אחר זרק KeyError, חודש ריק בקובץ המשקלות
        # זרק ValueError, ומשקלות שסכומם 0 העלימו את הסכום של התקופה - עכשיו החלון נחתך לימי התקופה, שורה לא שמישה
        # מדולגת, ובלי משקל חיובי - הפיזור הרגיל שלמטה
        for _, mr in rows.iterrows():
            window = mr[start_col] if start_col in mr else None
            if isinstance(window, str) and window:
                idx = pd.date_range(window, mr[end_col], freq="D").intersection(days)
            else:
                month = pd.to_numeric(mr[month_col], errors="coerce")
                idx = days[days.month == int(month)] if pd.notna(month) else days[:0]
            weight = pd.to_numeric(mr[value_col], errors="coerce")
            if len(idx) and pd.notna(weight):
                s[idx] += float(weight) / len(idx)
        if s.sum() > 0:
            s *= total / s.sum()
            return s
        s[:] = 0.0
    if str(spread.get("per", "day")) == "month" and period == "year":
        for month in range(1, 13):
            idx = days[days.month == month]
            s[idx] += (total / 12) / len(idx)
        return s
    s[:] = total / len(days)
    return s


def _weight_rows(weights: pd.DataFrame | None, spec: Mapping[str, Any], start: pd.Timestamp, period: str) -> pd.DataFrame | None:
    """שורות המשקל ששייכות לתקופה הזו (לפי period_column = השנה, או החודש לתקופה חודשית)."""
    if weights is None or not spec:
        return None
    column = spec.get("period_column", "year")
    rows = weights[weights[column] == start.year]
    if period == "month":
        month_col = spec.get("month_column", "month")
        rows = rows[rows[month_col] == start.month]
    return rows
