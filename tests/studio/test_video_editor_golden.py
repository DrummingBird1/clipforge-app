# tests/studio/test_video_editor_golden.py - גל 48: process_video של עורך-העל קורא מאובייקט הגדרות (RenderConfig) ולא
# מהגלובלים - והפקודות שהוא בונה זהות בייט-בבייט לפקודות שנשמרו מהקוד לפני השינוי (48 צירופי דגלים,
# tests/video_editor_golden.py). בלי ffmpeg ובלי רינדור: הבדיקה, הזיהויים והקידוד עצמו מוחלפים.
# שינוי מכוון בפקודות = לכתוב מחדש את קובץ הזהב:  uv run python -m tests.video_editor_golden --write
import ast
import json
import tempfile


import pytest

from tests import video_editor_golden as golden


@pytest.fixture(scope="module")
def expected():
    with open(golden.GOLDEN, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("index", range(len(golden.SCENARIOS)), ids=[s["name"] for s in golden.SCENARIOS])
def test_ffmpeg_commands_are_unchanged(expected, index):
    scenario = golden.SCENARIOS[index]
    with tempfile.TemporaryDirectory(prefix="ve_golden_") as tmp:
        commands = golden.run_scenario(scenario, tmp, index)
    assert commands == expected[scenario["name"]]


def test_process_video_reads_settings_only_from_cfg():
    with open(golden.SCRIPT, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    module_names = {n.id for node in tree.body if not isinstance(node, (ast.FunctionDef, ast.ClassDef))
                    for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "process_video")
    leaked = sorted({n.id for n in ast.walk(func) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                     and n.id in module_names and (n.id.isupper() or n.id == "args")} - {"RENDER_CONFIG"})
    assert leaked == [], leaked


@pytest.mark.parametrize("pix_fmt, gpu", [("yuv420p", True), ("yuv420p10le", False), ("p010le", False)])
def test_more_than_8_bit_sdr_decodes_on_the_cpu(pix_fmt, gpu):
    # הרצה אמיתית (16.10): 10 ביט SDR עם --hwaccel ופילטר CPU נכשל מיד ב-"hwdownload ... nv12" - נתיב ה-CUDA 8 ביט בלבד
    scenario = {"name": "ten_bit", "flags": ["--codec", "hevc", "--hwaccel", "--eq-contrast", "1.2"], "probe": dict(golden.SDR, pix_fmt=pix_fmt)}
    with tempfile.TemporaryDirectory(prefix="ve_golden_") as tmp:
        commands = golden.run_scenario(scenario, tmp, 990)
    render = " ".join(commands[-1])
    assert ("-hwaccel" in render and "hwdownload" in render) is gpu, render


def test_a_file_can_get_other_settings_without_touching_the_globals():
    with tempfile.TemporaryDirectory(prefix="ve_golden_") as tmp:
        golden._prepare_files(tmp)
        module = golden._load(tmp, [], 999)
        hevc = module.RENDER_CONFIG.replace(CODEC="hevc", CODEC_QUALITY=26)
        assert module.CODEC == "h264" and module.RENDER_CONFIG.CODEC == "h264" and hevc.CODEC == "hevc"
        assert hevc.SETTINGS is module.SETTINGS and hevc.HWACCEL_REQUESTED is False
        with pytest.raises(AttributeError):
            module.RENDER_CONFIG.replace(NOT_A_SETTING=1)
