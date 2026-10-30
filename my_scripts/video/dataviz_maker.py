# Name: 📊 סרטוני נתונים (Data is Beautiful)
# Name (EN): 📊 Data Videos (Data is Beautiful)
# Description: מרנדר פרק בסדרת סרטוני הנתונים (bar chart race ועוד) מתיקיית פרק עם config.yaml, נתונים, אירועים ומוזיקה. תיקיית הקלט היא תיקיית הפרק, או תיקייה של כמה פרקים (כולם ירונדרו). הפלט נשמר ב-workspace לפי כיוון התמונה.
# Description (EN): Renders an episode of the data video series (bar chart race and more) from an episode folder with config.yaml, data, events and music. The input folder is the episode folder, or a folder of several episodes (all are rendered). Output goes to workspace by orientation.
# Concurrency: heavy
# Safety: read-only
#
# עטיפה דקה למנוע src/dataviz (חבילה מבודדת שלא מכירה את ClipForge): כאן רק מה שקשור
# לפרויקט - נתיבי data/ ו-workspace/, ffmpeg_locator, מנעול הרינדור, בדיקת מקום בדיסק,
# שורות PROGRESS:/RESULT: ל-worker.py ומחרוזות דרך utils/i18n.
#
# מצבים: --mode full (ברירת מחדל), test (סרטון קצר: 7 שניות של הקטע הראשי), preview (תצוגה
# מקדימה מהירה: 5 שניות בחצי רזולוציה), stills (פריימים בודדים כ-PNG לבדיקת עיצוב), share (גל 42: תמונה
# ו-GIF מהרגע החזק), shorts (גל 55: הרגעים הדרמטיים כ-Shorts לאורך). כתוביות SRT (captions.enabled או --captions)
# וקריינות (narration.enabled) - אחרי הרינדור; --lang en|both (גל 55) - הגרסה מ-translations.en, או שתי השפות.
# פרסום: publish.enabled ב-config.yaml (או --publish) - אחרי רינדור מלא נוצרים תמונה ממוזערת,
# דף SEO וקובץ <שם>.publish.json במצב pending_approval; --decide approved|rejected --package <נתיב>
# מעדכן את ההחלטה. שום דבר לא מועלה אוטומטית. הקוד מחוץ ל-main() מינימלי בכוונה: תהליכי הרינדור
# (multiprocessing spawn) מריצים מחדש את רמת המודול של הסקריפט הראשי בכל תהליך.

import json
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure") and sys.stderr.encoding != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.shared.export_dir import output_dir as export_output_dir  # noqa: E402 - תיקיית הייצוא, או workspace
from utils.shared.workspace_dir import DATAVIZ, tool_output_dir  # noqa: E402 - קל (רק os), בניגוד לייבואים העצלים למטה
from utils.shared import data_paths

EPISODE_FILE = "config.yaml"


def say(text, **kwargs):
    from utils.i18n import t
    print(t(text, _fix_word_order=False, **kwargs), flush=True)


def find_episodes(input_dir, episode, episodes_root):
    """--episode (שם תחת data/dataviz_episodes או נתיב), אחרת תיקיית הקלט: פרק בודד, או תיקייה
    שכל תת-תיקייה בה עם config.yaml היא פרק."""
    if episode:
        path = episode if os.path.isdir(episode) else os.path.join(episodes_root, episode)
        return [path] if os.path.isfile(os.path.join(path, EPISODE_FILE)) else []
    folder = input_dir or episodes_root
    if os.path.isfile(os.path.join(folder, EPISODE_FILE)):
        return [folder]
    if not os.path.isdir(folder):
        return []
    return [os.path.join(folder, name) for name in sorted(os.listdir(folder))
            if os.path.isfile(os.path.join(folder, name, EPISODE_FILE))]


def orientation(width, height):
    if width > height:
        return "horizontal"
    return "vertical" if height > width else "square"


