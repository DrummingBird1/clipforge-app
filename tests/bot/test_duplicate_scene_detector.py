# tests/bot/test_duplicate_scene_detector.py
#
# בודק utils/media/duplicate_scene_detector.py - הלוגיקה הטהורה בלבד (hashing +
# השוואת זוגות), בלי ffmpeg/OpenCV אמיתיים. אלה נבדקים ב-
# test_duplicate_scene_detector_e2e.py מול קובץ וידאו אמיתי.


import pytest

from utils.media.duplicate_scene_detector import (
    compute_average_hash_from_gray,
    compute_frame_match_fraction,
    find_cross_file_duplicate_pairs,
    find_duplicate_scene_pairs,
    hamming_distance,
)


def test_identical_images_produce_identical_hash():
    pixels = [100] * 64
    assert compute_average_hash_from_gray(pixels) == compute_average_hash_from_gray(pixels)


def test_hamming_distance_zero_for_identical_hashes():
    pixels = list(range(64))
    h = compute_average_hash_from_gray(pixels)
    assert hamming_distance(h, h) == 0


def test_hamming_distance_is_symmetric():
    a = compute_average_hash_from_gray([10] * 32 + [200] * 32)
    b = compute_average_hash_from_gray([200] * 32 + [10] * 32)
    assert hamming_distance(a, b) == hamming_distance(b, a)


def test_rejects_wrong_pixel_count():
    with pytest.raises(ValueError):
        compute_average_hash_from_gray([1, 2, 3])


def test_all_dark_vs_all_bright_are_maximally_different_in_pattern():
    # תמונה חצי-כהה-חצי-בהירה מול ההפך המדויק שלה - כל ביט אמור להתהפך.
    dark_then_bright = compute_average_hash_from_gray([10] * 32 + [250] * 32)
    bright_then_dark = compute_average_hash_from_gray([250] * 32 + [10] * 32)
    assert hamming_distance(dark_then_bright, bright_then_dark) == 64


def test_find_duplicate_scene_pairs_finds_similar_frames_far_apart():
    # פריים ב-t=0 וב-t=20 כמעט זהים (hash זהה) - אמור להיחשב "סצנה כפולה".
    same_hash = compute_average_hash_from_gray([100] * 64)
    different_hash_1 = compute_average_hash_from_gray([10] * 32 + [250] * 32)
    different_hash_2 = compute_average_hash_from_gray([250] * 16 + [10] * 16 + [250] * 32)
    timestamps = [0.0, 5.0, 10.0, 20.0]
    hashes = [same_hash, different_hash_1, different_hash_2, same_hash]

    pairs = find_duplicate_scene_pairs(timestamps, hashes, hash_threshold=8, min_gap_seconds=5.0)

    assert (0.0, 20.0, 0) in pairs
    assert not any(p[0] == 5.0 and p[1] == 10.0 for p in pairs)  # different_hash_1 vs different_hash_2 are far apart visually, not a duplicate


def test_find_duplicate_scene_pairs_ignores_frames_too_close_in_time():
    # שני פריימים זהים אבל קרובים מדי בזמן (רגע סטטי, לא סצנה שחוזרת) - לא
    # אמורים להיספר כ"כפילות".
    same_hash = compute_average_hash_from_gray([100] * 64)
    timestamps = [0.0, 2.0]  # gap of 2s, min_gap_seconds=5.0
    hashes = [same_hash, same_hash]

    pairs = find_duplicate_scene_pairs(timestamps, hashes, hash_threshold=8, min_gap_seconds=5.0)

    assert pairs == []


def test_find_duplicate_scene_pairs_respects_hash_threshold():
    a = compute_average_hash_from_gray([100] * 64)
    # הפוך ביט בודד בלבד (משנה פיקסל אחד קרוב לממוצע) - מרחק Hamming קטן אבל לא אפס
    b = compute_average_hash_from_gray([100] * 63 + [101])
    timestamps = [0.0, 10.0]
    hashes = [a, b]

    strict = find_duplicate_scene_pairs(timestamps, hashes, hash_threshold=0, min_gap_seconds=5.0)
    lenient = find_duplicate_scene_pairs(timestamps, hashes, hash_threshold=64, min_gap_seconds=5.0)

    assert lenient != []
    assert len(lenient) >= len(strict)


def test_find_duplicate_scene_pairs_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        find_duplicate_scene_pairs([0.0, 1.0], [123], hash_threshold=8, min_gap_seconds=5.0)


