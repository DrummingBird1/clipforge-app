# tests/fake_gemini.py
#
# שרת HTTP מקומי שמחקה את generateContent של Gemini - הקוד האמיתי (google-genai SDK בתוך
# story_cutter.py / title_generator.py) מדבר איתו דרך GOOGLE_GEMINI_BASE_URL, כך שבודקים תגובת HTTP
# אמיתית (כולל 429 RESOURCE_EXHAUSTED בפורמט של גוגל) בלי רשת, בלי מפתח אמיתי ובלי לצרוך מכסה.
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

QUOTA_BODY = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                        "message": "You exceeded your current quota, please check your plan and billing details."}}


def ok_reply(text):
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP", "index": 0}]}


class FakeGemini:
    """script = רשימת תגובות לפי סדר הבקשות: ("ok", טקסט) או ("429", None). אחרי הסוף חוזרת התגובה האחרונה."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                with outer._lock:
                    index = len(outer.requests)
                    outer.requests.append(self.path)
                kind, text = outer.script[min(index, len(outer.script) - 1)]
                status, body = (429, QUOTA_BODY) if kind == "429" else (200, ok_reply(text))
                payload = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def env(self):
        return {"GOOGLE_GEMINI_BASE_URL": self.url, "GEMINI_API_KEY": "fake-key-for-tests"}