def output_paths(config, mode, output_base=None):
    """(תיקייה, נתיב סרטון או תיקיית סטילס) - <בסיס>/dataviz/outputs/<כיוון>/<שם>[_test].mp4 (עד 19.10.2026: workspace/<כיוון>/dataviz).
    23.10.2026: בלי output_base (‏--output_dir) - בתיקיית הייצוא שהמשתמש בחר (utils/shared/export_dir.py), או ב-workspace כשלא
    הוגדרה או לא זמינה עכשיו (שורה בלוג). המטמון, ה-staging וההעברה לסטודיו נשארים ב-workspace."""
    video = config["video"]
    parts = ("outputs", orientation(video["width"], video["height"]))
    folder = tool_output_dir(DATAVIZ, *parts, base=output_base) if output_base else export_output_dir(DATAVIZ, *parts)
    name = video.get("output_name") or config["name"]
    if mode == "stills":
        return folder, os.path.join(folder, f"{name}_stills")
    if mode == "share":
        return folder, os.path.join(folder, f"{name}_share")
    suffix = {"test": "_test", "preview": "_preview"}.get(mode, "")
    return folder, os.path.join(folder, f"{name}{suffix}.mp4")


class Progress:
    """PROGRESS:<0-100> לכל הריצה (כמה פרקים = חלקים שווים), רק כשהאחוז השלם משתנה."""

    def __init__(self, parts):
        self.parts = max(parts, 1)
        self.index = 0
        self.last = -1

    def __call__(self, done, total):
        pct = int((self.index + done / max(total, 1)) / self.parts * 100)
        if pct != self.last:
            self.last = pct
            print(f"PROGRESS:{pct}", flush=True)


class QueueSkip(BaseException):
    """הפרק שרץ עכשיו סומן לדילוג במסך - הרינדור שלו נעצר. BaseException כדי שלא ייחשב "רינדור שנכשל"."""


class QueueTracker:
    """גל 44: תור של כמה פרקים - המצב של כל פרק נכתב לקובץ (המסך קורא), ורשימת הפרקים לדילוג נקראת מקובץ
    הבקרה שלידו (המסך כותב). שני קבצים נפרדים - אף אחד לא כותב לקובץ של השני."""

    def __init__(self, path, names):
        import time
        self._time = time.monotonic
        self.path = path
        self.control = path[: -len(".json")] + ".control.json"
        self.episodes = [{"name": n, "state": "pending", "pct": 0} for n in names]
        self._skip = set()
        self.variants = {}   # 20.10.2026: פרק -> גרסה (dataviz/web/variants.py) - המסך כותב בקובץ הבקרה לפני הריצה
        try:
            with open(self.control, "r", encoding="utf-8") as f:
                variants = json.load(f).get("variants") or {}
            self.variants = {str(k): str(v) for k, v in variants.items()} if isinstance(variants, dict) else {}
        except (OSError, ValueError, AttributeError):
            pass
        self._checked = self._written = 0.0
        self.write()

    def write(self):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"episodes": self.episodes}, f, ensure_ascii=False)
            os.replace(tmp, self.path)   # safe: קובץ מצב התור של האפליקציה (data/dataviz_queue.json), לא קובץ של המשתמש
        except OSError:
            pass   # התור הוא תוספת - כשל בכתיבה לא עוצר רינדור

    def skipped(self, name, force=False):
        now = self._time()
        if force or now - self._checked > 0.75:
            self._checked = now
            try:
                with open(self.control, "r", encoding="utf-8") as f:
                    self._skip = set(json.load(f).get("skip") or [])
            except (OSError, ValueError, AttributeError):
                pass
        return name in self._skip

    def state(self, name):
        return next((ep["state"] for ep in self.episodes if ep["name"] == name), "")

    def mark(self, name, state=None, pct=None):
        for ep in self.episodes:
            if ep["name"] == name:
                if state:
                    ep["state"] = state
                if pct is not None:
                    ep["pct"] = int(pct)
        now = self._time()
        if state or now - self._written > 0.5:
            self._written = now
            self.write()


def notify_finished(results, episodes, mode, seconds, queue=None, post=None):
    """20.10.2026: הודעה ל-Discord webhook של עורך הגרפים (אם הוגדר בהגדרות) - הסתיים / נכשל, עם הפרקים והקבצים.
    בלי כתובת - כלום; כשל רשת לא מפיל את הריצה (dataviz/web/notify.py)."""
    try:
        from dataviz.web import notify
        url = notify.get_url()
        if not url:
            return False
        names = [os.path.basename(os.path.normpath(p)) for p in episodes]
        variant = ", ".join(sorted(set(queue.variants.values()))) if queue is not None and queue.variants else ""
        sent = notify.send(url, notify.message(results, names, mode, seconds, variant), post=post)
        say("[INFO] נשלחה התראה ל-Discord." if sent else "[WARNING] ההתראה ל-Discord לא נשלחה.")
        return sent
    except Exception:
        return False


