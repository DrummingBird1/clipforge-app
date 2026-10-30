# tests/studio/test_editor_field_schema.py - גל 37: סכימת שדות אחת (utils/video/editor_field_schema.py)
#
# שדה בעורך-העל מוגדר במקורות שונים (CLI, אזור, הסבר, סגנון, רישום ב-JS). הטסט הזה תופס שדה
# שנוסף לאחד מהם ונשכח באחר - לפני שהוא מתגלה בריצה.
import re

from entrypoints.web import frontend_assembly as fa
from utils.video import editor_field_schema as efs
from utils.video.video_editor_field_help import FIELD_HELP
from utils.video.video_editor_profiles import PROFILE_FIELDS

from tests.web_app_support import client  # noqa: F401

# שדות שקיימים רק בממשק (לא דגל CLI): הקבצים, השכבות כ-JSON, יעדים ומיתוג
UI_ONLY = {"folder", "queue_files", "layers", "targets", "brand_kit", "favorite_fields"}
# שדות של מצב ריצה (ולא של המראה) - אין להם אזור במפקח
NO_AREA = {"force", "preview_only", "validate_only", "favorite_fields"}


def _js_registered_keys():
    js = "".join(fa.read_part(part) for part in fa.page_parts() if part.endswith(".js"))
    return sorted(set(re.findall(r'^\s+([a-z0-9_]+): \{id: "ve[A-Za-z0-9]+"', js, re.M)))


def test_every_field_registered_in_the_ui_is_in_the_schema():
    keys = _js_registered_keys()
    assert len(keys) > 100
    assert efs.fields_missing(keys) == []
    schema = efs.field_schema()
    assert [k for k in keys if not schema[k]["flag"] and k not in UI_ONLY] == []
    assert [k for k in keys if not schema[k]["help"]] == []
    assert [k for k in keys if not schema[k]["area"] and k not in NO_AREA] == []


def test_help_and_style_fields_are_real_fields():
    schema = efs.field_schema()
    known = set(_js_registered_keys()) | set(efs.cli_fields()) | UI_ONLY
    assert sorted(set(FIELD_HELP) - known) == []
    assert all(schema[k]["profile"] for k in PROFILE_FIELDS)


def test_aliases_point_to_real_flags():
    cli = efs.cli_fields()
    for field, dest in efs.CLI_DEST_ALIASES.items():
        assert dest in cli, dest
        assert efs.field_flag(field) == cli[dest]["flags"][0]
    assert efs.field_flag("lut_path") == "--lut"
    assert efs.field_flag("nvenc_cq") == "--nvenc-cq"


def test_types_defaults_and_choices_come_from_the_parser():
    schema = efs.field_schema()
    assert schema["watermark_scale"]["type"] == "float" and schema["watermark_scale"]["default"] == 0.15
    assert schema["vertical"]["type"] == "bool"
    assert "bottom-right" in schema["watermark_position"]["choices"]


def test_field_schema_route():
    data = client.get("/api/video_editor/field_schema").json()["fields"]
    assert data["lut_path"]["flag"] == "--lut" and data["lut_path"]["term"]
