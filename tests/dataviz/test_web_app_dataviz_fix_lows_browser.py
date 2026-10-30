# tests/dataviz/test_web_app_dataviz_fix_lows_browser.py
#
# 23.10.2026, סריקת הבאגים - מנה 7 (הנמוכים שנשארו). המספרים לפי הדוח (dataviz-bug-hunt-2026-10-23.md):
# נ10 אותה חבילה בשני מסכים - הכפתורים של הכרטיס הלא נכון ננעלו; נ15 שונות: הסמן על הסליידר קפץ בריחוף ב-LTR, הקלטה
# המשיכה אחרי מעבר פרק ונשמרה לפרק שנבחר, חיפוש בקטלוג בלי "רק האחרון", שדות כתובת ועמודה בלי dir="ltr", ולוח הצפיות
# נתקע על "⏳" כשאין רשת.
# xdist-group: workspace
import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    for name in ("alpha", "beta"):
        write_episode(data / "dataviz_episodes", overrides={"title": name}, name=name)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    return data


def _open(page):
    page.evaluate("() => { localStorage.setItem('dvzMode', 'regular'); closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector("#dvzEpisodes .dvz-card")
    page.wait_for_function("() => dvzState.selected === 'alpha'")


# בקשות שיוצאות דרך ה-service worker לא עוברות ב-page.route - תשובה מזויפת בתוך הדף. replies: חלק מהכתובת -> קוד JS
# שמחזיר Promise של Response (או "hang" - בקשה שלא חוזרת)
def _stub(page, script):
    page.evaluate("(script) => { const real = window.fetch; window.__calls = []; const route = eval(script);"
                  " window.fetch = (url, options) => { const hit = route(String(url), options);"
                  " if (hit === undefined) return real(url, options); window.__calls.push([String(url), options && options.body]); return hit; }; }", script)


# ---------- נ10 ----------
def test_a_decision_locks_the_buttons_of_the_clicked_card(editor_page, screen):
    page = editor_page
    _open(page)
    _stub(page, "(url) => url.includes('/decide') ? new Promise(() => {}) : undefined")   # הבקשה לא חוזרת - הכפתורים נשארים נעולים
    page.evaluate("""() => {
        const pkg = {id: "horizontal/race", orientation: "horizontal", name: "race", status: "pending_approval", video: "race.mp4",
                     created_at: "", video_exists: true};
        for (const id of ["boxA", "boxB"]) { const box = document.createElement("div"); box.id = id; box.append(_datavizCard(pkg)); document.body.append(box); }
    }""")
    page.evaluate("() => document.querySelector('#boxB .approval-approve-btn').click()")
    page.wait_for_function("() => window.__calls.length === 1")
    states = page.evaluate("() => ['boxA', 'boxB'].map(id => [...document.querySelectorAll(`#${id} button`)].every(b => b.disabled))")
    assert states == [False, True]                                              # קודם: [True, False] - הכרטיס הראשון בדף ננעל


# ---------- נ15: הסמן על הסליידר ----------
def test_a_slider_marker_stays_in_place_on_hover_in_ltr(editor_page, screen):
    page = editor_page
    _open(page)
    page.evaluate("""() => {
        const wrap = document.createElement("div"); wrap.dir = "ltr"; wrap.style.cssText = "position:fixed;top:200px;left:200px;width:300px;z-index:99999";
        wrap.innerHTML = '<div class="dvz-markers"><button type="button" class="dvz-marker" id="probeMarker" style="inset-inline-start:50%">●</button></div>';
        document.body.append(wrap);
    }""")
    matrix = "() => { const m = new DOMMatrix(getComputedStyle(document.getElementById('probeMarker')).transform); return [m.a, m.e]; }"
    before = page.evaluate(matrix)
    page.hover("#probeMarker")
    # מחכים לסוף המעבר (transition): הסמן מוגדל ובאותו צד. קודם: בריחוף translateX(50%) - הסמן קפץ מתחת לעכבר, איבד את
    # הריחוף וחזר (מהבהב), ובאמצע המעבר ההגדלה מגיעה רק כשהוא כבר בצד השני - התנאי לא מתקיים אף פעם
    page.wait_for_function("() => { const m = new DOMMatrix(getComputedStyle(document.getElementById('probeMarker')).transform);"
                           " return m.a > 1.3 && m.e < 0; }", timeout=3000)
    assert before[1] < 0 and before[0] == 1


# ---------- נ15: הקלטה ----------
def test_switching_episode_stops_the_recording_and_keeps_it_for_its_episode(editor_page, screen):
    page = editor_page
    _open(page)
    _stub(page, "(url) => url.includes('/api/dataviz/episodes/recordings') ? Promise.resolve(new Response('{\"ok\": true}', {status: 200})) : undefined")
    page.evaluate("""() => {
        navigator.mediaDevices.getUserMedia = async () => ({getTracks: () => [{stop() {}}]});
        window.MediaRecorder = class {
            constructor() { this.state = "inactive"; this.mimeType = "audio/webm"; }
            start() { this.state = "recording"; }
            stop() { this.state = "inactive"; this.ondataavailable({data: new Blob(["x"])}); this.onstop(); }
        };
        window.__btn = document.createElement("button");
        return _dvzToggleRecording("2023-10-07", window.__btn, () => {});
    }""")
    assert page.evaluate("() => dvzRecorder.state") == "recording"
    page.evaluate("() => { dvzState.selected = 'beta'; }")                      # מעבר לפרק אחר
    page.wait_for_function("() => window.__calls.length === 1", timeout=5000)   # קודם: ההקלטה ממשיכה, ושום דבר לא נשמר
    body = page.evaluate("() => JSON.parse(window.__calls[0][1])")
    assert body["episode"] == "alpha" and page.evaluate("() => dvzRecorder.state") == "inactive"


# ---------- נ15: חיפוש בקטלוג ----------
def test_a_late_answer_of_an_older_catalog_search_does_not_win(editor_page, screen):
    page = editor_page
    _open(page)
    _stub(page, """(url, options) => {
        if (!url.includes('/api/dataviz/catalog?')) return undefined;
        const q = new URL(url, location.href).searchParams.get('q');
        const reply = () => new Response(JSON.stringify({items: [{id: 'item_' + q, title: q, provider_name: 'p', units: ''}]}), {status: 200});
        if (q !== 'old') return Promise.resolve(reply());
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => resolve(reply()), 600);           // התשובה הישנה מגיעה אחרונה
            if (options && options.signal) options.signal.addEventListener('abort', () => { clearTimeout(timer); reject(new DOMException('aborted', 'AbortError')); });
        });
    }""")
    page.evaluate("""async () => {
        const box = document.getElementById("dvzCatalogSearch");
        box.value = "old"; const first = dvzCatalogSearch();
        box.value = "new"; await dvzCatalogSearch();
        await first.catch(() => {});                                          // החיפוש הישן הסתיים (נעצר, או צייר - קודם)
    }""")
    assert page.evaluate("() => [...document.querySelectorAll('#dvzCatalogList [data-catalog-id]')].map(r => r.dataset.catalogId)") == ["item_new"]   # קודם: item_old


# ---------- נ15: שדות כתובת ועמודה ----------
def test_the_url_and_column_fields_are_left_to_right(editor_page, screen):
    page = editor_page
    _open(page)
    dirs = page.evaluate("""async () => {
        const view = await _dvzRemoteView();
        return Object.fromEntries([...view.querySelectorAll('input[data-field]')].map(i => [i.dataset.field, i.dir]));
    }""")
    assert dirs == {"url": "ltr", "time_column": "ltr", "value_column": "ltr", "entity_column": "ltr", "legend": ""}   # קודם: בלי dir


# ---------- נ15: לוח הצפיות ----------
def test_the_views_board_shows_an_error_without_network(editor_page, screen):
    page = editor_page
    _open(page)
    _stub(page, "(url) => url.includes('/api/dataviz/series_board') ? Promise.reject(new TypeError('Failed to fetch')) : undefined")
    page.evaluate("() => dvzOpenBoard().catch(() => {})")
    page.wait_for_selector("#dvzBoard .empty-msg.bad", timeout=5000)            # קודם: נשאר "⏳"
    assert "Failed to fetch" in page.inner_text("#dvzBoard")
