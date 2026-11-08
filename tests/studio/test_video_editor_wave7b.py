# tests/studio/test_video_editor_wave7b.py
#
# גל 7ב של 102-ההצעות - לוגיקה טהורה: שכבות מתוזמנות וטקסט מונפש/טיימר/חותמת-זמן
# (79, 80, 89), סרגל התקדמות ומסגרת (82, 88), watermark נודד/Ken Burns/וינייטה
# (87, 88), עיבוד-אחרי: bumper/loop/boomerang/פרקים/GIF/WebP/אודיו (81, 89),
# וזיהוי הייליטס (85).
import os
import subprocess


import pytest

from tests.media_support import needs_ffmpeg
from utils.video import highlight_detect as hd
from utils.video import video_editor_layers as vel
from utils.video import video_editor_post as vep_post


# --- sanitize_layers ---

def test_sanitize_layers_defaults_and_drops_invalid(tmp_path):
    image = tmp_path / "logo.png"
    image.write_bytes(b"png")
    layers = vel.sanitize_layers([
        {"type": "text", "text": "שלום", "start": 1, "end": 4, "animation": "fade", "color": "ff0000"},
        {"type": "text", "text": "   "},                         # טקסט ריק - מושמט
        {"type": "image", "path": str(tmp_path / "missing.png")},  # תמונה חסרה - מושמטת
        {"type": "image", "path": str(image), "scale": 5, "position": "top-left"},
        {"type": "timer", "timer_mode": "weird", "start": 0},
        {"type": "sticker"},                                     # סוג לא מוכר
        "not a dict",
        {"type": "text", "text": "x", "start": 5, "end": 2, "position": "nowhere", "font": "Bad;Font", "font_size": 9999},
    ])
    assert [layer["type"] for layer in layers] == ["text", "image", "timer", "text"]
    text, image_layer, timer, weird = layers
    assert text["color"] == "#FF0000" and text["animation"] == "fade" and (text["start"], text["end"]) == (1.0, 4.0)
    assert image_layer["scale"] == 1.0 and image_layer["position"] == "top-left"
    assert timer["timer_mode"] == "countdown"
    assert weird["end"] is None and weird["position"] == "bottom-center" and weird["font"] == "Arial" and weird["font_size"] == 300


def test_sanitize_layers_accepts_json_text_and_caps_count():
    assert vel.sanitize_layers('[{"type": "text", "text": "a"}]')[0]["text"] == "a"
    assert vel.sanitize_layers("not json") == []
    assert vel.sanitize_layers(None) == []
    many = [{"type": "text", "text": str(i)} for i in range(50)]
    assert len(vel.sanitize_layers(many)) == vel.MAX_LAYERS


# --- טקסט: מיקום / הנפשה / טיימר / חותמת-זמן ---

def _text(**overrides):
    base = {"type": "text", "text": "Hello", "start": 2.0, "end": 6.0, "position": "bottom-center", "opacity": 1.0,
            "font": "Arial", "font_size": 40, "color": "#FFFFFF", "box": False, "animation": "none"}
    base.update(overrides)
    return base


def test_text_layer_filter_has_enable_window_and_position():
    [f] = vel.build_text_layer_filters(_text(), ["C:\\tmp\\layer_0_0.txt"])
    assert f.startswith("drawtext=textfile='C\\:/tmp/layer_0_0.txt'")
    assert "enable='between(t,2,6)'" in f and "expansion=none" in f
    assert "x='(w-text_w)/2'" in f and "y='h-text_h-h*0.04'" in f
    [open_ended] = vel.build_text_layer_filters(_text(end=None, position="top-right", box=True), ["a.txt"])
    assert "enable='gte(t,2)'" in open_ended and "x='w-text_w-h*0.04'" in open_ended and "box=1" in open_ended


def test_fade_and_slide_animation_expressions():
    [fade] = vel.build_text_layer_filters(_text(animation="fade"), ["a.txt"])
    assert "alpha='if(lt(t,2.5),(t-2)/0.5,if(gt(t,5.5),(6-t)/0.5,1))'" in fade
    [slide] = vel.build_text_layer_filters(_text(animation="slide"), ["a.txt"])
    assert "x='if(lt(t,2.5),-text_w+(((w-text_w)/2)+text_w)*(t-2)/0.5,(w-text_w)/2)'" in slide
    [faded_half] = vel.build_text_layer_filters(_text(animation="fade", opacity=0.5, end=None), ["a.txt"])
    assert "alpha='0.5*if(lt(t,2.5),(t-2)/0.5,1)'" in faded_half


