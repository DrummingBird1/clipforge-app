# tests/studio/test_color_audio.py
#
# גל 25: כלי צבע ושמע מקצועיים (utils/video/color_audio.py) - בניית הפילטרים, השילוב בשרשרת
# (build_edit_filter_complex), הדגלים מהממשק (_build_wave25_args), בדיקת השדות, והרישום
# בכל המקומות שהשדה צריך להופיע בהם. בסוף: ריצה אמיתית של video_editor.py עם הכל יחד.
import os
from tests import PROJECT_ROOT
import subprocess
import sys


import pytest

from utils.video import color_audio as ca
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

from tests.conftest import remove_video_editor_output

BASE_DIR = PROJECT_ROOT
from utils.shared.workspace_dir import WORKSPACE_DIR  # הזמני של הריצה (tests/conftest.py) - לא workspace/ של המשתמש
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "video_editor.py")
HORIZONTAL_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "studio", "horizontal")
WAVE25_FIELDS = ("grade_shadows", "grade_midtones", "grade_highlights", "curves_preset", "curves_master", "curves_red", "curves_green",
                 "curves_blue", "audio_highpass", "audio_eq_low", "audio_eq_mid", "audio_eq_mid_freq", "audio_eq_high", "audio_compressor",
                 "audio_denoise", "audio_denoise_model")


def _ffmpeg_available():
    import shutil
    exe = get_ffmpeg_exe()
    return (os.path.isabs(exe) and os.path.exists(exe)) or bool(shutil.which(exe))


needs_ffmpeg = pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg לא זמין בסביבה הזו")


# --- צבע ---

def test_wheels_become_a_colorbalance_filter_with_only_the_non_zero_offsets():
    assert ca.build_colorbalance_filter("", "  ", None) == ""
    assert ca.build_colorbalance_filter("0,0,0.05", "", "0.1, -0.02 ,0") == "colorbalance=bs=0.050:rh=0.100:gh=-0.020"
    assert ca.parse_rgb_offsets("2,-3,0.5") == (1.0, -1.0, 0.5)  # מהודק ל-1..-1
    with pytest.raises(ValueError):
        ca.parse_rgb_offsets("0.1,0.2")


def test_curves_combine_a_preset_with_custom_points_and_skip_the_identity():
    assert ca.build_curves_filter("none", "0/0 1/1") == ""
    assert ca.build_curves_filter("vintage") == "curves=preset=vintage"
    assert ca.build_curves_filter("none", "0/0 0.5/0.62 1/1", blue="0/0.1 1/0.9") == "curves=master='0/0 0.5/0.62 1/1':blue='0/0.1 1/0.9'"
    for bad in ("0/0", "0/0 0.5", "0/0 1.2/1", "0.5/0.5 0.2/0.1 1/1", " ".join(f"{i / 20}/{i / 20}" for i in range(20))):
        with pytest.raises(ValueError):
            ca.build_curves_filter("none", bad)
    with pytest.raises(ValueError):
        ca.build_curves_filter("sepia")


def test_grade_is_wheels_then_curves():
    grade = ca.build_color_grade_filter("0,0,0.05", curves_preset="lighter")
    assert grade == "colorbalance=bs=0.050,curves=preset=lighter"
    assert ca.build_color_grade_filter() == ""


# --- שמע ---

def test_audio_chain_order_is_lowcut_denoise_eq_compressor():
    chain = ca.build_audio_fx_chain(80, 3, -2, 2500, 4, "voice", "medium")
    assert [f.split("=")[0] for f in chain] == ["highpass", "afftdn", "bass", "equalizer", "treble", "acompressor"]
    assert ca.build_audio_fx_chain() == []
    assert ca.build_audio_fx_chain(0, 0.02, 0, 1000, 0, "off", "off") == []


def test_eq_values_are_clamped_and_formatted():
    assert ca.build_audio_eq_filters(5, 40, -40, 99999, 0.5) == [
        "highpass=f=20", "bass=g=20:f=120", "equalizer=f=5000:t=q:w=1:g=-20", "treble=g=0.5:f=8000"]