def output_base(args):
    """הבסיס של המטמון (ושל התוצרים כשיש ‏--output_dir) - לא תיקיית הייצוא."""
    return args.output_dir or os.environ.get("CLIPFORGE_WORKSPACE_DIR") or os.path.join(BASE_DIR, "workspace")


def segment_cache_dir(args):
    """מטמון המקטעים של רינדור מלא. 19.10.2026: תחת workspace/.cache/ (קודם workspace/.dataviz_segments - נשאר כמו שהוא,
    לא נקרא ולא נמחק; מטמון, אז בלי מעבר)."""
    return os.path.join(output_base(args), ".cache", "dataviz_segments")


STATS_FILE = data_paths.DATAVIZ_RENDER_STATS
MAX_STATS = 50


def record_render_time(mode, rendered, workers, seconds):
    """גל 54: כמה זמן רינדור באמת לקח (פריימים שצוירו, פיקסלים, תהליכים) - האומדן במסך לומד מזה."""
    from utils.data_dir import DATA_DIR
    path = data_paths.path(STATS_FILE, DATA_DIR)   # אחרי ההעברה: data/dataviz/
    try:
        with open(path, "r", encoding="utf-8") as f:
            runs = json.load(f).get("runs", [])
    except (OSError, ValueError, AttributeError):
        runs = []
    runs = [r for r in runs if isinstance(r, dict)] if isinstance(runs, list) else []   # נ8: {"runs": null} הפך רינדור שהצליח ל"נכשל"
    width, height = rendered["size"]
    runs.append({"mode": mode, "frames": rendered["frames"], "rendered_frames": rendered["frames"] - rendered.get("cached_frames", 0),
                 "pixels": width * height, "workers": workers, "seconds": round(seconds, 2), "encoder": rendered.get("encoder", "")})
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"runs": runs[-MAX_STATS:]}, f)
        os.replace(tmp, path)   # safe: קובץ זמני הרינדור של האפליקציה (data/dataviz_render_stats.json), לא קובץ של המשתמש
    except OSError:
        pass   # הסטטיסטיקה היא תוספת - כשל בכתיבה לא עוצר רינדור


def render_shorts(episode, plan, chart, folder, target, args, progress, results, name):
    """גל 55: הרגעים הדרמטיים של הפרק כ-Shorts לאורך - <שם>_shorts_1.mp4 ואילך, מהחזק לחלש."""
    from dataviz.render import default_workers, render_video
    from dataviz.shorts import build_shorts
    from utils.disk_space import estimate_required_bytes_for_duration, has_enough_disk_space
    from utils.ffmpeg_locator import get_ffmpeg_exe
    from utils.render_lock import render_lock_if_needed

    shorts = build_shorts(episode, plan)
    if not shorts:
        say("[WARNING] לא נמצאו רגעים דרמטיים ב-{name} - בלי Shorts", name=name)
        return
    fps = int(episode.config["video"]["fps"])
    total = sum(len(short) for short in shorts)
    if not has_enough_disk_space(folder, estimate_required_bytes_for_duration(total / fps)):
        say("[ERROR] שטח פנוי לא מספיק ב-{folder} - מדלג על {name}.", folder=folder, name=name)
        results["errors"] += 1
        return
    os.makedirs(folder, exist_ok=True)
    base = os.path.splitext(target)[0]
    done = 0
    with render_lock_if_needed(on_wait=lambda _s: say("⏳ ממתין לסיום רינדור אחר שרץ כרגע (GUI/דפדפן/בוט)...")):
        for k, short in enumerate(shorts, start=1):
            path = f"{base}_{k}.mp4"
            started = time.time()
            try:
                render_video(episode, short, path, ffmpeg=get_ffmpeg_exe(), workers=args.workers or default_workers(),
                             progress=lambda d, _t, offset=done: progress(offset + d, total), chart=chart)
            except QueueSkip:
                _drop_partial(path, started)
                raise
            except Exception as e:
                _drop_partial(path, started)
                say("[ERROR] ה-Short {k} של {name} נכשל: {error}", k=k, name=name, error=e)
                results["errors"] += 1
                continue
            done += len(short)
            say("[APPROVED] נוצר: {path}", path=path)
            results["files_created"] += 1


