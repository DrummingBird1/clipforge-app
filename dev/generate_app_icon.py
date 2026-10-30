# generate_app_icon.py
#
# מייצר את סמל המותג של ClipForge (רקע כתום מעוגל + קלֶפֶּרבורד 🎬 במרכז) -
# ריבוע מעוגל בצבע מותג *קבוע* (לא accent הנושא הנוכחי, שהמשתמש יכול לשנות
# בכל רגע - סמל מותג יציב לא אמור לזוז יחד עם זה) עם גליף האמוג'י הצבעוני של
# 🎬 מרונדר דרך גופן האמוג'י של Windows עצמו (seguiemj.ttf, נתמך ב-Pillow
# דרך embedded_color=True). fallback לעיגול פשוט (אותו טכניקה שכבר קיימת
# באייקון המגש הישן ב-gui_manager.pyw) אם גופן האמוג'י לא זמין/נכשל - כדי
# שיצירת הסמל אף פעם לא תיכשל לגמרי.
#
# הרצה חד-פעמית: uv run python dev/generate_app_icon.py
# (התוצרים - assets/app_icon.ico ו-assets/app_icon.png - נשמרים בריפו כנכסים
# סטטיים קטנים, בדיוק כמו assets/overlay.png הקיים; אין צורך להריץ מחדש
# בכל הפעלה של האפליקציה).
import os

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
ICO_PATH = os.path.join(ASSETS_DIR, "app_icon.ico")
PNG_PATH = os.path.join(ASSETS_DIR, "app_icon.png")
# item: התקנת PWA לממשק הווב - manifest.json (web_app.py) מצביע על שני הגדלים
# האלה (192/512, המינימום הנפוץ לדרישות התקנת PWA של דפדפנים) - נגזרים מאותו
# מאסטר 512x512, לא נכס נפרד עם עיצוב משלו.
PNG_192_PATH = os.path.join(ASSETS_DIR, "app_icon_192.png")

MASTER_SIZE = 512
# כתום-"כבשן" - קבוע ובלתי-תלוי בערכת הנושא (accent) שהמשתמש יכול לשנות.
BRAND_BG_COLOR = (232, 93, 4, 255)
EMOJI_FONT_PATH = "C:/Windows/Fonts/seguiemj.ttf"


def _draw_emoji_badge():
    img = Image.new("RGBA", (MASTER_SIZE, MASTER_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = int(MASTER_SIZE * 0.22)
    draw.rounded_rectangle((0, 0, MASTER_SIZE - 1, MASTER_SIZE - 1), radius=radius, fill=BRAND_BG_COLOR)

    font = ImageFont.truetype(EMOJI_FONT_PATH, int(MASTER_SIZE * 0.6))
    # +10px אנכית - לפיצוי חזותי קל על ה-bounding box של גליף האמוג'י (לא
    # ממורכז מושלם מסביב לבסיס-הקו כברירת מחדל).
    draw.text((MASTER_SIZE // 2, MASTER_SIZE // 2 + 10), "🎬", font=font, embedded_color=True, anchor="mm")
    return img


def _draw_fallback_badge():
    """עיגול פשוט על אותו רקע מעוגל - אותה טכניקה בדיוק שכבר משמשת את אייקון
    המגש הישן ב-gui_manager.pyw, למקרה ש-seguiemj.ttf לא זמין/נכשל."""
    img = Image.new("RGBA", (MASTER_SIZE, MASTER_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = int(MASTER_SIZE * 0.22)
    draw.rounded_rectangle((0, 0, MASTER_SIZE - 1, MASTER_SIZE - 1), radius=radius, fill=BRAND_BG_COLOR)
    margin = int(MASTER_SIZE * 0.2)
    draw.ellipse((margin, margin, MASTER_SIZE - margin, MASTER_SIZE - margin), fill=(255, 255, 255, 255))
    return img


def generate():
    try:
        master = _draw_emoji_badge()
    except Exception as e:
        print(f"[!] רינדור גליף האמוג'י נכשל ({e}) - נופל חזרה לעיצוב גיאומטרי פשוט.")
        master = _draw_fallback_badge()

    os.makedirs(ASSETS_DIR, exist_ok=True)
    master.save(PNG_PATH)
    master.save(ICO_PATH, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    master.resize((192, 192), Image.LANCZOS).save(PNG_192_PATH)
    print(f"[*] נוצר: {ICO_PATH}")
    print(f"[*] נוצר: {PNG_PATH}")
    print(f"[*] נוצר: {PNG_192_PATH}")


if __name__ == "__main__":
    generate()
