# tests/studio/test_web_app_editor_dogfood_browser.py
#
# הרצה אמיתית מקצה לקצה של הסטודיו (16.10, פרויקט אמיתי בעותק זמני) - מה שנמצא ותוקן:
# פתיחת פרויקט דרסה תוך שניות את ההגדרות שבו בהגדרות שבטופס (בלי שום פעולה של המשתמש), שינוי שנעשה פחות
# מ-1.5 שנ' לפני רענון אבד, שמות באנגלית בתור נחתכו מההתחלה ("…ugh.mp4" בכל השורות), ושדות החיתוך התכווצו
# ל-16px בעמודת המפקח. חלק ב': פתיחת פרויקט מחילה את ההגדרות שלו כשאין בטופס עבודה שלא נשמרה (בלי "החל" בכל
# פתיחה), בחירת סגנון לא מוחקת יעדים ושכבות, אזהרה כשיש שמע במקור ו"שמירת אודיו" כבויה, וסרטון מעורך הגרפים
# נפתח עם "שמירת אודיו".
import subprocess
import time


import pytest

from tests.media_support import needs_ffmpeg
from utils.video import editor_projects
from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _open_folder(page, folder):
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(folder))
    page.wait_for_function("(f) => _veProjectLoadedFor === f", arg=str(folder), timeout=15000)


def _wait_saved(page):
    page.wait_for_function("() => _veProjectSaveInfo.state === 'saved' && !_veProjectPendingSince", timeout=10000)


def _saved_project(folder, check, timeout=4.0):
    deadline = time.time() + timeout
    while True:
        project = editor_projects.load_project(str(folder)) or {}
        if check(project) or time.time() > deadline:
            return project
        time.sleep(0.1)


def _unsaved_form_edit(page):
    page.fill("#veTrimStart", "3")                                      # עבודה בטופס שעוד לא נשמרה באף פרויקט


def test_opening_a_project_applies_its_settings_when_nothing_is_unsaved(editor_page, tmp_path):
    page = editor_page
    first, second = tmp_path / "first", tmp_path / "second"
    for folder in (first, second):
        folder.mkdir()
        (folder / "a.mp4").write_bytes(b"x")
    editor_projects.save_project(str(second), {"recipe": {"codec": "hevc", "vertical": True}, "targets": []})
    _open_folder(page, second)                                         # דף חדש - בלי "החל" בכל פתיחה
    assert page.is_hidden("#veProjectBanner")
    assert page.evaluate("() => [_collectRunOptions().codec, _collectRunOptions().vertical]") == ["hevc", True]
    _open_folder(page, first)                                          # עבודה בתיקייה אחרת - נשמרת בפרויקט שלה
    _unsaved_form_edit(page)
    _wait_saved(page)
    _open_folder(page, second)
    assert page.is_hidden("#veProjectBanner")
    assert page.evaluate("() => _collectRunOptions().codec") == "hevc"


def test_opening_a_project_keeps_its_settings_until_the_user_chooses(editor_page, tmp_path):
    page = editor_page
    (tmp_path / "a.mp4").write_bytes(b"x")
    editor_projects.save_project(str(tmp_path), {"recipe": {"codec": "av1", "vertical": True}, "targets": []})
    _unsaved_form_edit(page)
    _open_folder(page, tmp_path)
    assert page.is_visible("#veProjectApplyRecipeBtn")
    page.click("#veTargetChips button[data-target=tiktok]")          # שינוי אחר - השמירה האוטומטית רצה
    _wait_saved(page)
    project = editor_projects.load_project(str(tmp_path))
    assert project["targets"] == ["tiktok"]
    assert project["recipe"] == {"codec": "av1", "vertical": True}   # קודם: ההגדרות של הטופס (h264, אופקי)
    page.click("#veProjectBanner button[aria-label='השאר את ההגדרות הנוכחיות']")
    _wait_saved(page)
    assert editor_projects.load_project(str(tmp_path))["recipe"]["codec"] == "h264"
    assert page.is_hidden("#veProjectBanner")