def test_find_duplicate_scene_pairs_empty_input():
    assert find_duplicate_scene_pairs([], [], hash_threshold=8, min_gap_seconds=5.0) == []


# --- compute_frame_match_fraction / find_cross_file_duplicate_pairs (item: cross-file duplicate clip detection) ---

def test_compute_frame_match_fraction_all_frames_match():
    h = compute_average_hash_from_gray([100] * 64)
    assert compute_frame_match_fraction([h, h, h], [h, h]) == 1.0


def test_compute_frame_match_fraction_no_frames_match():
    same = compute_average_hash_from_gray([100] * 64)
    different = compute_average_hash_from_gray([10] * 32 + [250] * 32)
    assert compute_frame_match_fraction([same, same], [different], hash_threshold=0) == 0.0


def test_compute_frame_match_fraction_partial_match():
    same = compute_average_hash_from_gray([100] * 64)
    different = compute_average_hash_from_gray([10] * 32 + [250] * 32)
    # אחד מתוך שניים ב-hashes_a תואם משהו ב-hashes_b
    assert compute_frame_match_fraction([same, different], [same], hash_threshold=0) == 0.5


def test_compute_frame_match_fraction_empty_a_is_zero():
    same = compute_average_hash_from_gray([100] * 64)
    assert compute_frame_match_fraction([], [same]) == 0.0


def test_compute_frame_match_fraction_does_not_require_index_alignment():
    # התאמה בסדר הפוך (a[0] תואם ל-b[1], a[1] תואם ל-b[0]) - עדיין 100%,
    # כי זה לא משווה לפי אינדקס, אלא "יש התאמה איפשהו".
    h1 = compute_average_hash_from_gray([100] * 64)
    h2 = compute_average_hash_from_gray([10] * 32 + [250] * 32)
    assert compute_frame_match_fraction([h1, h2], [h2, h1]) == 1.0


def test_find_cross_file_duplicate_pairs_flags_near_identical_files():
    h1 = compute_average_hash_from_gray([100] * 64)
    h2 = compute_average_hash_from_gray([10] * 32 + [250] * 32)
    file_hashes = {
        "clip_a.mp4": [h1, h2],
        "clip_b.mp4": [h1, h2],  # אותם hashes בדיוק - כנראה אותו קליפ
        "clip_c.mp4": [compute_average_hash_from_gray([200] * 20 + [50] * 44)],  # שונה לגמרי
    }

    pairs = find_cross_file_duplicate_pairs(file_hashes, hash_threshold=0, match_fraction_threshold=0.8)

    assert len(pairs) == 1
    name_a, name_b, similarity = pairs[0]
    assert {name_a, name_b} == {"clip_a.mp4", "clip_b.mp4"}
    assert similarity == 1.0


def test_find_cross_file_duplicate_pairs_no_duplicates_returns_empty():
    # שים לב: תמונה בצבע אחיד (כל הפיקסלים שווים) תמיד מייצרת אותו hash
    # ("כל הביטים דלוקים", כי כל פיקסל == הממוצע) בלי קשר לצבע עצמו - זו
    # תכונה ידועה של average-hash, אז הדפוסים כאן חייבים להיות לא-אחידים
    # כדי שבאמת ייצרו hash-ים שונים (כמו ביתר הטסטים בקובץ הזה).
    file_hashes = {
        "clip_a.mp4": [compute_average_hash_from_gray([10] * 32 + [250] * 32)],
        "clip_b.mp4": [compute_average_hash_from_gray([250] * 32 + [10] * 32)],  # ההפך המדויק
    }
    assert find_cross_file_duplicate_pairs(file_hashes, hash_threshold=0, match_fraction_threshold=0.8) == []


def test_find_cross_file_duplicate_pairs_sorted_by_similarity_descending():
    h1 = compute_average_hash_from_gray([100] * 64)
    h2 = compute_average_hash_from_gray([10] * 32 + [250] * 32)
    file_hashes = {
        "identical_a.mp4": [h1, h2],
        "identical_b.mp4": [h1, h2],
        "partial_a.mp4": [h1],
        "partial_b.mp4": [h1, h2],
    }

    pairs = find_cross_file_duplicate_pairs(file_hashes, hash_threshold=0, match_fraction_threshold=0.4)

    assert pairs[0][2] >= pairs[-1][2]