def _drop_partial(path, started):
    """נ7 / ק7: Short או סרטון שדולג או נכשל באמצע - הקובץ החלקי שהניסיון הזה כתב נמחק. קובץ שלא נגעו בו בניסיון הזה (ffmpeg לא הספיק
    להתחיל) נשאר כמו שהוא."""
    try:
        if os.path.isfile(path) and os.path.getmtime(path) >= started - 1:
            os.remove(path)   # safe: הסרטון החלקי שהניסיון הזה התחיל לכתוב (נבדק לפי זמן השינוי)
    except OSError:
        pass


def render_episode(path, mode, args, progress, results, queue=None, lang=""):
    from dataviz import ConfigError, build_plan, load_episode, render_stills, render_video
    from dataviz.config import preview_config
    from dataviz.render import default_workers
    from dataviz.web.episodes import load_overrides_for_path
    from utils.disk_space import estimate_required_bytes_for_duration, has_enough_disk_space
    from utils.ffmpeg_locator import get_ffmpeg_exe
    from utils.render_lock import render_lock_if_needed

    name = os.path.basename(os.path.normpath(path))
    if queue is not None:   # גל 44: אחוז לכל פרק בתור, ועצירה כשהפרק סומן לדילוג
        overall = progress

        def progress(done, total):
            overall(done, total)
            queue.mark(name, pct=done * 100 / max(total, 1))
            if queue.skipped(name):
                raise QueueSkip()
    variant = queue.variants.get(name, "") if queue is not None else ""
    try:
        if variant:   # 20.10.2026: גרסה של הפרק - השכבה שלה מעל קובץ השינויים, ושם קובץ פלט משלה
            from dataviz.web.variants import effective_overrides
            say("[INFO] גרסה: {variant}", variant=variant)
            data_dir = os.path.dirname(os.path.dirname(os.path.normpath(path)))   # data/dataviz_episodes/<פרק> -> data/
            episode = load_episode(path, effective_overrides(data_dir, name, variant))
        else:
            episode = load_episode(path, load_overrides_for_path(path))   # שינויים מהדפדפן (data/dataviz_overrides) מעל config.yaml
    except ConfigError as e:
        say("[ERROR] הגדרות לא תקינות בפרק {name}:", name=name)
        for error in e.errors:
            print(f"  - {error}", flush=True)
        results["errors"] += 1
        return
    except (OSError, ValueError, KeyError) as e:
        say("[ERROR] קריאת הנתונים של {name} נכשלה: {error}", name=name, error=e)
        results["errors"] += 1
        return

    if lang:   # גל 55: הגרסה בשפה אחרת - הטקסטים מ-translations.<שפה>, בשם קובץ משלה
        from dataviz.episode import build_episode
        from dataviz.languages import apply_language
        try:
            episode = build_episode(apply_language(episode.config, lang))
        except ConfigError as e:
            say("[ERROR] הגרסה ב-{lang} של {name}:", lang=lang, name=name)
            for error in e.errors:
                print(f"  - {error}", flush=True)
            results["errors"] += 1
            return
        except (OSError, ValueError, KeyError) as e:
            say("[ERROR] הגרסה ב-{lang} של {name}: {error}", lang=lang, name=name, error=e)
            results["errors"] += 1
            return

    if mode == "shorts" and not getattr(args, "target", ""):
        from dataviz.targets import apply_target
        episode.config = apply_target(episode.config, "shorts")   # גל 55: Shorts תמיד לאורך
    if getattr(args, "target", ""):
        from dataviz.targets import apply_target
        episode.config = apply_target(episode.config, args.target)   # גל 41: Shorts/TikTok - לאורך, בשם קובץ משלו
    if mode == "preview":
        episode.config = preview_config(episode.config)   # חצי רזולוציה - אותה פריסה, פחות פיקסלים
    config = episode.config
    chart = args.chart or config["chart"]
    plan = build_plan(episode, mode)
    span = getattr(args, "range", "")
    if span and mode in ("full", "test"):   # 27.10.2026: רינדור טווח - רק הקטע הראשי בין שני תאריכים, לבדיקה
        from dataviz.plan import clip_range
        start, _sep, end = span.partition(",")
        try:
            plan = clip_range(plan, episode, start.strip(), (end or start).strip())
        except ValueError as e:
            say("[ERROR] {error}", error=e)
            results["errors"] += 1
            return
    fps = int(config["video"]["fps"])
    say("[INFO] {name}: {frames} פריימים, {seconds} שניות ({chart}, מצב {mode})",
        name=name, frames=len(plan), seconds=round(len(plan) / fps, 1), chart=chart, mode=mode)
    folder, target = output_paths(config, mode, args.output_dir or None)
    if span and mode in ("full", "test"):
        target = target[:-4] + "_range.mp4"   # קובץ משלו - לא דורס את הסרטון המלא
    # 27.10.2026: video.priority - בעדיפות נמוכה (ברירת המחדל) תהליכי הציור ו-ffmpeg יורשים אותה, והמחשב נשאר זמין
    from dataviz.render import lower_priority
    if lower_priority(str(config["video"].get("priority", "low"))):
        say("[INFO] רינדור בעדיפות נמוכה - המחשב נשאר זמין בזמן הרינדור")

    if mode == "stills":
        try:
            paths = render_stills(episode, plan, target, chart=chart, progress=progress)
        except Exception as e:  # תרשים שנכשל בציור - שאר הפרקים ממשיכים
            say("[ERROR] הרינדור של {name} נכשל: {error}", name=name, error=e)
            results["errors"] += 1
            return
        say("[APPROVED] {n} סטילס נשמרו ב-{folder}", n=len(paths), folder=target)
        results["files_created"] += len(paths)
        return
    if mode == "share":   # גל 42: תמונה ו-GIF מהרגע החזק - בלי ffmpeg
        from dataviz.share import render_share
        try:
            shared = render_share(episode, plan, target, chart=chart, progress=progress)
        except Exception as e:
            say("[ERROR] הרינדור של {name} נכשל: {error}", name=name, error=e)
            results["errors"] += 1
            return
        say("[APPROVED] תמונה ו-GIF לשיתוף נשמרו ב-{folder}", folder=target)
        results["files_created"] += 2
        results["share_frame"] = shared["frame"]
        return
    if mode == "shorts":
        render_shorts(episode, plan, chart, folder, target, args, progress, results, name)
        return

    duration = len(plan) / fps
    if not has_enough_disk_space(folder, estimate_required_bytes_for_duration(duration)):
        say("[ERROR] שטח פנוי לא מספיק ב-{folder} - מדלג על {name}.", folder=folder, name=name)
        results["errors"] += 1
        return
    os.makedirs(folder, exist_ok=True)

    def _log_waiting(_seconds_waited):
        say("⏳ ממתין לסיום רינדור אחר שרץ כרגע (GUI/דפדפן/בוט)...")

    # render_lock_if_needed - כמו video_editor.py/timelapse_maker.py: מגן גם כשמריצים מטרמינל
    import time
    workers = args.workers or default_workers()
    # גל 54: סרטון מלא - מקטעים שכבר רונדרו (אותם נתונים, רק הפתיח או הסיום השתנו) נלקחים מהמטמון
    segment_cache = segment_cache_dir(args) if mode == "full" else ""
    with render_lock_if_needed(on_wait=_log_waiting):
        started_at = time.time()
        try:
            started = time.monotonic()
            rendered = render_video(episode, plan, target, ffmpeg=get_ffmpeg_exe(), workers=workers,
                                    progress=progress, chart=chart, segment_cache=segment_cache)
            record_render_time(mode, rendered, workers, time.monotonic() - started)
            if rendered.get("cached_frames"):
                say("[INFO] {n} פריימים נלקחו מהמטמון (לא השתנו)", n=rendered["cached_frames"])
            if rendered.get("encoder") == "nvenc":
                say("[INFO] קודד בכרטיס המסך (NVENC)")
        except QueueSkip:
            # ק7: רק מה שהריצה הזו כתבה. במצב מלא (מטמון המקטעים) הקובץ נכתב רק בחיבור שבסוף - בזמן הדילוג מה שיש שם הוא
            # הרינדור הקודם, השלם, וקודם הוא נמחק
            _drop_partial(target, started_at)
            raise
        except Exception as e:  # ffmpeg/תהליך רינדור שנכשל - שאר הפרקים ממשיכים
            say("[ERROR] הרינדור של {name} נכשל: {error}", name=name, error=e)
            results["errors"] += 1
            return
    say("[APPROVED] נוצר: {path}", path=target)
    results["files_created"] += 1
    add_captions_and_narration(target, config, plan, mode, args, results,
                               event_dates={label: date for date, label, _di in episode.events})
    publish = dict(config.get("publish") or {})
    if mode == "full" and (publish.get("enabled") or args.publish) and not args.no_publish and not span:   # טווח - בלי פרסום
        run_publish(target, config, results)
    results["seconds"] = round(results.get("seconds", 0) + duration, 1)


