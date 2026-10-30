# Name: 🎁 Wrapped שנתי
# Name (EN): 🎁 Annual Wrapped
# Description: מרכיב סרטון "Wrapped" שנתי (בסגנון Spotify Wrapped) - כרטיסי סטטיסטיקה (קליפים שפורסמו, שעות רינדור, התגית הכי נפוצה, שעות משחק) ואחריהם מבחר קליפים מייצג מהשנה.
# Description (EN): Builds an annual "Wrapped" video (Spotify-Wrapped style) - stat title cards (clips published, render hours, most common tag, hours played) followed by a representative sample of the year's clips.
# Safety: read-only

import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import shutil
import subprocess
from datetime import date

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.shared.workspace_dir import WORKSPACE_DIR  # CLIPFORGE_WORKSPACE_DIR (טסטים, שרת בדיקה) - ברירת המחדל workspace/ כמו קודם
from utils.shared.workspace_dir import ROCKET_SHORTS, existing_output_dir
from utils.shared.export_dir import follow_global  # כמו OUTPUT_BASE_DIR של rocket_shorts_publisher.py
from utils.media import game_playtime
from utils.shared import job_history, ui_language
from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.media.ffprobe_cache import probe_video
from utils.shared.i18n import fix_hebrew_word_order
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.media.wrapped_stats import (
    count_successful_jobs_and_hours_for_year,
    gather_year_clips,
    get_top_tags_for_year,
    sample_highlight_clips,
)
from utils.shared import data_paths

FFMPEG_EXE = get_ffmpeg_exe()
TAGS_CACHE_DIR = os.path.join(WORKSPACE_DIR, ".tags_cache")
CARD_DURATION_SECONDS = 3
MAX_HIGHLIGHT_CLIPS = 12
CARD_BG_COLOR = (12, 12, 16)
CARD_TEXT_COLOR = (255, 255, 255)
CARD_ACCENT_COLOR = (0, 229, 255)

parser = argparse.ArgumentParser()
parser.add_argument("--input_dir", type=str, default="", help="לא בשימוש ישיר - נשמר לתאימות עם worker.py")
parser.add_argument("--year", type=int, default=None, help="שנה קלנדרית ל-Wrapped - ברירת מחדל: השנה הנוכחית")
parser.add_argument("--source", choices=["youtube", "tiktok"], default="youtube")
parser.add_argument("--output_base", type=str, default="", help="דריסת תיקיית הבסיס לבדיקות - ברירת מחדל: output_dir מההגדרות")
args, _unknown = parser.parse_known_args()
args.year = args.year or date.today().year


def load_settings():
    settings_path = data_paths.path(data_paths.ROCKET_SETTINGS)
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _load_font(size_px):
    # seguisb.ttf (Segoe UI Semibold) תומך בעברית מלאה בלי shaping מיוחד (לא
    # כמו ערבית - כל אות עברית תמיד בצורתה הבודדת) - fix_hebrew_word_order
    # כבר פותר את סדר-המילים-ההפוך (אותה תופעת Tk מתועדת ב-utils/shared/i18n.py).
    # נופל ל-PIL's bitmap font אם הגופן לא נמצא (למשל לא-Windows) - מכוער אבל
    # לעולם לא קורס, כמו כל תוספת קוסמטית-בלבד בפרויקט הזה.
    try:
        return ImageFont.truetype(r"C:\Windows\Fonts\seguisb.ttf", size_px)
    except Exception:
        try:
            return ImageFont.load_default(size=size_px)
        except TypeError:
            return ImageFont.load_default()


# 30.10.2026: הטקסטים של הכרטיסים בשפת ההתקנה (utils/shared/ui_language.py)
CARD_TEXTS = {
    "he": {"year": "השנה שלך בקליפים", "clips": "קליפים פורסמו השנה", "render": "שעות רינדור השנה",
           "moment": "הרגע הכי נפוץ שלך השנה", "playtime": "שעות משחק ({game})"},
    "en": {"year": "Your year in clips", "clips": "clips published this year", "render": "hours of rendering this year",
           "moment": "your most common moment this year", "playtime": "hours played ({game})"},
}
TEXTS = CARD_TEXTS[ui_language.current()]
MAX_CARD_TEXT_WIDTH_FRACTION = 0.9  # שוליים של 10% מכל צד - אף שורה לא אמורה לגעת בקצה הקנבס
MIN_FONT_SIZE_PX = 14


