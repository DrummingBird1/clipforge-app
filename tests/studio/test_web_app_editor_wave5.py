# tests/studio/test_web_app_editor_wave5.py
#
# גל 5 של 102-ההצעות - תור העיבוד (items 51-57): שורות עשירות (ממוזערת/משך/
# רזולוציה/HDR), בחירה מרובה לפעולות קבוצתיות, גרירת קבצים מהמערכת (העתקה
# לתיקייה), סטטוס מהריצה האחרונה, סינון תור, מתג תתי-תיקיות, ושמירת תור עם פרופיל.
import json
from tests import PROJECT_ROOT
import os
import shutil
import subprocess
import sys


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.video import video_editor_profiles as vep

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

BASE_DIR = PROJECT_ROOT
from utils.shared.workspace_dir import WORKSPACE_DIR  # הזמני של הריצה (tests/conftest.py) - לא workspace/ של המשתמש
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "video_editor.py")


def _ffmpeg_available():
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    exe = get_ffmpeg_exe()
    return (os.path.isabs(exe) and os.path.exists(exe)) or bool(shutil.which(exe))


needs_ffmpeg = pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg לא זמין")


def _make_clip(path, duration=3, size="320x180"):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=10", "-pix_fmt", "yuv420p", str(path)],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "profiles" / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "profiles" / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "profiles" / "video_editor_profile_history.json"))
    monkeypatch.setattr(web_app, "PREVIEWS_DIR", str(tmp_path / "previews"))
    monkeypatch.setattr(web_app, "RUN_MANIFESTS_DIR", str(tmp_path / "manifests"))
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: None)


# --- 56: מתג תתי-תיקיות ---

def test_build_extra_args_no_subfolders_only_on_explicit_false():
    assert "--no-subfolders" in web_app._build_extra_args("video_editor.py", {"include_subfolders": False})
    assert "--no-subfolders" not in web_app._build_extra_args("video_editor.py", {"include_subfolders": True})
    assert "--no-subfolders" not in web_app._build_extra_args("video_editor.py", {})  # פרופיל ישן


def test_queue_fields_are_profile_fields_and_roundtrip():
    from utils.video.video_editor_field_help import FIELD_HELP
    for key in ("include_subfolders", "queue_files"):
        assert key in vep.PROFILE_FIELDS and key in FIELD_HELP
    vep.save_profile("Q", {"include_subfolders": False, "queue_files": [{"name": "b.mp4", "selected": True}, {"name": "a.mp4", "selected": False}]})
    saved = vep.load_profiles()["Q"]
    assert saved["include_subfolders"] is False
    assert saved["queue_files"][1] == {"name": "a.mp4", "selected": False}


@needs_ffmpeg
def test_e2e_no_subfolders_skips_nested_folders(tmp_path):
    from tests.conftest import remove_video_editor_output
    root = tmp_path / "root"
    (root / "nested").mkdir(parents=True)
    _make_clip(root / "top_level_w5.mp4", duration=1)
    _make_clip(root / "nested" / "nested_w5.mp4", duration=1)
    out_dir = os.path.join(WORKSPACE_DIR, "studio", "horizontal")
    top_out = os.path.join(out_dir, "top_level_w5_edited_horizontal.mp4")
    nested_out = os.path.join(out_dir, "nested", "nested_w5_edited_horizontal.mp4")
    for path in (top_out, nested_out):
        remove_video_editor_output(path)
    manifest_path = None
    try:
        result = subprocess.run([sys.executable, SCRIPT, "--input_dir", str(root), "--no-subfolders"],
                                cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=180)
        line = next(ln for ln in result.stdout.splitlines() if ln.startswith("RESULT: "))
        parsed = json.loads(line[len("RESULT: "):])
        manifest_path = parsed.get("manifest_path")
        assert parsed["files_created"] == 1, result.stdout
        assert os.path.exists(top_out) and not os.path.exists(nested_out)
    finally:
        for path in (top_out, nested_out):
            remove_video_editor_output(path)
        if manifest_path and os.path.exists(manifest_path):
            os.remove(manifest_path)


# --- 51: probe לקבוצה + ממוזערת מקור ---

