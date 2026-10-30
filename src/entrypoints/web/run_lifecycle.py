# entrypoints/web/run_lifecycle.py
#
# 24.10.2026 (פיצול web_app.py, קבוצה 3): מחזור החיים של ריצה - התחלה (/api/run, ריצה לכל יעד), הסוף (היסטוריה, webhook,
# גיבוי אוטומטי, מצב לילה, מרכז ההתראות) ולולאת המשימות המתוזמנות. עבר מ-web_app.py בלי שינוי התנהגות. web_app מייבא את
# השמות האלה בחזרה (web_app.<שם> נשאר), וה-routes ממשיכים לקרוא W.<שם>. המצב (_current_run, _night_shutdown_waiting,
# _finished_queue...) נשאר מוגדר ב-web_app ונקרא ונכתב דרך W. - טסטים מחליפים את web_app.<שם> (_night_shutdown_waiting,
# worker...), והקוד כאן צריך לראות את ההחלפה (tests/web/test_web_app_split.py בודק את זה).
import datetime
import os
import threading
import time

from entrypoints import web_app as W
from utils.video.video_editor_profiles import record_profile_used as record_video_editor_profile_used


def _export_fallback_note(script_basename=None):
    """שורה ללוג כשתיקיית הייצוא של הריצה (של הכלי, או הכללית) לא זמינה עכשיו - התוצרים נשמרים ב-workspace. None כשהכל בסדר."""
    tool = W._SCRIPT_EXPORT_TOOLS.get(script_basename or "")
    return W.export_dir.fallback_note(W.export_dir.resolve_tool(tool) if tool else W.export_dir.resolve())


def _on_task_finished(outcome, script_name=None):
    # נקרא מ-thread של worker.py, לא מה-event loop של FastAPI - בדיוק כמו
    # ui/dashboard.py, שום עדכון UI/state ישיר כאן, רק דחיפה לתור thread-safe.
    # script_name: ריצה משורשרת (פרסום Rocket אחרי עורך-העל) - _current_run עוד מחזיק את הריצה שלפניה
    name = script_name or W._current_run.get("script_name")
    started_at = None if script_name else W._current_run.get("started_at")
    if not outcome.get("removed_from_queue"):   # משימה שהוסרה מהתור לא רצה - לא היסטוריה, לא webhook ולא התראה
        note = W._export_fallback_note(name)
        if note:
            W.worker.log_queue.put((note + "\n", "red"))   # גם בסוף הריצה, לא רק בתחילתה
        W._record_run_end(name, started_at, outcome)
        W._notify_run_finished(name, outcome, note, started_at)
    W._finish_waiting_night_shutdown(outcome)   # גם כשהמשימה האחרונה בתור הוסרה ממנו
    W._finished_queue.put(outcome)


def _record_run_end(script_name, started_at, outcome):
    """23.10.2026: היסטוריית הריצות, ה-webhook, הגיבוי האוטומטי ומצב לילה - כאן, בסוף הריצה עצמה, ולא בלולאת ה-/ws:
    היא רצה רק כשטאב מחובר (טאב סגור = כלום מזה לא קרה). כיבוי שהופעל נכנס ל-outcome (shutdown_seconds), וה-/ws מציג
    לדפדפן את הספירה לאחור עם ביטול, כמו קודם. כמו קודם, ריצה בלי התחלה ידועה (פרסום משורשר) לא נרשמת."""
    if not (script_name and started_at):
        return
    success = outcome.get("returncode") == 0
    finished_at = time.time()
    duration = finished_at - started_at
    try:
        W.job_history.record_job(
            script_name, "success" if success else "failed",
            datetime.datetime.fromtimestamp(started_at).isoformat(timespec="seconds"),
            datetime.datetime.fromtimestamp(finished_at).isoformat(timespec="seconds"),
            round(duration, 1), result=outcome.get("result"),
        )
    except Exception as e:
        W.worker.log_queue.put((f"⚠️ שמירת הריצה בהיסטוריה נכשלה: {e}\n", "red"))
    try:
        if W._run_completion_side_effects(script_name, success, duration, outcome.get("result"), last_in_queue=not W._work_still_queued()):
            outcome["shutdown_seconds"] = W.SHUTDOWN_COUNTDOWN_SECONDS
    except Exception as e:
        W.worker.log_queue.put((f"⚠️ פעולות סוף הריצה נכשלו: {e}\n", "red"))


