# tests/dataviz/test_web_app_wave44_browser.py
#
# גל 44 בדפדפן: באשף הפרסום - הצעה מ-Gemini שממלאת את השדות ושלוש תמונות לבחירה; צפיות של סרטון שהועלה על
# כרטיס החבילה; ותור הפרקים עם שורה לכל פרק ו"הסר מהתור". Gemini, ffmpeg, יוטיוב וההרצה עצמה מוחלפים.
# xdist-group: workspace
import json


import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    small = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", **small}, name="alarms")
    write_episode(data / "dataviz_episodes", overrides={"title": "מכוניות", **small}, name="cars")
    out = workspace / "dataviz" / "outputs" / "horizontal"
    out.mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    monkeypatch.setattr(web_app, "_start_script_run", lambda script, folder, payload, host: {"ok": True})
    from utils import dataviz_publish as dpub

    def fake_candidates(path, **kw):
        names = []
        for k in (1, 2, 3):
            name = dpub.candidate_name("alarms", k)
            (out / name).write_bytes((out / "alarms_thumb.jpg").read_bytes())
            names.append(name)
        return names

    monkeypatch.setattr(dpub, "thumbnail_candidates", fake_candidates)
    monkeypatch.setattr(dpub, "suggest_metadata", lambda path: {"title": "כותרת מ-Gemini", "description": "תיאור", "hashtags": ["#נתונים"]})
    from PIL import Image
    Image.new("RGB", (32, 18), "#336699").save(out / "alarms_thumb.jpg")
    (out / "alarms.mp4").write_bytes(b"\x00" * 64)
    sidecar = out / "alarms.publish.json"
    sidecar.write_text(json.dumps({"status": "approved", "video": "alarms.mp4", "thumbnail": "alarms_thumb.jpg", "created_at": "2026-10-16T10:00:00",
                                   "metadata": {"title": "ישן", "youtube_title": "ישן"},
                                   "stats": {"views": 1234, "likes": 5, "comments": 1, "at": "2026-10-16T10:00:00"},
                                   "sent": {"youtube": {"at": "2026-10-16T10:00:00", "video_id": "abc"}}}), encoding="utf-8")
    return {"data": data, "out": out, "sidecar": sidecar}


def _open(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")


def test_views_show_on_the_card_and_the_package(editor_page, screen):
    page = editor_page
    _open(page)
    page.wait_for_selector('.dvz-card[data-episode="alarms"] .dvz-card-badges >> text=1,234')
    page.click('.dvz-card[data-episode="alarms"]')
    page.wait_for_selector("#dvzPackages .dvz-stats >> text=1,234")


def test_the_wizard_suggests_texts_and_offers_three_pictures(editor_page, screen):
    # חבילה שעוד לא נשלחה ולא אושרה - האשף נפתח בשלב הטקסטים (חבילה שאושרה נפתחת בשלב השליחה)
    package = json.loads(screen["sidecar"].read_text(encoding="utf-8"))
    package.pop("sent")
    package["status"] = "pending_approval"
    screen["sidecar"].write_text(json.dumps(package), encoding="utf-8")
    page = editor_page
    _open(page)
    page.click('.dvz-card[data-episode="alarms"]')
    page.wait_for_selector("#dvzPublishSection", state="visible")
    page.click("#dvzPackages >> text=אשף פרסום")
    page.wait_for_selector("#dvzWzTitle")
    page.click("#dvzWizardBody >> text=הצעה מ-Gemini")
    page.wait_for_function("() => document.getElementById('dvzWzTitle').value === 'כותרת מ-Gemini'")
    page.click("#dvzWizardNext")
    page.wait_for_selector("#dvzWizardSteps li.is-current >> text=תמונה")
    page.click("#dvzWizardBody >> text=עוד 3 אפשרויות")
    page.wait_for_function("() => document.querySelectorAll('#dvzWizardBody .dvz-thumb-pick').length === 3")
    page.click("#dvzWizardBody .dvz-thumb-pick >> nth=1")
    page.wait_for_function("() => document.getElementById('dvzWizardStatus').textContent.includes('2')")
    assert (screen["out"] / "alarms_thumb_original.jpg").exists()
    page.evaluate("() => closeDvzWizard()")


def test_the_queue_lists_each_episode_and_removes_one(editor_page, screen):
    page = editor_page
    _open(page)
    page.check('.dvz-card-wrap:has(.dvz-card[data-episode="alarms"]) .dvz-queue-pick input')
    page.check('.dvz-card-wrap:has(.dvz-card[data-episode="cars"]) .dvz-queue-pick input')
    page.click("#dvzQueueRun")
    page.wait_for_function("() => document.querySelectorAll('#dvzQueueProgress .dvz-queue-row').length === 2")
    page.click('#dvzQueueProgress .dvz-queue-row:has-text("cars") button')
    page.wait_for_selector('#dvzQueueProgress .dvz-queue-row:has-text("cars") >> text=יוסר מהתור')
    control = json.loads((screen["data"] / "dataviz_queue.control.json").read_text(encoding="utf-8"))
    assert control == {"skip": ["cars"]}