def test_typewriter_reveals_prefixes_in_consecutive_windows(tmp_path):
    layer = _text(text="abcd", animation="typewriter")
    contents = vel.layer_text_contents(layer, None)
    assert contents == ["a", "ab", "abc", "abcd"]
    files = vel.write_layer_text_files([layer], str(tmp_path), None)[0]
    assert [open(p, encoding="utf-8").read() for p in files] == contents
    filters = vel.build_text_layer_filters(layer, files)
    assert len(filters) == 4
    assert "enable='between(t,2,2.125)'" in filters[0]
    assert "enable='between(t,2.375,6)'" in filters[-1]  # הטקסט המלא נשאר עד סוף השכבה


def test_typewriter_long_text_is_capped_in_steps():
    contents = vel.layer_text_contents(_text(text="x" * 300, animation="typewriter"), None)
    assert len(contents) <= vel.TYPEWRITER_MAX_STEPS + 1 and contents[-1] == "x" * 300


def test_timer_and_timestamp_expansions():
    countdown = vel.timer_expansion({"start": 5.0, "end": 65.0, "timer_mode": "countdown", "timer_seconds": None}, None)
    assert countdown == "%{eif:floor(max(0,65-t)/60):d:2}:%{eif:mod(floor(max(0,65-t)),60):d:2}"
    explicit = vel.timer_expansion({"start": 0.0, "end": None, "timer_mode": "countdown", "timer_seconds": 10}, 90)
    assert "max(0,10-t)" in explicit
    until_end = vel.timer_expansion({"start": 30.0, "end": None, "timer_mode": "countdown", "timer_seconds": None}, 90.0)
    assert "max(0,90-t)" in until_end
    elapsed = vel.timer_expansion({"start": 3.0, "end": None, "timer_mode": "elapsed"}, None)
    assert "max(0,t-3)" in elapsed
    assert vel.timestamp_expansion({"epoch": 1727258400.7}) == "%{pts:localtime:1727258400:%Y-%m-%d %H\\:%M\\:%S}"
    [timer_filter] = vel.build_text_layer_filters(_text(type="timer"), ["t.txt"])
    assert "expansion=normal" in timer_filter


# --- הרכבת שכבות + סרגל התקדמות + מסגרת ---

def test_build_layer_parts_chains_text_and_overlays_images():
    layers = [
        _text(),
        {"type": "image", "path": "C:/a.png", "scale": 0.25, "opacity": 0.5, "position": "top-left", "start": 0.0, "end": 3.0},
        _text(text="top", position="top-center"),
    ]
    parts, out = vel.build_layer_parts("outv", layers, {0: ["t0.txt"], 2: ["t2.txt"]}, {1: 3}, 1080, "30", 10.0)
    assert parts[0].startswith("[outv]drawtext=") and parts[0].endswith("[__lay1]")
    assert parts[1] == "[3:v]format=rgba,colorchannelmixer=aa=0.50,scale=270:-2[__img2]"
    assert parts[2] == "[__lay1][__img2]overlay=x='H*0.04':y='H*0.04':enable='between(t,0,3)'[__lay2]"
    assert parts[3].startswith("[__lay2]drawtext=") and parts[3].endswith(f"[{out}]")


def test_build_layer_parts_progress_bar_and_frame():
    parts, out = vel.build_layer_parts("outv", [], {}, {}, 1080, "30", 12.5,
                                       progress_bar={"color": "#00FF00", "height": 10, "position": "top"},
                                       frame_border=("#FFFFFF", 12))
    assert parts[0] == "[outv]drawbox=x=0:y=0:w=iw:h=ih:color=0xFFFFFF:t=12[__lay1]"
    assert parts[1] == "color=c=0x00FF00:s=1080x10:r=30[__pb2]"
    assert parts[2] == f"[__lay1][__pb2]overlay=x='-w+W*t/12.5':y=0:shortest=1[{out}]"
    assert vel.build_layer_parts("outv", [], {}, {}, 1080, "30", None, progress_bar={"height": 8}) == ([], "outv")


