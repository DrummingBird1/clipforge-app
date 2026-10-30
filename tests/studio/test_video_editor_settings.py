# tests/studio/test_video_editor_settings.py - גל 37: אובייקט ההגדרות של ריצה (utils/video/video_editor_settings.py)
import pytest

from utils.video.video_editor_cli import build_parser
from utils.video.video_editor_settings import VideoEditorSettings


def test_defaults_match_the_parser_for_every_flag():
    settings = VideoEditorSettings.from_argv([])
    defaults = vars(build_parser().parse_args([]))
    assert settings.as_dict() == defaults
    assert len(settings) == len(defaults) > 100


def test_values_from_argv_and_attribute_access():
    settings = VideoEditorSettings.from_argv(["--codec", "hevc", "--nvenc-cq", "22", "--vertical"])
    assert settings.codec == "hevc" and settings["nvenc_cq"] == 22 and settings.vertical is True
    with pytest.raises(AttributeError):
        _ = settings.no_such_setting


def test_read_only_and_overrides_make_a_copy():
    settings = VideoEditorSettings.from_argv(["--watermark_path", "C:/logo.png"])
    with pytest.raises(AttributeError):
        settings.codec = "av1"
    clip = settings.with_overrides({"watermark_path": "C:/other.png", "not_a_setting": 1})
    assert clip.watermark_path == "C:/other.png" and settings.watermark_path == "C:/logo.png"
    assert "not_a_setting" not in clip


def test_the_script_builds_the_settings_object():
    source = open("my_scripts/video/video_editor.py", encoding="utf-8").read()
    assert "SETTINGS = VideoEditorSettings.from_args(args)" in source
