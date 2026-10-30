# tests/web/test_web_app_visual_screens_browser.py
#
# גל 23: רגרסיה ויזואלית למסכים האמיתיים (לא רק /styleguide) - בית, עבודות, סטטיסטיקות
# וסטודיו, בערכה הכהה ובבהירה. הנתונים קבועים: fetch עטוף בדף מחזיר פרויקטים/ריצות/
# היסטוריה/חומרה מזויפים (השרת של ה-session משותף לקבצי טסט אחרים, שמוסיפים לו פרויקטים
# ופרופילים, ומועדפים/"הורצו לאחרונה" נקראים מהמכונה), והזמנים יחסיים ל"עכשיו" כך
# ש"לפני שעה" נשאר "לפני שעה".
#
# ההשוואה: צילום מוקטן לאפור (200x132) ומדד הפרש ממוצע מול baseline - גס מספיק כדי
# שהבדלי רינדור גופנים בין מכונות לא יפילו, רגיש מספיק לפריסה שבורה, צבע שגוי או
# פאנל שנעלם. CLIPFORGE_UPDATE_VISUAL_BASELINES=1 כותב baseline חדש אחרי שינוי מכוון.
# בכשל נשמרים הצילום המלא וההשוואה תחת .cache/visual_failures/ (ה-CI מעלה אותם).
import json
from tests import PROJECT_ROOT
import os


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

ROOT = PROJECT_ROOT
BASELINE_DIR = os.path.join(ROOT, "tests", "visual_baselines")
FAILURE_DIR = os.path.join(ROOT, ".cache", "visual_failures")
SIZE = (200, 132)
MAX_MEAN_DIFF = 6.0

HOUR = 3600
FAKE = {
    "/api/editor_projects": {"projects": [
        {"folder": "C:/Clips/Rocket League", "name": "Rocket League", "folder_exists": True, "targets": ["shorts", "tiktok"],
         "profile_name": "ערוץ ראשי", "clip_edit_count": 4, "updated_hours_ago": 1},
        {"folder": "C:/Clips/Valorant", "name": "Valorant", "folder_exists": True, "targets": ["shorts"], "updated_hours_ago": 26},
        {"folder": "C:/Clips/Old", "name": "Old", "folder_exists": False, "targets": [], "updated_hours_ago": 24 * 5},
    ]},
    "/api/video_editor/runs": [
        {"folder": "C:/Clips/Rocket League", "status": "success", "files_created": 12, "started_hours_ago": 1},
        {"folder": "C:/Clips/Valorant", "status": "failed", "started_hours_ago": 26},
    ],
    "/api/history": [
        {"script": "video_editor.py", "status": "success", "duration": 754, "started_hours_ago": 1,
         "result": {"files_created": 12, "errors": 0}, "summary": "files_created: 12 | errors: 0"},
        {"script": "video_editor.py", "status": "failed", "duration": 41, "started_hours_ago": 26,
         "result": {"files_created": 0, "errors": 2}, "summary": "errors: 2"},
        {"script": "rocket_shorts_publisher.py", "status": "success", "duration": 95, "started_hours_ago": 50,
         "result": {"uploaded": 3}, "summary": "uploaded: 3"},
    ],
    "/api/queue_status": {"pending": 0, "light": 0, "heavy": 0},
    "/api/lock_status": {"locked": False},
    "/api/hardware_stats": {"cpu": 23.0, "ram": 61.0, "gpu": 12.0, "vram": 34.0, "encoder": 0.0},
    "/api/render_stats": [
        {"script": "my_scripts/video/video_editor.py", "avg_seconds": 612, "run_count": 48},
        {"script": "my_scripts/publish/rocket_shorts_publisher.py", "avg_seconds": 95, "run_count": 17},
        {"script": "my_scripts/files/clip_organizer.py", "avg_seconds": 12, "run_count": 90},
    ],
    "/api/hardware_history": {
        "cpu": [20 + (i * 37) % 55 for i in range(48)],
        "ram": [55 + (i * 7) % 12 for i in range(48)],
        "gpu": [5 + (i * 23) % 40 for i in range(48)],
    },
    "/api/clips_captured_by_day": {"counts": [(i * 5) % 9 for i in range(30)]},
    "/api/game_playtime": [{"game": "Rocket League", "hours": 12.5}, {"game": "Valorant", "hours": 3.25}],
    "/api/video_editor/eta": {"estimated_total_seconds": 95, "run_count": 3},
    "/api/render_queue": {"paused": False, "running": None, "pending": [],
                          "settings": {"wait_when_busy": True, "processes": ["obs64.exe"], "gpu_percent": 80}},
    # "הורצו לאחרונה" ומועדפים נקראים מההיסטוריה ומ-config.json של המכונה - קבועים כאן
    "/api/scripts/recent": {"names": ["video_editor.py", "rocket_shorts_publisher.py"]},
    # פרופילים/ערכות מותג שטסטים אחרים באותו session שמרו
    "/api/video_editor_profiles": {},
    "/api/video_editor_profiles_meta_all": {"meta": {}},
    "/api/brand_kits": {"kits": {}},
    "/api/undo/status": {"pending": False},
}
FAVORITE_SCRIPTS = ["video_editor.py"]