def add_captions_and_narration(video_path, config, plan, mode, args, results, event_dates=None):
    """גל 42-43: קריינות לאירועים (מוקלטת או בקול של Windows), אינטרו / אאוטרו מקליפ, ואז <שם>.srt ליד הסרטון
    (מוזז באורך האינטרו). בסרטון מלא ובבדיקה. כשל באחד השלבים לא מפיל את הסרטון."""
    from dataviz.captions import episode_spans, write_srt

    narration = config.get("narration") or {}
    if narration.get("enabled") and mode in ("full", "test"):
        from dataviz.narration import narrate_video
        from utils.ffmpeg_locator import get_ffmpeg_exe
        try:
            count = narrate_video(video_path, config, episode_spans(config, plan, settings=narration), ffmpeg=get_ffmpeg_exe(),
                                  duration=len(plan) / float(config["video"]["fps"]), event_dates=event_dates)
            say("[INFO] קריינות: {n} אירועים הוקראו", n=count)
        except Exception as e:
            say("[WARNING] הקריינות נכשלה (הסרטון עצמו נוצר): {error}", error=e)
    if (narration.get("track") or "") and mode in ("full", "test"):   # 27.10.2026: הקלטה רציפה מהעורך
        from dataviz.narration import narrate_track
        from utils.ffmpeg_locator import get_ffmpeg_exe
        try:
            if narrate_track(video_path, config, ffmpeg=get_ffmpeg_exe(), duration=len(plan) / float(config["video"]["fps"])):
                say("[INFO] נוספה ההקלטה הרציפה")
        except Exception as e:
            say("[WARNING] ההקלטה הרציפה לא נוספה (הסרטון עצמו נוצר): {error}", error=e)
    offset = 0.0
    bumpers = config.get("bumpers") or {}
    if (bumpers.get("intro") or bumpers.get("outro")) and mode in ("full", "test"):
        from dataviz.bumpers import add_bumpers
        from utils.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
        try:
            offset = add_bumpers(video_path, config, ffmpeg=get_ffmpeg_exe(), ffprobe=get_ffprobe_exe())
            say("[INFO] נוסף אינטרו / אאוטרו מקליפ")
        except Exception as e:
            say("[WARNING] האינטרו / האאוטרו לא נוספו (הסרטון עצמו נוצר): {error}", error=e)
    if mode == "full" and (config.get("publish") or {}).get("chapters", True):
        from dataviz.captions import write_chapters, youtube_chapters
        try:   # ב29: כשל כאן (קובץ נעול, דיסק מלא) עצר את כל התור - בלי RESULT, והפרק נשאר "רץ"
            chapters = youtube_chapters(config, plan, offset)   # גל 55: פרקים ביוטיוב - נכנסים לתיאור בחבילת הפרסום
            if chapters:
                say("[INFO] {n} פרקים ליוטיוב: {path}", n=len(chapters), path=write_chapters(video_path, chapters))
        except Exception as e:
            say("[WARNING] הפרקים ליוטיוב לא נכתבו (הסרטון עצמו נוצר): {error}", error=e)
    if (config.get("captions") or {}).get("enabled") or getattr(args, "captions", False):
        from dataviz.bumpers import shift_spans
        try:
            path = write_srt(video_path, shift_spans(episode_spans(config, plan), offset))
            say("[INFO] כתוביות: {path}", path=path)
            results["files_created"] += 1
        except Exception as e:
            say("[WARNING] הכתוביות לא נכתבו (הסרטון עצמו נוצר): {error}", error=e)


