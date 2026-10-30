# tests/web/test_web_app_wave22_browser.py
#
# גל 22 (יציבות ובטיחות) בדפדפן אמיתי: vePrompt במקום prompt() של הדפדפן, שמות
# לא-מהימנים (קבצים, פרופילים, שגיאות מהשרת) מוצגים כטקסט ולא כ-HTML, "רק הבקשה
# האחרונה קובעת" בציר-הזמן ובהערכה, veFlow (פרופיל גובר על פרויקט בכל סדר), ו-uiBus
# ו-uiPaletteProviders במקום עטיפות פונקציות.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

XSS_NAME = "a'); window.__xss=1; ('<img src=x onerror=\"window.__xss=2\">"


@pytest.fixture
def home_page(editor_server, edge_browser):
    context = edge_browser.new_context(viewport={"width": 1440, "height": 950}, locale="he-IL")
    context.add_init_script("try { if (localStorage.getItem('veFocus') === null) localStorage.setItem('veFocus', 'false'); } catch (e) {}")
    page = context.new_page()
    try:
        page.goto(f"{editor_server['base_url']}/?token={editor_server['web_app'].ACCESS_TOKEN}")
        page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)
    except Exception:
        context.close()
        raise
    yield page
    context.close()


def _fake_fetch(page, routes):
    """מחליף את fetch בדף לנתיבים מסוימים (הבקשות עוברות דרך ה-service worker, ש-page.route
    לא רואה). routes: [[חלק-מהכתובת, תשובה JSON, השהיה ב-ms], ...] - התאמה ראשונה מנצחת."""
    page.evaluate("""(routes) => {
        const realFetch = window.__realFetch || window.fetch;
        window.__realFetch = realFetch;
        window.__fakeRoutes = routes;
        window.fetch = (url, ...rest) => {
            const hit = window.__fakeRoutes.find(([part]) => String(url).includes(part));
            if (!hit) return realFetch(url, ...rest);
            const [, body, delay] = hit;
            return new Promise(resolve => setTimeout(() => resolve(new Response(JSON.stringify(body),
                {headers: {'Content-Type': 'application/json'}})), delay || 0));
        };
    }""", routes)


# --- vePrompt ---

def test_ve_prompt_returns_text_or_null_and_supports_password(home_page):
    page = home_page
    ask = "(opts) => { window.__answer = 'pending'; vePrompt('שם לבדיקה:', opts).then(v => { window.__answer = v; }); }"
    page.evaluate(ask, {"value": "abc"})
    page.wait_for_selector("#vePromptModalBg.show")
    assert page.input_value("#vePromptInput") == "abc"
    assert page.evaluate("() => document.activeElement.id") == "vePromptInput"
    assert "שם לבדיקה" in page.inner_text("#vePromptMessage")
    page.fill("#vePromptInput", "xyz")
    page.press("#vePromptInput", "Enter")
    page.wait_for_function("() => window.__answer === 'xyz'")
    assert not page.is_visible("#vePromptModalBg")
    page.evaluate(ask, {})
    page.wait_for_selector("#vePromptModalBg.show")
    page.keyboard.press("Escape")
    page.wait_for_function("() => window.__answer === null")
    page.evaluate(ask, {"type": "password"})
    page.wait_for_selector("#vePromptModalBg.show")
    assert page.get_attribute("#vePromptInput", "type") == "password"
    page.fill("#vePromptInput", "secret")
    page.click("#vePromptModalBg .modal-close")
    page.wait_for_function("() => window.__answer === null")
    assert page.input_value("#vePromptInput") == ""  # הסיסמה לא נשארת בשדה


# --- שמות לא-מהימנים כטקסט ---

def test_untrusted_names_render_as_text_not_html(home_page):
    page = home_page
    _fake_fetch(page, [
        ["/api/backup/list", [{"filename": XSS_NAME + ".enc", "size_bytes": 10}], 0],
        ["/api/credentials/rotation_status", [{"name": XSS_NAME, "configured": True, "age_days": 3, "stale": True}], 0],
        ["/api/credentials/check_validity", [{"name": XSS_NAME, "configured": True, "valid": False, "detail": "<img src=x onerror=\"window.__xss=3\">"}], 0],
    ])
    page.evaluate("async () => { await loadBackupList(); await loadCredentialRotationStatus(); await checkCredentialValidity(); }")
    for box in ("#backupList", "#credentialRotationList", "#credentialValidityResult"):
        assert page.locator(f"{box} img").count() == 0, box
        assert page.locator(f"{box} [onclick]").count() == 0, box
        assert "<img" in page.inner_text(box), box
    assert page.inner_text("#backupList .backup-name") == XSS_NAME + ".enc"
    # השחזור מקבל את השם המדויק כנתון (דרך handler), לא כקוד
    page.evaluate("() => document.querySelector('#backupList .backup-row button').click()")  # המודאל של ההגדרות סגור
    page.wait_for_selector("#veConfirmModalBg.show")
    assert XSS_NAME in page.inner_text("#veConfirmMessage")
    page.click("#veConfirmCancelBtn")
    # שמות פרופילים (גם מקישורי שיתוף) בדיאלוג ההשוואה
    page.evaluate("(name) => { state.videoEditorProfiles = {[name]: {}, 'B': {}}; return openCompareProfilesDialog(); }", XSS_NAME)
    assert page.evaluate("() => [...document.getElementById('compareProfileA').options].map(o => o.value)")[0] in (XSS_NAME, "B")
    assert page.locator("#compareProfileA img").count() == 0
    assert page.evaluate("() => window.__xss") is None


