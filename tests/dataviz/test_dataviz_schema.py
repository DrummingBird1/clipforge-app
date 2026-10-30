# tests/dataviz/test_dataviz_schema.py - גל 39: סכימת ההגדרות של פרק (dataviz/schema.py), צבע קבוע לישות,
# ושמות חלופיים / מיזוג / החרגה של ישויות (dataviz/episode.apply_entity_rules).
import os


import pandas as pd
import pytest

from dataviz import schema
from dataviz.config import DEFAULTS, ConfigError, load_config
from dataviz.episode import apply_entity_rules, load_episode
from dataviz.render import chart_context
from tests.dataviz_helpers import write_episode


def test_every_schema_field_exists_in_the_defaults_and_has_a_group():
    groups = {key for key, _title, _about in schema.GROUPS}
    for field in schema.FIELDS:
        schema.default_value(field["path"])   # KeyError אם הנתיב לא ב-DEFAULTS
        assert field["group"] in groups, field["path"]
        assert field["label"] and field["type"] in ("text", "lines", "int", "number", "bool", "choice", "date"), field["path"]
    assert len({f["path"] for f in schema.FIELDS}) == len(schema.FIELDS)


@pytest.mark.parametrize("path,value,expected", [
    ("timing.step", "0.01", 0.01), ("video.width", 1280, 1280), ("records.enabled", False, False),
    ("records.when", "lead_change", "lead_change"), ("notes", "א\n\nב ", ["א", "ב"]), ("timeline.start", "2020-1-5", "2020-01-05"),
    ("timeline.end", "", ""), ("intro.title", "  שלום ", "שלום"),
])
def test_clean_value_converts(path, value, expected):
    assert schema.clean_value(path, value) == expected


@pytest.mark.parametrize("path,value", [
    ("timing.step", 5), ("video.width", 1281), ("video.fps", 2.5), ("records.when", "x"), ("records.enabled", "yes"),
    ("timeline.start", "not a date"), ("intro.title", "א" * 500), ("outro.places", ""), ("video.output_name", "a/b"), ("chart", "rocket_race"),   # גל 59: סוג התרשים נערך כאן - רק סוג לא מוכר נדחה
])
def test_clean_value_refuses(path, value):
    with pytest.raises(schema.FieldError):
        schema.clean_value(path, value)


def test_json_schema_describes_config_yaml():
    js = schema.json_schema()
    assert js["$schema"].startswith("https://json-schema.org/") and js["type"] == "object"
    step = js["properties"]["timing"]["properties"]["step"]
    assert step["type"] == "number" and step["default"] == DEFAULTS["timing"]["step"] and step["description"]
    assert "bar_race" in js["properties"]["chart"]["enum"]
    assert js["properties"]["records"]["properties"]["when"]["enum"] == ["current_takes_lead", "lead_change"]


def test_form_groups_tell_default_file_and_override(tmp_path):
    folder = write_episode(tmp_path, overrides={"timing": {"step": 0.004}})
    raw = __import__("yaml").safe_load(open(os.path.join(folder, "config.yaml"), encoding="utf-8"))
    overrides = {"intro": {"title": "חדש"}}
    config = load_config(os.path.join(folder, "config.yaml"), overrides)
    rows = {f["path"]: f for g in schema.form_groups(config, raw, overrides) for f in g["fields"]}
    assert rows["timing.step"]["value"] == 0.004 and rows["timing.step"]["in_file"] and not rows["timing.step"]["overridden"]
    assert rows["timing.step"]["default"] == DEFAULTS["timing"]["step"]
    assert rows["intro.title"]["value"] == "חדש" and rows["intro.title"]["overridden"]


def _matrix():
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    return pd.DataFrame({"תל אביב": [1.0, 2, 3], "ת\"א": [1.0, 1, 1], "חיפה": [5.0, 0, 0]}, index=idx), {"תל אביב": 0, "ת\"א": 1, "חיפה": 0}


def test_aliases_merge_and_exclude():
    matrix, origins = _matrix()
    merged, new_origins = apply_entity_rules(matrix, origins, {"aliases": {"ת\"א": "תל אביב"}, "exclude": ["חיפה"]})
    assert list(merged.columns) == ["תל אביב"]
    assert list(merged["תל אביב"]) == [2.0, 3.0, 4.0]
    assert new_origins == {"תל אביב": 0}


def test_no_rules_change_nothing():
    matrix, origins = _matrix()
    same, same_origins = apply_entity_rules(matrix, origins, {})
    assert same is matrix and same_origins is origins
    with pytest.raises(ValueError):
        apply_entity_rules(matrix, origins, {"exclude": list(matrix.columns)})


def test_entity_rules_and_colors_through_the_engine(tmp_path):
    folder = write_episode(tmp_path)
    base = load_episode(folder)
    year = base.entities[0]
    episode = load_episode(folder, {"entities": {"exclude": [str(year)]}, "colors": {str(base.entities[-1]): "#112233"}})
    assert year not in episode.entities and len(episode.entities) == len(base.entities) - 1
    assert chart_context(episode)["colors"] == {str(base.entities[-1]): "#112233"}
    with pytest.raises(ConfigError):
        load_episode(folder, {"colors": {"x": "red"}})
