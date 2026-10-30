# utils/media/duplicate_scene_detector.py
#
# לוגיקה טהורה (בלי ffmpeg/OpenCV בפועל - ראו my_scripts/video/duplicate_scene_detector.py
# לחלק שקורא בפועל פריימים מהסרטון) לזיהוי סצנות כפולות *בתוך* סרטון בודד -
# שונה מ-my_scripts/tools/disk_scanner.py, שמאתר קבצים כפולים (hash של הקובץ
# כולו), לא סצנות חוזרות בתוך אותו קובץ (למשל מסך טעינה שחוזר, או קטע שהוקלט
# פעמיים בטעות).
#
# average hash (aHash) - לא perceptual hash "אמיתי" (כמו pHash מבוסס DCT), אבל
# מספיק טוב וזול לחישוב עבור "כמעט זהה חזותית" בין שני פריימים שנדגמו מאותו
# סרטון, בלי לדרוש ספריית hashing חיצונית נוספת.


def compute_average_hash_from_gray(gray_pixels_8x8):
    """gray_pixels_8x8: איטרבל שטוח של 64 ערכי אפור (0-255), סדר שורה-אחר-שורה
    של תמונה 8x8. מחזיר hash בן 64 ביט (int) - ביט i דלוק אם הפיקסל ה-i-י
    גדול/שווה לממוצע כל הפיקסלים."""
    pixels = list(gray_pixels_8x8)
    if len(pixels) != 64:
        raise ValueError("expected exactly 64 pixels (8x8 grayscale)")
    mean = sum(pixels) / len(pixels)
    bits = 0
    for i, p in enumerate(pixels):
        if p >= mean:
            bits |= 1 << i
    return bits


def hamming_distance(hash_a, hash_b):
    """מספר הביטים השונים בין שני hash-ים בני 64 ביט - 0 = זהים לגמרי,
    64 = הפוכים לגמרי. ~8/64 (12.5%) הוא סף סביר ל"כמעט זהה חזותית"."""
    return bin(hash_a ^ hash_b).count("1")


def compute_frame_match_fraction(hashes_a, hashes_b, hash_threshold=8):
    """
    חלק (0.0-1.0) מהפריימים ב-hashes_a שיש להם לפחות התאמה קרובה אחת (Hamming
    distance <= hash_threshold) איפשהו ב-hashes_b - לא דורש התאמה לפי אינדקס/סדר
    (item: cross-file duplicate clip detection), כי שני קבצים ש"זה אותו קליפ"
    יכולים להתחיל בהיסט זמן שונה (למשל אותה הקלטה שנחתכה פעמיים במקומות שונים
    בהתחלה/בסוף) - השוואה מבוססת-אינדקס הייתה מפספסת את זה.
    """
    if not hashes_a:
        return 0.0
    matched = sum(1 for h_a in hashes_a if any(hamming_distance(h_a, h_b) <= hash_threshold for h_b in hashes_b))
    return matched / len(hashes_a)


def find_cross_file_duplicate_pairs(file_hashes, hash_threshold=8, match_fraction_threshold=0.8):
    """
    file_hashes: dict {filename: [hash, ...]} - ה-hashes שכבר נדגמו לכל קובץ
    (item: cross-file duplicate clip detection - שונה מ-find_duplicate_scene_pairs
    למעלה, שמחפש סצנות חוזרות *בתוך* קובץ בודד; זה מחפש שני *קבצים* נפרדים
    שכנראה אותו קליפ בעצם, למשל אותו highlight שיוצא/יובא פעמיים בטעות תחת
    שני שמות). מחזיר [(file_a, file_b, similarity), ...] ממוין מהדומה ביותר,
    רק זוגות עם similarity >= match_fraction_threshold - הממוצע הסימטרי של
    compute_frame_match_fraction בשני הכיוונים (כדי שקובץ קצר בהרבה מהשני,
    עם התאמה חד-כיוונית מלאה אבל לא הפוכה, לא יסומן בטעות כ"זהה" באותה מידה
    כמו שני קבצים דומים באורכם).
    """
    filenames = list(file_hashes.keys())
    pairs = []
    for i in range(len(filenames)):
        for j in range(i + 1, len(filenames)):
            name_a, name_b = filenames[i], filenames[j]
            forward = compute_frame_match_fraction(file_hashes[name_a], file_hashes[name_b], hash_threshold)
            backward = compute_frame_match_fraction(file_hashes[name_b], file_hashes[name_a], hash_threshold)
            similarity = (forward + backward) / 2
            if similarity >= match_fraction_threshold:
                pairs.append((name_a, name_b, similarity))
    return sorted(pairs, key=lambda pair: -pair[2])


def find_duplicate_scene_pairs(timestamps, hashes, hash_threshold=8, min_gap_seconds=5.0):
    """מוצא זוגות פריימים (מתוך אותו סרטון) שנראים כמעט זהים אבל מרוחקים
    בזמן זה מזה - זה מה שמבדיל "סצנה שחוזרת במקום אחר בסרטון" (מסך טעינה,
    קטע שהוקלט פעמיים) מ"שני פריימים סמוכים של אותו רגע שקט/סטטי" (שגם הם
    יהיו כמעט זהים, אבל זה לא "כפילות" במובן המעניין). timestamps ו-hashes
    חייבים להיות מקבילים (timestamps[i] הוא הזמן של hashes[i]) וממוינים
    לפי זמן עולה. מחזיר רשימת (t1, t2, hamming_distance), ממוינת לפי t1."""
    n = len(timestamps)
    if len(hashes) != n:
        raise ValueError("timestamps and hashes must have the same length")

    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            if timestamps[j] - timestamps[i] < min_gap_seconds:
                continue
            distance = hamming_distance(hashes[i], hashes[j])
            if distance <= hash_threshold:
                pairs.append((timestamps[i], timestamps[j], distance))
    return pairs
