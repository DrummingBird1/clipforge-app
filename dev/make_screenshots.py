# dev/make_screenshots.py
#
# 30.10.2026 (הכנה להפצה ציבורית): מייצר מחדש את צילומי המסך של ה-README - docs/images/<מסך>.png באנגלית ו-docs/images/he/
# בעברית - מנתוני דמה בלבד. data/, ‏workspace/ ותיקיית הייצוא מופנים לתיקייה זמנית ב-%TEMP% (CLIPFORGE_DATA_DIR,
# CLIPFORGE_WORKSPACE_DIR, CLIPFORGE_EXPORT_DIR) לפני שמשהו מ-src/ מיובא, כך שאף קובץ של המשתמש לא נקרא ולא נכתב, ואין
# בתמונות שום שם אישי. השרת רץ בתוך התהליך על פורט פנוי (לא 8878) בלי בדיקת עדכונים ברשת, והדפדפן הוא Edge דרך Playwright,
# כמו בטסטי הדפדפן (tests/conftest.py). צריך ffmpeg (ffmpeg/bin או PATH) לקליפים ולתמונות הממוזערות.
#
#   uv run python dev/make_screenshots.py            # שתי השפות
#   uv run python dev/make_screenshots.py --lang en  # רק אנגלית
import argparse

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENS = ("studio", "simple", "branding", "dataviz", "outputs", "notifications", "phone")
DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}

# נתוני הטלפון מזויפים בדף (כמו tests/web/test_web_app_phone_browser.py) - service worker מטפל ב-fetch, אז page.route לא
# תופס אותם. שום POST לא יוצא לשרת.
PHONE_FAKE = """([he, clip]) => {
  const now = Date.now() / 1000;
  const queue = {paused: false, resume_at: null,
                 pending: [{id: 2, label: he ? 'קליפים מהשבוע' : 'This week\\'s clips', folder: 'D:/Videos/Week 44'}],
                 running: {script: 'video_editor.py', run_id: 'r3', started_at: now - 95}};
  const approvals = [{id: 1, path: clip, name: 'match_03.mp4', game: 'Gameplay', created_at: '2026-10-30'}];
  const runs = {runs: [
    {id: 'r2', folder: 'D:/Videos/Week 43', status: 'success', started_at: '2026-10-29T18:20:00', profile_name: 'Shorts'},
    {id: 'r1', folder: 'D:/Videos/Trip', status: 'success', started_at: '2026-10-28T11:05:00', profile_name: 'TikTok'}]};
  const realFetch = window.fetch;
  const json = (body) => Promise.resolve(new Response(JSON.stringify(body), {status: 200, headers: {'Content-Type': 'application/json'}}));
  window.fetch = (url, options = {}) => {
    const u = String(url);
    if ((options.method || 'GET') !== 'GET') return json({ok: true});
    if (u === '/api/render_queue') return json(queue);
    if (u === '/api/approvals') return json(approvals);
    if (u === '/api/video_editor/runs') return json(runs);
    return realFetch(url, options);
  };
}"""

CSV_HEAD = "date,fruit,tons\n"
FRUITS = {"Apples": 40, "Bananas": 25, "Cherries": 12, "Dates": 8, "Grapes": 30, "Mangoes": 6, "Oranges": 35, "Pears": 15}


def _ffmpeg():
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    return get_ffmpeg_exe()


# 8.11.2026: קליפי הדוגמה נראים כמו משחק (שמיים, קרקע, אויבים שזזים, HUD) במקום מעברי צבע חלקים. הכול מצויר ב-ffmpeg בלי
# שום נכס חיצוני, ובלי טקסט (drawtext תלוי בגופן) - אז אין רישיון לבדוק ואין שם אישי בתמונה. (שמיים עליון, שמיים באופק)
SKIES = (("0x1d2b53", "0xff8a4c"), ("0x0b3c49", "0x62d2a2"), ("0x2b1055", "0xf06aa0"),
         ("0x1a2a1f", "0xd9b44a"), ("0x10253f", "0x7fb7ff"), ("0x331a2e", "0xff6b6b"))
ENEMIES = ("0xe5484d", "0xf5a524", "0xb86bff", "0x4cc9f0", "0xff7ab6")


