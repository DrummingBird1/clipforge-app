# dev/make_demo_gif.py
#
# 30.10.2026 (הריפו הציבורי): ה-GIF שבראש ה-README - docs/images/demo.gif. קליפ דוגמה נטען לסטודיו, בוחרים סגנון, רואים
# אותו בנגן החי, "Run", והסרטון מופיע בתוצרים. אותם נתוני דוגמה ושרת כמו dev/make_screenshots.py (תיקייה זמנית ב-%TEMP%,
# שום קובץ של המשתמש), בממשק באנגלית. Playwright מקליט וידאו של הדף, ו-ffmpeg הופך אותו ל-GIF (palettegen / paletteuse),
# עם ההמתנה לרינדור מקוצרת. הנתיב הזמני (עם שם המשתמש) לא יכול להיות מוסתר בדיעבד בווידאו, אז הרכיבים שמציגים נתיבים
# (שורות "נשמר ב-", הלוג, ההודעות הקופצות) מוסתרים מההתחלה, ובכל שלב נבדק שאין בדף הגלוי נתיב או שם משתמש - אחרת נעצר.
#
#   uv run python dev/make_demo_gif.py
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_screenshots as shots  # noqa: E402 - אחרי ה-sys.path

SIZE = {"width": 1440, "height": 900}   # מוקלט כמו צילומי המסך, ומוקטן ב-GIF
HIDE_PATHS = """document.addEventListener('DOMContentLoaded', () => { const style = document.createElement('style');
  style.textContent = '[id$="SavedTo"], #toastHost, #consoleDrawer, #lockStatus { display: none !important; }';
  document.head.appendChild(style); });"""
STYLE = "Vertical Short"   # סגנון דוגמה שנוצר לפני ההקלטה - בתסריט בוחרים אותו מהבורר


def record(browser, url, demo, video_dir, lang="en"):
    """מקליט את התסריט; מחזיר (נתיב הווידאו, זמני השלבים בשניות מתחילת ההקלטה)."""
    clip_folder, tmp = demo
    context = browser.new_context(viewport=SIZE, record_video_dir=video_dir, record_video_size=SIZE,
                                  locale="he-IL" if lang == "he" else "en-US", service_workers="block")
    context.add_init_script(f"""try {{ localStorage.setItem('uiLang', '{lang}'); localStorage.setItem('veMode', JSON.stringify('regular'));
      localStorage.setItem('veRunSheet', 'false'); }} catch (e) {{}}""")
    context.add_init_script(HIDE_PATHS)
    start = time.monotonic()
    marks = {}
    page = context.new_page()
    user = os.environ.get("USERNAME", "")

    def check(step):
        leaks = page.evaluate(shots.MASK, [[tmp, tmp.replace("\\", "/")], user if len(user) > 2 else ""])
        if leaks:
            raise RuntimeError(f"{step}: the page shows {leaks} - not making the GIF")
        marks[step] = time.monotonic() - start

    shots._ready(page, url)
    page.evaluate("""async (name) => { await fetch('/api/video_editor_profiles', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, settings: {vertical: true, codec: 'h264'}})}); await loadVideoEditorProfiles(); }""", STYLE)
    page.evaluate("() => selectScript(state.scripts.find(s => s.id.endsWith('video_editor.py')).id)")
    page.evaluate("() => setVeFocus(true)")
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", clip_folder)
    page.wait_for_selector("#veQueueList .ve-queue-row", timeout=30000)
    page.wait_for_function("() => _veInLiveMode() && document.getElementById('veLiveVideo').readyState >= 2", timeout=30000)
    page.evaluate("() => { const bar = document.getElementById('veStartFromBar'); if (bar) bar.hidden = true; }")
    page.wait_for_load_state("networkidle")
    check("ready")
    page.wait_for_timeout(2500)

    page.select_option("#vePreset", "profile:" + STYLE)                                  # change -> applyVideoEditorPreset
    page.wait_for_function("() => document.getElementById('veVertical').checked", timeout=10000)
    page.wait_for_function("() => _veInLiveMode() && document.getElementById('veLiveVideo').readyState >= 2", timeout=30000)
    page.evaluate("() => { const v = document.getElementById('veLiveVideo'); v.muted = true; v.play(); }")
    check("styled")
    page.wait_for_timeout(6500)

    page.click("#veStickyRunBtn")
    check("run")
    page.wait_for_selector("#veResultsList .ve-result-main", timeout=240000)
    hidden = page.evaluate("() => [...document.querySelectorAll('[id$=\"SavedTo\"]')].every(el => getComputedStyle(el).display === 'none')")
    if not hidden:
        raise RuntimeError("results: the saved-to line with the folder path is visible - not making the GIF")
    page.wait_for_load_state("networkidle")
    check("results")
    page.wait_for_timeout(3500)

    page.evaluate("() => { closeVeEditor(); switchTab('outputs'); }")
    page.wait_for_function("() => document.querySelectorAll('#outputsList .output-card').length > 0", timeout=30000)
    page.wait_for_function("() => [...document.querySelectorAll('#outputsList .output-card img')].every(i => i.complete)", timeout=60000)
    check("outputs")
    page.wait_for_timeout(5000)
    marks["end"] = time.monotonic() - start
    video = page.video.path()
    context.close()
    return video, marks


