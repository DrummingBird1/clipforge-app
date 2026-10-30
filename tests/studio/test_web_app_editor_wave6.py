# tests/studio/test_web_app_editor_wave6.py
#
# גל 6 של 102-ההצעות - פרופילים, השלב הבא (items 60-68): תגיות/צבעים/הערות,
# מיון לפי שימוש, צ'יפים מהירים, ברירת-מחדל מפורשת, היסטוריה עם diff, "מזג שדה"
# מההשוואה, ייצוא/ייבוא של כל הפרופילים, שיתוף בקישור/QR, וירושה בין פרופילים.


import pytest

from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.video import video_editor_profiles as vep

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: None)


# --- 60: תגיות/צבע/הערות ---

def test_annotate_profile_cleans_tags_and_validates_color():
    vep.save_profile("A", {"codec": "h264"})
    meta = vep.annotate_profile("A", tags=[" #shorts ", "RL", "shorts", ""], color="green", notes="for tiktok")
    assert meta["tags"] == ["shorts", "RL"] and meta["color"] == "green" and meta["notes"] == "for tiktok"
    with pytest.raises(ValueError):
        vep.annotate_profile("A", color="neon")
    with pytest.raises(ValueError):
        vep.annotate_profile("missing", tags=["x"])


def test_annotate_endpoint_accepts_comma_string():
    vep.save_profile("A", {"codec": "h264"})
    resp = client.post("/api/video_editor_profiles/A/annotate", json={"tags": "one, two", "color": "blue", "notes": "n"})
    assert resp.status_code == 200 and resp.json()["tags"] == ["one", "two"]
    meta_all = client.get("/api/video_editor_profiles_meta_all").json()["meta"]
    assert meta_all["A"]["color"] == "blue"


def test_meta_all_has_defaults_for_every_profile_and_created_at():
    vep.save_profile("A", {"codec": "h264"})
    vep.save_profile("B", {"codec": "hevc"})
    meta = vep.load_all_profile_meta()
    assert set(meta) == {"A", "B"}
    assert meta["A"]["tags"] == [] and meta["A"]["is_default"] is False and meta["A"]["created_at"]


# --- 63: ברירת-מחדל מפורשת ---

def test_default_profile_is_exclusive_and_clearable():
    for name in ("A", "B"):
        vep.save_profile(name, {"codec": "h264"})
    vep.set_default_profile("A")
    vep.set_default_profile("B")
    assert vep.get_default_profile_name() == "B"
    assert vep.load_profile_meta("A")["is_default"] is False
    assert client.post("/api/video_editor_profile_default", json={"name": None}).status_code == 200
    assert vep.get_default_profile_name() is None
    assert client.post("/api/video_editor_profile_default", json={"name": "nope"}).status_code == 400


# --- 65: מזג שדה ---

def test_set_profile_field_pushes_history_and_rejects_unknown_fields():
    vep.save_profile("A", {"codec": "h264", "vertical": False})
    resp = client.post("/api/video_editor_profiles/A/set_field", json={"field": "vertical", "value": True})
    assert resp.status_code == 200 and vep.load_profiles()["A"]["vertical"] is True
    assert vep.get_profile_history("A")[-1]["vertical"] is False
    assert client.post("/api/video_editor_profiles/A/set_field", json={"field": "evil", "value": 1}).status_code == 400


# --- 66: ייצוא/ייבוא הכל ---

def test_export_all_then_import_all_with_each_strategy():
    vep.save_profile("A", {"codec": "av1"})
    vep.annotate_profile("A", tags=["t"], color="red")
    exported = client.get("/api/video_editor_profiles_export_all").json()
    assert exported["format"] == vep.EXPORT_FORMAT and exported["meta"]["A"]["tags"] == ["t"]
    vep.save_profile("A", {"codec": "h264"})  # מצב מקומי שונה
    skip = client.post("/api/video_editor_profiles_import_all", json={"data": exported, "strategy": "skip"}).json()
    assert skip == {"imported": [], "skipped": ["A"], "renamed": []}
    assert vep.load_profiles()["A"]["codec"] == "h264"
    renamed = client.post("/api/video_editor_profiles_import_all", json={"data": exported, "strategy": "rename"}).json()
    assert renamed["renamed"] == ["A (מיובא)"] and vep.load_profiles()["A (מיובא)"]["codec"] == "av1"
    assert vep.load_profile_meta("A (מיובא)")["tags"] == ["t"]
    over = client.post("/api/video_editor_profiles_import_all", json={"data": exported, "strategy": "overwrite"}).json()
    assert over["imported"] == ["A"] and vep.load_profiles()["A"]["codec"] == "av1"
    assert client.post("/api/video_editor_profiles_import_all", json={"data": {"x": 1}}).status_code == 400


