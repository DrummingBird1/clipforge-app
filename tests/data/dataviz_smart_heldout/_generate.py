# tests/data/dataviz_smart_heldout/_generate.py
#
# 20.10.2026: קורפוס מבחן עצמאי (held-out) לגלאי החכם של עורך הגרפים (src/dataviz/smart/) - 8 תיקיות פרק סינתטיות,
# מספרים ריאליסטיים שנוצרו כאן (seed קבוע, בלי הורדות), ולכל אחת _expected/<תיקייה>.json (עד 20.10.2026 expected.json בתוך התיקייה) שנכתב *לפני* שהגלאי רץ עליהן (ראו
# ההיסטוריה ב-git: הקומיט של הנתונים קודם לטסט). מכסה מקרים שלא היו בקורפוס שהגלאי כויל עליו: שמות עמודות באנגלית
# ובעברית, 2020-Q3, 03/2021, חודשים בעברית, טבלה רחבה (שנים כעמודות), אחוזים, עמודת מזהה מספרית, שורת סך בסוף,
# קובץ אירועים בלי כותרת, שני קבצים ביחידות שונות, סדרת רמה שמתחילה מ-0, וקובץ XLSX.
#
#   uv run python tests/data/dataviz_smart_heldout/_generate.py     (כותב מחדש את הקבצים; _expected/ נכתב ביד)
import csv
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
HEBREW_MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]