def _game_scene_filter(width, height, seed):
    """שרשרת drawbox לסצנה: קרקע ואופק, שלושה "אויבים" שנעים, וה-HUD - שורת חיים ומגן, מיני-מפה, כוונת ותחמושת."""
    unit = min(width, height) / 720.0
    horizon = round(height * 0.60)

    def px(value):
        return f"{value * unit:.1f}"

    parts = [f"drawbox=y={horizon}:w=iw:h=ih-{horizon}:color=0x16241c:t=fill", f"drawbox=y={horizon}:w=iw:h={px(3)}:color=0x7be0a0@0.6:t=fill"]
    for n in range(3):   # אויבים: מיקום אופקי נע לפי הזמן, נעמדים על האופק
        color = ENEMIES[(seed + n) % len(ENEMIES)]
        w_, h_ = (50 + 14 * ((seed + n) % 3)) * unit, (110 + 40 * ((seed + 2 * n) % 3)) * unit
        base, amp = (0.18, 0.62, 0.45)[n] + 0.04 * (seed % 3), (0.08, 0.10, 0.05)[n]
        speed, phase = (0.9, 0.6, 1.3)[n], (0.0, 1.0, 0.5)[n] + seed
        parts.append(f"drawbox=x='iw*{base:.2f}+iw*{amp:.2f}*sin(t*{speed}+{phase})':y={horizon - h_:.1f}:w={w_:.1f}:h={h_:.1f}:color={color}:t=fill")
    parts += [
        f"drawbox=x={px(24)}:y={px(24)}:w={px(300)}:h={px(26)}:color=white@0.9:t={px(3)}",   # חיים
        f"drawbox=x={px(30)}:y={px(30)}:w='{px(288)}*(0.55+0.4*sin(t*0.7)*sin(t*0.7))':h={px(14)}:color=0x30d158:t=fill",
        f"drawbox=x={px(24)}:y={px(60)}:w={px(220)}:h={px(12)}:color=white@0.85:t={px(2)}",   # מגן
        f"drawbox=x={px(28)}:y={px(64)}:w={px(150)}:h={px(4)}:color=0x4cc9f0:t=fill",
        f"drawbox=x=iw-{px(196)}:y={px(24)}:w={px(172)}:h={px(172)}:color=white@0.85:t={px(3)}",   # מיני-מפה
        f"drawbox=x=iw-{px(190)}:y={px(30)}:w={px(160)}:h={px(160)}:color=black@0.45:t=fill",
        f"drawbox=x='iw-{px(110)}+{px(30)}*sin(t*1.1)':y='{px(110)}+{px(28)}*cos(t*0.8)':w={px(10)}:h={px(10)}:color=0xe5484d:t=fill",
        f"drawbox=x=iw-{px(110)}:y={px(110)}:w={px(12)}:h={px(12)}:color=0x30d158:t=fill",
    ]
    for dx, dy, w_, h_ in ((-1, -20, 3, 14), (-1, 6, 3, 14), (-20, -1, 14, 3), (6, -1, 14, 3)):   # כוונת
        parts.append(f"drawbox=x=iw/2+{px(dx)}:y=ih/2+{px(dy)}:w={px(w_)}:h={px(h_)}:color=white:t=fill")
    parts.append(f"drawbox=x=iw/2-{px(70)}:y=ih-{px(70)}:w={px(140)}:h={px(34)}:color=black@0.5:t=fill")   # תחמושת
    for pip in range(5):
        parts.append(f"drawbox=x=iw/2-{px(60 - 24 * pip)}:y=ih-{px(60)}:w={px(16)}:h={px(14)}:color={'0xf5a524' if pip < 3 else '0x666666'}:t=fill")
    parts.append("vignette=PI/5")
    return ",".join(parts)


def _make_clip(ffmpeg, path, size="1280x720", seconds=8, seed=0):
    # סצנת משחק מצוירת (שמיים בהדרגה + _game_scene_filter) עם צליל - H.264 + AAC כדי שהנגן החי בדפדפן יפענח אותו
    width, height = (int(n) for n in size.split("x"))
    top, bottom = SKIES[seed % len(SKIES)]
    sky = f"gradients=s={size}:c0={top}:c1={bottom}:x0={width // 2}:y0=0:x1={width // 2}:y1={round(height * 0.6)}:nb_colors=2:speed=0.0001:r=30"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", sky,
                    "-f", "lavfi", "-i", f"sine=frequency={330 + 110 * seed}:sample_rate=44100",
                    "-vf", _game_scene_filter(width, height, seed),
                    "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
                   check=True, timeout=120)


def _fruit_csv():
    rows = []
    for year in range(2018, 2026):
        for month in (1, 4, 7, 10):
            step = (year - 2018) * 4 + month // 3
            for i, (fruit, base) in enumerate(FRUITS.items()):
                growth = 1 + step * (0.02 + 0.012 * ((i * 3) % 7))
                rows.append(f"{year}-{month:02d}-01,{fruit},{round(base * growth, 1)}")
    return CSV_HEAD + "\n".join(rows) + "\n"


