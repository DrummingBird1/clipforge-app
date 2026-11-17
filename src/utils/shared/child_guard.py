# utils/shared/child_guard.py
#
# 17.11.2026 (ClipForge 2.0.1): תהליך-ילד שמת יחד עם האפליקציה. ב-2.0.0 ffmpeg של ההקלטה נשאר לרוץ כשהשרת נסגר בלי יציאה
# מסודרת (חלון שנסגר, "סיים משימה", קריסה): replay buffer המשיך לכתוב מקטעים בלי שאף אחד ימחק אותם, עד שהדיסק מתמלא
# (בבדיקה: שני תהליכים יתומים כתבו 10GB ב-19 שעות), והמשיך להחזיק את כרטיס הלכידה והמצלמה.
#
# Windows Job Object עם KILL_ON_JOB_CLOSE: כל תהליך שמשויך ל-job נהרג כשה-handle האחרון שלו נסגר - כלומר כשהתהליך הזה מת,
# בכל דרך. ה-job נוצר פעם אחת ונשאר פתוח לכל חיי התהליך. בלי Windows, או כשהשיוך נכשל - False, והקורא ממשיך כמו קודם.
import sys
import threading
from typing import Any

_lock = threading.Lock()
_job: Any = None

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def _create_job() -> Any:
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                         "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        return None
    info = Extended()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)):
        return None
    return kernel32, handle


def tie_to_this_process(process: Any) -> bool:
    """משייך את process (subprocess.Popen) ל-job של התהליך הזה. True כשהילד ימות יחד איתנו."""
    global _job
    if sys.platform != "win32":
        return False
    handle = getattr(process, "_handle", None)
    if handle is None:
        return False
    try:
        with _lock:
            if _job is None:
                _job = _create_job() or False
            if not _job:
                return False
            kernel32, job = _job
        return bool(kernel32.AssignProcessToJobObject(job, int(handle)))
    except Exception:
        return False
