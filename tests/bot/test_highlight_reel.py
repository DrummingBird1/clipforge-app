# tests/bot/test_highlight_reel.py
#
# בודק utils/media/highlight_reel.py's build_concat_filter_complex - בניית מחרוזת
# filter_complex בלבד (לא ffmpeg אמיתי), בדיוק כמו test_video_editor.py
# בודק את build_edit_filter_complex.


import pytest

from utils.media.highlight_reel import build_concat_filter_complex


def test_all_clips_have_audio_no_lavfi_needed():
    filter_complex, lavfi_indices = build_concat_filter_complex(3, [True, True, True], "scale=1920:1080", 30)

    assert lavfi_indices == []
    assert "concat=n=3:v=1:a=1[outv][outa]" in filter_complex
    for i in range(3):
        assert f"[{i}:v]scale=1920:1080,fps=30,setsar=1[v{i}]" in filter_complex
        assert f"[{i}:a]aresample=async=1:first_pts=0[a{i}]" in filter_complex
        assert f"[v{i}][a{i}]" in filter_complex


def test_clip_without_audio_gets_lavfi_placeholder():
    # קליפ 1 (אינדקס 1 מתוך 3) שקט - אמור לקבל anullsrc, ה-lavfi input הראשון
    # (אינדקס 3, כי יש 3 קליפים אמיתיים ב--i לפניו).
    filter_complex, lavfi_indices = build_concat_filter_complex(3, [True, False, True], "scale=1920:1080", 30)

    assert lavfi_indices == [1]
    assert "[3:a]anull[a1]" in filter_complex
    assert "[1:a]aresample" not in filter_complex


def test_multiple_clips_without_audio_get_sequential_lavfi_indices():
    filter_complex, lavfi_indices = build_concat_filter_complex(4, [False, True, False, False], "scale=1920:1080", 30)

    assert lavfi_indices == [0, 2, 3]
    # 4 קליפים אמיתיים (0..3) - lavfi הראשון באינדקס 4, השני ב-5, השלישי ב-6
    assert "[4:a]anull[a0]" in filter_complex
    assert "[5:a]anull[a2]" in filter_complex
    assert "[6:a]anull[a3]" in filter_complex
    assert "[1:a]aresample=async=1:first_pts=0[a1]" in filter_complex


def test_single_clip_is_allowed():
    filter_complex, lavfi_indices = build_concat_filter_complex(1, [True], "scale=1920:1080", 30)
    assert "concat=n=1:v=1:a=1[outv][outa]" in filter_complex
    assert lavfi_indices == []


def test_rejects_zero_clips():
    with pytest.raises(ValueError):
        build_concat_filter_complex(0, [], "scale=1920:1080", 30)


def test_rejects_mismatched_audio_flags_length():
    with pytest.raises(ValueError):
        build_concat_filter_complex(3, [True, False], "scale=1920:1080", 30)
