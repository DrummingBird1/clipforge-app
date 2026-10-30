@echo off
setlocal enabledelayedexpansion
REM קובץ זה יושב תחת dev\ - חוזרים תחילה לשורש הפרויקט (%~dp0..), כי כל
REM הנתיבים למטה (.venv, data\logs, src\entrypoints\web_app.py) יחסיים לשורש.
cd /d "%~dp0.."
if not exist "data\logs" mkdir "data\logs" >nul 2>nul

REM כל הבדיקות למטה כותבות ללוג הזה בלבד, לא לקונסולה - WebLauncher.vbs מריץ
REM את הקובץ הזה מוסתר לגמרי (בלי חלון CMD בכלל), אז שום echo כאן לא נראה
REM לאף אחד. בלי pause על כשל - אותה סיבה בדיוק כמו _launcher_impl.bat.
set "LOG=data\logs\web_launcher.log"
set "TOKEN_FILE=data\web_app_token.txt"
REM 24.10.2026: אחרי ההעברה לתיקיות לפי נושא (data\.data_layout קיים) הטוקן ב-data\security\ - כמו data_paths.path():
REM החדש, אלא אם הוא קיים רק במקום הישן.
if exist "data\.data_layout" (
    if exist "data\security\web_app_token.txt" (
        set "TOKEN_FILE=data\security\web_app_token.txt"
    ) else if not exist "data\web_app_token.txt" (
        set "TOKEN_FILE=data\security\web_app_token.txt"
    )
)
set "LOCK_DIR=data\.web_launcher.lock"
echo [WebLauncher] starting > "%LOG%"

REM נועלים לפני כל בדיקה/החלטה, כדי למנוע מרוץ בין שתי הפעלות כמעט-בו-זמניות
REM (למשל לחיצה כפולה על הקיצור, כי בלי חלון גלוי קל לחשוב שהלחיצה הראשונה
REM לא עשתה כלום). mkdir אטומי ב-Windows - רק תהליך אחד יכול להצליח ליצור
REM תיקייה בשם נתון בו-זמנית, וזו בדיוק התכונה שהופכת אותה למנעול תקין כאן.
REM בלי הנעילה, שתי ההפעלות היו יכולות שתיהן לעבור את בדיקת "מישהו כבר מאזין
REM על 8878?" למטה *לפני* שאף אחת מהן הספיקה להאזין בפועל (uv sync + עליית
REM פייתון יכולים לקחת כמה שניות טובות) - ואז שתיהן ממשיכות ומפעילות pythonw.exe
REM משלהן.
set "LOCK_ATTEMPTS=0"
:acquire_lock
mkdir "%LOCK_DIR%" 2>nul
if not errorlevel 1 goto lock_acquired
set /a LOCK_ATTEMPTS+=1
if !LOCK_ATTEMPTS! GEQ 90 (
    REM 90 שניות - יותר מסך שני ה-timeout-ים למטה (30+30) בתוספת מרווח ל-uv
    REM sync ולעליית פייתון, אז הפעלה תקינה לא הייתה אמורה להחזיק את המנעול
    REM כל כך הרבה זמן. כנראה שריד מהפעלה שקרסה באמצע בלי לשחרר - מוחקים
    REM אותה בכוח וממשיכים, כדי לא להישאר תקועים לצמיתות על מנעול מת.
    echo [!] Stale lock at %LOCK_DIR% after 90s - removing it and continuing. >> "%LOG%"
    rmdir "%LOCK_DIR%" 2>nul
    goto acquire_lock
)
timeout /t 1 /nobreak >nul
goto acquire_lock
:lock_acquired

