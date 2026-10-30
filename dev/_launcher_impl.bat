@echo off
setlocal
REM קובץ זה יושב תחת dev\ - חוזרים תחילה לשורש הפרויקט (%~dp0..), כי כל
REM הנתיבים למטה (.venv, data\logs, src\entrypoints\gui_manager.pyw) יחסיים לשורש.
cd /d "%~dp0.."
if not exist "data\logs" mkdir "data\logs" >nul 2>nul

REM כל הבדיקות למטה כותבות ללוג הזה בלבד, לא לקונסולה - Launcher.vbs מריץ את
REM הקובץ הזה מוסתר לגמרי (בלי חלון CMD בכלל), אז שום echo כאן לא נראה לאף אחד.
REM בכוונה בלי pause על כשל (בניגוד לגרסה הקודמת) - pause היה תוקע את התהליך
REM לנצח על המתנה-להקשה שאף אחד לא יכול לתת לו כשהחלון מוסתר. Launcher.vbs
REM מציג הודעת שגיאה (MsgBox) לפי קוד היציאה, ומפנה ללוג הזה לפרטים.
set "LOG=data\logs\launcher.log"
echo [Launcher] starting > "%LOG%"

where uv >nul 2>>"%LOG%"
if errorlevel 1 (
    echo [!] uv not found on PATH. Install from https://github.com/astral-sh/uv >> "%LOG%"
    exit /b 1
)

REM uv sync קורא מ-pyproject.toml + uv.lock - יוצר את .venv בעצמו אם היא לא
REM קיימת, ומוודא שהיא תואמת בדיוק ל-lockfile בכל הפעלה.
echo [*] Syncing environment (uv sync)... >> "%LOG%"
uv sync >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [!] uv sync failed - see output above. >> "%LOG%"
    exit /b 1
)

echo [*] Launching GUI... >> "%LOG%"

REM pythonw.exe (לא python.exe) - כדי שלא ייפתח שום חלון קונסולה בשביל ה-GUI
REM עצמו, גם אם מישהו מריץ את הקובץ הזה ישירות (לא דרך Launcher.vbs).
REM start /B מנתק את התהליך - בלי זה, cmd.exe (ולכן גם Launcher.vbs שממתין לו)
REM היה נשאר "תקוע" כל עוד ה-GUI פתוח, במקום לסיים מיד אחרי ההפעלה.
start "" /B ".venv\Scripts\pythonw.exe" src\entrypoints\gui_manager.pyw
