# Name: 🔐 העברת סודות ל-Credential Manager
# Name (EN): 🔐 Migrate Secrets to Credential Manager
# Description: מעביר את המפתחות הרגישים מקובץ .env ל-Windows Credential Manager (מוצפן ע"י המערכת).
# Description (EN): Moves sensitive keys from the .env file to Windows Credential Manager (OS-encrypted).
# Concurrency: light
# Safety: read-only

import os
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

from dotenv import dotenv_values
from utils.shared.secrets_vault import set_secret, is_vault_available

ENV_PATH = os.path.join(BASE_DIR, ".env")


def main():
    if not is_vault_available():
        print("❌ החבילה 'keyring' אינה מותקנת. הרץ: pip install keyring")
        return

    if not os.path.exists(ENV_PATH):
        print(f"❌ לא נמצא קובץ .env בנתיב: {ENV_PATH}")
        return

    values = dotenv_values(ENV_PATH)
    migrated = 0

    for key, value in values.items():
        if not value:
            continue
        set_secret(key, value)
        print(f"✅ הועבר ל-Credential Manager: {key}")
        migrated += 1

    if migrated == 0:
        print("ℹ️ לא נמצאו ערכים להעברה ב-.env.")
        return

    print(f"\n🎉 הועברו {migrated} מפתחות ל-Windows Credential Manager.")
    print("הקוד קורא קודם מ-Credential Manager ורק אם לא נמצא נופל חזרה ל-.env,")
    print("כך שאפשר להשאיר את .env כרגע כגיבוי, או לרוקן אותו ידנית אחרי שווידאת שהכל עובד.")


if __name__ == "__main__":
    main()
