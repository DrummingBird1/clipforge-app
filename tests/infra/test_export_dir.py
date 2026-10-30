# tests/infra/test_export_dir.py
#
# 23.10.2026: תיקיית הייצוא (utils/shared/export_dir.py). ההגדרה בקובץ זמני לכל טסט - לא ב-data/ המשותף של הריצה, שכל
# ה-workers של xdist קוראים ממנו (הגדרה שם הייתה מפנה רינדורים של טסטים אחרים).
import json
import os

import pytest

from utils.shared import export_dir, workspace_dir


@pytest.fixture(autouse=True)
def settings(tmp_path, monkeypatch):
    path = tmp_path / "export_settings.json"
    monkeypatch.setattr(export_dir, "SETTINGS_PATH", str(path))
    monkeypatch.delenv(export_dir.ENV_VAR, raising=False)
    monkeypatch.setattr(export_dir, "_announced", False)
    return path


@pytest.fixture
def root(tmp_path):
    folder = tmp_path / "exports"
    folder.mkdir()
    return str(folder)


def test_nothing_set_means_workspace_as_before():
    assert export_dir.resolve() == (workspace_dir.WORKSPACE_DIR, None, None)
    assert export_dir.output_base() == workspace_dir.WORKSPACE_DIR


def test_a_saved_folder_receives_the_outputs(root, settings):
    export_dir.save_root(root)
    assert json.loads(settings.read_text(encoding="utf-8")) == {"root": root}
    assert export_dir.resolve() == (root, root, None)
    assert workspace_dir.tool_output_dir(workspace_dir.STUDIO, "vertical", base=export_dir.output_base()) == os.path.join(
        root, "studio", "vertical")


def test_an_unavailable_folder_falls_back_to_workspace_with_one_note(tmp_path, capsys):
    missing = str(tmp_path / "unplugged_drive" / "exports")
    export_dir.save_root(missing)
    resolution = export_dir.resolve()
    assert resolution.base == workspace_dir.WORKSPACE_DIR and resolution.root == missing and resolution.problem
    assert export_dir.output_base() == workspace_dir.WORKSPACE_DIR
    export_dir.output_base()
    printed = capsys.readouterr().out
    assert printed.count(missing) == 1 and "workspace" in printed   # שורה אחת ללוג, גם כשנקרא כמה פעמים


def test_a_folder_without_write_permission_falls_back(root, monkeypatch):
    export_dir.save_root(root)
    real_open = open

    def deny_probe(path, *args, **kwargs):
        if ".clipforge_write_test_" in str(path):
            raise PermissionError(13, "Access is denied", path)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(export_dir, "open", deny_probe, raising=False)
    assert export_dir.resolve().base == workspace_dir.WORKSPACE_DIR
    assert "כתיבה" in export_dir.resolve().problem
    assert os.listdir(root) == []   # קובץ הבדיקה לא נשאר


def test_the_env_var_overrides_the_setting(root, tmp_path, monkeypatch):
    export_dir.save_root(str(tmp_path))
    monkeypatch.setenv(export_dir.ENV_VAR, root)
    assert export_dir.resolve().base == root
    monkeypatch.setenv(export_dir.ENV_VAR, "")
    assert export_dir.resolve().base == workspace_dir.WORKSPACE_DIR


def test_choosing_workspace_itself_is_the_default():
    export_dir.save_root(workspace_dir.WORKSPACE_DIR)
    assert export_dir.configured_root() == "" and export_dir.resolve().root is None


def test_a_tool_with_its_own_folder_keeps_it_and_its_default_follows(root):
    export_dir.save_root(root)
    assert export_dir.follow_global("") == root
    assert export_dir.follow_global(workspace_dir.WORKSPACE_DIR) == root      # ברירת המחדל של Rocket
    assert export_dir.follow_global(r"D:\Rocket") == r"D:\Rocket"


def test_save_keeps_other_keys(root, settings):
    settings.write_text(json.dumps({"root": "", "tools": {"studio": "X"}}), encoding="utf-8")
    export_dir.save_root(root)
    assert json.loads(settings.read_text(encoding="utf-8")) == {"root": root, "tools": {"studio": "X"}}


def test_bad_choices_are_refused(tmp_path):
    assert export_dir.invalid_choice_reason("relative\\exports")
    assert "data/" in export_dir.invalid_choice_reason(os.path.join(export_dir.DATA_DIR, "exports"))
    assert export_dir.invalid_choice_reason(os.path.join(workspace_dir.PROJECT_ROOT, "src"))
    file_path = tmp_path / "a_file.txt"
    file_path.write_text("x", encoding="utf-8")
    assert export_dir.invalid_choice_reason(str(file_path))
    assert export_dir.invalid_choice_reason(str(tmp_path)) is None


def test_a_corrupt_settings_file_means_workspace(settings):
    settings.write_text("{not json", encoding="utf-8")
    assert export_dir.resolve().base == workspace_dir.WORKSPACE_DIR


# ---------- שלב 2: תיקייה לכלי ----------
def test_a_tool_folder_wins_and_receives_the_outputs_directly(root, tmp_path):
    export_dir.save_root(root)
    studio = tmp_path / "studio_out"
    studio.mkdir()
    export_dir.save_tool_root(workspace_dir.STUDIO, str(studio))
    assert export_dir.output_dir(workspace_dir.STUDIO, "vertical") == os.path.join(str(studio), "vertical")   # בלי "studio/"
    assert export_dir.output_dir(workspace_dir.TIMELAPSES, "horizontal") == os.path.join(root, "timelapses", "horizontal")


def test_an_unavailable_tool_folder_falls_back_to_workspace_with_a_note(root, tmp_path, capsys):
    export_dir.save_root(root)
    missing = str(tmp_path / "unplugged_studio")
    export_dir.save_tool_root(workspace_dir.STUDIO, missing)
    assert export_dir.output_dir(workspace_dir.STUDIO, "vertical") == os.path.join(workspace_dir.WORKSPACE_DIR, "studio", "vertical")
    assert missing in capsys.readouterr().out


def test_the_env_var_overrides_a_tool_folder_too(root, tmp_path, monkeypatch):
    export_dir.save_tool_root(workspace_dir.STUDIO, str(tmp_path))
    monkeypatch.setenv(export_dir.ENV_VAR, root)
    assert export_dir.output_dir(workspace_dir.STUDIO, "vertical") == os.path.join(root, "studio", "vertical")


def test_clearing_a_tool_folder_keeps_the_rest(root, tmp_path, settings):
    export_dir.save_root(root)
    export_dir.save_tool_root(workspace_dir.STUDIO, str(tmp_path))
    export_dir.save_tool_root(workspace_dir.STUDIO, "")
    assert json.loads(settings.read_text(encoding="utf-8")) == {"root": root, "tools": {}}


def test_configured_folders_list_every_place_outputs_can_be(root, tmp_path):
    export_dir.save_root(root)
    export_dir.save_tool_root(workspace_dir.STUDIO, str(tmp_path))
    folders = export_dir.configured_folders()
    assert (workspace_dir.STUDIO, os.path.join(root, "studio")) in folders and (workspace_dir.STUDIO, str(tmp_path)) in folders
    assert {tool for tool, _ in folders} == set(workspace_dir.TOOLS)