def _fit_font_and_text(draw, text, max_font_size_px, max_width_px):
    """מקטין את גודל הגופן בהדרגה עד שהשורה נכנסת ברוחב הקנבס (עם שוליים) -
    בלי זה, טקסט ארוך (תגית ארוכה, שם משחק ארוך) על קנבס צר (למשל פורמט אנכי)
    היה נחתך מחוץ לתמונה במקום פשוט להיראות קטן יותר."""
    font_size = max_font_size_px
    while font_size > MIN_FONT_SIZE_PX:
        font = _load_font(font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width_px:
            return font, w, bbox[3] - bbox[1]
        font_size -= 2
    font = _load_font(MIN_FONT_SIZE_PX)
    bbox = draw.textbbox((0, 0), text, font=font)
    return font, bbox[2] - bbox[0], bbox[3] - bbox[1]


def render_title_card(lines, size, out_path):
    """lines: [(text, font_size_fraction, color), ...] - font_size_fraction
    יחסי לרוחב הקנבס (לא פיקסלים קבועים), כדי שאותו קלף ייראה נכון גם בפורמט
    אופקי (1920x1080) וגם אנכי (1080x1920) - ראו MAX_CARD_TEXT_WIDTH_FRACTION
    להגנה נוספת מפני טקסט שעדיין רחב מדי (תגית ארוכה במיוחד וכו')."""
    image = Image.new("RGB", size, CARD_BG_COLOR)
    draw = ImageDraw.Draw(image)
    max_width_px = size[0] * MAX_CARD_TEXT_WIDTH_FRACTION

    rendered = []
    total_height = 0
    for text, font_size_fraction, color in lines:
        display_text = fix_hebrew_word_order(text)
        max_font_size_px = max(MIN_FONT_SIZE_PX, int(size[0] * font_size_fraction))
        font, w, h = _fit_font_and_text(draw, display_text, max_font_size_px, max_width_px)
        rendered.append((display_text, font, color, w, h))
        total_height += h + 20

    y = (size[1] - total_height) / 2
    for display_text, font, color, w, h in rendered:
        draw.text(((size[0] - w) / 2, y), display_text, font=font, fill=color)
        y += h + 20

    image.save(out_path)


def render_card_video_segment(card_png_path, size, out_path):
    cmd = [
        FFMPEG_EXE, "-y", "-loop", "1", "-i", card_png_path, "-t", str(CARD_DURATION_SECONDS),
        "-vf", f"scale={size[0]}:{size[1]}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", out_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, creationflags=NO_WINDOW_FLAGS)
    return result.returncode == 0 and os.path.exists(out_path)


def build_stat_cards(work_dir, size, stats):
    """בונה קלף פתיחה + עד 4 קלפי סטטיסטיקה (רק לסטטיסטיקות עם נתון אמיתי -
    לא מציג "0" מטעה לסטטיסטיקה שאין עליה בכלל מידע), מחזיר רשימת נתיבי
    הסרטונים הקצרים שנוצרו, לפי הסדר."""
    segments = []

    def _add_card(card_name, lines):
        png_path = os.path.join(work_dir, f"{card_name}.png")
        segment_path = os.path.join(work_dir, f"{card_name}.mp4")
        render_title_card(lines, size, png_path)
        if render_card_video_segment(png_path, size, segment_path):
            segments.append(segment_path)

    _add_card("00_intro", [
        (f"Wrapped {stats['year']}", 0.12, CARD_ACCENT_COLOR),
        (TEXTS["year"], 0.06, CARD_TEXT_COLOR),
    ])

    if stats["clips_published"] > 0:
        _add_card("01_clips", [
            (str(stats["clips_published"]), 0.16, CARD_ACCENT_COLOR),
            (TEXTS["clips"], 0.05, CARD_TEXT_COLOR),
        ])

    if stats["render_hours"] > 0:
        _add_card("02_render_hours", [
            (f"{stats['render_hours']:.1f}", 0.16, CARD_ACCENT_COLOR),
            (TEXTS["render"], 0.05, CARD_TEXT_COLOR),
        ])

    if stats["top_tag"]:
        _add_card("03_top_tag", [
            (stats["top_tag"], 0.11, CARD_ACCENT_COLOR),
            (TEXTS["moment"], 0.05, CARD_TEXT_COLOR),
        ])

    if stats["top_game_hours"] is not None:
        game_name, hours = stats["top_game_hours"]
        _add_card("04_playtime", [
            (f"{hours:.1f}", 0.16, CARD_ACCENT_COLOR),
            (TEXTS["playtime"].format(game=game_name), 0.045, CARD_TEXT_COLOR),
        ])

    return segments


def compute_stats(year, source_dir):
    year_clips = gather_year_clips(source_dir, year)
    job_rows = job_history.get_jobs_since(f"{year}-01-01T00:00:00")
    run_count, render_hours = count_successful_jobs_and_hours_for_year(job_rows, year)
    top_tags = get_top_tags_for_year(TAGS_CACHE_DIR, year, limit=1)
    playtime_summary = game_playtime.get_playtime_summary_for_year(year)

    return {
        "year": year,
        "clips_published": len(year_clips),
        "render_runs": run_count,
        "render_hours": render_hours,
        "top_tag": top_tags[0][0] if top_tags else None,
        "top_game_hours": (playtime_summary[0][0], playtime_summary[0][1] / 3600) if playtime_summary else None,
    }, year_clips


def main():
    settings = load_settings()
    output_base = args.output_base or follow_global(settings.get("output_dir", BASE_DIR))
    source_dir = (
        # rocket_shorts/YouTube|TikTok, או התיקייה הישנה אם רק היא קיימת (לפני סקריפט ההעברה)
        existing_output_dir(ROCKET_SHORTS, "YouTube" if args.source == "youtube" else "TikTok", base=output_base)
    )

    if not os.path.exists(source_dir):
        print(f"❌ תיקיית המקור לא קיימת: {source_dir}")
        return

    stats, year_clips = compute_stats(args.year, source_dir)
    if not year_clips:
        print(f"ℹ️ לא נמצאו קליפים שפורסמו ב-{args.year} ב-{source_dir} - אין ממה להרכיב Wrapped.")
        return

    highlight_clips = sample_highlight_clips(year_clips, MAX_HIGHLIGHT_CLIPS)
    probe = probe_video(highlight_clips[0])
    size = (probe.get("width") or 1920, probe.get("height") or 1080)

    print(f"🎁 בונה Wrapped {args.year}: {stats['clips_published']} קליפים פורסמו, {stats['render_hours']:.1f} שעות רינדור, {len(highlight_clips)} קליפים נבחרים להיילייטס.")
    sys.stdout.flush()

    work_dir = os.path.join(source_dir, f"_wrapped_{args.year}_work")
    os.makedirs(work_dir, exist_ok=True)
    try:
        card_segments = build_stat_cards(work_dir, size, stats)
        all_segments = card_segments + highlight_clips

        concat_list_path = os.path.join(work_dir, "_concat_list.txt")
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for path in all_segments:
                escaped = path.replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        output_path = os.path.join(source_dir, f"Wrapped_{args.year}.mp4")

        cmd_copy = [FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", output_path]
        result = subprocess.run(cmd_copy, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NO_WINDOW_FLAGS)
        success = result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0

        if not success:
            print("⚠️ concat מהיר (ללא רה-קידוד) נכשל - מנסה עם רה-קידוד...")
            sys.stdout.flush()
            cmd_reencode = [
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path,
                "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", output_path,
            ]
            result = subprocess.run(cmd_reencode, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NO_WINDOW_FLAGS)
            success = result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0

        if success:
            print(f"\n✅ Wrapped {args.year} נוצר בהצלחה: {output_path}")
            print(f"RESULT: {json.dumps({'clips_published': stats['clips_published'], 'render_hours': round(stats['render_hours'], 1), 'output': output_path})}")
        else:
            print(f"\n❌ יצירת ה-Wrapped נכשלה: {result.stderr[-800:]}")
    finally:
        # תיקיית עבודה זמנית (כרטיסי PNG/MP4 ביניים + קובץ concat) - תמיד
        # מנוקה, גם אם הרכבת הסרטון נכשלה באמצע.
        shutil.rmtree(work_dir, ignore_errors=True)  # safe: work_dir is a temp dir this script created itself above


if __name__ == "__main__":
    main()
