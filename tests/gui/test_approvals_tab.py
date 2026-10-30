# tests/gui/test_approvals_tab.py
#
# בודק ui/approvals_tab.py (item: mobile-friendly clip-approval view) - גרסת
# הדסקטופ לטאב "אישור קליפים" שגם web_app.py מציג. thumbnail extraction נכשל
# בשקט על בתים מזויפים (לא mp4 אמיתי) - בדיוק כמו שהקוד עצמו מצפה (try/except
# רחב ב-_load_thumbnail), אז אין צורך ב-ffmpeg אמיתי בטסטים האלה.


import utils.bot.approval_store as approval_store
from utils.shared import db
from utils.shared.i18n import t
from ui.approvals_tab import ApprovalsTabComponent


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(approval_store, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(approval_store, "CLIPS_REVIEW_DIR", str(tmp_path / "clips"))
    monkeypatch.setattr(approval_store, "REJECTED_DIR", str(tmp_path / "rejected"))
    monkeypatch.setattr(approval_store, "get_rocket_input_dir", lambda: str(tmp_path / "rocket_input"))


def _insert_pending(db_path, video_path):
    with db.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS pending_approvals ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, video_path TEXT UNIQUE, "
            "status TEXT DEFAULT 'pending', channel_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        cursor = conn.execute(
            "INSERT INTO pending_approvals (video_path, status, channel_id) VALUES (?, 'pending', ?)",
            (video_path, 123),
        )
    return cursor.lastrowid


def _card_texts(comp):
    texts = []
    for card in comp.scroll.winfo_children():
        for w in card.winfo_children():
            try:
                texts.append(w.cget("text"))
            except Exception:
                pass
            for child in w.winfo_children():
                try:
                    texts.append(child.cget("text"))
                except Exception:
                    pass
    return texts


def test_shows_empty_message_when_no_pending_approvals(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)

    comp = ApprovalsTabComponent(shared_tk_root)
    try:
        assert t("אין קליפים שממתינים לאישור כרגע.") in _card_texts(comp) or any(
            w.cget("text") == t("אין קליפים שממתינים לאישור כרגע.") for w in comp.scroll.winfo_children()
        )
    finally:
        comp.destroy()


def test_shows_card_for_pending_clip(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    game_dir = tmp_path / "clips" / "SomeGame"
    game_dir.mkdir(parents=True)
    clip = game_dir / "clip.mp4"
    clip.write_bytes(b"fake")
    _insert_pending(str(tmp_path / "test.db"), str(clip))

    comp = ApprovalsTabComponent(shared_tk_root)
    try:
        texts = _card_texts(comp)
        assert "clip.mp4" in texts
        assert any("SomeGame" in text for text in texts)
    finally:
        comp.destroy()


def test_skips_rows_whose_file_no_longer_exists(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    _insert_pending(str(tmp_path / "test.db"), str(tmp_path / "clips" / "gone.mp4"))

    comp = ApprovalsTabComponent(shared_tk_root)
    try:
        texts = _card_texts(comp)
        assert "gone.mp4" not in texts
    finally:
        comp.destroy()


def test_approve_moves_clip_and_removes_card(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    clip = clips_dir / "clip.mp4"
    clip.write_bytes(b"fake")
    pending_id = _insert_pending(str(tmp_path / "test.db"), str(clip))

    comp = ApprovalsTabComponent(shared_tk_root)
    try:
        assert len(comp.scroll.winfo_children()) == 1
        comp._decide(pending_id, str(clip), True)

        assert not clip.exists()
        assert (tmp_path / "rocket_input" / "clip.mp4").exists()
        assert "clip.mp4" not in _card_texts(comp)
    finally:
        comp.destroy()


def test_reject_moves_clip_to_rejected_dir(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    clip = clips_dir / "clip.mp4"
    clip.write_bytes(b"fake")
    pending_id = _insert_pending(str(tmp_path / "test.db"), str(clip))

    comp = ApprovalsTabComponent(shared_tk_root)
    try:
        comp._decide(pending_id, str(clip), False)

        assert not clip.exists()
        assert (tmp_path / "rejected" / "clip.mp4").exists()
    finally:
        comp.destroy()


def test_refresh_approvals_picks_up_newly_added_pending_clip(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()

    comp = ApprovalsTabComponent(shared_tk_root)
    try:
        assert "clip.mp4" not in _card_texts(comp)

        clip = clips_dir / "clip.mp4"
        clip.write_bytes(b"fake")
        _insert_pending(str(tmp_path / "test.db"), str(clip))
        comp.refresh_approvals()

        assert "clip.mp4" in _card_texts(comp)
    finally:
        comp.destroy()
