# tests/gui/test_stats_tab_gallery_filter.py
#
# בודק את חיפוש+סינון-לפי-תגית בגלריית הקליפים של ui/stats_tab.py
# (item: clip gallery search/filter by tag) - אותו מטמון תגיות בדיוק כמו
# web_app.py (utils/media/clip_tagger.py), נקרא כאן בלי תלות ב-AI אמיתי.
import json
import os


from utils.shared import hardware_history, job_history
from utils.media.clip_tagger import tags_cache_path
from utils.shared.i18n import t
from ui.stats_tab import ALL_TAGS_LABEL, StatsTabComponent


def _button_texts(comp):
    texts = []
    for w in comp.scroll.winfo_children():
        try:
            texts.append(w.cget("text"))
        except Exception:
            pass
    return texts


def _make_clip(clips_dir, name):
    os.makedirs(clips_dir, exist_ok=True)
    path = os.path.join(clips_dir, name)
    with open(path, "wb") as f:
        f.write(b"fake-mp4-bytes")
    return path


def _tag_clip(cache_dir, clip_path, tags):
    os.makedirs(cache_dir, exist_ok=True)
    with open(tags_cache_path(clip_path, cache_dir), "w", encoding="utf-8") as f:
        json.dump({"tags": tags}, f)


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    clips_dir = str(tmp_path / "clips")
    cache_dir = str(tmp_path / ".tags_cache")
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", clips_dir)
    monkeypatch.setattr("ui.stats_tab.TAGS_CACHE_DIR", cache_dir)
    return clips_dir, cache_dir


def test_gallery_shows_all_clips_by_default(tmp_path, monkeypatch, shared_tk_root):
    clips_dir, _ = _setup(tmp_path, monkeypatch)
    _make_clip(clips_dir, "goal_clip.mp4")
    _make_clip(clips_dir, "save_clip.mp4")

    comp = StatsTabComponent(shared_tk_root)
    try:
        texts = _button_texts(comp)
        assert "goal_clip.mp4" in texts
        assert "save_clip.mp4" in texts
    finally:
        comp.destroy()


def test_gallery_search_filters_by_name(tmp_path, monkeypatch, shared_tk_root):
    clips_dir, _ = _setup(tmp_path, monkeypatch)
    _make_clip(clips_dir, "goal_clip.mp4")
    _make_clip(clips_dir, "save_clip.mp4")

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp.gallery_search_var.set("goal")

        texts = _button_texts(comp)
        assert "goal_clip.mp4" in texts
        assert "save_clip.mp4" not in texts
    finally:
        comp.destroy()


def test_gallery_tag_dropdown_populates_from_cache(tmp_path, monkeypatch, shared_tk_root):
    clips_dir, cache_dir = _setup(tmp_path, monkeypatch)
    goal_clip = _make_clip(clips_dir, "goal_clip.mp4")
    _make_clip(clips_dir, "untagged_clip.mp4")
    _tag_clip(cache_dir, goal_clip, ["Goal", "Victory"])

    comp = StatsTabComponent(shared_tk_root)
    try:
        values = comp.gallery_tag_menu.cget("values")
        assert values[0] == t(ALL_TAGS_LABEL)
        assert "Goal" in values
        assert "Victory" in values
    finally:
        comp.destroy()


def test_gallery_tag_filter_shows_only_matching_clips(tmp_path, monkeypatch, shared_tk_root):
    clips_dir, cache_dir = _setup(tmp_path, monkeypatch)
    goal_clip = _make_clip(clips_dir, "goal_clip.mp4")
    save_clip = _make_clip(clips_dir, "save_clip.mp4")
    _tag_clip(cache_dir, goal_clip, ["Goal"])
    _tag_clip(cache_dir, save_clip, ["Save"])

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp.gallery_tag_var.set("Goal")
        comp._render_gallery()

        texts = _button_texts(comp)
        assert "goal_clip.mp4" in texts
        assert "save_clip.mp4" not in texts
    finally:
        comp.destroy()


def test_gallery_all_tags_selection_shows_untagged_clips_too(tmp_path, monkeypatch, shared_tk_root):
    clips_dir, cache_dir = _setup(tmp_path, monkeypatch)
    goal_clip = _make_clip(clips_dir, "goal_clip.mp4")
    _make_clip(clips_dir, "untagged_clip.mp4")
    _tag_clip(cache_dir, goal_clip, ["Goal"])

    comp = StatsTabComponent(shared_tk_root)
    try:
        texts = _button_texts(comp)
        assert "goal_clip.mp4" in texts
        assert "untagged_clip.mp4" in texts
    finally:
        comp.destroy()


def test_refresh_gallery_resets_tag_filter_when_selection_no_longer_exists(tmp_path, monkeypatch, shared_tk_root):
    clips_dir, cache_dir = _setup(tmp_path, monkeypatch)
    comp = StatsTabComponent(shared_tk_root)
    try:
        comp.gallery_tag_var.set("Stale")
        comp.refresh_gallery()

        assert comp.gallery_tag_var.get() == t(ALL_TAGS_LABEL)
    finally:
        comp.destroy()