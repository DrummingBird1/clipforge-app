# tests/data/dataviz_smart_heldout_v2/_generate.py
#
# 20.10.2026: קורפוס מבחן עצמאי שני (v2) לגלאי החכם - הראשון (dataviz_smart_heldout) כבר שימש לכיול, אז הוא לא עיוור.
# 8 תיקיות פרק חדשות בצורות שלא היו ב-v1: CSV עם ';' ופסיק עשרוני, נתונים שבועיים, שנות כספים "2021/22", מקור JSON,
# שתי שורות כותרת, ערכים שליליים (מאזן), שיעור לנפש, קובץ גאוגרפי עם שמות מחוזות, סדרה ארוכה של ישות אחת, ותיקייה
# עם שני מאגרים לא קשורים. מספרים ריאליסטיים שנוצרו כאן (seed קבוע, בלי הורדות). expected.json נכתב ביד ונשמר בקומיט
# לפני שהגלאי רץ על התיקיות; התשובות הנכונות נקבעו לפי הנתונים, בלי להסתכל בכללים של src/dataviz/smart/.
#
#   uv run python tests/data/dataviz_smart_heldout_v2/_generate.py
import csv
import datetime
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))


def _path(folder, name):
    os.makedirs(os.path.join(HERE, folder), exist_ok=True)
    return os.path.join(HERE, folder, name)


