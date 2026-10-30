# tests/infra/test_export_dir_scripts.py
#
# 23.10.2026: הסקריפטים כותבים את התוצרים הסופיים לתיקיית הייצוא, והדוחות וה-run manifests נשארים ב-workspace. כל טסט עם
# workspace ו-data משלו (CLIPFORGE_WORKSPACE_DIR / CLIPFORGE_DATA_DIR לתת-התהליך), ותיקיית הייצוא דרך המשתנה או דרך
# data/export_settings.json שלו - לא ב-data/ המשותף של הריצה.
# xdist-group: workspace (רינדורים אמיתיים תופסים את מנעול הרינדור)
import json
import os
import subprocess
import sys

from tests import PROJECT_ROOT
from tests import video_editor_golden as golden
from tests.media_support import needs_ffmpeg
from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

TIMELAPSE = os.path.join(PROJECT_ROOT, "my_scripts", "video", "timelapse_maker.py")
ROCKET = os.path.join(PROJECT_ROOT, "my_scripts", "video", "rocket_shorts_publisher.py")


def _clip(folder, name, seconds=1):
    folder.mkdir(exist_ok=True)
    subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=160x120:rate=10", "-pix_fmt", "yuv420p",
                    str(folder / name)], capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)


def _env(tmp_path, **extra):
    env = {k: v for k, v in os.environ.items() if k not in ("RENDER_LOCK_HELD_BY_CALLER", "CLIPFORGE_EXPORT_DIR")}
    env.update(CLIPFORGE_WORKSPACE_DIR=str(tmp_path / "workspace"), CLIPFORGE_DATA_DIR=str(tmp_path / "data"), **extra)
    (tmp_path / "data").mkdir(exist_ok=True)
    return env


def _mp4s(folder):
    return sorted(n for n in os.listdir(folder) if n.endswith(".mp4")) if os.path.isdir(folder) else []


def test_studio_outputs_go_to_the_export_folder_and_reports_stay(tmp_path, monkeypatch):
    workspace, exports = tmp_path / "workspace", tmp_path / "exports"
    exports.mkdir()
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_EXPORT_DIR", str(exports))
    source = tmp_path / "in"
    source.mkdir()
    module = golden._load(str(source), ["--vertical"], 0)
    assert module.OUTPUT_DIR == os.path.join(str(exports), "studio", "vertical")
    assert module.REPORTS_DIR == os.path.join(str(workspace), "reports")
    assert module.RUN_MANIFESTS_DIR == os.path.join(str(workspace), ".cache", "run_manifests")


