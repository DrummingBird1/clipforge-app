# tests/bot/test_obs_replay_watcher.py
#
# בודק את החלקים החדשים של my_scripts/stream/obs_replay_watcher.py (item:
# קיצור "Clip That!") שניתן לבדוק בלי OBS אמיתי - שליחת בקשת SaveReplayBuffer
# על חיבור websocket מדומה, ותזמון-בטוח-ל-thread (run_coroutine_threadsafe)
# מ-thread הרקע של חבילת keyboard. שאר הקובץ (watch() המלאה, חיבור websocket
# אמיתי) כבר מתועד כלא-ניתן-לבדיקה כאן - אין OBS מותקן בסביבה הזו.
import asyncio
import time
from types import SimpleNamespace


from my_scripts.stream.obs_replay_watcher import schedule_replay_save, trigger_save_replay_buffer


def _run(coro):
    return asyncio.run(coro)


class _FakeWs:
    def __init__(self, result=True, comment=None, exception=None):
        self._result = result
        self._comment = comment
        self._exception = exception
        self.calls = []

    async def call(self, request):
        self.calls.append(request)
        if self._exception is not None:
            raise self._exception
        return SimpleNamespace(requestStatus=SimpleNamespace(result=self._result, comment=self._comment))


def test_trigger_save_replay_buffer_sends_the_correct_request_type(capsys):
    ws = _FakeWs(result=True)

    _run(trigger_save_replay_buffer(ws))

    assert len(ws.calls) == 1
    assert ws.calls[0].requestType == "SaveReplayBuffer"
    assert "בהצלחה" in capsys.readouterr().out


def test_trigger_save_replay_buffer_reports_when_obs_rejects_the_request(capsys):
    ws = _FakeWs(result=False, comment="Replay buffer not active")

    _run(trigger_save_replay_buffer(ws))

    assert "Replay buffer not active" in capsys.readouterr().out


def test_trigger_save_replay_buffer_swallows_connection_errors(capsys):
    ws = _FakeWs(exception=ConnectionError("OBS not reachable"))

    _run(trigger_save_replay_buffer(ws))  # לא אמור לזרוק

    assert "נכשלה" in capsys.readouterr().out


def test_schedule_replay_save_runs_the_coroutine_on_the_given_loop_from_another_thread():
    # מדמה בדיוק את התרחיש האמיתי - הקריאה ל-schedule_replay_save() מגיעה
    # מ-thread שאינו thread ה-event loop (בפועל: thread הרקע של חבילת
    # keyboard) - run_coroutine_threadsafe הוא מה שאמור לגשר על זה בבטחה.
    import threading

    ws = _FakeWs(result=True)

    async def scenario():
        loop = asyncio.get_running_loop()
        thread = threading.Thread(target=schedule_replay_save, args=(loop, ws))
        thread.start()
        thread.join(timeout=2)
        # נותן לקורוטינה שתוזמנה על הלולאה הרצה הזדמנות אמיתית לרוץ
        deadline = time.time() + 2
        while time.time() < deadline and not ws.calls:
            await asyncio.sleep(0.02)

    _run(scenario())

    assert len(ws.calls) == 1
    assert ws.calls[0].requestType == "SaveReplayBuffer"
