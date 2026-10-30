# tests/studio/test_video_editor_counter.py
#
# מונה מתמשך למספור סרטונים (item) - utils/video/video_editor_counter.py, אותו
# עיקרון בדיוק כמו rocket_shorts_publisher.py's get_next_number/save_current_number
# אבל בקובץ נפרד ומקבל counter_path כפרמטר (לא global קשיח) - כדי שהטסטים
# האלה יריצו על קובץ זמני, לא על data/video_editor_counter.txt האמיתי.
import os


from utils.video.video_editor_counter import get_next_number, save_number


def test_get_next_number_creates_file_with_start_value_when_missing(tmp_path):
    counter_path = str(tmp_path / "counter.txt")
    assert not os.path.exists(counter_path)

    assert get_next_number(start=5, counter_path=counter_path) == 5
    assert os.path.exists(counter_path)
    with open(counter_path, "r", encoding="utf-8") as f:
        assert f.read().strip() == "5"


def test_get_next_number_default_start_is_one(tmp_path):
    counter_path = str(tmp_path / "counter.txt")
    assert get_next_number(counter_path=counter_path) == 1


def test_get_next_number_reads_existing_value_ignoring_start(tmp_path):
    counter_path = str(tmp_path / "counter.txt")
    save_number(42, counter_path=counter_path)
    # start מתעלם - הקובץ הקיים תמיד מנצח (item: "לזכור את המספור האחרון").
    assert get_next_number(start=1, counter_path=counter_path) == 42


def test_get_next_number_corrupt_file_falls_back_to_start(tmp_path):
    counter_path = str(tmp_path / "counter.txt")
    with open(counter_path, "w", encoding="utf-8") as f:
        f.write("not-a-number")
    assert get_next_number(start=3, counter_path=counter_path) == 3


def test_save_number_creates_parent_directory(tmp_path):
    counter_path = str(tmp_path / "nested" / "counter.txt")
    save_number(9, counter_path=counter_path)
    assert os.path.exists(counter_path)
    with open(counter_path, "r", encoding="utf-8") as f:
        assert f.read().strip() == "9"


def test_save_and_get_round_trip(tmp_path):
    counter_path = str(tmp_path / "counter.txt")
    save_number(100, counter_path=counter_path)
    assert get_next_number(counter_path=counter_path) == 100
