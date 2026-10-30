# utils/video/contact_sheet.py
#
# "Preview thumbnail contact-sheet" (item) - לפני רינדור batch שלם על תיקייה,
# מרכיב grid של תמונה אחת מייצגת מכל סרטון (שם + הפריים ב-20% מהאורך שלו) לתמונה
# אחת, כדי שאפשר יהיה לוודא שנבחרה התיקייה הנכונה לפני שריצה של דקות/שעות מתחילה.
# my_scripts/video/video_editor.py's --preview-only משתמש בזה במקום לרנדר בפועל.

import os
import tempfile

from PIL import Image, ImageDraw, ImageFont

from utils.media.thumbnail_generator import extract_frame_at_timestamp, get_video_duration_via_ffprobe

MAX_COLUMNS = 5
THUMB_WIDTH = 320
THUMB_ASPECT_RATIO = 9 / 16  # תואם לרזולוציית הפלט הקבועה (16:9) של video_editor.py
CAPTION_HEIGHT = 22
CELL_PADDING = 6
SHEET_BACKGROUND = (24, 24, 24)
PLACEHOLDER_COLOR = (60, 60, 60)
CAPTION_COLOR = (230, 230, 230)


def compute_contact_sheet_columns(count: int, max_columns: int = MAX_COLUMNS) -> int:
    """מספר עמודות ה-grid - פשוט min(count, max_columns), כדי שאצווה קטנה (למשל
    2-3 סרטונים) לא תיפרש לרוחב מיותר עם עמודות ריקות."""
    if count <= 0:
        raise ValueError("count חייב להיות חיובי")
    return min(count, max_columns)


def generate_contact_sheet(video_paths, output_path, ffmpeg_exe="ffmpeg", ffprobe_exe="ffprobe", columns=None, thumb_width=THUMB_WIDTH):
    """
    מרכיב contact sheet יחיד (תמונת PNG) מתוך video_paths - פריים אחד מייצג
    (ב-20% מאורך הסרטון, לפני שינוי מהיר מדי בהתחלה) לכל קובץ, עם שם הקובץ
    ככיתוב מתחתיו. סרטון שהפריים שלו לא הצליח להיחלץ (קובץ פגום וכו') מקבל
    תא placeholder אפור במקום לעצור את כל התהליך - זו תצוגה מקדימה, לא הרינדור
    עצמו, אז כשל בקובץ בודד לא אמור למנוע תצוגה מקדימה לשאר האצווה.
    """
    if not video_paths:
        raise ValueError("video_paths ריק - אין ממה להרכיב contact sheet")

    columns = columns or compute_contact_sheet_columns(len(video_paths))
    rows = (len(video_paths) + columns - 1) // columns
    thumb_height = int(thumb_width * THUMB_ASPECT_RATIO)
    cell_width = thumb_width + CELL_PADDING * 2
    cell_height = thumb_height + CAPTION_HEIGHT + CELL_PADDING * 2

    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    with tempfile.TemporaryDirectory() as tmp_dir:
        for index, video_path in enumerate(video_paths):
            col, row = index % columns, index // columns
            cell_x = col * cell_width + CELL_PADDING
            cell_y = row * cell_height + CELL_PADDING

            frame_path = os.path.join(tmp_dir, f"frame_{index}.jpg")
            duration = get_video_duration_via_ffprobe(video_path, ffprobe_exe)
            timestamp = max(0.1, duration * 0.2)
            extracted = extract_frame_at_timestamp(video_path, timestamp, frame_path, ffmpeg_exe)

            if extracted and os.path.exists(frame_path):
                try:
                    with Image.open(frame_path) as frame:
                        thumb = frame.convert("RGB").resize((thumb_width, thumb_height))
                    sheet.paste(thumb, (cell_x, cell_y))
                except Exception:
                    extracted = False
            if not extracted:
                draw.rectangle([cell_x, cell_y, cell_x + thumb_width, cell_y + thumb_height], fill=PLACEHOLDER_COLOR)

            name = os.path.basename(video_path)
            label = name if len(name) <= 34 else name[:31] + "..."
            draw.text((cell_x, cell_y + thumb_height + 4), label, fill=CAPTION_COLOR, font=font)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sheet.save(output_path)
    return output_path
