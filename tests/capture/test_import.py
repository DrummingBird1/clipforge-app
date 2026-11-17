# tests/capture/test_import.py
#
# utils/capture/import_presets.py + importer.py: איפה כל תוכנה וקונסולה שומרת, ייבוא רק של מה שחדש, המקור לא נוגע,
# ו-Steam (DASH) עם ffmpeg אמיתי. עץ תיקיות מזויף בכל טסט.
import json
import os
import subprocess
import time

from tests.media_support import needs_ffmpeg
from utils.capture import import_presets as ip
from utils.capture import importer
from utils.shared.ffmpeg_locator import get_ffmpeg_exe

OLD = time.time() - 3600


def _file(path, data=b"video", mtime=OLD):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (mtime, mtime))
    return path


def test_presets_cover_pc_tools_and_consoles_on_removable_drives(tmp_path):
    env = {"USERPROFILE": str(tmp_path / "me"), "APPDATA": str(tmp_path / "appdata"), "OneDrive": str(tmp_path / "od")}
    steam = tmp_path / "steam"
    (steam / "userdata" / "123" / "gamerecordings").mkdir(parents=True)
    obs_profile = tmp_path / "appdata" / "obs-studio" / "basic" / "profiles" / "Main"
    obs_profile.mkdir(parents=True)
    (obs_profile / "basic.ini").write_text("[Output]\nMode=Advanced\n[AdvOut]\nRecFilePath=D:\\Rec\n", encoding="utf-8")
    registry = {r"Software\Valve\Steam": str(steam)}
    found = ip.presets(env, registry=lambda key, value, hive="HKCU": registry.get(key), drives=["F:\\"])
    by_id = {p.id: p for p in found}
    assert by_id["gamebar"].path.endswith(os.path.join("Videos", "Captures"))
    assert by_id["obs"].path == os.path.normpath("D:\\Rec")
    assert by_id["steam"].kind == "steam" and by_id["steam"].path == str(steam / "userdata")
    (steam / "userdata" / "456" / "gamerecordings").mkdir(parents=True)                     # חשבון שני - עדיין מקור אחד
    again = ip.presets(env, registry=lambda key, value, hive="HKCU": registry.get(key), drives=[])
    assert [p.id for p in again if p.kind == "steam"] == ["steam"]
    assert importer._steam_roots(str(steam / "userdata")) == [str(steam / "userdata" / "123" / "gamerecordings"),
                                                              str(steam / "userdata" / "456" / "gamerecordings")]
    assert by_id["ps5:F:"].path == os.path.join("F:\\", "PS5", "CREATE", "Video Clips") and by_id["ps5:F:"].console
    assert by_id["switch:F:"].path.endswith(os.path.join("Nintendo", "Album"))
    assert by_id["xbox"].path.endswith(os.path.join("Videos", "Xbox Game DVR"))


def test_nvidia_takes_only_its_own_files_from_the_shared_videos_folder(tmp_path):
    videos = tmp_path / "Videos"
    _file(videos / "Rocket League" / "Rocket League 2026.11.16 - 14.03.22.01.DVR.mp4")
    _file(videos / "Family" / "birthday.mp4")
    preset = ip.Preset("nvidia", "NVIDIA", str(videos), "folder", True, False, ip.NVIDIA_NAME)
    assert [os.path.basename(i.source) for i in importer.find_new(preset, {})] == ["Rocket League 2026.11.16 - 14.03.22.01.DVR.mp4"]


def test_a_ps5_drive_is_imported_once_and_left_untouched(tmp_path):
    drive = tmp_path / "usb"
    clip = _file(drive / "PS5" / "CREATE" / "Video Clips" / "Astro Bot" / "clip.webm")
    _file(drive / "PS5" / "CREATE" / "Screenshots" / "shot.jpg")
    _file(drive / "PS5" / "CREATE" / "Video Clips" / "Astro Bot" / "growing.mp4", mtime=time.time())   # עוד נכתב
    preset = [p for p in ip.presets({"USERPROFILE": str(tmp_path)}, registry=lambda *a, **k: None, drives=[str(drive)])
              if p.id.startswith("ps5:")][0]
    manifest_path = str(tmp_path / "ws" / ".cache" / "import_manifest.json")
    items = importer.find_new(preset, importer.load_manifest(manifest_path))
    assert [os.path.basename(i.source) for i in items] == ["clip.webm"]
    dest = tmp_path / "imports"
    (dest).mkdir()
    (dest / "clip.webm").write_bytes(b"already here")
    done = importer.import_items(items, str(dest), manifest_path, "ffmpeg")
    assert [os.path.basename(p) for p in done] == ["clip_2.webm"]
    assert clip.exists() and clip.read_bytes() == b"video"
    assert importer.find_new(preset, importer.load_manifest(manifest_path)) == []
    assert json.load(open(manifest_path, encoding="utf-8"))


