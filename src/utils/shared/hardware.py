# utils/shared/hardware.py
import shutil
import os
import subprocess
import threading
import time

from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

try:
    import psutil
except ImportError:
    psutil = None

# היסטוריית ביצועים לצורך רישום הגרפים הנעים - 120 דגימות (כ-3 דקות בקצב
# הרענון של הסיידבר, 1.5 שניות לדגימה) כדי שגרף usage-over-time (item 17)
# יראה משהו משמעותי, לא רק כמה שניות אחרונות. הוגדל מ-20 (שמספיק בקושי
# ל-sparkline הטקסטואלי הקיים, אבל לא לגרף אמיתי).
HISTORY_LENGTH = 120
cpu_history = [0] * HISTORY_LENGTH
ram_history = [0] * HISTORY_LENGTH
gpu_history = [0] * HISTORY_LENGTH
vram_history = [0] * HISTORY_LENGTH

# --- ניטור GPU (NVIDIA בלבד, דרך nvidia-smi) ---
# רץ ב-thread רקע נפרד כי subprocess.run על nvidia-smi לוקח עשרות/מאות מ"ש -
# קריאה ישירה מתוך _update_hw_loop של הסיידבר (שרץ על ה-Tk mainloop כל 1.5 שניות)
# הייתה תוקעת את כל ה-GUI לרגע בכל רענון.
_gpu_lock = threading.Lock()
_gpu_cache = {"util": None, "vram_pct": None, "encoder_pct": None}
_gpu_available = None  # None = עוד לא נבדק, False = אין GPU של NVIDIA / nvidia-smi לא נמצא
_gpu_poll_started = False


def _gpu_poll_loop():
    global _gpu_available
    while True:
        try:
            # utilization.gpu (מנועי CUDA/shader) הוא מד נפרד לגמרי מ-
            # utilization.encoder (ASIC ה-NVENC הייעודי) - רינדור שכולו
            # delogo/scale/overlay ב-CPU ורק הקידוד עצמו ב-GPU יראה
            # utilization.gpu נמוך גם כשה-NVENC בפועל עסוק לגמרי.
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,utilization.encoder,memory.used,memory.total", "--format=csv,noheader,nounits"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=2,
                creationflags=NO_WINDOW_FLAGS
            )
            if result.returncode == 0 and result.stdout.strip():
                util_str, encoder_str, used_str, total_str = [p.strip() for p in result.stdout.strip().splitlines()[0].split(",")]
                total = float(total_str)
                util = float(util_str)
                encoder_pct = float(encoder_str)
                vram_pct = (float(used_str) / total * 100) if total > 0 else 0.0
                with _gpu_lock:
                    _gpu_cache["util"] = util
                    _gpu_cache["vram_pct"] = vram_pct
                    _gpu_cache["encoder_pct"] = encoder_pct
                    gpu_history.pop(0)
                    gpu_history.append(util)
                    vram_history.pop(0)
                    vram_history.append(vram_pct)
                _gpu_available = True
            else:
                _gpu_available = False
                return
        except FileNotFoundError:
            _gpu_available = False
            return
        except Exception:
            pass
        time.sleep(2)


def get_gpu_stats():
    """מחזיר (אחוז ניצול GPU כללי, אחוז ניצול VRAM, אחוז ניצול מנוע ה-NVENC)
    עבור GPU של NVIDIA, מ-cache שמתעדכן ברקע כל 2 שניות. שלושתם None אם אין
    GPU של NVIDIA (nvidia-smi לא נמצא). ה-encoder הוא המד הרלוונטי בפועל
    בזמן רינדור עם קידוד hevc_nvenc/av1_nvenc - ה-util הכללי יכול להישאר
    נמוך גם כשה-NVENC עסוק לגמרי, ראו ההערה ב-_gpu_poll_loop."""
    global _gpu_poll_started
    if _gpu_available is False:
        return None, None, None
    if not _gpu_poll_started:
        _gpu_poll_started = True
        threading.Thread(target=_gpu_poll_loop, daemon=True).start()
    with _gpu_lock:
        return _gpu_cache["util"], _gpu_cache["vram_pct"], _gpu_cache["encoder_pct"]

def get_system_stats():
    """מחזיר אחוזי ניצול מעבד וזיכרון בצורה בטוחה ומעדכן היסטוריה"""
    global cpu_history, ram_history
    if not psutil:
        return 0, 0
    try:
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent

        # עדכון מערכי ההיסטוריה (הזזת אינדקסים)
        cpu_history.pop(0)
        cpu_history.append(cpu)
        ram_history.pop(0)
        ram_history.append(ram)

        # רישום ל-DB לצורך גרף "24 שעות אחרונות" (item: historical hardware usage
        # graph) - מעבר לזיכרון בלבד (~3 דקות, ראו cpu_history למעלה). קורא ל-
        # get_gpu_stats() (לא ל-nvidia-smi ישירות) - זה רק קורא מ-cache שכבר
        # מתעדכן ברקע, לא מפעיל עוד קריאת nvidia-smi. record_sample עצמו דוגם
        # לכל היותר פעם ב-60 שניות, אז זה בטוח לקרוא לו מכאן בכל טיק.
        try:
            from utils.shared import hardware_history
            gpu, vram, encoder = get_gpu_stats()
            hardware_history.record_sample(cpu, ram, gpu, vram, encoder)
        except Exception:
            pass  # רישום היסטוריה הוא תוספת אופציונלית - לא אמור להפיל את קריאת הסטטוס עצמה

        return cpu, ram
    except Exception as e:
        print(f"[hardware] שגיאה בקריאת ניצולת מערכת: {e}")
        return 0, 0

def get_performance_history():
    """מחזיר את ההיסטוריה הנוכחית של ה-CPU וה-RAM לצורך ציור הגרף"""
    return cpu_history, ram_history


def get_gpu_performance_history():
    """מחזיר את היסטוריית ה-GPU/VRAM (item 17) - תחת אותו _gpu_lock ששומר על
    _gpu_cache, כדי לא לקרוא רשימה שנמצאת באמצע עדכון מ-_gpu_poll_loop.
    מחזיר עותקים (לא את הרשימות המקוריות) כדי שלא ישתנו מתחת לקורא בין
    קריאה לקריאה תוך כדי ציור הגרף."""
    with _gpu_lock:
        return list(gpu_history), list(vram_history)

def get_disk_status(target_path):
    """מחזיר את אחוז הדיסק המנוצל ואת השטח הפנוי ב-GB"""
    if not target_path or not os.path.exists(target_path):
        target_path = os.path.abspath(__file__)
    try:
        total, used, free = shutil.disk_usage(target_path)
        used_percentage = used / total
        free_gb = free / (1024**3)
        return used_percentage, free_gb
    except Exception as e:
        print(f"[hardware] שגיאה בקריאת נתוני דיסק: {e}")
        return 0.0, 0.0