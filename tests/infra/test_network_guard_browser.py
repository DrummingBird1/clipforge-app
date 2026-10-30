# tests/infra/test_network_guard_browser.py
#
# 23.10.2026: Edge של הטסטים (edge_browser) עולה מאחורי proxy חוסם (network_proxy ב-tests/conftest.py), כך שגם בקשה של service
# worker - ש-page.route לא רואה - לא יוצאת. בלי ה-proxy הבקשה הייתה הולכת ל-DNS (ונכשלת שם, כי example.invalid לא קיים) וה-proxy
# לא היה רואה אותה - הטסט נכשל.
import functools
import http.server
import threading

import pytest

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning")]

_SERVICE_WORKER = """
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
  if (new URL(event.request.url).pathname !== "/probe") return;
  event.respondWith(fetch("http://example.invalid/from-service-worker", {mode: "no-cors"})
    .then((response) => new Response("reached:" + response.type), (error) => new Response("failed:" + error.name)));
});
"""

_REGISTER_AND_PROBE = """async () => {
  await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  if (!navigator.serviceWorker.controller) {
    await new Promise((resolve) => navigator.serviceWorker.addEventListener("controllerchange", resolve));
  }
  return (await fetch("/probe")).text();
}"""


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    # service worker נרשם רק עם MIME של JavaScript - לא סומכים על ה-registry של Windows
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def log_message(self, *args):
        pass


@pytest.fixture
def local_site(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>network guard</title>", encoding="utf-8")
    (tmp_path / "sw.js").write_text(_SERVICE_WORKER, encoding="utf-8")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_QuietHandler, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_a_service_worker_fetch_to_the_internet_is_blocked(edge_browser, network_proxy, local_site):
    context = edge_browser.new_context()
    try:
        page = context.new_page()
        page.goto(f"{local_site}/index.html")
        result = page.evaluate(_REGISTER_AND_PROBE)
    finally:
        context.close()
    assert result.startswith("failed:"), result                            # ה-service worker ניסה, והבקשה נכשלה
    assert network_proxy.seen("example.invalid/from-service-worker"), network_proxy.requests   # ב-proxy החוסם, לא באינטרנט