# --- מסגרת עם פינות מעוגלות (--frame-radius) ---

def test_build_layer_parts_rounded_frame_overlays_a_one_frame_alpha_ring():
    parts, out = vel.build_layer_parts("outv", [], {}, {}, 1080, "30", None, frame_border=("#FF8C00", 24),
                                       output_height=1920, frame_radius=60)
    source, overlay = parts
    assert source.startswith("color=c=black:s=1080x1920:r=30,format=gbrap,geq=r=255:g=140:b=0:a='") and source.endswith("[__fr1]")
    assert "-60+0.5" in source  # הרדיוס בנוסחת המרחק
    assert ",trim=end_frame=1,loop=loop=-1:size=1:start=0,setpts=N/30/TB[" in source  # geq רץ על פריים אחד, לא על כל פריים
    assert overlay == f"[outv][__fr1]overlay=x=0:y=0:shortest=1[{out}]"
    assert not any("drawbox" in part for part in parts)


def test_build_layer_parts_rounded_frame_sits_above_the_text_layers():
    text = {"type": "text", "text": "hi", "start": 0.0, "end": None, "position": "top-center", "font": "Arial", "font_size": 24,
            "color": "#FFFFFF", "animation": "none", "opacity": 1.0}
    parts, out = vel.build_layer_parts("outv", [text], {0: ["t0.txt"]}, {}, 640, "30", None, frame_border=("#112233", 10),
                                       output_height=360, frame_radius=20)
    assert parts[0].startswith("[outv]drawtext=") and parts[0].endswith("[__lay1]")
    assert parts[1].endswith("[__fr2]")
    assert parts[2] == f"[__lay1][__fr2]overlay=x=0:y=0:shortest=1[{out}]"


@pytest.mark.parametrize("kwargs", [
    {"frame_radius": 0},                      # ברירת המחדל: פינות ישרות כמו תמיד
    {"frame_radius": 30, "output_height": None},   # בלי גודל פלט ידוע אי אפשר לחשב את הטבעת
    {"frame_radius": 30, "output_height": 1920, "frame_border": ("#FFFFFF", 600)},  # העובי אוכל את כל הפריים
    {"frame_radius": 30, "output_height": 1920, "frame_border": ("red", 12)},       # צבע לא תקין
])
def test_build_layer_parts_frame_falls_back_to_the_straight_drawbox(kwargs):
    kwargs = {"frame_border": ("#FFFFFF", 12), "output_height": 1920, **kwargs}
    parts, _ = vel.build_layer_parts("outv", [], {}, {}, 1080, "30", None, **kwargs)
    assert len(parts) == 1 and parts[0].startswith("[outv]drawbox=x=0:y=0:w=iw:h=ih:color=0x")


def test_rounded_frame_source_clamps_the_radius_to_the_window_and_handles_fractional_fps():
    source = vel.build_rounded_frame_source("#FFFFFF", 10, 5000, 200, 100, "30000/1001")
    assert "-40+0.5" in source  # חצי הצד הקצר של החלון הפנימי (180x80)
    assert source.startswith("color=c=black:s=200x100:r=30000/1001,") and source.endswith(",setpts=N/29.97/TB")
    assert vel.build_rounded_frame_source("#FFFFFF", 10, 0, 200, 100, "30") is None
    assert vel.build_rounded_frame_source("#FFFFFF", 0, 20, 200, 100, "30") is None


@needs_ffmpeg
def test_rounded_frame_renders_square_outside_and_round_inside_with_real_ffmpeg(tmp_path):
    from PIL import Image
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    frame_color, video_color = (255, 140, 0), (0, 0, 255)
    source = vel.build_rounded_frame_source("#FF8C00", 20, 50, 320, 240, "10")
    out = tmp_path / "frame.png"
    result = subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "color=c=0x0000FF:s=320x240:r=10:d=1",
                             "-filter_complex", f"{source}[ring];[0:v][ring]overlay=x=0:y=0:shortest=1[o]", "-map", "[o]",
                             "-frames:v", "1", str(out)],
                            capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS, cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr[-800:]
    picture = Image.open(out).convert("RGB")

    def close(point, expected):
        return all(abs(a - b) <= 12 for a, b in zip(picture.getpixel(point), expected))
    assert close((0, 0), frame_color)       # הפינה החיצונית נשארת ישרה, בצבע המסגרת
    assert close((10, 120), frame_color)    # רצועת המסגרת בצד
    assert close((23, 23), frame_color)     # בתוך המסגרת אבל מחוץ לפינה המעוגלת של חלון הווידאו
    assert close((22, 120), video_color)    # הקצה הישר של החלון - כבר וידאו
    assert close((70, 70), video_color)     # מרכז הקשת - וידאו
    assert close((160, 120), video_color)


