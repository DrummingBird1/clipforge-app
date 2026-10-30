# utils/media/tesseract_locator.py
#
# מקור אמת יחיד לאיתור Tesseract-OCR - בניגוד ל-ffmpeg, הפרויקט לא מצרף עותק
# משלו (זו התקנה חיצונית עם installer, לא רק קובץ בינארי אחד להעתיק), אז בודק
# את נתיבי ההתקנה הסטנדרטיים בווינדוס ונופל בחזרה לפקודה הגלובלית "tesseract".

import os
import shutil

_COMMON_INSTALL_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def get_tesseract_exe():
    for path in _COMMON_INSTALL_PATHS:
        if os.path.exists(path):
            return path
    return "tesseract"


def is_tesseract_available():
    exe = get_tesseract_exe()
    if os.path.isabs(exe):
        return True
    return shutil.which(exe) is not None
