# tests/video_editor_golden.py
#
# גל 48: "פקודות זהב" לעורך-העל - מריץ את process_video של my_scripts/video/video_editor.py בתוך התהליך, על
# קובץ מדומה, עם צירופי דגלים רבים, ואוסף את פקודות ה-ffmpeg שהוא בונה (בלי להריץ ffmpeg: הבדיקה, החיתוך,
# זיהוי השקט, הייצוב והרינדור עצמו מוחלפים). פקודה זהה = סרטון זהה, אז זה מוכיח ששינוי פנימי (כמו מעבר
# לאובייקט הגדרות) לא שינה שום פלט - בלי לרנדר כלום. הקובץ tests/data/video_editor_golden_commands.json נוצר
# מהקוד לפני השינוי:  uv run python -m tests.video_editor_golden --write

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "video_editor.py")
GOLDEN = os.path.join(BASE_DIR, "tests", "data", "video_editor_golden_commands.json")

SDR = {"duration": 30.0, "fps": "30/1", "width": 1920, "height": 1080, "has_audio": True,
       "color_transfer": "bt709", "color_primaries": "bt709", "color_space": "bt709"}
HDR = dict(SDR, color_transfer="smpte2084", color_primaries="bt2020", color_space="bt2020nc")
VERTICAL_SOURCE = dict(SDR, width=1080, height=1920)

# (שם, דגלים, אפשרויות) - קבצים שהדגלים צריכים (לוגו, LUT, PiP...) נוצרים בתיקייה הזמנית: {tmp}
SCENARIOS: List[Dict[str, Any]] = [
    {"name": "default", "flags": []},
    {"name": "vertical", "flags": ["--vertical"]},
    {"name": "hevc_nvenc", "flags": ["--codec", "hevc", "--nvenc-cq", "24", "--nvenc-preset", "p6"]},
    {"name": "hevc_hwaccel", "flags": ["--codec", "hevc", "--hwaccel"]},
    {"name": "hwaccel_decode", "flags": ["--hwaccel-decode"]},
    {"name": "hdr_passthrough", "flags": ["--codec", "hevc"], "probe": HDR},
    {"name": "hdr_tonemap", "flags": [], "probe": HDR},
    {"name": "watermark", "flags": ["--watermark_path", "{tmp}/logo.png", "--watermark_position", "top-left", "--watermark_opacity", "0.6", "--watermark_scale", "0.2"]},
    {"name": "watermark_vertical_corner", "flags": ["--vertical", "--watermark_path", "{tmp}/logo.png", "--watermark-position-vertical", "bottom-left"]},
    {"name": "watermark_drag", "flags": ["--watermark_path", "{tmp}/logo.png", "--watermark_x", "0.3", "--watermark_y", "0.7"]},
    {"name": "watermark_move", "flags": ["--watermark_path", "{tmp}/logo.png", "--watermark-move-seconds", "5"]},
    {"name": "trim", "flags": ["--trim-start", "2.5", "--trim-duration", "10"]},
    {"name": "trim_silence", "flags": ["--trim-silence"]},
    {"name": "remove_ranges", "flags": ["--remove-ranges", "3-5,10-12"]},
    {"name": "mid_silence", "flags": ["--remove-mid-silence", "--keep-audio"], "silence": [[4.0, 6.0]]},
    {"name": "speed", "flags": ["--speed", "1.5", "--keep-audio"]},
    {"name": "timelapse", "flags": ["--target-seconds", "10"]},
    {"name": "preserve_resolution", "flags": ["--preserve-resolution"], "probe": dict(SDR, width=2560, height=1440)},
    {"name": "aspect_pad", "flags": ["--aspect", "1:1", "--fit", "pad", "--pad-color", "#112233"]},
    {"name": "custom_size_crop", "flags": ["--aspect", "custom", "--custom-width", "1280", "--custom-height", "1024", "--fit", "crop"]},
    {"name": "dual_output", "flags": ["--dual-output"], "variant": 1},
    {"name": "smart_crop", "flags": ["--vertical", "--smart-crop"], "crop": 0.25},
    {"name": "rotate_flip", "flags": ["--rotate", "90", "--flip", "h"], "probe": VERTICAL_SOURCE},
    {"name": "resolution_scale_algo", "flags": ["--resolution", "720p", "--scale-algo", "lanczos"]},
    {"name": "deinterlace_eq", "flags": ["--deinterlace", "--eq-brightness", "0.1", "--eq-contrast", "1.2", "--eq-saturation", "1.3", "--eq-gamma", "0.9"]},
    {"name": "grade_curves", "flags": ["--grade-shadows", "0.1,0,-0.1", "--curves-preset", "vintage"]},
    {"name": "lut", "flags": ["--lut", "{tmp}/look.cube", "--lut-intensity", "0.5", "--auto-levels"]},
    {"name": "denoise_sharpen_stabilize", "flags": ["--denoise", "--denoise-level", "strong", "--sharpen", "--stabilize"], "stabilize": True},
    {"name": "smooth_fps", "flags": ["--smooth-fps", "--fps", "60"]},
    {"name": "fps_fraction", "flags": ["--fps", "30000/1001"]},
    {"name": "chromakey", "flags": ["--chromakey", "--chromakey-color", "0x00FF00", "--chromakey-bg-color", "black"]},
    {"name": "blur_background", "flags": ["--vertical", "--blur-background"]},
    {"name": "text_fade", "flags": ["--text", "שלום: עולם", "--text-position", "top", "--fade-in-seconds", "1", "--fade-out-seconds", "2"]},
    {"name": "layers", "flags": ["--layers-json", "{tmp}/layers.json"]},
    {"name": "progress_frame_vignette_kenburns", "flags": ["--progress-bar", "--frame-thickness", "8", "--vignette", "medium", "--ken-burns", "1.1"]},
    {"name": "frame_rounded", "flags": ["--frame-thickness", "12", "--frame-color", "#FF8C00", "--frame-radius", "40"]},
    {"name": "pip_audio", "flags": ["--pip", "{tmp}/pip.mp4", "--pip-position", "top-right", "--pip-scale", "0.3", "--pip-audio", "--pip-duck", "--keep-audio"]},
    {"name": "replace_audio_loudnorm", "flags": ["--replace-audio", "{tmp}/music.mp3", "--loudnorm", "--loudnorm-target", "-16"]},
    {"name": "audio_fx", "flags": ["--keep-audio", "--audio-highpass", "80", "--audio-eq-low", "2", "--audio-compressor", "voice", "--noise-gate", "--audio-track", "1"]},
    {"name": "remove_logo_region", "flags": ["--remove-watermark-region", "0.1,0.1,0.2,0.1"]},
    {"name": "remove_logo_corner", "flags": ["--remove_watermark_position", "bottom-right"]},
    {"name": "target_size_h264", "flags": ["--target-size-mb", "20", "--keep-audio"]},
    {"name": "target_size_hevc", "flags": ["--codec", "hevc", "--target-size-mb", "20"]},
    {"name": "crf_effort_mkv", "flags": ["--crf", "20", "--effort", "low", "--container", "mkv", "--no-suffix"]},
    {"name": "output_template", "flags": ["--output-template", "{name}_{codec}_cut"]},
    {"name": "validate_only", "flags": ["--validate-only", "--watermark_path", "{tmp}/logo.png"]},
    {"name": "preview_frame_captions", "flags": ["--preview-frame", "5", "--preview-frame-out", "{tmp}/frame.png", "--captions", "--caption-color", "yellow"]},
    {"name": "clip_overrides", "flags": ["--watermark_path", "{tmp}/logo.png"],
     "overrides": {"trim_start": 1.0, "trim_duration": 8.0, "watermark_x": 0.2, "watermark_y": 0.3,
                   "layers": [{"type": "text", "text": "כותרת", "start": 0, "end": 3}]}},
    {"name": "clip_ranges", "flags": [], "overrides": {"remove_ranges": [[1.0, 2.0], [5.0, 6.0]]}},
]

