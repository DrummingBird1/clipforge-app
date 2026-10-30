# dataviz_smart_heldout_v3/_generate.py  (BLIND SET - kept outside the repo until the final scoring)
#
# 20.10.2026: third held-out set for the smart detector. Written with its expectations BEFORE any detector run, and not
# committed, so neither the graph editor nor infra tunes on it. Shapes not in v1/v2: TSV, 'Jan-2021' English month
# abbreviations, dotted 2-digit-year dates '15.03.21', entities as columns (one column per currency), currency symbols and
# thousands separators inside quoted cells, a units row under the header, several value columns where README names the
# one the episode uses, missing-value markers ('-', 'n/a', blanks), an already-cumulative column, and an events file with
# Hebrew headers.
#
#   python _generate.py      (writes the 8 folders next to this file; answers are in _expected/)
import csv
import datetime
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _write(folder, name, rows, delimiter=","):
    os.makedirs(os.path.join(HERE, folder), exist_ok=True)
    with open(os.path.join(HERE, folder, name), "w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter=delimiter).writerows(rows)


def tsv_month_abbrev_sales(rng):
    stores = {"Downtown": 82_000, "Airport": 64_000, "Mall North": 71_000, "Harbor": 39_000}
    rows = [["period", "store", "sales_usd"]]
    for i in range(30):
        year, month = 2021 + i // 12, i % 12
        for store, base in stores.items():
            rows.append([f"{MONTHS[month]}-{year}", store, int(base * (1.25 if month == 11 else 1.0) * rng.uniform(0.85, 1.15))])
    _write("tsv_month_abbrev_sales", "store_sales.tsv", rows, delimiter="\t")


def dotted_dates_hebrew_events(rng):
    cities = {"ירושלים": 9000, "תל אביב": 12000, "חיפה": 5000, "עכו": 2500}
    rows = [["תאריך", "עיר", "מבקרים"]]
    day = datetime.date(2023, 3, 1)
    for _ in range(120):
        for city, base in cities.items():
            weekend = 1.4 if day.weekday() in (4, 5) else 1.0
            rows.append([day.strftime("%d.%m.%y"), city, int(base * weekend * rng.uniform(0.8, 1.2))])
        day += datetime.timedelta(days=1)
    _write("dotted_dates_hebrew_events", "מבקרים_במוזיאונים.csv", rows)
    _write("dotted_dates_hebrew_events", "אירועים.csv", [["תאריך", "אירוע"], ["14.04.23", "חופשת פסח"], ["26.05.23", "פסטיבל אביב"]])


def entities_as_columns_fx(rng):
    rates = {"USD": 3.55, "EUR": 3.85, "GBP": 4.45, "JPY": 0.027}
    rows = [["month"] + list(rates)]
    for i in range(48):
        year, month = 2020 + i // 12, i % 12 + 1
        row = [f"{year}-{month:02d}"]
        for cur, base in rates.items():
            row.append(round(base * (1 + 0.06 * math.sin(i / 7)) * rng.uniform(0.99, 1.01), 4))
        rows.append(row)
    _write("entities_as_columns_fx", "ils_exchange_rates.csv", rows)


def currency_in_cells(rng):
    branches = {"Tel Aviv": 4_800_000, "Haifa": 2_100_000, "Beersheba": 1_400_000, "Eilat": 900_000, "Netanya": 1_700_000}
    rows = [["year", "branch", "revenue"]]
    for year in range(2015, 2024):
        for branch, base in branches.items():
            value = int(base * (1.05 ** (year - 2015)) * rng.uniform(0.92, 1.08))
            rows.append([year, branch, f"₪{value:,}"])
    _write("currency_in_cells", "branch_revenue.csv", rows)


def units_row_under_header(rng):
    sectors = {"Residential": 21_000, "Commercial": 17_500, "Industrial": 14_000, "Agriculture": 2_600, "Public": 6_200}
    rows = [["year", "sector", "consumption"], ["", "", "GWh"]]
    for year in range(2010, 2024):
        for sector, base in sectors.items():
            rows.append([year, sector, int(base * (1.022 ** (year - 2010)) * rng.uniform(0.97, 1.03))])
    _write("units_row_under_header", "electricity_consumption.csv", rows)


def several_values_readme(rng):
    ports = {"Haifa": (17.0, 8.5, 1.2), "Ashdod": (15.5, 7.8, 0.6), "Eilat": (1.8, 0.4, 0.05)}
    rows = [["year", "port", "imports_tonnes_million", "exports_tonnes_million", "transit_tonnes_million"]]
    for year in range(2010, 2024):
        for port, (imp, exp, tr) in ports.items():
            g = 1 + 0.025 * (year - 2010)
            rows.append([year, port, round(imp * g * rng.uniform(0.95, 1.05), 2), round(exp * g * rng.uniform(0.95, 1.05), 2),
                         round(tr * rng.uniform(0.8, 1.2), 2)])
    _write("several_values_readme", "port_cargo.csv", rows)
    with open(os.path.join(HERE, "several_values_readme", "README.md"), "w", encoding="utf-8") as f:
        f.write("# Port cargo\n\nThe episode shows IMPORTS by port (imports_tonnes_million). Exports and transit are kept for reference only.\n")


def missing_markers_reservoirs(rng):
    reservoirs = {"Lowland": -211.5, "Eshkol": 82.0, "Menashe": 45.0}
    rows = [["date", "reservoir", "water_height_m"]]
    for i in range(60):
        year, month = 2019 + i // 12, i % 12 + 1
        for name, base in reservoirs.items():
            r = rng.random()
            value = "-" if r < 0.04 else ("n/a" if r < 0.07 else ("" if r < 0.09 else round(base + 1.2 * math.sin(2 * math.pi * month / 12) + rng.uniform(-0.2, 0.2), 2)))
            rows.append([f"{year}-{month:02d}-15", name, value])
    _write("missing_markers_reservoirs", "reservoir_levels.csv", rows)


def already_cumulative_vaccination(rng):
    regions = {"North": 1_400_000, "Center": 2_600_000, "South": 1_200_000, "Jerusalem": 1_100_000}
    rows = [["date", "region", "total_vaccinated"]]
    totals = {r: 0 for r in regions}
    day = datetime.date(2021, 1, 1)
    for d in range(150):
        for region, pop in regions.items():
            totals[region] += int(pop * 0.006 * math.exp(-d / 60) * rng.uniform(0.8, 1.2))
            rows.append([day.isoformat(), region, totals[region]])
        day += datetime.timedelta(days=1)
    _write("already_cumulative_vaccination", "vaccinated_cumulative.csv", rows)


if __name__ == "__main__":
    rng = random.Random(20261022)
    for make in (tsv_month_abbrev_sales, dotted_dates_hebrew_events, entities_as_columns_fx, currency_in_cells, units_row_under_header,
                 several_values_readme, missing_markers_reservoirs, already_cumulative_vaccination):
        make(rng)
    print("ok")
