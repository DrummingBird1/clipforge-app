# tests/gui/test_dashboard_worker_integration.py
#
# בודק את שכבת ה"דבק" בין ה-GUI (ui/dashboard.py) לתור הריצה (utils/shared/worker.py) -
# בדיוק השכבה שבה ישבו שניים משלושת הבאגים האמיתיים האחרונים בפרויקט (guard
# שחסם הרצת סקריפטים בלי משוב, ו-race condition ב-terminate_current()). קודם
# לכן זה נבדק רק ידנית עם סקריפט חד-פעמי - כאן זה טסט קבוע כדי שרגרסיה דומה
# תיתפס אוטומטית.
#
# xdist-group: workspace - הפייפליין מריץ משימות heavy אמיתיות שתופסות את מנעול הרינדור
# של המחשב (data/render.lock), כמו טסטי הרינדור; ב-CI הן חיכו מאחורי רינדור במקביל.
import os
import time


import customtkinter as ctk
import psutil
import ui.dashboard as dashboard_module
import utils.shared.worker as worker_module
from ui.dashboard import DashboardTabComponent
from utils.shared.i18n import t
from utils.shared.state import state
from utils.shared.worker import worker


def test_render_lock_held_by_this_gui_process_itself_is_not_flagged_as_another_process(shared_tk_root, monkeypatch):
    # utils/shared/worker.py תופס את מנעול הרינדור (utils/shared/render_lock.py) מתוך תהליך
    # ה-GUI עצמו עבור כל משימה "heavy" שהוא מריץ - כך שה-PID השמור במנעול הוא
    # תמיד ה-PID של ה-GUI עצמו, גם כשאין שום תהליך "אחר" באמת. רגרסיה: התווית
    # הייתה מוצגת כ"רינדור אחר תפוס" בכל פעם שהמשתמש הריץ סקריפט כבד, לא רק
    # כשתהליך חיצוני אמיתי (הבוט/scheduler_cog) מחזיק את המנעול.
    monkeypatch.setattr(
        dashboard_module, "get_render_lock_status",
        lambda: {"pid": os.getpid(), "acquired_at": time.time(), "age_seconds": 5.0, "is_stale": False},
    )
    comp = DashboardTabComponent(shared_tk_root, lambda color, text: None)
    try:
        comp._poll_render_lock()
        assert comp.render_lock_label.cget("text") == ""
    finally:
        comp.destroy()


def test_render_lock_held_by_another_process_is_flagged(shared_tk_root, monkeypatch):
    other_pid = os.getpid() + 1
    monkeypatch.setattr(
        dashboard_module, "get_render_lock_status",
        lambda: {"pid": other_pid, "acquired_at": time.time(), "age_seconds": 5.0, "is_stale": False},
    )
    comp = DashboardTabComponent(shared_tk_root, lambda color, text: None)
    try:
        comp._poll_render_lock()
        assert str(other_pid) in comp.render_lock_label.cget("text")
    finally:
        comp.destroy()


def test_render_lock_stale_is_flagged_even_when_pid_is_this_process(shared_tk_root, monkeypatch):
    # מנעול תקוע (is_stale) ראוי להתראה גם אם ה-PID השמור הוא שלנו עצמנו -
    # למשל מנעול ישן שנשאר מריצה קודמת של אותו תהליך ולא שוחרר כראוי.
    monkeypatch.setattr(
        dashboard_module, "get_render_lock_status",
        lambda: {"pid": os.getpid(), "acquired_at": time.time() - 99999, "age_seconds": 99999.0, "is_stale": True},
    )
    comp = DashboardTabComponent(shared_tk_root, lambda color, text: None)
    try:
        comp._poll_render_lock()
        assert "תקוע" in comp.render_lock_label.cget("text")
    finally:
        comp.destroy()


def _make_fake_script(path, body_lines):
    path.write_text("import sys\n" + "\n".join(body_lines) + "\n", encoding="utf-8")
    return str(path)