def test_a_changed_file_with_the_same_name_counts_as_new(tmp_path):
    folder = tmp_path / "rec"
    clip = _file(folder / "a.mp4")
    preset = ip.Preset("x", "X", str(folder), "folder", False, False)
    manifest_path = str(tmp_path / "m.json")
    importer.import_items(importer.find_new(preset, {}), str(tmp_path / "out"), manifest_path, "ffmpeg")
    _file(clip, data=b"a longer, new recording")
    assert len(importer.find_new(preset, importer.load_manifest(manifest_path))) == 1


@needs_ffmpeg
def test_a_steam_dash_recording_is_remuxed_to_mp4(tmp_path):
    session = tmp_path / "steam" / "gamerecordings" / "clips" / "clip_730_20261116_140322" / "video" / "bg_730_x"
    session.mkdir(parents=True)
    # cwd = תיקיית ה-session: עם נתיב מוחלט ה-dash muxer כותב את הקטעים לתיקיית העבודה הנוכחית, לא ליד ה-mpd
    subprocess.run([get_ffmpeg_exe(), "-hide_banner", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=3",
                    "-c:v", "libx264", "-preset", "ultrafast", "-f", "dash", "session.mpd"],
                   check=True, capture_output=True, timeout=120, cwd=str(session))
    assert (session / "init-stream0.m4s").exists()
    for path in session.iterdir():
        os.utime(path, (OLD, OLD))
    preset = ip.Preset("steam", "Steam", str(tmp_path / "steam" / "gamerecordings"), "steam", True, False)
    items = importer.find_new(preset, {})
    assert len(items) == 1 and items[0].kind == "steam"
    done = importer.import_items(items, str(tmp_path / "imports"), str(tmp_path / "m.json"), get_ffmpeg_exe())
    assert [os.path.basename(p) for p in done] == ["clip_730_20261116_140322.mp4"] and os.path.getsize(done[0]) > 0


# ---- 2.0.1: מהבדיקה המעמיקה ----

def test_obs_takes_only_files_obs_named(tmp_path):
    # תיקיית ההקלטות של OBS היא בדרך כלל Videos כולה. ב-2.0.0 "ייבוא מ-OBS" העתיק כל סרטון שיש שם.
    env = {"USERPROFILE": str(tmp_path / "me"), "APPDATA": str(tmp_path / "appdata")}
    videos = tmp_path / "me" / "Videos"
    profiles = tmp_path / "appdata" / "obs-studio" / "basic" / "profiles"
    (profiles / "Old").mkdir(parents=True)
    (profiles / "Stream").mkdir()
    (profiles / "Old" / "basic.ini").write_text("[SimpleOutput]\nFilePath=C:\\Wrong\n", encoding="utf-8")
    (profiles / "Stream" / "basic.ini").write_text(f"[SimpleOutput]\nFilePath={videos}\n", encoding="utf-8")
    (tmp_path / "appdata" / "obs-studio" / "user.ini").write_text("[Basic]\nProfileDir=Stream\n", encoding="utf-8")   # OBS חדש
    obs = next(p for p in ip.presets(env, registry=lambda *a, **k: None, drives=[]) if p.id == "obs")
    assert obs.path == os.path.normpath(str(videos))          # הפרופיל הפעיל מ-user.ini, לא הראשון לפי הא"ב
    for name in ("2026-11-17 14-03-22.mkv", "Replay 2026-11-17 14-05-00.mp4", "wedding.mp4", "holiday 2024.mp4"):
        _file(videos / name)
    assert sorted(os.path.basename(i.source) for i in importer.find_new(obs, {})) == [
        "2026-11-17 14-03-22.mkv", "Replay 2026-11-17 14-05-00.mp4"]
    custom = ip.obs_name_pattern("Rec_%YY%MM%DD_%hh%mm", "Clip")
    import re
    assert re.search(custom, "Rec_261117_1403.mkv") and re.search(custom, "Clip Rec_261117_1403.mp4") and not re.search(custom, "wedding.mp4")


def test_a_moved_videos_folder_and_a_usb_disk_that_is_not_removable(tmp_path):
    moved = tmp_path / "D" / "Movies"
    moved.mkdir(parents=True)
    env = {"USERPROFILE": str(tmp_path / "me")}
    found = ip.presets(env, registry=lambda key, value, hive="HKCU": str(moved) if value == "My Video" else None, drives=[])
    assert next(p for p in found if p.id == "nvidia").path == str(moved)
    assert next(p for p in found if p.id == "elgato").path == os.path.join(str(moved), "4K Capture Utility")


