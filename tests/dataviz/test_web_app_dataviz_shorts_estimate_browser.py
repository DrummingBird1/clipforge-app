# tests/dataviz/test_web_app_dataviz_shorts_estimate_browser.py
#
# 23.10.2026, המלצה 10: בבחירת "Shorts אוטומטיים" ב"מה להפיק" מוצג כמה Shorts ייצאו, האורך וזמן הרינדור (קודם: כלום).
# xdist-group: workspace
import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"shorts": {"count": 2, "seconds": 8}}, name="alpha")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    return data


def test_choosing_shorts_shows_how_many_and_how_long(editor_page, screen):
    page = editor_page
    page.evaluate("() => { localStorage.setItem('dvzMode', 'regular'); closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector("#dvzEpisodes .dvz-card")
    page.wait_for_function("() => dvzState.selected === 'alpha' && dvzState.estimates.alpha")
    page.select_option("#dvzMode", "shorts")
    page.wait_for_function("() => /2 Shorts/.test(document.getElementById('dvzEstimate').textContent)", timeout=10000)   # קודם: ריק
    assert "רינדור משוער" in page.inner_text("#dvzEstimate")
