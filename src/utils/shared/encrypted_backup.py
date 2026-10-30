# utils/shared/encrypted_backup.py
#
# גיבוי-על-פי-בקשה של תיקיית data/ כולה (הגדרות, DB, מצב תזמון) לקובץ יחיד
# *מוצפן* עם סיסמה - בניגוד לגיבוי האוטומטי היומי הקיים (cogs/scheduler_cog.py's
# _backup_database/_backup_data_directory), שכותב zip/DB גלויים לגמרי תחת
# data/backups/ - שימושי כ"רשת ביטחון מקומית", אבל לא בטוח להעביר/להעתיק
# החוצה (דיסק חיצוני, ענן) כמו שהוא. כאן בדיוק בשביל זה - קובץ יחיד שאפשר
# להוציא מהמכונה בבטחה.
#
# כולל את אותו תוכן בדיוק (DB דרך sqlite3's backup API, לא shutil.copy - כדי
# שקובץ שנפתח כרגע לכתיבה יגובה בעקביות ולא כ-snapshot חצוי), ואת אותם חריגים
# (backups/, logs/, render.lock) - בכוונה לא כולל secrets_vault.py's credentials:
# אלה שמורים כבר מוצפנים ב-Windows Credential Manager, לא בקובץ על הדיסק בכלל,
# אז אין מה "לגבות" מהם לתוך קובץ נייד בלי לבנות מנגנון ייצוא-סודות נפרד ומורכב
# משמעותית יותר - מחוץ לתחום הפיצ'ר הזה.
import base64
import io
import os
import shutil
import sqlite3
import tempfile
import zipfile

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from utils.shared.data_dir import DATA_DIR
from utils.shared import data_paths

BACKUPS_DIR = data_paths.path(data_paths.BACKUPS)

SALT_SIZE = 16
# המלצת OWASP הנוכחית ל-PBKDF2-HMAC-SHA256 (2023) - איטי מספיק כדי להאט ניחוש-סיסמה
# בכוח גס, אבל עדיין מיידי מבחינת המשתמש (חלקיק שנייה) בפעולה חד-פעמית כמו זו.
PBKDF2_ITERATIONS = 480_000

_EXCLUDE_DIRNAMES = data_paths.BACKUP_SKIP_DIRS
_EXCLUDE_FILENAMES = data_paths.BACKUP_SKIP_FILES


class BackupError(Exception):
    """שגיאת גיבוי/שחזור שראויה להיות מוצגת למשתמש כמו שהיא (סיסמה שגויה,
    קובץ פגום וכו') - לא Traceback גולמי."""


def _derive_key(passphrase, salt):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def _snapshot_database_bytes(db_path):
    if not os.path.exists(db_path):
        return None
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        src_conn = sqlite3.connect(db_path)
        dest_conn = sqlite3.connect(tmp_path)
        with dest_conn:
            src_conn.backup(dest_conn)
        src_conn.close()
        dest_conn.close()
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.remove(tmp_path)


def _build_zip_bytes(data_dir):
    buffer = io.BytesIO()
    included = []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        db_path = data_paths.path(data_paths.BOT_DB, data_dir)
        db_bytes = _snapshot_database_bytes(db_path)
        if db_bytes is not None:
            db_name = data_paths.relative(db_path, data_dir)   # בשם היחסי שלו (bot/... אחרי ההעברה) - שחזור מחזיר אותו לאותו מקום
            zf.writestr(db_name, db_bytes)
            included.append(db_name)

        for root, dirs, files in os.walk(data_dir):
            dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIRNAMES]
            for filename in files:
                if filename in _EXCLUDE_FILENAMES:
                    continue
                full_path = os.path.join(root, filename)
                arcname = os.path.relpath(full_path, data_dir)
                zf.write(full_path, arcname)
                included.append(arcname)
    return buffer.getvalue(), included


def create_backup_bundle(passphrase, output_path, data_dir=DATA_DIR):
    """יוצר קובץ גיבוי מוצפן יחיד ב-output_path. מחזיר dict עם included_files
    ו-size_bytes. זורק BackupError אם אין סיסמה."""
    if not passphrase:
        raise BackupError("סיסמה נדרשת ליצירת גיבוי מוצפן.")

    zip_bytes, included = _build_zip_bytes(data_dir)
    salt = os.urandom(SALT_SIZE)
    key = _derive_key(passphrase, salt)
    token = Fernet(key).encrypt(zip_bytes)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(salt + token)

    return {"included_files": included, "size_bytes": os.path.getsize(output_path)}


def restore_backup_bundle(passphrase, input_path, data_dir=DATA_DIR):
    """מפענח ומשחזר קובץ גיבוי מוצפן לתוך data_dir. כל קובץ שכבר קיים ועומד
    להידרס מגובה קודם ל-<name>.bak (אותו עיקרון בדיוק כמו api_settings_reset/
    api_settings_import הקיימים). זורק BackupError על סיסמה שגויה/קובץ פגום,
    או אם הארכיון מנסה "לברוח" מ-data_dir (zip-slip)."""
    if not passphrase:
        raise BackupError("סיסמה נדרשת לשחזור הגיבוי.")

    with open(input_path, "rb") as f:
        raw = f.read()
    if len(raw) <= SALT_SIZE:
        raise BackupError("קובץ הגיבוי פגום או לא שלם.")

    salt, token = raw[:SALT_SIZE], raw[SALT_SIZE:]
    key = _derive_key(passphrase, salt)
    try:
        zip_bytes = Fernet(key).decrypt(token)
    except InvalidToken:
        raise BackupError("סיסמה שגויה או שקובץ הגיבוי פגום.")

    data_dir_real = os.path.realpath(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    restored = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            # 24.10.2026: גיבוי שטוח (לפני ההעברה לתיקיות לפי נושא) משוחזר לתיקיות אחריה, וגיבוי חדש - שטוח לפניה.
            # הסימן של ההעברה לא משוחזר: המבנה של data_dir קובע, לא של הגיבוי
            target = data_paths.localize(name, data_dir)
            if not target or os.path.basename(target) == data_paths.LAYOUT_MARKER:
                continue
            dest_path = os.path.realpath(os.path.join(data_dir, *target.split("/")))
            if dest_path != data_dir_real and not dest_path.startswith(data_dir_real + os.sep):
                raise BackupError(f"קובץ גיבוי לא תקין (ניסיון גישה מחוץ לתיקייה): {name}")

            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            if os.path.exists(dest_path):
                shutil.copy2(dest_path, dest_path + ".bak")
            with open(dest_path, "wb") as out_f:
                out_f.write(zf.read(name))
            restored.append(name)

    return {"restored_files": restored}
