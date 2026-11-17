# tests/capture/test_capture_command.py
#
# utils/capture/command.py: פקודת ההקלטה - מסך (ddagrab / gdigrab), כרטיס לכידה לקונסולה, מיקרופון ו-facecam כערוצים
# נפרדים, הקלטה ל-MKV או replay לקטעים. בסוף - מעבר אמיתי (ffmpeg) של קטעי replay -> קליפ MP4 עם שני ערוצי שמע.
import os
import subprocess

import pytest

from tests.media_support import needs_ffmpeg
from utils.capture import ring_buffer
from utils.capture.command import CaptureSpec, build_command, remux_command
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe


def _value(cmd, flag):
    return cmd[cmd.index(flag) + 1]


def test_screen_with_game_audio_and_mic_records_two_audio_tracks_to_mkv():
    spec = CaptureSpec(output="C:/rec/a.mkv", fps=60, game_audio_port=50123, game_audio_rate=44100, mic="Mic (USB)",
                       video_args=["-c:v", "hevc_nvenc", "-preset", "p4", "-cq", "21"])
    cmd = build_command("ffmpeg", spec)
    assert _value(cmd, "-i") == "ddagrab=output_idx=0:framerate=60"
    assert "hwdownload,format=bgra,format=yuv420p[game]" in _value(cmd, "-filter_complex")
    assert [cmd[i + 1] for i, part in enumerate(cmd) if part == "-map"] == ["[game]", "1:a", "2:a"]
    assert "audio=Mic (USB)" in cmd and "tcp://127.0.0.1:50123?listen=1&listen_timeout=20000" in cmd
    assert _value(cmd, "-ar") == "44100"
    assert cmd[cmd.index("-metadata:s:a:0") + 1] == "title=game" and cmd[cmd.index("-metadata:s:a:1") + 1] == "title=mic"
    assert cmd[-3:] == ["-f", "matroska", "C:/rec/a.mkv"]
    assert _value(cmd, "-g") == "120"


def test_a_console_capture_card_keeps_video_and_hdmi_audio_in_one_input():
    spec = CaptureSpec(source="device", output="C:/rec/ps5.mkv", device_video="HD60 X", device_audio="HD60 X Audio",
                       device_size="1920x1080", device_codec="nv12", fps=60)
    cmd = build_command("ffmpeg", spec)
    assert "video=HD60 X:audio=HD60 X Audio" in cmd
    assert _value(cmd, "-video_size") == "1920x1080" and _value(cmd, "-pixel_format") == "nv12"
    assert [cmd[i + 1] for i, part in enumerate(cmd) if part == "-map"] == ["[game]", "0:a"]


def test_an_mjpeg_card_mode_is_asked_by_vcodec():
    cmd = build_command("ffmpeg", CaptureSpec(source="device", output="x.mkv", device_video="Cam", device_codec="mjpeg"))
    assert _value(cmd, "-vcodec") == "mjpeg" and "-pixel_format" not in cmd


def test_facecam_is_a_second_video_track():
    cmd = build_command("ffmpeg", CaptureSpec(output="x.mkv", facecam="Webcam"))
    assert "[1:v]format=yuv420p[cam]" in _value(cmd, "-filter_complex")
    assert cmd[cmd.index("-metadata:s:v:1") + 1] == "title=facecam"


def test_replay_writes_short_segments_into_the_buffer_folder():
    cmd = build_command("ffmpeg", CaptureSpec(mode="replay", output="C:/cache/replay/s1", fps=30, segment_seconds=2))
    assert cmd[-1] == "C:/cache/replay/s1/" + ring_buffer.SEGMENT_PATTERN
    assert _value(cmd, "-f") != "segment" and "segment" in cmd and _value(cmd, "-segment_time") == "2"
    assert _value(cmd, "-g") == "60"   # keyframe בתחילת כל קטע - החיבור בלי קידוד מחדש מתחיל נקי


def test_gdigrab_is_the_fallback_for_screens_ddagrab_cannot_see():
    cmd = build_command("ffmpeg", CaptureSpec(output="x.mkv", use_gdigrab=True))
    assert _value(cmd, "-f") == "gdigrab" and "desktop" in cmd


@pytest.mark.parametrize("spec", [CaptureSpec(output=""), CaptureSpec(source="device", output="x.mkv"),
                                  CaptureSpec(mode="stream", output="x.mkv")])
def test_bad_specs_are_refused(spec):
    with pytest.raises(ValueError):
        build_command("ffmpeg", spec)


def test_remux_keeps_every_track():
    assert remux_command("ffmpeg", "a.mkv", "a.mp4") == ["ffmpeg", "-hide_banner", "-y", "-i", "a.mkv", "-map", "0",
                                                          "-c", "copy", "-movflags", "+faststart", "a.mp4"]


@needs_ffmpeg
def test_replay_segments_join_into_a_clip_with_both_audio_tracks(tmp_path):
    """אמיתי וקטן: 8 שניות של testsrc + שני ערוצי שמע לקטעים (אותם דגלי segment כמו build_command), ואז "שמור 4 שניות"."""
    folder = tmp_path / "replay"
    folder.mkdir()
    spec = CaptureSpec(mode="replay", output=str(folder), fps=10, segment_seconds=1)
    tail = build_command("ffmpeg", spec)
    tail = tail[tail.index("-f", tail.index("-keyint_min")):]
    subprocess.run([get_ffmpeg_exe(), "-hide_banner", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=8",
                    "-f", "lavfi", "-i", "sine=f=440:d=8", "-f", "lavfi", "-i", "sine=f=880:d=8",
                    "-map", "0:v", "-map", "1:a", "-map", "2:a", "-c:v", "libx264", "-preset", "ultrafast", "-g", "10",
                    "-c:a", "aac", *tail], check=True, capture_output=True, timeout=120)
    segments = ring_buffer.list_segments(str(folder))
    assert len(segments) >= 7
    picked = ring_buffer.select_for_save(segments, 4, segment_seconds=1)
    list_path = tmp_path / "list.txt"
    list_path.write_text(ring_buffer.concat_list([s.path for s in picked]), encoding="utf-8")
    out = tmp_path / "clip.mp4"
    subprocess.run(ring_buffer.save_command(get_ffmpeg_exe(), str(list_path), str(out)), check=True, capture_output=True, timeout=120)
    probe = subprocess.run([get_ffprobe_exe(), "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "csv=p=0",
                            str(out)], capture_output=True, text=True, encoding="utf-8", check=True).stdout.split()
    assert probe.count("audio") == 2 and probe.count("video") == 1
    duration = float(next(p for p in probe if p.replace(".", "", 1).isdigit()))
    assert 4.0 <= duration <= 6.5
    assert os.path.getsize(out) > 0