@needs_ffmpeg
def test_probe_batch_returns_rich_info_and_ignores_traversal(tmp_path):
    _make_clip(tmp_path / "a.mp4", duration=2)
    data = client.post("/api/video_editor/probe_batch", json={"folder": str(tmp_path), "names": ["a.mp4", "..\\..\\evil.mp4", "missing.mp4"]}).json()
    assert list(data["files"]) == ["a.mp4"]
    info = data["files"]["a.mp4"]
    assert abs(info["duration"] - 2) < 0.3 and (info["width"], info["height"]) == (320, 180)
    assert info["hdr"] is False and info["size"] > 0 and info["mtime"] > 0
    assert client.post("/api/video_editor/probe_batch", json={"folder": "Z:\\nope", "names": []}).status_code == 400


@needs_ffmpeg
def test_file_thumbnail_is_generated_and_cached(tmp_path):
    _make_clip(tmp_path / "a.mp4", duration=2)
    first = client.get("/api/video_editor/file_thumbnail", params={"path": str(tmp_path / "a.mp4")})
    assert first.status_code == 200 and first.headers["content-type"] == "image/jpeg"
    assert len(os.listdir(tmp_path / "previews")) == 1
    assert client.get("/api/video_editor/file_thumbnail", params={"path": str(tmp_path / "a.mp4")}).status_code == 200
    assert len(os.listdir(tmp_path / "previews")) == 1
    assert client.get("/api/video_editor/file_thumbnail", params={"path": str(tmp_path / "missing.mp4")}).status_code == 404


def test_file_thumbnail_without_ffmpeg_is_a_clean_error(tmp_path, monkeypatch):
    """גל 19: מסך העבודות מבקש ממוזערת לכל פרויקט - בלי ffmpeg (למשל ב-CI) זו תשובת שגיאה, לא חריגה לא מטופלת."""
    (tmp_path / "a.mp4").write_bytes(b"x")
    monkeypatch.setattr(web_app, "get_ffmpeg_exe", lambda: str(tmp_path / "no_such_ffmpeg.exe"))
    response = client.get("/api/video_editor/file_thumbnail", params={"path": str(tmp_path / "a.mp4")})
    assert response.status_code == 500 and "error" in response.json()


# --- 53: העלאה (גרירה מהמערכת) ---

def test_upload_writes_file_and_never_overwrites(tmp_path):
    resp = client.post("/api/video_editor/upload", params={"folder": str(tmp_path), "name": "dropped.mp4"}, content=b"video-bytes")
    assert resp.status_code == 200 and resp.json()["size"] == 11
    assert (tmp_path / "dropped.mp4").read_bytes() == b"video-bytes"
    again = client.post("/api/video_editor/upload", params={"folder": str(tmp_path), "name": "dropped.mp4"}, content=b"other")
    assert again.status_code == 409 and (tmp_path / "dropped.mp4").read_bytes() == b"video-bytes"


def test_upload_rejects_bad_names_folders_and_empty_bodies(tmp_path):
    assert client.post("/api/video_editor/upload", params={"folder": str(tmp_path), "name": "notes.txt"}, content=b"x").status_code == 400
    assert client.post("/api/video_editor/upload", params={"folder": "Z:\\nope", "name": "a.mp4"}, content=b"x").status_code == 400
    assert client.post("/api/video_editor/upload", params={"folder": str(tmp_path), "name": "empty.mp4"}, content=b"").status_code == 400
    traversal = client.post("/api/video_editor/upload", params={"folder": str(tmp_path), "name": "..\\..\\escape.mp4"}, content=b"x")
    assert traversal.status_code == 200 and (tmp_path / "escape.mp4").exists()
    assert not any(n.startswith(".upload_") for n in os.listdir(tmp_path))  # בלי שאריות קבצים זמניים


# --- דפדפן אמיתי ---

def _open_queue(page, folder):
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(folder))
    page.evaluate("() => { veScrollToCategory('queue'); return refreshVeQueue(); }")
    page.wait_for_function("() => _veQueueState.length > 0", timeout=15000)


def _fake_clips(folder, names):
    for name in names:
        (folder / name).write_bytes(b"x")