@needs_ffmpeg
def test_a_real_studio_render_lands_in_the_export_folder(tmp_path):
    exports = tmp_path / "exports"
    exports.mkdir()
    _clip(tmp_path / "in", "exportclip.mp4")
    result = subprocess.run([sys.executable, "-u", golden.SCRIPT, "--input_dir", str(tmp_path / "in"), "--codec", "h264", "--force"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
                            creationflags=NO_WINDOW_FLAGS, env=_env(tmp_path, CLIPFORGE_EXPORT_DIR=str(exports)))
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert [n for n in _mp4s(exports / "studio" / "horizontal") if n.startswith("exportclip")]
    assert _mp4s(tmp_path / "workspace" / "studio" / "horizontal") == []
    manifests = list((tmp_path / "workspace" / ".cache" / "run_manifests").glob("*.json"))
    assert len(manifests) == 1
    assert json.loads(manifests[0].read_text(encoding="utf-8"))["output_dir"].startswith(str(exports))


def _timelapse(tmp_path, root):
    _clip(tmp_path / "in", "tl.mp4", seconds=3)   # קצר מהיעד = מדולג
    env = _env(tmp_path)
    (tmp_path / "data" / "export_settings.json").write_text(json.dumps({"root": root}), encoding="utf-8")
    return subprocess.run([sys.executable, TIMELAPSE, "--input_dir", str(tmp_path / "in"), "--target-seconds", "1"],
                          cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120,
                          creationflags=NO_WINDOW_FLAGS, env=env)


@needs_ffmpeg
def test_the_saved_setting_sends_a_timelapse_to_the_export_folder(tmp_path):
    exports = tmp_path / "exports"
    exports.mkdir()
    result = _timelapse(tmp_path, str(exports))
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert _mp4s(exports / "timelapses" / "horizontal")
    assert _mp4s(tmp_path / "workspace" / "timelapses" / "horizontal") == []


@needs_ffmpeg
def test_an_unavailable_export_folder_falls_back_to_workspace_and_says_so(tmp_path):
    missing = str(tmp_path / "unplugged" / "exports")
    result = _timelapse(tmp_path, missing)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert _mp4s(tmp_path / "workspace" / "timelapses" / "horizontal")
    assert missing in result.stdout and "workspace" in result.stdout
    assert not os.path.exists(missing)


def _rocket_dry_run(tmp_path, output_dir):
    env = _env(tmp_path)
    data, source = tmp_path / "data", tmp_path / "rocket_in"
    source.mkdir()
    (source / "clip1.mp4").write_bytes(b"\x00" * 1024)
    (data / "counter.txt").write_text("1", encoding="utf-8")
    settings = {"input_dir": str(source), "output_dir": output_dir, "watermark_image_path": "",
                "counter_file_path": str(data / "counter.txt"), "encoder": "libx264"}
    (data / "rocket_settings.json").write_text(json.dumps(settings), encoding="utf-8")
    exports = tmp_path / "exports"
    exports.mkdir(exist_ok=True)
    (data / "export_settings.json").write_text(json.dumps({"root": str(exports)}), encoding="utf-8")
    result = subprocess.run([sys.executable, ROCKET, "--dry-run"], cwd=str(tmp_path), capture_output=True, text=True,
                            encoding="utf-8", timeout=120, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    return [line for line in result.stdout.splitlines() if line.startswith("[DRY-RUN] פקודה: ")], str(exports)


def test_rocket_with_its_default_folder_follows_the_export_folder(tmp_path):
    commands, exports = _rocket_dry_run(tmp_path, str(tmp_path / "workspace"))   # ברירת המחדל של Rocket = workspace
    assert commands and all(os.path.join(exports, "rocket_shorts") in cmd for cmd in commands)


def test_rocket_with_its_own_folder_keeps_it(tmp_path):
    own = tmp_path / "rocket_out"
    own.mkdir()
    commands, exports = _rocket_dry_run(tmp_path, str(own))
    assert commands and all(os.path.join(str(own), "rocket_shorts") in cmd and exports not in cmd for cmd in commands)


# ---------- שלב 2: תיקייה לכלי ----------
def test_a_studio_folder_receives_the_studio_outputs_directly(tmp_path, monkeypatch):
    from utils.shared import export_dir
    studio = tmp_path / "studio_out"
    studio.mkdir()
    settings = tmp_path / "export_settings.json"
    settings.write_text(json.dumps({"root": "", "tools": {"studio": str(studio)}}), encoding="utf-8")
    monkeypatch.setattr(export_dir, "SETTINGS_PATH", str(settings))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(tmp_path / "workspace"))
    (tmp_path / "in").mkdir()
    module = golden._load(str(tmp_path / "in"), ["--vertical"], 0)
    assert module.OUTPUT_DIR == os.path.join(str(studio), "vertical")


@needs_ffmpeg
def test_a_timelapse_folder_receives_the_timelapses(tmp_path):
    own = tmp_path / "my_timelapses"
    own.mkdir()
    _clip(tmp_path / "in", "tl.mp4", seconds=3)
    env = _env(tmp_path)
    (tmp_path / "data" / "export_settings.json").write_text(json.dumps({"tools": {"timelapses": str(own)}}), encoding="utf-8")
    result = subprocess.run([sys.executable, TIMELAPSE, "--input_dir", str(tmp_path / "in"), "--target-seconds", "1"],
                            cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120,
                            creationflags=NO_WINDOW_FLAGS, env=env)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert _mp4s(own / "horizontal") and _mp4s(tmp_path / "workspace" / "timelapses" / "horizontal") == []
