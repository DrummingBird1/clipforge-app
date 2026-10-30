# tests/infra/test_subprocess_flags.py
#
# רגרסיה: Launcher.vbs מריץ את ה-GUI דרך pythonw.exe (בלי קונסולה בכלל) - כל
# subprocess.run/Popen שנקרא מהתהליך הזה (או מסקריפט שהוא מריץ, שגם הוא בלי
# קונסולה) פותח קונסולה חדשה משלו כברירת מחדל בווינדוס, שנפתחת ונסגרת מיד
# (הבהוב) - למשל nvidia-smi כל 1.5-2 שניות ב-utils/shared/hardware.py. NO_WINDOW_FLAGS
# חייב להימנע מזה.
import sys


from utils.shared.subprocess_flags import NO_WINDOW_FLAGS


def test_no_window_flags_is_nonzero_on_windows():
    if sys.platform == "win32":
        assert NO_WINDOW_FLAGS != 0


def test_no_window_flags_is_zero_off_windows():
    if sys.platform != "win32":
        assert NO_WINDOW_FLAGS == 0
