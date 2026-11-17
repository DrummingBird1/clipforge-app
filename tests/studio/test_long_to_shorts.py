# tests/studio/test_long_to_shorts.py
#
# 16.11.2026 (2.0): "הקלטה ארוכה לכמה שורטס" - moment_finder (בחירת רגעים), shorts_layout (הפקודה), והסקריפט מקצה לקצה על
# הקלטה קטנה אמיתית: שני "פיצוצים" בשמע ומצלמה כ-stream וידאו שני -> שני שורטס אנכיים 1080x1920 עם Facecam.
import os
import subprocess
import sys

from tests import PROJECT_ROOT
from tests.media_support import needs_ffmpeg
from utils.media import face_track as ft
from utils.media import moment_finder as mf
from utils.media import shorts_layout as sl
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe

SCRIPT = os.path.join(PROJECT_ROOT, "my_scripts", "video", "long_to_shorts.py")


def _levels(peaks, total_seconds, loud=-5.0, quiet=-40.0):
    levels = [quiet] * int(total_seconds * 10)
    for second, extra in peaks:
        levels[int(second * 10)] = loud + extra
    return levels


def test_the_strongest_moments_win_and_never_overlap():
    levels = _levels([(50, 0), (55, 5), (200, 2), (400, 1)], 600)
    moments = mf.find_moments(levels, -40.0, 600, count=3, length=30)
    assert [m.peak for m in moments] == [55.0, 200.0, 400.0]       # 50 נבלע בחלון של 55 (החזק יותר)
    assert all(m.end - m.start == 30 for m in moments)
    assert moments[0].start == 34.0 and moments[0].peak_in_clip == 21.0   # השיא ב-70% מהחלון


def test_windows_stay_inside_the_file_and_quiet_files_have_none():
    moments = mf.find_moments(_levels([(1, 0), (59, 0)], 60), -40.0, 60, count=5, length=30)
    assert [(m.start, m.end) for m in moments] == [(0.0, 30.0), (30.0, 60.0)]
    assert mf.find_moments([-40.0] * 100, -40.0, 10) == []


def test_layout_commands():
    center = sl.build_command("ffmpeg", "in.mkv", 10, 30, "out.mp4")
    graph = center[center.index("-filter_complex") + 1]
    assert "crop=1080:1920" in graph and "between" not in graph and center[center.index("-ss") + 1] == "10.00"
    face = sl.build_command("ffmpeg", "in.mkv", 0, 30, "out.mp4", layout="facecam", has_cam=True, punch_at=21, mic_track=1)
    graph = face[face.index("-filter_complex") + 1]
    assert "[0:v:1]" in graph and "vstack" in graph and "between(t\\,20.00\\,22.50)" in graph and "[0:a:1]" in graph
    no_cam = sl.build_command("ffmpeg", "in.mkv", 0, 30, "o.mp4", layout="facecam", has_cam=False)
    assert "vstack" not in no_cam[no_cam.index("-filter_complex") + 1]


