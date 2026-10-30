# utils/media/game_detector.py
import os
import subprocess
try:
    import psutil
except ImportError:
    psutil = None

GAME_PROCESSES = {
    "gta5.exe": "Cyberpunk",
    "fivem_b2699_gta5.exe": "Cyberpunk",
    "fivem": "Cyberpunk",
    "minecraft.exe": "Green",
    "javaw.exe": "Green",
    "rocketleague.exe": "Rocket League",
}

# check_active_game() מחזיר את ערכי GAME_PROCESSES (שמות ערכות-נושא, כמו
# "Cyberpunk" ל-GTA5/FiveM) - שם תיאורי אמיתי למסך "שעות משחק" (item: personal
# stats dashboard) הוא מיפוי נפרד ומכוון, לא אותה מחרוזת: מציג "Cyberpunk" בתור
# שם המשחק היה מטעה (זה שם ערכת-נושא, לא שם המשחק בפועל).
GAME_DISPLAY_NAMES = {
    "Cyberpunk": "GTA5 / FiveM",
    "Green": "Minecraft",
    "Rocket League": "Rocket League",
}

# תוכנות רקע כבדות שייסגרו אוטומטית במצב טורבו לגיימינג
BANNED_BACKGROUND_PROCS = ["chrome.exe", "msedge.exe", "discord.exe"]
killed_processes_paths = []

def check_active_game(turbo_mode_active=False):
    """סורק תהליכים, משנה Theme ומפעיל מצב טורבו לניקוי RAM במידה ומשחקים"""
    global killed_processes_paths
    if not psutil:
        return None
    
    game_detected = None
    try:
        for proc in psutil.process_iter(['name', 'cmdline']):
            pname = proc.info['name'].lower() if proc.info['name'] else ""
            for game_key, theme_name in GAME_PROCESSES.items():
                if game_key not in pname:
                    continue
                if game_key == "javaw.exe":
                    # javaw.exe הוא ה-launcher הגנרי של כל אפליקציית Java (IntelliJ,
                    # Android Studio, Eclipse וכו'), לא רק מיינקראפט - בלי הבדיקה הזו
                    # פתיחת IDE במצב טורבו הייתה סוגרת כרום/דיסקורד בטעות.
                    cmdline = " ".join(proc.info.get("cmdline") or []).lower()
                    if "minecraft" not in cmdline:
                        continue
                game_detected = theme_name
                break
            if game_detected:
                break
    except Exception as e:
        print(f"[game_detector] שגיאה בסריקת תהליכים: {e}")

    # אם זוהה משחק ומצב טורבו פעיל – מנקים תוכנות רקע
    if game_detected and turbo_mode_active:
        try:
            for proc in psutil.process_iter(['name', 'exe']):
                if proc.info['name'] and proc.info['name'].lower() in BANNED_BACKGROUND_PROCS:
                    if proc.info['exe'] and proc.info['exe'] not in killed_processes_paths:
                        killed_processes_paths.append(proc.info['exe'])
                    proc.kill()
        except Exception as e:
            print(f"[game_detector] שגיאה בסגירת תוכנות רקע: {e}")
            
    return game_detected

def restore_background_processes():
    """מחזיר לפעולה את כל תוכנות הרקע שנסגרו אוטומטית כשיצאת מהמשחק"""
    global killed_processes_paths
    for exe_path in killed_processes_paths:
        if os.path.exists(exe_path):
            try:
                subprocess.Popen([exe_path], start_new_session=True)
            except Exception as e:
                print(f"[game_detector] שגיאה בהחזרת תהליך רקע ({exe_path}): {e}")
    killed_processes_paths.clear()