# utils/shared/python_locator.py
#
# בגרסה הארוזה (PyInstaller onedir), sys.executable מצביע על Launcher.exe
# עצמו, לא על פרשן פייתון אמיתי. אומת בפועל: הרצת subprocess.Popen([sys.executable,
# "some_script.py", ...]) מתוך ה-exe הארוז לא מריצה את הסקריפט בכלל - היא פותחת
# עוד עותק מלא של אפליקציית ה-GUI (כי הנקודת-כניסה של ה-exe קבועה, הוא לא פרשן
# כללי שיודע "להריץ קובץ py שקיבל בארגומנטים"). זה שבר בשקט גם את "הרץ סקריפט"
# מהסיידבר (utils/shared/worker.py) וגם את "הפעל בוט" (ui/bot_tab.py) בגרסה הארוזה.
#
# כשרצים דרך Launcher.vbs / uv (הדרך המומלצת - ראו README), sys.executable
# הוא כבר פרשן פייתון אמיתי ועובד כרגיל בלי צורך בקובץ הזה כלל.

import os
import shutil
import sys


def get_python_executable():
    """מחזיר פרשן פייתון תקין להרצת תת-תהליכים, או None אם לא נמצא כזה.

    כשלא רצים כ-exe ארוז, זה פשוט sys.executable כרגיל. כשרצים כ-exe ארוז,
    קודם מחפש .venv מצורף (dist/Launcher/venv/ - ראו build_exe.py, מכיל
    את כל התלויות המדויקות מ-uv.lock, בדיוק מה ש-my_scripts צריכים), ורק אם
    הוא לא קיים נופל חזרה לחיפוש python/py גלובלי במערכת - שכמעט אף פעם לא
    כולל את tqdm/openpyxl/pydub וכו', כך שגם אם *נמצא* פרשן גלובלי, הרצת
    סקריפט שדורש חבילה כזו עדיין נכשלת (רק שעכשיו עם שגיאת import ברורה
    בקונסולה במקום כישלון שקט).

    בעבר, כשלא נמצא כלום, היה fallback ל-sys.executable - אבל בגרסה הארוזה
    sys.executable מצביע על Launcher.exe עצמו (לא פרשן כללי), אז
    fallback כזה היה "מצליח" בלי שגיאה ופשוט פותח עוד עותק מלא של ה-GUI
    במקום להריץ את הסקריפט - כישלון שקט לגמרי. עדיף להחזיר None ולתת לקורא
    להציג שגיאה ברורה."""
    if not getattr(sys, "frozen", False):
        return sys.executable

    bundled = os.path.join(os.path.dirname(sys.executable), "venv", "Scripts", "python.exe")
    if os.path.exists(bundled):
        return bundled

    for candidate in ("python", "py"):
        found = shutil.which(candidate)
        if found:
            return found
    return None