@needs_ffmpeg
def test_a_long_recording_becomes_vertical_facecam_shorts(tmp_path):
    folder = tmp_path / "recordings"
    folder.mkdir()
    source = folder / "session.mkv"
    loud = "volume='if(between(t,4,4.5)+between(t,14,14.5),8,0.02)':eval=frame"
    subprocess.run([get_ffmpeg_exe(), "-hide_banner", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=20",
                    "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10:duration=20", "-f", "lavfi", "-i", "sine=f=300:d=20",
                    "-filter_complex", f"[2:a]{loud}[a]", "-map", "0:v", "-map", "1:v", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(source)], check=True, capture_output=True, timeout=120)
    (tmp_path / "exports").mkdir()   # תיקיית ייצוא שלא קיימת = workspace (export_dir)
    env = dict(os.environ, CLIPFORGE_EXPORT_DIR=str(tmp_path / "exports"))
    result = subprocess.run([sys.executable, SCRIPT, "--input_dir", str(folder), "--count", "2", "--length", "5", "--threshold", "10"],
                            cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=300, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    out_dir = tmp_path / "exports" / "long_to_shorts" / "vertical"
    outputs = sorted(os.listdir(out_dir))
    assert outputs == ["session_short_1.mp4", "session_short_2.mp4"], result.stdout
    size = subprocess.run([get_ffprobe_exe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", str(out_dir / outputs[0])], capture_output=True, text=True, encoding="utf-8").stdout.strip()
    assert size == "1080,1920"
    # 2.0.1: ההילוך האיטי על השיא (שנייה של מקור בחצי מהירות) מאריך כל Short בשנייה, בווידאו ובשמע
    for kind in ("v:0", "a:0"):
        length = subprocess.run([get_ffprobe_exe(), "-v", "error", "-select_streams", kind, "-show_entries", "stream=duration",
                                 "-of", "csv=p=0", str(out_dir / outputs[0])], capture_output=True, text=True, encoding="utf-8").stdout.strip()
        assert 5.7 <= float(length) <= 6.3, (kind, length)
    assert "לא זוהו פנים" in result.stdout       # testsrc2 בלי פנים: המצלמה נשארת חתוכה למרכז, והריצה לא נכשלת


def test_slowmo_sits_on_the_peak_and_skips_an_empty_edge():
    assert sl.slowmo_window(30, 21) == (20.7, 21.7) and sl.slowmo_window(30, None) is None
    assert sl.slowmo_window(30, 0.1) == (0.0, 0.8) and sl.slowmo_window(30, 30.0) == (29.7, 30.0)
    assert sl.slowmo_window(30, 30.2) is None                      # פחות מ-0.2 שניות בתוך הקטע
    cmd = sl.build_command("ffmpeg", "in.mkv", 0, 30, "out.mp4", punch_at=21, slowmo_at=21, fps=60)
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "[vl]split=3[sv0][sv1][sv2]" in graph and "trim=start=20.70:end=21.70,setpts=PTS-STARTPTS,setpts=PTS/0.5" in graph
    assert "concat=n=3:v=1:a=0[vs];[vs]fps=60[v]" in graph
    assert "[0:a:0]asplit=3" in graph and "atrim=start=20.70:end=21.70,asetpts=PTS-STARTPTS,atempo=0.5" in graph
    assert cmd[cmd.index("[v]") + 1:cmd.index("[v]") + 3] == ["-map", "[a]"]
    start = sl.build_command("ffmpeg", "in.mkv", 0, 30, "out.mp4", slowmo_at=0.1, mic_track=1)   # שיא בהתחלה: שני חלקים, והמיקרופון לפני ההאטה
    graph = start[start.index("-filter_complex") + 1]
    assert "split=2" in graph and "amix=inputs=2:duration=first:dropout_transition=0:normalize=0[am];[am]asplit=2" in graph
    silent = sl.build_command("ffmpeg", "in.mkv", 0, 30, "out.mp4", slowmo_at=21, has_audio=False)
    assert "asplit" not in silent[silent.index("-filter_complex") + 1] and "[a]" not in silent and "0:a:0?" not in silent
    plain = sl.build_command("ffmpeg", "in.mkv", 0, 30, "out.mp4", punch_at=21)                   # בלי הילוך איטי - כמו ב-2.0.0
    assert "split" not in plain[plain.index("-filter_complex") + 1] and "0:a:0?" in plain


def test_the_facecam_frame_holds_still_then_follows_the_face():
    still = [(0.50, 0.40, 0.11)] * 6
    moved = [(0.70, 0.45, 0.11)] * 6
    track = ft.plan(still + [None, None] + moved)          # חור של שנייה מקבל את המיקום האחרון
    assert track.zoom == 2.0                                # פנים קטנות (11% מהרוחב) - הזום המרבי
    assert track.keys == [(0.0, 0.5, 0.4), (3.5, 0.5, 0.4), (4.0, 0.7, 0.45), (6.5, 0.7, 0.45)]
    jitter = [(0.50 + 0.01 * (i % 3), 0.40, 0.30) for i in range(20)]
    calm = ft.plan(jitter)
    assert calm.zoom == 1.0 and len({k[1:] for k in calm.keys}) == 1   # רעד קטן מה-deadband לא מזיז את המסגרת
    assert ft.plan([None] * 20) is None and ft.plan([None] * 9 + [(0.5, 0.5, 0.2)]) is None
    wander = [(0.1 + 0.8 * (i % 2), 0.5, 0.2) for i in range(200)]
    assert len(ft.plan(wander).keys) <= ft.MAX_KEYS         # מי שלא מפסיק לזוז: פחות נקודות מפתח, לא שורת פקודה אינסופית
    text = ft.crop_filter(track, 1080, 608)
    assert text.startswith(r"scale=2160:1216:force_original_aspect_ratio=increase,crop=1080:608:x='max(0\,min(iw-ow\,iw*(")
    assert r"gte(t\,3.50)*lt(t\,4.00)*(0.5000+(0.2000)*(t-3.50)/0.50)" in text and r"0.7000*gte(t\,6.50)" in text
    assert ft.crop_filter(calm, 1080, 608).count("gte(") == 0   # מסגרת שלא זזה = מספר קבוע
    cmd = sl.build_command("ffmpeg", "in.mkv", 0, 30, "out.mp4", layout="facecam", has_cam=True, cam_track=track)
    assert "[0:v:1]scale=2160:1216" in cmd[cmd.index("-filter_complex") + 1]


@needs_ffmpeg
def test_a_tracked_facecam_and_slowmo_render_with_real_ffmpeg(tmp_path):
    source, out = tmp_path / "cam.mkv", tmp_path / "short.mp4"
    subprocess.run([get_ffmpeg_exe(), "-hide_banner", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=8",
                    "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10:duration=8", "-f", "lavfi", "-i", "sine=f=300:d=8",
                    "-map", "0:v", "-map", "1:v", "-map", "2:a", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(source)],
                   check=True, capture_output=True, timeout=120)
    track = ft.Track(1.5, [(0.0, 0.3, 0.4), (2.0, 0.3, 0.4), (2.5, 0.7, 0.6), (6.0, 0.7, 0.6)])
    cmd = sl.build_command(get_ffmpeg_exe(), str(source), 1, 6, str(out), layout="facecam", has_cam=True, punch_at=3, slowmo_at=3,
                           cam_track=track, fps=10, video_args=["-c:v", "libx264", "-preset", "ultrafast"])
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")[-600:]
    info = subprocess.run([get_ffprobe_exe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,duration",
                           "-of", "csv=p=0", str(out)], capture_output=True, text=True, encoding="utf-8").stdout.strip().split(",")
    assert info[:2] == ["1080", "1920"] and 6.7 <= float(info[2]) <= 7.3
    assert ft.sample_faces(str(source), 1, 6, get_ffmpeg_exe(), 160, 120) == [None] * 12    # 6 שניות, פעמיים בשנייה, בלי פנים


def test_sampling_reads_ffmpeg_frames_and_keeps_the_biggest_sure_face(monkeypatch):
    import cv2
    import numpy as np
    frame = ft.SAMPLE_W * 270 * 3                       # מצלמת 16:9 -> 480x270
    seen = {}

    class _Done:
        stdout = bytes(frame * 3 + 100)                 # שלושה פריימים שלמים ושארית שנזרקת

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return _Done()

    class _Detector:
        calls = 0

        def detect(self, image):
            assert image.shape == (270, ft.SAMPLE_W, 3)
            _Detector.calls += 1
            if _Detector.calls == 2:
                return 1, None                           # פריים בלי פנים
            return 1, np.array([[48, 27, 96, 108, 0.9], [240, 100, 200, 150, 0.3], [0, 0, 20, 20, 0.95]], dtype=np.float32)

    monkeypatch.setattr(ft.subprocess, "run", fake_run)
    monkeypatch.setattr(cv2, "FaceDetectorYN_create", lambda *a, **k: _Detector())
    samples = ft.sample_faces("in.mkv", 12.5, 30, "ffmpeg", 1280, 720)
    assert samples == [(0.2, 0.3, 0.2), None, (0.2, 0.3, 0.2)]    # הגדול מבין הבטוחים; 0.3 ביטחון לא נחשב
    cmd = seen["cmd"]
    assert cmd[cmd.index("-map") + 1] == "0:v:1" and cmd[cmd.index("-ss") + 1] == "12.50" and "fps=2,scale=480:270" in cmd
    assert ft.sample_faces("in.mkv", 0, 30, "ffmpeg", 0, 0) == []   # גודל מצלמה לא ידוע - בלי מעקב