def test_denoise_uses_rnnoise_when_a_model_is_given():
    assert ca.build_audio_denoise_filter("strong") == "afftdn=nr=20:nf=-40"
    assert ca.build_audio_denoise_filter("light", r"C:\models\voice.rnnn") == r"arnndn=m='C\:/models/voice.rnnn':mix=0.5"
    assert ca.build_audio_denoise_filter("off", "x.rnnn") == ""
    with pytest.raises(ValueError):
        ca.build_audio_denoise_filter("max")
    with pytest.raises(ValueError):
        ca.build_audio_fx_chain(compressor="brickwall")


def test_audio_fx_sit_after_tempo_and_before_gate_and_loudnorm():
    from utils.video.video_editor import build_edit_filter_complex
    graph, maps = build_edit_filter_complex(
        "scale=640:360", 30, speed_factor=1.5, keep_audio=True, loudnorm=True, noise_gate=True,
        audio_fx_filters=["highpass=f=80", "acompressor=threshold=-24dB"],
    )
    audio = next(part for part in graph.split(";") if part.endswith("[outa]"))
    order = [audio.index(name) for name in ("atempo", "highpass", "acompressor", "agate", "loudnorm")]
    assert order == sorted(order)
    assert "[outa]" in maps
    # בלי שמע - האפקטים לא נכנסים בכלל
    graph, _maps = build_edit_filter_complex("scale=640:360", 30, keep_audio=False, audio_fx_filters=["highpass=f=80"])
    assert "highpass" not in graph


