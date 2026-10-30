# tests/studio/test_broll_layers.py
#
# גל 26: שכבת וידאו (B-roll) - קליפ שני בטווח-זמן בתוך הפלט. בניית הקלט וה-filtergraph
# (מסך מלא / מותאם / חלון), הסוף בזמן הפלט, ערבוב השמע (mix/replace), בדיקת השדה,
# ורינדור אמיתי שבודק שהקליפ השני באמת מופיע בפריים ושהשמע נשאר.
import os
from tests import PROJECT_ROOT
import subprocess
import sys


import json

import pytest

from utils.video import video_editor_layers as vl
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.video.video_editor import build_edit_filter_complex

from tests.conftest import remove_video_editor_output

BASE_DIR = PROJECT_ROOT
from utils.shared.workspace_dir import WORKSPACE_DIR  # הזמני של הריצה (tests/conftest.py) - לא workspace/ של המשתמש
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "video_editor.py")
HORIZONTAL_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "studio", "horizontal")


def _ffmpeg_available():
    import shutil
    exe = get_ffmpeg_exe()
    return (os.path.isabs(exe) and os.path.exists(exe)) or bool(shutil.which(exe))


needs_ffmpeg = pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg לא זמין בסביבה הזו")


def _layer(**overrides):
    layer = {"type": "video", "path": "broll.mp4", "start": 1.5, "end": 3.5, "source_in": 1.0, "fit": "fill", "scale": 0.35,
             "position": "top-right", "opacity": 1.0, "audio": "mute", "volume": 1.0, "has_audio": True}
    layer.update(overrides)
    return layer


def test_video_layers_are_sanitized_with_defaults(tmp_path):
    clip = tmp_path / "b.mp4"
    clip.write_bytes(b"x")
    clean = vl.sanitize_layers([
        {"type": "video", "path": str(clip), "start": 2, "source_in": -5, "fit": "zoom", "audio": "loud", "scale": 9},
        {"type": "video", "path": str(tmp_path / "missing.mp4")},
        {"type": "video", "path": ""},
    ])
    assert len(clean) == 1
    layer = clean[0]
    assert (layer["fit"], layer["audio"], layer["source_in"], layer["scale"], layer["volume"]) == ("fill", "mute", 0.0, 1.0, 1.0)
    assert vl.sanitize_layers([{"type": "video", "path": str(tmp_path / "later.mp4")}], require_existing_images=False)[0]["type"] == "video"


def test_the_end_in_output_time_is_the_earliest_of_chosen_clip_and_output():
    assert vl.video_layer_end({"start": 2, "end": None, "source_in": 1}, 5.0, 60.0) == 6.0  # עד שהקליפ נגמר
    assert vl.video_layer_end({"start": 2, "end": 4, "source_in": 0}, 10.0, 60.0) == 4.0  # הסוף שנבחר
    assert vl.video_layer_end({"start": 2, "end": None, "source_in": 0}, 30.0, 10.0) == 10.0  # לא אחרי סוף הפלט
    assert vl.video_layer_end({"start": 12, "end": None, "source_in": 0}, 5.0, 10.0) is None  # מחוץ לפלט
    assert vl.video_layer_end({"start": 0, "end": None, "source_in": 9}, 5.0, 10.0) is None  # נקודת ההתחלה אחרי סוף הקליפ


def test_input_args_seek_fast_and_read_only_what_is_needed():
    assert vl.build_video_layer_input_args(_layer()) == ["-ss", "1", "-t", "2", "-i", "broll.mp4"]
    assert vl.build_video_layer_input_args(_layer(source_in=0)) == ["-t", "2", "-i", "broll.mp4"]


@pytest.mark.parametrize("fit, expect", [
    ("fill", "force_original_aspect_ratio=increase,crop=1280:720"),
    ("fit", "force_original_aspect_ratio=decrease,pad=1280:720"),
    ("pip", "scale=448:-2"),
])
def test_each_fit_scales_the_clip_and_overlays_it_only_in_its_range(fit, expect):
    parts, label = vl.build_layer_parts("outv", [_layer(fit=fit)], {}, {0: 3}, 1280, 30, 10.0, output_height=720)
    assert parts[0].startswith("[3:v]trim=duration=2,setpts=PTS-STARTPTS+1.5/TB") and expect in parts[0]
    assert "overlay=" in parts[1] and "eof_action=pass" in parts[1] and "between(t,1.5,3.5)" in parts[1]
    assert (("x='0'" in parts[1]) == (fit != "pip")) and label == "__lay1"


def test_a_layer_without_an_end_or_input_is_skipped():
    parts, label = vl.build_layer_parts("outv", [_layer(end=None)], {}, {0: 3}, 1280, 30, 10.0, output_height=720)
    assert parts == [] and label == "outv"