def _write(folder, name, rows, delimiter=","):
    with open(_path(folder, name), "w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter=delimiter).writerows(rows)


def semicolon_weekly_fuel(rng):
    """CSV אירופאי: ';' כמפריד, פסיק עשרוני (1,679), נתונים שבועיים (כל יום שני)."""
    fuels = {"Super 95": 1.72, "Super 98": 1.84, "Diesel": 1.61, "LPG": 0.92}
    rows = [["date", "fuel", "price_eur_per_litre"]]
    day = datetime.date(2022, 1, 3)
    for week in range(104):
        for fuel, base in fuels.items():
            price = base + 0.25 * math.sin(week / 9) + (0.18 if 8 <= week <= 30 else 0) + rng.uniform(-0.02, 0.02)
            rows.append([day.isoformat(), fuel, f"{price:.3f}".replace(".", ",")])
        day += datetime.timedelta(days=7)
    _write("semicolon_weekly_fuel", "fuel_prices_weekly.csv", rows, delimiter=";")


def fiscal_year_budget(rng):
    """שנות כספים "2021/22" (לא שנה קלנדרית), תקציב לפי משרד במיליארדי ש"ח."""
    ministries = {"Education": 68.0, "Health": 47.0, "Defense": 62.0, "Welfare": 14.0, "Transport": 9.5, "Housing": 3.2}
    rows = [["fiscal_year", "ministry", "budget_nis_billion"]]
    for start in range(2014, 2024):
        for ministry, base in ministries.items():
            rows.append([f"{start}/{str(start + 1)[2:]}", ministry, round(base * (1.035 ** (start - 2014)) * rng.uniform(0.96, 1.04), 1)])
    _write("fiscal_year_budget", "budget_by_ministry.csv", rows)


def json_app_downloads(rng):
    """מקור JSON (רשימת רשומות), הורדות חודשיות לפי אפליקציה."""
    apps = {"Waze": 210_000, "Moovit": 160_000, "Gett": 75_000, "Wolt": 190_000, "Pango": 60_000}
    records = []
    for i in range(30):
        year, month = 2021 + i // 12, i % 12 + 1
        for app, base in apps.items():
            records.append({"month": f"{year}-{month:02d}", "app": app, "downloads": int(base * (1 + 0.01 * i) * rng.uniform(0.8, 1.2))})
    with open(_path("json_app_downloads", "downloads.json"), "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=1)


def two_header_rows_employment(rng):
    """שתי שורות כותרת: שורת קבוצה מעל שמות העמודות האמיתיים (כמו ייצוא מגיליון), בעברית."""
    districts = {"ירושלים": 520_000, "הצפון": 610_000, "חיפה": 470_000, "המרכז": 1_080_000, "תל אביב": 760_000, "הדרום": 540_000}
    rows = [["נתוני תעסוקה לפי מחוז", "", ""], ["שנה", "מחוז", "מועסקים"]]
    for year in range(2012, 2024):
        for district, base in districts.items():
            dip = 0.93 if year == 2020 else 1.0
            rows.append([year, district, int(base * (1.015 ** (year - 2012)) * dip * rng.uniform(0.98, 1.02))])
    _write("two_header_rows_employment", "תעסוקה_לפי_מחוז.csv", rows)


def geo_district_unemployment(rng):
    """קובץ גאוגרפי (GeoJSON) עם שמות המחוזות, ולצדו נתוני אבטלה (%) לפי מחוז."""
    names = ["ירושלים", "הצפון", "חיפה", "המרכז", "תל אביב", "הדרום"]
    features = []
    for i, name in enumerate(names):   # מלבנים פשוטים, אחד מתחת לשני (צפון-דרום) - מספיק לזיהוי לפי השם
        top = 33.3 - i * 0.6
        ring = [[34.6, top], [35.6, top], [35.6, top - 0.6], [34.6, top - 0.6], [34.6, top]]
        features.append({"type": "Feature", "properties": {"name": name}, "geometry": {"type": "Polygon", "coordinates": [ring]}})
    with open(_path("geo_district_unemployment", "districts.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False)
    base = {"ירושלים": 6.1, "הצפון": 5.4, "חיפה": 4.6, "המרכז": 3.4, "תל אביב": 3.1, "הדרום": 5.9}
    rows = [["year", "district", "unemployment_pct"]]
    for year in range(2010, 2024):
        for name in names:
            covid = 3.5 if year == 2020 else (1.5 if year == 2021 else 0)
            rows.append([year, name, round(base[name] - 0.12 * (year - 2010) + covid + rng.uniform(-0.3, 0.3), 1)])
    _write("geo_district_unemployment", "unemployment_by_district.csv", rows)


def negative_trade_balance(rng):
    """מאזן סחר: ערכים שליליים (גירעון) ליד חיוביים, שנתי לפי מדינה שותפה."""
    partners = {"United States": 4200, "China": -6100, "Germany": -2300, "India": 1100, "Turkey": -1500, "Netherlands": 900}
    rows = [["year", "partner", "trade_balance_usd_million"]]
    for year in range(2013, 2024):
        for partner, base in partners.items():
            rows.append([year, partner, round(base * (1 + 0.04 * (year - 2013)) + rng.uniform(-400, 400), 1)])
    _write("negative_trade_balance", "trade_balance.csv", rows)


def per_capita_single_long(rng):
    """סדרה ארוכה של ישות אחת (בלי עמודת ישות): שיעור חודשי ל-100 אלף תושבים, 1995-2023."""
    rows = [["date", "road_injuries_per_100k"]]
    for i in range(29 * 12):
        year, month = 1995 + i // 12, i % 12 + 1
        trend = 52 - 0.06 * i
        rows.append([f"{year}-{month:02d}-01", round(trend + 4 * math.sin(2 * math.pi * month / 12) + rng.uniform(-1.5, 1.5), 2)])
    _write("per_capita_single_long", "road_injuries_rate.csv", rows)


def two_unrelated_datasets(rng):
    """שני מאגרים לא קשורים באותה תיקייה; SOURCES.md אומר על מה הפרק (מכירות רכב), הגשמים לא שייכים."""
    brands = {"Hyundai": 2600, "Toyota": 2900, "Kia": 2300, "Skoda": 1500, "Tesla": 700}
    sales = [["month", "brand", "cars_sold"]]
    for i in range(36):
        year, month = 2021 + i // 12, i % 12 + 1
        for brand, base in brands.items():
            boost = 1.6 if month == 1 else 1.0
            sales.append([f"{year}-{month:02d}", brand, int(base * boost * rng.uniform(0.8, 1.2))])
    _write("two_unrelated_datasets", "car_sales.csv", sales)
    rain = [["year", "station", "rain_mm"]]
    for year in range(2000, 2024):
        for station, base in {"Jerusalem": 540, "Haifa": 600, "Eilat": 25}.items():
            rain.append([year, station, round(base * rng.uniform(0.6, 1.4))])
    _write("two_unrelated_datasets", "rainfall_annual.csv", rain)
    with open(_path("two_unrelated_datasets", "SOURCES.md"), "w", encoding="utf-8") as f:
        f.write("# Sources\n\nThis episode is about new car sales in Israel by brand (car_sales.csv, monthly registrations).\n\n"
                "rainfall_annual.csv was left here from another project and is not part of this episode.\n")


if __name__ == "__main__":
    rng = random.Random(20261021)
    for make in (semicolon_weekly_fuel, fiscal_year_budget, json_app_downloads, two_header_rows_employment,
                 geo_district_unemployment, negative_trade_balance, per_capita_single_long, two_unrelated_datasets):
        make(rng)
    print("ok")