# 30.10.2026: ההתראות לדוגמה בשפת הצילום - בצילום העברי הן היו נשארות באנגלית
NOTIFICATIONS = {
    "en": (("run", "3 videos are ready", "Gameplay - Shorts and YouTube", "ok", "outputs"),
           ("dataviz", "Fruit harvest exported", "1080p, 45 seconds", "ok", "outputs"),
           ("approval", "A new clip is waiting for approval", "match_03.mp4", "info", "bot"),
           ("disk", "The export drive is 85% full", "D:\\ - 120 GB free", "warn", ""),
           ("run", "A run stopped", "Week 43 - the source file is missing", "bad", "scripts")),
    "he": (("run", "3 סרטונים מוכנים", "Gameplay - Shorts ו-YouTube", "ok", "outputs"),
           ("dataviz", "קציר הפירות יוצא", "1080p, ‏45 שניות", "ok", "outputs"),
           ("approval", "קליפ חדש מחכה לאישור", "match_03.mp4", "info", "bot"),
           ("disk", "כונן הייצוא מלא ב-85%", "נשארו 120GB פנויים", "warn", ""),
           ("run", "ריצה נעצרה", "שבוע 43 - קובץ המקור חסר", "bad", "scripts")),
}


def seed_notifications(lang):
    """מרוקן את ההתראות של נתוני הדמה ומוסיף את אלה של השפה (ה-DB הזמני של הצילומים, לא של המשתמש)."""
    from utils.shared import notification_log
    with notification_log._open("") as conn:   # אין API למחיקה - זה DB של תיקיית הדמה הזמנית בלבד
        conn.execute("DELETE FROM notifications")
    for kind, title, body, level, target in NOTIFICATIONS[lang]:
        notification_log.add(kind, title, body, level=level, target=target)


def seed(tmp, ffmpeg):
    """נתוני הדמה: שלושה קליפים לסטודיו, כמה תוצרים, פרק אחד בעורך הגרפים והתראות."""
    clips = os.path.join(tmp, "videos", "Gameplay")
    os.makedirs(clips)
    for i in range(1, 4):
        _make_clip(ffmpeg, os.path.join(clips, f"match_{i:02d}.mp4"), seed=i)

    workspace = os.environ["CLIPFORGE_WORKSPACE_DIR"]
    outputs = [("studio/vertical", "match_01_shorts.mp4", "1080x1920", 1), ("studio/vertical", "match_02_shorts.mp4", "1080x1920", 2),
               ("studio/horizontal", "match_03_youtube.mp4", "1280x720", 3), ("dataviz/outputs/horizontal", "fruit_harvest.mp4", "1280x720", 4),
               ("timelapses/horizontal", "build_timelapse.mp4", "1280x720", 5), ("highlight_reels/vertical", "best_of_october.mp4", "1080x1920", 6)]
    now = time.time()
    for age, (folder, name, size, seed_) in enumerate(outputs):
        path = os.path.join(workspace, *folder.split("/"), name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _make_clip(ffmpeg, path, size=size, seconds=4, seed=seed_)
        os.utime(path, (now - age * 5400, now - age * 5400))

    from dataviz.web.episodes import create_episode
    from utils.shared import data_paths
    root = data_paths.dataviz_root(os.environ["CLIPFORGE_DATA_DIR"])
    create_episode(root, {
        "name": "fruit_harvest", "title": "Fruit harvest", "subtitle": "Tons per quarter (demo data)", "chart": "bar_race",
        "theme": "dark", "time_column": "date", "value_column": "tons", "group_column": "fruit", "period": "day", "csv_text": _fruit_csv()})
    # 31.10.2026: התוויות של הפרק באנגלית - ברירות המחדל של dataviz/config.py בעברית, והן מופיעות בשדות של העורך
    import yaml
    config_path = os.path.join(root, "dataviz_episodes", "fruit_harvest", "config.yaml")
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config.update({"labels": {"date_format": "%b %d, %Y", "record": "New record: {entity}", "others": "Others"},
                   "outro": {"places": ["1st place", "2nd place", "3rd place"]},
                   "scatter": {"x_label": "Total", "y_label": "In the last 30 days"}})
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)

    approval = os.path.join(workspace, "clips", "match_03.mp4")   # תור האישור (CLIPS_DIR) - הנגן בטלפון מנגן ממנו
    os.makedirs(os.path.dirname(approval))
    shutil.copy2(os.path.join(clips, "match_03.mp4"), approval)

    return clips, approval


