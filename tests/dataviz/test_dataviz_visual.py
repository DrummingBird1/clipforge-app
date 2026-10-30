# tests/dataviz/test_dataviz_visual.py - גל 54: רגרסיה חזותית לסרטוני הנתונים. כל תרחיש ב-tests/dataviz_visual.py מצויר
# מחדש ומושווה לתמונת הזהב שלו: הבדל ממוצע קטן ופחות מחצי אחוז פיקסלים שהשתנו הרבה (החלקת קצוות של גופן יכולה
# לזוז בפיקסל - תרשים ששבר משהו משנה הרבה יותר). כשל שומר את התמונה החדשה ליד הזהב, בשם <שם>.actual.png.
import os


import numpy as np
import pytest
from PIL import Image

from tests.dataviz_visual import SCENARIOS, golden_path, render_scenario

MAX_MEAN_DIFF = 2.0         # מתוך 255, בממוצע על כל הפיקסלים והערוצים
MAX_CHANGED_SHARE = 0.005   # פיקסלים שאחד הערוצים שלהם זז ביותר מ-64


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_frames_look_like_their_golden_images(tmp_path, scenario):
    actual = render_scenario(scenario, str(tmp_path))
    with Image.open(golden_path(scenario["name"])) as image:
        golden = np.asarray(image.convert("RGB"))
    assert actual.shape == golden.shape, f"{scenario['name']}: גודל {actual.shape} במקום {golden.shape}"
    diff = np.abs(actual.astype(int) - golden.astype(int))
    mean, changed = float(diff.mean()), float((diff.max(axis=2) > 64).mean())
    if mean > MAX_MEAN_DIFF or changed > MAX_CHANGED_SHARE:
        Image.fromarray(actual).save(golden_path(scenario["name"])[:-4] + ".actual.png")
        pytest.fail(f"{scenario['name']}: הבדל ממוצע {mean:.2f}, {changed:.2%} פיקסלים השתנו - ראו {scenario['name']}.actual.png")


def test_every_chart_type_has_a_golden_image():
    from dataviz.charts import CHART_MODULES
    names = {s["name"] for s in SCENARIOS}
    assert set(CHART_MODULES) <= names
    assert all(os.path.isfile(golden_path(name)) for name in names)