@needs_ffmpeg
def test_every_filter_we_build_runs_in_ffmpeg():
    video = ca.build_color_grade_filter("0.05,0,-0.05", "0,0.03,0", "-0.02,0,0.08", "strong_contrast",
                                        "0/0 0.3/0.25 0.7/0.8 1/1", "0/0 1/0.95", "", "0/0.05 1/1")
    audio = ca.build_audio_fx_chain(100, 2.5, -3, 3000, 1.5, "strong", "light")
    cmd = [get_ffmpeg_exe(), "-hide_banner", "-v", "error", "-f", "lavfi", "-i", "testsrc2=d=0.5:s=160x120", "-f", "lavfi", "-i", "sine=d=0.5",
           "-filter_complex", f"[0:v]{video}[v];[1:a]{','.join(audio)}[a]", "-map", "[v]", "-map", "[a]", "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, result.stderr
    for preset in ca.CURVES_PRESETS[1:]:
        for compressor in ca.COMPRESSOR_PRESETS:
            pass
        result = subprocess.run([get_ffmpeg_exe(), "-hide_banner", "-v", "error", "-f", "lavfi", "-i", "testsrc2=d=0.1:s=64x48",
                                 "-vf", ca.build_curves_filter(preset), "-f", "null", "-"], capture_output=True, text=True, timeout=30,
                                creationflags=NO_WINDOW_FLAGS)
        assert result.returncode == 0, (preset, result.stderr)


# --- מהממשק לשורת הפקודה ---

def test_web_options_become_cli_flags_only_when_valid_and_relevant():
    from entrypoints import web_app
    args = web_app._build_wave25_args({
        "grade_shadows": "0,0,0.05", "grade_midtones": "0,0,0", "grade_highlights": "oops",
        "curves_preset": "vintage", "curves_master": "0/0  0.5/0.6 1/1", "curves_red": "bad",
        "keep_audio": True, "audio_highpass": "80", "audio_eq_low": 0.01, "audio_eq_mid": "-3", "audio_eq_mid_freq": "2500",
        "audio_eq_high": 30, "audio_compressor": "voice", "audio_denoise": "strong", "audio_denoise_model": r"C:\m.rnnn",
    })
    assert args == ["--grade-shadows", "0,0,0.05", "--curves-preset", "vintage", "--curves-master", "0/0 0.5/0.6 1/1",
                    "--audio-highpass", "80", "--audio-eq-mid", "-3", "--audio-eq-high", "20", "--audio-eq-mid-freq", "2500",
                    "--audio-compressor", "voice", "--audio-denoise", "strong", "--audio-denoise-model", r"C:\m.rnnn"]
    # שמע כבוי - בלי דגלי שמע; ערכי ברירת מחדל - בלי דגלים בכלל
    assert web_app._build_wave25_args({"audio_compressor": "voice", "curves_preset": "none"}) == []
    assert web_app._build_wave25_args({"keep_audio": True, "audio_eq_mid": 2, "audio_eq_mid_freq": 1000}) == ["--audio-eq-mid", "2"]


def test_fields_are_validated_next_to_the_field():
    from utils.video.video_editor_validation import map_ffmpeg_error_to_field, validate_fields
    errors = validate_fields({"grade_shadows": "1,2", "curves_red": "0/0 0.9/0.1 0.5/0.5", "curves_master": "0/0 0.5/0.6 1/1",
                              "audio_denoise_model": r"C:\definitely\missing.rnnn"})
    assert set(errors) == {"grade_shadows", "curves_red", "audio_denoise_model"}
    assert map_ffmpeg_error_to_field("[Parsed_curves_1] Invalid key", {}) == "curves_master"
    assert map_ffmpeg_error_to_field("arnndn: failed to load model", {}) == "audio_denoise_model"
    assert map_ffmpeg_error_to_field("[Parsed_acompressor_3] error", {}) == "audio_compressor"


def test_every_new_field_is_registered_everywhere():
    from utils.video import editor_model, video_editor_profiles
    from utils.video.video_editor_field_help import field_help_as_json_dict
    from utils.video.video_editor_field_help_en import FIELD_HELP_EN
    from entrypoints.web import frontend_assembly as fa
    page = fa.assemble_inline_page()
    help_he = field_help_as_json_dict()
    for field in WAVE25_FIELDS:
        assert field in video_editor_profiles.PROFILE_FIELDS, field
        assert editor_model.FIELD_AREAS[field] == ("look" if field.startswith(("grade", "curves")) else "sound"), field
        assert field in help_he and field in FIELD_HELP_EN, field
        assert f"{field}: {{id: \"ve" in page, field  # רשום ב-VE_WAVE25_FIELDS (70-editor-grade.js)
    help_text = subprocess.run([sys.executable, SCRIPT, "--help"], cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8",
                               timeout=60, creationflags=NO_WINDOW_FLAGS).stdout
    for flag in ("--grade-shadows", "--curves-preset", "--curves-master", "--audio-highpass", "--audio-eq-mid-freq",
                 "--audio-compressor", "--audio-denoise", "--audio-denoise-model"):
        assert flag in help_text, flag


# --- ריצה אמיתית ---

@needs_ffmpeg
@pytest.mark.skipif(not os.path.exists(get_ffprobe_exe()) and not os.path.isabs(get_ffprobe_exe()), reason="ffprobe לא זמין")
def test_a_real_render_with_grade_curves_and_audio_processing(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source = input_dir / "wave25_grade_clip.mp4"
    made = subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
                           "-f", "lavfi", "-i", "sine=frequency=500:duration=2", "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
                           "-pix_fmt", "yuv420p", str(source)], capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert made.returncode == 0, made.stderr
    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "wave25_grade_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--codec", "h264", "--keep-audio", "--loudnorm",
             "--grade-shadows", "0,0,0.08", "--grade-highlights", "0.06,0.02,0", "--curves-preset", "medium_contrast",
             "--curves-master", "0/0 0.3/0.25 0.7/0.78 1/1", "--audio-highpass", "80", "--audio-eq-low", "3",
             "--audio-eq-mid", "-2", "--audio-eq-mid-freq", "2500", "--audio-compressor", "voice", "--audio-denoise", "medium"],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=180, creationflags=NO_WINDOW_FLAGS,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path), result.stdout
        probe = subprocess.run([get_ffprobe_exe(), "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", output_path],
                               capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
        assert sorted(probe.stdout.split()) == ["audio", "video"]
    finally:
        remove_video_editor_output(output_path)