# fetch עטוף (לא page.route - ה-service worker מטפל ב-fetch לפני ש-Playwright רואה אותו).
# *_hours_ago הופך ל-ISO יחסית לרגע הריצה, כדי שהזמן היחסי המוצג יהיה תמיד זהה.
FAKE_FETCH = """
(() => {
  const fake = __FAKE__;
  const favorites = __FAVORITES__;
  const iso = hours => new Date(Date.now() - hours * 3600e3).toISOString();
  const fix = value => {
    if (Array.isArray(value)) return value.map(fix);
    if (!value || typeof value !== "object") return value;
    const out = {};
    for (const [key, v] of Object.entries(value)) {
      if (key === "updated_hours_ago") out.updated_at = iso(v);
      else if (key === "started_hours_ago") out.started_at = iso(v);
      else out[key] = fix(v);
    }
    return out;
  };
  const original = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const method = ((init && init.method) || (input && input.method) || "GET").toUpperCase();
    const url = new URL(typeof input === "string" ? input : input.url, location.href);
    const json = data => new Response(JSON.stringify(data), {headers: {"Content-Type": "application/json"}});
    if (method === "GET" && Object.prototype.hasOwnProperty.call(fake, url.pathname)) return Promise.resolve(json(fix(fake[url.pathname])));
    if (method === "GET" && url.pathname === "/api/scripts") {
      return original(input, init).then(r => r.json()).then(scripts => json(scripts.map(s => ({...s, is_favorite: favorites.includes(s.id.split("/").pop())}))));
    }
    return original(input, init);
  };
})();
""".replace("__FAKE__", json.dumps(FAKE, ensure_ascii=False)).replace("__FAVORITES__", json.dumps(FAVORITE_SCRIPTS))

# אנימציות ומעברים קפואים - אין הבהוב סמן, spinner או מעבר באמצע הצילום
FREEZE_CSS = """
*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }
"""

SCREENS = {
    "home": {
        "open": "() => goHome()",
        "ready": "() => document.querySelectorAll('#homeProjects .home-project').length === 3 && document.querySelectorAll('#homeRuns .feed-item').length === 3",
    },
    "jobs": {
        "open": "() => openStudioJobs()",
        "ready": "() => document.querySelectorAll('#veJobsList .ve-job-card').length === 3",
    },
    "stats": {
        "open": "() => openStats()",
        "ready": "() => document.querySelectorAll('#statsList .stats-row .stats-bar').length === 3 && document.querySelectorAll('#statsTiles > *').length >= 3",
    },
    "studio": {
        "open": "() => openStudio()",
        "ready": "() => document.body.classList.contains('ve-focus') && !document.getElementById('videoEditorOptions').hidden",
    },
}


