# tests/web/test_web_app_portable_update.py
#
# 30.10.2026: בחבילה הניידת (portable.json בשורש) אין git ואין uv - "יש גרסה חדשה" מציג רק קישור ל-Release, ו-/apply מסרב
# במקום להריץ git pull.
from tests.web_app_support import client, web_app


def test_a_git_checkout_reports_not_portable(monkeypatch):
    monkeypatch.setattr(web_app, "check_for_update", lambda *_a, **_k: None)
    data = client.get("/api/update_check").json()
    assert data["portable"] is False and data["releases_url"] == web_app.RELEASES_PAGE_URL


def test_the_portable_package_reports_portable_and_refuses_git_pull(monkeypatch, tmp_path):
    from utils.shared import update_checker
    (tmp_path / update_checker.PORTABLE_MARKER).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(web_app, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(web_app, "check_for_update", lambda *_a, **_k: "v9.9.9")

    def no_git_pull(*_a, **_k):
        raise AssertionError("apply_update ran in the portable package")

    monkeypatch.setattr(web_app, "apply_update", no_git_pull)
    data = client.get("/api/update_check").json()
    assert data["portable"] is True and data["latest_version"] == "v9.9.9"
    resp = client.post("/api/update_check/apply")
    assert resp.status_code == 400 and resp.json()["error"] == update_checker.PORTABLE_UPDATE_REFUSAL


def test_new_versions_come_from_the_public_repository():
    """30.10.2026: הגרסאות יוצאות ב-DrummingBird1/clipforge-app; הריפו הפרטי clipforge לא מפרסם Releases."""
    assert web_app.RELEASES_PAGE_URL == "https://github.com/DrummingBird1/clipforge-app/releases/latest"
