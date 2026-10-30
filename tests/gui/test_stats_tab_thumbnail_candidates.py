# tests/gui/test_stats_tab_thumbnail_candidates.py
#
# בודק את חלק "A/B thumbnail testing" ב-ui/stats_tab.py - יצירת מועמדות
# (generate_candidates ממופתח, בלי ffmpeg אמיתי), הדיאלוג (תמונות אמיתיות
# דרך PIL, לא מזויפות), והגדרת תמונה (set_video_thumbnail ממופתח, בלי
# קריאת רשת אמיתית ל-YouTube).

from PIL import Image


import utils.media.game_playtime as game_playtime
import utils.bot.youtube_publish_log as youtube_publish_log
import utils.bot.youtube_thumbnail_log as youtube_thumbnail_log
from utils.shared import hardware_history, job_history
from ui.stats_tab import StatsTabComponent


class _ImmediateThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(game_playtime, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", str(tmp_path / "clips"))


def _make_real_jpeg(path):
    Image.new("RGB", (64, 64), color="red").save(path, "JPEG")


def test_generate_and_record_thumbnail_candidates_records_paths(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr("ui.stats_tab.generate_candidates", lambda video_path, out_dir, ffmpeg, ffprobe: ["/a.jpg", "/b.jpg"])

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp._generate_and_record_thumbnail_candidates("vid1", "/fake/clip.mp4")

        assert youtube_thumbnail_log.get_candidates("vid1") == [(0, "/a.jpg"), (1, "/b.jpg")]
    finally:
        comp.destroy()


def test_generate_and_record_thumbnail_candidates_never_raises(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)

    def _fail(*a, **kw):
        raise RuntimeError("ffmpeg exploded")

    monkeypatch.setattr("ui.stats_tab.generate_candidates", _fail)

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp._generate_and_record_thumbnail_candidates("vid1", "/fake/clip.mp4")  # לא אמור לזרוק
    finally:
        comp.destroy()


def test_analytics_row_shows_views_gained_since_switch(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    youtube_publish_log.record_upload("vid1", "clip.mp4", "My Clip")
    youtube_publish_log.update_cached_stats("vid1", views=150, likes=10, comments=1)
    youtube_thumbnail_log.record_switch("vid1", candidate_index=0, views_at_switch=100)

    comp = StatsTabComponent(shared_tk_root)
    try:
        texts = []
        for row in comp.yt_analytics_scroll.winfo_children():
            for w in row.winfo_children():
                try:
                    texts.append(w.cget("text"))
                except Exception:
                    pass
        assert any("+50" in text for text in texts)
    finally:
        comp.destroy()


def test_open_thumbnail_candidates_dialog_shows_empty_message(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp._open_thumbnail_candidates_dialog("vid1")
    finally:
        comp.destroy()


def test_open_thumbnail_candidates_dialog_shows_real_candidate_images(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    image_path = tmp_path / "candidate_0.jpg"
    _make_real_jpeg(image_path)
    youtube_thumbnail_log.record_candidates("vid1", [str(image_path)])

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp._open_thumbnail_candidates_dialog("vid1")
    finally:
        comp.destroy()


def test_set_video_thumbnail_records_switch_and_refreshes_list(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    youtube_publish_log.record_upload("vid1", "clip.mp4", "My Clip")
    youtube_publish_log.update_cached_stats("vid1", views=77, likes=5, comments=1)
    image_path = tmp_path / "candidate_0.jpg"
    _make_real_jpeg(image_path)
    youtube_thumbnail_log.record_candidates("vid1", [str(image_path)])
    monkeypatch.setattr("ui.stats_tab.youtube_analytics.set_video_thumbnail", lambda video_id, path: None)
    monkeypatch.setattr("ui.stats_tab.threading.Thread", _ImmediateThread)

    comp = StatsTabComponent(shared_tk_root)
    try:
        import customtkinter as ctk
        fake_dialog = ctk.CTkToplevel(comp)
        comp._set_video_thumbnail("vid1", 0, fake_dialog)
        comp._dispatcher.drain()

        latest = youtube_thumbnail_log.get_latest_switch("vid1")
        assert latest == (0, latest[1], 77)
    finally:
        comp.destroy()


def test_set_video_thumbnail_does_not_crash_on_api_failure(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    youtube_publish_log.record_upload("vid1", "clip.mp4", "My Clip")
    image_path = tmp_path / "candidate_0.jpg"
    _make_real_jpeg(image_path)
    youtube_thumbnail_log.record_candidates("vid1", [str(image_path)])

    def _fail(video_id, path):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr("ui.stats_tab.youtube_analytics.set_video_thumbnail", _fail)
    monkeypatch.setattr("ui.stats_tab.threading.Thread", _ImmediateThread)

    comp = StatsTabComponent(shared_tk_root)
    try:
        import customtkinter as ctk
        fake_dialog = ctk.CTkToplevel(comp)
        comp._set_video_thumbnail("vid1", 0, fake_dialog)
        comp._dispatcher.drain()

        assert youtube_thumbnail_log.get_latest_switch("vid1") is None
    finally:
        comp.destroy()
