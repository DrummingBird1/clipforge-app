# tests/capture/test_devices.py
#
# utils/capture/devices.py: פענוח הפלט של ffmpeg -list_devices / -list_options (DirectShow) ובחירת מצב לקונסולה.
# הפלט לדוגמה בנוי לפי הפורמט האמיתי של ffmpeg 2026 (שמות ההתקנים בדויים).
from utils.capture import devices as dv

LIST_OUTPUT = """\
[in#0 @ 0000011f5db41d40] "Cam Link 4K" (video)
[in#0 @ 0000011f5db41d40]   Alternative name "@device_pnp_\\\\?\\usb#vid_0fd9&pid_0066#cam"
[in#0 @ 0000011f5db41d40] "Game Capture HD60 X" (video)
[in#0 @ 0000011f5db41d40]   Alternative name "@device_pnp_\\\\?\\usb#vid_0fd9&pid_0082#hd60x"
[in#0 @ 0000011f5db41d40] "מיקרופון (USB Audio)" (audio)
[in#0 @ 0000011f5db41d40]   Alternative name "@device_cm_{33D9A762}\\wave_{A1B2}"
[in#0 @ 0000011f5db41d40] "Mystery" (none)
Error opening input file dummy.
"""

OPTIONS_OUTPUT = """\
[in#0 @ X]   vcodec=mjpeg  min s=3840x2160 fps=5 max s=3840x2160 fps=30
[in#0 @ X]   pixel_format=nv12  min s=1920x1080 fps=5 max s=1920x1080 fps=60.0002
[in#0 @ X]   pixel_format=yuyv422  min s=1920x1080 fps=5 max s=1920x1080 fps=60.0002
[in#0 @ X]   pixel_format=nv12  min s=1920x1080 fps=5 max s=1920x1080 fps=60.0002
[in#0 @ X]   pixel_format=yuyv422  min s=1280x720 fps=5 max s=1280x720 fps=60
"""


def test_devices_come_with_their_kind_and_alternative_name():
    found = dv.parse_device_list(LIST_OUTPUT)
    assert [(d.name, d.kind) for d in found] == [("Cam Link 4K", "video"), ("Game Capture HD60 X", "video"),
                                                 ("מיקרופון (USB Audio)", "audio")]
    assert found[1].alternative.endswith("hd60x")
    assert dv.as_dicts(found)["audio"][0]["name"] == "מיקרופון (USB Audio)"


def test_modes_are_parsed_and_deduplicated():
    modes = dv.parse_device_options(OPTIONS_OUTPUT)
    assert len(modes) == 4
    assert modes[0] == dv.Mode("mjpeg", 3840, 2160, 5.0, 30.0)


def test_a_ps5_on_a_1080p_card_gets_1080p60_uncompressed():
    modes = dv.parse_device_options(OPTIONS_OUTPUT)
    ps5 = dv.console_profile("ps5")
    picked = dv.pick_mode([m for m in modes if m.width < 3840], ps5.width, ps5.height, ps5.fps)
    assert (picked.width, picked.height, picked.max_fps >= 60) == (1920, 1080, True)
    assert picked.codec in ("nv12", "yuyv422")


def test_a_switch_does_not_ask_for_more_than_1080p():
    modes = dv.parse_device_options(OPTIONS_OUTPUT)
    switch = dv.console_profile("switch")
    assert dv.pick_mode(modes, switch.width, switch.height, switch.fps).height == 1080


def test_no_modes_means_let_ffmpeg_choose():
    assert dv.pick_mode([], 1920, 1080, 60) is None


def test_every_console_has_a_profile():
    assert {p.id for p in dv.CONSOLE_PROFILES} == {"ps5", "ps4", "xbox_series", "xbox_one", "switch2", "switch"}