def run_publish(video_path, config, results):
    """כותרת/SEO + תמונה ממוזערת + קובץ אישור ליד הסרטון (utils/dataviz_publish). כשל כאן לא מפיל את הרינדור."""
    from dataviz.web.publish import prepare_publish
    from utils.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe

    try:
        package = prepare_publish(video_path, config, ffmpeg=get_ffmpeg_exe(), ffprobe=get_ffprobe_exe())
    except Exception as e:
        say("[WARNING] שלבי הפרסום נכשלו (הסרטון עצמו נוצר): {error}", error=e)
        return
    failed = {name: state for name, state in package["steps"].items() if state.startswith("failed")}
    for name, state in failed.items():
        say("[WARNING] שלב הפרסום {step} נכשל: {state}", step=name, state=state)
    say("[INFO] כותרת: {title}", title=package["metadata"]["title"])
    say("[INFO] סטטוס פרסום: {status} ({path})", status=package["status"], path=os.path.splitext(video_path)[0] + ".publish.json")
    results["published_packages"] = results.get("published_packages", 0) + 1


def decide(package_path, decision):
    from dataviz.web.publish import set_decision

    try:
        package = set_decision(package_path, decision)
    except (OSError, ValueError) as e:
        say("[ERROR] עדכון ההחלטה נכשל: {error}", error=e)
        print("RESULT: " + json.dumps({"decision": decision, "errors": 1}, ensure_ascii=False), flush=True)
        sys.exit(1)
    say("[SUCCESS] {video}: {status}", video=package["video"], status=package["status"])
    print("RESULT: " + json.dumps({"decision": decision, "errors": 0}, ensure_ascii=False), flush=True)


