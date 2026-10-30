# utils/media/highlight_reel.py
#
# בונה את מחרוזת ה-filter_complex למיזוג כמה קליפים (רזולוציות/פריימרייט/
# ערוצי-אודיו שונים, כי כל קליפ הגיע ממשחק אחר) לסרטון "highlight reel" אחד -
# ראו my_scripts/video/highlight_reel_maker.py. concat FILTER (לא concat
# DEMUXER) בכוונה - הדמאקסר דורש שכל הקלטים יהיו זהים בפרמטרים (קודק/רזולוציה),
# מה שכמעט אף פעם לא נכון כשהקליפים מגיעים ממשחקים/הקלטות שונות; הפילטר
# מבצע רסקייל+רי-אנקוד לכל קלט תחילה, כך שהם תמיד תואמים לפני החיבור.
#
# הלוגיקה כאן טהורה (בניית מחרוזת בלבד, אין קריאה ל-ffmpeg בפועל) בדיוק כמו
# utils/video/video_editor.py's build_edit_filter_complex - כדי שאפשר יהיה לבדוק
# אותה בטסטים בלי להריץ ffmpeg אמיתי.


def build_concat_filter_complex(num_clips, has_audio_flags, scale_chain, fps):
    """בונה filter_complex למיזוג num_clips קלטי וידאו (אינדקסים 0..num_clips-1)
    לסרטון אחד. has_audio_flags הוא רשימת bool (אורך num_clips) - True אם לקליפ
    הזה יש טראק אודיו אמיתי. קליפ בלי אודיו (למשל הקלטה שקטה) מקבל אודיו שקט
    מסונתז במקום - בלי זה, concat=... עם מספר סטרימי-אודיו לא-אחיד לכל קלט
    נכשל ב-ffmpeg בפועל ("Input link ... parameters mismatch").

    מחזיר (filter_complex: str, lavfi_indices: list[int]) - lavfi_indices הוא
    האינדקסים (בתוך has_audio_flags, לא אינדקסי -i בפועל) של הקליפים שזקוקים
    ל-anullsrc; הקורא אחראי להוסיף עבור כל אחד מהם קלט "-f lavfi -i anullsrc=...:duration=<משך הקליפ>"
    *אחרי* כל קלטי הקבצים האמיתיים, לפי הסדר הזה בדיוק (כך שהאינדקס בפועל של
    ה-lavfi ה-N-י הוא num_clips + N)."""
    if num_clips < 1:
        raise ValueError("num_clips must be at least 1")
    if len(has_audio_flags) != num_clips:
        raise ValueError("has_audio_flags length must match num_clips")

    parts = []
    concat_labels = []
    lavfi_indices = []
    lavfi_counter = 0

    for i in range(num_clips):
        parts.append(f"[{i}:v]{scale_chain},fps={fps},setsar=1[v{i}]")
        if has_audio_flags[i]:
            parts.append(f"[{i}:a]aresample=async=1:first_pts=0[a{i}]")
        else:
            lavfi_input_index = num_clips + lavfi_counter
            parts.append(f"[{lavfi_input_index}:a]anull[a{i}]")
            lavfi_indices.append(i)
            lavfi_counter += 1
        concat_labels.append(f"[v{i}][a{i}]")

    parts.append("".join(concat_labels) + f"concat=n={num_clips}:v=1:a=1[outv][outa]")
    return ";".join(parts), lavfi_indices
