# tests/dataviz/test_web_app_dataviz.py
#
# /api/dataviz/packages* (entrypoints/web/routes/dataviz.py): רשימת חבילות הפרסום של סרטוני נתונים,
# תמונה ממוזערת, דף SEO ואישור/דחייה. חבילות אמיתיות מ-utils.dataviz_publish.prepare_publish (תמונה
# מזויפת בלבד), בתיקיית workspace זמנית. בדיקה שאין שום העלאה: רק הקובץ .publish.json משתנה.
import os


import pytest
from fastapi.testclient import TestClient

from dataviz.config import load_config
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from dataviz.web import publish as dp

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _fake_thumb(video, out, **kwargs):
    with open(out, "wb") as f:
        f.write(b"\xff\xd8\xff\xe0fakejpeg")


def make_package(workspace, name, orientation="horizontal", title="פרק בדיקה", thumbnail=True, **publish):
    folder = workspace / "dataviz" / "outputs" / orientation
    folder.mkdir(parents=True, exist_ok=True)
    config = load_config(os.path.join(write_episode(workspace / "_eps", overrides={"title": title, "publish": publish}, name=name),
                                      "config.yaml"))
    (folder / f"{name}.mp4").write_bytes(b"video")
    return dp.prepare_publish(str(folder / f"{name}.mp4"), config,
                              make_thumbnail=_fake_thumb if thumbnail else None) if thumbnail else \
        dp.prepare_publish(str(folder / f"{name}.mp4"), {**config, "publish": {**config["publish"], "thumbnail": False}})


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(tmp_path))
    return tmp_path


def test_empty_workspace_lists_nothing(workspace):
    assert client.get("/api/dataviz/packages").json() == []


def test_list_shows_packages_from_all_orientations_pending_first(workspace):
    make_package(workspace, "old", title="ישן")
    make_package(workspace, "vert", orientation="vertical", title="אנכי")
    dp.set_decision(str(workspace / "dataviz" / "outputs" / "horizontal" / "old.mp4"), dp.APPROVED)

    rows = client.get("/api/dataviz/packages").json()

    assert [(r["id"], r["status"]) for r in rows] == [("vertical/vert", "pending_approval"), ("horizontal/old", "approved")]
    first = rows[0]
    assert first["title"] == "אנכי" and first["youtube_title"] == "אנכי"
    assert first["has_thumbnail"] and first["video_exists"] and "#dataviz" in first["hashtags"]
    assert first["steps"] == {"seo": "ok", "thumbnail": "ok"}


def test_missing_thumbnail_and_video_are_reported_not_hidden(workspace):
    make_package(workspace, "nothumb", thumbnail=False)
    (workspace / "dataviz" / "outputs" / "horizontal" / "nothumb.mp4").unlink()

    row = client.get("/api/dataviz/packages").json()[0]

    assert row["has_thumbnail"] is False and row["video_exists"] is False
    assert client.get("/api/dataviz/packages/horizontal/nothumb/thumbnail").status_code == 404


def test_detail_includes_the_seo_sheet_and_thumbnail_is_served(workspace):
    make_package(workspace, "ep", title="כותרת מיוחדת")

    detail = client.get("/api/dataviz/packages/horizontal/ep").json()
    thumb = client.get("/api/dataviz/packages/horizontal/ep/thumbnail")

    assert "[YOUTUBE TITLE]:\nכותרת מיוחדת" in detail["sheet"]
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg" and thumb.content.startswith(b"\xff\xd8")


@pytest.mark.parametrize("orientation,name", [
    ("nowhere", "ep"), ("horizontal", "missing"), ("horizontal", "..%2F..%2Fsecret"), ("horizontal", ".hidden"),
    ("horizontal", "a%5Cb"),
])
def test_unknown_or_traversal_names_are_404(workspace, orientation, name):
    make_package(workspace, "ep")
    (workspace / "secret.publish.json").write_text('{"status": "pending_approval"}', encoding="utf-8")

    assert client.get(f"/api/dataviz/packages/{orientation}/{name}").status_code == 404
    assert client.post(f"/api/dataviz/packages/{orientation}/{name}/decide", json={"decision": "approved"}).status_code == 404
    assert client.get(f"/api/dataviz/packages/{orientation}/{name}/thumbnail").status_code == 404


