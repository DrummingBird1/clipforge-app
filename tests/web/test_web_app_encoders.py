# tests/web/test_web_app_encoders.py
#
# 16.11.2026 (2.0): GET/POST /api/encoders - מקודד HEVC/AV1 בהגדרות הכלליות (utils/media/encoders.py). הבדיקה של הכרטיס
# מוחלפת - בלי ffmpeg אמיתי.
import pytest

from tests.web_app_support import client
from utils.media import encoders


@pytest.fixture(autouse=True)
def settings(tmp_path, monkeypatch):
    path = str(tmp_path / "encoder_settings.json")
    monkeypatch.setattr(encoders, "settings_path", lambda: path)
    monkeypatch.delenv(encoders.ENV_VAR, raising=False)
    return path


def test_the_default_is_auto_and_no_probe_runs_without_asking(monkeypatch):
    monkeypatch.setattr(encoders, "detect_backends", lambda *a, **k: pytest.fail("probe ran"))
    data = client.get("/api/encoders").json()
    assert data["setting"] == "auto" and data["available"] is None
    assert [c["id"] for c in data["choices"]] == ["auto", "nvenc", "amf", "qsv", "cpu"]


def test_probe_reports_what_the_card_can_do_and_what_will_be_used(monkeypatch):
    monkeypatch.setattr(encoders, "detect_backends",
                        lambda *a, **k: {"nvenc": [], "amf": ["hevc"], "qsv": [], "cpu": ["hevc", "av1"]})
    data = client.get("/api/encoders", params={"probe": 1}).json()
    assert data["effective"] == {"hevc": "amf", "av1": "cpu"}


def test_saving_a_choice(settings):
    data = client.post("/api/encoders", json={"backend": "qsv"}).json()
    assert data["setting"] == "qsv" and encoders.load_setting(settings) == "qsv"


def test_an_unknown_choice_is_refused(settings):
    resp = client.post("/api/encoders", json={"backend": "voodoo"})
    assert resp.status_code == 400
    assert encoders.load_setting(settings) == "auto"
