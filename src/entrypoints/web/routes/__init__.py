# entrypoints/web/routes - ה-endpoints של ממשק הדפדפן, router אחד לכל תחום.
# web_app.py מחבר אותם (app.include_router) ומחזיק את המצב המשותף; כל router
# ניגש אליו כ-W.<שם> - מקור-אמת אחד, ו-monkeypatch על web_app חל גם כאן.
