# tests/infra/test_outputs_index.py
#
# 23.10.2026: הסורק של מסך "תוצרים" (utils/shared/outputs_index.py). workspace, תיקיות הייצוא וההגדרה זמניים לכל טסט.
import os
import sys

import pytest

from utils.shared import export_dir, outputs_index


@pytest.fixture(autouse=True)
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr(export_dir, "SETTINGS_PATH", str(tmp_path / "export_settings.json"))
    monkeypatch.delenv(export_dir.ENV_VAR, raising=False)


@pytest.fixture
def ws(tmp_path):
    return tmp_path / "workspace"


def _video(path, mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


def _names(ws):
    return [item["name"] for item in outputs_index.scan(str(ws))]


def _link_dir(link, target):
    if sys.platform == "win32":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def test_outputs_of_every_tool_newest_first(ws):
    _video(ws / "studio" / "horizontal" / "edited.mp4", 1_000_000)
    _video(ws / "timelapses" / "vertical" / "lapse.mov", 3_000_000)
    _video(ws / "rocket_shorts" / "TikTok" / "short.mp4", 2_000_000)
    episode = _video(ws / "dataviz" / "outputs" / "horizontal" / "episode.mp4", 4_000_000)
    items = outputs_index.scan(str(ws))
    assert [(i["name"], i["tool"], i["folder"]) for i in items] == [
        ("episode.mp4", "dataviz", "horizontal"), ("lapse.mov", "timelapses", "vertical"),
        ("short.mp4", "rocket_shorts", "TikTok"), ("edited.mp4", "studio", "horizontal")]
    assert items[0]["path"] == os.path.normpath(episode) and items[0]["size"] == 1 and items[0]["mtime"] == 4_000_000


def test_internal_folders_and_unfinished_files_are_not_outputs(ws):
    _video(ws / "studio" / "horizontal" / "done.mp4")
    _video(ws / "dataviz" / "outputs" / "horizontal" / "ep_shorts_1.mp4")
    for skipped in ("studio/horizontal/_sig/done.mp4", "studio/horizontal/_previous/old.mp4",
                    "studio/studio_handoff/horizontal/a/a.mp4", "studio/horizontal/done.partial.mp4",
                    "studio/horizontal/notes.txt", "studio/horizontal/.hidden.mp4", "studio/.cache/x.mp4",
                    "dataviz/outputs/horizontal/ep_test.mp4", "dataviz/outputs/horizontal/ep_preview.mp4",
                    "dataviz/outputs/horizontal/ep_stills/a.mp4", "dataviz/outputs/horizontal/ep_share/a.mp4",
                    "dataviz/staging/x/raw.mp4", "dataviz/studio_handoff/horizontal/ep/ep.mp4", "clips/clip.mp4"):
        _video(ws.joinpath(*skipped.split("/")))
    assert sorted(_names(ws)) == ["done.mp4", "ep_shorts_1.mp4"]


def test_the_export_folder_and_a_tools_own_folder(ws, tmp_path):
    exports, own = tmp_path / "exports", tmp_path / "MyStudio"
    _video(exports / "timelapses" / "horizontal" / "a.mp4")
    _video(exports / "dataviz" / "outputs" / "vertical" / "c.mp4")
    _video(own / "vertical" / "b.mp4")
    export_dir.save_root(str(exports))
    export_dir.save_tool_root("studio", str(own))
    found = {i["name"]: (i["tool"], i["folder"]) for i in outputs_index.scan(str(ws))}
    assert found == {"a.mp4": ("timelapses", "horizontal"), "b.mp4": ("studio", "vertical"), "c.mp4": ("dataviz", "vertical")}


def test_the_same_folder_twice_is_listed_once(ws, tmp_path):
    exports = tmp_path / "exports"
    _video(exports / "studio" / "horizontal" / "a.mp4")
    export_dir.save_root(str(exports))
    export_dir.save_tool_root("studio", str(exports / "studio"))
    assert _names(ws) == ["a.mp4"]


def test_limit_and_depth(ws):
    for n in range(3):
        _video(ws / "studio" / "horizontal" / f"v{n}.mp4", 1_000_000 + n)
    assert [i["name"] for i in outputs_index.scan(str(ws), limit=2)] == ["v2.mp4", "v1.mp4"]
    _video(ws / "studio" / "a" / "b" / "c" / "deep_enough.mp4")
    _video(ws / "studio" / "a" / "b" / "c" / "d" / "too_deep.mp4")
    names = _names(ws)
    assert "deep_enough.mp4" in names and "too_deep.mp4" not in names


def test_a_junction_to_another_folder_is_not_followed(ws, tmp_path):
    _video(tmp_path / "elsewhere" / "private.mp4")
    (ws / "studio").mkdir(parents=True)
    _link_dir(ws / "studio" / "link", tmp_path / "elsewhere")
    assert (ws / "studio" / "link" / "private.mp4").is_file()
    assert _names(ws) == []
    assert outputs_index.locate(str(ws / "studio" / "link" / "private.mp4"), str(ws)) is None


def test_locate_finds_the_tool_and_folder_of_an_output_only(ws, tmp_path):
    video = _video(ws / "rocket_shorts" / "TikTok" / "a.mp4")
    assert outputs_index.locate(str(video), str(ws)) == {"path": os.path.realpath(video), "tool": "rocket_shorts", "folder": "TikTok"}
    root_level = _video(ws / "studio" / "b.mp4")
    assert outputs_index.locate(str(root_level), str(ws))["folder"] == ""
    _video(tmp_path / "outside.mp4")
    sneaky = os.path.join(str(ws), "studio", "..", "..", "outside.mp4")
    for refused in (str(tmp_path / "outside.mp4"), sneaky, str(_video(ws / "studio" / "horizontal" / "_previous" / "old.mp4")),
                    str(_video(ws / "studio" / "horizontal" / "notes.txt")), str(ws / "studio" / "missing.mp4"), ""):
        assert outputs_index.locate(refused, str(ws)) is None, refused
