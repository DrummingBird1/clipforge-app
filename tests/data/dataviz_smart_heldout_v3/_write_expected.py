# Answers for the v3 blind set, written before any detector run (same schema as v2's _expected/).
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
E = {
    "tsv_month_abbrev_sales": {
        "files": {"store_sales.tsv": "series"}, "series_files": ["store_sales.tsv"], "first_file": "store_sales.tsv",
        "time": "period", "period": "month", "entity": "store", "value": "sales_usd", "unit": "$", "kind": "amount", "chart": "bar_race",
        "notes": "Tab-separated; months as 'Jan-2021'. Sales add up -> amount."},
    "dotted_dates_hebrew_events": {
        "files": {"מבקרים_במוזיאונים.csv": "series", "אירועים.csv": "events"}, "series_files": ["מבקרים_במוזיאונים.csv"],
        "first_file": "מבקרים_במוזיאונים.csv", "time": "תאריך", "period": "day", "entity": "עיר", "value": "מבקרים",
        "unit": "מבקרים", "kind": "amount", "chart": "bar_race",
        "notes": "Dates '15.03.23' (dd.mm.yy, daily). The events file has Hebrew headers (תאריך, אירוע)."},
    "entities_as_columns_fx": {
        "files": {"ils_exchange_rates.csv": "series"}, "series_files": ["ils_exchange_rates.csv"], "first_file": "ils_exchange_rates.csv",
        "time": "month", "period": "month", "entity": "<columns>", "value": "<cells>", "unit": "₪", "kind": "level", "chart": "line_race",
        "notes": "One column per currency (entities as columns) - a correct draft melts it; '<columns>'/'<cells>' mark that. "
                 "Exchange rates are levels, in shekels per unit."},
    "currency_in_cells": {
        "files": {"branch_revenue.csv": "series"}, "series_files": ["branch_revenue.csv"], "first_file": "branch_revenue.csv",
        "time": "year", "period": "year", "entity": "branch", "value": "revenue", "unit": "₪", "kind": "amount", "chart": "bar_race",
        "notes": "Values are quoted strings like '₪4,800,000' - symbol and thousands separators inside the cell; the unit comes from them."},
    "units_row_under_header": {
        "files": {"electricity_consumption.csv": "series"}, "series_files": ["electricity_consumption.csv"],
        "first_file": "electricity_consumption.csv", "time": "year", "period": "year", "entity": "sector", "value": "consumption",
        "unit": "GWh", "kind": "amount", "chart": "bar_race",
        "notes": "A units row ('', '', 'GWh') right under the header - it is the unit, not data."},
    "several_values_readme": {
        "files": {"port_cargo.csv": "series"}, "series_files": ["port_cargo.csv"], "first_file": "port_cargo.csv",
        "time": "year", "period": "year", "entity": "port", "value": "imports_tonnes_million", "unit": "טון (מיליון)",
        "kind": "amount", "chart": "bar_race",
        "notes": "Three value columns; README.md says the episode shows imports."},
    "missing_markers_reservoirs": {
        "files": {"reservoir_levels.csv": "series"}, "series_files": ["reservoir_levels.csv"], "first_file": "reservoir_levels.csv",
        "time": "date", "period": "month", "entity": "reservoir", "value": "water_height_m", "unit": "מטר", "kind": "level",
        "chart": "line_race",
        "notes": "Missing values as '-', 'n/a' and blanks (~9%). Dates are the 15th of each month -> monthly. Water height is a level "
                 "(Lowland is negative, below sea level)."},
    "already_cumulative_vaccination": {
        "files": {"vaccinated_cumulative.csv": "series"}, "series_files": ["vaccinated_cumulative.csv"],
        "first_file": "vaccinated_cumulative.csv", "time": "date", "period": "day", "entity": "region", "value": "total_vaccinated",
        "unit": "מחוסנים", "kind": "level", "chart": "bar_race",
        "notes": "The column is already a running total - must be a level, or the engine would sum it again."},
}
os.makedirs(os.path.join(HERE, "_expected"), exist_ok=True)
for folder, want in E.items():
    with open(os.path.join(HERE, "_expected", folder + ".json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(want, f, ensure_ascii=False, indent=2)
        f.write("\n")
print(len(E))
