# tests/bot/test_rocket_shorts_publisher.py
#
# my_scripts/video/rocket_shorts_publisher.py כתת-תהליך, בתיקיות זמניות (CLIPFORGE_DATA_DIR + rocket_settings.json
# שמפנה ל-tmp_path). בלי ffmpeg אמיתי: ב---dry-run לא מרנדרים, ובלי --dry-run הסקריפט עוצר לפני הרינדור.
import json
from tests import PROJECT_ROOT
import os
import subprocess
import sys

BASE_DIR = PROJECT_ROOT
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "rocket_shorts_publisher.py")


def _setup(tmp_path, with_logo_key=True):
    data_dir, input_dir, output_dir = tmp_path / "data", tmp_path / "in", tmp_path / "out"
    for d in (data_dir, input_dir, output_dir):
        d.mkdir()
    (input_dir / "clip1.mp4").write_bytes(b"\x00" * 1024)
    (data_dir / "counter.txt").write_text("7", encoding="utf-8")
    settings = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "watermark_image_path": str(tmp_path / "missing_logo.png"),
        "counter_file_path": str(data_dir / "counter.txt"),
        "encoder": "libx264",
    }
    if not with_logo_key:
        del settings["watermark_image_path"]
    (data_dir / "rocket_settings.json").write_text(json.dumps(settings), encoding="utf-8")
    return data_dir, output_dir


def _run(tmp_path, data_dir, *args):
    env = {k: v for k, v in os.environ.items() if k != "RENDER_LOCK_HELD_BY_CALLER"}
    env["CLIPFORGE_DATA_DIR"] = str(data_dir)
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=str(tmp_path), env=env, capture_output=True,
                          text=True, encoding="utf-8", timeout=120)


def _rendered_files(output_dir):
    return [name for _, _, names in os.walk(output_dir) for name in names]


