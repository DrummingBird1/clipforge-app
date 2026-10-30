# tests/dataviz/test_dataviz_config.py
#
# src/dataviz/config.py: ברירות המחדל של הסרטון הראשון, מיזוג עם config.yaml, ולידציה
# שאוספת את כל השגיאות יחד, ואירועים מ-CSV.
import os

import pytest

from dataviz.config import DEFAULTS, ConfigError, load_config, merge, mode_timing
from dataviz.episode import load_episode, load_events
from tests.dataviz_helpers import write_episode


def test_minimal_config_gets_the_first_episode_defaults(tmp_path):
    folder = write_episode(tmp_path)

    config = load_config(os.path.join(folder, "config.yaml"))

    assert config["name"] == "tiny" and config["base_dir"] == folder
    assert config["video"]["width"] == 1440 and config["video"]["fps"] == 60
    assert config["timing"]["step"] == 0.005
    assert config["ranking"]["top_n"] == 3                 # נדרס בפרק
    assert config["ranking"]["smoothing"] == 0.07          # ברירת מחדל
    assert config["outro"]["places"] == ["מקום ראשון", "מקום שני", "מקום שלישי"]


def test_merge_is_deep_for_dicts_and_replaces_lists():
    merged = merge({"a": {"x": 1, "y": 2}, "l": [1, 2]}, {"a": {"y": 3}, "l": [9]})
    assert merged == {"a": {"x": 1, "y": 3}, "l": [9]}
    assert DEFAULTS["ranking"]["top_n"] == 10              # המקור לא השתנה


def test_validation_collects_every_error_at_once(tmp_path):
    folder = write_episode(tmp_path, {
        "title": "",
        "chart": "rocket_race",
        "theme": "neon",
        "ranking": {"top_n": 0, "smoothing": 2},
        "video": {"width": 1441},
        "audio": {"path": "missing.mp3"},
        "events": [{"date": "not-a-date", "label": "x"}, {"label": "בלי תאריך"}],
        "sources": [{"path": "nope.csv", "time": {"column": "t", "period": "week"}, "texture": "dots"}],
    })

    with pytest.raises(ConfigError) as info:
        load_config(os.path.join(folder, "config.yaml"))

    text = "\n".join(info.value.errors)
    for fragment in ("title", "rocket_race", "neon", "ranking.top_n", "ranking.smoothing", "זוגיים", "missing.mp3",
                     "events[0]", "events[1]", "nope.csv", "time.period", "texture"):
        assert fragment in text, fragment
    assert len(info.value.errors) >= 12


def test_broken_yaml_and_non_mapping_are_config_errors(tmp_path):
    (tmp_path / "bad.yaml").write_text("title: [unclosed\n", encoding="utf-8")
    (tmp_path / "list.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="YAML"):
        load_config(str(tmp_path / "bad.yaml"))
    with pytest.raises(ConfigError, match="מילון"):
        load_config(str(tmp_path / "list.yaml"))
    with pytest.raises(ConfigError, match="לא ניתן לקרוא"):
        load_config(str(tmp_path / "missing.yaml"))


def test_events_load_sorted_from_csv_and_out_of_range_ones_are_dropped(tmp_path):
    episode = load_episode(write_episode(tmp_path))

    assert load_events(episode.config)[0] == ("1990-01-01", "מחוץ לטווח")
    assert [(d, label) for d, label, _ in episode.events] == [("2021-05-10", "אירוע קטן"), ("2023-10-07", "אירוע גדול")]
    for date, _, day in episode.events:
        assert episode.dates[day].strftime("%Y-%m-%d") == date


def test_mode_timing_full_test_and_stills():
    config = merge(DEFAULTS, {})
    assert mode_timing(config, "full") == {"intro": 360, "outro": 600, "main": 0}
    assert mode_timing(config, "stills") == mode_timing(config, "full")
    assert mode_timing(config, "test") == {"intro": 60, "outro": 60, "main": 420}
    assert mode_timing(config, "preview") == {"intro": 30, "outro": 30, "main": 300}
    with pytest.raises(ValueError):
        mode_timing(config, "bogus")
