# tests/infra/test_crash_supervisor.py


from utils.shared.crash_supervisor import record_crash_and_check_giveup


def test_single_crash_does_not_give_up():
    updated, give_up = record_crash_and_check_giveup([], now=100.0, window_seconds=300, max_restarts=5)
    assert updated == [100.0]
    assert give_up is False


def test_old_crashes_outside_window_are_dropped():
    old_crashes = [0.0, 10.0]
    updated, give_up = record_crash_and_check_giveup(old_crashes, now=1000.0, window_seconds=300, max_restarts=5)
    assert updated == [1000.0]
    assert give_up is False


def test_gives_up_when_exceeding_max_restarts_within_window():
    crashes = [100.0, 110.0, 120.0, 130.0, 140.0]  # 5 קריסות קודמות
    updated, give_up = record_crash_and_check_giveup(crashes, now=150.0, window_seconds=300, max_restarts=5)
    assert len(updated) == 6
    assert give_up is True


def test_does_not_give_up_at_exactly_max_restarts():
    crashes = [100.0, 110.0, 120.0, 130.0]  # 4 קודמות + 1 חדשה = 5, לא חורג מ-5
    updated, give_up = record_crash_and_check_giveup(crashes, now=140.0, window_seconds=300, max_restarts=5)
    assert len(updated) == 5
    assert give_up is False


def test_spread_out_crashes_never_give_up():
    # קריסה כל 10 דקות (מחוץ לחלון של 5 דקות) - אף פעם לא יותר מקריסה אחת בחלון
    crash_timestamps = []
    now = 0.0
    for _ in range(10):
        crash_timestamps, give_up = record_crash_and_check_giveup(crash_timestamps, now, window_seconds=300, max_restarts=5)
        assert give_up is False
        now += 600.0
