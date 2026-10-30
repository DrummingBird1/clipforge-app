# dev/make_demo_video.py
#
# 30.10.2026 (הריפו הציבורי, "קבוצה ד'"): סרטון הדגמה של 2-3 דקות ליוטיוב - mp4 ב-1920x1080, ‏30fps, ‏H.264, בלי קריינות,
# עם כרטיסי כותרת בין הקטעים, ו-SRT עם אותן כותרות. אותם נתוני דוגמה ושרת כמו dev/make_screenshots.py ו-dev/make_demo_gif.py
# (תיקייה זמנית ב-%TEMP%, ממשק באנגלית, שום קובץ של המשתמש). הסרטון כבד ולא נכנס לריפו - ברירת המחדל היא build/demo/
# (ב-.gitignore); תיקייה אחרת עוברת ב---out. הנתיב הזמני כולל את שם המשתמש ואי אפשר לטשטש אותו בדיעבד, אז הרכיבים שמציגים נתיבים מוסתרים
# מההתחלה (make_demo_gif.HIDE_PATHS), ומשגיח בדף בודק חמש פעמים בשנייה, לאורך כל ההקלטה וגם בתוך מסגרת הטלפון, שהנתיב
# ושם המשתמש לא גלויים - אם הופיעו, לא נוצר סרטון. ההמתנות לרינדור מקוצרות.
#
#   uv run python dev/make_demo_video.py [--out <folder>/clipforge-demo.mp4]
import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_demo_gif as gif  # noqa: E402 - אחרי ה-sys.path
import make_screenshots as shots  # noqa: E402

SIZE = {"width": 1920, "height": 1080}


def default_out():
    """build/demo/clipforge-demo-<גרסה>.mp4 בתוך הריפו (build/ ב-.gitignore) - בלי נתיב של מחשב מסוים."""
    sys.path.insert(0, os.path.join(shots.ROOT, "src"))
    from utils.shared.version import APP_VERSION
    return os.path.join(shots.ROOT, "build", "demo", f"clipforge-demo-{APP_VERSION}.mp4")



REPO = "github.com/DrummingBird1/clipforge-app"
TITLES = ["1. Start here", "2. Pick your clips", "3. Run it", "4. Shorts and publishing targets", "5. Data videos",
          "6. Every output in one place", "7. On your phone"]
MAX_WAIT_SECONDS = 2.0   # המתנה לרינדור מתקצרת לכל היותר לזה