def test_an_import_folder_inside_the_source_is_not_imported_into_itself(tmp_path):
    # ב-2.0.0, עם תיקיית NVIDIA כתיקיית ה-Import, כל ייבוא יצר עותק _2 של כל קליפ
    videos = tmp_path / "Videos"
    preset = ip.Preset("amd", "AMD", str(videos), "folder", True, False)
    _file(videos / "Game" / "clip.mp4")
    dest = videos / "Import"
    manifest_path = str(tmp_path / "cache" / "manifest.json")
    first = importer.find_new(preset, {}, exclude=str(dest))
    assert len(first) == 1
    importer.import_items(first, str(dest), manifest_path, "ffmpeg")
    assert importer.find_new(preset, importer.load_manifest(manifest_path), exclude=str(dest)) == []
    assert sorted(os.listdir(dest)) == ["clip.mp4"]


def test_the_same_usb_drive_under_another_letter_is_not_imported_again(tmp_path):
    clip = _file(tmp_path / "F" / "PS5" / "CREATE" / "Video Clips" / "Game" / "win.webm", b"x" * 50)
    manifest_path = str(tmp_path / "cache" / "manifest.json")
    preset = ip.Preset("ps5:F", "PS5", str(tmp_path / "F" / "PS5" / "CREATE" / "Video Clips"), "folder", True, True)
    importer.import_items(importer.find_new(preset, {}), str(tmp_path / "import"), manifest_path, "ffmpeg")
    other = tmp_path / "G" / "PS5" / "CREATE" / "Video Clips" / "Game" / "win.webm"
    _file(other, b"x" * 50, mtime=os.path.getmtime(clip))
    again = ip.Preset("ps5:G", "PS5", str(tmp_path / "G" / "PS5" / "CREATE" / "Video Clips"), "folder", True, True)
    assert importer.find_new(again, importer.load_manifest(manifest_path)) == []


def test_a_copy_that_fails_leaves_no_broken_file_and_the_rest_continue(tmp_path, monkeypatch):
    source = tmp_path / "src"
    good, bad, last = _file(source / "a.mp4", mtime=OLD), _file(source / "b.mp4", mtime=OLD + 1), _file(source / "c.mp4", mtime=OLD + 2)
    preset = ip.Preset("x", "X", str(source), "folder", False, False)
    real_copy = importer.shutil.copy2

    def flaky(src, dst):
        if os.path.basename(src) == "b.mp4":
            open(dst, "wb").write(b"half")
            raise OSError("the drive was pulled out")
        return real_copy(src, dst)

    monkeypatch.setattr(importer.shutil, "copy2", flaky)
    failures = []
    dest = tmp_path / "import"
    done = importer.import_items(importer.find_new(preset, {}), str(dest), str(tmp_path / "m.json"), "ffmpeg", failures=failures)
    assert [os.path.basename(p) for p in done] == ["a.mp4", "c.mp4"] and sorted(os.listdir(dest)) == ["a.mp4", "c.mp4"]
    assert len(failures) == 1 and failures[0].startswith("b.mp4") and bad.read_bytes() == b"video"
    assert time.time() - os.path.getmtime(dest / "a.mp4") < 60          # זמן שינוי של עכשיו, לא של ההקלטה המקורית
    assert os.path.getmtime(good) == OLD and last.exists()               # המקור לא השתנה
    monkeypatch.undo()
    retry = importer.find_new(preset, importer.load_manifest(str(tmp_path / "m.json")))
    assert [os.path.basename(i.source) for i in retry] == ["b.mp4"]      # מה שנכשל מיובא בפעם הבאה


def test_a_full_disk_stops_the_import_with_a_reason(tmp_path, monkeypatch):
    source = tmp_path / "src"
    _file(source / "a.mp4")
    preset = ip.Preset("x", "X", str(source), "folder", False, False)
    monkeypatch.setattr(importer.shutil, "disk_usage", lambda path: type("U", (), {"free": 10})())
    failures = []
    assert importer.import_items(importer.find_new(preset, {}), str(tmp_path / "import"), str(tmp_path / "m.json"), "ffmpeg",
                                 failures=failures) == []
    assert "מקום פנוי" in failures[0] and os.listdir(tmp_path / "import") == []


def test_steam_background_recordings_are_left_alone(tmp_path):
    root = tmp_path / "userdata" / "1" / "gamerecordings"
    _file(root / "clips" / "clip_730_20261117" / "video" / "fg_730" / "session.mpd")
    _file(root / "video" / "bg_730_20261117" / "session.mpd")
    preset = ip.Preset("steam", "Steam", str(tmp_path / "userdata"), "steam", True, False)
    found = importer.find_new(preset, {})
    assert len(found) == 1 and "clip_730_20261117" in found[0].source
