# tests/dataviz/test_dataviz_wave56.py - גל 56: עורך הגרפים והסטודיו. "🎬 פתח בסטודיו" מכין לסרטון מוכן תיקייה משלו
# (utils/dataviz_handoff.py - קישור או עותק; עותק ישן עובר ל-_previous ולא נמחק; התוצר עצמו לא זז), ועורך הגרפים
# נפתח באותה מסגרת כמו הסטודיו (מסך מלא, סרגל עליון, ☰, Pro Dark). הממשק עצמו נבדק בדפדפן ב-test_web_app_wave56_browser.py.
import os
import time


from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web import frontend_assembly as fa
from entrypoints.web_app import app
from dataviz.web import handoff as dh

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _render(path, content, mtime=None):
    """כמו רינדור אמיתי: קובץ זמני ואז החלפה - inode חדש."""
    tmp = str(path) + ".part"
    with open(tmp, "wb") as f:
        f.write(content)
    os.replace(tmp, path)
    if mtime:
        os.utime(path, (mtime, mtime))


# ---------- התיקייה לסטודיו ----------
def test_the_video_gets_its_own_folder_and_the_output_stays(tmp_path):
    out = tmp_path / "dataviz"
    out.mkdir()
    source = out / "ep.mp4"
    _render(source, b"video-1")
    (out / "ep_preview.mp4").write_bytes(b"preview")
    root = tmp_path / "studio"
    result = dh.studio_folder(str(source), str(root))
    assert result["folder"] == str(root / "ep") and result["file"] == "ep.mp4" and result["state"] in ("linked", "copied")
    assert os.listdir(root / "ep") == ["ep.mp4"]                         # רק הסרטון הזה - לא התצוגה המקדימה
    assert (root / "ep" / "ep.mp4").read_bytes() == b"video-1"
    assert source.read_bytes() == b"video-1" and sorted(os.listdir(out)) == ["ep.mp4", "ep_preview.mp4"]
    assert dh.studio_folder(str(source), str(root))["state"] == "ready"   # שוב - אותה תיקייה, בלי לגעת
    assert not (root / dh.PREVIOUS).exists()


def test_a_new_render_replaces_the_copy_and_the_old_one_moves_aside(tmp_path):
    source = tmp_path / "ep.mp4"
    _render(source, b"old", mtime=time.time() - 3600)
    root = tmp_path / "studio"
    dh.studio_folder(str(source), str(root))
    _render(source, b"new render")
    assert dh.studio_folder(str(source), str(root))["state"] in ("linked", "copied")
    assert os.listdir(root / "ep") == ["ep.mp4"] and (root / "ep" / "ep.mp4").read_bytes() == b"new render"
    previous = os.listdir(root / dh.PREVIOUS)                            # מחוץ לתיקיית הסרטון - הסטודיו לא ירנדר אותו
    assert len(previous) == 1 and previous[0].startswith("ep_") and (root / dh.PREVIOUS / previous[0]).read_bytes() == b"old"
    _render(source, b"third")
    os.utime(source, (time.time() + 60, time.time() + 60))
    dh.studio_folder(str(source), str(root))
    assert len(os.listdir(root / dh.PREVIOUS)) == 2                      # שום עותק לא נדרס


def test_copy_when_a_link_is_not_possible(tmp_path, monkeypatch):
    source = tmp_path / "ep.mp4"
    _render(source, b"video")

    def no_link(*_a):
        raise OSError("cross-device link")

    monkeypatch.setattr(dh.os, "link", no_link)
    result = dh.studio_folder(str(source), str(tmp_path / "studio"))
    assert result["state"] == "copied" and (tmp_path / "studio" / "ep" / "ep.mp4").read_bytes() == b"video"
    assert dh.studio_folder(str(source), str(tmp_path / "studio"))["state"] == "ready"   # copy2 שומר את הזמן


def test_a_video_named_like_the_previous_folder(tmp_path):
    source = tmp_path / "_previous.mp4"
    _render(source, b"v")
    assert dh.studio_folder(str(source), str(tmp_path / "studio"))["folder"] == str(tmp_path / "studio" / "_previous_video")


# ---------- הנתיב בשרת ----------
def test_the_route_prepares_the_folder_and_validates_the_name(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(tmp_path))
    out = tmp_path / "dataviz" / "outputs" / "horizontal"
    out.mkdir(parents=True)
    (out / "ep.mp4").write_bytes(b"video")
    (out / "ep_stills").mkdir()
    (tmp_path / "secret.mp4").write_bytes(b"x")
    for body in ({"orientation": "horizontal", "name": "missing.mp4"}, {"orientation": "horizontal", "name": "../../secret.mp4"},
                 {"orientation": "sideways", "name": "ep.mp4"}, {"orientation": "horizontal", "name": "ep_stills"},
                 {"orientation": "horizontal", "name": ".hidden.mp4"}):
        assert client.post("/api/dataviz/outputs/studio", json=body).status_code == 404, body
    resp = client.post("/api/dataviz/outputs/studio", json={"orientation": "horizontal", "name": "ep.mp4"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["folder"] == str(tmp_path / "dataviz" / "studio_handoff" / "horizontal" / "ep") and data["file"] == "ep.mp4"
    assert (tmp_path / "dataviz" / "studio_handoff" / "horizontal" / "ep" / "ep.mp4").read_bytes() == b"video"
    assert (out / "ep.mp4").read_bytes() == b"video"
    names = [o["name"] for o in client.get("/api/dataviz/outputs").json()["outputs"]]
    assert sorted(names) == ["ep.mp4", "ep_stills"]                      # תיקיית הסטודיו לא נכנסת לתוצרים


# ---------- המסגרת המשותפת והכפתור (מקור) ----------
def test_the_shell_and_the_button_are_wired():
    assert "js/87-dataviz-shell.js" in fa.LAZY_JS["dataviz_pro"]
    pro = fa.lazy_bundle("dataviz_pro")
    assert "/api/dataviz/outputs/studio" in pro and "openProject(data.folder)" in pro
    assert "_dvzStudioButton(out, actions)" in fa.lazy_bundle("dataviz_tools")   # 20.10.2026: הפרסום (86) ב-bundle השלישי
    assert 'getElementById("dvzTopbarEpisode")' in fa.lazy_bundle("dataviz")
    page, js, css = fa.assemble_page(), fa.bundle("js"), fa.bundle("css")
    assert 'id="dvzNavBtn"' in page and 'onclick="dvzToggleNav()"' in page and 'id="dvzTopbarEpisode"' in page
    assert "switchTab('dataviz')" in page                                # ומהסטודיו - חזרה לעורך הגרפים
    assert "function dvzToggleNav" in js and '"dvz-focus"' in js
    assert "body.dvz-focus > .nav-rail" in css and "body.dvz-focus.dvz-nav-open" in css
    assert css.count("body.dvz-focus {") >= 2                            # גם ה-Pro Dark של הסטודיו