def test_browser_multi_select_bulk_actions(editor_page, tmp_path):
    _fake_clips(tmp_path, ["a.mp4", "b.mp4", "c.mp4", "d.mp4"])
    _open_queue(editor_page, tmp_path)
    rows = editor_page.locator("#veQueueList .ve-queue-row")
    rows.nth(1).locator(".ve-queue-name").click()
    rows.nth(3).locator(".ve-queue-name").click(modifiers=["Shift"])
    assert editor_page.evaluate("() => _veQueueState.filter(f => f._picked).map(f => f.name)") == ["b.mp4", "c.mp4", "d.mp4"]
    editor_page.locator("#veQueueList .ve-queue-row").nth(2).locator(".ve-queue-name").click(modifiers=["Control"])
    assert editor_page.evaluate("() => _veQueueState.filter(f => f._picked).map(f => f.name)") == ["b.mp4", "d.mp4"]
    # גל 27: הפעולות הקבוצתיות בפס צף שמופיע רק כשיש שורות מסומנות
    assert editor_page.is_visible("#veQueueBulkBar")
    editor_page.click("#veQueueBulkBar button:has-text('הוצא')")
    assert editor_page.evaluate("() => _veQueueState.filter(f => f.selected).map(f => f.name)") == ["a.mp4", "c.mp4"]
    editor_page.click("#veQueueBulkBar button:has-text('לראש')")
    assert editor_page.evaluate("() => _veQueueState.map(f => f.name)") == ["b.mp4", "d.mp4", "a.mp4", "c.mp4"]
    assert editor_page.evaluate("() => _collectRunOptions().only_files") == ["a.mp4", "c.mp4"]


def test_browser_row_pencil_opens_clip_mode_for_that_file(editor_page, tmp_path):
    # גל 30: ✏️ בשורה = מצב עריכת קליפ לקובץ הזה (במקום עורך הדריסות שהיה נפתח בתוך השורה)
    _fake_clips(tmp_path, ["a.mp4", "b.mp4", "c.mp4"])
    _open_queue(editor_page, tmp_path)
    editor_page.click("#veQueueList .ve-queue-row[data-name='c.mp4'] .ve-queue-clip-btn")
    assert editor_page.evaluate("() => [_veTimeScope, _veClipScopeFile, document.getElementById('vePreviewFile').value]") == ["clip", "c.mp4", "c.mp4"]
    assert editor_page.is_visible("#veClipBanner")
    editor_page.fill("#veTrimStart", "4")
    editor_page.dispatch_event("#veTrimStart", "input")
    assert editor_page.evaluate("() => _collectRunOptions().clip_edits") == {"c.mp4": {"trim_start": 4, "trim_duration": None, "remove_ranges": []}}
    editor_page.wait_for_function("() => (document.querySelector(\"#veQueueList .ve-queue-row[data-name='c.mp4'] .ve-clip-badge\") || {}).textContent === '✏️ 1'")
    editor_page.click("#veQueueList .ve-queue-row[data-name='c.mp4'] .ve-queue-clip-btn")  # לחיצה חוזרת = סיום
    assert editor_page.evaluate("() => _veTimeScope") == "recipe"


@needs_ffmpeg
def test_browser_rich_rows_and_duration_filter(editor_page, tmp_path):
    _make_clip(tmp_path / "short.mp4", duration=2)
    _make_clip(tmp_path / "long.mp4", duration=8)
    _open_queue(editor_page, tmp_path)
    editor_page.wait_for_function("() => document.querySelectorAll('#veQueueList .ve-queue-meta')[0].textContent.includes('320×180')", timeout=30000)
    editor_page.wait_for_function("() => Array.from(document.querySelectorAll('.ve-queue-thumb')).every(i => i.naturalWidth > 0)", timeout=30000)
    editor_page.click("#veQueueFilterBtn")  # גל 27: הסינון מתקפל מאחורי כפתור
    editor_page.fill("#veQueueFilterMinSeconds", "0:05")
    editor_page.click("button:has-text('🔍 סנן')")
    assert editor_page.evaluate("() => _veQueueState.filter(f => f.selected).map(f => f.name)") == ["long.mp4"]
    editor_page.click("#veQueueToolbar button:has-text('נקה'):not(:has-text('בחירה'))")
    assert editor_page.evaluate("() => _veQueueState.every(f => f.selected)")


