# tests/studio/test_property_based_video_math.py
#
# בדיקות property-based (hypothesis) לפונקציות גיאומטריה/מהירות טהורות -
# במקום כמה דוגמאות ידניות (tests/studio/test_video_editor.py וכו', שנשארים כפי
# שהם), אלה מייצרות מאות קלטים אקראיים בטווחים סבירים ובודקות שהתכונות
# הבסיסיות (הידוק בתוך גבולות הפריים, שימור יחס-גובה-רוחב, מכפלת ה-atempo
# המשורשרת שווה למקדם המקורי) מתקיימות תמיד, לא רק במקרי הבדיקה הידניים.


from hypothesis import given, settings
from hypothesis import strategies as st

from utils.media.timelapse import build_atempo_chain, compute_speed_factor
from utils.video.video_editor import WATERMARK_POSITIONS, compute_removal_region, compute_watermark_geometry

_positions = st.sampled_from(WATERMARK_POSITIONS)
_dimensions = st.integers(min_value=100, max_value=4000)
_small_dimensions = st.integers(min_value=1, max_value=2000)
_fractions = st.floats(min_value=0.01, max_value=0.9, allow_nan=False, allow_infinity=False)
_margins = st.integers(min_value=0, max_value=100)


@given(
    output_width=_dimensions, output_height=_dimensions,
    watermark_width=_small_dimensions, watermark_height=_small_dimensions,
    position=_positions, scale_fraction=_fractions, margin=_margins,
)
@settings(max_examples=200)
def test_watermark_geometry_always_stays_inside_the_frame(output_width, output_height, watermark_width, watermark_height, position, scale_fraction, margin):
    target_w, target_h, x, y = compute_watermark_geometry(
        output_width, output_height, watermark_width, watermark_height, position, scale_fraction=scale_fraction, margin=margin
    )
    assert target_w > 0
    assert target_h > 0
    assert x >= 0
    assert y >= 0
    assert x + target_w <= output_width
    assert y + target_h <= output_height


@given(
    output_width=_dimensions, output_height=_dimensions,
    watermark_width=_small_dimensions, watermark_height=_small_dimensions,
    position=_positions, scale_fraction=_fractions,
)
@settings(max_examples=200)
def test_watermark_geometry_preserves_aspect_ratio(output_width, output_height, watermark_width, watermark_height, position, scale_fraction):
    # יחס-רוחב/גובה יחסי (לא ה-target_w/target_h המדויקים) - compute_watermark_geometry
    # יכול לגזור את הגודל מהרוחב *או* מהגובה (ראו ההערה שם: watermark עם יחס-
    # גובה-רוחב קיצוני על פריים לא-שגרתי עלול לחרוג בגובה אם הגזירה תמיד
    # הייתה מהרוחב בלבד) - שני המסלולים אמורים לשמר את אותו יחס, בקירוב עגילה.
    target_w, target_h, _x, _y = compute_watermark_geometry(
        output_width, output_height, watermark_width, watermark_height, position, scale_fraction=scale_fraction
    )
    assert abs(target_w * watermark_height - target_h * watermark_width) <= max(watermark_width, watermark_height)


@given(
    frame_width=_dimensions, frame_height=_dimensions,
    position=_positions, width_fraction=_fractions, height_fraction=_fractions, margin=_margins,
)
@settings(max_examples=200)
def test_removal_region_always_stays_inside_the_frame(frame_width, frame_height, position, width_fraction, height_fraction, margin):
    x, y, w, h = compute_removal_region(frame_width, frame_height, position, width_fraction=width_fraction, height_fraction=height_fraction, margin=margin)
    assert w > 0
    assert h > 0
    assert x >= 0
    assert y >= 0
    assert x + w <= frame_width
    assert y + h <= frame_height


@given(duration=st.floats(min_value=0.1, max_value=100_000, allow_nan=False), target=st.floats(min_value=0.1, max_value=100_000, allow_nan=False))
@settings(max_examples=200)
def test_compute_speed_factor_is_none_iff_already_short_enough(duration, target):
    factor = compute_speed_factor(duration, target)
    if duration <= target:
        assert factor is None
    else:
        assert factor is not None
        assert factor > 1.0
        # מכפלת המקדם ביעד אמורה לשחזר בקירוב את האורך המקורי
        assert abs(factor * target - duration) < 1e-6 * max(1.0, duration)


@given(speed_factor=st.floats(min_value=1.0, max_value=500.0, allow_nan=False))
@settings(max_examples=200)
def test_build_atempo_chain_stages_multiply_back_to_original_factor(speed_factor):
    chain = build_atempo_chain(speed_factor)
    stage_values = [float(part.split("=")[1]) for part in chain.split(",")]
    product = 1.0
    for v in stage_values:
        product *= v
    assert abs(product - speed_factor) < 1e-3 * max(1.0, speed_factor)
    # כל שלב-ביניים (לא האחרון) הוא בדיוק 2.0 - זה מה ש-"משרשרים" אומר כאן
    for v in stage_values[:-1]:
        assert v == 2.0
