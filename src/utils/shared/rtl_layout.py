# utils/shared/rtl_layout.py
#
# Tkinter/customtkinter אין להם שום מודעות ל-RTL: pack(side="right") ו-
# grid(column=i) מתייחסים תמיד ל"ימין"/"עמודה i" הגיאומטריים הקבועים, בלי
# קשר לכיוון השפה. עד כה כל תיקון RTL (סדר מילים בטקסט, סדר כרטיסיות)
# היה טלאי ידני נקודתי במקום שהתגלה בו באג. שני helpers קטנים כאן נותנים
# לקוד GUI *חדש* לתאר כיוון לוגי ("start"/"end", בדיוק כמו flex-start/
# flex-end ב-CSS) במקום left/right קשיח - כך שהוא RTL-נכון מאליו לפי
# state.language, בלי לחשב ידנית "מה ההפך" בכל מקום. קוד קיים שכבר תוקן
# ידנית (anchor="e" וכו') לא צריך להשתנות - זה כלי לעבודה הבאה.

from utils.shared.state import state


def rtl_side(logical_side):
    """ממיר צד לוגי ("start"/"end") לצד pack() פיזי (left/right) לפי כיוון
    השפה - בעברית start=right, end=left; באנגלית start=left, end=right.
    "left"/"right" ממשי עובר כמו שהוא בלי שינוי, לנוחות קריאה."""
    if logical_side == "start":
        return "left" if state.language == "en" else "right"
    if logical_side == "end":
        return "right" if state.language == "en" else "left"
    return logical_side


def rtl_column(index, total_columns):
    """ממיר אינדקס עמודה לוגי (0 = start, קרוב לתחילת הקריאה) לאינדקס grid()
    פיזי, לפי כיוון השפה וסך העמודות בשורה."""
    if state.language == "en":
        return index
    return total_columns - 1 - index
