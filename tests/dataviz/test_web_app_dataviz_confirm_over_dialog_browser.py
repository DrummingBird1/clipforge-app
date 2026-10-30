# tests/dataviz/test_web_app_dataviz_confirm_over_dialog_browser.py
#
# 20.10.2026: חלון האישור (veConfirm) וחלון השאלה (vePrompt) של האפליקציה מעל <dialog> שנפתח ב-showModal. dialog כזה
# נמצא ב-top layer - מעל כל z-index - ושאר הדף inert, אז החלון נפתח מאחוריו ואי אפשר ללחוץ עליו. עכשיו הוא עובר לתוך
# ה-dialog העליון כל עוד הוא מוצג, וחוזר למקומו בסגירה; Escape סוגר רק אותו, לא את ה-dialog.
# 22.10.2026: אותו דבר לכל השאר - הודעה קופצת (uiToast), לוח הפקודות (Ctrl+K) וכל חלון .modal-bg של האפליקציה. חלון שעדיין
# פתוח כשה-dialog נסגר לפניו חוזר למקומו ונשאר גלוי (אחרת הוא "פתוח" בלי שרואים אותו, וקיצורי המקלדת חסומים).
# SHOT_DIR שומר צילומים של ההודעה ושל לוח הפקודות מעל ה-dialog.
# xdist-group: workspace
import os

import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "אישור"}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))


def _open_modal(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click("#dvzToolsBtn")   # 21.10.2026: ב"🧰 כלים"
    page.click("#dvzToolSettings")                                               # dialog אמיתי של המסך, ב-showModal
    page.wait_for_function("() => document.getElementById('dvzSettings').matches(':modal')")


def test_confirm_and_prompt_open_above_a_modal_dialog(editor_page, screen):
    page = editor_page
    _open_modal(page)
    page.evaluate("() => { window._answer = undefined; veConfirm('מעל החלון?').then(v => { window._answer = v; }); }")
    page.click("#veConfirmOkBtn", timeout=3000)                               # היום: חסום מאחורי ה-dialog
    page.wait_for_function("() => window._answer === true")
    page.wait_for_function("() => !document.getElementById('veConfirmModalBg').closest('dialog')", timeout=3000)   # חזר למקומו
    page.evaluate("() => { window._answer = undefined; vePrompt('שם?', {value: 'א'}).then(v => { window._answer = v; }); }")
    page.fill("#vePromptInput", "שלום", timeout=3000)
    page.click("#vePromptOkBtn", timeout=3000)
    page.wait_for_function("() => window._answer === 'שלום'")
    page.evaluate("() => { window._answer = undefined; veConfirm('Escape?').then(v => { window._answer = v; }); }")
    page.wait_for_selector("#veConfirmModalBg.show")
    page.keyboard.press("Escape")
    page.wait_for_function("() => window._answer === false")
    assert page.evaluate("() => document.getElementById('dvzSettings').open")  # Escape סגר רק את האישור


_LOOK = """(sel) => { const el = document.querySelector(sel), r = el.getBoundingClientRect(), s = getComputedStyle(el);
  return {box: [r.left, r.top, r.width, r.height].map(Math.round), position: s.position, z: s.zIndex, bg: s.backgroundColor}; }"""


def _shot(page, name):   # SHOT_DIR - צילומים לבדיקה בעין
    folder = os.environ.get("SHOT_DIR")
    if folder:
        os.makedirs(folder, exist_ok=True)
        page.screenshot(path=os.path.join(folder, name))


def _look(page, *selectors):
    """מקום, גודל, position, z-index ורקע - אחרי שאנימציות הכניסה (fade / slide) נגמרו."""
    page.wait_for_function("() => document.getAnimations().every(a => a.playState !== 'running' || a.effect.getComputedTiming().iterations === Infinity)")
    return [page.evaluate(_LOOK, sel) for sel in selectors]


def test_a_toast_shows_above_a_modal_dialog_and_stays_when_the_dialog_closes(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); uiToast('בלי חלון', 'ok', {timeout: 60000}); }")
    alone = _look(page, "#toastHost .toast:last-child")
    page.click("#toastHost .toast:last-child .toast-close")
    page.wait_for_function("() => !document.querySelector('#toastHost .toast')")
    _open_modal(page)
    page.evaluate("() => uiToast('בלי חלון', 'ok', {timeout: 60000})")
    assert _look(page, "#toastHost .toast:last-child") == alone   # אותו מקום, גודל ורקע גם בתוך ה-dialog
    _shot(page, "toast_over_dialog.png")
    page.click("#toastHost .toast:last-child .toast-close", timeout=3000)
    page.wait_for_function("() => !document.querySelector('#toastHost .toast')")
    page.evaluate("() => uiToast('מעל החלון?', 'ok', {timeout: 60000})")
    page.click("#toastHost .toast:last-child .toast-close", timeout=3000)      # היום: מאחורי ה-dialog
    page.wait_for_function("() => !document.querySelector('#toastHost .toast')")
    page.evaluate("() => uiToast('גם אחרי הסגירה', '', {timeout: 60000})")
    page.wait_for_function("() => document.getElementById('toastHost').closest('dialog')")
    page.evaluate("() => document.getElementById('dvzSettings').close()")
    # אירוע close של dialog נשלח אחרי close() (במשימה נפרדת) - מחכים לחזרה, לא בודקים מיד (נכשל לפעמים)
    page.wait_for_function("() => document.getElementById('toastHost').parentNode === document.body", timeout=3000)
    page.click("#toastHost .toast:last-child .toast-close", timeout=3000)