# --- 68: ירושה ---

def test_inheritance_tracks_overrides_and_pulls_parent_changes():
    vep.save_profile("Base", {"codec": "h264", "vertical": True, "watermark_path": "C:\\a.png"})
    vep.duplicate_profile("Base", "Child")
    vep.set_profile_parent("Child", "Base")
    assert vep.load_profile_meta("Child")["overridden_fields"] == []
    child = vep.load_profiles()["Child"]
    child["codec"] = "hevc"  # הילד משנה בעצמו
    vep.save_profile("Child", child)
    assert vep.load_profile_meta("Child")["overridden_fields"] == ["codec"]
    base = vep.load_profiles()["Base"]
    base["codec"] = "av1"
    base["watermark_path"] = "C:\\b.png"  # שינוי בהורה שהילד לא נגע בו
    vep.save_profile("Base", base)
    result = vep.pull_from_parent("Child")
    assert result["pulled_fields"] == ["watermark_path"]
    assert result["settings"]["watermark_path"] == "C:\\b.png"
    assert result["settings"]["codec"] == "hevc"  # הדריסה של הילד נשמרה


def test_inheritance_rejects_cycles_and_self_and_follows_rename():
    for name in ("A", "B"):
        vep.save_profile(name, {"codec": "h264"})
    vep.set_profile_parent("B", "A")
    with pytest.raises(ValueError):
        vep.set_profile_parent("A", "B")
    with pytest.raises(ValueError):
        vep.set_profile_parent("A", "A")
    vep.rename_profile("A", "A2")
    assert vep.load_profile_meta("B")["parent"] == "A2"


def test_inheritance_endpoints():
    vep.save_profile("P", {"codec": "h264", "fps": "30"})
    vep.duplicate_profile("P", "C")
    assert client.post("/api/video_editor_profiles/C/parent", json={"parent": "P"}).json()["parent"] == "P"
    p = vep.load_profiles()["P"]
    p["fps"] = "60"
    vep.save_profile("P", p)
    pulled = client.post("/api/video_editor_profiles/C/pull_parent").json()
    assert pulled["pulled_fields"] == ["fps"]
    assert client.post("/api/video_editor_profiles/P/pull_parent").status_code == 400


# --- 67: QR / LAN / טוקן ---

def test_qr_endpoint_returns_svg_and_limits_size():
    resp = client.get("/api/qr", params={"data": "http://127.0.0.1:8878/?import_profile=z.abc"})
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("image/svg+xml") and b"<svg" in resp.content
    assert client.get("/api/qr", params={"data": "x" * 5000}).status_code == 400
    assert client.get("/api/qr").status_code == 400


def test_lan_info_and_access_token(monkeypatch):
    assert client.get("/api/lan_info").json() == {"lan": False, "base_url": None}
    monkeypatch.setattr(web_app, "LAN_BASE_URL", "https://192.168.1.5:8878")
    assert client.get("/api/lan_info").json()["base_url"] == "https://192.168.1.5:8878"
    assert client.get("/api/access_token").json()["token"] == web_app.ACCESS_TOKEN
    anonymous = TestClient(app)
    assert anonymous.get("/api/access_token").status_code == 401


# --- דפדפן אמיתי ---

def _save_profile_in_page(page, name):
    page.evaluate("() => openVeProfileManager()")  # גל 10: פעולות הפרופיל בדיאלוג "👤 פרופילים"
    page.fill("#veProfileName", name)
    page.evaluate("() => saveVideoEditorProfile()")
    page.wait_for_function(f"() => document.getElementById('vePreset').value === 'profile:{name}'")


@pytest.fixture
def page(editor_page):
    # גל 22: שמות מתבקשים בדיאלוג בתוך הדף (answer_ve_prompt); דיאלוג דפדפן אחר, אם יופיע, מאושר
    editor_page.on("dialog", lambda dialog: dialog.accept())
    return editor_page


