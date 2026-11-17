# tests/studio/test_encoders.py
#
# utils/media/encoders.py (16.11.2026, 2.0): מקודד hevc/av1 לפי הכרטיס - NVIDIA / AMD / Intel / CPU. בלי ffmpeg אמיתי:
# הבדיקה (_probe) מוחלפת. פקודות הרינדור המלאות - בקובץ הזהב (tests/video_editor_golden.py, התרחישים hevc_amf וכו').
import json

import pytest

from utils.media import encoders
from utils.video.video_editor_codec_args import get_codec_args, get_two_pass_codec_args
from utils.video.video_editor_effort import CODEC_ARGS

ALL = {"nvenc": ["hevc", "av1"], "amf": ["hevc", "av1"], "qsv": ["hevc", "av1"], "cpu": ["hevc", "av1"]}
NONE_HW = {"nvenc": [], "amf": [], "qsv": [], "cpu": ["hevc", "av1"]}


@pytest.mark.parametrize("codec", ["hevc", "av1"])
def test_nvenc_is_byte_for_byte_what_the_studio_always_used(codec):
    assert encoders.codec_args(codec, "nvenc") == CODEC_ARGS[codec]
    assert get_codec_args(codec, preset="p6", cq=24, backend="nvenc") == get_codec_args(codec, preset="p6", cq=24)
    assert encoders.bitrate_args(codec, "nvenc", 4000, preset="p3") == get_two_pass_codec_args(codec, 4000, 2, "", preset="p3")


def test_h264_stays_on_the_cpu_whatever_the_card():
    assert get_codec_args("h264", backend="amf") == CODEC_ARGS["h264"]


@pytest.mark.parametrize("backend,codec,expected", [
    ("amf", "hevc", ["-c:v", "hevc_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", "20", "-qp_p", "20"]),
    ("qsv", "av1", ["-c:v", "av1_qsv", "-preset", "slow", "-global_quality", "26"]),
    ("cpu", "hevc", ["-c:v", "libx265", "-preset", "slow", "-crf", "22"]),
    ("cpu", "av1", ["-c:v", "libsvtav1", "-preset", "6", "-crf", "32"]),
])
def test_each_card_gets_its_own_flags(backend, codec, expected):
    assert get_codec_args(codec, backend=backend) == expected


def test_the_nvenc_speed_scale_maps_onto_each_encoder():
    assert encoders.codec_args("hevc", "amf", preset="p1")[3] == "speed"
    assert encoders.codec_args("hevc", "qsv", preset="p7")[3] == "veryslow"
    assert encoders.codec_args("av1", "cpu", preset="p1")[3] == "12"
    assert encoders.codec_args("hevc", "amf", cq=30)[-1] == "30"


@pytest.mark.parametrize("requested,available,expected,warns", [
    ("auto", None, "nvenc", False),                       # ffmpeg לא רץ - ההתנהגות הקודמת
    ("auto", ALL, "nvenc", False),
    ("auto", {**NONE_HW, "amf": ["hevc"]}, "amf", False),
    ("auto", {**NONE_HW, "qsv": ["hevc"]}, "qsv", False),
    ("auto", NONE_HW, "cpu", False),
    ("qsv", ALL, "qsv", False),
    ("qsv", {**NONE_HW, "amf": ["hevc"]}, "amf", True),   # נבחר Intel ואין - AMD, עם הודעה
    ("nvenc", NONE_HW, "cpu", True),
])
def test_resolve_backend(requested, available, expected, warns):
    backend, note = encoders.resolve_backend(requested, "hevc", available)
    assert backend == expected
    assert bool(note) == warns


def test_av1_falls_back_when_the_card_only_does_hevc():
    assert encoders.resolve_backend("auto", "av1", {**NONE_HW, "amf": ["hevc"]})[0] == "cpu"


def test_the_setting_env_beats_the_file_and_the_default_is_auto(tmp_path, monkeypatch):
    path = str(tmp_path / "encoder_settings.json")
    monkeypatch.delenv(encoders.ENV_VAR, raising=False)
    assert encoders.load_setting(path) == "auto"
    encoders.save_setting("qsv", path)
    assert json.loads(open(path, encoding="utf-8").read()) == {"backend": "qsv"}
    assert encoders.load_setting(path) == "qsv"
    monkeypatch.setenv(encoders.ENV_VAR, "amf")
    assert encoders.load_setting(path) == "amf"
    monkeypatch.setenv(encoders.ENV_VAR, "bogus")
    assert encoders.load_setting(path) == "qsv"
    with pytest.raises(ValueError):
        encoders.save_setting("bogus", path)


