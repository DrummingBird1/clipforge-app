# utils/shared/i18n.py
#
# מנגנון תרגום פשוט: t(hebrew_text) מחזיר את התרגום לאנגלית אם state.language == "en",
# אחרת מחזיר את הטקסט העברי המקורי כמו שהוא. המפתח במילון התרגומים הוא תמיד
# הטקסט העברי המקורי (לא מזהה סמלי מופשט) - כך שאין צורך להמציא/לתחזק שמות
# מפתח נפרדים, וקל לראות בקוד בדיוק אילו טקסטים מתורגמים.
#
# עבור טקסט דינמי (עם ערכים משתנים כמו אחוזי CPU) - קוראים ל-t() עם התבנית
# בלבד (למשל "CPU: {pct}%") ומעצבים איתה אחרי, כדי שהתרגום יקרה על התבנית
# ולא על המחרוזת הסופית שכבר כוללת מספר ספציפי:
#     t("נמצאו {n} קבצים").format(n=total_files)
#
# מעבר שפה דורש הפעלה מחדש של האפליקציה - אותה מוסכמה בדיוק כמו מעבר Dark/Light
# ב-utils/shared/state.py (אין רענון חי של widgets קיימים בלי לבנות מחדש את כל העץ).

import re

from utils.shared.state import state

# מפצה על באג ידוע בפריסת הטקסט של Tk (הרכיב הגרפי הבסיסי של Tkinter/
# customtkinter, לא קוד שלנו): Tcl/Tk הרגיל (אומת: אין הטמעת bidi משלו,
# tk.call('info','patchlevel') -> 8.6.12 רגיל) לפעמים מציג טקסט עברי טהור
# (בלי אותיות/ספרות לועזיות) עם סדר המילים הפוך על המסך - "זיהוי וחיתוך
# קליפים אוטומטי" מוצג כ"אוטומטי קליפים וחיתוך זיהוי". האותיות *בתוך* כל
# מילה מוצגות נכון (כנראה שכבת עיצוב הגופנים של Windows כבר מטפלת בכיוון
# ברמת התו), והתופעה לא קרתה במחרוזות מעורבות עברית+אנגלית (כמו "פרסום
# Rocket Shorts") - שם סדר המילים כבר מוצג נכון. לכן מתקנים (הופכים את סדר
# המילים המופרדות ברווח) רק במקרה הטהור, כדי לא לשבור את מה שכבר עובד.
_LATIN_OR_DIGIT_PATTERN = re.compile(r"[A-Za-z0-9]")


def fix_hebrew_word_order(text):
    if not text or _LATIN_OR_DIGIT_PATTERN.search(text):
        return text
    words = text.split(" ")
    if len(words) < 2:
        return text
    return " ".join(reversed(words))


