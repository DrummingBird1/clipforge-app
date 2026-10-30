# tests/infra/test_benchmarks.py
#
# בנצ'מארק ביצועים (item: dev/infra - benchmark suite for render-performance
# regression tracking) לחלק ה"טהור" (בלי ffmpeg בפועל) ממסלול הרינדור/ניתוח
# הווידאו - החישובים שרצים על כל פריים/סרטון/תיקייה בפועל, שבהם רגרסיה בביצועים
# (למשל שינוי תמים שהופך O(n) ל-O(n^2)) הייתה נשארת סמויה עד שמישהו מריץ על
# תיקייה גדולה באמת ומחכה הרבה יותר זמן משציפה. בכוונה *לא* מכיל שום קריאת
# ffmpeg/ffprobe אמיתית - זו לא בנצ'מארק לזמן-רינדור-בפועל (תלוי-חומרה, לא
# דטרמיניסטי, לא שווה להריץ ב-CI) אלא לחלק ה-Python הטהור שמזין את ההחלטות
# סביבו: חתימת-רינדור (smart re-encode skip), סריקת-תיקיות רקורסיבית
# (video_editor.py's --input_dir recursion), וזיהוי קליפים כפולים (perceptual
# hashing). כל טסט כאן רץ גם כטסט רגיל (assert על נכונות הפלט) - pytest-benchmark
# רק מוסיף מדידת-זמן סביב אותה קריאה, לא הופך את זה לתלוי-בזמן-מוחלט; ה-JSON
# שנשמר (--benchmark-autosave) הוא כלי-פיתוח מקומי, לא שער-CI - בדיוק כמו
# mutmut (ראו README, "Mutation Testing") השוואת זמן-ריצה מוחלט על ריצות
# CI נפרדות (חומרה משותפת, לא-דטרמיניסטית) לא אמינה מספיק בשביל שער חובה.


from utils.video.video_editor import compute_render_signature
from utils.media.timelapse import find_video_files_by_folder
from utils.media.duplicate_scene_detector import (
    compute_average_hash_from_gray,
    hamming_distance,
    compute_frame_match_fraction,
    find_cross_file_duplicate_pairs,
)


def test_benchmark_compute_render_signature(benchmark):
    source_fingerprint = "video.mp4:1700000000:123456789"
    params = {f"param_{i}": f"value_{i}" for i in range(30)}

    result = benchmark(compute_render_signature, source_fingerprint, params)

    assert len(result) == 64  # sha256 hex digest


def test_benchmark_find_video_files_by_folder(tmp_path, benchmark):
    # 40 תת-תיקיות עם 5 קבצי וידאו (מסיומות שונות) כל אחת - סדר גודל סביר
    # לפרויקט "הקלטות מפוצלות לפי תיקייה" בפועל, לא תיקייה ריקה טריוויאלית.
    for folder_i in range(40):
        folder = tmp_path / f"session_{folder_i:03d}"
        folder.mkdir()
        for file_i in range(5):
            ext = [".mp4", ".mkv", ".mov", ".avi"][file_i % 4]
            (folder / f"clip_{file_i}{ext}").write_bytes(b"")

    result = benchmark(find_video_files_by_folder, str(tmp_path))

    assert len(result) == 40
    assert sum(len(videos) for _folder, videos in result) == 200


def test_benchmark_compute_average_hash_from_gray(benchmark):
    gray_pixels = [(i * 37) % 256 for i in range(64)]

    result = benchmark(compute_average_hash_from_gray, gray_pixels)

    assert isinstance(result, int)


def test_benchmark_hamming_distance(benchmark):
    hash_a, hash_b = 0x1234567890ABCDEF, 0xFEDCBA0987654321

    result = benchmark(hamming_distance, hash_a, hash_b)

    assert 0 <= result <= 64


def test_benchmark_compute_frame_match_fraction(benchmark):
    # 150 פריימים נדגמים לכל קובץ (סרטון קצר-בינוני שנדגם כל כמה שניות) -
    # compute_frame_match_fraction הוא O(len(hashes_a) * len(hashes_b)), אז
    # זה בדיוק סדר-הגודל שבו רגרסיה אלגוריתמית תיראה בפועל.
    hashes_a = [i * 1000 for i in range(150)]
    hashes_b = [i * 1000 + 1 for i in range(150)]

    result = benchmark(compute_frame_match_fraction, hashes_a, hashes_b)

    assert result == 1.0  # כל hash ב-a במרחק 1 ביט בלבד מ-hash תואם ב-b


def test_benchmark_find_cross_file_duplicate_pairs(benchmark):
    # 15 קבצים * 80 פריימים כל אחד - find_cross_file_duplicate_pairs קורא
    # ל-compute_frame_match_fraction פעמיים לכל זוג קבצים, אז זה O(files^2 * frames^2)
    # יחד - בדיוק המקום שרגרסיה קטנה בכל אחת מהשכבות תצטבר ותיראה הכי ברור.
    file_hashes = {f"clip_{i}.mp4": [j * 1000 + i for j in range(80)] for i in range(15)}

    result = benchmark(find_cross_file_duplicate_pairs, file_hashes)

    assert isinstance(result, list)
