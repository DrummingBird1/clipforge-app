# tests/infra/test_workspace_output_layout.py
#
# 19.10.2026: תוצרים לפי כלי ואז לפי כיוון/יעד - workspace/studio/horizontal במקום workspace/horizontal/edited_videos.
# utils.shared.workspace_dir בונה את החדש, יודע מה הישן המקביל, וקוראים מקבלים את הישן רק כשרק הוא קיים.
import os

from utils.shared import workspace_dir as layout


def test_new_paths_are_tool_first(tmp_path):
    base = str(tmp_path)
    assert layout.tool_output_dir(layout.STUDIO, "vertical", base=base) == os.path.join(base, "studio", "vertical")
    assert layout.tool_output_dir(layout.DATAVIZ, "outputs", "square", base=base) == os.path.join(base, "dataviz", "outputs", "square")
    assert layout.tool_output_dir(layout.ROCKET_SHORTS, "TikTok", base=base) == os.path.join(base, "rocket_shorts", "TikTok")


def test_each_new_path_knows_its_old_orientation_first_path(tmp_path):
    base = str(tmp_path)
    cases = {
        (layout.STUDIO, "horizontal", "tiktok"): ("horizontal", "edited_videos", "tiktok"),
        (layout.TIMELAPSES, "vertical"): ("vertical", "timelapses"),
        (layout.HIGHLIGHT_REELS, "horizontal"): ("horizontal", "highlight_reels"),
        (layout.DATAVIZ, "outputs", "square"): ("square", "dataviz"),
        (layout.DATAVIZ, "studio_handoff", "vertical", "ep"): ("vertical", "dataviz_studio", "ep"),
        (layout.ROCKET_SHORTS, "YouTube"): ("horizontal", "YouTube"),
        (layout.ROCKET_SHORTS, "TikTok"): ("vertical", "TikTok"),
        (layout.ROCKET_SHORTS, "Instagram"): ("vertical", "Instagram"),
        (layout.ROCKET_SHORTS, "square"): ("square",),
    }
    for new, old in cases.items():
        assert layout.legacy_output_dir(*new, base=base) == os.path.join(base, *old), new
    assert layout.legacy_output_dir("clips", base=base) is None


def test_readers_use_the_old_folder_only_when_only_it_exists(tmp_path):
    base = str(tmp_path)
    new = os.path.join(base, "rocket_shorts", "YouTube")
    old = os.path.join(base, "horizontal", "YouTube")
    assert layout.existing_output_dir(layout.ROCKET_SHORTS, "YouTube", base=base) == new     # אף אחת - החדשה
    os.makedirs(old)
    assert layout.existing_output_dir(layout.ROCKET_SHORTS, "YouTube", base=base) == old     # רק הישנה
    os.makedirs(new)
    assert layout.existing_output_dir(layout.ROCKET_SHORTS, "YouTube", base=base) == new     # שתיהן - החדשה


def test_scripts_write_through_the_helper_not_orientation_first():
    # אף כותב לא בונה עוד <כיוון>/edited_videos|timelapses|highlight_reels|YouTube|TikTok בעצמו
    from tests import PROJECT_ROOT
    scripts = ["video_editor.py", "timelapse_maker.py", "highlight_reel_maker.py", "rocket_shorts_publisher.py",
               "weekly_compilation.py", "wrapped_generator.py"]
    for name in scripts:
        source = open(os.path.join(PROJECT_ROOT, "my_scripts", "video", name), encoding="utf-8").read()
        for old in ('"edited_videos"', '"timelapses")', '"highlight_reels")', '"horizontal", "YouTube"', '"vertical", "TikTok"'):
            assert old not in source, (name, old)