def _on_publisher_finished(outcome):
    W._on_task_finished(outcome, os.path.basename(W.PUBLISHER_SCRIPT_PATH))


def _notify_run_finished(script_name, outcome, export_note, started_at):
    """מרכז ההתראות: הריצה נרשמת כאן, בסופה - לא בלולאת ה-/ws, שרצה רק כשטאב מחובר. התראה שלא נשמרה לא עוצרת סיום ריצה."""
    name = script_name or "ריצה"
    success = (outcome or {}).get("returncode") == 0
    stopped = not success and W._current_run.get("stop_requested")
    title, level, target = (f"✅ הסתיים: {name}", "ok", "outputs") if success else (
        (f"⏹️ נעצר: {name}", "info", "scripts") if stopped else (f"❌ נכשל: {name}", "bad", "scripts"))
    details = []
    if started_at:
        seconds = time.time() - started_at
        details.append(f"משך: {seconds:.0f} שניות" if seconds < 60 else f"משך: {seconds / 60:.1f} דקות")
    summary = W.job_history.format_result_summary((outcome or {}).get("result"))
    if summary:
        details.append(summary)
    try:
        W.notification_log.add("run", title, body=" · ".join(details), level=level, target=target)
        if export_note:
            W.notification_log.add("export", export_note, level="warn", target="globalsettings")
    except Exception as e:
        W.worker.log_queue.put((f"⚠️ שמירת ההתראה נכשלה: {e}\n", "red"))


def _mirror_export_dirs(dest_dir):
    """מגבה כל תיקיית-אוריינטציה שכבר קיימת בפועל בנפרד - לא כל אחת מהשלוש
    מובטחת להיווצר אצל כל משתמש (למשל square/ נוצרת רק אם enable_square_export
    מופעל), אז מדלגים בשקט על מי שלא קיימת במקום להעביר אותה ל-mirror_folder
    (שהייתה מחזירה שגיאת "תיקייה לא קיימת" בלי סיבה אמיתית).
    23.10.2026: גם מתיקיות הייצוא שבחר המשתמש (הכללית ושל כל כלי) - שם נכתבים עכשיו התוצרים החדשים, ל-<יעד>/<כלי>."""
    sources = [(os.path.basename(path), path) for path in W.WEB_APP_EXPORT_DIRS] + W.export_dir.configured_folders()
    for name, source in sources:
        if os.path.isdir(source):
            W.mirror_folder(source, os.path.join(dest_dir, name))


def _work_still_queued():
    """עוד משימה בתור, או תהליך שרץ במסלול כלשהו. התהליך של הריצה שהסתיימה כבר יצא מ-active_processes לפני ה-callback
    (worker.add_script_task, ה-finally של run_proc), כך שמה שנשאר שם הוא ריצה אחרת."""
    return W.worker.pending_count() > 0 or bool(W.worker.active_processes)


def _finish_waiting_night_shutdown(outcome):
    """23.10.2026: הכיבוי שחיכה לסוף התור - בסוף המשימה האחרונה, גם אם היא עצמה לא נרשמת (פרסום משורשר) או נכשלה,
    ורק אם מצב לילה עדיין פעיל. עם אותה ספירה לאחור עם ביטול (shutdown_seconds ל-/ws)."""
    if outcome.get("shutdown_seconds"):
        W._night_shutdown_waiting = False
        return
    if not W._night_shutdown_waiting or W._work_still_queued():
        return
    W._night_shutdown_waiting = False
    if W._load_raw_config().get("night_active"):
        os.system(f"shutdown /s /t {W.SHUTDOWN_COUNTDOWN_SECONDS}")
        outcome["shutdown_seconds"] = W.SHUTDOWN_COUNTDOWN_SECONDS


