# tests/media_support.py
#
# טסטים שמרנדרים באמת (ffmpeg אמיתי) - מדלגים כשאין ffmpeg בסביבה. במחשב הפיתוח יש ffmpeg/bin/
# בתוך הפרויקט; במכונת ה-CI של GitHub אין, ושם הטסטים האלה נכשלו עם WinError 2 (קובץ לא נמצא).
import os
import shutil

import pytest

from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe


def _exists(exe):
    return (os.path.isabs(exe) and os.path.exists(exe)) or bool(shutil.which(exe))


def ffmpeg_available():
    return _exists(get_ffmpeg_exe()) and _exists(get_ffprobe_exe())


needs_ffmpeg = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg/ffprobe לא זמינים בסביבה הזו")
