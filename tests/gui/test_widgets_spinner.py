# tests/gui/test_widgets_spinner.py
#
# בודק ui.widgets.Spinner בבידוד מלא מ-Tk אמיתי - עם אובייקט מזויף (FakeWidget)
# שמממש רק את שלוש המתודות ש-Spinner באמת קורא להן (winfo_exists/configure/
# after/after_cancel), כדי לבדוק את לוגיקת מחזור התווים/עצירה בלי חלון GUI.


from ui.widgets import Spinner


class FakeWidget:
    def __init__(self):
        self.exists = True
        self.configured_text = None
        self.after_calls = []
        self.after_cancel_calls = []
        self._next_id = 0

    def winfo_exists(self):
        return self.exists

    def configure(self, text):
        self.configured_text = text

    def after(self, _ms, _func):
        self._next_id += 1
        self.after_calls.append(self._next_id)
        return self._next_id

    def after_cancel(self, after_id):
        self.after_cancel_calls.append(after_id)


def test_start_shows_first_frame_and_schedules_next_tick():
    widget = FakeWidget()
    spinner = Spinner(widget, "בודק")
    spinner.start()
    assert widget.configured_text == f"{Spinner.FRAMES[0]} בודק"
    assert len(widget.after_calls) == 1


def test_manual_ticks_cycle_through_frames_in_order():
    widget = FakeWidget()
    spinner = Spinner(widget, "טוען")
    spinner.start()
    for expected_frame in Spinner.FRAMES[1:4]:
        spinner._tick()
        assert widget.configured_text == f"{expected_frame} טוען"


def test_stop_cancels_pending_after_call():
    widget = FakeWidget()
    spinner = Spinner(widget, "טוען")
    spinner.start()
    last_after_id = widget.after_calls[-1]
    spinner.stop()
    assert widget.after_cancel_calls == [last_after_id]


def test_tick_after_stop_does_not_update_text_or_reschedule():
    widget = FakeWidget()
    spinner = Spinner(widget, "טוען")
    spinner.start()
    spinner.stop()
    calls_before = len(widget.after_calls)
    text_before = widget.configured_text
    spinner._tick()
    assert widget.configured_text == text_before
    assert len(widget.after_calls) == calls_before


def test_tick_noop_when_widget_destroyed():
    widget = FakeWidget()
    spinner = Spinner(widget, "טוען")
    spinner.start()
    widget.exists = False
    calls_before = len(widget.after_calls)
    spinner._tick()
    assert len(widget.after_calls) == calls_before


def test_custom_text_template_respected():
    widget = FakeWidget()
    spinner = Spinner(widget, "X", text_template="[{spinner}] {label}...")
    spinner.start()
    assert widget.configured_text == f"[{Spinner.FRAMES[0]}] X..."