def to_gif(ffmpeg, video, marks, out, width=1080, fps=10, render_seconds=2.5):
    """הקלטה -> GIF: מהרגע שהסטודיו מוכן ועד הסוף, כשההמתנה לרינדור (מ-Run ועד התוצאות) מקוצרת ל-render_seconds."""
    a, b, c, d = marks["ready"] - 0.3, marks["run"] + 1.2, marks["results"], marks["end"]
    speed = max(1.0, (c - b) / render_seconds)
    graph = (f"[0:v]trim={a:.2f}:{b:.2f},setpts=PTS-STARTPTS[p1];"
             f"[0:v]trim={b:.2f}:{c:.2f},setpts=(PTS-STARTPTS)/{speed:.3f}[p2];"
             f"[0:v]trim={c:.2f}:{d:.2f},setpts=PTS-STARTPTS[p3];"
             f"[p1][p2][p3]concat=n=3:v=1:a=0,fps={fps},scale={width}:-1:flags=lanczos,split[s0][s1];"
             f"[s0]palettegen=max_colors=128:stats_mode=diff[pal];[s1][pal]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", video, "-filter_complex", graph, "-loop", "0", out], check=True, timeout=600)


def main():
    parser = argparse.ArgumentParser(description="Make docs/images/demo.gif from demo data")
    parser.add_argument("--lang", choices=("en", "he", "both"), default="both")
    parser.add_argument("--out", default=os.path.join(shots.ROOT, "docs", "images"), help="English: <out>/demo.gif, Hebrew: <out>/he/demo.gif")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=10)
    args = parser.parse_args()

    tmp = tempfile.mkdtemp(prefix="clipforge_demo_")
    for name, var in (("data", "CLIPFORGE_DATA_DIR"), ("workspace", "CLIPFORGE_WORKSPACE_DIR"), ("exports", "CLIPFORGE_EXPORT_DIR")):
        os.makedirs(os.path.join(tmp, name))
        os.environ[var] = os.path.join(tmp, name)
    os.environ["CLIPFORGE_NO_SCHTASKS"] = "1"
    server = None
    try:
        ffmpeg = shots._ffmpeg()
        clips, _approval = shots.seed(tmp, ffmpeg)
        server, url = shots.start_server()
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            for lang in (("en", "he") if args.lang == "both" else (args.lang,)):
                demo_folder = os.path.join(tmp, "videos", lang, "Highlights")   # קליפ אחד - הרינדור קצר
                os.makedirs(demo_folder)
                shutil.copy2(os.path.join(clips, "match_02.mp4"), os.path.join(demo_folder, "match_02.mp4"))
                video, marks = record(browser, url, (demo_folder, os.path.realpath(tmp)), os.path.join(tmp, "video", lang), lang)
                out = os.path.join(args.out, "demo.gif") if lang == "en" else os.path.join(args.out, "he", "demo.gif")
                to_gif(ffmpeg, video, marks, out, args.width, args.fps)
                print(f"{out}: {os.path.getsize(out) / 1e6:.1f} MB, steps {({k: round(v, 1) for k, v in marks.items()})}")
            browser.close()
    finally:
        if server is not None:
            server.should_exit = True
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
