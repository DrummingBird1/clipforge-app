# build_exe.py
#
# אורז את gui_manager.pyw כ-exe עצמאי עם PyInstaller (מצב onedir - יותר אמין
# ומהיר לבנייה מ-onefile עבור אפליקציה עם כל כך הרבה תלויות: customtkinter,
# tkinterdnd2, cv2, faster-whisper וכו').
#
# הרצה: python dev/build_exe.py (או uv run python dev/build_exe.py) מתוך שורש הפרויקט
# התוצר ייווצר תחת dist/Launcher/
#
# "הרץ סקריפט" (מהסיידבר) ו"הפעל בוט" מריצים תת-תהליכים חדשים (utils/shared/worker.py,
# ui/bot_tab.py) - בגרסה הארוזה sys.executable מצביע על Launcher.exe עצמו,
# לא על פרשן פייתון. בעבר utils/shared/python_locator.py היה נופל חזרה על "python"/"py"
# גלובליים במערכת - שכמעט אף פעם לא כוללים את tqdm/openpyxl/pydub וכו' שה-
# my_scripts צריכים, אז ההרצה נכשלה גם כשנמצא פרשן. הפתרון: מעתיקים את ה-.venv
# עצמו (עם כל התלויות המדויקות מ-uv.lock) לתוך dist/Launcher/venv/, ו-
# python_locator.py מחפש אותו קודם, לפני שהוא נופל חזרה על משהו גלובלי.

import os
import shutil
import sys
import PyInstaller.__main__

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(BASE_DIR, "dist", "Launcher")
SOURCE_VENV = os.path.join(BASE_DIR, ".venv")
BUNDLED_VENV = os.path.join(DIST_DIR, "venv")
SRC_DIR = os.path.join(BASE_DIR, "src")
# ראו dev/generate_app_icon.py - מריצים אותו פעם אחת מראש כדי שהקובץ הזה יהיה קיים.
APP_ICON_ICO = os.path.join(BASE_DIR, "assets", "app_icon.ico")
# overlay.png כבר לא בריפו (16.10.2026 - הלוגו נבחר בהגדרות Rocket Shorts); נארז רק אם קיים, אחרת PyInstaller נכשל
OVERLAY_PNG = os.path.join(BASE_DIR, "assets", "overlay.png")

# src/entrypoints/gui_manager.pyw מייבא "utils.*"/"ui.*"/"cogs.*" מתוך src/, לא
# מ-src/entrypoints/ עצמה - --paths אומר ל-PyInstaller לחפש גם שם בזמן ניתוח
# הייבואים (לפני שקוד המקור עבר תחת src/, gui_manager.pyw ישב בשורש עצמו
# ופייתון כבר מצא את החבילות האלה שם ממילא).
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

PyInstaller.__main__.run([
    os.path.join(SRC_DIR, "entrypoints", "gui_manager.pyw"),
    "--name=Launcher",
    "--onedir",
    "--windowed",
    "--noconfirm",
    "--clean",
    f"--icon={APP_ICON_ICO}",
    f"--paths={SRC_DIR}",
    # שם ה-.spec יוצא לתוך dist/build/ במקום לבלגן את שורש הפרויקט בתיקיית build/ נפרדת
    f"--specpath={os.path.join(BASE_DIR, 'dist', 'build')}",
    # קבצים/תיקיות שנדרשים בזמן ריצה ולא רק בזמן import.
    # my_scripts היה חסר כאן לגמרי - כלומר ה-exe הארוז לא הכיל אף סקריפט אוטומציה
    # (הסיידבר היה נטען עם רשימה ריקה, ו"הרץ סקריפט" לא עבד בכלל בגרסה הארוזה).
    *([f"--add-data={OVERLAY_PNG};assets"] if os.path.isfile(OVERLAY_PNG) else []),
    f"--add-data={APP_ICON_ICO};assets",
    f"--add-data={os.path.join(BASE_DIR, 'assets', 'app_icon.png')};assets",
    f"--add-data={os.path.join(SRC_DIR, 'cogs')};cogs",
    f"--add-data={os.path.join(SRC_DIR, 'ui')};ui",
    f"--add-data={os.path.join(BASE_DIR, 'my_scripts')};my_scripts",
    f"--add-data={os.path.join(BASE_DIR, 'data', 'config.example.json')};data",
    f"--add-data={os.path.join(BASE_DIR, 'data', 'rocket_settings.example.json')};data",
    # customtkinter דורש את קבצי ה-theme/assets שלו עצמו בפנים
    "--collect-data=customtkinter",
    "--collect-data=tkinterdnd2",
    "--hidden-import=PIL._tkinter_finder",
])

if os.path.isdir(SOURCE_VENV):
    print(f"[*] מעתיק את .venv ל-{BUNDLED_VENV} (כדי שהרצת סקריפטים/בוט תעבוד גם בלי Python גלובלי)...")
    if os.path.isdir(BUNDLED_VENV):
        shutil.rmtree(BUNDLED_VENV)
    shutil.copytree(SOURCE_VENV, BUNDLED_VENV)
    print("[*] הועתק בהצלחה.")
else:
    print(f"[!] לא נמצאה .venv ב-{SOURCE_VENV} - דילוג על צירוף פרשן Python. "
          "הרצת סקריפטים/בוט מה-exe הארוז תדרוש Python גלובלי עם כל התלויות מותקנות.")
