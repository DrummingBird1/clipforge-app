# tests/dataviz/test_dataviz_smart_score.py
#
# 20.10.2026: עורך הגרפים החכם - בחירת קבצי הסדרה של הפרק (בלי סדרה מצרפית "national" ובלי כפילות של אותם נתונים,
# אבל שני קבצים עם אותו שם עמודה וישויות שונות נשארים), והציון מול config.yaml ידני (delta_X שקול ל-X עם kind: level).
import yaml

from dataviz.smart import draft, score


def _csv(path, text):
    path.write_text(text.strip() + "\n", encoding="utf-8")


def test_series_choice_drops_the_aggregate_and_duplicates_but_keeps_two_measures(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    _csv(a / "district_index.csv", "month,entity,price_index\n2020-01-01,צפון,100\n2020-01-01,דרום,101\n2020-02-01,צפון,102\n2020-02-01,דרום,103")
    _csv(a / "national_index.csv", "month,national_price_index\n2020-01-01,100\n2020-02-01,102")
    _csv(a / "wide.csv", "year,entity,expectancy_years,spend_usd\n2000,x,70,1\n2000,y,71,2\n2001,x,70.5,1\n2001,y,72,2")
    _csv(a / "expectancy_levels.csv", "year,entity,expectancy_years\n2000,x,70\n2000,y,71\n2001,x,70.5\n2001,y,72")
    names = [f["name"] for f in draft.pick_series(draft.scan_folder(str(a))["files"])]
    assert "national_index.csv" not in names and "district_index.csv" in names
    assert ("expectancy_levels.csv" in names) != ("wide.csv" in names)          # אחד מהשניים - אותם נתונים
    b = tmp_path / "b"
    b.mkdir()
    _csv(b / "temperature.csv", "year,entity,level_value\n2000,טמפרטורה (°C),18\n2001,טמפרטורה (°C),19")
    _csv(b / "lake.csv", "year,entity,level_value\n2000,מפלס (מטר),210\n2001,מפלס (מטר),211")
    picked = draft.choices(str(b))
    assert picked["file"] == ["lake.csv", "temperature.csv"]                    # אותו שם עמודה, ישויות שונות
    assert picked["unit_by_file"] == {"lake.csv": "מטר", "temperature.csv": "°C"}


def test_score_against_a_hand_written_config(tmp_path):
    folder = tmp_path / "prices"
    folder.mkdir()
    _csv(folder / "prices.csv", "year,entity,price_nis,delta_nis\n2019,לחם,5,5\n2019,חלב,6,6\n2020,לחם,5.5,0.5\n2020,חלב,6.1,0.1")
    (folder / "config.yaml").write_text(yaml.safe_dump({"chart": "line_race", "sources": [
        {"path": "prices.csv", "time": {"column": "year", "period": "year"}, "entity": {"column": "entity"}, "value": {"column": "delta_nis"}}]},
        allow_unicode=True), encoding="utf-8")
    want = score.expected(str(folder))
    assert want["kind"] == "level" and want["value"] == "delta_nis"              # delta_ = סדרת רמה
    row = score.score_folder(str(folder))
    assert row["hits"]["value"] is True and row["hits"]["time"] is True and row["hits"]["file"] is True
    assert row["hits"]["unit"] is None                                           # אין יחידה צפויה לפרק שלא בקורפוס
    assert score.score_folder(str(folder), lambda f: {"file": ["x.csv"], "value": "price_nis", "columns": []})["hits"]["file"] is False
    assert "| prices |" in score.table([row])