def test_applying_the_project_settings_saves_them(editor_page, tmp_path):
    page = editor_page
    (tmp_path / "a.mp4").write_bytes(b"x")
    editor_projects.save_project(str(tmp_path), {"recipe": {"codec": "hevc"}, "targets": []})
    _unsaved_form_edit(page)
    _open_folder(page, tmp_path)
    page.click("#veProjectApplyRecipeBtn")
    assert page.evaluate("() => _collectRunOptions().codec") == "hevc"
    _wait_saved(page)
    recipe = editor_projects.load_project(str(tmp_path))["recipe"]
    assert recipe["codec"] == "hevc" and "keep_audio" in recipe                # מעכשיו - כל ההגדרות שבטופס


def test_a_change_right_before_reload_is_saved(editor_page, tmp_path):
    page = editor_page
    (tmp_path / "a.mp4").write_bytes(b"x")
    _open_folder(page, tmp_path)
    page.click("#veTargetChips button[data-target=reels]")
    # עוזבים את הדף בתוך ההמתנה של השמירה האוטומטית (1.5 שנ'). about:blank נטען מיד - ברענון רגיל הטיימר
    # של הדף הישן הספיק לפעמים לרוץ עד שהשרת החזיר את הדף החדש, והטסט עבר גם בלי התיקון
    page.goto("about:blank")
    project = _saved_project(tmp_path, lambda p: p.get("targets") == ["reels"])
    assert project.get("targets") == ["reels"]


