# tests/infra/test_disk_space.py


from utils.shared.disk_space import estimate_required_bytes, estimate_required_bytes_for_duration, has_enough_disk_space


def test_estimate_required_bytes_applies_safety_factor(tmp_path):
    f = tmp_path / "source.mp4"
    f.write_bytes(b"x" * 1000)
    assert estimate_required_bytes(str(f), safety_factor=1.5) == 1500


def test_estimate_required_bytes_missing_file_returns_zero():
    assert estimate_required_bytes(str("Z:\\not_a_real_file.mp4")) == 0


def test_estimate_required_bytes_for_duration_scales_with_outputs():
    single = estimate_required_bytes_for_duration(60, num_outputs=1, bitrate_mbps=8)
    double = estimate_required_bytes_for_duration(60, num_outputs=2, bitrate_mbps=8)
    assert double == single * 2
    assert single == 60 * 8 * 1_000_000 // 8


def test_estimate_required_bytes_for_duration_much_smaller_than_input_based_estimate():
    # 3 שעות מקור (10GB) נדחסות ל-60 שניות - ההערכה חייבת לשקף פלט קטן, לא
    # להניח שגוי שהפלט קרוב לגודל הקלט (כמו estimate_required_bytes הרגיל).
    duration_based = estimate_required_bytes_for_duration(60, num_outputs=2)
    assert duration_based < 10 * 1024 ** 3


def test_has_enough_disk_space_true_when_plenty_free(tmp_path):
    assert has_enough_disk_space(str(tmp_path), required_bytes=1024, min_free_bytes=1024) is True


def test_has_enough_disk_space_false_when_required_exceeds_free(tmp_path):
    huge_requirement = 10 ** 18  # יותר מכל דיסק אמיתי
    assert has_enough_disk_space(str(tmp_path), required_bytes=huge_requirement) is False


def test_has_enough_disk_space_walks_up_to_existing_parent(tmp_path):
    not_yet_created = tmp_path / "will_be_created_later" / "nested"
    assert has_enough_disk_space(str(not_yet_created), required_bytes=1024, min_free_bytes=1024) is True


def test_has_enough_disk_space_unreachable_path_does_not_block():
    # לא ניתן לבדוק בכלל (לא קיים, גם לא תיקיית אב הגיונית) - לא חוסמים
    assert has_enough_disk_space("", required_bytes=1024) is True