def _pump_until(root, condition, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        root.update()
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_run_task_streams_console_progress_and_result(tmp_path, monkeypatch, shared_tk_root):
    # מנטרל תופעות לוואי אמיתיות (webhook/גיבוי/כיבוי מחשב/סאונד) שריצה דרך
    # run_task() הייתה עלולה לגרום להן אם ל-config.json האמיתי של המשתמש יש
    # webhook/גיבוי/מצב לילה פעילים - טסט אסור שיהיה תלוי בהגדרות מקומיות.
    monkeypatch.setattr(state, "discord_webhook_url", "")
    monkeypatch.setattr(state, "auto_backup_active", False)
    monkeypatch.setattr(state, "night_mode_active", False)
    monkeypatch.setattr(state, "selected_gameplay_folder", "")
    monkeypatch.setattr(dashboard_module, "play_system_sound", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module, "send_toast_notification", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module.job_history, "record_job", lambda *_a, **_k: None)

    script_path = _make_fake_script(tmp_path / "fake_script.py", [
        "print('hello from fake script')",
        "print('PROGRESS:50')",
        "print('RESULT: {\"ok\": true, \"count\": 3}')",
    ])

    root = shared_tk_root
    comp = DashboardTabComponent(root, lambda color, text: None)
    try:
        state.selected_script = script_path

        comp.run_task()

        found = _pump_until(root, lambda: "hello from fake script" in comp.console.get("1.0", "end"))
        assert found, "לא הופיע פלט בקונסולה - הריצה מעולם לא התחילה בפועל"

        _pump_until(root, lambda: comp.stop_btn.cget("state") == "disabled")

        # on_task_finished() ממשיך אחרי זה (וידג'טים, אנימציית קונפטי דרך
        # self.after) על ה-thread של ה-worker - ממתינים שהכל יתייצב לפני
        # שהורסים את comp, אחרת קריאות after מאוחרות פוגעות ב-widget שנהרס.
        _pump_until(root, lambda: False, timeout=2)

        console_text = comp.console.get("1.0", "end")
        assert "hello from fake script" in console_text
        assert "RESULT:" not in console_text  # שורת RESULT היא פרוטוקול פנימי, לא מוצגת למשתמש
        assert comp.progress_pct_label.cget("text") == "100%"  # 50% ואז 100% (הצלחה) - האחרון מנצח
    finally:
        worker.terminate_current()
        comp.destroy()


def test_run_task_shows_eta_alongside_percentage_for_tqdm_style_progress(tmp_path, monkeypatch, shared_tk_root):
    # ה-ETA בתווית מגיע ישירות מהטקסט שtqdm כבר מדפיס בפועל (utils/shared/worker.py's
    # _parse_tqdm_eta_seconds שולף אותו) - זה בודק את השרשרת המלאה (subprocess
    # אמיתי -> worker.py -> progress_queue -> ui/dashboard.py's תווית), לא רק
    # את הפרסינג המבודד (ראו tests/infra/test_worker_progress.py לזה).
    monkeypatch.setattr(state, "discord_webhook_url", "")
    monkeypatch.setattr(state, "auto_backup_active", False)
    monkeypatch.setattr(state, "night_mode_active", False)
    monkeypatch.setattr(state, "selected_gameplay_folder", "")
    monkeypatch.setattr(dashboard_module, "play_system_sound", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module, "send_toast_notification", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module.job_history, "record_job", lambda *_a, **_k: None)

    script_path = _make_fake_script(tmp_path / "fake_script.py", [
        "print('fake.mp4:  50%|#####     | 500/1000 [00:30<01:30, 16.67frames/s]')",
        "import time; time.sleep(0.5)",
    ])

    root = shared_tk_root
    comp = DashboardTabComponent(root, lambda color, text: None)
    try:
        state.selected_script = script_path
        comp.run_task()

        found = _pump_until(root, lambda: "נותרו" in comp.progress_pct_label.cget("text"))
        assert found, "ה-ETA מעולם לא הופיע בתווית ההתקדמות"
        assert comp.progress_pct_label.cget("text") == "50% · נותרו כ-1ד"
    finally:
        worker.terminate_current()
        comp.destroy()


# --- Pause/Resume (item) ---

def test_pause_button_suspends_the_running_script_and_resume_continues_it(tmp_path, monkeypatch, shared_tk_root):
    # שרשרת מלאה, subprocess אמיתי: כפתור השהה -> worker.pause_current() ->
    # psutil.suspend() בפועל על תת-התהליך הרץ - ולא רק "לא קרס", אלא שהתהליך
    # באמת קפוא (0% CPU, psutil.STATUS_STOPPED) עד שממשיכים.
    monkeypatch.setattr(state, "discord_webhook_url", "")
    monkeypatch.setattr(state, "auto_backup_active", False)
    monkeypatch.setattr(state, "night_mode_active", False)
    monkeypatch.setattr(state, "selected_gameplay_folder", "")
    monkeypatch.setattr(dashboard_module, "play_system_sound", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module, "send_toast_notification", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module.job_history, "record_job", lambda *_a, **_k: None)
    monkeypatch.setattr(worker_module, "_touch_render_lock", lambda: None)

    script_path = _make_fake_script(tmp_path / "slow_script.py", [
        "import time",
        "print('starting')",
        "time.sleep(4)",
        "print('done')",
    ])

    root = shared_tk_root
    comp = DashboardTabComponent(root, lambda color, text: None)
    try:
        state.selected_script = script_path
        comp.run_task()

        found = _pump_until(root, lambda: "starting" in comp.console.get("1.0", "end"))
        assert found, "הריצה מעולם לא התחילה בפועל"
        assert comp.pause_btn.cget("state") == "normal"

        pid = list(worker.active_processes.values())[0].pid
        ps_proc = psutil.Process(pid)

        comp.toggle_pause()
        assert comp.pause_btn.cget("text") == t("▶️ המשך")
        assert worker.is_paused() is True
        _pump_until(root, lambda: ps_proc.status() == psutil.STATUS_STOPPED, timeout=3)
        assert ps_proc.status() == psutil.STATUS_STOPPED

        before = ps_proc.cpu_times()
        time.sleep(0.8)
        after = ps_proc.cpu_times()
        # tick אחד (15.6ms ב-Windows) יכול להירשם על השעיית התהליך עצמה - תהליך שרץ צובר הרבה יותר
        assert after.user - before.user <= 0.02 and after.system - before.system <= 0.02, "תהליך מושהה לא אמור לצרוך CPU"

        comp.toggle_pause()
        assert comp.pause_btn.cget("text") == t("⏸️ השהה")
        assert worker.is_paused() is False
        _pump_until(root, lambda: ps_proc.status() != psutil.STATUS_STOPPED, timeout=3)

        finished = _pump_until(root, lambda: comp.stop_btn.cget("state") == "disabled", timeout=15)
        assert finished, "הריצה לא הסתיימה אחרי resume"
        assert "done" in comp.console.get("1.0", "end")
        assert comp.pause_btn.cget("state") == "disabled"
    finally:
        worker.terminate_current()
        comp.destroy()


def test_pause_button_is_disabled_until_a_task_is_running(shared_tk_root):
    comp = DashboardTabComponent(shared_tk_root, lambda color, text: None)
    try:
        assert comp.pause_btn.cget("state") == "disabled"
    finally:
        comp.destroy()


# --- milestone toast notifications (item) ---

def test_heavy_task_fires_start_and_50pct_toast_milestones(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "discord_webhook_url", "")
    monkeypatch.setattr(state, "auto_backup_active", False)
    monkeypatch.setattr(state, "night_mode_active", False)
    monkeypatch.setattr(state, "selected_gameplay_folder", "")
    monkeypatch.setattr(dashboard_module, "play_system_sound", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module.job_history, "record_job", lambda *_a, **_k: None)
    toast_calls = []
    monkeypatch.setattr(dashboard_module, "send_toast_notification", lambda title, msg: toast_calls.append((title, msg)))

    # אין "# Concurrency:" בכותרת - ברירת המחדל היא heavy (utils/shared/script_metadata.py)
    script_path = _make_fake_script(tmp_path / "fake_heavy_script.py", [
        "print('PROGRESS:10')",
        "print('PROGRESS:50')",
        "print('PROGRESS:100')",
    ])

    root = shared_tk_root
    comp = DashboardTabComponent(root, lambda color, text: None)
    try:
        state.selected_script = script_path
        comp.run_task()

        # ה-toast של "התחיל" נשלח מיידית ב-_start_script_task, לפני שהתת-תהליך
        # בכלל התחיל להריץ - לא צריך להמתין ל-pump בשבילו.
        assert any(title.startswith("▶️") for title, _msg in toast_calls), "לא נשלחה התראת 'התחיל'"

        _pump_until(root, lambda: comp.stop_btn.cget("state") == "disabled")
        _pump_until(root, lambda: False, timeout=2)  # ראו test_run_task_streams_console_progress_and_result

        start_toasts = [c for c in toast_calls if c[0].startswith("▶️")]
        pct50_toasts = [c for c in toast_calls if c[0].startswith("⏳")]
        done_toasts = [c for c in toast_calls if c[0].startswith("✅") or c[0].startswith("❌")]
        assert len(start_toasts) == 1
        assert len(pct50_toasts) == 1, f"ציפינו להתראת 50% אחת בדיוק, קיבלנו {len(pct50_toasts)}"
        assert len(done_toasts) == 1
    finally:
        worker.terminate_current()
        comp.destroy()


def test_light_task_does_not_fire_start_or_50pct_toast_milestones(tmp_path, monkeypatch, shared_tk_root):
    # סקריפט light מסתיים בדרך כלל תוך שניות - שלוש התראות (התחיל/50%/הסתיים)
    # על ריצה כמעט-מיידית זו רעש, לא מידע שימושי. רק ה-toast הרגיל של השלמה
    # (שכבר היה קיים לפני הפיצ'ר הזה, לכל סוגי הסקריפטים) אמור להישלח.
    monkeypatch.setattr(state, "discord_webhook_url", "")
    monkeypatch.setattr(state, "auto_backup_active", False)
    monkeypatch.setattr(state, "night_mode_active", False)
    monkeypatch.setattr(state, "selected_gameplay_folder", "")
    monkeypatch.setattr(dashboard_module, "play_system_sound", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module.job_history, "record_job", lambda *_a, **_k: None)
    toast_calls = []
    monkeypatch.setattr(dashboard_module, "send_toast_notification", lambda title, msg: toast_calls.append((title, msg)))

    script_path = _make_fake_script(tmp_path / "fake_light_script.py", [
        "# Concurrency: light",
        "print('PROGRESS:50')",
        "print('PROGRESS:100')",
    ])

    root = shared_tk_root
    comp = DashboardTabComponent(root, lambda color, text: None)
    try:
        state.selected_script = script_path
        comp.run_task()
        _pump_until(root, lambda: comp.stop_btn.cget("state") == "disabled")
        _pump_until(root, lambda: False, timeout=2)

        assert not any(title.startswith("▶️") for title, _msg in toast_calls)
        assert not any(title.startswith("⏳") for title, _msg in toast_calls)
        assert any(title.startswith("✅") or title.startswith("❌") for title, _msg in toast_calls)
    finally:
        worker.terminate_current()
        comp.destroy()


def test_run_task_passes_ai_provider_flag_only_for_story_cutter(tmp_path, monkeypatch, shared_tk_root):
    # extra_args (utils/shared/worker.py) חייב להישאר ספציפי-לסקריפט (ראו התיעוד שם) -
    # זה בודק את שני הצדדים: גם שהדגל כן מגיע ל-story_cutter.py, וגם שהוא לא
    # "דולף" לסקריפט אחר שנקרא באותו session (שהיה קורס עם parse_args() קפדני).
    monkeypatch.setattr(state, "discord_webhook_url", "")
    monkeypatch.setattr(state, "auto_backup_active", False)
    monkeypatch.setattr(state, "night_mode_active", False)
    monkeypatch.setattr(state, "selected_gameplay_folder", "")
    monkeypatch.setattr(state, "story_cutter_ai_provider", "local")
    monkeypatch.setattr(dashboard_module, "play_system_sound", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module, "send_toast_notification", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module.job_history, "record_job", lambda *_a, **_k: None)

    # השם עצמו (לא רק תוכן הקובץ) הוא מה ש-dashboard.py בודק
    story_cutter_dir = tmp_path / "story_cutter_variant"
    story_cutter_dir.mkdir()
    story_cutter_path = _make_fake_script(story_cutter_dir / "story_cutter.py", [
        "print('argv:', sys.argv[1:])",
    ])
    other_script_path = _make_fake_script(tmp_path / "other_script.py", [
        "print('argv:', sys.argv[1:])",
    ])

    root = shared_tk_root
    comp = DashboardTabComponent(root, lambda color, text: None)
    try:
        state.selected_script = story_cutter_path
        comp.run_task()
        found = _pump_until(root, lambda: "argv:" in comp.console.get("1.0", "end"))
        assert found
        _pump_until(root, lambda: comp.stop_btn.cget("state") == "disabled")
        assert "--ai-provider" in comp.console.get("1.0", "end")
        assert "local" in comp.console.get("1.0", "end")

        comp.console.configure(state="normal")
        comp.console.delete("1.0", "end")
        comp.console.configure(state="disabled")

        state.selected_script = other_script_path
        comp.run_task()
        found = _pump_until(root, lambda: "argv:" in comp.console.get("1.0", "end"))
        assert found
        _pump_until(root, lambda: comp.stop_btn.cget("state") == "disabled")
        assert "--ai-provider" not in comp.console.get("1.0", "end")
    finally:
        worker.terminate_current()
        comp.destroy()


def test_run_task_passes_remove_watermark_position_only_when_set(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "discord_webhook_url", "")
    monkeypatch.setattr(state, "auto_backup_active", False)
    monkeypatch.setattr(state, "night_mode_active", False)
    monkeypatch.setattr(state, "selected_gameplay_folder", "")
    monkeypatch.setattr(state, "video_editor_watermark_path", "")
    monkeypatch.setattr(state, "video_editor_remove_watermark_position", "top-left")
    monkeypatch.setattr(dashboard_module, "play_system_sound", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module, "send_toast_notification", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module.job_history, "record_job", lambda *_a, **_k: None)

    video_editor_dir = tmp_path / "video_editor_variant"
    video_editor_dir.mkdir()
    video_editor_path = _make_fake_script(video_editor_dir / "video_editor.py", [
        "print('argv:', sys.argv[1:])",
    ])

    root = shared_tk_root
    comp = DashboardTabComponent(root, lambda color, text: None)
    try:
        state.selected_script = video_editor_path
        comp.run_task()
        found = _pump_until(root, lambda: "argv:" in comp.console.get("1.0", "end"))
        assert found
        _pump_until(root, lambda: comp.stop_btn.cget("state") == "disabled")
        console_text = comp.console.get("1.0", "end")
        assert "--remove_watermark_position" in console_text
        assert "top-left" in console_text

        comp.console.configure(state="normal")
        comp.console.delete("1.0", "end")
        comp.console.configure(state="disabled")

        monkeypatch.setattr(state, "video_editor_remove_watermark_position", "")
        comp.run_task()
        found = _pump_until(root, lambda: "argv:" in comp.console.get("1.0", "end"))
        assert found
        _pump_until(root, lambda: comp.stop_btn.cget("state") == "disabled")
        assert "--remove_watermark_position" not in comp.console.get("1.0", "end")
    finally:
        worker.terminate_current()
        comp.destroy()


def test_run_task_passes_target_seconds_and_keep_audio_only_for_timelapse_maker(tmp_path, monkeypatch, shared_tk_root):
    # רגרסיה: timelapse_maker.py לא היה מוכר בכלל ב-extra_args builder - כל
    # ריצה מה-GUI קיבלה ברירות מחדל של הסקריפט עצמו (כולל --keep-audio כבוי),
    # בלי שום דרך מהממשק להשפיע על זה. ראו גם test_timelapse_keep_audio_defaults_to_true
    # ב-tests/infra/test_state_config.py.
    monkeypatch.setattr(state, "discord_webhook_url", "")
    monkeypatch.setattr(state, "auto_backup_active", False)
    monkeypatch.setattr(state, "night_mode_active", False)
    monkeypatch.setattr(state, "selected_gameplay_folder", "")
    monkeypatch.setattr(state, "timelapse_target_seconds", "45")
    monkeypatch.setattr(state, "timelapse_keep_audio", True)
    monkeypatch.setattr(dashboard_module, "play_system_sound", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module, "send_toast_notification", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module.job_history, "record_job", lambda *_a, **_k: None)

    timelapse_dir = tmp_path / "timelapse_variant"
    timelapse_dir.mkdir()
    timelapse_path = _make_fake_script(timelapse_dir / "timelapse_maker.py", [
        "print('argv:', sys.argv[1:])",
    ])
    other_script_path = _make_fake_script(tmp_path / "other_script.py", [
        "print('argv:', sys.argv[1:])",
    ])

    root = shared_tk_root
    comp = DashboardTabComponent(root, lambda color, text: None)
    try:
        state.selected_script = timelapse_path
        comp.run_task()
        found = _pump_until(root, lambda: "argv:" in comp.console.get("1.0", "end"))
        assert found
        _pump_until(root, lambda: comp.stop_btn.cget("state") == "disabled")
        console_text = comp.console.get("1.0", "end")
        assert "--target-seconds" in console_text
        assert "45" in console_text
        assert "--keep-audio" in console_text

        comp.console.configure(state="normal")
        comp.console.delete("1.0", "end")
        comp.console.configure(state="disabled")

        state.selected_script = other_script_path
        comp.run_task()
        found = _pump_until(root, lambda: "argv:" in comp.console.get("1.0", "end"))
        assert found
        _pump_until(root, lambda: comp.stop_btn.cget("state") == "disabled")
        assert "--keep-audio" not in comp.console.get("1.0", "end")
    finally:
        worker.terminate_current()
        comp.destroy()


def test_light_task_does_not_wait_behind_heavy_task(tmp_path):
    # התועלת המרכזית של מסלול ה-"light" (utils/shared/worker.py): סקריפט קל לא צריך
    # לחכות בתור מאחורי סקריפט כבד (כמו רינדור ffmpeg) שכבר רץ.
    heavy_script = _make_fake_script(tmp_path / "heavy.py", [
        "import time",
        "time.sleep(2)",
        "print('heavy done')",
    ])
    light_script = _make_fake_script(tmp_path / "light.py", [
        "print('light done')",
    ])

    heavy_finished = {"done": False}
    light_finished = {"done": False}

    worker.add_script_task(heavy_script, "", lambda outcome: heavy_finished.__setitem__("done", True), concurrency="heavy")
    heavy_deadline = time.time() + 5  # מחכים שהמשימה הכבדה באמת רצה, לא לזמן קבוע
    while time.time() < heavy_deadline and not worker.active_processes:
        time.sleep(0.02)
    assert worker.active_processes, "המשימה הכבדה לא התחילה"
    worker.add_script_task(light_script, "", lambda outcome: light_finished.__setitem__("done", True), concurrency="light")

    deadline = time.time() + 5
    while time.time() < deadline and not light_finished["done"]:
        time.sleep(0.05)

    assert light_finished["done"], "המשימה הקלה לא הסתיימה - כנראה נתקעה מאחורי המשימה הכבדה בתור אחד משותף"
    assert not heavy_finished["done"], "המשימה הכבדה כבר הסתיימה - הטסט לא בדק בפועל ריצה מקבילה"

    worker.terminate_current()
    deadline = time.time() + 3
    while time.time() < deadline and not heavy_finished["done"]:
        time.sleep(0.05)


def test_run_pipeline_runs_scripts_in_order(tmp_path, monkeypatch, shared_tk_root):
    # item 15: כמה סקריפטים ברצף, כל שלב רק אחרי שהקודם הצליח - הטסט בונה שני
    # סקריפטים מזויפים עם סמנים ייחודיים ומוודא שהם רצים בסדר הנכון (לא רק ששניהם
    # רצים בסופו של דבר, אלא שהסמן של השלב השני מופיע *אחרי* של הראשון בקונסולה).
    monkeypatch.setattr(state, "discord_webhook_url", "")
    monkeypatch.setattr(state, "auto_backup_active", False)
    monkeypatch.setattr(state, "night_mode_active", False)
    monkeypatch.setattr(state, "selected_gameplay_folder", "")
    monkeypatch.setattr(dashboard_module, "play_system_sound", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module, "send_toast_notification", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module.job_history, "record_job", lambda *_a, **_k: None)

    step1 = _make_fake_script(tmp_path / "step1.py", ["print('STEP_ONE_MARKER')"])
    step2 = _make_fake_script(tmp_path / "step2.py", ["print('STEP_TWO_MARKER')"])

    root = shared_tk_root
    comp = DashboardTabComponent(root, lambda color, text: None)
    try:
        comp.pipeline_scripts = [step1, step2]
        comp.run_pipeline()

        found = _pump_until(root, lambda: "STEP_TWO_MARKER" in comp.console.get("1.0", "end"), timeout=15)
        assert found, "השלב השני של הפייפליין מעולם לא רץ"
        # pipeline_running הופך ל-False תוך כדי on_task_finished, אבל הודעת
        # הסיכום עצמה (worker.log_queue.put) רק מצטרפת לקונסולה ב-tick הבא של
        # _poll_logs (שכבר עבר על תור הלוגים לפני שקרא ל-on_task_finished
        # באותה קריאה) - לכן ממתינים על התוכן בפועל, לא רק על הדגל.
        found_summary = _pump_until(root, lambda: "הפייפליין הושלם בהצלחה" in comp.console.get("1.0", "end"), timeout=5)
        assert found_summary, "הודעת סיכום הפייפליין מעולם לא הופיעה"

        console_text = comp.console.get("1.0", "end")
        assert console_text.index("STEP_ONE_MARKER") < console_text.index("STEP_TWO_MARKER")
        assert not comp.pipeline_running
    finally:
        worker.terminate_current()
        comp.destroy()


def _find_buttons_by_text(widget, text):
    # רק CTkButton עצמו, לא ה-Label הפנימי שלו (שגם הוא "מד"ה" את אותו טקסט,
    # ולא CTkButton בעצמו - היה כופל כל תוצאה פעמיים).
    found = []
    for child in widget.winfo_children():
        if isinstance(child, ctk.CTkButton) and child.cget("text") == text:
            found.append(child)
        found.extend(_find_buttons_by_text(child, text))
    return found


def test_open_pipeline_dialog_add_and_remove_flow(shared_tk_root):
    # בודק את קוד בניית הדיאלוג עצמו (open_pipeline_dialog) - שני הטסטים
    # למעלה עוקפים אותו לגמרי (מגדירים pipeline_scripts ישירות), אז בלעדי זה
    # כפתורי ➕/✖ עצמם היו יכולים להישבר (למשל שגיאת late-binding קלאסית של
    # lambda בלולאה) בלי שום טסט שהיה תופס את זה.
    comp = DashboardTabComponent(shared_tk_root, lambda color, text: None)
    comp.pipeline_scripts = []
    try:
        comp.open_pipeline_dialog()
        dialog = shared_tk_root.winfo_children()[-1]
        try:
            add_buttons = _find_buttons_by_text(dialog, "➕")
            assert len(add_buttons) >= 2, "אמורים להיות כפתורי הוספה לכל סקריפט זמין"

            add_buttons[0].cget("command")()
            assert len(comp.pipeline_scripts) == 1
            remove_buttons = _find_buttons_by_text(dialog, "✖")
            assert len(remove_buttons) == 1

            add_buttons[1].cget("command")()
            assert len(comp.pipeline_scripts) == 2

            remove_buttons = _find_buttons_by_text(dialog, "✖")
            remove_buttons[0].cget("command")()
            assert len(comp.pipeline_scripts) == 1
        finally:
            dialog.destroy()
    finally:
        comp.destroy()


def test_run_pipeline_stops_after_a_failed_step(tmp_path, monkeypatch, shared_tk_root):
    # אם שלב באמצע הפייפליין נכשל (קוד יציאה שאינו 0), השלבים הבאים אחריו לא
    # אמורים לרוץ בכלל - בלי זה, למשל video_editor שרץ על תוצר לא-קיים של
    # story_cutter שנכשל היה קורס בצורה מבלבלת הרבה יותר מ"הפייפליין נעצר".
    monkeypatch.setattr(state, "discord_webhook_url", "")
    monkeypatch.setattr(state, "auto_backup_active", False)
    monkeypatch.setattr(state, "night_mode_active", False)
    monkeypatch.setattr(state, "selected_gameplay_folder", "")
    monkeypatch.setattr(dashboard_module, "play_system_sound", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module, "send_toast_notification", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_module.job_history, "record_job", lambda *_a, **_k: None)

    failing_step = _make_fake_script(tmp_path / "failing.py", ["print('FAILING_STEP_MARKER')", "sys.exit(1)"])
    never_run_step = _make_fake_script(tmp_path / "never_run.py", ["print('SHOULD_NOT_RUN_MARKER')"])

    root = shared_tk_root
    comp = DashboardTabComponent(root, lambda color, text: None)
    try:
        comp.pipeline_scripts = [failing_step, never_run_step]
        comp.run_pipeline()

        # ראו ההערה המקבילה ב-test_run_pipeline_runs_scripts_in_order - ממתינים
        # על תוכן הודעת הכשל בפועל, לא רק על pipeline_running=False, כי הודעת
        # הלוג מצטרפת ל-tick הבא של _poll_logs.
        found = _pump_until(root, lambda: "הפייפליין נעצר" in comp.console.get("1.0", "end"), timeout=15)
        assert found, "הודעת כשל הפייפליין מעולם לא הופיעה"

        console_text = comp.console.get("1.0", "end")
        assert "FAILING_STEP_MARKER" in console_text
        assert "SHOULD_NOT_RUN_MARKER" not in console_text
        assert not comp.pipeline_running
    finally:
        worker.terminate_current()
        comp.destroy()


def _insert_console_text(comp, text):
    comp.console.configure(state="normal")
    comp.console.insert("end", text)
    comp.console.configure(state="disabled")


def test_console_search_bar_starts_hidden_and_toggles(shared_tk_root):
    # winfo_ismapped() דורש שהחלון ייצוייר בפועל על המסך (root המשותף לטסטים
    # נשאר withdraw()-ed בכוונה - ראו conftest.py), אז נבדק דרך winfo_manager()
    # (רשום/לא-רשום אצל pack, בלי קשר לציור בפועל) במקום.
    comp = DashboardTabComponent(shared_tk_root, lambda color, text: None)
    try:
        assert comp.console_search_bar.winfo_manager() == ""
        comp.toggle_console_search()
        assert comp.console_search_bar.winfo_manager() == "pack"
        comp.toggle_console_search()
        assert comp.console_search_bar.winfo_manager() == ""
    finally:
        comp.destroy()


def test_search_console_log_highlights_all_matches(shared_tk_root):
    # item 18: חיפוש בקונסולה - מדגיש כל התאמה (לא רק הראשונה), case-insensitive.
    comp = DashboardTabComponent(shared_tk_root, lambda color, text: None)
    try:
        _insert_console_text(comp, "line one ERROR here\nline two ok\nanother error line\n")
        comp.console_search_entry.insert(0, "error")
        comp.search_console_log()

        ranges = comp.console.tag_ranges("search_hit")
        # שני זוגות (start, end) - שתי התאמות ("ERROR" ו-"error", case-insensitive)
        assert len(ranges) == 4
    finally:
        comp.destroy()


def test_search_console_log_clears_highlights_when_query_emptied(shared_tk_root):
    comp = DashboardTabComponent(shared_tk_root, lambda color, text: None)
    try:
        _insert_console_text(comp, "some error text\n")
        comp.console_search_entry.insert(0, "error")
        comp.search_console_log()
        assert len(comp.console.tag_ranges("search_hit")) == 2

        comp.console_search_entry.delete(0, "end")
        comp.search_console_log()
        assert len(comp.console.tag_ranges("search_hit")) == 0
    finally:
        comp.destroy()


def test_search_console_log_finds_nothing_for_unmatched_query(shared_tk_root):
    comp = DashboardTabComponent(shared_tk_root, lambda color, text: None)
    try:
        _insert_console_text(comp, "all good here\n")
        comp.console_search_entry.insert(0, "nonexistent_marker")
        comp.search_console_log()
        assert len(comp.console.tag_ranges("search_hit")) == 0
    finally:
        comp.destroy()


def test_prune_console_removes_lines_older_than_the_retention_window(shared_tk_root, monkeypatch):
    # item: log spam - שורות ישנות מ-30 הדקות (CONSOLE_LOG_RETENTION_SECONDS)
    # האחרונות נמחקות מהקונסולה החיה, גם אם הן מתחת לתקרת-המספר.
    comp = DashboardTabComponent(shared_tk_root, lambda color, text: None)
    try:
        monkeypatch.setattr(dashboard_module, "CONSOLE_LOG_MAX_LINES", 1000)
        now = time.monotonic()
        for line, ts in [("old line 1\n", now - 2000), ("old line 2\n", now - 1900), ("recent line\n", now - 10)]:
            _insert_console_text(comp, line)
            comp._console_line_times.append(ts)

        comp._prune_console()

        console_text = comp.console.get("1.0", "end")
        assert "old line 1" not in console_text
        assert "old line 2" not in console_text
        assert "recent line" in console_text
        assert len(comp._console_line_times) == 1
    finally:
        comp.destroy()


def test_prune_console_caps_total_lines_even_within_the_retention_window(shared_tk_root, monkeypatch):
    # item: log spam - רשת ביטחון: גם שורות "טריות" (בתוך חלון הזמן) נחתכות אם
    # יש יותר מדי מהן בבת אחת, כדי שריצה "רועשת" (הרבה שורות אמיתיות, לא רק
    # tqdm) לא תנפח את הזיכרון/ה-GUI.
    comp = DashboardTabComponent(shared_tk_root, lambda color, text: None)
    try:
        monkeypatch.setattr(dashboard_module, "CONSOLE_LOG_MAX_LINES", 3)
        now = time.monotonic()
        for i in range(5):
            _insert_console_text(comp, f"line {i}\n")
            comp._console_line_times.append(now)

        comp._prune_console()

        console_text = comp.console.get("1.0", "end")
        assert "line 0" not in console_text
        assert "line 1" not in console_text
        assert "line 2" in console_text
        assert "line 3" in console_text
        assert "line 4" in console_text
        assert len(comp._console_line_times) == 3
    finally:
        comp.destroy()


def test_poll_logs_caps_lines_inserted_per_tick_and_drains_the_rest_later(shared_tk_root, monkeypatch):
    # item: log spam - סקריפט שמדפיס פרץ ענק של שורות אמיתיות בין tick ל-tick
    # (למשל אלפי "[SKIP] קובץ קיים כבר" ברצף מהיר על ספריית-וידאו ענקית) לא
    # אמור לגרום ל-_poll_logs בודד לבצע קריאת Tkinter נפרדת לכל שורה - רק עד
    # MAX_CONSOLE_LINES_PER_TICK מוכנסות ב-tick אחד, השאר ממתין וממשיך
    # להתנקז ב-ticks הבאים (שום דבר לא הולך לאיבוד).
    comp = DashboardTabComponent(shared_tk_root, lambda color, text: None)
    try:
        monkeypatch.setattr(dashboard_module, "MAX_CONSOLE_LINES_PER_TICK", 5)
        monkeypatch.setattr(dashboard_module, "CONSOLE_LOG_MAX_LINES", 1000)
        while not worker.log_queue.empty():
            worker.log_queue.get_nowait()
        for i in range(8):
            worker.log_queue.put((f"line {i}\n", None))

        comp._poll_logs()
        first_tick_text = comp.console.get("1.0", "end")
        for i in range(5):
            assert f"line {i}\n" in first_tick_text
        for i in range(5, 8):
            assert f"line {i}\n" not in first_tick_text

        comp._poll_logs()
        second_tick_text = comp.console.get("1.0", "end")
        for i in range(8):
            assert f"line {i}\n" in second_tick_text
    finally:
        while not worker.log_queue.empty():
            worker.log_queue.get_nowait()
        comp.destroy()


def test_missing_python_interpreter_reports_error_instead_of_silent_failure(monkeypatch):
    # רגרסיה ל-utils/shared/python_locator.py: בגרסה הארוזה (exe), אם אין python/py
    # גלובלי במערכת, get_python_executable() היה נופל בעבר בשקט ל-sys.executable
    # (ה-exe עצמו) - מה שפתח עוד עותק מלא של ה-GUI במקום להריץ את הסקריפט, בלי
    # שום שגיאה. עכשיו היא מחזירה None, ו-add_script_task אמור לדווח על כך
    # בבירור בלי לתור אף משימה.
    monkeypatch.setattr(worker_module, "get_python_executable", lambda: None)

    # worker.log_queue משותף בין הטסטים (worker הוא singleton ברמת המודול) -
    # מרוקנים שאריות מטסטים קודמים כדי לא לקרוא שורה ישנה בטעות.
    while not worker.log_queue.empty():
        worker.log_queue.get_nowait()

    before_size = worker.heavy_queue.qsize()
    called = {"count": 0}
    worker.add_script_task("dummy_script.py", "", lambda outcome: called.__setitem__("count", called["count"] + 1))

    assert worker.heavy_queue.qsize() == before_size, "משימה נתורה על אף שלא נמצא פרשן Python"
    assert called["count"] == 0

    line, tag = worker.log_queue.get_nowait()
    assert "פרשן Python" in line
    assert tag == "red"