def start_server():
    import socket
    import uvicorn
    from entrypoints import web_app
    web_app.check_for_update = lambda *_args, **_kwargs: None   # בלי פנייה ל-GitHub בכל טעינת דף
    web_app.limiter.enabled = False
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(web_app.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("the web app didn't start")
    return server, f"http://127.0.0.1:{port}/?token={web_app.ACCESS_TOKEN}"


def _context(browser, lang, viewport, mode="regular"):
    context = browser.new_context(viewport=viewport, locale="he-IL" if lang == "he" else "en-US", service_workers="block",
                                  device_scale_factor=1)
    context.add_init_script(f"""try {{ localStorage.setItem('uiLang', '{lang}'); localStorage.setItem('veMode', JSON.stringify('{mode}'));
      localStorage.setItem('dvzMode', 'regular'); }} catch (e) {{}}""")
    return context


# כתוביות עם שבירת שורות, מסגרת מעוגלת ושכבת שם הקובץ - מדמה את מה שמשתמש היה מגדיר בסטודיו (שדות + אירועי input/change)
BRANDING = """() => {
  const set = (id, value) => {
    const el = document.getElementById(id);
    if (el.type === 'checkbox') el.checked = !!value; else el.value = value;
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  };
  set('veKeepAudio', true); set('veCaptions', true); set('veCaptionStyle', 'box'); set('veCaptionFontSize', 20); set('veCaptionMaxChars', 16);
  addVeLayerCard('frame'); set('veFrameThickness', 14); set('veFrameColor', '#FF8A4C'); set('veFrameRadius', 46);
  addVeLayer('filename');
}"""


def open_studio(page, clips):
    """פותח את הסטודיו על תיקיית הקליפים, עם הנגן החי על פריים אחד (בשני המצבים, הפשוט והרגיל)."""
    page.evaluate("() => selectScript(state.scripts.find(s => s.id.endsWith('video_editor.py')).id)")
    page.evaluate("() => setVeFocus(true)")
    page.wait_for_function("() => document.body.classList.contains('ve-focus')")
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", clips)
    page.wait_for_selector("#veQueueList .ve-queue-row", state="attached", timeout=30000)   # במצב הפשוט התור מוסתר
    page.wait_for_function("() => _veInLiveMode() && document.getElementById('veLiveVideo').readyState >= 2", timeout=30000)
    page.evaluate("() => { const bar = document.getElementById('veStartFromBar'); if (bar) bar.hidden = true; }")   # שאלת "להתחיל מ:"
    page.evaluate("() => { const v = document.getElementById('veLiveVideo'); v.currentTime = 2.5; }")
    page.wait_for_function("() => !document.getElementById('veLiveVideo').seeking")
    page.wait_for_load_state("networkidle")


# נתיב התיקייה הזמנית (עם שם המשתמש ב-Windows) לא נכנס לתמונה: רגע לפני כל צילום, כל טקסט ושדה גלוי שמכילים אותו מקבלים
# נתיב דוגמה, ואז נבדק שבדף הגלוי אין לא את הנתיב ולא את שם המשתמש - אחרת הסקריפט נעצר בלי לשמור את התמונה
MASK = r"""([paths, user]) => {
  const clean = (text) => paths.reduce((out, path) => out.split(path).join('D:\\ClipForge'), text);
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (paths.some(path => node.nodeValue.includes(path))) node.nodeValue = clean(node.nodeValue);
  }
  const inputs = [...document.querySelectorAll('input, textarea')].filter(el => el.checkVisibility());
  for (const el of inputs) if (paths.some(path => el.value.includes(path))) el.value = clean(el.value);
  const shown = (document.body.innerText + ' ' + inputs.map(el => el.value).join(' ')).toLowerCase();
  return [...paths, user].filter(needle => needle && shown.includes(needle.toLowerCase()));
}"""


def _ready(page, url):
    page.goto(url)
    page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=30000)