def test_browser_last_run_status_badges(editor_page, editor_server, tmp_path, monkeypatch):
    _fake_clips(tmp_path, ["ok.mp4", "bad.mp4", "new.mp4"])
    manifests = tmp_path / "manifests_browser"
    manifests.mkdir()
    monkeypatch.setattr(editor_server["web_app"], "RUN_MANIFESTS_DIR", str(manifests))
    (manifests / "20260101_000000_1.json").write_text(json.dumps({
        "input_dir": str(tmp_path), "finished_at": "2026-01-01T00:00:00",
        "files": [{"source": "ok.mp4", "status": "created"}, {"source": "bad.mp4", "status": "error", "reason": "boom"}],
    }), encoding="utf-8")
    _open_queue(editor_page, tmp_path)
    editor_page.wait_for_function("() => document.querySelectorAll('#veQueueList .ve-badge-status').length === 2", timeout=15000)
    badges = editor_page.evaluate("() => Object.fromEntries(Array.from(document.querySelectorAll('#veQueueList .ve-queue-row')).map(r => [r.querySelector('.ve-queue-name').textContent.split('. ')[1], (r.querySelector('.ve-badge-status') || {}).textContent || '']))")
    assert badges == {"bad.mp4": "❌", "new.mp4": "", "ok.mp4": "✅"}
    editor_page.click("#veQueueFilterBtn")
    editor_page.check("#veQueueFilterNotCreated")
    editor_page.click("button:has-text('🔍 סנן')")
    assert editor_page.evaluate("() => _veQueueState.filter(f => f.selected).map(f => f.name).sort()") == ["bad.mp4", "new.mp4"]


def test_browser_drop_files_copies_into_folder_after_confirm(editor_page, tmp_path):
    _fake_clips(tmp_path, ["existing.mp4"])
    _open_queue(editor_page, tmp_path)
    editor_page.evaluate("() => { window.__dropDone = _veUploadDroppedFiles([new File(['abc'], 'dropped_in.mp4'), new File(['x'], 'skip.txt')]); }")
    editor_page.wait_for_selector("#veConfirmModalBg.show")
    assert "1 קבצים" in editor_page.inner_text("#veConfirmMessage")
    editor_page.click("#veConfirmOkBtn")
    editor_page.wait_for_function("() => _veQueueState.some(f => f.name === 'dropped_in.mp4')", timeout=15000)
    assert (tmp_path / "dropped_in.mp4").read_bytes() == b"abc"
    assert not (tmp_path / "skip.txt").exists()


def test_browser_subfolders_toggle_defaults_on_even_for_old_profiles(editor_page):
    assert editor_page.evaluate("() => document.getElementById('veIncludeSubfolders').checked") is True
    editor_page.evaluate("() => _applyVideoEditorFields({codec: 'h264'})")  # פרופיל ישן בלי המפתח
    assert editor_page.evaluate("() => document.getElementById('veIncludeSubfolders').checked") is True
    editor_page.evaluate("() => _applyVideoEditorFields({include_subfolders: false})")
    assert editor_page.evaluate("() => _collectRunOptions().include_subfolders") is False
    assert "בלי תתי-תיקיות" in editor_page.evaluate("() => { _veRenderSummaryCard(); return document.getElementById('veSummaryText').textContent; }")


