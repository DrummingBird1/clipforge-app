# dev/make_social_preview.py
#
# 30.10.2026 (הכנה להפצה ציבורית): התמונה של GitHub ל-"Social preview" (Settings -> General) - docs/images/social-preview.png,
# ‏1280x640. בלי צילומי מסך (הם של dev/make_screenshots.py ומשתנים): האייקון של האפליקציה, השם ושורת תיאור, בצבעים של
# הממשק (styles/00-tokens.css: --n-1 רקע, --brand הדגשה) ובפונט שלו (Heebo, ‏OFL, ‏assets/fonts/). בלי רשת ובלי נתוני משתמש.
#
#   uv run python dev/make_social_preview.py
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "images", "social-preview.png")
SIZE = (1280, 640)
BG, SURFACE, BORDER = "#0b0c0f", "#15181e", "#2c3240"
TEXT, MUTED, BRAND = "#e9ecf1", "#a2aabb", "#22d3ee"
FONT = os.path.join(ROOT, "assets", "fonts", "heebo-latin.woff2")
ICON = os.path.join(ROOT, "assets", "app_icon.png")
TAGLINE = "A local video studio for Windows"
CHIPS = ("Gameplay clips", "Data videos", "Shorts · TikTok · YouTube")
FOOTER = "Runs on your PC  ·  Edit in the browser  ·  MIT license"


def _font(size, weight):
    font = ImageFont.truetype(FONT, size)
    font.set_variation_by_axes([weight])
    return font


def render():
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)
    # פס הדגשה דק למעלה, כמו בכותרת של הממשק
    draw.rectangle((0, 0, SIZE[0], 6), fill=BRAND)

    icon = Image.open(ICON).convert("RGBA").resize((224, 224), Image.LANCZOS)
    img.paste(icon, (96, 160), icon)

    x = 372
    draw.text((x, 146), "ClipForge", font=_font(108, 800), fill=TEXT)
    draw.text((x, 286), TAGLINE, font=_font(42, 500), fill=MUTED)

    chip_font, cx = _font(26, 600), x
    for chip in CHIPS:
        left, top, right, bottom = draw.textbbox((0, 0), chip, font=chip_font)
        width = right - left + 40
        draw.rounded_rectangle((cx, 368, cx + width, 418), radius=25, fill=SURFACE, outline=BORDER, width=2)
        draw.text((cx + 20, 393), chip, font=chip_font, fill=BRAND, anchor="lm")
        cx += width + 14

    draw.line((96, 510, SIZE[0] - 96, 510), fill=BORDER, width=2)
    draw.text((96, 548), FOOTER, font=_font(28, 400), fill=MUTED)
    return img


def main():
    img = render()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT, optimize=True)
    print(f"{OUT} - {img.size[0]}x{img.size[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