REM בדיקה: האם כבר יש שרת מאזין על 8878 (הפעלה קודמת שעדיין רצה ברקע, או
REM הפעלה מקבילה שזכתה במנעול לפנינו והספיקה כבר לעלות)? בלי הבדיקה הזו כל
REM הפעלה נוספת הייתה מריצה pythonw.exe יתום נוסף (רק תהליך אחד יכול להאזין
REM בפועל על הפורט, כל השאר תקועים בלי מטרה, צורכים זיכרון לצמיתות) - וגרוע
REM מזה: __main__ ב-web_app.py כותב טוקן גישה חדש ל-TOKEN_FILE מיד עם העלייה
REM (_persist_token), עוד לפני שהוא בכלל מנסה להאזין על הפורט; אם ההאזנה
REM נכשלת כי הפורט כבר תפוס ע"י ההפעלה הקודמת, הטוקן החדש שכבר נכתב דורס את
REM הטוקן התקף של השרת שכן ממשיך לרוץ - ומי שמנסה להיכנס אליו (כולל דרך
REM הקישור שכבר פתוח בדפדפן) נתקל ב-401 עד שמישהו יטרח להפעיל אותו מחדש.
echo [*] Checking whether a server is already listening on port 8878... >> "%LOG%"
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient('127.0.0.1', 8878); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [*] Server already running on port 8878 - reusing it instead of starting a new one. >> "%LOG%"
    rmdir "%LOCK_DIR%" 2>nul
    if exist "%TOKEN_FILE%" (
        set /p EXISTING_TOKEN=<"%TOKEN_FILE%"
        start "" "http://127.0.0.1:8878/?token=!EXISTING_TOKEN!"
    ) else (
        echo [!] %TOKEN_FILE% missing even though port 8878 is in use - opening without a token. >> "%LOG%"
        start "" "http://127.0.0.1:8878/"
    )
    exit /b 0
)

where uv >nul 2>>"%LOG%"
if errorlevel 1 (
    echo [!] uv not found on PATH. Install from https://github.com/astral-sh/uv >> "%LOG%"
    rmdir "%LOCK_DIR%" 2>nul
    exit /b 1
)

REM עובד גם אם מישהו מריץ WebLauncher.vbs בלי שהריץ קודם את Launcher.vbs
REM הרגיל - uv sync יוצר את .venv בעצמו אם היא לא קיימת.
echo [*] Syncing environment (uv sync)... >> "%LOG%"
uv sync >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [!] uv sync failed - see output above. >> "%LOG%"
    rmdir "%LOCK_DIR%" 2>nul
    exit /b 1
)

echo [*] Launching web server... >> "%LOG%"

REM pythonw.exe (לא python.exe) - כדי שלא ייפתח שום חלון קונסולה, בדיוק כמו
REM _launcher_impl.bat. web_app.py כבר קורא ל-setup_persistent_logging("web_app")
REM בעצמו (utils/logging_setup.py) - הפלט שלו נשמר ללוג הייעודי שלו, לא צריך
REM הפניית stdout/stderr ידנית כאן.
start "" /B ".venv\Scripts\pythonw.exe" src\entrypoints\web_app.py

REM ממתינים (עד 30 שניות, לא לנצח) שהטוקן ייכתב - טוקן חדש נוצר בכל הפעלה
REM של השרת (ראו _persist_token ב-web_app.py, כדי שקישור ישן שדלף לא יישאר
REM תקף לצמיתות) - לפני שאפשר בכלל לבנות את ה-URL עם הטוקן הנכון.
set "ATTEMPTS=0"
:wait_token
if exist "%TOKEN_FILE%" goto token_ready
set /a ATTEMPTS+=1
if !ATTEMPTS! GEQ 30 (
    echo [!] Timed out waiting for %TOKEN_FILE% to appear. >> "%LOG%"
    rmdir "%LOCK_DIR%" 2>nul
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_token
:token_ready

REM ואז (עד 30 שניות נוספות) שהשרת עצמו יתחיל להאזין בפועל על 8878 - אחרת
REM פתיחת הדפדפן הייתה נתקלת ב-"connection refused" ברגע הראשון. המנעול
REM נשאר תפוס עד כאן בכוונה (לא משוחרר מיד אחרי start /B למעלה) - אחרת הפעלה
REM מקבילה שממתינה עלינו הייתה יכולה לבדוק את הפורט ברגע שבו pythonw.exe כבר
REM רץ אבל עדיין לא הספיק להאזין בפועל, לא לראות שום דבר מאזין, ולהפעיל
REM pythonw.exe משלה בכל זאת.
set "ATTEMPTS=0"
:wait_port
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient('127.0.0.1', 8878); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto port_ready
set /a ATTEMPTS+=1
if !ATTEMPTS! GEQ 30 (
    echo [!] Timed out waiting for the web server to listen on port 8878. >> "%LOG%"
    rmdir "%LOCK_DIR%" 2>nul
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_port
:port_ready

rmdir "%LOCK_DIR%" 2>nul

set /p TOKEN=<"%TOKEN_FILE%"
echo [*] Opening browser... >> "%LOG%"
start "" "http://127.0.0.1:8878/?token=%TOKEN%"
