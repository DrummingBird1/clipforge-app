# tests/page_source.py
#
# גל 24: ה-CSS וה-JS כבר לא בתוך ה-HTML אלא ב-/static/app.<hash>.css|js. טסטים שבודקים
# את תוכן הדף (פונקציה קיימת, שדה מחובר) מקבלים אותו כמו שהדפדפן מקבל: ה-HTML ושני
# ה-bundles שהוא מפנה אליהם - כך הם בודקים גם שההגשה עצמה עובדת.
import re

BUNDLE_URL = re.compile(r'(?:href|src)="(/static/app\.[0-9a-f]{12}\.(?:css|js))"')


def served_page_text(client):
    response = client.get("/")
    assert response.status_code == 200
    parts = [response.text]
    for url in BUNDLE_URL.findall(response.text):
        bundle = client.get(url)
        assert bundle.status_code == 200, url
        parts.append(bundle.text)
    assert len(parts) == 3, "הדף חייב להפנות ל-bundle אחד של CSS ואחד של JS"
    return "\n".join(parts)