CARD = r"""([title, sub, logo]) => {
  document.getElementById('demoCard')?.remove();
  const card = document.createElement('div');
  card.id = 'demoCard';
  card.style.cssText = 'position:fixed;inset:0;z-index:2147483647;display:flex;flex-direction:column;align-items:center;' +
    'justify-content:center;gap:24px;background:#0b1016;color:#f2f5f8;font-family:Heebo,"Segoe UI",system-ui,sans-serif;direction:ltr';
  if (logo) card.append(Object.assign(document.createElement('img'), {src: logo, style: 'width:160px;height:160px;border-radius:32px'}));
  card.append(Object.assign(document.createElement('div'), {textContent: title, style: 'font-size:72px;font-weight:700'}));
  if (sub) for (const line of sub.split('\n')) card.append(Object.assign(document.createElement('div'), {textContent: line, style: 'font-size:40px;color:#7fd8ea'}));
  document.body.appendChild(card);
}"""
WATCH = r"""(needles) => {
  window.__demoLeaks = [];
  needles = needles.filter(Boolean).map(n => n.toLowerCase());
  setInterval(() => {
    if (!document.body || !window.top.__demoRecording) return;   // לפני הפריים הראשון של הסרטון (טעינת הדף) - נחתך
    // מסגרת שהדף שמעליה מסתיר (הטלפון, עד שהוא באנגלית) - לא נראית בסרטון
    if (window.frameElement && getComputedStyle(window.frameElement).visibility !== 'visible') return;
    const inputs = [...document.querySelectorAll('input, textarea')].filter(el => el.checkVisibility());
    // מה שעל המסך: innerText כולל את כל האפשרויות של <select> סגור - בסרטון רואים רק את הנבחרת
    const selects = [...document.querySelectorAll('select')].filter(el => el.checkVisibility());
    const closed = selects.map(el => [el, el.style.display]);
    for (const [el] of closed) el.style.display = 'none';
    const text = document.body.innerText;
    for (const [el, display] of closed) el.style.display = display;
    const picked = selects.map(el => el.selectedOptions[0]?.text || '').join(' ');
    const shown = (text + ' ' + picked + ' ' + inputs.map(el => el.value).join(' ')).toLowerCase();
    // 31.10.2026: גם עברית - הסרטון באנגלית מהפריים הראשון (קודם מסך הטלפון הבהב בעברית)
    const he = shown.search(/[֐-׿]/);
    if (he >= 0 && window.__demoLeaks.length < 20) window.__demoLeaks.push(`hebrew: ...${shown.slice(Math.max(0, he - 40), he + 40)}`);
    for (const n of needles) {
      const i = shown.indexOf(n);
      if (i >= 0 && window.__demoLeaks.length < 20) {
        const tab = document.querySelector('.tab-btn.active, [data-tab].active')?.dataset.tab || '';
        window.__demoLeaks.push(`${n} @ ${tab} / focus=${document.body.classList.contains('ve-focus')}: ...${shown.slice(Math.max(0, i - 90), i)}`);
      }
    }
  }, 200);
}"""
# מרכז ההתראות בהדגמה: ההתראות של נתוני הדוגמה, מוגשות בדף. אחרי הריצות /api/notifications נתקע לפעמים, וההתראות שהריצות
# הוסיפו הן סיכום גולמי עם manifest_path (נתיב עם שם המשתמש) - לכן לא מהשרת
DEMO_NOTIFICATIONS = r"""() => {
  const now = Date.now() / 1000;
  const items = [
    ['3 videos are ready', 'Highlights - Vertical Short', 'ok', 'outputs', 40],
    ['Fruit harvest preview is ready', 'Data videos - 5 seconds', 'ok', 'outputs', 90],
    ['A new clip is waiting for approval', 'match_03.mp4', 'info', 'bot', 600],
    ['The export drive is 85% full', 'D:\\ - 120 GB free', 'warn', '', 3600],
    ['A run stopped', 'Week 43 - the source file is missing', 'bad', 'scripts', 7200],
  ].map(([title, body, level, target, ago], i) => ({id: 100 - i, title, body, level, target, read: i > 1, created_at: now - ago, kind: 'run'}));
  const real = window.fetch;
  const json = (body) => Promise.resolve(new Response(JSON.stringify(body), {headers: {'Content-Type': 'application/json'}}));
  window.fetch = (url, options) => {
    const u = String(url);
    if (u === '/api/notifications') return json({items, unread: 2});
    if (u.startsWith('/api/notifications/')) return json({ok: true});
    return real(url, options);
  };
}"""
CLICK_TAB = r"""(label) => {
  const tab = [...document.querySelectorAll('#videoEditorOptions button')].find(b => b.checkVisibility() && b.textContent.trim().endsWith(label));
  if (tab) tab.click();
  return !!tab;
}"""
HIDE_HOME_LISTS = """document.addEventListener('DOMContentLoaded', () => { const style = document.createElement('style');
  style.textContent = '#homeProjects, #homeRuns { display: none !important; }';   /* פרויקטים וריצות אחרונים - עם נתיבים */
  document.head.appendChild(style); });"""
PHONE_FRAME = r"""(src) => {
  const back = document.createElement('div');
  back.id = 'demoPhone';
  back.style.cssText = 'position:fixed;inset:0;z-index:2147483646;display:flex;align-items:center;justify-content:center;background:#0b1016';
  const frame = Object.assign(document.createElement('iframe'), {src});
  frame.style.cssText = 'width:390px;height:844px;border:14px solid #222a33;border-radius:44px;background:#000;visibility:hidden';
  back.append(frame);
  document.body.appendChild(back);
}"""


