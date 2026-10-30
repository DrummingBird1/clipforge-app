# tests/studio/test_editor_model.py
#
# גל 12 - מודל הנתונים v2 (utils/video/editor_model.py): רמה ואזור לכל שדה (תואם ל-HTML
# בפועל), יעדים (מתכון × יעדים), תרגום עריכת-קליפ לדריסות פר-קובץ, מיגרציה צד-שרת
# ויצוא מובנה; ערכות מותג (utils/video/brand_kits.py) ופרויקטים (utils/video/editor_projects.py).
import json
import re


import pytest

from utils.video import brand_kits, editor_model as em, editor_projects
from utils.video import video_editor_profiles as vep


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))


# --- רמות ואזורים ---

def test_every_profile_field_has_an_area_except_ui_and_run_mode():
    missing = [f for f in vep.PROFILE_FIELDS if em.field_area(f) is None and em.field_level(f) not in ("ui", "run")]
    assert missing == []


def test_field_areas_match_where_the_page_shows_each_field():
    """שדה גלוי יושב באזור שלו ב-HTML; שדה legacy מוסתר - באזור של הבורר שכותב אותו."""
    from entrypoints.web.frontend_assembly import assemble_page
    html = assemble_page()
    spans = [(m.start(), m.group(1)) for m in re.finditer(r'<details class="ve-category[^"]*"[^>]*data-cat="(\w+)"', html)]
    legacy_at = html.index('id="veLegacyFields"')
    checked = 0
    for field in vep.PROFILE_FIELDS:
        element_id = "ve" + "".join(part.capitalize() for part in field.split("_"))
        pos = html.find(f'id="{element_id}"')
        if pos < 0 or pos > legacy_at:
            continue
        area = None
        for start, cat in spans:
            if start < pos:
                area = cat
        assert area == em.field_area(field), (field, area, em.field_area(field))
        checked += 1
    assert checked > 90


def test_levels():
    assert em.field_level("codec") == "target" and em.field_level("vertical") == "target"
    assert em.field_level("watermark_path") == "brand" and em.field_level("caption_style") == "brand"
    assert em.field_level("folder") == "project" and em.field_level("force") == "run"
    assert em.field_level("eq_saturation") == "recipe" and em.field_level("targets") == "recipe"


# --- יעדים ---

def test_sanitize_targets_drops_unknown_and_duplicates():
    assert em.sanitize_targets(["shorts", "nope", "shorts", "discord"]) == ["shorts", "discord"]
    assert em.sanitize_targets("tiktok, youtube") == ["tiktok", "youtube"]
    assert em.sanitize_targets(None) == []


def test_expand_targets_is_recipe_times_targets():
    payload = {"codec": "hevc", "vertical": False, "eq_saturation": 1.3, "targets": ["shorts", "discord"], "target_size_mb": 50}
    runs = em.expand_targets(payload)
    assert [t for t, _ in runs] == ["shorts", "discord"]
    shorts, discord = runs[0][1], runs[1][1]
    assert shorts["vertical"] is True and shorts["output_subdir"] == "shorts" and shorts["codec"] == "hevc"
    assert shorts["eq_saturation"] == 1.3 and shorts["target_size_mb"] == 50  # היעד לא נוגע במה שלא הגדיר
    assert discord["codec"] == "h264" and discord["target_size_mb"] == 9.5 and discord["vertical"] is False
    assert payload["vertical"] is False  # המקור לא השתנה


def test_expand_targets_without_targets_is_a_single_plain_run():
    payload = {"codec": "h264"}
    assert em.expand_targets(payload) == [(None, payload)]


def test_archive_target_removes_size_limit():
    [(_, run)] = em.expand_targets({"targets": ["archive"], "target_size_mb": 20})
    assert "target_size_mb" not in run and run["codec"] == "hevc"


# --- עריכת קליפ ---

def test_trim_only_clip_edit_stays_a_fast_trim():
    assert em.compile_clip_edit({"trim_start": "0:05", "trim_duration": 20}) == {"trim_start": 5.0, "trim_duration": 20.0}


def test_trim_plus_cuts_compiles_to_ranges_only():
    compiled = em.compile_clip_edit({"trim_start": 5, "trim_duration": 30, "remove_ranges": [[10, 12], [11, 15], [20, 22]]})
    assert compiled == {"remove_ranges": [[0.0, 5.0], [10.0, 15.0], [20.0, 22.0], [35.0, em.FAR_END_SECONDS]]}


