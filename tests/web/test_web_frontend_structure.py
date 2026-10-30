# tests/web/test_web_frontend_structure.py
#
# גל 11 (סידור הארכיטקטורה): הדף של ממשק הדפדפן יושב בקבצים נפרדים תחת
# src/entrypoints/web/frontend/ ומורכב לפי frontend/parts.txt. הטסטים כאן שומרים
# על המבנה: אין קובץ יתום, כל קובץ JS עומד בפני עצמו תחבירית, ה-CSS וה-JS נקיים
# מתגיות, והדף המורכב הוא בדיוק מה ש-web_app מגיש - ה-HTML, וה-CSS/JS כ-bundles (גל 24).
import os
import re
import shutil
import subprocess


import pytest

from entrypoints import web_app
from entrypoints.web import frontend_assembly as fa


def _all_frontend_files():
    found = []
    for root, _dirs, files in os.walk(fa.FRONTEND_DIR):
        for name in files:
            if name == "parts.txt":
                continue
            found.append(os.path.relpath(os.path.join(root, name), fa.FRONTEND_DIR).replace(os.sep, "/"))
    return sorted(found)


def test_every_frontend_file_is_assembled_exactly_once():
    parts = fa.page_parts()
    assert len(parts) == len(set(parts))
    assert sorted(parts) == _all_frontend_files(), "קובץ ב-frontend/ שלא ב-parts.txt (או להפך)"


def test_assembled_page_is_what_the_app_serves():
    assert web_app._PAGE_HTML == fa.assemble_page()
    html = web_app._PAGE_HTML
    assert html.startswith("<!doctype html>") and html.rstrip().endswith("</html>")
    # גל 24: אין CSS/JS בתוך הדף - רק קישור אחד לכל bundle
    assert "<style>" not in html and "<script>" not in html
    assert len(re.findall(r'<link rel="stylesheet" href="/static/app\.[0-9a-f]{12}\.css">', html)) == 1
    assert len(re.findall(r'<script src="/static/app\.[0-9a-f]{12}\.js"></script>', html)) == 1
    inline = fa.assemble_inline_page()
    assert inline.count("<style>") == 1 and inline.count("</style>") == 1
    assert inline.count("<script>") == 1 and inline.count("</script>") == 1
    for part in fa.page_parts():
        if not part.startswith("html/"):
            assert fa.read_part(part) in inline, part


def _client():
    from fastapi.testclient import TestClient
    client = TestClient(web_app.app)
    client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
    return client


def test_bundles_are_served_compressed_and_cached_forever():
    client = _client()
    page = client.get("/")
    assert page.headers["cache-control"] == "no-cache"
    assert page.headers["content-encoding"] == "gzip"
    urls = re.findall(r'(?:href|src)="(/static/app\.[0-9a-f]{12}\.(css|js))"', page.text)
    assert sorted(kind for _url, kind in urls) == ["css", "js"]
    for url, kind in urls:
        response = client.get(url)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert response.headers["content-encoding"] == "gzip"
        assert response.headers["content-type"].startswith("text/css" if kind == "css" else "application/javascript")
        assert response.text == fa.bundle(kind)
        plain = client.get(url, headers={"Accept-Encoding": "identity"})
        assert "content-encoding" not in plain.headers and plain.text == fa.bundle(kind)
    assert client.get("/static/app.000000000000.js").status_code == 404
    assert client.get("/static/..%2Fweb_app.py").status_code == 404


def test_the_bundle_name_changes_with_its_content(monkeypatch):
    before = fa.asset_name("js", fa.bundle("js"))
    original = fa.read_part
    monkeypatch.setattr(fa, "read_part", lambda part: original(part) + ("// changed" if part == "js/90-init.js" else ""))
    after = fa.asset_name("js", fa.bundle("js"))
    assert before != after
    assert fa.asset_name("css", fa.bundle("css")) in fa.assemble_page()
    assert after in fa.assemble_page() and before not in fa.assemble_page()


