# utils/shared/version.py
#
# מקור אמת יחיד לגרסה הנוכחית של האפליקציה - נשמר ידנית בסנכרון עם
# pyproject.toml's version (לא נקרא משם בזמן ריצה).
# משמש את utils/shared/update_checker.py כדי להשוות מול הגרסה האחרונה
# שפורסמה ב-GitHub Releases.
APP_VERSION = "1.1.3"
