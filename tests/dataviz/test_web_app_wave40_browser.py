# tests/dataviz/test_web_app_wave40_browser.py
#
# גל 40 בדפדפן: חלון "נתונים ובדיקות" של עורך הגרפים - מקורות עם 20 שורות, בדיקה (וסימון ליד "הרץ"),
# מצטבר, גרף קצב עם אירועים ושיאים, פיזור, עדכון נתונים עם השוואת סכומים (קובץ חדש בלבד), גרירת קובץ
# Excel/JSON לפרק חדש, ומוזיקה על גרף גלי קול. בלי ffmpeg (WAV נקרא ישירות).
# xdist-group: workspace
import base64
import hashlib
import io
import json
import os
import struct
import wave


import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    folder = write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", "video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}, name="alarms")
    with wave.open(os.path.join(folder, "song.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"".join(struct.pack("<h", (i * 37) % 20000) for i in range(16000)))
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    return {"data": data, "folder": folder, "md5": {n: hashlib.md5(open(os.path.join(folder, n), "rb").read()).hexdigest() for n in os.listdir(folder)}}


def _open(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")


def _data_tab(page, tab):
    page.evaluate("(t) => { dvzData.tab = t; const d = document.getElementById('dvzData'); d.open = true; dvzLoadData(); }", tab)


def test_sources_check_badge_cumulative_and_pacing(editor_page, screen):
    page = editor_page
    _open(page)
    page.wait_for_function("() => !document.getElementById('dvzDataBadge').hidden")   # שורות שנזרקו / ימים ריקים
    _data_tab(page, "sources")
    page.wait_for_selector("#dvzDataBody .dvz-source")
    assert page.evaluate("() => document.querySelectorAll('#dvzDataBody .dvz-source').length") == 2
    assert page.evaluate("() => document.querySelectorAll('#dvzDataBody .dvz-source:last-child tbody tr').length") == 20
    page.click("#dvzDataBadge")   # 21.10.2026: הבדיקה ברשימה "✅ לפני רינדור"
    page.wait_for_selector("#dvzPreData .dvz-finding.is-warn")
    page.click("#dvzPrerender >> text=✕ סגור")
    _data_tab(page, "cumulative")
    page.wait_for_selector("#dvzDataBody .dvz-data-table tbody tr")
    _data_tab(page, "pacing")
    page.wait_for_selector("#dvzDataBody svg.dvz-chart polyline")
    assert page.evaluate("() => document.querySelectorAll('#dvzDataBody .dvz-chart-mark.is-event').length") >= 1
    _data_tab(page, "spread")
    page.wait_for_selector("#dvzDataBody svg.dvz-chart polyline", state="attached")   # פיזור שווה = קו ישר (גובה 0 - "מוסתר" בעיני Playwright)


def test_update_data_shows_the_totals_then_saves_a_new_file(editor_page, screen):
    page = editor_page
    _open(page)
    _data_tab(page, "update")
    page.wait_for_selector("#dvzUpdateFile")
    csv = "time,origin\n" + "".join(f"2021-0{m}-01 10:00:00,South\n" for m in range(1, 10))
    page.select_option("#dvzUpdateSource", "1")   # המקור היומי (alarms.csv) - הראשון הוא הסיכום השנתי
    page.set_input_files("#dvzUpdateFile", files=[{"name": "new.csv", "mimeType": "text/csv", "buffer": csv.encode()}])
    page.wait_for_selector("#dvzUpdateApply")
    assert page.evaluate("() => document.querySelectorAll('#dvzDataBody .dvz-compare-table tbody tr').length") >= 1
    assert not (screen["data"] / "dataviz_overrides" / "alarms.json").exists()
    page.click("#dvzUpdateApply")
    page.wait_for_function("() => document.getElementById('dvzDataBody').textContent.includes('הוחלפו')")
    assert (screen["data"] / "dataviz_overrides" / "alarms.json").exists()
    assert {n: hashlib.md5(open(os.path.join(screen["folder"], n), "rb").read()).hexdigest() for n in os.listdir(screen["folder"])} == screen["md5"]


def test_add_a_data_file_as_a_new_source_shows_the_totals_then_saves(editor_page, screen):
    # 18.10.2026: "➕ קובץ נתונים נוסף" - מקור שלישי לצד שני המקורות של הפרק, תיקיית הפרק לא משתנה
    page = editor_page
    _open(page)
    _data_tab(page, "update")
    page.wait_for_selector("#dvzAddSourceFile")
    csv = "year,region,total\n2019,C,365\n2020,C,366\n"
    page.set_input_files("#dvzAddSourceFile", files=[{"name": "regions.csv", "mimeType": "text/csv", "buffer": csv.encode()}])
    page.wait_for_selector("#dvzAddSourceCheck")
    field = "#dvzDataBody .dvz-source-mapping [data-field='%s']"
    assert page.input_value(field % "time_column") == "year" and page.input_value(field % "period") == "year"   # כמו המקור הראשון
    page.select_option(field % "group_column", "region")
    page.click("#dvzAddSourceCheck")
    page.wait_for_selector("#dvzAddSourceApply")
    assert "C" in page.locator("#dvzDataBody .dvz-compare-table").inner_text()
    assert not (screen["data"] / "dataviz_overrides" / "alarms.json").exists()
    page.click("#dvzAddSourceApply")
    page.wait_for_function("() => document.getElementById('dvzDataBody').textContent.includes('נוסף כמקור 3')")
    _data_tab(page, "sources")
    page.wait_for_function("() => document.querySelectorAll('#dvzDataBody .dvz-source').length === 3")
    assert {n: hashlib.md5(open(os.path.join(screen["folder"], n), "rb").read()).hexdigest() for n in os.listdir(screen["folder"])} == screen["md5"]


def test_an_added_source_can_be_removed_after_confirming_and_its_file_stays_on_disk(editor_page, screen, monkeypatch):
    # 18.10.2026: כפתור "🗑️ הסר" רק במקור שנוסף מהדפדפן, עם חלון אישור; המקור יוצא מה-override והקובץ נשאר בדיסק בלי שינוי
    import send2trash
    from utils import dataviz_data as dd
    trashed = []
    monkeypatch.setattr(send2trash, "send2trash", lambda p: (trashed.append(os.path.basename(p)), os.remove(p)))   # safe: קובץ זמני
    saved = dd.add_source(str(screen["data"]), "alarms", "regions.csv", "year,region,total\n2019,C,365\n2020,C,366\n",
                          {"time_column": "year", "period": "year", "value_column": "total", "group_column": "region"}, confirm=True)
    added = screen["data"] / "dataviz_overrides" / "alarms" / saved["file"]
    content = added.read_bytes()
    page = editor_page
    _open(page)
    _data_tab(page, "sources")
    page.wait_for_function("() => document.querySelectorAll('#dvzDataBody .dvz-source').length === 3")
    assert page.evaluate("() => [...document.querySelectorAll('#dvzDataBody .dvz-source')].map(c => !!c.querySelector('.dvz-remove-source'))") == [False, False, True]
    page.click("#dvzDataBody .dvz-remove-source")
    page.wait_for_selector("#veConfirmModalBg.show")
    page.click("#veConfirmCancelBtn")   # ביטול - שום דבר לא השתנה
    assert len(json.loads((screen["data"] / "dataviz_overrides" / "alarms.json").read_text(encoding="utf-8"))["sources"]) == 3
    page.click("#dvzDataBody .dvz-remove-source")
    page.wait_for_selector("#veConfirmModalBg.show")
    page.click("#veConfirmOkBtn")
    page.wait_for_function("() => document.querySelectorAll('#dvzDataBody .dvz-source').length === 2")
    assert not trashed and added.read_bytes() == content
    assert len(json.loads((screen["data"] / "dataviz_overrides" / "alarms.json").read_text(encoding="utf-8"))["sources"]) == 2
    assert {n: hashlib.md5(open(os.path.join(screen["folder"], n), "rb").read()).hexdigest() for n in os.listdir(screen["folder"])} == screen["md5"]


def test_the_browser_accepts_a_file_over_5mb_and_rejects_one_over_25mb(editor_page, screen):
    # 18.10.2026: המגבלה בדפדפן כמו בשרת - 25MB לקובץ
    page = editor_page
    _open(page)
    result = page.evaluate("""async () => {
        const make = (mb) => new File([new Uint8Array(mb * 1024 * 1024).fill(97)], 'big.csv', {type: 'text/csv'});
        const ok = (await _dvzFileAsCsv(make(6))).length;
        let error = '';
        try { await _dvzFileAsCsv(make(26)); } catch (e) { error = e.message; }
        return {ok, error};
    }""")
    assert result["ok"] == 6 * 1024 * 1024 and "25MB" in result["error"]


def test_a_weights_file_is_added_to_a_yearly_source_and_can_be_removed(editor_page, screen):
    # 18.10.2026: "⚖️ קובץ משקלות" - קובץ חדש תחת dataviz_overrides, המקור מפנה אליו; הסרה רק מה-override, הקובץ נשאר
    page = editor_page
    _open(page)
    _data_tab(page, "update")
    page.wait_for_selector("#dvzWeightsFile")
    assert page.evaluate("() => [...document.querySelectorAll('#dvzWeightsSource option')].map(o => o.value)") == ["0"]   # רק המקור השנתי
    csv = "year,month,total\n2019,1,1\n2019,7,3\n"
    page.set_input_files("#dvzWeightsFile", files=[{"name": "weights.csv", "mimeType": "text/csv", "buffer": csv.encode()}])
    page.wait_for_selector("#dvzWeightsApply")
    field = "#dvzDataBody .dvz-weights-mapping [data-field='%s']"
    assert [page.input_value(field % f) for f in ("period_column", "month_column", "value")] == ["year", "month", "total"]
    page.click("#dvzWeightsApply")
    page.wait_for_function("() => document.getElementById('dvzDataBody').textContent.includes('קובץ המשקלות נוסף')")
    overrides = json.loads((screen["data"] / "dataviz_overrides" / "alarms.json").read_text(encoding="utf-8"))
    weights = overrides["sources"][0]["spread"]["weights"]
    added = screen["data"] / "dataviz_overrides" / "alarms" / os.path.basename(weights["path"])
    assert added.read_bytes() == csv.encode() and weights["value"] == "total"
    _data_tab(page, "sources")
    page.wait_for_selector("#dvzDataBody .dvz-remove-weights")
    assert page.evaluate("() => [...document.querySelectorAll('#dvzDataBody .dvz-source')].map(c => !!c.querySelector('.dvz-remove-weights'))") == [True, False]
    page.click("#dvzDataBody .dvz-remove-weights")
    page.wait_for_selector("#veConfirmModalBg.show")
    page.click("#veConfirmOkBtn")
    page.wait_for_function("() => !document.querySelector('#dvzDataBody .dvz-remove-weights') && document.querySelector('#dvzDataBody .dvz-source')")
    overrides = json.loads((screen["data"] / "dataviz_overrides" / "alarms.json").read_text(encoding="utf-8"))
    assert overrides["sources"][0]["spread"]["weights"] == {"path": "monthly.csv"} and added.read_bytes() == csv.encode()
    assert {n: hashlib.md5(open(os.path.join(screen["folder"], n), "rb").read()).hexdigest() for n in os.listdir(screen["folder"])} == screen["md5"]


def test_an_excel_file_dropped_on_the_screen_fills_the_new_episode_form(editor_page, screen):
    page = editor_page
    _open(page)
    import pandas as pd
    buf = io.BytesIO()
    pd.DataFrame({"date": ["2020-01-01", "2020-01-02"], "city": ["A", "B"], "n": [1, 2]}).to_excel(buf, index=False)
    data = base64.b64encode(buf.getvalue()).decode()
    page.evaluate("""(b64) => {
        const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
        const file = new File([bytes], 'ערים.xlsx', {type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
        const dt = new DataTransfer(); dt.items.add(file);
        const panel = document.querySelector('[data-tab-panel="dataviz"]');
        panel.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));
    }""", data)
    page.wait_for_function("() => [...document.getElementById('dvzNewTime').options].map(o => o.value).includes('date')")
    assert page.evaluate("() => document.getElementById('dvzNewDialog').open")   # גל 59: הטופס בחלון
    assert [o for o in page.eval_on_selector_all("#dvzNewGroup option", "els => els.map(e => e.value)") if o] == ["date", "city", "n"]


def test_music_is_picked_on_the_waveform(editor_page, screen):
    page = editor_page
    _open(page)
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; }")
    page.wait_for_selector("#dvzEditorBody .dvz-group")
    page.click("#dvzEditorTabs button[data-tab=music]")
    page.wait_for_selector("#dvzMusicFile")
    page.select_option("#dvzMusicFile", "song.wav")
    page.wait_for_selector("#dvzEditorBody .dvz-wave svg")
    page.evaluate("""() => { const svg = document.querySelector('#dvzEditorBody .dvz-wave svg'); const r = svg.getBoundingClientRect();
        svg.dispatchEvent(new MouseEvent('click', {clientX: r.left + r.width / 2, clientY: r.top + 5, bubbles: true})); }""")
    assert page.evaluate("() => dvzEd.draft['audio.path']") == "song.wav"
    assert abs(page.evaluate("() => dvzEd.draft['audio.start']") - 1.0) < 0.15