def test_browser_sorting_filtering_and_quick_chips(page):
    for name, runs in (("Alpha", 1), ("Beta", 5), ("Gamma", 3)):
        vep.save_profile(name, {"codec": "h264"})
        for _ in range(runs):
            vep.record_profile_used(name)
    vep.annotate_profile("Gamma", tags=["shorts"], color="red")
    page.evaluate("() => loadVideoEditorProfiles()")
    # גל 58: "⚡ הכי בשימוש" בראש בורר הסגנון, לא שבבים בשורת הסטטוס
    page.wait_for_function("() => !!document.getElementById('veTopProfilesGroup')")
    chips = page.evaluate("() => Array.from(document.querySelectorAll('#veTopProfilesGroup option')).map(o => o.textContent)")
    assert chips == ["Beta", "🔴 Gamma", "Alpha"]
    assert page.evaluate("() => _veStyleOptions().filter(o => o.value === 'profile:Beta').length") == 1   # בלי כפילות
    page.evaluate("() => openVeProfileManager()")
    page.select_option("#veProfileSort", "count")
    page.wait_for_function("() => document.querySelector('#veProfilesGroup option').value === 'profile:Beta'")
    options = page.evaluate("() => Array.from(document.querySelectorAll('#veProfilesGroup option')).map(o => o.value)")
    assert options == ["profile:Beta", "profile:Gamma", "profile:Alpha"]
    page.select_option("#veProfileTagFilter", "shorts")
    page.wait_for_function("() => document.querySelectorAll('#veProfilesGroup option').length === 1")
    assert page.evaluate("() => Array.from(document.querySelectorAll('#veProfilesGroup option')).map(o => o.value)") == ["profile:Gamma"]
    page.select_option("#veProfileTagFilter", "")
    page.wait_for_function("() => document.querySelectorAll('#veProfilesGroup option').length === 3")
    page.evaluate("() => closeVeProfileManager()")
    page.select_option("#vePreset", "profile:Alpha")
    assert page.evaluate("() => document.getElementById('vePreset').value") == "profile:Alpha"


def test_browser_annotate_dialog_and_default_star(page):
    _save_profile_in_page(page, "Mine")
    page.evaluate("() => openVeAnnotateDialog()")
    page.fill("#veAnnotateTags", "rl, shorts")
    page.click("#veAnnotateColors button[aria-label=purple]")
    page.fill("#veAnnotateNotes", "the good one")
    page.click("#veAnnotateModalBg button:has-text('שמור')")
    page.wait_for_function("() => document.getElementById('veProfileMetaInfo').textContent.includes('#rl')")
    assert "the good one" in page.inner_text("#veProfileNotesText")
    page.evaluate("() => toggleVeDefaultProfile()")
    page.wait_for_function("() => document.getElementById('veProfileMetaInfo').textContent.includes('ברירת המחדל')")
    assert "🟣 Mine ⭐" in page.evaluate("() => document.querySelector('#veProfilesGroup option').textContent")
    assert vep.get_default_profile_name() == "Mine"


def test_browser_default_profile_loads_on_open(editor_server, edge_browser):
    from entrypoints import web_app as live_app
    vep.save_profile("Startup", {"codec": "av1", "vertical": True})
    vep.save_profile("Other", {"codec": "h264"})
    vep.set_default_profile("Startup")
    from tests.conftest import _collect_tk_garbage_on_main_thread
    _collect_tk_garbage_on_main_thread()
    context = edge_browser.new_context(viewport={"width": 1400, "height": 900})
    try:
        fresh = context.new_page()
        fresh.goto(f"{editor_server['base_url']}/?token={live_app.ACCESS_TOKEN}")
        fresh.wait_for_function("() => document.getElementById('vePreset').value === 'profile:Startup'", timeout=20000)
        assert fresh.evaluate("() => document.getElementById('veCodec').value") == "av1"
    finally:
        context.close()


def test_browser_history_shows_field_diffs(page):
    _save_profile_in_page(page, "Hist")
    page.evaluate("() => { const c = document.getElementById('veCodec'); c.value = 'hevc'; c.dispatchEvent(new Event('change', {bubbles: true})); }")
    page.evaluate("() => updateVideoEditorProfile()")  # evaluate מחכה להבטחה - העדכון נשמר
    page.evaluate("() => openProfileHistoryDialog()")
    page.wait_for_selector("#profileHistoryList .ve-diff-line")
    assert "h264 → hevc" in page.inner_text("#profileHistoryList")


