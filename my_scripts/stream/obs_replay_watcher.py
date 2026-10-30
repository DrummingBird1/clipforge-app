# Name: 📼 מעקב Replay מ-OBS
# Name (EN): 📼 OBS Replay Watcher
# Description: מאזין ל-OBS (דרך obs-websocket) ומעתיק אוטומטית כל Replay Buffer שנשמר לתוך תיקיית ה-Import (העותק המקורי שנשמר על ידי OBS נשאר במקומו). קיצור מקלדת גלובלי אופציונלי ("Clip That!") שולח בקשת שמירה יזומה ל-OBS.
# Description (EN): Listens to OBS (via obs-websocket) and automatically copies every saved Replay Buffer into the Import folder (the original file OBS saved is left untouched). An optional global hotkey ("Clip That!") actively triggers OBS to save the buffer.
# Safety: read-only
#
# דורש הגדרה חד-פעמית מהצד שלך (לא ניתן לבצע מהקוד):
#   1. ב-OBS: Tools -> obs-websocket Settings -> "Enable WebSocket server".
#   2. שים לב לפורט (ברירת מחדל 4455) ולסיסמה (אם מוגדרת).
#   3. הוסף ל-.env (או ל-Credential Manager):
#        OBS_WEBSOCKET_PASSWORD=<הסיסמה, אם הוגדרה - אפשר להשאיר ריק אם אין>
#        OBS_WEBSOCKET_PORT=4455
#
# זהו סקריפט מאזין ארוך-טווח (לא "הרץ פעם אחת וסיים" כמו שאר my_scripts) -
# מריצים אותו מה-GUI ומשאירים רץ ברקע; "🛑 עצור רינדור" ב-GUI עוצר אותו.
#
# לא ניתן היה לבדוק את זה מקצה לקצה כאן - אין OBS מותקן עם obs-websocket פעיל
# בסביבה הזו. ההיגיון מבוסס על תיעוד רשמי של obs-websocket v5 protocol.
#
# קיצור "Clip That!" (item) - אופציונלי (rocket_settings.json's "clip_hotkey",
# ריק=כבוי): OBS כבר תומך בקיצור מקלדת משלו לשמירת ה-Replay Buffer (Settings
# -> Hotkeys), אבל זה דורש הגדרה נפרדת שם ולא עובד דרך חלון OBS אם המשחק
# תפוס-מסך (fullscreen exclusive) בלי שיוך המקלדת ל-OBS. הקיצור הגלובלי כאן
# נרשם ברמת המערכת (חבילת keyboard) ושולח בקשת SaveReplayBuffer על אותו
# חיבור websocket שכבר פתוח - אותה תוצאה, בלי תלות בהגדרות OBS.

import argparse
import asyncio
import json
import os
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))
from utils.media.auto_chain import clip_ready_line
from utils.shared.secrets_vault import get_secret
from utils.shared import data_paths

parser = argparse.ArgumentParser()
parser.add_argument("--input_dir", type=str, default="", help="לא בשימוש ישיר - נשמר לתאימות עם worker.py")
args, _unknown = parser.parse_known_args()


def load_settings():
    settings_path = data_paths.path(data_paths.ROCKET_SETTINGS)
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


async def trigger_save_replay_buffer(ws):
    """שולח בקשת SaveReplayBuffer ל-OBS על חיבור websocket קיים (item: Clip
    That!) - אותה בקשה בדיוק ש-OBS's own hotkey שולח, רק שהמקור כאן הוא קיצור
    מקלדת גלובלי של האפליקציה עצמה. כשל (למשל OBS לא ב-Recording/Streaming,
    Replay Buffer לא מופעל בכלל) נרשם ולא מפיל את שאר המאזין."""
    import simpleobsws
    try:
        response = await ws.call(simpleobsws.Request("SaveReplayBuffer"))
        if response.requestStatus.result:
            print("✂️ Clip That! - בקשת שמירת Replay Buffer נשלחה ל-OBS בהצלחה.")
        else:
            print(f"⚠️ OBS דחה את בקשת שמירת ה-Replay Buffer: {response.requestStatus.comment}")
    except Exception as e:
        print(f"❌ שליחת בקשת שמירת Replay Buffer נכשלה: {e}")
    sys.stdout.flush()


def schedule_replay_save(loop, ws):
    """נקרא מ-thread הרקע של חבילת keyboard (לא thread ה-event loop של
    asyncio) - run_coroutine_threadsafe הוא הדרך הבטוחה היחידה לתזמן קורוטינה
    בחזרה ללולאה הרצה מ-thread אחר; קריאה ישירה לקורוטינה משם הייתה נכשלת."""
    asyncio.run_coroutine_threadsafe(trigger_save_replay_buffer(ws), loop)


async def watch():
    try:
        import simpleobsws
    except ImportError:
        print("❌ החבילה 'simpleobsws' אינה מותקנת. הרץ: pip install simpleobsws")
        return

    password = get_secret("OBS_WEBSOCKET_PASSWORD")
    port = get_secret("OBS_WEBSOCKET_PORT") or "4455"

    settings = load_settings()
    target_dir = args.input_dir or settings.get("input_dir", BASE_DIR)
    os.makedirs(target_dir, exist_ok=True)

    ws = simpleobsws.WebSocketClient(url=f"ws://localhost:{port}", password=password or "")

    try:
        await ws.connect()
        await ws.wait_until_identified()
    except Exception as e:
        print(f"❌ לא ניתן להתחבר ל-OBS ({e}). ודא ש-OBS פתוח וש-obs-websocket מופעל (Tools -> obs-websocket Settings).")
        return

    print(f"🟢 מחובר ל-OBS. מאזין ל-Replay Buffer שנשמר, יעביר אוטומטית ל-{target_dir}...")
    sys.stdout.flush()

    async def on_event(event_type, event_data):
        if event_type != "ReplayBufferSaved":
            return
        saved_path = event_data.get("savedReplayPath")
        if not saved_path or not os.path.exists(saved_path):
            print(f"⚠️ התקבל אירוע שמירת Replay אך לא נמצא קובץ: {saved_path}")
            return
        try:
            dest = os.path.join(target_dir, os.path.basename(saved_path))
            shutil.copy2(saved_path, dest)
            print(f"✅ Replay Buffer הועבר לפייפליין: {os.path.basename(saved_path)}")
            # גל 32: השרת (ממשק הדפדפן) ממשיך מכאן לפי "אחרי שקליפ נכנס" בהגדרות Rocket
            print(clip_ready_line(dest, "obs"))
        except Exception as e:
            print(f"❌ העברת ה-Replay נכשלה: {e}")
        sys.stdout.flush()

    ws.register_event_callback(on_event)

    clip_hotkey = (settings.get("clip_hotkey") or "").strip()
    registered_hotkey = None
    if clip_hotkey:
        try:
            import keyboard
            loop = asyncio.get_event_loop()
            registered_hotkey = keyboard.add_hotkey(clip_hotkey, lambda: schedule_replay_save(loop, ws))
            print(f"⌨️ קיצור 'Clip That!' פעיל: {clip_hotkey}")
        except Exception as e:
            print(f"⚠️ רישום קיצור המקלדת נכשל (ממשיך בלי clip-hotkey): {e}")
        sys.stdout.flush()

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        if registered_hotkey is not None:
            try:
                import keyboard
                keyboard.remove_hotkey(registered_hotkey)
            except Exception:
                pass
        await ws.disconnect()


def main():
    try:
        asyncio.run(watch())
    except KeyboardInterrupt:
        print("\n🛑 המאזין הופסק.")


if __name__ == "__main__":
    main()