class Recorder:
    """הקלטה אחת: זמנים של כרטיסי הכותרת ושל ההמתנות, כדי לקצר אותן ולכתוב SRT."""

    def __init__(self):
        self.start = time.monotonic()
        self.first = 0.0   # תחילת הסרטון - אחרי טעינת הדף
        self.cards = []    # (התחלה, סוף, טקסט)
        self.waits = []    # (התחלה, סוף)

    def now(self):
        return time.monotonic() - self.start

    def card(self, page, title, sub="", logo="", seconds=2.6):
        t0 = self.now()
        page.evaluate(CARD, [title, sub, logo])
        page.wait_for_timeout(int(seconds * 1000))
        page.evaluate("() => document.getElementById('demoCard')?.remove()")
        self.cards.append((t0, self.now(), title if not sub else f"{title}\n{sub}"))

    def wait(self, page, fn, timeout):
        t0 = self.now()
        page.wait_for_function(fn, timeout=timeout)
        self.waits.append((t0, self.now()))


def segments(rec, end):
    """[(התחלה, סוף, מהירות)] לכל ההקלטה - ההמתנות הארוכות מואצות."""
    out, t = [], rec.first
    for a, b in sorted(rec.waits):
        if b - a <= MAX_WAIT_SECONDS or a < t:
            continue
        out += [(t, a, 1.0), (a, b, (b - a) / MAX_WAIT_SECONDS)]
        t = b
    return out + [(t, end, 1.0)]


def map_time(segs, t):
    out = 0.0
    for a, b, speed in segs:
        if t <= a:
            break
        out += (min(t, b) - a) / speed
    return out