_LAYERS = [{"type": "text", "text": "שכבה", "position": "bottom", "start": 1, "end": 4, "animation": "fade"},
           {"type": "timer", "mode": "countdown", "position": "top-right", "start": 0},
           {"type": "image", "path": "{tmp}/logo.png", "position": "top-left", "scale": 0.1, "start": 2, "end": 6}]


def _prepare_files(tmp: str) -> None:
    from PIL import Image
    Image.new("RGBA", (64, 32), (255, 0, 0, 255)).save(os.path.join(tmp, "logo.png"))
    with open(os.path.join(tmp, "look.cube"), "w", encoding="utf-8") as f:
        f.write("LUT_3D_SIZE 2\n" + "0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n")
    for name in ("pip.mp4", "music.mp3", "clip.mp4"):
        with open(os.path.join(tmp, name), "wb") as f:
            f.write(b"x")
    with open(os.path.join(tmp, "layers.json"), "w", encoding="utf-8") as f:
        json.dump([{k: (v.replace("{tmp}", tmp) if isinstance(v, str) else v) for k, v in layer.items()} for layer in _LAYERS], f, ensure_ascii=False)


def _load(tmp: str, flags: List[str], index: int) -> Any:
    argv = ["video_editor.py", "--input_dir", tmp] + [f.replace("{tmp}", tmp) for f in flags]
    saved = sys.argv
    sys.argv = argv
    try:
        spec = importlib.util.spec_from_file_location(f"ve_golden_{index}", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.argv = saved
    return module


def _normalize(value: str, tmp: str, ffmpeg: str) -> str:
    temp = tempfile.gettempdir()
    for path, label in ((tmp, "<TMP>"), (temp, "<TEMP>")):
        for variant in {path, os.path.realpath(path)}:
            forward = variant.replace("\\", "/")
            for form in (variant, forward, forward.replace(":", "\\:"), forward.replace(":", "\\\\:")):
                value = value.replace(form, label)
    value = value.replace(ffmpeg, "<FFMPEG>")
    # שמות זמניים אקראיים (tempfile: 8 תווים) - "video_editor_text_u1qkwdlg.txt" -> "video_editor_text_*.txt"
    return re.sub(r"<TEMP>([\\/]+)([A-Za-z_]+?_)[a-z0-9_]{8}(?=[.'/\\]|$)", r"<TEMP>\1\2*", value)


def run_scenario(scenario: Dict[str, Any], tmp: str, index: int = 0, stderr: str = "", loaded: Any = None) -> List[List[str]]:
    """stderr: מה שהקידוד "מדפיס" (on_stderr - למשל הסיכום של loudnorm); loaded: רשימה שמקבלת את המודול (ה-run manifest)."""
    _prepare_files(tmp)
    module = _load(tmp, scenario["flags"], index)
    if loaded is not None:
        loaded.append(module)
    captured: List[List[str]] = []
    probe = dict(scenario.get("probe") or SDR)

    def fake_probe(path):
        return dict(probe) if path.endswith("source.mp4") else dict(SDR, duration=12.0)

    def fake_run(cmd, *args, **kwargs):
        captured.append(list(cmd))
        out = cmd[-1]
        if isinstance(out, str) and ".partial" in out:
            open(out, "wb").close()
        if kwargs.get("on_stderr"):
            kwargs["on_stderr"](stderr)
        return True

    class _Result:
        returncode, stderr, stdout = 0, "", ""

    module.probe_video = fake_probe
    module.run_ffmpeg_with_progress = fake_run
    module.run_ffmpeg_with_progress_and_nvenc_retry = fake_run
    module.detect_silence_trim_bounds = lambda path, duration: (1.5, 20.0)
    module.detect_all_silence_intervals = lambda path, duration: [tuple(r) for r in scenario.get("silence", [])]
    module.resolve_smart_crop_offset = lambda path: scenario.get("crop")
    module.detect_stabilization_transform = lambda path: os.path.join(tmp, "transforms.trf") if scenario.get("stabilize") else None
    module.estimate_required_bytes = lambda path: 1
    module.has_enough_disk_space = lambda folder, needed: True
    module.available_cuda_filters = lambda: {"scale_cuda", "transpose_cuda", "bwdif_cuda"}
    module._compute_current_signature = lambda path: None
    module.maybe_generate_thumbnail = lambda *a, **k: None
    module.maybe_burn_captions = lambda *a, **k: None
    module.maybe_post_process = lambda *a, **k: None
    module.maybe_notify_per_file = lambda *a, **k: None
    module.render_preview_frame = lambda video_path, filename, cmd_prefix, *a, **k: captured.append(list(cmd_prefix))
    module._reserve_next_number = lambda: 7
    module._mark_number_used_successfully = lambda number: None
    out_dir = os.path.join(tmp, "out")
    os.makedirs(out_dir, exist_ok=True)
    source = os.path.join(tmp, "source.mp4")
    with open(source, "wb") as f:
        f.write(b"x")
    results: Dict[str, Any] = {"files_created": 0, "errors": 0, "skipped": 0, "valid": 0, "invalid": 0, "cancelled": 0, "files": []}
    variant = module.VARIANTS[scenario.get("variant", 0)]
    # module.subprocess הוא המודול subprocess המשותף לכל התהליך - מוחלף רק לזמן הריצה ומוחזר תמיד,
    # אחרת כל טסט שרץ אחר כך באותו worker מקבל "הצלחה" ריקה במקום להריץ באמת
    real_cpu_count, real_subprocess_run = os.cpu_count, subprocess.run
    os.cpu_count = lambda: 8   # --effort low/medium מחשב threads לפי הליבות - קבוע, כדי שהפקודה תהיה זהה בכל מחשב
    subprocess.run = lambda cmd, *a, **k: (captured.append(list(cmd)), _Result())[1]
    try:
        module.process_video(source, results, out_dir, overrides=scenario.get("overrides"), variant=variant)
    finally:
        os.cpu_count, subprocess.run = real_cpu_count, real_subprocess_run
    return [[_normalize(str(part), tmp, module.FFMPEG_EXE) for part in cmd] for cmd in captured]


def run_all() -> Dict[str, List[List[str]]]:
    result = {}
    for index, scenario in enumerate(SCENARIOS):
        with tempfile.TemporaryDirectory(prefix="ve_golden_") as tmp:
            result[scenario["name"]] = run_scenario(scenario, tmp, index)
    return result


if __name__ == "__main__":
    commands = run_all()
    if "--write" in sys.argv:
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        with open(GOLDEN, "w", encoding="utf-8") as f:
            json.dump(commands, f, ensure_ascii=False, indent=1)
        print(f"wrote {len(commands)} scenarios to {GOLDEN}")
    else:
        print(json.dumps(commands, ensure_ascii=False, indent=1)[:4000])