def test_browser_compare_dialog_merges_a_field(page):
    vep.save_profile("Left", {"codec": "h264", "vertical": True})
    vep.save_profile("Right", {"codec": "av1", "vertical": True})
    page.evaluate("() => loadVideoEditorProfiles().then(openCompareProfilesDialog)")
    page.wait_for_selector("#compareProfilesModalBg.show")
    page.select_option("#compareProfileA", "Left")
    page.select_option("#compareProfileB", "Right")
    page.evaluate("() => _runProfileComparison()")
    page.wait_for_selector("#compareProfilesResult .ve-merge-btn")
    page.click("#compareProfilesResult .ve-merge-btn:has-text('העתק ל-Right')")
    page.wait_for_selector("#veConfirmModalBg.show")
    page.click("#veConfirmOkBtn")
    page.wait_for_function("() => document.getElementById('compareProfilesResult').textContent.includes('זהים')", timeout=10000)
    assert vep.load_profiles()["Right"]["codec"] == "h264"


def test_browser_child_profile_pull_from_parent(page, ve_prompt):
    vep.save_profile("Parent", {"codec": "h264", "fps": "30"})
    page.evaluate("() => loadVideoEditorProfiles()")
    page.evaluate("() => { document.getElementById('vePreset').value = 'profile:Parent'; applyVideoEditorPreset(); }")
    page.evaluate("() => { createVeChildProfile(); }")  # לא מחכים להבטחה - היא ממתינה לדיאלוג
    ve_prompt(page, "Kid")
    page.wait_for_function("() => document.getElementById('vePreset').value === 'profile:Kid'", timeout=10000)
    page.wait_for_function("() => document.getElementById('veProfileMetaInfo').textContent.includes('מבוסס על')")
    parent = vep.load_profiles()["Parent"]
    parent["fps"] = "60"
    vep.save_profile("Parent", parent)
    page.evaluate("() => loadVideoEditorProfiles().then(() => _loadAndShowProfileMeta('Kid'))")
    page.wait_for_function("() => !document.getElementById('vePullParentBtn').hidden")
    page.evaluate("() => openVeProfileManager()")
    page.click("#vePullParentBtn")
    page.wait_for_selector("#veConfirmModalBg.show")
    page.click("#veConfirmOkBtn")
    page.wait_for_function("() => document.getElementById('veFps').value === '60'", timeout=10000)


def test_browser_share_link_roundtrip_imports_profile(page, editor_server, ve_prompt):
    vep.save_profile("Shared", {"codec": "av1", "vertical": True, "text": "Hello share"})
    page.evaluate("() => loadVideoEditorProfiles()")
    page.evaluate("() => { document.getElementById('vePreset').value = 'profile:Shared'; applyVideoEditorPreset(); }")
    page.evaluate("() => openVeShareDialog()")
    page.wait_for_function("() => document.getElementById('veShareUrl').value.includes('import_profile=z.')")
    url = page.evaluate("() => document.getElementById('veShareUrl').value")
    assert len(url) < 700  # רק שדות ששונו מברירת המחדל, דחוסים
    page.wait_for_function("() => document.getElementById('veShareQr').complete && document.getElementById('veShareQr').naturalWidth > 0", timeout=10000)
    page.check("#veShareIncludeToken")
    page.wait_for_function("() => document.getElementById('veShareUrl').value.includes('token=')")
    vep.delete_profile("Shared")
    page.goto(url)
    ve_prompt(page, "Shared Back", timeout=20000)
    page.wait_for_function("() => document.getElementById('vePreset').value === 'profile:Shared Back'", timeout=20000)
    saved = vep.load_profiles()["Shared Back"]
    # גל 12: טקסט קבוע של פרופיל ישן עובר מיגרציה לשכבת טקסט (צד-שרת) - ומשותף ככזה
    assert saved["codec"] == "av1" and saved["vertical"] is True and not saved.get("text")
    assert any(layer.get("text") == "Hello share" for layer in saved["layers"])
    assert "import_profile" not in page.evaluate("() => location.search")


def test_browser_export_import_all_dialog(page, tmp_path):
    import json
    data = {"format": vep.EXPORT_FORMAT, "version": 1, "profiles": {"Imp1": {"codec": "hevc"}, "Imp2": {"codec": "av1"}}, "meta": {}}
    path = tmp_path / "all.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    page.evaluate("() => openVeImportAllDialog()")
    page.set_input_files("#veImportAllFile", str(path))
    page.click("#veImportAllModalBg button:has-text('ייבא')")
    page.wait_for_function("() => document.getElementById('veImportAllResult').textContent.includes('יובאו 2')")
    assert set(vep.load_profiles()) >= {"Imp1", "Imp2"}