def test_queue_names_and_the_preview_picker_start_from_the_beginning(editor_page, tmp_path):
    page = editor_page
    for name in ("Busway Islands - Puzzle Walkthrough.mp4", "קליפ בעברית.mp4"):
        (tmp_path / name).write_bytes(b"x")
    _open_folder(page, tmp_path)
    page.wait_for_function("() => document.querySelectorAll('#veQueueList .ve-queue-name').length === 2", timeout=10000)
    directions = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#veQueueList .ve-queue-name')]
        .map(n => [n.title, getComputedStyle(n).direction]))""")
    assert directions == {"Busway Islands - Puzzle Walkthrough.mp4": "ltr", "קליפ בעברית.mp4": "rtl"}
    assert page.evaluate("() => getComputedStyle(document.getElementById('vePreviewFile')).direction") == "ltr"


def test_leaving_asks_only_when_the_style_really_changed(editor_page, tmp_path, monkeypatch):
    from utils.video import video_editor_profiles as vep
    for attr, name in (("PROFILES_PATH", "p.json"), ("META_PATH", "m.json"), ("HISTORY_PATH", "h.json")):
        monkeypatch.setattr(vep, attr, str(tmp_path / name))
    vep.save_profile("Base", {"codec": "h264"})
    page = editor_page
    asks = "() => { const e = new Event('beforeunload', {cancelable: true}); window.dispatchEvent(e); return e.defaultPrevented; }"
    page.evaluate("() => loadVideoEditorProfiles()")
    page.evaluate("() => { document.getElementById('vePreset').value = 'profile:Base'; applyVideoEditorPreset(); }")
    page.wait_for_function("() => !!state.veBaseline")
    assert page.evaluate(asks) is False                                 # הסגנון כמו שנשמר - אין מה לאבד
    page.evaluate("() => { const c = _veEl('veCodec'); c.value = 'av1'; c.dispatchEvent(new Event('change', {bubbles: true})); }")
    assert page.evaluate(asks) is True


def test_picking_a_style_keeps_the_projects_targets_and_layers(editor_page, tmp_path, monkeypatch):
    from utils.video import video_editor_profiles as vep
    for attr, name in (("PROFILES_PATH", "p.json"), ("META_PATH", "m.json"), ("HISTORY_PATH", "h.json")):
        monkeypatch.setattr(vep, attr, str(tmp_path / name))
    logo = {"type": "text", "text": "LOGO", "start": 0, "end": None, "position": "top-left", "opacity": 1}
    vep.save_profile("Plain", {"codec": "hevc", "targets": [], "layers": []})
    vep.save_profile("Branded", {"codec": "h264", "targets": ["youtube"], "layers": [logo]})
    page = editor_page
    page.click("#veTargetChips button[data-target=tiktok]")
    page.evaluate("() => { addVeLayer('text'); const l = _veLayersValue(); l[0].text = 'שלי'; _veWriteLayers(l); _veRenderLayersEditor(true); }")
    page.evaluate("() => loadVideoEditorProfiles()")
    state = "() => ({codec: _veEl('veCodec').value, targets: _veTargets(), layers: _veLayersValue().map(l => l.text)})"
    pick = "(name) => { _veEl('vePreset').value = 'profile:' + name; applyVideoEditorPreset(); }"
    page.evaluate(pick, "Plain")
    assert page.evaluate(state) == {"codec": "hevc", "targets": ["tiktok"], "layers": ["שלי"]}   # קודם: [] ו-[]
    page.evaluate(pick, "Branded")
    assert page.evaluate(state) == {"codec": "h264", "targets": ["youtube"], "layers": ["שלי", "LOGO"]}
    page.evaluate(pick, "Branded")
    assert page.evaluate(state)["layers"] == ["שלי", "LOGO"]                                       # בלי כפילות


@needs_ffmpeg
def test_sound_in_the_queue_with_keep_audio_off_warns(editor_page, tmp_path):
    subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "color=black:size=160x90:duration=1:rate=10", "-f", "lavfi", "-i", "sine=duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(tmp_path / "music.mp4")],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)
    page = editor_page
    _open_folder(page, tmp_path)
    page.wait_for_function("() => [...document.querySelectorAll('#veWarningsBox .ve-warning')].some(w => w.textContent.includes('יש שמע'))", timeout=15000)
    page.evaluate("() => _veRevealElement(_veEl('veAudioSource'))")
    page.select_option("#veAudioSource", "original")
    page.wait_for_function("() => ![...document.querySelectorAll('#veWarningsBox .ve-warning')].some(w => w.textContent.includes('יש שמע'))")


def test_a_video_from_the_graph_editor_keeps_its_music(editor_page, tmp_path):
    folder = tmp_path / "dataviz" / "studio_handoff" / "vertical" / "alarms"                     # utils/dataviz_handoff.py
    folder.mkdir(parents=True)
    (folder / "alarms.mp4").write_bytes(b"x")
    page = editor_page
    assert page.input_value("#veAudioSource") == "none"
    _open_folder(page, folder)
    page.wait_for_function("() => _veEl('veAudioSource').value === 'original'")        # גם הבורר שהמשתמש רואה
    page.evaluate("() => _veSaveProjectNow()")
    assert editor_projects.load_project(str(folder))["recipe"]["keep_audio"] is True


def test_the_tour_shows_once_and_a_screen_switch_closes_it(editor_page):
    # הסיור "1/4" נשאר מעל המסך הבא כשעוברים מסך בלי "דלג", ולא סומן כנראה - חזר בכל טעינה (16.10)
    page = editor_page
    page.evaluate("() => { localStorage.removeItem('uiTourSeen'); startUiTour(); }")
    page.wait_for_selector("#tourCard")
    assert page.evaluate("() => localStorage.getItem('uiTourSeen')") == "1"
    page.evaluate("() => switchTab('dataviz')")
    assert page.evaluate("() => !document.getElementById('tourCard') && !document.getElementById('tourSpot')")


def test_trim_fields_keep_their_width_in_clip_mode(editor_page, tmp_path):
    page = editor_page
    (tmp_path / "a.mp4").write_bytes(b"x")
    _open_folder(page, tmp_path)
    page.evaluate("() => { setVeMode('regular'); enterVeClipMode('a.mp4'); _veRevealElement(_veEl('veTrimStart')); }")
    page.wait_for_selector("#veClipBanner:not([hidden])")
    widths = page.evaluate("() => ['veTrimStart', 'veTrimDuration'].map(id => Math.round(_veEl(id).getBoundingClientRect().width))")
    assert min(widths) >= 60, widths                                    # קודם: 16px במצב קליפ ב-1440px
    assert page.evaluate("() => _veEl('veTrimStart').closest('.ve-row') !== _veEl('veTrimDuration').closest('.ve-row')")