def test_approve_changes_only_the_status_and_cannot_be_overwritten(workspace):
    make_package(workspace, "ep")
    folder = workspace / "dataviz" / "outputs" / "horizontal"
    before = sorted(p.name for p in folder.iterdir())

    resp = client.post("/api/dataviz/packages/horizontal/ep/decide", json={"decision": "approved"})

    assert resp.status_code == 200 and resp.json()["status"] == "approved" and resp.json()["decided_at"]
    assert dp.load_package(str(folder / "ep.mp4"))["status"] == dp.APPROVED
    assert sorted(p.name for p in folder.iterdir()) == before          # שום קובץ לא נוצר/הוזז/נמחק
    again = client.post("/api/dataviz/packages/horizontal/ep/decide", json={"decision": "rejected"})
    assert again.status_code == 400 and "כבר התקבלה החלטה" in again.json()["error"]


def test_reject_and_bad_payloads(workspace):
    make_package(workspace, "ep")
    url = "/api/dataviz/packages/horizontal/ep/decide"

    assert client.post(url, json={"decision": "maybe"}).status_code == 400
    assert client.post(url, json={}).status_code == 400
    assert client.post(url, content=b"not json", headers={"Content-Type": "application/json"}).status_code == 400
    assert client.post(url, json={"decision": "rejected"}).json()["status"] == "rejected"


def test_decide_rejects_a_foreign_origin(workspace):
    make_package(workspace, "ep")

    resp = client.post("/api/dataviz/packages/horizontal/ep/decide", json={"decision": "approved"},
                       headers={"Origin": "http://evil.example", "Host": "127.0.0.1:8878"})

    assert resp.status_code == 403
    assert dp.load_package(str(workspace / "dataviz" / "outputs" / "horizontal" / "ep.mp4"))["status"] == dp.PENDING


def test_decide_is_recorded_in_the_audit_log(workspace, monkeypatch):
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: calls.append((a, k)))
    make_package(workspace, "ep")

    client.post("/api/dataviz/packages/horizontal/ep/decide", json={"decision": "approved"})

    assert calls and calls[0][0][1] == "dataviz_decide" and calls[0][1]["details"] == "horizontal/ep=approved"

# ---------- שליחת חבילה שאושרה (dry-run / Rocket / YouTube) - בטסטים אף פעם לא מעלים באמת ----------

def _approved(workspace, name="send"):
    make_package(workspace, name, title="כותרת לשליחה")
    dp.set_decision(str(workspace / "dataviz" / "outputs" / "horizontal" / f"{name}.mp4"), dp.APPROVED)
    return f"/api/dataviz/packages/horizontal/{name}/send"


