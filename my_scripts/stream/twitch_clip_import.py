# Name: 🟣 ייבוא קליפים מ-Twitch
# Name (EN): 🟣 Twitch Clip Import
# Description: מוריד קליפים אחרונים מהערוץ שלך ב-Twitch לתוך תיקיית ה-Import, כדי שיזרמו לאותו פייפליין וידאו.
# Description (EN): Downloads your channel's latest Twitch clips into the Import folder, feeding them into the same video pipeline.
# Concurrency: light
# Safety: read-only
#
# דורש הגדרה חד-פעמית מהצד שלך (לא ניתן לבצע מהקוד - זו פעולה בחשבון Twitch שלך):
#   1. היכנס ל-https://dev.twitch.tv/console/apps וצור אפליקציה חדשה.
#   2. שמור את ה-Client ID ואת ה-Client Secret שנוצרים.
#   3. הוסף אותם ל-.env (או ל-Windows Credential Manager דרך migrate_secrets_to_vault.py):
#        TWITCH_CLIENT_ID=...
#        TWITCH_CLIENT_SECRET=...
#        TWITCH_CHANNEL_NAME=<שם המשתמש שלך ב-Twitch, לא display name>
#
# לא ניתן היה לבדוק את זה מקצה לקצה כאן - אין חשבון Twitch/פרטי אפליקציה זמינים
# בסביבה הזו. ההיגיון מבוסס על Twitch Helix API (מתועד רשמית) + הפורמט הידוע
# להורדת קובץ mp4 מתוך thumbnail_url של קליפ (טריק נפוץ אך לא מתועד רשמית -
# אם Twitch ישנו את הפורמט, ההורדה תפסיק לעבוד וצריך יהיה לעדכן את הפונקציה
# _thumbnail_to_download_url).

import argparse
import json
import os
import sys

import requests

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
from utils.shared.secrets_vault import get_secret
from utils.shared import data_paths

parser = argparse.ArgumentParser()
parser.add_argument("--input_dir", type=str, default="", help="לא בשימוש ישיר - נשמר לתאימות עם worker.py")
parser.add_argument("--limit", type=int, default=10, help="כמה קליפים אחרונים להוריד")
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


def get_app_access_token(client_id, client_secret):
    resp = requests.post("https://id.twitch.tv/oauth2/token", params={
        "client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _thumbnail_to_download_url(thumbnail_url):
    # דוגמה: https://.../AT-cm%7C123-preview-480x272.jpg -> https://.../AT-cm%7C123.mp4
    if "-preview-" not in thumbnail_url:
        return None
    base = thumbnail_url.split("-preview-")[0]
    return base + ".mp4"


def main():
    client_id = get_secret("TWITCH_CLIENT_ID")
    client_secret = get_secret("TWITCH_CLIENT_SECRET")
    channel_name = get_secret("TWITCH_CHANNEL_NAME")

    if not client_id or not client_secret or not channel_name:
        print("❌ נא להגדיר TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET ו-TWITCH_CHANNEL_NAME (ב-.env או ב-Credential Manager).")
        print("   הוראות הגדרה מלאות בראש קובץ הסקריפט הזה.")
        return

    settings = load_settings()
    target_dir = args.input_dir or settings.get("input_dir", BASE_DIR)
    os.makedirs(target_dir, exist_ok=True)

    try:
        token = get_app_access_token(client_id, client_secret)
        headers = {"Client-Id": client_id, "Authorization": f"Bearer {token}"}

        user_resp = requests.get("https://api.twitch.tv/helix/users", headers=headers,
                                  params={"login": channel_name}, timeout=15)
        user_resp.raise_for_status()
        users = user_resp.json().get("data", [])
        if not users:
            print(f"❌ לא נמצא משתמש Twitch בשם {channel_name}.")
            return
        broadcaster_id = users[0]["id"]

        clips_resp = requests.get("https://api.twitch.tv/helix/clips", headers=headers,
                                   params={"broadcaster_id": broadcaster_id, "first": args.limit}, timeout=15)
        clips_resp.raise_for_status()
        clips = clips_resp.json().get("data", [])
    except Exception as e:
        print(f"❌ שגיאה בתקשורת עם Twitch API: {e}")
        return

    if not clips:
        print("ℹ️ לא נמצאו קליפים בערוץ.")
        return

    print(f"🎬 נמצאו {len(clips)} קליפים ב-Twitch, מוריד ל-{target_dir}...")
    downloaded = 0
    for clip in clips:
        download_url = _thumbnail_to_download_url(clip.get("thumbnail_url", ""))
        if not download_url:
            print(f"⚠️ דילוג על {clip.get('id')} - לא ניתן היה לגזור קישור הורדה.")
            continue

        safe_title = "".join(c for c in clip.get("title", clip["id"]) if c.isalnum() or c in " _-")[:60].strip() or clip["id"]
        out_path = os.path.join(target_dir, f"twitch_{safe_title}.mp4")

        if os.path.exists(out_path):
            continue

        try:
            video_resp = requests.get(download_url, timeout=60)
            video_resp.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(video_resp.content)
            print(f"✅ הורד: {os.path.basename(out_path)}")
            downloaded += 1
        except Exception as e:
            print(f"❌ הורדת {clip.get('id')} נכשלה: {e}")

    print(f"\n🎉 סה\"כ {downloaded} קליפים חדשים הורדו.")


if __name__ == "__main__":
    main()