def srt(segs, cards):
    def stamp(s):
        ms = int(round(s * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return "\n".join(f"{i}\n{stamp(map_time(segs, a))} --> {stamp(map_time(segs, b))}\n{text}\n" for i, (a, b, text) in enumerate(cards, 1))


def record(browser, url, demo, video_dir):
    clips, approval, tmp, logo = demo
    context = browser.new_context(viewport=SIZE, record_video_dir=video_dir, record_video_size=SIZE, locale="en-US",
                                  service_workers="block")
    context.add_init_script("""try { localStorage.setItem('uiLang', 'en'); localStorage.setItem('veMode', JSON.stringify('regular'));
      localStorage.setItem('veLayout', JSON.stringify('tabs')); localStorage.setItem('veRunSheet', 'false');
      localStorage.setItem('dvzMode', 'regular'); } catch (e) {}""")
    context.add_init_script(gif.HIDE_PATHS)
    context.add_init_script(HIDE_HOME_LISTS)
    user = os.environ.get("USERNAME", "")
    context.add_init_script(f"({WATCH})({json.dumps([tmp, tmp.replace(chr(92), '/'), user if len(user) > 2 else ''])})")
    rec = Recorder()
    page = context.new_page()
    shots._ready(page, url)
    page.evaluate("""async (name) => { await fetch('/api/video_editor_profiles', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, settings: {vertical: true, codec: 'h264'}})}); await loadVideoEditorProfiles(); }""", gif.STYLE)
    page.evaluate("() => { closeVeEditor(); switchTab('scripts'); }")
    page.wait_for_load_state("networkidle")
    rec.first = rec.now()
    page.evaluate("() => { window.__demoRecording = true; }")   # המשגיח בודק מכאן - זה הפריים הראשון של הסרטון

    # 1. מסך הבית
    rec.card(page, "ClipForge", "A local video studio for gameplay clips and data videos", logo, seconds=3.2)
    rec.card(page, TITLES[0])
    page.wait_for_timeout(4000)
    page.mouse.move(700, 400)
    page.wait_for_timeout(3000)

    # 2. הסטודיו: קבצים, סגנון, תצוגה מקדימה וציר זמן
    rec.card(page, TITLES[1])
    page.evaluate("() => selectScript(state.scripts.find(s => s.id.endsWith('video_editor.py')).id)")
    page.evaluate("() => setVeFocus(true)")
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", clips)
    rec.wait(page, "() => document.querySelectorAll('#veQueueList .ve-queue-row').length === 3", 30000)
    rec.wait(page, "() => _veInLiveMode() && document.getElementById('veLiveVideo').readyState >= 2", 30000)
    page.evaluate("() => { const bar = document.getElementById('veStartFromBar'); if (bar) bar.hidden = true; }")
    page.wait_for_timeout(2500)
    page.select_option("#vePreset", "profile:" + gif.STYLE)
    rec.wait(page, "() => document.getElementById('veVertical').checked", 10000)
    rec.wait(page, "() => _veInLiveMode() && document.getElementById('veLiveVideo').readyState >= 2", 30000)
    page.evaluate("() => { const v = document.getElementById('veLiveVideo'); v.muted = true; v.play(); }")
    page.wait_for_timeout(5000)
    for label, seconds in (("Color", 3500), ("Layers", 3500), ("Time", 5000)):   # כמה מהלשוניות, ואז ציר הזמן
        page.evaluate(CLICK_TAB, label)
        page.wait_for_timeout(seconds)

    # 3. Run ותוצאות
    rec.card(page, TITLES[2])
    page.click("#veStickyRunBtn")
    rec.wait(page, "() => document.querySelectorAll('#veResultsList .ve-result-main').length === 3", 300000)
    page.wait_for_timeout(7000)

    # 4. Shorts ויעדי פרסום - רק ההגדרות, שום העלאה
    rec.card(page, TITLES[3])
    page.evaluate("() => { closeVeResults?.(); }")
    page.evaluate(CLICK_TAB, "Export")
    page.wait_for_timeout(6000)
    page.evaluate("() => { closeVeEditor(); switchTab('rocket'); }")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(6000)

    # 5. עורך הגרפים: פרק דוגמה, תצוגה מונפשת ורינדור קצר
    rec.card(page, TITLES[4])
    page.evaluate("() => switchTab('dataviz')")
    rec.wait(page, "() => typeof dvzState !== 'undefined' && dvzState.selected === 'fruit_harvest'", 30000)
    rec.wait(page, "() => (document.getElementById('dvzPreviewImg') || {}).src?.startsWith('blob:')", 60000)
    page.wait_for_timeout(2500)
    page.evaluate("() => dvzToggleAnimation(true)")
    page.wait_for_timeout(9000)
    page.evaluate("() => { dvzEditor.open = true; dvzLoadEditor(); }")
    page.wait_for_timeout(5000)
    page.evaluate("() => { dvzToggleAnimation(false); document.getElementById('dvzMode').value = 'preview'; dvzModeChanged?.(); dvzRun(); }")
    rec.wait(page, "() => dvzState.running === true", 20000)
    rec.wait(page, "() => dvzState.running === false", 300000)
    page.wait_for_timeout(5000)

    # 6. התוצרים ומרכז ההתראות
    rec.card(page, TITLES[5])
    page.evaluate("() => switchTab('outputs')")
    rec.wait(page, "() => document.querySelectorAll('#outputsList .output-card').length > 0", 30000)
    page.wait_for_timeout(6000)
    page.evaluate(DEMO_NOTIFICATIONS)
    page.evaluate("() => toggleNotificationCenter(true)")
    rec.wait(page, "() => document.querySelectorAll('#notifList .notif-item').length === 5", 30000)
    page.wait_for_timeout(6000)
    page.evaluate("() => toggleNotificationCenter(false)")

    # 7. מסך הטלפון - במסגרת בגודל טלפון
    rec.card(page, TITLES[6])
    page.evaluate(PHONE_FRAME, url.split("?")[0])
    frame = None
    deadline = time.monotonic() + 30
    while frame is None and time.monotonic() < deadline:
        frame = next((f for f in page.frames if f != page.main_frame and f.url.startswith(url.split("?")[0])), None)
        page.wait_for_timeout(100)
    frame.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=30000)
    frame.evaluate(shots.PHONE_FAKE, [False, approval])
    frame.evaluate("() => { closeVeEditor(); switchTab('phone'); }")
    frame.wait_for_function("() => document.querySelectorAll('#phoneRuns .phone-run').length > 0", timeout=30000)
    frame.evaluate("() => document.querySelectorAll('video').forEach(v => { v.muted = true; v.controls = false; v.currentTime = 1; })")
    # המסגרת נחשפת רק כשהטלפון כבר באנגלית ומוכן (קודם הממשק העברי הבהב בה לפני התרגום)
    frame.wait_for_function("() => _uiLang === 'en' && document.documentElement.dir === 'ltr' && !/[\\u0590-\\u05ff]/.test(document.body.innerText)",
                            timeout=30000)
    page.evaluate("() => { document.querySelector('#demoPhone iframe').style.visibility = 'visible'; }")
    page.wait_for_timeout(8000)

    # 8. סיום
    rec.card(page, "ClipForge", f"{REPO}\nFree & open source (MIT)", logo, seconds=5.0)
    end = rec.now()
    leaks = [leak for f in page.frames for leak in (f.evaluate("() => window.__demoLeaks || []") or [])]
    video = page.video.path()
    context.close()
    if leaks:
        report = os.path.join(tempfile.gettempdir(), "clipforge_demo_leaks.json")   # התיקייה הזמנית של ההדגמה נמחקת
        with open(report, "w", encoding="utf-8") as f:
            json.dump(sorted(set(leaks)), f, ensure_ascii=False, indent=1)
        raise RuntimeError(f"the recording showed Hebrew, a local path or the user name - not making the video ({len(set(leaks))}, see {report})")
    return video, rec, end


def encode(ffmpeg, video, segs, out):
    parts = [f"[0:v]trim={a:.3f}:{b:.3f},setpts=(PTS-STARTPTS)/{speed:.4f}[p{i}]" for i, (a, b, speed) in enumerate(segs)]
    graph = ";".join(parts) + ";" + "".join(f"[p{i}]" for i in range(len(segs))) + \
        f"concat=n={len(segs)}:v=1:a=0,fps=30,scale=1920:1080:flags=lanczos,format=yuv420p[v]"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", video, "-filter_complex", graph, "-map", "[v]", "-c:v", "libx264",
                    "-preset", "slow", "-crf", "20", "-profile:v", "high", "-movflags", "+faststart", out], check=True, timeout=1800)