def test_the_command_palette_opens_above_a_modal_dialog(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); openCommandPalette(); }")
    page.wait_for_selector("#paletteModalBg.show")
    alone = _look(page, "#paletteModalBg", "#paletteModalBg > .modal")
    page.evaluate("() => closeCommandPalette()")
    _open_modal(page)
    page.keyboard.press("Control+k")
    page.wait_for_selector("#paletteModalBg.show")
    page.wait_for_function("() => document.getElementById('paletteModalBg').closest('dialog')")
    assert _look(page, "#paletteModalBg", "#paletteModalBg > .modal") == alone   # כל המסך, אותו רקע ושכבה
    _shot(page, "palette_over_dialog.png")
    page.click("#paletteInput", timeout=3000)                                     # היום: מאחורי ה-dialog
    page.keyboard.type("dataviz")
    assert page.input_value("#paletteInput") == "dataviz"
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('paletteModalBg').classList.contains('show')")
    assert page.evaluate("() => document.getElementById('dvzSettings').open")   # Escape סגר רק את הלוח
    page.wait_for_function("() => !document.getElementById('paletteModalBg').closest('dialog')", timeout=3000)   # חזר למקומו


def test_an_app_window_opened_over_a_modal_dialog_can_be_used_and_outlives_it(editor_page, screen):
    page = editor_page
    _open_modal(page)
    page.evaluate("() => openSettingsModal()")
    page.click("#settingsModalBg .modal-close", timeout=3000)                    # היום: מאחורי ה-dialog
    page.wait_for_function("() => !document.getElementById('settingsModalBg').classList.contains('show')")
    page.wait_for_function("() => !document.getElementById('settingsModalBg').closest('dialog')", timeout=3000)
    assert page.evaluate("() => document.getElementById('dvzSettings').open")
    page.evaluate("() => openSettingsModal()")
    page.wait_for_function("() => document.getElementById('settingsModalBg').closest('dialog')")
    page.evaluate("() => document.getElementById('dvzSettings').close()")       # ה-dialog נסגר לפני החלון
    # אירוע close נשלח אחרי close() (במשימה נפרדת) - מחכים שהחלון יחזור, לא בודקים מיד (נכשל תחת עומס)
    page.wait_for_function("() => !document.getElementById('settingsModalBg').closest('dialog')", timeout=3000)
    page.click("#settingsModalBg .modal-close")                                  # עדיין גלוי ולחיץ
    page.wait_for_function("() => !document.querySelector('.modal-bg.show')")