def test_detection_probes_every_pair_once_and_then_reads_the_cache(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"fake")
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(tmp_path / "ws"))
    calls = []

    def fake_probe(exe, args, flags):
        calls.append(args[1])
        return args[1] in ("hevc_amf", "libx265", "libsvtav1")

    monkeypatch.setattr(encoders, "_probe", fake_probe)
    monkeypatch.setattr(encoders, "_gpu_signature", lambda: "Card A@1.0")
    first = encoders.detect_backends(str(ffmpeg))
    assert first == {"nvenc": [], "amf": ["hevc"], "qsv": [], "cpu": ["hevc", "av1"]}
    assert len(calls) == 9                       # 6 בכרטיס, libx265, ושני מקודדי ה-AV1 של ה-CPU
    assert encoders.detect_backends(str(ffmpeg)) == first and len(calls) == 9
    ffmpeg.write_bytes(b"a newer ffmpeg")      # ffmpeg אחר - בודקים שוב
    encoders.detect_backends(str(ffmpeg))
    assert len(calls) == 18
    # 2.0.1: דרייבר חדש או כרטיס אחר - בודקים שוב; והכפתור "בדוק את הכרטיס" (use_cache=False) בודק תמיד
    monkeypatch.setattr(encoders, "_gpu_signature", lambda: "Card A@2.0")
    encoders.detect_backends(str(ffmpeg))
    assert len(calls) == 27
    encoders.detect_backends(str(ffmpeg), use_cache=False)
    assert len(calls) == 36


def test_a_probe_that_timed_out_is_not_remembered(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"fake")
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setattr(encoders, "_gpu_signature", lambda: "")
    busy = {"on": True}
    calls = []

    def fake_probe(exe, args, flags):
        calls.append(args[1])
        if args[1] == "hevc_nvenc":
            return None if busy["on"] else True      # None = הזמן נגמר (מחשב עמוס), לא "אין כרטיס"
        return args[1] == "libx265"

    monkeypatch.setattr(encoders, "_probe", fake_probe)
    assert encoders.detect_backends(str(ffmpeg))["nvenc"] == []
    busy["on"] = False
    assert encoders.detect_backends(str(ffmpeg))["nvenc"] == ["hevc"]    # לא נשמר "אין NVIDIA" לתמיד
    assert len(calls) == 18
    encoders.detect_backends(str(ffmpeg))
    assert len(calls) == 18                                               # תשובה מלאה - נשמרה


def test_av1_on_the_cpu_uses_the_encoder_this_ffmpeg_has(tmp_path, monkeypatch):
    # ה-build שהחבילה מביאה (essentials) בלי libsvtav1 - שם AV1 ב-CPU הוא libaom-av1
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"essentials")
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setattr(encoders, "_gpu_signature", lambda: "")
    monkeypatch.setattr(encoders, "_cpu_av1", "libsvtav1")
    seen = {}

    def fake_probe(exe, args, flags):
        seen[args[1]] = args
        return args[1] in ("libx265", "libaom-av1")

    monkeypatch.setattr(encoders, "_probe", fake_probe)
    assert encoders.detect_backends(str(ffmpeg))["cpu"] == ["hevc", "av1"]
    assert seen["libaom-av1"][:2] == ["-c:v", "libaom-av1"] and seen["libsvtav1"][:2] == ["-c:v", "libsvtav1"]
    assert encoders.encoder_name("av1", "cpu") == "libaom-av1"
    assert encoders.codec_args("av1", "cpu", preset="p5", cq=30) == ["-c:v", "libaom-av1", "-cpu-used", "4", "-row-mt", "1", "-crf", "30", "-b:v", "0"]
    assert encoders.bitrate_args("av1", "cpu", 3000) == ["-c:v", "libaom-av1", "-cpu-used", "4", "-row-mt", "1", "-b:v", "3000k"]
    monkeypatch.setattr(encoders, "_cpu_av1", "libsvtav1")
    encoders.detect_backends(str(ffmpeg))                    # מהמטמון - והבחירה חוזרת איתו
    assert encoders.encoder_name("av1", "cpu") == "libaom-av1"


def test_the_probe_runs_the_real_flags_of_each_encoder():
    assert encoders._probe_args("hevc", "amf") == encoders.codec_args("hevc", "amf")
    assert encoders._probe_args("av1", "qsv")[:2] == ["-c:v", "av1_qsv"] and "-global_quality" in encoders._probe_args("av1", "qsv")


def test_av1_on_amd_gets_its_own_quality_scale():
    # av1_amf: QP 0-255. עם הערך של hevc (0-51) הקובץ יצא כמעט בלי דחיסה.
    assert encoders.codec_args("av1", "amf") == ["-c:v", "av1_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", "104", "-qp_p", "104"]
    assert encoders.codec_args("av1", "amf", cq=51)[-1] == "204" and encoders.codec_args("av1", "amf", cq=90)[-1] == "255"
    assert encoders.codec_args("hevc", "amf", cq=30)[-1] == "30"


def test_only_the_environment_variable_skips_the_check(monkeypatch):
    monkeypatch.setenv(encoders.ENV_VAR, "nvenc")
    assert encoders.forced_by_env() == "nvenc"
    monkeypatch.setenv(encoders.ENV_VAR, "bogus")
    assert encoders.forced_by_env() is None
    monkeypatch.delenv(encoders.ENV_VAR)
    assert encoders.forced_by_env() is None


def test_no_ffmpeg_means_no_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(tmp_path / "ws"))
    assert encoders.detect_backends(str(tmp_path / "missing" / "ffmpeg.exe")) is None