def _capture(editor_server, edge_browser, screen, theme):
    spec = SCREENS[screen]
    context = edge_browser.new_context(viewport={"width": 1440, "height": 900}, locale="he-IL", reduced_motion="reduce",
                                       device_scale_factor=1, color_scheme="dark" if theme == "dark" else "light")
    context.add_init_script(FAKE_FETCH)
    context.add_init_script("try { localStorage.setItem('veFocus', 'false'); localStorage.setItem('veMode', JSON.stringify('simple'));"
                            " localStorage.setItem('uiTourSeen', '1'); } catch (e) {}")
    try:
        page = context.new_page()
        page.goto(f"{editor_server['base_url']}/?token={editor_server['web_app'].ACCESS_TOKEN}")
        page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)
        page.evaluate(f"() => {{ document.documentElement.dataset.theme = {theme!r}; }}")
        page.add_style_tag(content=FREEZE_CSS)
        page.evaluate(spec["open"])
        page.wait_for_function(spec["ready"], timeout=15000)
        page.wait_for_function("() => typeof uiPendingWork !== 'function' || uiPendingWork() === 0")
        page.evaluate("() => document.fonts.ready")
        page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        return page.screenshot(animations="disabled", caret="hide")
    finally:
        context.close()


def _mean_diff(a, b):
    return sum(abs(x - y) for x, y in zip(a.getdata(), b.getdata())) / (SIZE[0] * SIZE[1])


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("screen", sorted(SCREENS))
def test_real_screen_matches_the_visual_baseline(editor_server, edge_browser, screen, theme):
    image_module = pytest.importorskip("PIL.Image")
    from io import BytesIO
    shot = _capture(editor_server, edge_browser, screen, theme)
    full = image_module.open(BytesIO(shot))
    current = full.convert("L").resize(SIZE, image_module.Resampling.BILINEAR)
    if os.environ.get("CLIPFORGE_SAVE_VISUAL_SCREENS") == "1":  # לעיון במסכים המלאים (למשל אחרי עדכון baseline)
        os.makedirs(FAILURE_DIR, exist_ok=True)
        full.save(os.path.join(FAILURE_DIR, f"{screen}_{theme}_full.png"))
    baseline_path = os.path.join(BASELINE_DIR, f"screen_{screen}_{theme}.png")
    if os.environ.get("CLIPFORGE_UPDATE_VISUAL_BASELINES") == "1" or not os.path.isfile(baseline_path):
        os.makedirs(BASELINE_DIR, exist_ok=True)
        current.save(baseline_path)
        pytest.skip(f"baseline נכתב: {baseline_path}")
    baseline = image_module.open(baseline_path).convert("L")
    diff = _mean_diff(current, baseline)
    if diff > MAX_MEAN_DIFF:
        os.makedirs(FAILURE_DIR, exist_ok=True)
        full.save(os.path.join(FAILURE_DIR, f"{screen}_{theme}_actual.png"))
        current.save(os.path.join(FAILURE_DIR, f"{screen}_{theme}_small.png"))
    assert diff <= MAX_MEAN_DIFF, (
        f"{screen}/{theme}: הפרש ממוצע {diff:.2f}/255 מול ה-baseline - שינוי עיצוב לא מכוון? "
        f"(צילום מלא ב-.cache/visual_failures; לעדכון: CLIPFORGE_UPDATE_VISUAL_BASELINES=1)")


def test_the_fake_data_really_reaches_the_screens(editor_server, edge_browser):
    """בלי זה baseline של מסך ריק (fetch לא נעטף) היה עובר בשקט לנצח."""
    context = edge_browser.new_context(viewport={"width": 1440, "height": 900}, locale="he-IL")
    context.add_init_script(FAKE_FETCH)
    try:
        page = context.new_page()
        page.goto(f"{editor_server['base_url']}/?token={editor_server['web_app'].ACCESS_TOKEN}")
        page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)
        page.evaluate("() => goHome()")
        page.wait_for_function(SCREENS["home"]["ready"], timeout=15000)
        names = page.eval_on_selector_all("#homeProjects .home-project-name", "els => els.map(e => e.textContent)")
        assert names == ["📁 Rocket League", "📁 Valorant", "📁 Old"]
        assert page.inner_text("#hwCpuText") == "23%"
        assert page.evaluate("() => state.scripts.filter(s => s.is_favorite).map(s => s.id.split('/').pop())") == FAVORITE_SCRIPTS
        assert page.evaluate("() => state.recentScriptNames") == FAKE["/api/scripts/recent"]["names"]
    finally:
        context.close()