def test_dry_run_simulates_both_targets_without_rendering_or_advancing_the_counter(tmp_path):
    data_dir, output_dir = _setup(tmp_path)
    proc = _run(tmp_path, data_dir, "--dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.count("[DRY-RUN] היה מריץ") == 2
    assert "Shorts #7" in proc.stdout
    assert (data_dir / "counter.txt").read_text(encoding="utf-8") == "7"
    assert _rendered_files(output_dir) == []


def _saved_naming(data_dir):
    saved = json.loads((data_dir / "rocket_settings.json").read_text(encoding="utf-8"))
    return saved.get("title_prefix"), saved.get("game_name")


def test_settings_without_the_naming_keys_get_the_defaults_written_and_a_chosen_4k_keeps_the_old_graph(tmp_path):
    """30.10.2026: קובץ הגדרות בלי title_prefix/game_name/output_resolution - ברירות המחדל נכתבות אליו (גם כשיש מונה). מי
    שבוחר 4K מקבל בדיוק את הגרף של לפני שהייתה הגדרה."""
    data_dir, _output_dir = _setup(tmp_path)
    proc = _run(tmp_path, data_dir, "--dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Shorts #7" in proc.stdout
    assert _saved_naming(data_dir) == ("Shorts", "")
    settings = json.loads((data_dir / "rocket_settings.json").read_text(encoding="utf-8"))
    assert settings["output_resolution"] == "source"
    settings["output_resolution"] = "2160"
    (data_dir / "rocket_settings.json").write_text(json.dumps(settings), encoding="utf-8")
    proc = _run(tmp_path, data_dir, "--dry-run")
    yt, tt = _dry_run_commands(proc)
    # 4K כמו קודם, ואותו גרף בדיוק (בלי scale ללוגו)
    assert "scale=3840:2160:force_original_aspect_ratio=decrease,pad=3840:2160" in yt and "overlay=(W-w)/2:H-h-120" in yt
    assert "crop=2160:3840" in tt and "[1:v]format=rgba" in tt


def test_a_new_install_names_files_shorts_and_stays_that_way_after_the_counter_appears(tmp_path):
    data_dir, _output_dir = _setup(tmp_path)
    (data_dir / "counter.txt").unlink()
    proc = _run(tmp_path, data_dir, "--dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Shorts #1" in proc.stdout
    assert _saved_naming(data_dir) == ("Shorts", "")
    (data_dir / "counter.txt").write_text("2", encoding="utf-8")   # כמו אחרי הרינדור הראשון
    proc = _run(tmp_path, data_dir, "--dry-run")
    assert "Shorts #2" in proc.stdout


def _dry_run_commands(proc):
    return [line.split("פקודה: ", 1)[1] for line in proc.stdout.splitlines() if line.startswith("[DRY-RUN] פקודה: ")]


def test_loudnorm_resamples_to_48khz_in_every_target(tmp_path):
    """loudnorm מוציא 192kHz, ובלי aresample=48000 ה-AAC יצא ב-96kHz (נמצא בסטודיו, 16.10.2026)."""
    data_dir, _ = _setup(tmp_path)
    proc = _run(tmp_path, data_dir, "--dry-run")
    commands = _dry_run_commands(proc)
    assert len(commands) == 2, proc.stdout
    for cmd in commands:
        assert "loudnorm=I=-14:LRA=11:TP=-1.5,aresample=48000" in cmd, cmd


def test_no_loudnorm_leaves_the_audio_untouched(tmp_path):
    data_dir, _ = _setup(tmp_path)
    proc = _run(tmp_path, data_dir, "--dry-run", "--no-loudnorm")
    commands = _dry_run_commands(proc)
    assert len(commands) == 2, proc.stdout
    # "loudnorm=" ולא "loudnorm" - שם הטסט נכנס לנתיב של tmp_path
    assert not any("loudnorm=" in cmd or "aresample=" in cmd for cmd in commands)


def test_real_run_without_the_logo_file_exits_1_before_rendering(tmp_path):
    data_dir, output_dir = _setup(tmp_path)
    proc = _run(tmp_path, data_dir)
    assert proc.returncode == 1
    assert "קובץ הלוגו לא נמצא" in proc.stdout
    assert (data_dir / "counter.txt").read_text(encoding="utf-8") == "7"
    assert _rendered_files(output_dir) == []


def test_without_a_chosen_logo_it_renders_without_one(tmp_path):
    """ברירת המחדל הייתה assets/overlay.png, שכבר לא בריפו - עכשיו ריקה. מ-30.10.2026 בלי לוגו מרנדרים בלעדיו, לא יוצאים."""
    data_dir, _ = _setup(tmp_path, with_logo_key=False)
    proc = _run(tmp_path, data_dir, "--dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    commands = _dry_run_commands(proc)
    assert len(commands) == 2
    assert all(c.count(" -i ") == 1 and "[wm]" not in c and "overlay" not in c for c in commands)


def test_without_a_chosen_encoder_it_renders_on_the_cpu(tmp_path):
    """30.10.2026: ברירת המחדל עובדת בכל מחשב (libx264); NVENC רק כשבוחרים פרופיל שלו - קובץ קיים שומר את המקודד שלו."""
    data_dir, _output_dir = _setup(tmp_path)
    settings_path = data_dir / "rocket_settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    del settings["encoder"]
    settings_path.write_text(json.dumps(settings), encoding="utf-8")
    proc = _run(tmp_path, data_dir, "--dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    commands = _dry_run_commands(proc)
    assert commands and all("libx264" in c and "nvenc" not in c for c in commands)


def test_a_new_install_renders_at_the_source_resolution(tmp_path):
    """30.10.2026: בלי מונה (התקנה חדשה) - output_resolution="source"; הקליפ המזויף לא נקרא, אז המידע הוא ברירת המחדל 1920x1080."""
    data_dir, _output_dir = _setup(tmp_path)
    (data_dir / "counter.txt").unlink()
    proc = _run(tmp_path, data_dir, "--dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads((data_dir / "rocket_settings.json").read_text(encoding="utf-8"))["output_resolution"] == "source"
    yt, tt = _dry_run_commands(proc)
    assert "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080" in yt and "3840" not in yt
    assert "crop=1080:1920" in tt
    assert "scale=iw*0.5000:-2" in yt and "H-h-60" in yt   # הלוגו והמרווח מוקטנים באותו יחס
    assert "YouTube (1080p" in proc.stdout
