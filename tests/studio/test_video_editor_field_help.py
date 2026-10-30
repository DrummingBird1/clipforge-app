# tests/studio/test_video_editor_field_help.py
#
# FIELD_HELP הוא מקור-האמת היחיד למונח הקצר וה-tooltip שמוצגים בדסקטופ ובווב
# (item: מונחים קצרים + tooltip/מקראה לכל הגדרה) - בדיקות אלה שומרות שהוא
# באמת "קצר" (לא חזר להיות משפט-הסבר מלא בטעות) ושהוא נשאר מסונכרן עם
# settings_tab.py's _favorite_field_registry (שני המקורות אמורים לכסות בדיוק
# את אותה קבוצת שדות, פחות שני היוצאים-מן-הכלל המתועדים).


from utils.video.video_editor_field_help import FIELD_HELP, field_help_as_json_dict


def test_every_entry_has_a_short_term_and_a_nonempty_tooltip():
    for key, help_ in FIELD_HELP.items():
        assert help_.term.strip(), f"{key}: term ריק"
        assert help_.tooltip.strip(), f"{key}: tooltip ריק"
        assert len(help_.term) <= 30, f"{key}: term ארוך מדי ({help_.term!r}) - זה אמור להיות מונח קצר, לא משפט"
        assert not help_.term.endswith(":"), f"{key}: term לא אמור להסתיים ב-':' כמו תווית-משפט ישנה"


def test_field_help_as_json_dict_round_trips_term_and_tooltip():
    as_json = field_help_as_json_dict()
    assert set(as_json.keys()) == set(FIELD_HELP.keys())
    for key, help_ in FIELD_HELP.items():
        assert as_json[key] == {"term": help_.term, "tooltip": help_.tooltip}


def test_field_help_keys_cover_every_profile_field():
    # PROFILE_FIELDS (utils/video/video_editor_profiles.py) הוא רשימת כל השדות
    # שנשמרים בפרופיל - watermark_x/watermark_y (קואורדינטות גרירה, לא שדה-UI
    # עצמאי משלהן, מכוסות מושגית בתוך watermark_position) ו-favorite_fields
    # עצמו (CSV פנימי, לא שדה-תוכן) הם היוצאים-מן-הכלל המתועדים היחידים.
    from utils.video.video_editor_profiles import PROFILE_FIELDS
    excluded_from_field_help = {"watermark_x", "watermark_y", "pip_x", "pip_y", "favorite_fields"}
    expected = set(PROFILE_FIELDS) - excluded_from_field_help
    missing = expected - set(FIELD_HELP.keys())
    assert not missing, f"חסרים ב-FIELD_HELP: {missing}"