TRANSLATIONS = {
    # --- כללי / חלון ראשי ---
    "⚡ LAUNCHER - CONTROL CENTER PRO ⚡": "⚡ LAUNCHER - CONTROL CENTER PRO ⚡",
    "🚀 הסטודיו שלי": "🚀 My Studio",
    "🔍 חפש סקריפט...": "🔍 Search scripts...",
    "בחר סקריפט להפעלה": "Select a script to run",
    "⭐ מועדפים": "⭐ Favorites",
    "📋 הצג את כל הסקריפטים": "📋 Show all scripts",
    "📋 הצג פחות": "📋 Show less",
    "נא לבחור סקריפט מהרשימה": "Please select a script from the list",
    "סקריפט: {name} ({filename})": "Script: {name} ({filename})",
    "> נבחר להרצה: {name}.": "> Selected to run: {name}.",
    "מערכת בהמתנה": "System idle",
    "מוכן": "Ready",

    # --- קטגוריות סיידבר ---
    "🎬 פייפליין וידאו": "🎬 Video Pipeline",
    "📡 סטרימינג": "📡 Streaming",
    "🎮 Steam": "🎮 Steam",
    "🛠️ כלי עזר": "🛠️ Utilities",

    # --- HW monitor ---
    "CPU: {pct}%  [{spark}]": "CPU: {pct}%  [{spark}]",
    "RAM: {pct}%  [{spark}]": "RAM: {pct}%  [{spark}]",
    "GPU: {pct}%": "GPU: {pct}%",
    "GPU: -": "GPU: -",
    "GPU: לא זמין (אין NVIDIA)": "GPU: unavailable (no NVIDIA)",
    "VRAM: -": "VRAM: -",
    "VRAM: {pct}%": "VRAM: {pct}%",

    # --- Command Palette ---
    "🔍 חיפוש פקודות וסקריפטים": "🔍 Search Commands & Scripts",
    "חפש סקריפט... (Ctrl+K)": "Search scripts... (Ctrl+K)",

    # --- טאבים ---
    "🎮 לוח בקרה": "🎮 Dashboard",
    "🤖 ניהול דיסקורד": "🤖 Discord Management",
    "🎨 עיצוב וממשק": "🎨 Design & Interface",
    "⚙️ הגדרות": "⚙️ Settings",
    "🔊 סאונדבורד": "🔊 Soundboard",
    "🌐 הגדרות גלובליות": "🌐 Global Settings",
    "📊 סטטיסטיקות": "📊 Statistics",
    "שחזר חלון": "Restore Window",
    "סגור לגמרי": "Close Completely",

    # --- Dashboard ---
    "> מערכת מודולרית מוכנה לפעולה. בחר סקריפט.": "> Modular system ready. Select a script.",
    "▶ הרץ סקריפט": "▶ Run Script",
    "▶ מריץ את {name}...": "▶ Running {name}...",
    "🛑 עצור": "🛑 Stop",
    "ממתין בתור": "Queued",
    "ריצה פעילה ברקע": "Running in background",
    "⚠️ גיבוי אוטומטי נכשל: {error}": "⚠️ Automatic backup failed: {error}",
    "💾 גיבוי אוטומטי הושלם - {n} קבצים הועתקו ל-{path}": "💾 Automatic backup complete - {n} files copied to {path}",
    "{sec} שניות": "{sec}s",
    "{minutes} דקות": "{minutes}m",
    "הסתיים בהצלחה": "completed successfully",
    "נכשל": "failed",
    "💤 מצב לילה - כיבוי אוטומטי": "💤 Night Mode - Automatic Shutdown",
    "🛑 בטל כיבוי": "🛑 Cancel Shutdown",
    "הריצה הסתיימה בהצלחה.\nהמחשב יכבה בעוד {sec} שניות.": "The run completed successfully.\nThe computer will shut down in {sec} seconds.",
    "🗂️ {n} משימות ממתינות בתור": "🗂️ {n} tasks queued",
    "🗂️ {n} בתור ({light} קל, {heavy} כבד)": "🗂️ {n} queued ({light} light, {heavy} heavy)",
    "⚠️ מנעול רינדור תקוע (PID {pid}, {age})": "⚠️ Render lock stuck (PID {pid}, {age})",
    "🔒 רינדור אחר תפוס (PID {pid}, {age})": "🔒 Another render in progress (PID {pid}, {age})",
    "{icon} **{name}** {status} (משך ריצה: {duration})": "{icon} **{name}** {status} (run time: {duration})",
    "{status} - משך ריצה: {duration}": "{status} - run time: {duration}",

    # --- Settings tab ---
    "⚙️ הגדרות עבור הסקריפט הנבחר": "⚙️ Settings for the selected script",
    "⚙️ הגדרות עבור {name} ({filename})": "⚙️ Settings for {name} ({filename})",
    "אין תיאור זמין לסקריפט זה.": "No description available for this script.",
    "📂 בחר תיקיית סרטוני גיימפליי": "📂 Choose gameplay footage folder",
    "לא נבחרה תיקיית מקור": "No source folder selected",
    "לא נבחרה תיקייה": "No folder selected",

    # --- Rocket Settings panel ---
    "🎬 הגדרות נתיבים, מונה ופרופילים עבור Rocket Shorts": "🎬 Paths, counter, and quality profiles for Rocket Shorts",
    "תיקיית קליפים (Import):": "Clips folder (Import):",
    "תיקיית ייצוא (Export):": "Export folder:",
    "תמונת Overlay:": "Overlay image:",
    "עיון...": "Browse...",
    "גרור לכאן תיקייה...": "Drag a folder here...",
    "מספר מונה קליפ נוכחי (#):": "Current clip counter (#):",
    "פרופיל איכות ואיכות וידאו:": "Quality profile:",
    "ריקאפ שבועי אוטומטי (דרך הבוט):": "Automatic weekly recap (via bot):",
    "הפעל": "Enable",
    "💾 שמור הגדרות Rocket": "💾 Save Rocket Settings",
    "🌊 תצוגת גל קול": "🌊 Waveform Preview",
    "🚀 Max Quality (HEVC NVENC, P7)": "🚀 Max Quality (HEVC NVENC, P7)",
    "📱 Balanced (HEVC NVENC, P5)": "📱 Balanced (HEVC NVENC, P5)",
    "⚡ Fast Render (HEVC NVENC, P1)": "⚡ Fast Render (HEVC NVENC, P1)",
    "🧪 AV1 Next-Gen (NVENC, P5)": "🧪 AV1 Next-Gen (NVENC, P5)",
    "💻 CPU Fallback (H.264, Medium)": "💻 CPU Fallback (H.264, Medium)",
    "ערוץ קול לזיהוי חברים (ריק=כבוי):": "Voice channel for friend detection (empty=off):",
    "מזהה ערוץ קול": "Voice channel ID",
    "שני": "Mon", "שלישי": "Tue", "רביעי": "Wed", "חמישי": "Thu", "שישי": "Fri", "שבת": "Sat", "ראשון": "Sun",

    # --- Global settings ---
    "🎨 שליטה ברכיבי עיצוב, אפקטים וממשק": "🎨 Design, effects, and interface controls",
    "💽 כונן עבודה מקור:": "💽 Source working drive:",
    "סורק...": "Scanning...",
    "כונן חיצוני / NAS": "External drive / NAS",
    "🔥 מצב טורבו (סגירת תוכנות רקע במשחק)": "🔥 Turbo Mode (close background apps during games)",
    "📂 בחר תיקיית גיבוי": "📂 Choose backup folder",
    "גיבוי תוצרים אוטומטי לתיקייה שנבחרה בסיום ריצה": "Automatically back up output to the selected folder when a run finishes",
    "💤 מצב לילה (כיבוי אוטומטי בסיום)": "💤 Night Mode (auto shutdown when done)",
    "💾 שמור הגדרות גלובליות": "💾 Save Global Settings",
    "{gb} GB פנוי": "{gb} GB free",
    "🌗 מצב עיצוב (נדרשת הפעלה מחדש)": "🌗 Design Mode (restart required)",
    "מצב בהיר (Light Mode)": "Light Mode",
    "🌐 שפה (נדרשת הפעלה מחדש) / Language (restart required)": "🌐 Language (restart required)",
    "טבעות ניצולת מעגליות (CPU/RAM)": "Circular usage rings (CPU/RAM)",
    "מגירת התראות נשלפת (🔔)": "Pull-out notification drawer (🔔)",
    "חלון פקודות מהיר (Ctrl+K)": "Quick command palette (Ctrl+K)",
    "אפקט שקיפות חלון (Alpha Glass)": "Window transparency effect (Alpha Glass)",
    "אפקטים קוליים לממשק (UI Sound FX)": "UI sound effects",
    "צביעה אוטומטית של מילות מפתח בלוגים": "Automatic keyword highlighting in logs",
    "באנר אזהרת עומס מערכת (CPU High Alert)": "System overload warning banner (CPU High Alert)",
    "סרגל קיצורי מקלדת בתחתית הלוג": "Keyboard shortcut bar at the bottom of the log",

    # --- Bot tab ---
    "בקרה ולוגים": "Control & Logs",
    "RSS & AI": "RSS & AI",
    "הפעל בוט 🚀": "Start Bot 🚀",
    "כבה בוט 🛑": "Stop Bot 🛑",
    "סטטוס בוט: כבוי 🔴": "Bot status: Off 🔴",
    "סטטוס בוט: מחובר ורץ 🟢": "Bot status: Connected & Running 🟢",
    "ערוץ דיסקורד ID": "Discord Channel ID",
    "כתובת RSS": "RSS URL",
    "שם המקור": "Source name",
    "הוסף מקור": "Add source",
    "מחיקה": "Delete",
    "App ID": "App ID",
    "שם משחק": "Game name",
    "עקוב": "Track",
    "📰 {name} | ערוץ: {channel_id}": "📰 {name} | Channel: {channel_id}",
    "🎮 {name} ({app_id}) | ערוץ: {channel_id}": "🎮 {name} ({app_id}) | Channel: {channel_id}",
    "\n--- הבוט כובה על ידי המשתמש ---": "\n--- Bot stopped by user ---",
    "\n[שגיאה בהרצה]: {error}": "\n[Run error]: {error}",

    # --- Stats tab ---
    "🎬 גלריית קליפים מסווגים": "🎬 Classified Clips Gallery",
    "🔍 חפש לפי שם קליפ...": "🔍 Search by clip name...",
    "🏷️ כל התגיות": "🏷️ All tags",
    "בחר סרטון מהגלריה ליצוא": "Select a video from the gallery to export",
    "🎮 שעות משחק": "🎮 Hours Played",
    "עוד לא נרשם זמן משחק.": "No playtime recorded yet.",
    "{name}: {hours:.1f} שעות": "{name}: {hours:.1f} hours",
    "📅 קליפים שנלכדו ({days} ימים אחרונים)": "📅 Clips Captured (last {days} days)",
    "🎵 TikTok Export Pro": "🎵 TikTok Export Pro",
    "📺 YouTube Export Pro": "📺 YouTube Export Pro",
    "🔗 העלאה אוטומטית פעילה": "🔗 Automatic upload active",
    "🔗 פותח דפדפן (הגדר client_secret.json להעלאה אוטומטית)": "🔗 Opens browser (set up client_secret.json for automatic upload)",
    "📜 היסטוריית ריצות אחרונות": "📜 Recent Run History",
    "עוד לא בוצעו ריצות.": "No runs yet.",
    "נבחר: {name}": "Selected: {name}",
    "⏳ מעלה... {pct}%": "⏳ Uploading... {pct}%",
    "✅ הועלה ל-YouTube! ID: {id}": "✅ Uploaded to YouTube! ID: {id}",
    "❌ העלאה נכשלה: {error}": "❌ Upload failed: {error}",
    "📈 אנליטיקס YouTube": "📈 YouTube Analytics",
    'עוד לא הועלו סרטונים דרך "📺 YouTube Export Pro".': 'No videos uploaded via "📺 YouTube Export Pro" yet.',
    "עוד לא רוענן": "Not refreshed yet",
    "מאז ההחלפה": "since switching",
    "🖼️ תמונות ממוזערות": "🖼️ Thumbnails",
    "🖼️ תמונות ממוזערות מועמדות": "🖼️ Candidate Thumbnails",
    "אין תמונות מועמדות לסרטון הזה.": "No candidate thumbnails for this video.",
    "✅ הגדר": "✅ Set",

    # --- Soundboard ---
    "🔊 פאנל אפקטים קוליים לסטרימינג": "🔊 Streaming Sound Effects Panel",

    # --- Approvals tab (item: mobile-friendly clip-approval view) ---
    "✅ אישור קליפים": "✅ Clip Approvals",
    "אין קליפים שממתינים לאישור כרגע.": "No clips waiting for approval right now.",
    "🎮 {game} · {created_at}": "🎮 {game} · {created_at}",
    "✅ אשר לרינדור": "✅ Approve for render",
    "❌ דחה": "❌ Reject",

    # --- gui_manager.pyw: header/notifications/log ---
    "🔔 מרכז התראות": "🔔 Notification Center",
    "⚠️ אזהרה: ניצולת מעבד/זיכרון גבוהה במיוחד!": "⚠️ Warning: unusually high CPU/RAM usage!",
    "📐 מצב מרוכז": "📐 Compact Mode",
    "📖 מורחב": "📖 Expanded",
    "📐 מרוכז": "📐 Compact",
    "📝 מרכז לוגים מאוחד (זמן אמת)": "📝 Unified Log Center (real-time)",
    "⌨️ קיצורים: Ctrl+K (חיפוש) | Ctrl+L (ניקוי לוג)": "⌨️ Shortcuts: Ctrl+K (search) | Ctrl+L (clear log)",
    "↕️ גודל לוג": "↕️ Log Size",
    "🧹 ניקוי (Ctrl+L)": "🧹 Clear (Ctrl+L)",
    "📂 פתח תיקיית תוצרים": "📂 Open Output Folder",
    "🛑 עצור רינדור": "🛑 Stop Render",
    "🔍 חיפוש": "🔍 Search",
    "🔌 ניהול שירותי רשת": "🔌 Network Services Management",
    "שרת Docker": "Docker Server",
    "סטטוס ClipForge": "ClipForge Status",
    "פעיל": "Active",
    "לא פעיל": "Inactive",

    # --- gui_manager.pyw: Rocket Settings panel (file dialogs etc.) ---
    "בחר תיקייה לחיפוש סרטונים לעריכה (Import)": "Choose a folder to find videos to edit (Import)",
    "בחר תיקייה לשמירת התוצרים המרונדרים (Export)": "Choose a folder to save rendered output (Export)",
    "בחר קובץ תמונת Overlay / לוגו": "Choose an overlay image / logo file",
    "בחר סרטון להצגת גל קול": "Choose a video to display its waveform",
    "טוען נתוני שמע...": "Loading audio data...",
    "שגיאה בטעינת השמע: {error}": "Error loading audio: {error}",

    # --- gui_manager.pyw: log messages ---
    "מבצע בדיקת תקינות רכיבי מערכת...": "Running system health check...",
    "FFmpeg זוהה בהצלחה (מצורף לפרויקט או במערכת).": "FFmpeg detected successfully (bundled or system-installed).",
    "FFmpeg לא נמצא (לא ב-ffmpeg/bin/ ולא ב-PATH)! חלק מאפשרויות הרינדור לא יעבדו.": "FFmpeg not found (not in ffmpeg/bin/ or PATH)! Some rendering features won't work.",
    "מאיץ חומרה Nvidia (NVENC) זמין ופעיל.": "NVIDIA hardware accelerator (NVENC) available and active.",
    "מאיץ Nvidia לא זוהה - הרינדור יפעל במצב תוכנתי/CPU.": "NVIDIA accelerator not detected - rendering will run in software/CPU mode.",
    "מערכת השליטה מוכנה!": "Control system ready!",
    "המונה עודכן ידנית ל: #{val}": "Counter manually updated to: #{val}",
    "פרופיל איכות הוחל: {name}": "Quality profile applied: {name}",
    "שגיאה בהחלת פרופיל: {error}": "Error applying profile: {error}",
    "תיקיית קליפים עודכנה מגרירה: {dir}": "Clips folder updated via drag-drop: {dir}",
    "הגדרות נשמרו! Import: {input} | Export: {output}": "Settings saved! Import: {input} | Export: {output}",
    "שגיאה בשמירת הגדרות Rocket: {error}": "Error saving Rocket settings: {error}",
    "תיקיית התוצרים נפתחה: {path}": "Output folder opened: {path}",
    "תיקיית התוצרים אינה קיימת עדיין.": "Output folder doesn't exist yet.",
    "התקבלה הוראת ביטול: כל תהליכי הרינדור הופסקו בהצלחה!": "Cancel command received: all render processes stopped successfully!",
    "שגיאה בביטול התהליך: {error}": "Error cancelling the process: {error}",
    "האפליקציה מוזערה למגש המערכת. לחץ על האייקון כדי לשחזר.": "The app was minimized to the system tray. Click the icon to restore.",
    "קיצור מקלדת גלובלי פעיל: Ctrl+Alt+R מריץ את הסקריפט האחרון.": "Global hotkey active: Ctrl+Alt+R runs the last script.",
    "לא ניתן היה לרשום קיצור מקלדת גלובלי (ייתכן שנדרשות הרשאות מנהל): {error}": "Could not register global hotkey (admin permissions may be required): {error}",
    "מצב העיצוב נשמר - סגור ופתח מחדש את האפליקציה כדי שהשינוי ייכנס לתוקף.": "Design mode saved - close and reopen the app for the change to take effect.",
    "השפה נשמרה - סגור ופתח מחדש את האפליקציה כדי שהשינוי ייכנס לתוקף. / Language saved - restart the app to apply.": "Language saved - close and reopen the app for the change to take effect.",
    "הגדרת עיצוב [{key}] שונתה ל: {state}": "Design setting [{key}] changed to: {state}",
    "מצב חלון תמיד עליון: {state}": "Always-on-top window mode: {state}",
    "מתבצע ניסיון אימות מול קונטיינרים של Docker ברשת...": "Attempting to verify Docker containers on the network...",
    "שרת Docker הופעל בהצלחה!": "Docker server started successfully!",
    "שגיאה בהפעלת Docker: {error}": "Error starting Docker: {error}",
    "התקבלה הוראת ניתוק משירותי Docker.": "Disconnect command received from Docker services.",
    "סטטוס הבוט שונה מהתפריט המהיר ל: {state}.": "Bot status changed from the quick menu to: {state}.",
    "נבחר סקריפט חדש בממשק: {name}": "New script selected in the interface: {name}",
    "סטטוס מערכת עודכן: {text}": "System status updated: {text}",
    "צבעי הממשק עודכנו אוטומטית לפי פרופיל: {name}": "Interface colors automatically updated for profile: {name}",
    "מופעל": "On",
    "כבוי": "Off",
    "❌ שגיאה בהפעלת הסקריפט: {error}\n": "❌ Error launching script: {error}\n",
    "🩺 אבחון מערכת": "🩺 System Diagnostics",
    "בודק...": "Checking...",
    "הבדיקה הושלמה.": "Check complete.",
    "לא נמצא (חיפש: {exe})": "Not found (looked for: {exe})",
    "לא נמצא Python גלובלי - הרצת סקריפטים תיכשל (רלוונטי בעיקר לגרסה הארוזה/exe)": "No global Python found - running scripts will fail (mainly relevant to the packaged exe)",
    "פרשן Python להרצת סקריפטים": "Python interpreter for running scripts",
    "מסד נתונים (clipforge_data.db)": "Database (clipforge_data.db)",
    "{n} סקריפטים נבדקו": "{n} scripts checked",
    "תקינות תחבירית של my_scripts ({n} קבצים)": "my_scripts syntax check ({n} files)",
    "שטח פנוי בכונן הפרויקט": "Free space on the project drive",
    "{gb} GB פנויים": "{gb} GB free",
    "הבדיקה עצמה נכשלה: {error}": "The check itself failed: {error}",
    "תיקיית workspace/ (קליפים/תוצרים)": "workspace/ folder (clips/outputs)",
    "מנעול רינדור חוצה-תהליכים": "Cross-process render lock",
    "פנוי": "Free",
    "תקוע (PID {pid}) - ישוחרר אוטומטית בניסיון התפיסה הבא": "Stuck (PID {pid}) - will auto-release on the next acquire attempt",
    "תפוס כרגע (PID {pid}) - רינדור אחר פעיל": "Currently held (PID {pid}) - another render is active",
    "הערת המחשב למשימות מתוזמנות": "Waking the PC for scheduled tasks",
    "כבוי (מופעל במסך המשימות המתוזמנות)": "Off (turned on in the scheduler screen)",
    "מופעל, אבל 'Allow wake timers' כבוי בתוכנית החשמל של Windows - המחשב לא יתעורר":
        "On, but 'Allow wake timers' is off in the Windows power plan - the PC will not wake",
    "הרישום ב-Task Scheduler נכשל: {error}": "Registering with Task Scheduler failed: {error}",
    "מעיר ב-{time} ({task})": "Wakes at {time} ({task})",
    "מופעל - אין כרגע משימה קרובה": "On - no upcoming task right now",
    "🔄 איפוס הגדרות לברירת מחדל": "🔄 Reset Settings to Default",
    "🔄 איפוס הגדרות": "🔄 Reset Settings",
    "לאפס את כל ההגדרות לברירת מחדל? הגדרות נוכחיות יגובו ל-config.json.bak.\nיידרש הפעלה מחדש של התוכנה.": "Reset all settings to default? Current settings will be backed up to config.json.bak.\nThe app will need to be restarted.",
    "שגיאה": "Error",
    "הגיבוי נכשל, האיפוס בוטל: {error}": "Backup failed, reset cancelled: {error}",
    "ההגדרות אופסו. הפעל מחדש את התוכנה כדי שהשינוי ייכנס לתוקף.": "Settings have been reset. Restart the app for the change to take effect.",
    "🎨 ערכת נושא": "🎨 Theme",
    "🎨 מותאם אישית...": "🎨 Custom...",
    "בחר צבע accent מותאם אישית": "Choose a custom accent color",
    "👋 ברוך הבא ל-Launcher": "👋 Welcome to Launcher",
    "👋 ברוך הבא!": "👋 Welcome!",
    "1️⃣ בטאב 'הגדרות' - בחר תיקיית גיימפליי (רק לסקריפטים שצריכים תיקיית עבודה).": "1️⃣ In the 'Settings' tab - pick a gameplay folder (only needed for scripts that require a working folder).",
    "2️⃣ לחץ על 🩺 בפינה העליונה כדי לוודא שהמערכת מוכנה (ffmpeg, Python, מסד נתונים).": "2️⃣ Click 🩺 in the top corner to make sure the system is ready (ffmpeg, Python, database).",
    "3️⃣ בחר סקריפט מהסיידבר ולחץ 'הרץ סקריפט' בלשונית 'לוח בקרה'.": "3️⃣ Pick a script from the sidebar and click 'Run Script' in the 'Dashboard' tab.",
    "💡 ⚡ ליד סקריפט = רץ מיד, לא מחכה בתור. ⚠️ = מזיז/משנה קבצים קיימים.": "💡 ⚡ next to a script = runs immediately, no queue wait. ⚠️ = moves/changes existing files.",
    "✅ הבנתי, אל תראה שוב": "✅ Got it, don't show again",
    "יומי": "Daily",
    "שבועי": "Weekly",
    "כל X שעות": "Every X hours",
    "⏰ הוסף משימה מתוזמנת חדשה": "⏰ Add a New Scheduled Task",
    "אין סקריפטים זמינים": "No scripts available",
    "סקריפט:": "Script:",
    "תדירות:": "Frequency:",
    "שעה (HH:MM):": "Time (HH:MM):",
    "יום (לשבועי):": "Day (for weekly):",
    "מספר שעות (ל'כל X שעות'):": "Number of hours (for 'every X hours'):",
    "➕ הוסף משימה מתוזמנת": "➕ Add Scheduled Task",
    "📋 משימות מתוזמנות": "📋 Scheduled Tasks",
    "כל יום ב-{time}": "Every day at {time}",
    "כל {weekday} ב-{time}": "Every {weekday} at {time}",
    "כל {hours} שעות": "Every {hours} hours",
    "אין משימות מתוזמנות עדיין.": "No scheduled tasks yet.",
    "🗑️ מחק": "🗑️ Delete",
    "⏰ תזמון": "⏰ Scheduler",
    "⏰ הרצה מתוזמנת התחילה: {name}": "⏰ Scheduled run started: {name}",
    "שגיאה בבדיקת משימות מתוזמנות: {error}": "Error checking scheduled tasks: {error}",

    # --- my_scripts/video/dataviz_maker.py (סרטוני נתונים) ---
    "[ERROR] לא נמצא אף פרק (תיקייה עם config.yaml) ב-{folder}.": "[ERROR] No episode (a folder with config.yaml) found in {folder}.",
    "[INFO] נמצאו {n} פרקים: {names}": "[INFO] Found {n} episodes: {names}",
    "[ERROR] הגדרות לא תקינות בפרק {name}:": "[ERROR] Invalid settings in episode {name}:",
    "[ERROR] קריאת הנתונים של {name} נכשלה: {error}": "[ERROR] Reading the data of {name} failed: {error}",
    "[INFO] {name}: {frames} פריימים, {seconds} שניות ({chart}, מצב {mode})": "[INFO] {name}: {frames} frames, {seconds} seconds ({chart}, {mode} mode)",
    "[APPROVED] {n} סטילס נשמרו ב-{folder}": "[APPROVED] {n} stills saved in {folder}",
    "[ERROR] שטח פנוי לא מספיק ב-{folder} - מדלג על {name}.": "[ERROR] Not enough free space in {folder} - skipping {name}.",
    "⏳ ממתין לסיום רינדור אחר שרץ כרגע (GUI/דפדפן/בוט)...": "⏳ Waiting for another render that is running now (GUI/browser/bot)...",
    "[ERROR] הרינדור של {name} נכשל: {error}": "[ERROR] Rendering {name} failed: {error}",
    "[APPROVED] נוצר: {path}": "[APPROVED] Created: {path}",
    "[SUCCESS] העיבוד הסתיים.": "[SUCCESS] Processing finished.",
}


