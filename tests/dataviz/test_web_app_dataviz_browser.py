# tests/dataviz/test_web_app_dataviz_browser.py
#
# חבילות הפרסום של סרטוני נתונים בדפדפן אמיתי מול השרת האמיתי (אותו תהליך): לשונית "✅ אישור קליפים",
# סעיף "📊 סרטוני נתונים לפרסום". workspace זמני (monkeypatch של web_app.WORKSPACE_DIR), חבילות אמיתיות
# מ-prepare_publish עם JPEG אמיתי קטן; אישור/דחייה בלחיצה משנים רק את ה-.publish.json.
import os


import pytest

from dataviz.config import load_config
from tests.dataviz_helpers import write_episode
from dataviz.web import publish as dp

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _real_jpeg(video, out, **kwargs):
    from PIL import Image
    Image.new("RGB", (64, 36), (200, 30, 30)).save(out, quality=80)


def _make(workspace, name, title, orientation="horizontal"):
    folder = workspace / "dataviz" / "outputs" / orientation
    folder.mkdir(parents=True, exist_ok=True)
    config = load_config(os.path.join(write_episode(workspace / "_eps", overrides={"title": title}, name=name), "config.yaml"))
    (folder / f"{name}.mp4").write_bytes(b"video")
    return dp.prepare_publish(str(folder / f"{name}.mp4"), config, make_thumbnail=_real_jpeg)


@pytest.fixture
def packages(editor_server, tmp_path, monkeypatch):
    monkeypatch.setattr(editor_server["web_app"], "WORKSPACE_DIR", str(tmp_path))
    _make(tmp_path, "first", "הפרק הראשון")
    _make(tmp_path, "second", "הפרק השני", orientation="vertical")
    return tmp_path


def _open(page):
    page.evaluate("() => { closeVeEditor(); switchTab('approvals'); }")
    page.wait_for_selector(".dataviz-card")


def test_cards_show_thumbnail_title_status_and_seo_sheet(editor_page, packages):
    page = editor_page
    _open(page)

    cards = page.locator(".dataviz-card")
    assert cards.count() == 2
    assert set(page.eval_on_selector_all(".dataviz-card", "els => els.map(e => e.dataset.packageId)")) == {"horizontal/first", "vertical/second"}
    first = page.locator('.dataviz-card[data-package-id="horizontal/first"]')
    page.wait_for_function("() => [...document.querySelectorAll('.dataviz-card img')].every(i => i.complete && i.naturalWidth === 64)")
    assert "הפרק הראשון" in first.inner_text() and "ממתין לאישור" in first.inner_text()
    first.locator("summary").click()
    assert "#DataIsBeautiful" in first.locator(".dataviz-sheet").inner_text()
    assert first.locator("button").count() == 2
    page.screenshot(path=str(packages / "dataviz_cards.png"))


def test_approve_and_reject_by_clicking_change_only_the_sidecar(editor_page, packages):
    page = editor_page
    _open(page)
    before = sorted(str(p.relative_to(packages)) for p in packages.rglob("*") if p.is_file() and p.suffix != ".json")

    page.locator('.dataviz-card[data-package-id="horizontal/first"] .approval-approve-btn').click()
    page.wait_for_function("() => { const e = document.querySelector('.dataviz-card[data-package-id=\"horizontal/first\"]'); return !!e && e.dataset.status === 'approved'; }")
    page.locator('.dataviz-card[data-package-id="vertical/second"] .approval-reject-btn').click()
    page.wait_for_function("() => { const e = document.querySelector('.dataviz-card[data-package-id=\"vertical/second\"]'); return !!e && e.dataset.status === 'rejected'; }")

    assert dp.load_package(str(packages / "dataviz" / "outputs" / "horizontal" / "first.mp4"))["status"] == dp.APPROVED
    assert dp.load_package(str(packages / "dataviz" / "outputs" / "vertical" / "second.mp4"))["status"] == dp.REJECTED
    assert page.locator('.dataviz-card[data-package-id="vertical/second"] button').count() == 0       # נדחתה: אין פעולות
    assert page.locator('.dataviz-card[data-package-id="horizontal/first"] button[data-send-target]').count() == 3   # אושרה: רק פעולות שליחה
    assert "אושר" in page.locator('.dataviz-card[data-package-id="horizontal/first"]').inner_text()
    assert before == sorted(str(p.relative_to(packages)) for p in packages.rglob("*") if p.is_file() and p.suffix != ".json")


def test_an_already_decided_package_shows_the_server_error(editor_page, packages):
    page = editor_page
    _open(page)
    page.evaluate("() => { window.__alert = null; window.alert = (m) => { window.__alert = m; }; }")
    dp.set_decision(str(packages / "dataviz" / "outputs" / "horizontal" / "first.mp4"), dp.REJECTED)   # נקבע במקביל, למשל מ-CLI

    page.locator('.dataviz-card[data-package-id="horizontal/first"] .approval-approve-btn').click()
    page.wait_for_function("() => window.__alert !== null")

    assert "כבר התקבלה החלטה" in page.evaluate("() => window.__alert")
    assert dp.load_package(str(packages / "dataviz" / "outputs" / "horizontal" / "first.mp4"))["status"] == dp.REJECTED


def test_empty_state_explains_how_to_get_packages(editor_page, editor_server, tmp_path, monkeypatch):
    monkeypatch.setattr(editor_server["web_app"], "WORKSPACE_DIR", str(tmp_path))
    editor_page.evaluate("() => { closeVeEditor(); switchTab('approvals'); }")
    editor_page.wait_for_function("() => document.getElementById('datavizPackagesList').innerText.includes('--publish')")


def test_send_buttons_dry_run_then_copy_to_rocket_after_confirmation(editor_page, packages, editor_server, tmp_path_factory, monkeypatch):
    page = editor_page
    rocket = tmp_path_factory.mktemp("rocket_in")
    monkeypatch.setattr(editor_server["web_app"].approval_store, "get_rocket_input_dir", lambda: str(rocket))
    uploads = []
    monkeypatch.setattr(editor_server["web_app"].youtube_uploader, "upload_video", lambda *a, **k: uploads.append(a) or "X")
    monkeypatch.setattr(editor_server["web_app"].youtube_uploader, "set_thumbnail", lambda *a, **k: None)   # גל 55: בלי רשת
    _open(page)
    page.locator('.dataviz-card[data-package-id="horizontal/first"] .approval-approve-btn').click()
    send = '.dataviz-card[data-package-id="horizontal/first"] button[data-send-target="%s"]'
    page.wait_for_selector(send % "dry_run")
    page.locator(send % "dry_run").click()
    page.wait_for_function("() => document.body.innerText.includes('לא נשלח כלום')")   # alert של האפליקציה מוצג כהודעה צפה
    assert not list(rocket.iterdir())
    page.wait_for_selector(send % "rocket")
    page.locator(send % "rocket").click()
    page.wait_for_selector("#veConfirmModalBg.show")
    assert "Shorts" in page.inner_text("#veConfirmMessage")   # 30.10.2026: "Rocket Shorts" נקרא "Shorts" בממשק
    page.click("#veConfirmOkBtn")                                  # אישור מפורש במודאל של האפליקציה
    page.wait_for_selector(send % "rocket" + ":disabled")
    page.wait_for_function("() => document.body.innerText.includes('הועתק')")    # ההודעה הצפה אחרי שההעתקה הסתיימה
    assert (rocket / "first.mp4").read_bytes() == b"video"
    assert uploads == []                                            # שום העלאה אמיתית