def test_image_layer_without_input_is_skipped():
    assert vel.build_layer_parts("outv", [{"type": "image", "start": 0, "end": None, "position": "center"}], {}, {}, 1920, 30, 5) == ([], "outv")


# --- watermark נודד / Ken Burns / וינייטה ---

def test_cycling_overlay_expression():
    x, y = vel.build_cycling_overlay_xy([(10, 20), (500, 20), (500, 900), (10, 900)], 5)
    assert x == "if(lt(mod(t,20),5),10,if(lt(mod(t,20),10),500,if(lt(mod(t,20),15),500,10)))"
    assert y.startswith("if(lt(mod(t,20),5),20,")
    assert vel.build_cycling_overlay_xy([(7, 8)], 5) == ("7", "8")
    assert vel.build_cycling_overlay_xy([(1, 2), (3, 4)], 0) == ("1", "2")


def test_vignette_and_ken_burns_filters():
    assert vel.build_vignette_filter("none") == "" and vel.build_vignette_filter(None) == ""
    assert vel.build_vignette_filter("strong") == "vignette=angle=PI/4"
    with pytest.raises(ValueError):
        vel.build_vignette_filter("extreme")
    kb = vel.build_ken_burns_filter(0.1, 1080, 1920, "30", 10.0)
    assert kb == "zoompan=z='1+0.1*on/300':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30"
    assert "on/300" in vel.build_ken_burns_filter(0.1, 1080, 1920, "30000/1001", 10.01)
    assert vel.build_ken_burns_filter(0, 1080, 1920, "30", 10) == ""


# --- עיבוד-אחרי ---

def test_post_temp_path_stays_next_to_output_with_same_extension():
    path = vep_post.post_temp_path("E:\\out\\clip.mkv", "bumpers")
    assert os.path.dirname(path) == os.path.abspath("E:\\out") and path.endswith(".clip.bumpers.mkv")


def test_bumper_concat_command_pads_and_fills_missing_audio():
    cmd = vep_post.build_bumper_concat_command(
        "ffmpeg", [("intro.mp4", 2.0, False), ("main.mp4", 10.0, True), ("outro.mp4", 3.5, True)],
        1080, 1920, "30", True, ["-c:v", "libx264"], "out.mp4",
    )
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert cmd.count("-i") == 3
    assert "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920" in graph
    assert "anullsrc=r=48000:cl=stereo,atrim=duration=2.000" in graph
    assert "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]" in graph
    silent = vep_post.build_bumper_concat_command("ffmpeg", [("a.mp4", 1, True), ("b.mp4", 1, True)], 1920, 1080, "30", False, [], "o.mp4")
    assert "concat=n=2:v=1:a=0[v]" in silent[silent.index("-filter_complex") + 1] and "[a]" not in silent


def test_boomerang_and_loop_commands():
    cmd = vep_post.build_boomerang_command("ffmpeg", "in.mp4", True, ["-c:v", "libx264"], "out.mp4")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "reverse" in graph and "areverse" in graph and cmd[-1] == "out.mp4"
    assert "areverse" not in vep_post.build_boomerang_command("ffmpeg", "in.mp4", False, [], "o.mp4")[4]
    loop = vep_post.build_loop_command("ffmpeg", "in.mp4", 3, "out.mp4")
    assert loop[loop.index("-stream_loop") + 1] == "2" and "copy" in loop
    assert vep_post.build_loop_command("ffmpeg", "in.mp4", 99, "o.mp4")[3] == str(vep_post.MAX_LOOP_COUNT - 1)


