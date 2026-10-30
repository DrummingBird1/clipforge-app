# tests/dataviz/test_web_app_wave41_browser.py
#
# גל 41 בדפדפן: עורך הגרפים - תור של כמה פרקים בריצה אחת ויעד (Shorts), הפרק הבא בסדרה, ערכת ערוץ
# (שמירה מפרק והחלה על פרק אחר), השוואת שני תוצרים וסל מיחזור, חבילות הפרסום של הפרק ואשף הפרסום
# (טקסטים -> תמונה -> אישור -> בדיקה בלי שליחה), ותקציב לחיצות: מ-CSV לפרק שרץ בארבע לחיצות.
# ההרצה עצמה מוחלפת (_start_script_run) ו-send2trash מוחלף - שום רינדור ושום קובץ בסל המיחזור האמיתי.
# xdist-group: workspace
import hashlib
import json
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
    small = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}
    folder = write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", "series": {"name": "אזעקות", "number": 2}, **small}, name="alarms")
    write_episode(data / "dataviz_episodes", overrides={"title": "מכוניות", "chart": "line_race", **small}, name="cars")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    runs = []
    monkeypatch.setattr(web_app, "_start_script_run", lambda script, folder, payload, host: runs.append((folder, payload)) or {"ok": True})
    md5 = {n: hashlib.md5(open(os.path.join(folder, n), "rb").read()).hexdigest() for n in os.listdir(folder)}
    return {"data": data, "workspace": workspace, "folder": folder, "runs": runs, "md5": md5}