def test_browser_queue_saved_with_profile_and_restored(editor_page, tmp_path):
    _fake_clips(tmp_path, ["a.mp4", "b.mp4", "c.mp4"])
    _open_queue(editor_page, tmp_path)
    editor_page.evaluate("() => { _veQueueState.reverse(); _veQueueState[1].selected = false; _veQueueDirty = true; _renderVeQueue(); }")
    editor_page.evaluate("() => openVeProfileManager()")  # גל 10: שמירה בשם עברה לדיאלוג הפרופילים
    editor_page.check("#veSaveQueueWithProfile")
    editor_page.fill("#veProfileName", "With Queue")
    editor_page.on("dialog", lambda d: d.accept())  # הודעת "נשמר" + אישור "לוותר על שינויים לא-שמורים" במעבר
    editor_page.evaluate("() => saveVideoEditorProfile()")
    editor_page.wait_for_function("() => document.getElementById('vePreset').value === 'profile:With Queue'")
    # מאפסים את התור ואז טוענים את הפרופיל מחדש
    editor_page.evaluate("() => { _onVeFolderChanged(); document.getElementById('vePreset').value = ''; applyVideoEditorPreset(); }")
    # התור אופס -> שינוי לא-שמור -> אישור המעבר עכשיו ב-veConfirm (גל 9, item 102), לא confirm() של הדפדפן
    editor_page.wait_for_selector("#veConfirmModalBg.show")
    editor_page.click("#veConfirmOkBtn")
    editor_page.wait_for_function("() => document.getElementById('vePreset').value === ''")
    editor_page.evaluate("() => { document.getElementById('vePreset').value = 'profile:With Queue'; applyVideoEditorPreset(); }")
    # התור של הפרופיל מוחל אחרי רענון התיקייה (veFlow) - מחכים למצב הסופי, לא לרגע הראשון
    # שבו יש 3 קבצים (בסדר התיקייה). נכשל רק אם התור של הפרופיל לא מוחל בכלל.
    expected = [["c.mp4", True], ["b.mp4", False], ["a.mp4", True]]
    try:
        editor_page.wait_for_function("(expected) => JSON.stringify(_veQueueState.map(f => [f.name, f.selected])) === JSON.stringify(expected)",
                                      arg=expected, timeout=15000)
    except Exception:
        pass
    assert editor_page.evaluate("() => _veQueueState.map(f => [f.name, f.selected])") == expected


def test_browser_profile_queue_survives_a_slow_project_load(editor_page, tmp_path):
    """נמצא ב-CI: טעינת הפרויקט של התיקייה (ברקע, אחרי החלפת תיקייה) הסתיימה אחרי
    שהמשתמש כבר שחזר תור מפרופיל - ורעננה את התור לסדר ברירת-המחדל. עכשיו הבחירה
    של המשתמש גוברת."""
    _fake_clips(tmp_path, ["a.mp4", "b.mp4", "c.mp4"])
    _open_queue(editor_page, tmp_path)
    editor_page.evaluate("() => { _veQueueState.reverse(); _veQueueState[1].selected = false; _veQueueDirty = true; _renderVeQueue(); }")
    editor_page.evaluate("() => openVeProfileManager()")
    editor_page.check("#veSaveQueueWithProfile")
    editor_page.fill("#veProfileName", "Slow Project")
    editor_page.on("dialog", lambda d: d.accept())
    editor_page.evaluate("() => saveVideoEditorProfile()")
    editor_page.wait_for_function("() => document.getElementById('vePreset').value === 'profile:Slow Project'")
    # תיקייה בלי פרויקט שמור, ותשובה שמגיעה באיחור (fetch בתוך הדף - הבקשות עוברות דרך
    # ה-service worker, ש-page.route לא רואה)
    editor_page.evaluate("""() => { const realFetch = window.fetch; window.fetch = (url, ...rest) => String(url).includes('/api/editor_projects/by_folder')
        ? new Promise(resolve => setTimeout(() => resolve(new Response(JSON.stringify({project: null}), {headers: {'Content-Type': 'application/json'}})), 1500))
        : realFetch(url, ...rest); }""")
    # החלפת תיקייה (טעינת הפרויקט מתחילה ונתקעת 1.5 שניות) ומיד בחירת הפרופיל עם התור
    editor_page.evaluate("() => { _onVeFolderChanged(); state.vePresetPrevious = ''; captureVideoEditorBaseline(); document.getElementById('vePreset').value = 'profile:Slow Project'; applyVideoEditorPreset(); }")
    expected = [["c.mp4", True], ["b.mp4", False], ["a.mp4", True]]
    editor_page.wait_for_function("(expected) => JSON.stringify(_veQueueState.map(f => [f.name, f.selected])) === JSON.stringify(expected)", arg=expected, timeout=15000)
    editor_page.wait_for_function("() => _veProjectLoadedFor === state.folder", timeout=15000)
    editor_page.wait_for_timeout(800)
    assert editor_page.evaluate("() => _veQueueState.map(f => [f.name, f.selected])") == expected
