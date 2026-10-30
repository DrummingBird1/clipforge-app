# tests/dataviz/test_web_app_dataviz_trash_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): "🗑️ מחק פרק" מתפריט ⋯ (ומהכפתור בכרטיס) - אישור ב-veConfirm עם שם הפרק ומה זז,
# הפרק עובר לסל (data/dataviz_trash) ויוצא מהרשימה; "♻️ שנמחקו" מחזיר אותו; ביטול באישור - שום דבר לא זז;
# "רוקן סל" רק אחרי שני אישורים.
# xdist-group: workspace
import os

import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", **VIDEO}, name="alarms")
    write_episode(data / "dataviz_episodes", overrides={"title": "פרק למחיקה", **VIDEO}, name="doomed")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    monkeypatch.setattr(web_app.worker, "is_running", False)
    return {"data": data}


def _confirm(page, ok):
    page.wait_for_selector("#veConfirmModalBg.show")
    page.click("#veConfirmOkBtn" if ok else "#veConfirmCancelBtn")


def test_delete_from_the_menu_then_restore_from_deleted(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector('.dvz-card[data-episode="doomed"]')
    page.click('.dvz-card[data-episode="doomed"]')
    page.wait_for_function("() => dvzState.selected === 'doomed'")
    # ביטול - שום דבר לא זז
    page.click("#dvzEpisodeMenuBtn")
    page.click("#dvzDeleteMenuBtn")
    page.wait_for_selector("#veConfirmModalBg.show")
    message = page.inner_text("#veConfirmMessage")
    assert "פרק למחיקה" in message and "doomed" in message and "dataviz_trash" in message and "dataviz_overrides" in message
    page.click("#veConfirmCancelBtn")
    assert (screen["data"] / "dataviz_episodes" / "doomed").is_dir()
    # מחיקה
    page.click("#dvzEpisodeMenuBtn")
    page.click("#dvzDeleteMenuBtn")
    _confirm(page, True)
    page.wait_for_selector('.dvz-card[data-episode="doomed"]', state="detached")
    assert not (screen["data"] / "dataviz_episodes" / "doomed").exists()
    trashed = os.listdir(screen["data"] / "dataviz_trash")
    assert len(trashed) == 1 and trashed[0].startswith("doomed_")
    # שחזור
    page.click("#dvzToolsBtn")   # 21.10.2026: ב"🧰 כלים"
    page.click("#dvzToolTrash")
    page.wait_for_selector(f'#dvzTrashList .dvz-trash-row[data-trash-id="{trashed[0]}"]')
    assert "פרק למחיקה" in page.inner_text("#dvzTrashList")
    page.click(f'#dvzTrashList .dvz-trash-row[data-trash-id="{trashed[0]}"] >> text=♻️ שחזר')
    page.wait_for_selector('.dvz-card[data-episode="doomed"]')
    page.wait_for_function("() => document.getElementById('dvzTrashList').textContent.includes('הסל ריק')")
    assert (screen["data"] / "dataviz_episodes" / "doomed" / "config.yaml").is_file()


def test_the_card_button_deletes_and_emptying_needs_two_confirmations(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector('.dvz-card[data-episode="doomed"]')
    page.hover('.dvz-card[data-episode="doomed"]')
    page.click('.dvz-card-tools [data-delete-for="doomed"]')
    _confirm(page, True)
    page.wait_for_selector('.dvz-card[data-episode="doomed"]', state="detached")
    page.click("#dvzToolsBtn")   # 21.10.2026: ב"🧰 כלים"
    page.click("#dvzToolTrash")
    page.wait_for_selector("#dvzTrashList .dvz-trash-row")
    page.click("#dvzTrashEmptyBtn")
    _confirm(page, True)
    _confirm(page, False)                                                   # האישור השני בוטל - הסל נשאר
    page.wait_for_function("() => document.getElementById('dvzTrashDialog').open")
    assert len(os.listdir(screen["data"] / "dataviz_trash")) == 1
    page.click("#dvzTrashEmptyBtn")
    _confirm(page, True)
    _confirm(page, True)
    page.wait_for_function("() => document.getElementById('dvzTrashList').textContent.includes('הסל ריק')")
    assert os.listdir(screen["data"] / "dataviz_trash") == []
    assert (screen["data"] / "dataviz_episodes" / "alarms").is_dir()