def test_resolution_first_by_default_and_frames_first_when_asked():
    # 2.0.1: כרטיסים רבים נותנים 4K רק ב-30. ברירת המחדל - חדות (הרזולוציה הגדולה); "תנועה חלקה" מעדיף מצב שמגיע ל-60.
    modes = [dv.Mode("mjpeg", 3840, 2160, 5, 30.0), dv.Mode("nv12", 1920, 1080, 5, 60.0)]
    assert dv.pick_mode(modes, 3840, 2160, 60) == modes[0]
    assert dv.pick_mode(modes, 3840, 2160, 60, prefer="fps") == modes[1]
    assert dv.pick_mode([modes[0]], 3840, 2160, 60, prefer="fps") == modes[0]             # אין מצב ב-60: הכי טוב שיש
    assert dv.pick_mode([dv.Mode("nv12", 3840, 2160, 5, 60.0), modes[1]], 3840, 2160, 60, prefer="fps").width == 3840


def test_a_card_that_claims_60_and_delivers_30_is_caught_before_recording():
    # נמדד על כרטיס USB אמיתי: 1080p "ב-60" נותן 30 פריימים תקינים (חצי מהחבילות שבורות), ו-720p נותן 60 אמיתיים.
    # ב-2.0.0 ההקלטה יצאה ב-30 עם תווית של 60.
    full, small = dv.Mode("mjpeg", 1920, 1080, 10, 60.0002), dv.Mode("mjpeg", 1280, 720, 10, 60.0002)
    asked = []

    def measure(mode, fps):
        asked.append((mode.height, round(fps)))
        return 29.6 if mode.height == 1080 and fps > 31 else float(round(fps))

    mode, rate, found = dv.choose_mode([full, small], 3840, 2160, 60, "resolution", measure)
    assert (mode.height, rate) == (1080, 30.0) and found == (full, 60.0, 30.0)             # חדות: 1080p ב-30 האמיתיים
    assert asked == [(1080, 60), (1080, 30)]
    mode, rate, found = dv.choose_mode([full, small], 3840, 2160, 60, "fps", measure)
    assert (mode.height, rate) == (720, 60.0) and found == (full, 60.0, 30.0)              # תנועה חלקה: 720p ב-60
    honest = dv.choose_mode([full], 3840, 2160, 60, "resolution", lambda mode, fps: 59.8)
    assert honest[1] == 60.0 and honest[2] is None
    unknown = dv.choose_mode([full], 3840, 2160, 60, "resolution", lambda mode, fps: None)   # אי אפשר למדוד: סומכים על הכרטיס
    assert unknown[1] == 60.0 and unknown[2] is None
    assert dv.choose_mode([], 1920, 1080, 60, "resolution", measure) == (None, 60.0, None)
    assert dv.real_rate(29.6) == 30.0 and dv.real_rate(59.9) == 60.0 and dv.real_rate(41.3) == 41.3


def test_measuring_counts_the_frames_that_really_arrived(monkeypatch):
    seen = {}

    class _Done:
        returncode = 0
        stderr = "frame=   12 fps=0.0 q=-0.0 size=N/A\rframe=   60 fps= 30 q=-0.0 Lsize=N/A time=00:00:02.00\n"

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return _Done()

    monkeypatch.setattr(dv.subprocess, "run", fake_run)
    assert dv.measure_mode("ffmpeg", "usb video", dv.Mode("mjpeg", 1920, 1080, 10, 60.0), 60) == 30.0
    cmd = seen["cmd"]
    assert cmd[cmd.index("-video_size") + 1] == "1920x1080" and cmd[cmd.index("-vcodec") + 1] == "mjpeg"
    assert cmd[cmd.index("-framerate") + 1] == "60" and cmd[cmd.index("-i") + 1] == "video=usb video" and cmd[-3:] == ["-f", "null", "-"]
    _Done.returncode = 1
    assert dv.measure_mode("ffmpeg", "usb video", dv.Mode("yuyv422", 1280, 720, 10, 10.0), 10) is None
    assert "-pixel_format" in seen["cmd"]