def test_bundles_need_the_access_token():
    from fastapi.testclient import TestClient
    name = next(iter(web_app._PAGE_ASSETS))
    assert TestClient(web_app.app).get("/static/" + name).status_code == 401


def test_css_and_js_parts_are_pure():
    for part in fa.page_parts():
        content = fa.read_part(part)
        if part.endswith(".css"):
            assert "<style" not in content and "</style>" not in content, part
        if part.endswith(".js"):
            assert "<script" not in content and "</script>" not in content, part


def test_parts_are_grouped_html_css_js_in_page_order():
    kinds = [part.split("/")[0] for part in fa.page_parts()]
    assert kinds[0] == "html" and kinds[-1] == "html"
    js = [i for i, kind in enumerate(kinds) if kind == "js"]
    assert js == list(range(js[0], js[-1] + 1)), "קבצי ה-JS חייבים להיות רצף אחד בתוך <script>"


# סבב ייצוב: תהליך node אחד לכל הקבצים (קודם node --check לכל קובץ - ~95 תהליכים, 24 שניות). vm.Script מפרסר כמו
# הדפדפן סקריפט קלאסי, והשגיאה כוללת את שם הקובץ, השורה והקוד שבה
_NODE_PARSE_ALL = r"""
const fs = require("fs"), vm = require("vm");
const failures = [];
for (const file of process.argv.slice(2)) {
  try { new vm.Script(fs.readFileSync(file, "utf8"), {filename: file}); }
  catch (e) { failures.push(String(e.stack).split("\n").slice(0, 5).join("\n")); }
}
if (failures.length) { console.error(failures.join("\n\n")); process.exit(1); }
"""


def _parse_js_files(paths):
    return subprocess.run(["node", "-e", _NODE_PARSE_ALL, *map(str, paths)], capture_output=True, text=True, encoding="utf-8")


@pytest.mark.skipif(not shutil.which("node"), reason="node לא מותקן")
def test_every_js_part_parses_on_its_own(tmp_path):
    paths = []
    for part, content in fa.js_parts():
        path = tmp_path / part   # אותו נתיב כמו ב-parts.txt - כך הוא מופיע בשגיאה
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    result = _parse_js_files(paths)
    assert result.returncode == 0, result.stderr[-3000:]


@pytest.mark.skipif(not shutil.which("node"), reason="node לא מותקן")
def test_a_broken_js_part_is_reported_with_its_file_and_line(tmp_path):
    good, broken = tmp_path / "10-good.js", tmp_path / "20-broken.js"
    good.write_text("function ok() { return 1; }\n", encoding="utf-8")
    broken.write_text("const a = 1;\nconst b = ;\nconst c = 3;\n", encoding="utf-8")
    result = _parse_js_files([good, broken])
    assert result.returncode == 1
    assert f"{broken}:2" in result.stderr and "const b = ;" in result.stderr and "SyntaxError" in result.stderr
    assert "10-good.js" not in result.stderr


def test_dev_reload_serves_freshly_assembled_page(monkeypatch):
    from fastapi.testclient import TestClient
    client = TestClient(web_app.app)
    client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
    monkeypatch.setenv("CLIPFORGE_DEV_RELOAD_PAGE", "1")
    monkeypatch.setattr(fa, "read_part", lambda part: "<!doctype html><p>ZZ-DEV-RELOAD-MARKER</p></html>" if part == fa.page_parts()[0] else "")
    assert "ZZ-DEV-RELOAD-MARKER" in client.get("/").text
    monkeypatch.delenv("CLIPFORGE_DEV_RELOAD_PAGE")
    assert "ZZ-DEV-RELOAD-MARKER" not in client.get("/").text


