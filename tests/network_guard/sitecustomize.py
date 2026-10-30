# tests/network_guard/sitecustomize.py
#
# נטען אוטומטית בעליית כל תהליך פייתון שהתיקייה הזו ב-PYTHONPATH שלו - tests/conftest.py שם אותה שם, ותתי-תהליכים של
# טסטים (שרת, סקריפטים, הורדות) יורשים אותה. מתקין את חסימת הרשת רק כשהטסט לא ביקש opt-out (ראו clipforge_test_network_guard).
import os

if os.environ.get("CLIPFORGE_TEST_NETWORK_GUARD") == "1":
    import clipforge_test_network_guard

    clipforge_test_network_guard.install()
