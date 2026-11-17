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