def test_lazy_screens_are_their_own_bundle():
    # גל 38: קוד עורך הגרפים לא ב-bundle הראשי - נטען כשפותחים את המסך (uiLoadLazy)
    main = fa.bundle("js")
    assert "function loadDataviz(" not in main and "const UI_LAZY_BUNDLES = " in main
    lazy = fa.lazy_bundle("dataviz")
    assert "function loadDataviz(" in lazy and lazy.rstrip().endswith('{"dataviz": true});')
    name = fa.lazy_asset_name("dataviz", lazy)
    assert f'"/static/{name}"' in main
    client = _client()
    response = client.get("/static/" + name)
    assert response.status_code == 200 and response.text == lazy
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    # הדף המלא של הטסטים כולל גם אותו (בלי טעינה)
    assert "function loadDataviz(" in fa.assemble_inline_page()


def test_lazy_html_is_cut_from_the_served_page_and_loaded_before_the_screen_js():
    # סבב ייצוב: ה-HTML של עורך הגרפים (המסך ושני החלונות שלו) לא בדף שהשרת מגיש - רק <template> במקומו
    shell, page, inline = fa._html_shell(), fa.assemble_page(), fa.assemble_inline_page()
    # 23.10.2026: גם מסך "תוצרים", מרכז ההתראות ומסך "📱 בטלפון" (אזור אחד לכל אחד)
    assert fa.lazy_html_names() == ["dataviz", "notifications", "outputs", "phone"]
    assert shell.count("<!-- lazy-html:") == shell.count("<!-- /lazy-html:") == 5
    assert "lazy-html:" not in page and page.count('<template data-lazy-html="dataviz"></template>') == 2
    assert page.count('<template data-lazy-html="outputs"></template>') == 1
    assert page.count('<template data-lazy-html="notifications"></template>') == 1
    assert page.count('<template data-lazy-html="phone"></template>') == 1
    for fragment in fa.lazy_html_fragments("dataviz"):
        assert fragment not in page and fragment in inline       # הדף המלא של הטסטים - כמו שהיה
    for marker in ('id="dvzEpisodes"', 'id="dvzNewDialog"', 'id="dvzHelpBg"', 'id="dvzWizardBg"'):
        assert marker not in page and marker in inline, marker
    assert 'id="dvzNavBtn"' in page                                 # הסרגל העליון נשאר בדף
    # bundle משלו, שה-JS הראשי מכיר וטוען לפני ה-JS של המסך (uiLoadLazy)
    lazy = fa.lazy_html_bundle("dataviz")
    assert 'template[data-lazy-html=\\"dataviz\\"]' in lazy and 'uiBus.emit("ui:lazy-html"' in lazy
    name = fa.lazy_asset_name("dataviz_html", lazy)
    assert f'"dataviz:html": "/static/{name}"' in fa.bundle("js")
    response = _client().get("/static/" + name)
    assert response.status_code == 200 and response.text == lazy
    assert response.headers["content-type"].startswith("application/javascript")


def test_lazy_html_belongs_to_a_lazy_screen_and_main_js_does_not_touch_it():
    # ה-HTML נטען עם ה-JS של המסך שלו - ולכן JS שנטען עם הדף לא יכול לסמוך על האלמנטים האלה
    lazy_parts = fa._lazy_parts()
    main_js = "".join(fa.read_part(p) for p in fa.page_parts() if p.endswith(".js") and p not in lazy_parts)
    for name in fa.lazy_html_names():
        assert name in fa.LAZY_JS, name
        for fragment in fa.lazy_html_fragments(name):
            for element_id in re.findall(r'\bid="([^"]+)"', fragment):
                assert not re.search(r"""["'#]""" + re.escape(element_id) + r"""\b""", main_js), \
                    f"{element_id} (lazy-html:{name}) נגיש מה-JS הראשי - להוציא אותו מהאזור העצל או להעביר את הקוד למסך"


def test_lazy_screens_bring_their_own_css():
    # גל 39: ה-CSS של עורך הגרפים לא ב-bundle הראשי - נוסף לדף כשה-JS של המסך נטען
    main_css = fa.bundle("css")
    assert ".dvz-studio" not in main_css
    lazy = fa.lazy_bundle("dataviz")
    assert lazy.startswith("(() => { const s = document.createElement('style'); s.dataset.lazy = \"dataviz\";") and ".dvz-studio" in lazy
    assert ".dvz-studio" in fa.assemble_inline_page()
