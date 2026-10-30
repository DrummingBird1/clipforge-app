# tests/web/test_web_app_device_pairing_browser.py
#
# 22.10.2026: צימוד מכשיר מהמסך - "🌐 הגדרות כלליות" > "📱 גישה מהטלפון": צמד מכשיר (שם, QR, קישור), המסך רואה
# לבד שהמכשיר צומד, ו"בטל צימוד" מנתק אותו. "המכשיר" הוא בקשת HTTP רגילה לדף הצימוד; המאגר בתיקייה זמנית.
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from utils.shared import device_pairing
from utils.video import video_editor_profiles as vep

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning")]


@pytest.fixture
def devices(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    store = device_pairing.DeviceStore(str(tmp_path / "paired_devices.json"))
    monkeypatch.setattr(web_app, "device_store", store)
    monkeypatch.setattr(web_app, "TAILSCALE_BASE_URL", editor_server["base_url"])   # "כתובת ה-Tailscale" של השרת בטסט
    return store


def test_pair_a_device_from_the_settings_and_unpair_it(editor_page, editor_server, devices):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('globalsettings'); }")
    page.wait_for_selector("#gsDevices h4")
    assert "אין מכשירים מצומדים" in page.inner_text("#gsDevices")
    assert page.is_visible("#rotateTokenBtn")   # במחשב עצמו "🔑 החלף טוקן" נשאר

    page.click("#gsDevices >> text=צמד מכשיר")
    page.fill("#vePromptInput", "טלפון")
    page.click("#vePromptOkBtn")
    page.wait_for_selector("#gsPairBox img")
    assert page.get_attribute("#gsPairBox img", "src").startswith("/api/qr?data=")
    link = page.inner_text("#gsPairBox code").strip()
    code = parse_qs(urlparse(link).query)["code"][0]

    phone = httpx.post(f"{editor_server['base_url']}/pair", data={"code": code}, follow_redirects=False)
    assert phone.status_code == 303 and device_pairing.COOKIE_NAME in phone.cookies

    page.wait_for_selector("#gsDevices b:text('טלפון')")   # המסך בודק כל 2 שניות אם הקוד מומש
    assert [d["name"] for d in devices.list_devices()] == ["טלפון"]

    page.click("#gsDevices >> text=בטל צימוד")
    page.click("#veConfirmOkBtn")
    page.wait_for_function("() => document.getElementById('gsDevices').innerText.includes('אין מכשירים מצומדים')")
    assert devices.list_devices() == []


def test_a_paired_device_gets_no_token_tools(edge_browser, editor_server, devices):
    # "🔑 החלף טוקן" מוסתר (השרת עונה שם 403), ו-/api/access_token עונה 403 - "כלול טוקן" לא מכניס לקישור token=undefined
    base = editor_server["base_url"]
    paired = httpx.post(f"{base}/pair", data={"code": devices.create_code("טלפון")["code"]}, follow_redirects=False)
    context = edge_browser.new_context(viewport={"width": 1440, "height": 950}, locale="he-IL")
    try:
        context.add_cookies([{"name": device_pairing.COOKIE_NAME, "value": paired.cookies[device_pairing.COOKIE_NAME], "url": base}])
        page = context.new_page()
        page.goto(f"{base}/")
        page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)
        page.wait_for_function("() => document.getElementById('rotateTokenBtn').hidden")
        assert not page.is_visible("#rotateTokenBtn")   # hidden לא נדרס ע"י ה-CSS של הכפתור
        page.evaluate("() => selectScript(state.scripts.find(s => s.id.endsWith('video_editor.py')).id)")
        vep.save_profile("Shared from phone", {"codec": "av1"})
        page.evaluate("() => loadVideoEditorProfiles()")
        page.evaluate("() => { document.getElementById('vePreset').value = 'profile:Shared from phone'; applyVideoEditorPreset(); }")
        page.evaluate("() => openVeShareDialog()")
        page.wait_for_function("() => document.getElementById('veShareUrl').value.includes('import_profile=z.')")
        page.check("#veShareIncludeToken")
        url = page.evaluate("async () => { await renderVeShare(); return document.getElementById('veShareUrl').value; }")
        assert "import_profile=z." in url and "token=" not in url
    finally:
        context.close()
        vep.delete_profile("Shared from phone")