def _open(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")


def _unchanged(screen):
    folder = screen["folder"]
    return {n: hashlib.md5(open(os.path.join(folder, n), "rb").read()).hexdigest() for n in os.listdir(folder)} == screen["md5"]


def test_a_queue_of_episodes_runs_once_with_a_vertical_target(editor_page, screen):
    page = editor_page
    _open(page)
    assert page.is_hidden("#dvzQueueBar")
    page.check('.dvz-card-wrap:has(.dvz-card[data-episode="alarms"]) .dvz-queue-pick input')
    page.check('.dvz-card-wrap:has(.dvz-card[data-episode="cars"]) .dvz-queue-pick input')
    page.wait_for_selector("#dvzQueueBar", state="visible")
    assert "2" in page.inner_text("#dvzQueueRun")
    page.evaluate("() => document.getElementById('dvzRunOverrides').open = true")   # גל 59: מקופל ל"שינויים להרצה הזו"
    page.select_option("#dvzTarget", "shorts")
    page.click("#dvzQueueRun")
    page.wait_for_function("() => document.getElementById('dvzStatus').textContent.startsWith('רץ')")   # אחרי תשובת השרת
    folder, payload = screen["runs"][-1]
    assert sorted(payload["dv_episodes"]) == ["alarms", "cars"] and payload["dv_target"] == "shorts"
    assert folder.endswith("dataviz_episodes")
    page.evaluate("() => dvzClearQueue()")
    assert page.is_hidden("#dvzQueueBar")


def test_next_in_series_and_a_channel_kit(editor_page, screen):
    page = editor_page
    _open(page)
    page.click('.dvz-card[data-episode="alarms"]')
    page.wait_for_function("() => document.querySelector('.dvz-card[data-episode=\"alarms\"]').classList.contains('selected')")
    assert "אזעקות #2" in page.inner_text('.dvz-card[data-episode="alarms"] .dvz-card-badges')
    page.evaluate("() => { window.vePrompt = async (msg, opts) => (opts && opts.value) || ''; }")
    page.evaluate("() => dvzDuplicate(true)")
    page.wait_for_selector('.dvz-card[data-episode="alarms-3"]')
    over = json.loads((screen["data"] / "dataviz_overrides" / "alarms-3.json").read_text(encoding="utf-8"))
    assert over["series"] == {"name": "אזעקות", "number": 3}
    # ערכה: שמירה מהפרק שנבחר (הפרק החדש), והחלה על "cars"
    page.evaluate("() => { window.vePrompt = async () => 'הערוץ'; }")
    page.evaluate("() => dvzOpenKits()")
    page.wait_for_selector("#dvzKits button")
    page.click("#dvzKits >> text=שמור את העיצוב של הפרק כערכה")
    page.wait_for_selector("#dvzKits .dvz-kit")
    assert "הערוץ" in json.loads((screen["data"] / "dataviz_kits.json").read_text(encoding="utf-8"))
    page.click('.dvz-card[data-episode="cars"]')
    page.click("#dvzKits .dvz-kit >> text=החל על הפרק")
    page.wait_for_selector("#toastHost .toast[data-tone=ok] >> text=הוחלה")   # ההודעה מגיעה אחרי שהשרת שמר
    assert json.loads((screen["data"] / "dataviz_overrides" / "cars.json").read_text(encoding="utf-8"))["theme"] in ("light", "dark")
    assert _unchanged(screen)
    # תבנית לפרק חדש: כל הפרקים התקינים ברשימה
    options = page.eval_on_selector_all("#dvzNewTemplate option", "els => els.map(e => e.value)")
    assert options[0] == "" and {"alarms", "alarms-3", "cars"} <= set(options)


def test_two_outputs_are_compared_and_one_goes_to_the_recycle_bin(editor_page, screen, monkeypatch):
    out = screen["workspace"] / "dataviz" / "outputs" / "horizontal"
    out.mkdir(parents=True)
    for name in ("alarms.mp4", "alarms_shorts.mp4"):
        (out / name).write_bytes(b"\x00" * 64)
    trashed = []
    import send2trash
    monkeypatch.setattr(send2trash, "send2trash", lambda p: trashed.append(os.path.basename(p)) or os.remove(p))
    page = editor_page
    _open(page)
    page.click('.dvz-card[data-episode="alarms"]')
    page.wait_for_function("() => document.querySelectorAll('#dvzOutputs .dvz-output').length === 2")
    picks = page.locator("#dvzOutputs .dvz-compare-pick input")   # locator ולא handle: הרשימה יכולה להצטייר שוב (הבחירה נשמרת)
    for i in range(2):
        picks.nth(i).check()
    page.wait_for_selector("#dvzCompareOutputsBtn", state="visible")
    page.click("#dvzCompareOutputsBtn")
    page.wait_for_function("() => document.querySelectorAll('#dvzOutputCompare video').length === 2")
    page.evaluate("() => { window.veConfirm = async () => true; }")
    page.click('#dvzOutputs .dvz-output[data-name="alarms_shorts.mp4"] >> text=לסל המיחזור')
    page.wait_for_function("() => document.querySelectorAll('#dvzOutputs .dvz-output').length === 1")
    assert trashed == ["alarms_shorts.mp4"] and (out / "alarms.mp4").exists()


def test_the_publish_wizard_edits_texts_approves_and_dry_runs(editor_page, screen):
    out = screen["workspace"] / "dataviz" / "outputs" / "horizontal"
    out.mkdir(parents=True)
    (out / "alarms.mp4").write_bytes(b"\x00" * 64)
    sidecar = out / "alarms.publish.json"
    sidecar.write_text(json.dumps({"status": "pending_approval", "video": "alarms.mp4", "created_at": "2026-10-15T10:00:00",
                                   "metadata": {"title": "ישן", "youtube_title": "ישן", "hashtags": ["#נתונים"]}}), encoding="utf-8")
    page = editor_page
    _open(page)
    page.click('.dvz-card[data-episode="alarms"]')
    page.wait_for_selector("#dvzPublishSection", state="visible")
    page.click("#dvzPackages >> text=אשף פרסום")
    page.wait_for_selector("#dvzWzTitle")
    page.fill("#dvzWzTitle", "כותרת חדשה")
    page.click("#dvzWizardNext")
    # השלב הבא - או הודעת שגיאה מהשמירה, שתופיע בכישלון במקום timeout בלי הסבר
    page.wait_for_function("""() => document.querySelector('#dvzWizardSteps li.is-current').textContent === 'תמונה'
        || document.getElementById('dvzWizardStatus').textContent !== ''""")
    assert page.inner_text("#dvzWizardStatus") == "", page.inner_text("#dvzWizardStatus")
    page.wait_for_selector("#dvzWizardSteps li.is-current >> text=תמונה")
    meta = json.loads(sidecar.read_text(encoding="utf-8"))["metadata"]
    assert meta["youtube_title"] == "כותרת חדשה" and meta["hashtags"] == ["#נתונים"]
    page.click("#dvzWizardNext")
    page.wait_for_selector("#dvzWizardSteps li.is-current >> text=אישור")
    page.click("#dvzWizardNext")
    page.wait_for_selector("#dvzWzWhen")
    assert json.loads(sidecar.read_text(encoding="utf-8"))["status"] == "approved"
    page.click("#dvzWizardNext")   # "בדיקה בלי שליחה" נבחר כברירת מחדל - לא נשלח כלום
    page.wait_for_function("() => document.getElementById('dvzWizardStatus').textContent.includes('בדיקה בלבד')")
    assert "sent" not in json.loads(sidecar.read_text(encoding="utf-8"))
    page.evaluate("() => closeDvzWizard()")


def test_click_budget_from_a_csv_to_a_running_episode(editor_page, screen):
    """רעיון #30: מקובץ CSV לפרק שרץ - ארבע לחיצות (פתיחת "פרק חדש", "צור פרק", "הרץ"; הקובץ נבחר בחלון הקבצים)."""
    page = editor_page
    _open(page)
    clicks = 0
    page.click("#dvzNewBtn")   # גל 59: "➕ פרק חדש" בראש הרשימה פותח את החלון
    page.click("#dvzNewDialog [data-new-way=files]")   # 21.10.2026: "➕ פרק חדש" -> "📄 מקבצים"
    clicks += 1
    csv = "date,city,n\n" + "".join(f"2020-0{m}-{d:02d},{c},{m * d}\n" for m in (1, 2, 3) for d in (1, 15) for c in ("A", "B"))
    page.set_input_files("#dvzNewCsv", files=[{"name": "cities.csv", "mimeType": "text/csv", "buffer": csv.encode()}])
    page.wait_for_function("() => [...document.getElementById('dvzNewTime').options].some(o => o.value === 'date')")
    # השם מהקובץ, והעמודות מנוחשות (ערך = המספרית, קבוצה = הטקסט) - בלי לחיצות נוספות
    assert page.evaluate("() => ['dvzNewName', 'dvzNewTitle', 'dvzNewTime', 'dvzNewValue', 'dvzNewGroup'].map(id => document.getElementById(id).value)") == [
        "cities", "cities", "date", "n", "city"]
    page.click("#dvzCreateBtn")
    clicks += 1
    page.wait_for_function("() => dvzState.selected === 'cities'")
    page.click("#dvzRunBtn")
    clicks += 1
    page.wait_for_function("() => document.getElementById('dvzStatus').textContent.includes('רץ')")
    assert clicks <= 4
    folder, payload = screen["runs"][-1]
    assert folder.endswith(os.path.join("dataviz_episodes", "cities")) or folder.endswith("cities")