def test_bad_ranges_are_dropped():
    assert em.compile_clip_edit({"remove_ranges": [[5, 2], ["a", 3], [1, 2]]}) == {"remove_ranges": [[1.0, 2.0]]}
    assert em.compile_clip_edit({"remove_ranges": "[[1,2]]"}) == {"remove_ranges": [[1.0, 2.0]]}
    assert em.compile_clip_edit("junk") == {}


def test_clip_layers_pass_through():
    layer = {"type": "text", "text": "GOAL", "start": 3, "end": 5}
    assert em.compile_clip_edit({"layers": [layer]}) == {"layers": [layer]}


def test_clip_logo_fields_pass_through_and_leave_time_alone():
    edit = {"watermark_path": "C:\\logo.png", "watermark_x": 0.4, "watermark_y": 0.6, "watermark_scale": 0.2, "watermark_position": ""}
    assert em.compile_clip_edit(edit) == {"watermark_path": "C:\\logo.png", "watermark_x": 0.4, "watermark_y": 0.6, "watermark_scale": 0.2}
    # עריכת לוגו בלבד לא מאפסת את הזמן - הקובץ נשאר עם החיתוך של כל הקבצים
    merged = em.merge_clip_edits_into_overrides({"a.mp4": {"trim_start": 3.0}}, {"a.mp4": {"watermark_opacity": 0.5}})
    assert merged == {"a.mp4": {"trim_start": 3.0, "watermark_opacity": 0.5}}


def test_reset_time_clip_edit_keeps_the_file_untrimmed():
    assert em.compile_clip_edit({"trim_start": "0", "trim_duration": "", "remove_ranges": "", "reset_time": True}) == {"trim_start": 0.0}
    assert em.compile_clip_edit({"reset_time": True}) == {"trim_start": 0.0}


def test_clip_edits_override_queue_overrides_per_file():
    overrides = {"a.mp4": {"trim_start": 2.0, "watermark_path": "C:\\logo.png"}, "b.mp4": {"trim_start": 1.0}}
    merged = em.merge_clip_edits_into_overrides(overrides, {
        "a.mp4": {"remove_ranges": [[3, 4]]}, "C:\\x\\c.mp4": {"trim_start": 7}, "d.mp4": {},
    })
    assert merged["a.mp4"] == {"watermark_path": "C:\\logo.png", "remove_ranges": [[3.0, 4.0]]}  # החיתוך הישן הוחלף
    assert merged["b.mp4"] == {"trim_start": 1.0}
    assert merged["c.mp4"] == {"trim_start": 7.0}
    assert "d.mp4" not in merged


# --- מיגרציה ויצוא מובנה ---

def test_migrate_moves_text_and_timestamp_into_layers_and_corner_into_region():
    old = {"text": "Hello", "text_position": "top", "text_font_size": 30, "timestamp_overlay": "bottom-right",
           "remove_watermark_position": "top-left", "remove_watermark_width_fraction": 0.25, "layers": []}
    new = em.migrate_profile(old)
    assert new["text"] == "" and new["timestamp_overlay"] == "" and new["remove_watermark_position"] == ""
    assert [layer["type"] for layer in new["layers"]] == ["text", "timestamp"]
    assert new["layers"][0]["position"] == "top-center" and new["layers"][0]["font_size"] == 30
    assert new["remove_watermark_region"] == "0,0,0.25,0.12"
    assert new["schema_version"] == em.SCHEMA_VERSION
    assert em.migrate_profile(new)["layers"] == new["layers"]  # אידמפוטנטי


def test_migrate_keeps_json_string_layers_as_string():
    new = em.migrate_profile({"text": "Hi", "layers": "[]"})
    assert isinstance(new["layers"], str) and json.loads(new["layers"])[0]["text"] == "Hi"


