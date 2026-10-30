# tests/infra/test_gui_thread.py
#
# בודק utils/shared/gui_thread.py's MainThreadDispatcher - callback רגיל רץ, callback
# שזרק חריגה לא עוצר את השאר (item: בדיקת באגים מקיפה - כשל אחד היה נבלע
# בשקט מוחלט, בלי אפילו הדפסה, מה שהפך כל באג ב-callback ל-UI לבלתי-ניתן-לאבחון).


from utils.shared.gui_thread import MainThreadDispatcher


def test_drain_runs_a_queued_callback_with_its_args():
    dispatcher = MainThreadDispatcher()
    calls = []
    dispatcher.call_soon(calls.append, "a")

    dispatcher.drain()

    assert calls == ["a"]


def test_drain_runs_callbacks_in_order():
    dispatcher = MainThreadDispatcher()
    calls = []
    dispatcher.call_soon(calls.append, 1)
    dispatcher.call_soon(calls.append, 2)
    dispatcher.call_soon(calls.append, 3)

    dispatcher.drain()

    assert calls == [1, 2, 3]


def test_drain_is_a_noop_when_queue_is_empty():
    dispatcher = MainThreadDispatcher()
    dispatcher.drain()  # לא אמור לזרוק


def test_a_failing_callback_does_not_stop_the_rest_from_running():
    dispatcher = MainThreadDispatcher()
    calls = []

    def _boom():
        raise RuntimeError("callback boom")

    dispatcher.call_soon(_boom)
    dispatcher.call_soon(calls.append, "after")

    dispatcher.drain()  # לא אמור לזרוק - ה-callback השני עדיין רץ

    assert calls == ["after"]


def test_a_failing_callback_is_printed_not_silently_swallowed(capsys):
    dispatcher = MainThreadDispatcher()

    def _boom():
        raise RuntimeError("callback boom")

    dispatcher.call_soon(_boom)
    dispatcher.drain()

    captured = capsys.readouterr()
    assert "callback boom" in captured.out


def test_drain_called_twice_only_runs_new_callbacks_the_second_time():
    dispatcher = MainThreadDispatcher()
    calls = []
    dispatcher.call_soon(calls.append, "first")
    dispatcher.drain()
    dispatcher.call_soon(calls.append, "second")
    dispatcher.drain()

    assert calls == ["first", "second"]