def test_parse_chapters_and_ffmetadata():
    chapters = vep_post.parse_chapters("0:00 פתיחה\n1:30 - קרב בוס\nnot a chapter\n1:02:03.5 סוף|0:45: אמצע\n0:00 כפול")
    assert chapters == [(0.0, "פתיחה"), (45.0, "אמצע"), (90.0, "קרב בוס"), (3723.5, "סוף")]
    meta = vep_post.build_ffmetadata("כותרת = טובה", "הערה; עם #", chapters[:3], 120.0, offset=5.0)
    assert meta.startswith(";FFMETADATA1\ntitle=כותרת \\= טובה\ncomment=הערה\\; עם \\#")
    assert "START=5000\nEND=50000\ntitle=פתיחה" in meta
    assert "START=95000\nEND=120000\ntitle=קרב בוס" in meta
    assert "סוף" not in vep_post.build_ffmetadata("", "", chapters, 120.0)  # פרק אחרי סוף הסרטון מושמט


def test_export_commands_and_paths():
    gif = vep_post.build_gif_command("ffmpeg", "in.mp4", "out.gif", 320, 10)
    assert "palettegen" in gif[gif.index("-filter_complex") + 1] and "fps=10,scale=320:-2" in gif[gif.index("-filter_complex") + 1]
    webp = vep_post.build_webp_command("ffmpeg", "in.mp4", "out.webp")
    assert "libwebp" in webp and "-an" in webp
    assert vep_post.build_audio_export_command("ffmpeg", "in.mp4", "a.mp3", "mp3")[4:7] == ["-vn", "-c:a", "libmp3lame"]
    with pytest.raises(ValueError):
        vep_post.build_audio_export_command("ffmpeg", "in.mp4", "a.ogg", "ogg")
    paths = vep_post.extra_export_paths("C:/out/clip.mp4", "both", "m4a")
    assert paths == {"gif": "C:/out/clip.gif", "webp": "C:/out/clip.webp", "m4a": "C:/out/clip.m4a"}
    assert vep_post.extra_export_paths("C:/out/clip.mp4", None, "none") == {}


# --- זיהוי הייליטס ---

def test_highlight_pipeline_on_synthetic_levels():
    levels = [-40.0] * 600
    levels[100] = -5.0   # שיא ב-10s
    levels[105] = -4.0   # צמוד מדי (מרווח מינימלי) - לא שיא נוסף
    levels[450] = -6.0   # שיא ב-45s
    peaks = hd.find_audio_peaks(levels, -30.0, threshold_offset_db=18.0, min_gap_seconds=15.0)
    assert peaks == [10.0, 45.0]
    keep = hd.peaks_to_keep_windows(peaks, 60.0, before=5.0, after=3.0)
    assert keep == [(5.0, 13.0), (40.0, 48.0)]
    assert hd.keep_windows_to_remove_ranges(keep, 60.0) == [[0.0, 5.0], [13.0, 40.0], [48.0, 60.0]]
    assert hd.peaks_to_keep_windows([10.0, 12.0], 60.0, before=5.0, after=5.0) == [(5.0, 17.0)]


def test_chunk_levels_dbfs_from_samples():
    np = pytest.importorskip("numpy")
    quiet = np.full(800, 0.01)
    loud = np.concatenate([np.full(400, 0.01), np.full(400, 0.9)])
    levels, average = hd.chunk_levels_dbfs(np.concatenate([quiet, loud]), sample_rate=8000, chunk_ms=100)
    assert len(levels) == 2
    assert levels[0] == pytest.approx(-40.0, abs=0.1) and levels[1] == pytest.approx(20 * np.log10(0.9), abs=0.1)
    assert -40.0 < average < levels[1]
    assert hd.chunk_levels_dbfs([], 8000) == ([], -120.0)


def test_estimate_accounts_for_post_steps():
    from utils.video.video_editor_estimate import estimate_output_seconds
    assert estimate_output_seconds(20, {"_bumper_seconds": 5})[0] == pytest.approx(25)
    assert estimate_output_seconds(20, {"boomerang": True, "loop_count": 3})[0] == pytest.approx(120)
    assert estimate_output_seconds(90, {"boomerang": True})[0] == pytest.approx(90)  # מעל 60s - הסקריפט מדלג
    assert estimate_output_seconds(60, {"target_seconds": 10, "loop_count": 2})[0] == pytest.approx(20)