def test_structured_export_roundtrip():
    flat = {"codec": "av1", "eq_saturation": 1.2, "watermark_path": "C:\\l.png", "targets": ["shorts"], "brand_kit": "RL", "mystery": 1}
    view = em.structured_view(flat)
    assert view["recipe"]["export"] == {"codec": "av1"} and view["recipe"]["layers"] == {"watermark_path": "C:\\l.png"}
    assert view["targets"] == ["shorts"] and view["brand_kit"] == "RL" and view["other"] == {"mystery": 1}
    assert em.flatten_structured(view) == flat
    assert em.flatten_structured({"codec": "h264"}) == {"codec": "h264"}  # פרופיל שטוח ישן


def test_schema_description_lists_areas_targets_and_fields():
    schema = em.schema_description()
    assert [a["id"] for a in schema["areas"]][:3] == ["time", "look", "effects"]  # גל 34: סדר זרימת העבודה
    assert schema["fields"]["codec"] == {"area": "export", "level": "target", "section": "file"}
    assert "shorts" in schema["targets"] and schema["targets"]["shorts"]["safe_zone"] == "shorts"


# --- גל 28: הסכמה של המפקח (לשוניות, תתי-אזורים, תלויות) ---

def _visible_editor_html():
    from entrypoints.web.frontend_assembly import assemble_page
    html = assemble_page()
    return html[:html.index('id="veLegacyFields"')]


def test_the_page_areas_are_the_schema_areas_in_order():
    html = _visible_editor_html()
    on_page = re.findall(r'<details class="ve-category[^"]*"[^>]*data-cat="(\w+)"', html)
    assert [a for a in on_page if a != "runs"] == ["queue", "preview"] + [a for a in em.AREAS if a != "queue"]
    schema = em.schema_description()
    titles = {a["id"]: a["title"] for a in schema["areas"]}
    for area in ("look", "effects", "export"):
        assert f'<span class="ve-cat-title">{titles[area]}</span>' in html, area


def test_every_section_field_sits_inside_its_section_on_the_page():
    """כל שדה גלוי שהסכמה שמה בתת-אזור יושב בתוך ה-data-subcat שלו ב-HTML, ובאזור הנכון."""
    from html.parser import HTMLParser
    html = _visible_editor_html()
    found = {}

    class Walker(HTMLParser):
        VOID = {"input", "br", "hr", "img", "meta", "link", "source", "col", "area", "wbr"}

        def __init__(self):
            super().__init__()
            self.stack = []

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if a.get("id"):
                cat = sub = None
                for _t, at in self.stack + [(tag, a)]:
                    cat = at.get("data-cat", cat)
                    sub = at.get("data-subcat", sub)
                found[a["id"]] = (cat, sub)
            if tag not in self.VOID:
                self.stack.append((tag, a))

        def handle_endtag(self, tag):
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    break

    Walker().feed(html)
    checked = 0
    for area, sections in em.SECTIONS.items():
        for section, _title, _primary, fields in sections:
            assert f'data-subcat="{section}"' in html, section
            for field in fields:
                element_id = "ve" + "".join(part.capitalize() for part in field.split("_"))
                if element_id not in found:
                    continue  # שדה legacy מוסתר - נכתב מבורר מאוחד באותו תת-אזור
                assert found[element_id] == (area, section), (field, found[element_id], (area, section))
                assert em.field_area(field) == area, field
                checked += 1
    assert checked > 60
    # ולהפך: שדה גלוי בתוך תת-אזור מופיע ברשימה של אותו תת-אזור
    for field in vep.PROFILE_FIELDS:
        element_id = "ve" + "".join(part.capitalize() for part in field.split("_"))
        cat, sub = found.get(element_id, (None, None))
        if sub and cat in em.SECTIONS:
            assert em.field_section(field) == sub, (field, sub, em.field_section(field))


def test_dependencies_point_at_real_fields_and_are_served_to_the_page():
    fields = set(vep.PROFILE_FIELDS)
    for field, (parent, when) in em.DEPENDS_ON.items():
        assert field in fields and parent in fields, (field, parent)
        assert when in ("set", "true", ">1") or when.startswith("!"), when
        assert em.field_area(field) == em.field_area(parent), field  # התלוי והאב באותה לשונית
    schema = em.schema_description()
    assert schema["depends_on"]["chromakey_color"] == {"on": "chromakey", "when": "true"}
    effects = next(a for a in schema["areas"] if a["id"] == "effects")
    assert [s["id"] for s in effects["sections"]] == ["cleanup", "effects", "chromakey"] and effects["sections"][0]["primary"] is True


# --- ערכות מותג ---

