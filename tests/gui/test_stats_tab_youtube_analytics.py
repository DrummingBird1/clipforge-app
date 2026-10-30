# tests/gui/test_stats_tab_youtube_analytics.py
#
# בודק את סעיף "📈 אנליטיקס YouTube" ב-side_card של ui/stats_tab.py (item:
# YouTube Analytics feedback loop) - utils/bot/youtube_publish_log.py/
# utils/bot/youtube_analytics.py ממופתחים, בלי קריאת רשת אמיתית ל-YouTube.
# refresh_youtube_analytics() מריץ thread רקע אמיתי - _ImmediateThread מריץ
# את ה-target באותו thread במקום, ו-_dispatcher.drain() מריץ ידנית את ה-
# callback שהופקד בתור (בלי לחכות ללולאת after האמיתית של Tk).


import utils.media.game_playtime as game_playtime
import utils.bot.youtube_publish_log as youtube_publish_log
from utils.shared import hardware_history, job_history
from utils.shared.i18n import t
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
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", str(tmp_path / "clips"))


def _row_texts(comp):
    texts = []
    for row in comp.yt_analytics_scroll.winfo_children():
        for w in row.winfo_children():
            try:
                texts.append(w.cget("text"))
            except Exception:
                pass
    return texts


def test_shows_empty_message_when_nothing_uploaded(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)

    comp = StatsTabComponent(shared_tk_root)
    try:
        assert t('עוד לא הועלו סרטונים דרך "📺 YouTube Export Pro".') in [
            w.cget("text") for w in comp.yt_analytics_scroll.winfo_children()
        ]
    finally:
        comp.destroy()


def test_shows_row_for_uploaded_video_with_unrefreshed_stats(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    youtube_publish_log.record_upload("vid1", "clip.mp4", "My Clip")

    comp = StatsTabComponent(shared_tk_root)
    try:
        texts = _row_texts(comp)
        assert "My Clip" in texts
        assert t("עוד לא רוענן") in texts
    finally:
        comp.destroy()


def test_shows_cached_stats_when_present(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    youtube_publish_log.record_upload("vid1", "clip.mp4", "My Clip")
    youtube_publish_log.update_cached_stats("vid1", views=100, likes=10, comments=2)

    comp = StatsTabComponent(shared_tk_root)
    try:
        texts = _row_texts(comp)
        assert any("100" in text and "10" in text and "2" in text for text in texts)
    finally:
        comp.destroy()


def test_refresh_does_nothing_when_youtube_not_configured(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr("ui.stats_tab.youtube_uploader.is_configured", lambda: False)
    calls = []
    monkeypatch.setattr("ui.stats_tab.youtube_analytics.get_video_stats", lambda vid: calls.append(vid) or {"views": 1, "likes": 1, "comments": 1})

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp.refresh_youtube_analytics()
        assert calls == []
    finally:
        comp.destroy()


def test_refresh_updates_cached_stats_and_rerenders(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    youtube_publish_log.record_upload("vid1", "clip.mp4", "My Clip")
    monkeypatch.setattr("ui.stats_tab.youtube_uploader.is_configured", lambda: True)
    monkeypatch.setattr("ui.stats_tab.youtube_analytics.get_video_stats", lambda vid: {"views": 42, "likes": 5, "comments": 1})
    monkeypatch.setattr("ui.stats_tab.threading.Thread", _ImmediateThread)

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp.refresh_youtube_analytics()
        comp._dispatcher.drain()

        texts = _row_texts(comp)
        assert any("42" in text for text in texts)
        assert comp.yt_analytics_refresh_btn.cget("text") == "🔄"
    finally:
        comp.destroy()


def test_refresh_skips_videos_with_no_stats_returned(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    youtube_publish_log.record_upload("vid1", "clip.mp4", "My Clip")
    monkeypatch.setattr("ui.stats_tab.youtube_uploader.is_configured", lambda: True)
    monkeypatch.setattr("ui.stats_tab.youtube_analytics.get_video_stats", lambda vid: None)
    monkeypatch.setattr("ui.stats_tab.threading.Thread", _ImmediateThread)

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp.refresh_youtube_analytics()
        comp._dispatcher.drain()

        assert t("עוד לא רוענן") in _row_texts(comp)
    finally:
        comp.destroy()


def test_upload_completion_refreshes_the_analytics_list(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)

    comp = StatsTabComponent(shared_tk_root)
    try:
        assert "clip.mp4" not in _row_texts(comp)

        youtube_publish_log.record_upload("vid1", "clip.mp4", "clip")
        comp._on_youtube_upload_done(True, "vid1")

        assert any("clip" in text for text in _row_texts(comp))
    finally:
        comp.destroy()