class _NoUpload:
    """מחליף את מעלה היוטיוב: סופר קריאות, לא נוגע ברשת."""
    def __init__(self, monkeypatch, configured=True):
        self.calls = []
        self.thumbnails = []
        monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: configured)
        monkeypatch.setattr(web_app.youtube_uploader, "upload_video", self._upload)
        monkeypatch.setattr(web_app.youtube_uploader, "set_thumbnail", lambda video_id, path: self.thumbnails.append((video_id, path)))   # גל 55
        monkeypatch.setattr(web_app.youtube_publish_log, "record_upload", lambda *a, **k: None)

    def _upload(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return "FAKEID"


def test_send_dry_run_changes_nothing_and_shows_the_plan(workspace, monkeypatch):
    fake = _NoUpload(monkeypatch)
    url = _approved(workspace)
    sidecar = workspace / "dataviz" / "outputs" / "horizontal" / "send.publish.json"
    before = sidecar.read_bytes()
    body = client.post(url, json={}).json()
    assert body["dry_run"] is True and body["plan"]["privacy"] == "private" and body["plan"]["video"] == "send.mp4"
    assert "כותרת לשליחה" in body["plan"]["title"] and sidecar.read_bytes() == before and fake.calls == []


def test_send_requires_an_approved_package_and_an_explicit_confirmation(workspace, monkeypatch):
    fake = _NoUpload(monkeypatch)
    make_package(workspace, "pend")
    assert client.post("/api/dataviz/packages/horizontal/pend/send", json={"target": "youtube", "confirm": True}).status_code == 400
    url = _approved(workspace)
    assert client.post(url, json={"target": "youtube"}).status_code == 400
    assert client.post(url, json={"target": "youtube", "confirm": "yes"}).status_code == 400
    assert client.post(url, json={"target": "ftp", "confirm": True}).status_code == 400
    assert client.post(url, json={"target": "rocket"}).status_code == 400
    assert fake.calls == []


def test_send_to_rocket_copies_once_and_never_overwrites(workspace, monkeypatch, tmp_path):
    rocket = tmp_path / "rocket_in"
    monkeypatch.setattr(web_app.approval_store, "get_rocket_input_dir", lambda: str(rocket))
    url = _approved(workspace)
    r = client.post(url, json={"target": "rocket", "confirm": True})
    assert r.status_code == 200 and (rocket / "send.mp4").read_bytes() == b"video"
    assert (workspace / "dataviz" / "outputs" / "horizontal" / "send.mp4").exists()            # העתקה, לא העברה
    assert "rocket" in dp.load_package(str(workspace / "dataviz" / "outputs" / "horizontal" / "send.publish.json"))["sent"]
    assert client.post(url, json={"target": "rocket", "confirm": True}).status_code == 400   # כבר נשלח
    # קובץ קיים ביעד (חבילה אחרת) - לא נדרס
    make_package(workspace, "other")
    dp.set_decision(str(workspace / "dataviz" / "outputs" / "horizontal" / "other.mp4"), dp.APPROVED)
    (rocket / "other.mp4").write_bytes(b"keep")
    assert client.post("/api/dataviz/packages/horizontal/other/send", json={"target": "rocket", "confirm": True}).status_code == 409
    assert (rocket / "other.mp4").read_bytes() == b"keep"


def test_send_to_youtube_uses_the_configured_uploader_privately_with_a_fake(workspace, monkeypatch):
    import time
    fake = _NoUpload(monkeypatch)
    url = _approved(workspace)
    assert client.post(url, json={"target": "youtube", "confirm": True}).json()["started"] is True
    sidecar = str(workspace / "dataviz" / "outputs" / "horizontal" / "send.publish.json")
    deadline = time.time() + 5
    while "youtube" not in (dp.load_package(sidecar).get("sent") or {}) and time.time() < deadline:
        time.sleep(0.05)
    assert dp.load_package(sidecar)["sent"]["youtube"]["video_id"] == "FAKEID"
    assert len(fake.calls) == 1 and fake.calls[0][1]["privacy_status"] == "private"
    assert client.post(url, json={"target": "youtube", "confirm": True}).status_code == 400   # לא פעמיים


def test_send_to_youtube_without_configured_account_does_nothing(workspace, monkeypatch):
    fake = _NoUpload(monkeypatch, configured=False)
    url = _approved(workspace)
    assert client.post(url, json={"target": "youtube", "confirm": True}).status_code == 409 and fake.calls == []


def test_send_rejects_foreign_origin_and_unknown_package(workspace, monkeypatch):
    _NoUpload(monkeypatch)
    url = _approved(workspace)
    assert client.post(url, json={}, headers={"Origin": "http://evil.example", "Host": "127.0.0.1:8878"}).status_code == 403
    assert client.post("/api/dataviz/packages/horizontal/ghost/send", json={}).status_code == 404
    assert client.post("/api/dataviz/packages/../etc/send", json={}).status_code in (404, 405)