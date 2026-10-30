# utils/shared/sound.py
import sys
import threading
import winsound

def _beep_thread(freq, duration):
    if sys.platform == "win32":
        try:
            winsound.Beep(freq, duration)
        except Exception:
            pass

def play_board_sound(freq, duration):
    """מנגן צליל ב-Thread נפרד כדי למנוע תקיעה של ה-UI"""
    threading.Thread(target=_beep_thread, args=(freq, duration), daemon=True).start()

def play_system_sound(sound_type):
    """צלילי מערכת להפעלה, הצלחה או שגיאה"""
    if sound_type == "success":
        play_board_sound(523, 80)
        play_board_sound(659, 80)
        play_board_sound(784, 80)
    elif sound_type == "error":
        play_board_sound(220, 120)
        play_board_sound(147, 250)
    elif sound_type == "start":
        play_board_sound(587, 80)
        play_board_sound(880, 100)