def refresh_episode_data(data_dir, name, args, results):
    """גל 52: מוריד מחדש את המקורות מכתובת של הפרק. False = לדלג על הרינדור (--only-if-changed ושום דבר לא השתנה)."""
    from dataviz.web.episodes import EpisodeError
    from dataviz.web.remote import refresh_sources
    try:
        refreshed = refresh_sources(data_dir, name)
    except EpisodeError as e:
        say("[WARNING] רענון הנתונים של {name} נכשל: {error}", name=name, error=e)
        return True
    for source in refreshed["sources"]:
        if source.get("error"):
            say("[WARNING] {url}: {error}", url=source["url"], error=source["error"])
        else:
            say("[INFO] {url}: {state}", url=source["url"], state="השתנה" if source["changed"] else "לא השתנה")
    if args.only_if_changed and refreshed["sources"] and not refreshed["changed"]:
        say("[INFO] הנתונים של {name} לא השתנו מאז הפעם הקודמת - בלי רינדור", name=name)
        results["skipped"] = results.get("skipped", 0) + 1
        return False
    return True


def main():
    import argparse

    from dataviz.charts import CHART_MODULES
    from utils.data_dir import DATA_DIR

    parser = argparse.ArgumentParser(description="סרטוני נתונים (bar chart race ועוד) מתיקיית פרק עם config.yaml")
    parser.add_argument("--input_dir", type=str, default="", help="תיקיית פרק, או תיקייה של כמה פרקים")
    parser.add_argument("--episode", type=str, default="", help="שם פרק תחת data/dataviz_episodes (גובר על --input_dir)")
    parser.add_argument("--mode", choices=("full", "test", "stills", "preview", "share", "shorts"), default="full")
    parser.add_argument("--lang", choices=("en", "both"), default="", help="גל 55: גרסה באנגלית (translations.en), או שתי השפות")
    parser.add_argument("--captions", action="store_true", help="כתוביות SRT לאירועים ולשיאים ליד הסרטון (גם אם captions כבוי בהגדרות)")
    parser.add_argument("--publish", action="store_true", help="הכן כותרת/SEO/תמונה ממוזערת/קובץ אישור גם אם publish כבוי בהגדרות")
    parser.add_argument("--no-publish", dest="no_publish", action="store_true", help="דלג על שלבי הפרסום גם אם publish.enabled")
    parser.add_argument("--decide", choices=("approved", "rejected"), default=None, help="עדכון החלטת אישור לחבילת פרסום (עם --package)")
    parser.add_argument("--package", type=str, default="", help="נתיב ל-<שם>.publish.json או לסרטון (עם --decide)")
    parser.add_argument("--chart", choices=tuple(CHART_MODULES), default=None, help="סוג תרשים במקום זה שבהגדרות הפרק")
    parser.add_argument("--workers", type=int, default=0, help="תהליכי רינדור (ברירת מחדל: לפי מספר הליבות)")
    parser.add_argument("--output_dir", type=str, default="", help="תיקיית בסיס לפלט במקום workspace/ (לבדיקות)")
    parser.add_argument("--target", choices=("youtube", "shorts", "tiktok"), default="", help="יעד: youtube כמו בהגדרות, shorts/tiktok לאורך 1080x1920")
    parser.add_argument("--episodes", type=str, default="", help="כמה פרקים בריצה אחת (שמות מופרדים בפסיק, לפי הסדר)")
    parser.add_argument("--queue-file", dest="queue_file", type=str, default="", help="קובץ מצב התור (גל 44): התקדמות לכל פרק, ודילוג מקובץ הבקרה שלידו")
    parser.add_argument("--refresh-data", dest="refresh_data", action="store_true", help="גל 52: להוריד מחדש מקורות מכתובת (URL / Google Sheets) לפני הרינדור")
    parser.add_argument("--only-if-changed", dest="only_if_changed", action="store_true", help="עם --refresh-data: לדלג על פרק שהנתונים שלו לא השתנו")
    parser.add_argument("--range", type=str, default="", help="27.10.2026: רק הקטע הראשי בין שני תאריכים - START,END (YYYY-MM-DD), לקובץ <שם>_range.mp4")
    args, _unknown = parser.parse_known_args()

    if args.decide:
        decide(args.package, args.decide)
        return

    # 27.10.2026: תיקיית הדגלים (images.flags) - המנוע קורא אותה ממשתנה סביבה, ותהליכי הציור יורשים אותו
    from dataviz.render import FLAGS_DIR_ENV
    os.environ.setdefault(FLAGS_DIR_ENV, os.path.join(data_paths.dataviz_root(DATA_DIR), data_paths.DATAVIZ_FLAGS))

    episodes_root = data_paths.path(data_paths.DATAVIZ_EPISODES)
    if args.episodes:   # גל 41: תור של כמה פרקים בריצה אחת
        episodes = [p for name in args.episodes.split(",") if name.strip() for p in find_episodes("", name.strip(), episodes_root)]
    else:
        episodes = find_episodes(args.input_dir, args.episode, episodes_root)
    if not episodes:
        say("[ERROR] לא נמצא אף פרק (תיקייה עם config.yaml) ב-{folder}.", folder=args.episode or args.input_dir or episodes_root)
        print("RESULT: " + json.dumps({"episodes": 0, "files_created": 0, "errors": 1}, ensure_ascii=False), flush=True)
        sys.exit(1)
    if len(episodes) > 1:
        say("[INFO] נמצאו {n} פרקים: {names}", n=len(episodes), names=", ".join(os.path.basename(p) for p in episodes))

    results = {"episodes": len(episodes), "files_created": 0, "errors": 0}
    started = time.monotonic()
    langs = ["", "en"] if args.lang == "both" else [args.lang]
    progress = Progress(len(episodes) * len(langs))
    queue = QueueTracker(args.queue_file, [os.path.basename(os.path.normpath(p)) for p in episodes]) if args.queue_file else None
    for index, path in enumerate(episodes):
        progress.index = index * len(langs)
        name = os.path.basename(os.path.normpath(path))
        if queue is not None and queue.skipped(name, force=True):
            queue.mark(name, "skipped")
            say("[INFO] {name} דולג (הוסר מהתור)", name=name)
            results["skipped"] = results.get("skipped", 0) + 1
            continue
        if args.refresh_data and not refresh_episode_data(data_paths.dataviz_root(DATA_DIR), name, args, results):
            if queue is not None:
                queue.mark(name, "skipped")   # ב28: קודם נשאר "pending" לתמיד במסך
            continue
        if queue is not None:
            queue.mark(name, "running", 0)
        errors_before = results["errors"]
        try:
            for k, lang in enumerate(langs):
                progress.index = index * len(langs) + k
                render_episode(path, args.mode, args, progress, results, queue=queue, lang=lang)
        except QueueSkip:
            queue.mark(name, "skipped")
            say("[INFO] {name} נעצר והוסר מהתור - ממשיכים לפרק הבא", name=name)
            results["skipped"] = results.get("skipped", 0) + 1
            continue
        except Exception as e:   # ב29: שגיאה שלא נתפסה בפרק אחד - הפרק נכשל, שאר התור ממשיך וה-RESULT יוצא
            say("[ERROR] הרינדור של {name} נכשל: {error}", name=name, error=e)
            results["errors"] += 1
        if queue is not None:
            queue.mark(name, "failed" if results["errors"] > errors_before else "done", 100)
    progress.index = progress.parts - 1
    progress(1, 1)

    say("[SUCCESS] העיבוד הסתיים.")
    print("RESULT: " + json.dumps(results, ensure_ascii=False), flush=True)
    notify_finished(results, episodes, args.mode, time.monotonic() - started, queue)
    if results["errors"] and not results["files_created"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