# --- רק הבקשה האחרונה קובעת ---

def test_a_slow_stale_response_never_overwrites_a_newer_one(editor_page):
    page = editor_page
    _fake_fetch(page, [
        ["timeline?count=16&path=C%3A%5Cfake%2Fa.mp4", {"url": "/stale-a.png", "duration": 10}, 700],
        ["timeline?count=16&path=C%3A%5Cfake%2Fb.mp4", {"url": "/fresh-b.png", "duration": 20}, 0],
        ["/api/waveform", {"error": "none"}, 0],
        ["/api/video_editor/estimate", {"files": [], "total_output_seconds": 0, "total_output_mb": 0}, 0],
    ])
    page.evaluate("""() => {
        state.folder = 'C:\\\\fake';
        const select = document.getElementById('vePreviewFile');
        select.replaceChildren(new Option('a.mp4', 'a.mp4'), new Option('b.mp4', 'b.mp4'));
        select.value = 'a.mp4'; loadVeTimeline();
        select.value = 'b.mp4'; loadVeTimeline();
    }""")
    page.wait_for_function("() => _veTimeline && _veTimeline.duration === 20")
    page.wait_for_timeout(1000)  # התשובה הישנה של a.mp4 חוזרת עכשיו - ולא מצוירת
    assert page.evaluate("() => [_veTimeline.duration, document.getElementById('veTimelineImg').getAttribute('src')]") == [20, "/fresh-b.png"]
    # הערכה: הבקשה הראשונה (איטית, קובץ אחד) לא דורסת את השנייה (שני קבצים)
    page.evaluate("""() => {
        let call = 0;
        const realFetch = window.fetch;
        window.fetch = (url, ...rest) => {
            if (!String(url).includes('/api/video_editor/estimate')) return realFetch(url, ...rest);
            call += 1;
            const rows = call === 1 ? [{file: 'old.mp4', source_seconds: 1, output_seconds: 1, output_mb: 1, exact: true}]
                : [{file: 'x.mp4', source_seconds: 1, output_seconds: 1, output_mb: 1, exact: true}, {file: 'y.mp4', source_seconds: 1, output_seconds: 1, output_mb: 1, exact: true}];
            const body = JSON.stringify({files: rows, total_output_seconds: 2, total_output_mb: 2});
            return new Promise(resolve => setTimeout(() => resolve(new Response(body, {headers: {'Content-Type': 'application/json'}})), call === 1 ? 700 : 0));
        };
        runVeEstimate(); runVeEstimate();
    }""")
    page.wait_for_function("() => document.querySelectorAll('#veEstimateBox tbody tr').length === 2")
    page.wait_for_timeout(1000)
    assert page.evaluate("() => [...document.querySelectorAll('#veEstimateBox tbody tr td:first-child')].map(td => td.textContent)") == ["x.mp4", "y.mp4"]


# --- veFlow / uiBus / ספקי Ctrl+K ---

def test_ve_flow_profile_queue_beats_project_in_any_order(home_page):
    result = home_page.evaluate("""() => {
        const out = {};
        veFlow.folderChanged();
        veFlow.requestQueueRestore([{name: 'p.mp4'}], 'profile');
        out.projectWhilePending = veFlow.requestQueueRestore([{name: 'j.mp4'}], 'project');
        out.taken = veFlow.takeQueueRestore().source;
        out.projectAfterApplied = veFlow.requestQueueRestore([{name: 'j.mp4'}], 'project');
        veFlow.folderChanged();
        out.projectInNewFolder = veFlow.requestQueueRestore([{name: 'j.mp4'}], 'project');
        out.profileOverridesProject = veFlow.requestQueueRestore([{name: 'p.mp4'}], 'profile') && veFlow.takeQueueRestore().source;
        const first = veFlow.beginQueueRefresh(), second = veFlow.beginQueueRefresh();
        out.latest = [veFlow.isLatestQueueRefresh(first), veFlow.isLatestQueueRefresh(second)];
        return out;
    }""")
    assert result == {"projectWhilePending": False, "taken": "profile", "projectAfterApplied": False,
                      "projectInNewFolder": True, "profileOverridesProject": "profile", "latest": [False, True]}


def test_events_and_palette_providers_replace_wrappers(home_page):
    page = home_page
    result = page.evaluate("""() => {
        const out = {};
        let seen = 'none';
        const off = uiBus.on('ve:folder-changed', folder => { seen = folder; });
        state.folder = 'C:\\\\somewhere';
        _onVeFolderChanged();
        off();
        out.folderEvent = seen;
        let second = false;
        uiBus.on('test:isolation', () => { throw new Error('boom'); });
        uiBus.on('test:isolation', () => { second = true; });
        uiBus.emit('test:isolation');
        out.handlerErrorIsolated = second;
        const entries = _vePaletteEntries();
        const index = label => entries.findIndex(e => e.label.includes(label));
        out.order = [index('מסך הבית'), index('צפיפות'), index('ערכת נושא: אוטומטי'), entries.findIndex(e => e.section === '🎮 סקריפטים')];
        return out;
    }""")
    assert result["folderEvent"] == "C:\\somewhere"
    assert result["handlerErrorIsolated"] is True
    home, density, theme, scripts = result["order"]
    assert -1 < home < density < theme < scripts
