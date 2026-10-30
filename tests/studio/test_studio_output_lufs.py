# tests/studio/test_studio_output_lufs.py
#
# 24.10.2026, מנה 7 - החלטת המשתמש מסיור השימושיות בסטודיו: עוצמת השמע (LUFS) של הפלט בתוצאות, רק כשהנרמול דלוק. הערך נלקח
# מהסיכום ש-loudnorm מדפיס בסוף אותו קידוד (print_format=json) ונשמר ב-run manifest (output_lufs, lufs_target) - בלי מעבר
# ffmpeg נוסף. process_video רץ בתוך התהליך עם ffmpeg מדומה (tests/video_editor_golden.py).
from tests.video_editor_golden import run_scenario
from utils.video.video_editor_filtergraph import loudnorm_output_lufs, loudnorm_target_lufs

SUMMARY = ('frame=  300 fps=120 q=-1.0 Lsize=    8000kB time=00:00:10.00\n[Parsed_loudnorm_1 @ 0000012345] \n{\n'
           '\t"input_i" : "-23.54",\n\t"input_tp" : "-4.20",\n\t"output_i" : "-14.10",\n\t"output_tp" : "-1.50",\n'
           '\t"normalization_type" : "dynamic",\n\t"target_offset" : "0.10"\n}\n')


def test_the_loudness_is_read_from_the_summary_of_the_encode():
    assert loudnorm_output_lufs(SUMMARY) == -14.1
    assert loudnorm_output_lufs("frame=  300 fps=120\n") is None
    assert loudnorm_output_lufs('"output_i" : "-inf",') is None                          # שמע שקט
    assert loudnorm_target_lufs(None) == -14.0
    assert loudnorm_target_lufs("loudnorm=I=-16.0:LRA=11:TP=-1.5") == -16.0               # --loudnorm-target


def _render(tmp_path, flags, index, stderr=SUMMARY):
    tmp_path.mkdir()
    loaded = []
    commands = run_scenario({"name": "lufs", "flags": flags}, str(tmp_path), index=index, stderr=stderr, loaded=loaded)
    created = [f for f in loaded[0]._RUN_MANIFEST_FILES if f["status"] == "created"]
    return commands, created


def test_with_loudnorm_the_results_get_the_output_loudness_from_the_same_encode(tmp_path):
    plain, plain_files = _render(tmp_path / "a", ["--keep-audio"], 9701)
    commands, files = _render(tmp_path / "b", ["--keep-audio", "--loudnorm", "--loudnorm-target", "-16"], 9702)
    assert len(commands) == len(plain)                                                    # אותו מספר הרצות ffmpeg - בלי מעבר נוסף
    with_loudnorm = [c for c in commands if any("loudnorm=" in part for part in c)]
    assert len(with_loudnorm) == 1 and any(":print_format=json" in part for part in with_loudnorm[0])
    assert files[0]["output_lufs"] == -14.1 and files[0]["lufs_target"] == -16.0          # קודם: אין
    assert "output_lufs" not in plain_files[0] and "lufs_target" not in plain_files[0]    # בלי נרמול - כמו קודם


def test_without_a_summary_the_file_still_succeeds_and_has_no_loudness(tmp_path):
    # ffmpeg ישן שלא מדפיס את הסיכום, או ריצה שהפלט שלה נקטע - הקובץ נוצר כרגיל, בלי שורת LUFS ובלי כישלון
    for index, stderr in enumerate(("frame=  300 fps=120 q=-1.0 Lsize= 8000kB\n", '{\n\t"output_i" : "-inf",\n}\n', "")):
        _commands, files = _render(tmp_path / str(index), ["--keep-audio", "--loudnorm"], 9710 + index, stderr=stderr)
        assert files and files[0]["status"] == "created" and "output_lufs" not in files[0], stderr
