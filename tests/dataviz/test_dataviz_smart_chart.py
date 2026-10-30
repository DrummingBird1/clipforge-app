# tests/dataviz/test_dataviz_smart_chart.py
#
# 20.10.2026: עורך הגרפים החכם, פריט 7 - בחירת התרשים לפי צורת הנתונים, עם סיבה וחלופות: מפה (GeoJSON מתאים), שני
# צירים, גרפים קטנים, פיזור (מדד שני לאותן ישויות), שטח מוערם (חלקים של סך), קווים (רמה שלא מתחברת), מרוץ עמודות.
import json

from dataviz.smart import draft


def _csv(path, text):
    path.write_text(text.strip() + "\n", encoding="utf-8")


def _rows(entities, column, years=(2000, 2001, 2002), base=10):
    lines = [f"year,entity,{column}"]
    for y_i, year in enumerate(years):
        for e_i, entity in enumerate(entities):
            lines.append(f"{year},{entity},{base + e_i * 3 + y_i * (e_i + 1)}")
    return "\n".join(lines)


def _chart(folder):
    return draft.analyze(str(folder))["chart"]


def test_many_competing_entities_get_a_bar_race(tmp_path):
    _csv(tmp_path / "medals_per_games.csv", _rows([f"מדינה {i}" for i in range(15)], "total_medals"))
    chart = _chart(tmp_path)
    assert chart["value"] == "bar_race" and chart["top_n"] == 10 and chart["alternatives"] and chart["reason"]


def test_parts_of_a_whole_need_evidence_for_a_stacked_area(tmp_path):
    _csv(tmp_path / "exports_by_country.csv", _rows(["ארה\"ב", "גרמניה", "סין", "צרפת"], "exports"))
    assert _chart(tmp_path)["value"] == "bar_race"                       # "by_" בשם לבד - לא עדות לחלקים של סך
    residual = tmp_path / "residual"
    residual.mkdir()
    _csv(residual / "immigrants.csv", _rows(["אירופה", "אסיה", "אפריקה", "לא ידוע"], "immigrants"))
    chart = _chart(residual)
    assert chart["value"] == "stacked_area_race" and chart["top_n"] == 4 and "לא ידוע" in chart["reason"]
    assert "pie_race" in [a["value"] for a in chart["alternatives"]]
    shares = tmp_path / "shares"
    shares.mkdir()
    _csv(shares / "market.csv", "year,entity,share_pct\n2000,a,50\n2000,b,30\n2000,c,20\n2001,a,40\n2001,b,35\n2001,c,25")
    assert _chart(shares)["value"] == "stacked_area_race"                # מסתכם ל-100% בכל שנה


def test_a_level_that_does_not_add_up_gets_lines(tmp_path):
    _csv(tmp_path / "prices.csv", _rows(["לחם", "חלב", "ביצים"], "price_nis"))
    assert _chart(tmp_path)["value"] == "line_race"                     # מחירים לא מתחברים - קווים
    many = tmp_path / "many"
    many.mkdir()
    _csv(many / "gdp_per_capita_levels.csv", _rows([f"c{i}" for i in range(30)], "gdp_per_capita_usd", base=1000))
    assert _chart(many)["value"] == "bar_race"                          # 30 מדינות מתחרות


def test_two_units_get_lines_with_two_axes_and_more_get_small_multiples(tmp_path):
    _csv(tmp_path / "temperature.csv", "year,entity,level_value\n2000,טמפרטורה (°C),18\n2001,טמפרטורה (°C),19\n2002,טמפרטורה (°C),18.5")
    _csv(tmp_path / "lake.csv", "year,entity,level_value\n2000,מפלס (מטר),210\n2001,מפלס (מטר),211\n2002,מפלס (מטר),209")
    assert _chart(tmp_path)["value"] == "line_race"
    _csv(tmp_path / "rain.csv", "year,entity,rain_pct\n2000,גשם,90\n2001,גשם,95\n2002,גשם,80")
    assert _chart(tmp_path)["value"] == "small_multiples"


def test_a_second_measure_for_the_same_entities_gets_a_scatter(tmp_path):
    countries = [f"מדינה {i}" for i in range(6)]
    _csv(tmp_path / "expectancy_levels.csv", _rows(countries, "life_expectancy_years", base=70))
    wide = ["year,entity,life_expectancy_years,health_spend_per_capita_usd"]
    for year in (2000, 2001, 2002):
        wide += [f"{year},{c},{70 + i},{1000 + i * 10}" for i, c in enumerate(countries)]
    _csv(tmp_path / "expectancy_and_spend_wide.csv", "\n".join(wide))
    chart = _chart(tmp_path)
    assert chart["value"] == "scatter_race" and "health_spend_per_capita_usd" in chart["reason"]


def test_a_matching_geojson_gets_a_map(tmp_path):
    names = ["צפון", "דרום", "מרכז"]
    _csv(tmp_path / "alarms_by_region.csv", _rows(names, "alarms"))
    features = [{"type": "Feature", "properties": {"name": n}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}
                for n in names]
    (tmp_path / "regions.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    chart = _chart(tmp_path)
    assert chart["value"] == "map_race" and "100%" in chart["reason"]
