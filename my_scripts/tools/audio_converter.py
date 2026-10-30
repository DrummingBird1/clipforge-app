# Name: 🔊 הממיר לשמע-משחקים
# Name (EN): 🔊 Game Audio Converter (WAV→OGG)
# Description: ממיר קבצי WAV לפורמט OGG דחוס ואיכותי למשחקים.
# Description (EN): Converts WAV files to compressed, game-quality OGG format.
# Concurrency: light
# Safety: read-only

import os
import argparse
import sys

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure") and sys.stderr.encoding != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pydub import AudioSegment

def convert_wav_to_ogg(input_folder, output_folder, quality="5"):
    """
    ממיר את כל קובצי ה-WAV בתיקייה לפורמט OGG דחוס ואיכותי למשחקים.
    quality="5" מקביל בערך ל-160kbps, שזה איזון מושלם בין משקל קל לאיכות סאונד גבוהה.
    """
    # יצירת תיקיית היעד אם היא לא קיימת
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"נוצרה תיקיית יעד חדשה: {output_folder}")

    # סריקת הקבצים בתיקיית המקור
    for filename in os.listdir(input_folder):
        if filename.lower().endswith('.wav'):
            wav_path = os.path.join(input_folder, filename)

            # יצירת שם הקובץ החדש עם סיומת ogg
            ogg_filename = os.path.splitext(filename)[0] + '.ogg'
            ogg_path = os.path.join(output_folder, ogg_filename)

            print(f"ממיר כעת: {filename}...")

            try:
                # טעינת קובץ ה-WAV הכבד
                audio = AudioSegment.from_wav(wav_path)

                # ייצוא ל-OGG עם הגדרת האיכות (הביטרייט)
                # parameters=["-aq", quality] קובע את איכות הדחיסה של OGG
                audio.export(ogg_path, format="ogg", parameters=["-aq", quality])

                # בדיקת נפח החיסכון
                original_size = os.path.getsize(wav_path) / (1024 * 1024)
                new_size = os.path.getsize(ogg_path) / (1024 * 1024)
                print(f" הומר בהצלחה! משקל מקורי: {original_size:.2f}MB -> משקל חדש: {new_size:.2f}MB")

            except Exception as e:
                print(f"❌ שגיאה בהמרת הקובץ {filename}: {e}")

if __name__ == "__main__":
    # פרמטרים דינמיים - אותה מוסכמה כמו שאר הסקריפטים ב-my_scripts, כדי שיהיה ניתן
    # להריץ את הסקריפט הזה גם ישירות מה-GUI (worker.py מזין תמיד --input_dir)
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", type=str, default="./wav_tracks", help="תיקיית קובצי ה-WAV המקוריים")
    parser.add_argument("--output_dir", type=str, default="", help="תיקיית היעד לקובצי ה-OGG (ברירת מחדל: ./ogg_assets ליד תיקיית המקור)")
    parser.add_argument("--quality", type=str, default="5", help="איכות דחיסת OGG (0=הכי טוב, 9=הכי קטן)")
    args = parser.parse_args()

    SOURCE_DIR = args.input_dir
    TARGET_DIR = args.output_dir if args.output_dir else os.path.join(os.path.dirname(os.path.abspath(SOURCE_DIR)), "ogg_assets")

    if not os.path.exists(SOURCE_DIR):
        print(f"[ERROR] התיקייה לא נמצאה: {SOURCE_DIR}")
    else:
        convert_wav_to_ogg(SOURCE_DIR, TARGET_DIR, quality=args.quality)
        print("\n כל קבצי המוזיקה מוכנים וממוטבים למשחק!")
