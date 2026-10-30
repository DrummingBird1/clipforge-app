# tests/infra/test_worker_progress.py
#
# utils/shared/worker.py's progress_queue payload switched from a bare int percentage
# to a {"pct", "eta_seconds"} dict, so the desktop and web progress bars can
# also show the time-remaining estimate tqdm already computes and prints
# inline in its own bar text - ui/dashboard.py and web_app.py both read this
# same queue, so a regression here would silently break both surfaces' bars.


import utils.shared.worker as worker_module


def test_parse_tqdm_eta_seconds_handles_minutes_seconds():
    assert worker_module._parse_tqdm_eta_seconds("50%|##  | 500/1000 [00:30<02:30, 16.67it/s]") == 150


def test_parse_tqdm_eta_seconds_handles_hours_minutes_seconds():
    assert worker_module._parse_tqdm_eta_seconds("4%|# | 18541/472374 [06:26<2:45:59, 45.66frames/s]") == 2 * 3600 + 45 * 60 + 59


def test_parse_tqdm_eta_seconds_returns_none_when_no_match():
    assert worker_module._parse_tqdm_eta_seconds("PROGRESS:50") is None
    assert worker_module._parse_tqdm_eta_seconds("just a regular log line") is None


def test_handle_output_line_puts_pct_and_eta_from_tqdm_style_line():
    w = worker_module.TaskWorker()
    w._handle_output_line("fake.mp4:  50%|#####     | 500/1000 [00:30<01:30, 16.67frames/s]")

    # label (גל 4, item 47): תיאור פס ה-tqdm = שם הקובץ, להתקדמות פר-קובץ בווב
    assert w.progress_queue.get_nowait() == {"pct": 50, "eta_seconds": 90, "label": "fake.mp4"}


def test_handle_output_line_puts_pct_and_none_eta_for_explicit_protocol():
    # פרוטוקול PROGRESS: N הידני (סקריפט שלא משתמש ב-tqdm) אין לו שום מידע
    # זמן להציג - eta_seconds תמיד None כאן, בניגוד לפס tqdm.
    w = worker_module.TaskWorker()
    w._handle_output_line("PROGRESS:75")

    assert w.progress_queue.get_nowait() == {"pct": 75, "eta_seconds": None}


def test_handle_output_line_puts_done_and_total_for_the_count_protocol():
    # סבב ייצוב: "PROGRESS: k/N" - הדפדפן משקלל איתו את הקובץ שבעבודה; לא מגיע לקונסולה
    w = worker_module.TaskWorker()
    w._handle_output_line("PROGRESS:0/1")
    w._handle_output_line("PROGRESS: 2 / 5")
    w._handle_output_line("PROGRESS:1/0")          # בלי משימות - מתעלמים

    assert w.progress_queue.get_nowait() == {"pct": 0, "eta_seconds": None, "done": 0, "total": 1}
    assert w.progress_queue.get_nowait() == {"pct": 40, "eta_seconds": None, "done": 2, "total": 5}
    assert w.progress_queue.empty() and w.log_queue.empty()


def test_handle_output_line_caps_pct_at_100_and_keeps_eta_parsing():
    w = worker_module.TaskWorker()
    w._handle_output_line("done:  150%|##########| 1000/1000 [01:00<00:00, 16.67it/s]")

    assert w.progress_queue.get_nowait() == {"pct": 100, "eta_seconds": 0, "label": "done"}


# item: log spam - ריצה ארוכה יכולה לזרים אלפי עדכוני-tqdm כמעט-זהים לקונסולה
# החיה (GUI/דפדפן), שמכביד עליה ועל המחשב. עדכונים כאלה כבר מיוצגים במלואם
# בפס ההתקדמות הייעודי (progress_queue, נבדק למעלה) - אז מה-שתי הבדיקות
# הבאות מוודאות שהם *לא* מגיעים גם ל-log_queue (הקונסולה), בניגוד לשורה
# רגילה שממשיכה להגיע אליה כרגיל.
def test_handle_output_line_does_not_forward_tqdm_style_progress_to_console_log():
    w = worker_module.TaskWorker()
    w._handle_output_line("fake.mp4:  50%|#####     | 500/1000 [00:30<01:30, 16.67frames/s]")

    assert w.log_queue.empty()


def test_handle_output_line_does_not_forward_explicit_progress_protocol_to_console_log():
    w = worker_module.TaskWorker()
    w._handle_output_line("PROGRESS:75")

    assert w.log_queue.empty()


def test_handle_output_line_still_forwards_regular_lines_to_console_log():
    w = worker_module.TaskWorker()
    w._handle_output_line("[INFO] משהו קרה", prefix="script.py")

    line, tag = w.log_queue.get_nowait()
    assert line == "[script.py] [INFO] משהו קרה\n"
    assert tag is None


def test_handle_output_line_always_writes_full_line_to_the_persistent_script_run_log(monkeypatch):
    logged = []
    monkeypatch.setattr(worker_module, "_SCRIPT_RUN_LOGGER", type("_FakeLogger", (), {"info": staticmethod(logged.append)})())
    w = worker_module.TaskWorker()

    # גם שורה "רועשת" שלא מגיעה ל-log_queue (item: log spam) עדיין נכתבת
    # במלואה להיסטוריה הקבועה - זו רק תקרה על מה שמוצג *כרגע* בקונסולה החיה,
    # לא על מה שנשמר לתיעוד/דיבוג.
    w._handle_output_line("fake.mp4:  50%|#####     | 500/1000 [00:30<01:30, 16.67frames/s]", prefix="script.py")
    w._handle_output_line("[APPROVED] נוצר: out.mp4", prefix="script.py")

    assert logged == [
        "[script.py] fake.mp4:  50%|#####     | 500/1000 [00:30<01:30, 16.67frames/s]",
        "[script.py] [APPROVED] נוצר: out.mp4",
    ]
