# tests/dataviz/test_dataviz_episode_language.py
#
# 30.10.2026 (לפני ההפצה): פרק שנוצר בממשק באנגלית (lang=en מהדף) מקבל תוויות ותבנית תאריך באנגלית במקום ברירות המחדל
# העבריות של dataviz/config.py; פרק בעברית - כמו קודם, בלי תוויות בקובץ.
import yaml

from dataviz.web import episodes as de

CSV = "date,city,n\n2024-01-01,Haifa,1\n2024-01-02,Haifa,3\n2024-01-01,Eilat,2\n2024-01-02,Eilat,2\n"


def _create(tmp_path, name, **extra):
    (tmp_path / "dataviz_episodes").mkdir(exist_ok=True)
    de.create_episode(str(tmp_path), {"name": name, "title": "Demo", "time_column": "date", "value_column": "n",
                                      "group_column": "city", "csv_text": CSV, **extra})
    return yaml.safe_load((tmp_path / "dataviz_episodes" / name / "config.yaml").read_text(encoding="utf-8"))


def test_an_episode_made_in_english_gets_english_labels_and_dates(tmp_path):
    config = _create(tmp_path, "demo_en", lang="en")
    assert config["labels"] == {"date_format": "%b %d, %Y", "record": "New record: {entity}", "others": "Others"}   # קודם: "שיא חדש"
    assert config["outro"]["places"] == ["1st place", "2nd place", "3rd place"]
    assert _create(tmp_path, "demo_he").get("labels") is None                              # בעברית - ברירות המחדל, כמו קודם