def test_broll_audio_mixes_over_the_main_and_replace_silences_it():
    layers = [_layer(audio="mix", volume=0.5), _layer(audio="replace", start=5, end=6), _layer(audio="mute"), _layer(audio="mix", has_audio=False)]
    sources = vl.build_broll_audio_sources(layers, {0: 2, 1: 3, 2: 4, 3: 5})
    assert [s["input"] for s in sources] == [2, 3]
    parts = vl.build_broll_audio_parts("__amain", sources)
    assert parts[0] == "[__amain]volume=0:enable='between(t,5,6)'[__amain_duck]"
    assert parts[1].startswith("[2:a]atrim=duration=2,asetpts=PTS-STARTPTS,adelay=1500:all=1,volume=0.5")
    assert parts[-1] == "[__amain_duck][__broll_a1][__broll_a2]amix=inputs=3:duration=first:dropout_transition=0:normalize=0[outa]"


def test_the_filter_complex_mixes_broll_audio_with_and_without_other_audio_filters():
    layers = [_layer(audio="replace")]
    sources = vl.build_broll_audio_sources(layers, {0: 1})
    graph, maps = build_edit_filter_complex("scale=640:360", 25, keep_audio=True, layers=layers, layer_image_inputs={0: 1},
                                            output_width=640, output_height=360, output_duration_seconds=6, broll_audio_sources=sources)
    assert "[0:a]anull[__amain]" in graph and maps[-2:] == ["-map", "[outa]"]
    graph, maps = build_edit_filter_complex("scale=640:360", 25, keep_audio=True, loudnorm=True, layers=layers, layer_image_inputs={0: 1},
                                            output_width=640, output_height=360, output_duration_seconds=6, broll_audio_sources=sources)
    assert "loudnorm=I=-14:LRA=11:TP=-1.5:print_format=json,aresample=48000[__amain]" in graph and graph.count("[outa]") == 1 and maps[-2:] == ["-map", "[outa]"]


def test_a_missing_broll_clip_is_flagged_next_to_the_layers_field(tmp_path):
    from utils.video.video_editor_validation import validate_fields
    errors = validate_fields({"layers": json.dumps([{"type": "video", "path": str(tmp_path / "nope.mp4")}])})
    assert "layers" in errors and "nope.mp4" in errors["layers"]
    assert "layers" not in validate_fields({"layers": [{"type": "text", "text": "hi"}]})


@needs_ffmpeg
def test_a_real_render_shows_the_broll_in_its_range_and_keeps_the_length(tmp_path):
    ff = get_ffmpeg_exe()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    main = input_dir / "wave26_broll_main.mp4"
    broll = tmp_path / "broll.mp4"
    for path, source, audio in ((main, "color=c=blue:s=320x180:r=25:d=4", "sine=f=300:d=4"), (broll, "color=c=red:s=240x180:r=30:d=3", "sine=f=900:d=3")):
        made = subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", source, "-f", "lavfi", "-i", audio, "-c:v", "libx264",
                               "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], capture_output=True, text=True, timeout=60,
                              creationflags=NO_WINDOW_FLAGS)
        assert made.returncode == 0, made.stderr
    layers_path = tmp_path / "layers.json"
    layers_path.write_text(json.dumps([{"type": "video", "path": str(broll), "start": 1, "end": 2.5, "source_in": 0.5,
                                        "fit": "fill", "audio": "replace"}]), encoding="utf-8")
    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "wave26_broll_main_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = subprocess.run([sys.executable, SCRIPT, "--input_dir", str(input_dir), "--codec", "h264", "--keep-audio",
                                 "--layers-json", str(layers_path)], cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8",
                                timeout=180, creationflags=NO_WINDOW_FLAGS)
        assert result.returncode == 0 and os.path.exists(output_path), result.stdout + result.stderr

        def pixel_at(seconds):
            frame = subprocess.run([ff, "-v", "error", "-ss", str(seconds), "-i", output_path, "-frames:v", "1", "-vf", "scale=1:1",
                                    "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
            return tuple(frame.stdout[:3])

        r, g, b = pixel_at(1.8)
        assert r > 150 and b < 90, f"בטווח ה-B-roll ציפינו לאדום, קיבלנו {(r, g, b)}"
        r, g, b = pixel_at(3.3)
        assert b > 150 and r < 90, f"אחרי ה-B-roll ציפינו לכחול של הראשי, קיבלנו {(r, g, b)}"
        probe = subprocess.run([get_ffprobe_exe(), "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", output_path],
                               capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
        info = json.loads(probe.stdout)
        assert sorted(s["codec_type"] for s in info["streams"]) == ["audio", "video"]
        assert abs(float(info["format"]["duration"]) - 4.0) < 0.3
    finally:
        remove_video_editor_output(output_path)
