# entrypoints/web/server_startup.py
#
# 24.10.2026 (פיצול web_app.py, קבוצה 6): עליית השרת - הפורט, אייקון מגש המערכת וכתובת ה-LAN. עבר מ-web_app.py בלי שינוי
# התנהגות. web_app מייבא את השמות האלה בחזרה (web_app.<שם> נשאר), ו-__main__ שם קורא להם כמו קודם.
# כל שם שקיים גם ב-web_app נקרא דרך W. - טסטים מחליפים את web_app.<שם>, והקוד כאן צריך לראות את ההחלפה
# (tests/web/test_web_app_split.py בודק את זה).
import os
import webbrowser

from entrypoints import web_app as W

# 30.10.2026: תפריט המגש בשפת ההתקנה (ui_language.current) - בהתקנה באנגלית הוא היה בעברית. (פתיחה, עצירה)
TRAY_LABELS = {"en": ("Open ClipForge", "Stop server"), "he": ("פתח בדפדפן", "כבה שרת")}


def tray_labels(language):
    return W.TRAY_LABELS.get(language, W.TRAY_LABELS["en"])

DEFAULT_PORT = 8878
# שרת אחר כבר מחזיק את הפורט (בדרך כלל עותק קודם של עצמנו) - יוצאים בלי לגעת בקובץ הטוקן
PORT_IN_USE_EXIT_CODE = 3


def _run_tray_icon(server, url):
    """מריץ אייקון מגש מערכת (pystray) על thread נפרד - בלי זה, השרת (מופעל
    כ-pythonw.exe דרך WebLauncher.vbs, ראו _web_launcher_impl.bat) רץ לגמרי
    בלי שום חלון גלוי או סמל בשורת המשימות/מגש מוסתר, ואין שום דרך לכבות
    אותו חוץ מ-Task Manager. אותו עיקרון בדיוק כמו gui_manager.pyw's
    minimize_to_tray, רק בלי Tk בכלל - "כבה שרת" מפעיל should_exit=True על
    ה-uvicorn.Server (הדרך הנתמכת לעצור אותו בעדינות מ-thread אחר), לא
    os._exit גולמי, כדי שחיבורים פעילים ייסגרו כראוי."""
    try:
        import pystray
        from PIL import Image as PILImage
    except Exception as e:
        print(f"[web_app] אייקון מגש המערכת לא זמין ({e}) - סגירה אפשרית רק דרך Task Manager.")
        return

    if os.path.exists(W.APP_ICON_PNG):
        image = PILImage.open(W.APP_ICON_PNG)
    else:
        image = PILImage.new("RGB", (64, 64), (12, 12, 14))

    def _open_browser(icon=None, item=None):
        webbrowser.open(url)

    def _quit(icon=None, item=None):
        icon.stop()
        server.should_exit = True

    from utils.shared import ui_language
    open_label, stop_label = W.tray_labels(ui_language.current(W.CONFIG_FILE))
    menu = pystray.Menu(
        pystray.MenuItem(open_label, _open_browser, default=True),
        pystray.MenuItem(stop_label, _quit),
    )
    try:
        pystray.Icon("clipforge_web", image, "ClipForge - Web", menu).run()
    except Exception as e:
        print(f"[web_app] אייקון מגש המערכת נכשל בהפעלה ({e}) - סגירה אפשרית רק דרך Task Manager.")


def _bind_server_socket(host, port):
    """תופס את הפורט לפני שמשהו אחר בהפעלה קורה, ומחזיר socket קשור (עוד לא מאזין - uvicorn מאזין עליו).
    ב-Windows SO_EXCLUSIVEADDRUSE: בלעדיו (ו-uvicorn מגדיר SO_REUSEADDR) שני תהליכים יכולים להיקשר לאותו פורט, והשני
    נשאר כתהליך יתום. פורט תפוס = OSError, והקורא יוצא. 19.10.2026: הפעלה כפולה כתבה טוקן חדש לפני שבדקה את הפורט,
    והשרת שרץ נשאר עם הישן - הדפדפן וקישור ה-launcher קיבלו 401."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError:
        sock.close()
        raise
    return sock


def _bind_server_sockets(hosts, port):
    """כל הכתובות או כלום: socket לכל host (loopback, ובמצב Tailscale גם כתובת ה-Tailscale); אם אחד נכשל - הקודמים נסגרים
    וה-OSError עולה עם ה-host, כדי שהקורא ייצא לפני שנגע בטוקן."""
    sockets = []
    for host in hosts:
        try:
            sockets.append(W._bind_server_socket(host, port))
        except OSError as e:
            for sock in sockets:
                sock.close()
            raise OSError(f"{host}:{port} - {e}") from e
    return sockets


def _get_lan_ip():
    """מוצא את כתובת ה-IP המקומית ברשת (לא 127.0.0.1) - כדי שיהיה קל להעתיק
    לנייד/טאבלט באותה רשת במצב --lan. שיטת ה-socket UDP הרגילה (לא שולחת שום
    דבר בפועל - רק מבררת איזה ממשק רשת היה משמש לחיבור יוצא) - נופלת חזרה
    ל-127.0.0.1 אם אין רשת בכלל."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
