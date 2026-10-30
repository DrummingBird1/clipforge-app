# utils/shared/subprocess_flags.py
#
# Launcher.bat/Launcher.vbs עברו ל-pythonw.exe (בלי חלון קונסולה בכלל, כדי
# שלא ייפתח CMD כשמפעילים את האפליקציה - ראו Launcher.bat). אבל תת-תהליך
# שנפתח (subprocess.run/Popen) מתהליך-הורה בלי קונסולה משלו מקבל, כברירת
# מחדל בווינדוס, קונסולה חדשה משלו - שנפתחת ונסגרת מיד (הבהוב). זה קרה בכל
# מקום שה-GUI קורא ל-subprocess (nvidia-smi כל 1.5 שניות ב-utils/shared/hardware.py,
# כל "הרץ סקריפט"/"הפעל בוט" וכו') - צריך למנוע את זה במפורש בכל קריאה כזו.
#
# NO_WINDOW_FLAGS משמש כ-creationflags=NO_WINDOW_FLAGS בכל קריאת subprocess
# רלוונטית (0 בפלטפורמות שאינן Windows, שאין בהן את התופעה הזו בכלל).
import subprocess
import sys

NO_WINDOW_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
