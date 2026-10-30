# tests/dataviz/test_web_app_wave45_browser.py
#
# גל 45 בדפדפן: "לפני / אחרי" במדריך המנוע (שני פריימים של הפרק שנבחר), לשונית המפה בעורך (העלאה לספרייה,
# בדיקת התאמה ושימוש בפרק) ולשונית הקריינות (הקלטה נשלחת ומופיעה ליד האירוע - בלי מיקרופון: Blob קטן).
# config.yaml של הפרק לא משתנה.
# xdist-group: workspace
import hashlib
import json


import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

GEO = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"name": n}, "geometry": {"type": "Polygon", "coordinates": [[[34 + i, 31], [35 + i, 31], [35 + i, 32], [34 + i, 32], [34 + i, 31]]]}}
    for i, n in enumerate(("2019", "2023", "מקום"))]}


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", "video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    from entrypoints.web.routes import dataviz as routes
    routes._voices_cache["voices"] = []
    config = data / "dataviz_episodes" / "alarms" / "config.yaml"
    yield {"data": data, "config": config, "md5": hashlib.md5(config.read_bytes()).hexdigest()}
    routes._voices_cache.clear()


def _open_editor_tab(page, tab):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; }")
    page.wait_for_selector("#dvzEditorBody .dvz-group")
    page.click(f"#dvzEditorTabs button[data-tab={tab}]")


def test_before_after_in_the_engine_guide(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click("#dvzToolsBtn")   # 21.10.2026: ב"🧰 כלים"
    page.click("#dvzToolHelp")
    page.wait_for_selector("#dvzHelp-group-ranking dd button")
    assert page.evaluate("() => _dvzAltValue({type: 'int', default: 10, min: 3, max: 30})") == 20
    assert page.evaluate("() => _dvzAltValue({type: 'bool', default: true})") is False
    page.fill("#dvzHelpSearch", "ranking.smoothing")
    page.click("#dvzHelpBody dd button >> text=לפני / אחרי")
    page.wait_for_function("() => [...document.querySelectorAll('#dvzHelpBody .dvz-before-after img')].filter(i => i.complete && i.naturalWidth).length === 2")
    srcs = page.eval_on_selector_all("#dvzHelpBody .dvz-before-after img", "els => els.map(e => decodeURIComponent(e.src))")
    assert '"ranking.smoothing":0.07' in srcs[0] and '"ranking.smoothing":0.14' in srcs[1]


def test_the_map_tab_uploads_checks_and_uses_a_map(editor_page, screen):
    page = editor_page
    _open_editor_tab(page, "map")
    page.wait_for_selector("#dvzMapUpload", state="attached")
    page.set_input_files("#dvzMapUpload", files=[{"name": "שנים.geojson", "mimeType": "application/geo+json", "buffer": json.dumps(GEO).encode()}])
    page.wait_for_selector("#dvzMapPick option[value='שנים']", state="attached")
    page.click("#dvzEditorBody >> text=בדוק התאמה")
    page.wait_for_selector("#dvzEditorBody .dvz-map-report p")
    assert "נמצאו במפה" in page.inner_text("#dvzEditorBody .dvz-map-report")
    page.click("#dvzEditorBody >> text=השתמש במפה בפרק")
    page.wait_for_function("() => dvzState.episodes.some(e => e.name === 'alarms' && e.has_map)")
    over = json.loads((screen["data"] / "dataviz_overrides" / "alarms.json").read_text(encoding="utf-8"))
    assert over["map"]["geojson"].endswith("שנים.geojson") and over["map"]["key"] == "name"
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]


def test_the_voice_tab_saves_a_recording_for_an_event(editor_page, screen):
    page = editor_page
    _open_editor_tab(page, "voice")
    page.wait_for_selector("#dvzEditorBody .dvz-voice-table tr[data-date='2023-10-07']")
    assert page.evaluate("""async () => dvzUploadRecording('2023-10-07', new Blob([new Uint8Array([82, 73, 70, 70, 1, 2, 3])], {type: 'audio/webm'}))""") is True
    page.click("#dvzEditorTabs button[data-tab=voice]")
    page.wait_for_selector("#dvzEditorBody .dvz-voice-table tr[data-date='2023-10-07'] >> text=הוקלט")
    folder = screen["data"] / "dataviz_overrides" / "alarms" / "narration"
    assert [p.suffix for p in folder.iterdir()] == [".webm"]
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]


def test_ready_maps_are_downloaded_only_on_click(editor_page, screen, monkeypatch):
    from utils import dataviz_library as lib
    calls = []
    monkeypatch.setattr(lib, "fetch_ready_map", lambda data_dir, map_id: calls.append(map_id) or lib.save_map(data_dir, map_id + ".geojson", json.dumps(GEO)))
    page = editor_page
    _open_editor_tab(page, "map")
    page.wait_for_selector("#dvzEditorBody .dvz-ready-map[data-map='israel-districts'] button")
    assert calls == []   # לא יורד כלום עד שלוחצים
    page.click("#dvzEditorBody .dvz-ready-map[data-map='israel-districts'] button")
    page.wait_for_selector("#dvzEditorBody .dvz-ready-map[data-map='israel-districts'] >> text=בספרייה")
    assert calls == ["israel-districts"]
    page.wait_for_selector("#dvzMapPick option[value='israel-districts']", state="attached")
