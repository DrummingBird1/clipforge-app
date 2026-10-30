# tests/dataviz/test_web_app_dataviz_catalog_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): "📚 קטלוג נתונים" - חיפוש בלי הורדה, בחירה מציגה מקור / טבלה / יחידות / כתובת, ו"⬇️ הורד
# לפרק חדש" יוצר פרק עם SOURCES.md. מול שרת HTTP מזויף על localhost - שום בקשה לא יוצאת לרשת.
# xdist-group: workspace
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from dataviz.web import catalog
from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}
WB = json.dumps([{"page": 1}, [{"date": str(y), "value": 70 + y % 10, "country": {"value": "Israel"}} for y in range(2000, 2010)]]).encode()


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(WB)

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(catalog, "BASES", {k: f"http://127.0.0.1:{server.server_address[1]}/{k}" for k in catalog.BASES})
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    yield {"data": data, "seen": seen}
    server.shutdown()


def test_pick_a_series_from_the_catalog_and_download_it_into_a_new_episode(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click("#dvzToolsBtn")   # 21.10.2026: ב"🧰 כלים"
    page.click("#dvzToolCatalog")
    page.wait_for_selector("#dvzCatalogList .dvz-catalog-item")
    page.fill("#dvzCatalogSearch", "תוחלת")
    page.wait_for_function("() => document.querySelectorAll('#dvzCatalogList .dvz-catalog-item').length === 1")
    page.click('#dvzCatalogList [data-catalog-id="wb_life_expectancy"]')
    meta = page.inner_text("#dvzCatalogMeta")
    assert "SP.DYN.LE00.IN" in meta and "שנים" in meta and "הבנק העולמי" in meta
    assert screen["seen"] == []                                          # עד עכשיו - שום הורדה
    page.fill("#dvzCatalogName", "life_expectancy")
    page.click("#dvzCatalogNewBtn")
    page.wait_for_selector('.dvz-card[data-episode="life_expectancy"]')
    assert len(screen["seen"]) == 1 and "SP.DYN.LE00.IN" in screen["seen"][0]
    assert "SP.DYN.LE00.IN" in (screen["data"] / "dataviz_episodes" / "life_expectancy" / "SOURCES.md").read_text(encoding="utf-8")
    assert page.evaluate("() => dvzState.selected") == "life_expectancy"
