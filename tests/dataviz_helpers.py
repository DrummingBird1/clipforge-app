# tests/dataviz_helpers.py
#
# פרק קטן וסינתטי לטסטים של src/dataviz (בלי הנתונים האמיתיים שב-data/): קובץ התרעות
# יומי (שורה = מופע) ל-2021-2023 עם קפיצה חדה אחת (2023 עוקפת את 2020 ומובילה), וסיכום שנתי ל-2019-2020.
import os

import yaml

DAILY_ROWS = [
    # (תאריך-שעה, מקור) - "South" נספר, "North" מסונן החוצה
    ("2021-01-05 10:00:00", "South"), ("2021-01-05 11:00:00", "South"), ("2021-03-01 09:00:00", "North"),
    ("2021-05-10 08:00:00", "South"), ("2022-02-02 12:00:00", "South"), ("2022-08-05 07:30:00", "South"),
    ("not a date", "South"),
] + [("2023-10-07 06:30:00", "South")] * 800 + [("2023-11-01 12:00:00", "South")] * 20


def write_episode(root, overrides=None, name="tiny"):
    """תיקיית פרק מלאה ב-root/name - מחזירה את הנתיב. overrides ממוזגים לרמה העליונה של config.yaml."""
    folder = os.path.join(str(root), name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "alarms.csv"), "w", encoding="utf-8") as f:
        f.write("time,origin\n")
        for when, origin in DAILY_ROWS:
            f.write(f"{when},{origin}\n")
    with open(os.path.join(folder, "annual.csv"), "w", encoding="utf-8") as f:
        f.write("year,total\n2019,365\n2020,732\n")
    with open(os.path.join(folder, "monthly.csv"), "w", encoding="utf-8") as f:
        f.write("year,month,total,window_start,window_end\n2020,1,10,,\n2020,12,30,2020-12-25,2020-12-31\n")
    with open(os.path.join(folder, "events.csv"), "w", encoding="utf-8") as f:
        f.write("date,label\n2023-10-07,אירוע גדול\n2021-05-10,אירוע קטן\n1990-01-01,מחוץ לטווח\n")
    config = {
        "title": "פרק בדיקה",
        "subtitle": "תת-כותרת",
        "labels": {"total": "סך הכל", "leader": "מקום ראשון"},
        "intro": {"subtitle": "שנה מול שנה", "question": "מי מנצח?"},
        "outro": {"title": "המובילות"},
        "notes": ["הערה ראשונה", "הערה שנייה"],
        "events": "events.csv",
        "ranking": {"top_n": 3},
        "sources": [
            {"path": "annual.csv", "time": {"column": "year", "period": "year"}, "value": {"column": "total"},
             "spread": {"per": "day", "weights": {"path": "monthly.csv"}}, "texture": "stripes", "legend": "שנתי"},
            {"path": "alarms.csv", "time": {"column": "time"}, "filter": {"origin": "South"}, "value": "count",
             "legend": "יומי"},
        ],
    }
    for key, value in (overrides or {}).items():
        config[key] = value
    with open(os.path.join(folder, "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    return folder
