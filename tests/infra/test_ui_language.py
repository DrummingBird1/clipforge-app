# tests/infra/test_ui_language.py
#
# 30.10.2026 (לפני ההפצה הציבורית): התקנה חדשה מתחילה באנגלית; config.json קיים בלי "language" נשאר בעברית, וההחלטה
# נכתבת לקובץ פעם אחת (utils/shared/ui_language.py).
import json

from utils.shared.install_profile import NEW_INSTALL
from utils.shared.ui_language import ensure_language


def _ensure(tmp_path):
    return ensure_language(str(tmp_path / "config.json"), str(tmp_path / "config.json.lock"))


def test_a_new_install_starts_in_english_and_remembers_it(tmp_path):
    assert _ensure(tmp_path) == "en"
    # 30.10.2026: באותה כתיבה גם ההגדרות הניטרליות של התקנה חדשה (utils/shared/install_profile)
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8")) == {**NEW_INSTALL, "language": "en"}


def test_an_existing_install_without_a_language_keeps_hebrew_once_and_for_all(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"theme": "Pink", "webhook": "x"}), encoding="utf-8")
    assert _ensure(tmp_path) == "he"
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8")) == {**NEW_INSTALL, "theme": "Pink", "webhook": "x",
                                                                                "language": "he"}
    assert _ensure(tmp_path) == "he"


def test_a_chosen_language_is_left_alone(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"language": "en", "theme": "Blue", **NEW_INSTALL}), encoding="utf-8")
    before = (tmp_path / "config.json").read_bytes()
    assert _ensure(tmp_path) == "en"
    assert (tmp_path / "config.json").read_bytes() == before


def test_current_reads_the_install_language_without_writing(tmp_path):
    from utils.shared.ui_language import current
    config = tmp_path / "config.json"
    assert current(str(config)) == "en" and not config.exists()                           # התקנה חדשה, ושום דבר לא נכתב
    config.write_text(json.dumps({"theme": "Pink"}), encoding="utf-8")
    assert current(str(config)) == "he" and "language" not in json.loads(config.read_text(encoding="utf-8"))
    config.write_text(json.dumps({"language": "en"}), encoding="utf-8")
    assert current(str(config)) == "en"


def test_a_broken_config_is_not_overwritten(tmp_path):
    (tmp_path / "config.json").write_text("{not json", encoding="utf-8")
    assert _ensure(tmp_path) == "he"
    assert (tmp_path / "config.json").read_text(encoding="utf-8") == "{not json"