def _run_completion_side_effects(script_name, success, duration, result, last_in_queue=True):
    """webhook/גיבוי אוטומטי/כיבוי לילה בסיום ריצה - זהה ל-ui/dashboard.py's
    _record_and_notify/_run_backup_mirror/_start_shutdown_countdown, רק
    שההרצה כאן הופעלה מהדפדפן. קורא config.json טרי בכל סיום (לא עותק
    בזיכרון), כדי לשקף הגדרה ששונתה מאז תחילת הריצה. מחזיר True אם כיבוי
    אוטומטי הופעל, כדי שהקוראת תוכל להודיע לדפדפן (אפשרות לבטל)."""
    config = W._load_raw_config()

    webhook = str(config.get("webhook", "")).strip()
    if webhook:
        icon = "✅" if success else "❌"
        duration_str = f"{duration:.0f} שניות" if duration < 60 else f"{duration / 60:.1f} דקות"
        status_text = "הסתיים בהצלחה" if success else "נכשל"
        message = f"{icon} **{script_name}** {status_text} (משך ריצה: {duration_str})"
        summary = W.job_history.format_result_summary(result) if result else ""
        if summary:
            message += f"\n{summary}"
        W.send_webhook_notification(webhook, message)

    if not success:
        return False

    nas_folder = str(config.get("nas_folder", "")).strip()
    if config.get("auto_backup_active") and nas_folder:
        threading.Thread(target=W._mirror_export_dirs, args=(nas_folder,), daemon=True).start()

    if config.get("night_active"):
        if not last_in_queue:
            # 23.10.2026: עכשיו זה קורה גם בלי טאב פתוח (אין מי שיבטל) - כיבוי באמצע התור היה הורג את שאר המשימות
            W._night_shutdown_waiting = True
            W.worker.log_queue.put(("🌙 מצב לילה: יש עוד משימות בתור - הכיבוי יחכה לסוף\n", None))
            return False
        os.system(f"shutdown /s /t {W.SHUTDOWN_COUNTDOWN_SECONDS}")
        return True

    return False


def _start_script_run(script_path, folder, payload, client_host):
    """הליבה של /api/run - משותפת גם ל"הרץ שוב" מהיסטוריית הריצות (גל 8, item 92).
    גל 12: ערכת המותג המקושרת מוחלת כאן (הגרסה העדכנית שלה, לא מה שנשמר במתכון),
    ו"מתכון × יעדים" נפרש לריצה אחת לכל יעד - כולן נכנסות לתור בבת-אחת."""
    script_basename = os.path.basename(script_path)
    if script_basename == "video_editor.py" and not payload.get("concat_mode"):
        payload = W._effective_editor_payload(payload)
        target_runs = W.editor_model.expand_targets(payload)
        if target_runs[0][0] is not None:
            return W._start_target_runs(script_path, folder, target_runs, client_host)
    return W._start_single_run(script_path, folder, payload, client_host)


def _start_target_runs(script_path, folder, target_runs, client_host):
    """ריצה לכל יעד, ברצף בתור. פעולות סוף-ריצה (צליל/פתיחת תיקייה/שינה) רק אחרי
    האחרון; "ואז פרסם" (Rocket Shorts) רק ליעד ה-Shorts אם נבחר, אחרת לאנכי הראשון."""
    target_ids = [target_id for target_id, _ in target_runs]
    publish_target = "shorts" if "shorts" in target_ids else next(
        (t for t in target_ids if W.editor_model.TARGET_PRESETS[t]["fields"].get("vertical")), None)
    run_ids = []
    for index, (target_id, run_payload) in enumerate(target_runs):
        is_last = index == len(target_runs) - 1
        if not is_last:
            run_payload["finish_actions"] = {}
        if target_id != publish_target:
            run_payload["publish_after"] = False
        run_payload["run_label"] = W.editor_model.TARGET_PRESETS[target_id]["label"]
        response = W._start_single_run(script_path, folder, run_payload, client_host, record_profile_use=is_last)
        if isinstance(response, W.JSONResponse):
            return response
        run_ids.append(response.get("run_id"))
    return {"ok": True, "run_id": run_ids[0] if run_ids else None, "run_ids": run_ids, "targets": target_ids}