def t(text, /, _fix_word_order=True, **kwargs):
    # text מוגדר positional-only (ה-"/") בכוונה: קריאה כמו t("...{text}...", text=x)
    # (תבנית שמכילה placeholder בשם "text") הייתה מתנגשת עם הפרמטר הזה עצמו -
    # "t() got multiple values for argument 'text'" - וקרסה כל קריאה ל-run_task()
    # שעברה דרך update_led_indicator() ב-gui_manager.pyw. positional-only מבטל
    # את ההתנגשות: "..." תמיד נקשר למיקום, וה-kwarg "text=" זורם ל-kwargs בלבד.
    # _fix_word_order (שם עם קידומת "_" מאותה סיבה - לא סביר שתבנית תשתמש
    # ב-placeholder בשם הזה, אבל עדיף להיזהר) מאפשר לקורא לבקש את הטקסט
    # המתורגם *בלי* תיקון סדר-המילים - למקרים שבהם הטקסט הזה רק "אבן בניין"
    # שתורכב עם עוד טקסט אחר-כך (למשל icon+name), לא התצוגה הסופית בעצמה.
    # אם התיקון קורה כאן ושוב על המחרוזת המורכבת בהמשך, זה הופך פעמיים
    # (שקול לביטול) ולא מתקן שום דבר - זה בדיוק הבאג שהיה ב-get_script_metadata()
    # ותוקן (ראו utils/shared/script_metadata.py) - אותה בעיה יכולה לקרות בכל t()
    # שמחזיר "אבן בניין" ולא טקסט-תצוגה-סופי.
    if state.language == "en":
        text = TRANSLATIONS.get(text, text)

    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass

    if state.language != "en" and _fix_word_order:
        text = fix_hebrew_word_order(text)

    return text
