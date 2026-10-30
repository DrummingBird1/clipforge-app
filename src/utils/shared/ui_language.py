# utils/shared/ui_language.py
#
# 30.10.2026 (לפני ההפצה הציבורית): שפת הממשק בהתקנה חדשה היא אנגלית. config.json שכבר קיים בלי "language" - התקנה מלפני
# השינוי, שבה ברירת המחדל הייתה עברית - נשאר בעברית, וההחלטה נכתבת לקובץ פעם אחת (כמו title_prefix של Rocket Shorts, #98):
# אחרת קובץ שנוצר אחר כך בלי המפתח היה הופך התקנה חדשה לעברית. config.json שלא קיים נוצר עם "en". נקרא מהשרת (הדף שואל
# את /api/settings/style כשבדפדפן עוד אין בחירה); הדסקטופ הקפוא ממשיך לקרוא את "language" מהקובץ, עם עברית כשאין.


LANGUAGES = ("he", "en")
NEW_INSTALL = "en"
EXISTING_INSTALL = "he"


def ensure_language(config_file: str, lock_file: str) -> str:
    """השפה של ההתקנה, וכותב אותה ל-config.json כשהיא עוד לא שם. קובץ פגום לא נדרס - עברית, כמו קודם.
    30.10.2026: באותה כתיבה גם ההגדרות שתלויות בהתקנה (utils/shared/install_profile) - ההחלטה אחת לשתיהן."""
    from utils.shared import install_profile   # הוא מייבא את הקבועים מכאן
    return install_profile.ensure(config_file, lock_file)["language"]


def current(config_file: str = "") -> str:
    """השפה של ההתקנה בלי לכתוב - לטקסטים שהשרת והסקריפטים מייצרים (כותרת ברירת מחדל, שם מכשיר, כרטיסי Wrapped). אותה
    החלטה כמו ensure_language (install_profile.language_of): בלי config.json - "en"; קובץ בלי המפתח או פגום - "he"."""
    from utils.shared import data_paths, install_profile
    return install_profile.read_language(config_file or data_paths.path(data_paths.CONFIG))