def _start_single_run(script_path, folder, payload, client_host, record_profile_use=True):
    script_basename = os.path.basename(script_path)
    batch_overrides_path = None
    layers_path = None
    control_path = None
    run_id = None
    if script_basename == "video_editor.py":
        layers_path = W._write_layers_file(payload)
        # item: מצב "🔗 איחוד קטעים" - חסימה מפורשת במקום נפילה שקטה לעריכה
        # רגילה של כל התיקייה (זה בדיוק מה שהמשתמש *לא* התכוון אליו כשבחר איחוד).
        concat_files = payload.get("concat_files")
        if payload.get("concat_mode") and not (isinstance(concat_files, list) and len(concat_files) >= 2):
            return W.JSONResponse({"error": "מצב איחוד קטעים דורש לפחות 2 קבצים מסומנים בתור העיבוד (רענן את התור וסמן את הקטעים לפי הסדר)."}, status_code=400)
        # גל 12: עריכות-קליפ (חיתוך/טווחים/שכבות לקובץ אחד) גוברות על דריסות-התור
        overrides = W.sanitize_batch_overrides(W.editor_model.merge_clip_edits_into_overrides(
            payload.get("batch_overrides") if isinstance(payload.get("batch_overrides"), dict) else {}, payload.get("clip_edits")))
        payload = {**payload, "batch_overrides": overrides}
        if overrides:
            batch_overrides_path = W._write_batch_overrides_file(overrides)

    concurrency = W.get_script_metadata(script_path).get("concurrency", "heavy")
    W._current_run["script_name"] = script_basename
    W._current_run["started_at"] = time.time()
    W._LOG_REPLAY_BUFFER.clear()
    export_note = W._export_fallback_note(script_basename)
    if export_note:
        W.worker.log_queue.put((export_note + "\n", "red"))   # לפני הרינדור - הריצה ממשיכה ל-workspace
    extra_args = W._build_extra_args(script_basename, payload, batch_overrides_path=batch_overrides_path, layers_path=layers_path)
    on_finish = W._on_task_finished
    task_started_at = time.time()
    if script_basename == "video_editor.py" and not payload.get("concat_mode"):
        # גל 8: קובץ-בקרה (השהיה/ביטול קובץ בודד, שינוי סדר) + היסטוריית ריצות + פעולות סוף-ריצה
        control_path = W._create_run_control_file()
        extra_args += ["--control-file", control_path]
        run_id = W.editor_runs.record_start(W._editor_runs_path(), folder, payload, payload.get("ve_profile_name"))
        on_finish = W._make_editor_finish_callback(run_id, folder, payload, task_started_at)
    W._current_run["control_file"] = control_path
    W._current_run["run_id"] = run_id

    def _on_task_start(control_path=control_path, run_id=run_id):
        # גל 12: כמה משימות בתור (יעדים) - "הריצה הנוכחית" (שליטה בקבצים, לוג) היא זו שבאמת התחילה
        W._current_run["script_name"] = script_basename
        W._current_run["started_at"] = time.time()
        W._current_run["stop_requested"] = False   # /api/stop מסמן - מרכז ההתראות אומר "נעצר" ולא "נכשל"
        W._current_run["control_file"] = control_path
        W._current_run["run_id"] = run_id

    # גל 14: תווית לתור הרינדור, "לראש התור", והמתנה כשהמחשב עסוק (הגדרה גלובלית)
    label = payload.get("run_label") or os.path.basename(os.path.normpath(folder)) or script_basename
    busy_guard = W._routes_pro_busy_guard() if concurrency == "heavy" else None
    W.worker.add_script_task(script_path, folder, on_finish, concurrency=concurrency, extra_args=extra_args, on_start=_on_task_start,
                           label=label, priority="high" if payload.get("priority") == "high" else "normal", busy_guard=busy_guard)
    W.audit_log.record_action("web", "run_script", details=os.path.basename(script_path), username=client_host)
    ve_profile_name = payload.get("ve_profile_name")
    if os.path.basename(script_path) == "video_editor.py" and ve_profile_name and record_profile_use:
        record_video_editor_profile_used(str(ve_profile_name))
    return {"ok": True, "run_id": run_id}


def _run_scheduler_loop(interval_seconds=30):
    """בודק משימות מתוזמנות שהגיע זמנן (utils/bot/scheduler.py - אותה לוגיקה כמו ב-GUI)."""
    from utils.bot.scheduler import check_and_run_due_tasks
    from utils.bot import wake_timer
    while True:
        try:
            for task in check_and_run_due_tasks(W.worker):
                W.worker.log_queue.put((f"⏰ משימה מתוזמנת הופעלה: {task.get('label') or os.path.basename(task['script_path'])}\n", None))
        except Exception as e:  # משימה פגומה לא אמורה להרוג את הלולאה
            W.worker.log_queue.put((f"⚠️ בדיקת משימות מתוזמנות נכשלה: {e}\n", "red"))
        try:
            # הערת המחשב למשימה הבאה (כבוי כברירת מחדל) - schtasks רק כשהמועד משתנה
            wake_timer.sync(W.scheduler_store.load_tasks())
        except Exception as e:
            W.worker.log_queue.put((f"⚠️ עדכון טיימר ההתעוררות נכשל: {e}\n", "red"))
        time.sleep(interval_seconds)