def main():
    parser = argparse.ArgumentParser(description="Make the ClipForge demo video (mp4 + srt) from demo data")
    parser.add_argument("--out", default="", help="default: build/demo/clipforge-demo-<version>.mp4 in the repo")
    args = parser.parse_args()
    args.out = args.out or default_out()

    tmp = tempfile.mkdtemp(prefix="clipforge_video_")
    for name, var in (("data", "CLIPFORGE_DATA_DIR"), ("workspace", "CLIPFORGE_WORKSPACE_DIR"), ("exports", "CLIPFORGE_EXPORT_DIR")):
        os.makedirs(os.path.join(tmp, name))
        os.environ[var] = os.path.join(tmp, name)
    os.environ["CLIPFORGE_NO_SCHTASKS"] = "1"
    with open(os.path.join(tmp, "data", "rocket_settings.json"), "w", encoding="utf-8") as f:
        json.dump({"input_dir": "D:\\Videos\\Clips", "output_dir": "D:\\Videos\\Shorts"}, f)   # נתיבי דוגמה במסך ההגדרות
    with open(os.path.join(shots.ROOT, "assets", "app_icon_192.png"), "rb") as f:
        logo = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    server = None
    try:
        ffmpeg = shots._ffmpeg()
        clips, approval = shots.seed(tmp, ffmpeg)
        server, url = shots.start_server()
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            video, rec, end = record(browser, url, (clips, approval, os.path.realpath(tmp), logo), os.path.join(tmp, "video"))
            browser.close()
        segs = segments(rec, end)
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        encode(ffmpeg, video, segs, args.out)
        with open(os.path.splitext(args.out)[0] + ".srt", "w", encoding="utf-8") as f:
            f.write(srt(segs, rec.cards))
        print(f"{args.out}: {map_time(segs, end):.0f} s, {os.path.getsize(args.out) / 1e6:.1f} MB")
    finally:
        if server is not None:
            server.should_exit = True
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