def shoot(browser, url, lang, demo, out_dir):
    clips, approval, tmp = demo
    os.makedirs(out_dir, exist_ok=True)
    seed_notifications(lang)

    def shot(page, name):
        page.evaluate("() => document.getElementById('toastHost')?.replaceChildren()")   # הודעות קופצות מהשלבים הקודמים
        user = os.environ.get("USERNAME", "")
        leaks = page.evaluate(MASK, [[tmp, tmp.replace("\\", "/")], user if len(user) > 2 else ""])
        if leaks:
            raise RuntimeError(f"{name}: the page shows {leaks} - not saving this screenshot")
        page.screenshot(path=os.path.join(out_dir, f"{name}.png"))

    context = _context(browser, lang, DESKTOP, mode="simple")   # המצב הפשוט של הסטודיו - הממשק למי שרק רוצה סרטון
    page = context.new_page()
    _ready(page, url)
    open_studio(page, clips)
    shot(page, "simple")
    context.close()

    context = _context(browser, lang, DESKTOP)
    page = context.new_page()
    _ready(page, url)
    open_studio(page, clips)
    shot(page, "studio")

    # מראה המותג של 1.2: מסגרת עם פינות מעוגלות, שם הקובץ על הפלט וכתובית שנשברת בשורות - הכול בנגן החי
    page.evaluate(BRANDING)
    page.wait_for_function("() => !!document.querySelector('#veLiveOverlays .ve-live-caption') && !!document.querySelector('#veLiveOverlays .ve-live-item')", timeout=30000)
    page.evaluate("() => document.querySelector('#videoEditorOptions details.ve-category[data-cat=\"layers\"]')?.scrollIntoView({block: 'start'})")
    page.wait_for_load_state("networkidle")
    shot(page, "branding")

    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_function("() => typeof dvzState !== 'undefined' && dvzState.selected === 'fruit_harvest'", timeout=30000)
    page.wait_for_function("() => (document.getElementById('dvzPreviewImg') || {}).src?.startsWith('blob:')", timeout=60000)
    page.wait_for_function("() => (document.getElementById('dvzSavedTo') || {}).textContent?.includes(':')", timeout=30000)   # נטען אחרי התצוגה
    page.wait_for_load_state("networkidle")
    shot(page, "dataviz")

    page.evaluate("() => switchTab('outputs')")
    page.wait_for_function("() => document.querySelectorAll('#outputsList .output-card').length === 6", timeout=30000)
    page.wait_for_function("() => [...document.querySelectorAll('#outputsList .output-card img')].every(i => i.complete)", timeout=60000)
    page.wait_for_load_state("networkidle")
    shot(page, "outputs")

    page.evaluate("() => toggleNotificationCenter(true)")
    page.wait_for_function("() => document.querySelectorAll('#notifList .notif-item').length >= 5", timeout=30000)
    page.wait_for_load_state("networkidle")
    shot(page, "notifications")
    context.close()

    context = _context(browser, lang, PHONE)
    page = context.new_page()
    _ready(page, url)
    page.evaluate("() => closeVeEditor()")
    page.evaluate(PHONE_FAKE, [lang == "he", approval])
    page.evaluate("() => switchTab('phone')")
    page.wait_for_function("() => document.querySelectorAll('#phoneRuns .phone-run').length > 0", timeout=30000)
    # פריים מהקליף בלי פקדי הנגן - בדפדפן headless הם נשארים עם סמל טעינה
    page.evaluate("() => document.querySelectorAll('video').forEach(v => { v.muted = true; v.controls = false; v.preload = 'auto'; v.currentTime = 1; })")
    page.wait_for_function("() => [...document.querySelectorAll('video')].some(v => v.readyState >= 2 && !v.seeking)", timeout=30000)
    page.wait_for_load_state("networkidle")
    shot(page, "phone")
    context.close()


def main():
    parser = argparse.ArgumentParser(description="Regenerate the README screenshots from demo data")
    parser.add_argument("--lang", choices=("en", "he", "both"), default="both")
    parser.add_argument("--out", default=os.path.join(ROOT, "docs", "images"), help="English goes here, Hebrew in <out>/he")
    args = parser.parse_args()

    tmp = tempfile.mkdtemp(prefix="clipforge_screens_")
    for name, var in (("data", "CLIPFORGE_DATA_DIR"), ("workspace", "CLIPFORGE_WORKSPACE_DIR"), ("exports", "CLIPFORGE_EXPORT_DIR")):
        os.makedirs(os.path.join(tmp, name))
        os.environ[var] = os.path.join(tmp, name)
    os.environ["CLIPFORGE_NO_SCHTASKS"] = "1"
    server = None
    try:
        clips, approval = seed(tmp, _ffmpeg())
        server, url = start_server()
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            for lang in (("en", "he") if args.lang == "both" else (args.lang,)):
                shoot(browser, url, lang, (clips, approval, os.path.realpath(tmp)), args.out if lang == "en" else os.path.join(args.out, "he"))
                print(f"{lang}: {', '.join(SCREENS)} -> {args.out if lang == 'en' else os.path.join(args.out, 'he')}")
            browser.close()
    finally:
        if server is not None:
            server.should_exit = True
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
