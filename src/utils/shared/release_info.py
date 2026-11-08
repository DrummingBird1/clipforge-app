# utils/shared/release_info.py
#
# 8.11.2026: קבועי הפצת הגרסאות - הריפו הציבורי, כתובת עמוד ה-Release, ושם הקובץ שמסמן חבילה ניידת. בלי שום ייבוא חיצוני,
# בכוונה: dev/build_portable.py רץ ב-release.yml עם הפייתון של ה-runner, בלי ספריות הפרויקט (tests/infra/test_release_workflow.py
# דורש בלי uv run), והוא ייבא את utils.shared.update_checker רק בשביל שני קבועים. update_checker מייבא requests, וה-Release הראשון
# בריפו הציבורי (v1.2.0) נפל על ModuleNotFoundError. update_checker מייבא מכאן, והשמות נשארים נגישים גם דרכו.

# 30.10.2026: הגרסאות יוצאות בריפו הציבורי (dev/export_public.py מכין אותו, release.yml בונה בו את ה-zip). הריפו הפרטי
# DrummingBird1/clipforge נשאר לפיתוח, ו-apply_update מושך מה-origin של העותק עצמו, לא מכאן
REPO = "DrummingBird1/clipforge-app"
RELEASES_PAGE_URL = f"https://github.com/{REPO}/releases/latest"

# 30.10.2026: החבילה הניידת (dev/build_portable.py) כותבת את הקובץ הזה בשורש שלה. שם אין git ואין uv - מעדכנים בהורדת
# הגרסה החדשה מעמוד ה-Release, לא ב-apply_update.
PORTABLE_MARKER = "portable.json"