def test_brand_kit_save_keeps_only_brand_fields_and_applies_at_run():
    kit = brand_kits.save_kit("RL", {"watermark_path": "C:\\rl.png", "caption_color": "#FFD700", "codec": "av1"},
                              templates=[{"name": "Lower third", "layer": {"type": "text", "text": "RL"}}, {"bad": 1}])
    assert kit["fields"] == {"watermark_path": "C:\\rl.png", "caption_color": "#FFD700"}
    assert [t["name"] for t in kit["templates"]] == ["Lower third"]
    merged = brand_kits.apply_brand_kit({"brand_kit": "RL", "watermark_path": "C:\\old.png", "codec": "h264"})
    assert merged["watermark_path"] == "C:\\rl.png" and merged["codec"] == "h264"
    assert brand_kits.apply_brand_kit({"brand_kit": "Gone", "codec": "h264"}) == {"brand_kit": "Gone", "codec": "h264"}


def test_brand_kit_rename_delete_and_bad_names():
    brand_kits.save_kit("A", {})
    brand_kits.rename_kit("A", "B")
    assert list(brand_kits.load_kits()) == ["B"]
    with pytest.raises(ValueError):
        brand_kits.save_kit("bad/name", {})
    assert brand_kits.delete_kit("B") is True and brand_kits.delete_kit("B") is False


def test_brand_kits_file_lives_next_to_profiles(tmp_path):
    brand_kits.save_kit("X", {})
    assert (tmp_path / "brand_kits.json").is_file()


# --- פרויקטים ---

def test_project_save_merge_load_and_list(tmp_path):
    folder = tmp_path / "footage"
    folder.mkdir()
    editor_projects.save_project(str(folder), {"recipe": {"codec": "hevc"}, "targets": ["shorts", "zzz"], "junk": 1})
    editor_projects.save_project(str(folder), {"clip_edits": {"a.mp4": {"trim_start": 3}}})
    project = editor_projects.load_project(str(folder))
    assert project["recipe"] == {"codec": "hevc"} and project["targets"] == ["shorts"] and "junk" not in project
    assert project["clip_edits"] == {"a.mp4": {"trim_start": 3}} and project["name"] == "footage"
    [row] = editor_projects.list_projects()
    assert row["folder"] == str(folder) and row["clip_edit_count"] == 1 and row["folder_exists"] is True


def test_project_list_includes_first_video_for_the_jobs_thumbnail(tmp_path):
    """גל 19: מסך העבודות מציג תמונה ממוזערת מהקובץ הראשון - המסומן הראשון בתור, או הווידאו הראשון לפי שם."""
    folder = tmp_path / "match_day"
    folder.mkdir()
    for name in ("b.mp4", "a.mkv", "notes.txt"):
        (folder / name).write_bytes(b"x")
    editor_projects.save_project(str(folder), {})
    [row] = editor_projects.list_projects()
    assert row["first_file"] == str(folder / "a.mkv")
    editor_projects.save_project(str(folder), {"queue": {"files": [{"name": "a.mkv", "selected": False}, {"name": "b.mp4"}]}})
    [row] = editor_projects.list_projects()
    assert row["first_file"] == str(folder / "b.mp4")
    empty = tmp_path / "empty"
    empty.mkdir()
    editor_projects.save_project(str(empty), {})
    assert {r["name"]: r["first_file"] for r in editor_projects.list_projects()}["empty"] is None


def test_project_export_import_and_delete(tmp_path):
    folder = tmp_path / "f"
    folder.mkdir()
    editor_projects.save_project(str(folder), {"recipe": {"codec": "av1"}})
    exported = editor_projects.export_project(str(folder))
    assert exported["format"] == editor_projects.EXPORT_FORMAT
    other = tmp_path / "g"
    other.mkdir()
    editor_projects.import_project(exported, folder=str(other))
    assert editor_projects.load_project(str(other))["recipe"] == {"codec": "av1"}
    with pytest.raises(ValueError):
        editor_projects.import_project({"format": "nope"})
    assert editor_projects.delete_project(str(folder)) is True and editor_projects.load_project(str(folder)) is None


def test_project_requires_existing_folder(tmp_path):
    with pytest.raises(ValueError):
        editor_projects.save_project(str(tmp_path / "missing"), {})