def _write(folder, name, header, rows):
    os.makedirs(os.path.join(HERE, folder), exist_ok=True)
    with open(os.path.join(HERE, folder, name), "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if header:
            writer.writerow(header)
        writer.writerows(rows)


def en_monthly_inflation_pct(rng):
    """אנגלית, תאריכים 03/2021, אחוזים (יכולים להיות שליליים)."""
    rows = []
    base = {"Food": 2.1, "Housing": 3.4, "Transport": 1.2, "Energy": 4.0, "Health": 1.8}
    for i in range(36):
        year, month = 2021 + (i + 2) // 12, (i + 2) % 12 + 1
        for category, b in base.items():
            wave = math.sin(i / 6) * (2.5 if category == "Energy" else 1.0)
            rows.append([f"{month:02d}/{year}", category, round(b + wave + rng.uniform(-0.4, 0.4), 1)])
    _write("en_monthly_inflation_pct", "inflation_by_category.csv", ["month", "category", "inflation_pct"], rows)


def he_rainfall_hebrew_months(rng):
    """עמודות בעברית, חודשים בשמות עבריים ("ינואר 2022"), כמות (משקעים)."""
    stations = {"ירושלים": 1.0, "תל אביב": 0.95, "חיפה": 1.1, "באר שבע": 0.35, "אילת": 0.05}
    season = [140, 110, 70, 20, 4, 0, 0, 0, 1, 25, 70, 120]
    rows = []
    for year in (2022, 2023):
        for m, month in enumerate(HEBREW_MONTHS):
            for station, factor in stations.items():
                rows.append([f"{month} {year}", station, round(season[m] * factor * rng.uniform(0.6, 1.4), 1)])
    _write("he_rainfall_hebrew_months", "גשמים_לפי_תחנה.csv", ["חודש", "תחנה", 'משקעים_מ"מ'], rows)


def wide_city_population(rng):
    """טבלה רחבה: עיר בשורה, שנים כעמודות (2015..2023), ערכי אוכלוסייה."""
    cities = {"Jerusalem": 865_000, "Tel Aviv": 432_000, "Haifa": 279_000, "Rishon LeZion": 247_000, "Petah Tikva": 236_000,
              "Ashdod": 220_000, "Netanya": 207_000, "Beersheba": 205_000}
    years = list(range(2015, 2024))
    rows = []
    for city, start in cities.items():
        growth = rng.uniform(0.008, 0.022)
        rows.append([city] + [int(start * (1 + growth) ** k) for k in range(len(years))])
    _write("wide_city_population", "city_population.csv", ["city"] + [str(y) for y in years], rows)


def ids_and_totals_exports(rng):
    """עמודת מזהה מספרית (קוד מדינה ISO) שאסור שתהיה הערך, ושורת סך בסוף הקובץ."""
    countries = {"United States": (840, 4100), "Germany": (276, 1900), "China": (156, 1600), "India": (356, 950),
                 "United Kingdom": (826, 1100), "France": (250, 800)}
    rows = []
    for year in range(2015, 2024):
        total = 0.0
        for country, (code, base) in countries.items():
            value = round(base * (1 + 0.05 * (year - 2015)) * rng.uniform(0.85, 1.15), 1)
            total += value
            rows.append([year, code, country, value])
    grand = round(sum(r[3] for r in rows), 1)
    rows.append(["", "", "Total", grand])
    _write("ids_and_totals_exports", "exports_by_country.csv", ["year", "country_code", "country", "exports_usd_million"], rows)


def quarters_output_index_events(rng):
    """רבעונים 2020-Q3, מדד (רמה), וקובץ אירועים בלי שורת כותרת."""
    sectors = {"Technology": 100, "Manufacturing": 100, "Services": 100, "Agriculture": 100}
    trend = {"Technology": 3.0, "Manufacturing": 0.8, "Services": 1.2, "Agriculture": 0.4}
    rows = []
    for year in range(2019, 2024):
        for q in range(1, 5):
            for sector in sectors:
                shock = -9 if (year, q) == (2020, 2) else (-3 if (year, q) == (2020, 3) else 0)
                sectors[sector] = round(sectors[sector] + trend[sector] + shock + rng.uniform(-0.6, 0.6), 1)
                rows.append([f"{year}-Q{q}", sector, sectors[sector]])
    _write("quarters_output_index_events", "output_index_by_sector.csv", ["quarter", "sector", "output_index"], rows)
    _write("quarters_output_index_events", "milestones.csv", None, [
        ["2020-03-15", "First COVID-19 lockdown"], ["2021-01-10", "Vaccination campaign"], ["2022-02-24", "Energy price shock"],
        ["2023-07-01", "Rate hikes peak"]])


def two_units_tourism(rng):
    """שני קבצים לאותם אזורים ביחידות שונות: הכנסות (₪ מיליון) ולינות (מספר)."""
    regions = {"Eilat": (1.6, 2.4), "Jerusalem": (2.2, 3.1), "Tel Aviv": (2.8, 3.6), "Dead Sea": (0.9, 1.5), "Galilee": (0.7, 1.2)}
    revenue, nights = [], []
    for year in range(2014, 2024):
        dip = 0.25 if year == 2020 else (0.6 if year == 2021 else 1.0)
        for region, (rev, n) in regions.items():
            grow = 1 + 0.04 * (year - 2014)
            revenue.append([year, region, round(rev * 1000 * grow * dip * rng.uniform(0.9, 1.1))])
            nights.append([year, region, int(n * 1_000_000 * grow * dip * rng.uniform(0.9, 1.1))])
    _write("two_units_tourism", "tourism_revenue.csv", ["year", "region", "revenue_nis_million"], revenue)
    _write("two_units_tourism", "hotel_nights.csv", ["year", "region", "nights"], nights)


def level_from_zero_solar(rng):
    """סדרת רמה (הספק מותקן) שמתחילה מ-0 בכל המחוזות, שמות מחוזות בעברית."""
    districts = {"הדרום": 1.0, "המרכז": 0.45, "הצפון": 0.35, "חיפה": 0.15, "ירושלים": 0.1}
    rows = []
    for year in range(2008, 2024):
        for district, share in districts.items():
            capacity = 0 if year <= 2009 else round(share * 4200 * ((year - 2009) / 14) ** 1.8 * rng.uniform(0.97, 1.03))
            rows.append([year, district, capacity])
    _write("level_from_zero_solar", "solar_installed_capacity.csv", ["year", "district", "installed_capacity_mw"], rows)


def xlsx_hebrew_sales(rng):
    """קובץ XLSX (לא CSV) עם כותרות בעברית, תאריכים יומיים של תחילת חודש, מכירות בש"ח."""
    from openpyxl import Workbook
    products = {"קפה": 42_000, "תה": 18_000, "שוקולד": 31_000, "עוגיות": 22_000}
    wb = Workbook()
    ws = wb.active
    ws.title = "מכירות"
    ws.append(["תאריך", "מוצר", 'מכירות_ש"ח'])
    for i in range(24):
        year, month = 2022 + i // 12, i % 12 + 1
        for product, base in products.items():
            season = 1.3 if (product == "שוקולד" and month in (12, 1, 2)) else 1.0
            ws.append([f"{year}-{month:02d}-01", product, int(base * season * rng.uniform(0.85, 1.15))])
    folder = os.path.join(HERE, "xlsx_hebrew_sales")
    os.makedirs(folder, exist_ok=True)
    wb.save(os.path.join(folder, "מכירות_לפי_מוצר.xlsx"))


if __name__ == "__main__":
    rng = random.Random(20261020)
    for make in (en_monthly_inflation_pct, he_rainfall_hebrew_months, wide_city_population, ids_and_totals_exports,
                 quarters_output_index_events, two_units_tourism, level_from_zero_solar, xlsx_hebrew_sales):
        make(rng)
    print("ok")
