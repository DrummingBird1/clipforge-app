# tests/bot/test_captions.py
import re
import subprocess
import sys
import threading
from types import SimpleNamespace


import pytest

import utils.media.captions as captions
from tests.scoped_subprocess import fake_subprocess_run, flag_named_files_in_project_root
from utils.media.captions import _format_srt_timestamp, _hex_to_ass_color, _position_to_alignment, burn_captions


@pytest.fixture(autouse=True, scope="module")
def _no_flag_named_files_left_in_the_project_root():
    yield
    assert flag_named_files_in_project_root() == []


def test_format_srt_timestamp_zero():
    assert _format_srt_timestamp(0) == "00:00:00,000"


def test_format_srt_timestamp_with_milliseconds():
    assert _format_srt_timestamp(1.234) == "00:00:01,234"


def test_format_srt_timestamp_crosses_minute_boundary():
    assert _format_srt_timestamp(65.5) == "00:01:05,500"


def test_format_srt_timestamp_crosses_hour_boundary():
    assert _format_srt_timestamp(3661.001) == "01:01:01,001"


def test_burn_captions_raises_when_no_speech_detected(monkeypatch, tmp_path):
    # _transcribe_to_srt "מצליח" אבל לא כותב כלום (אין דיבור מזוהה) - קובץ ה-srt
    # קיים אבל ריק. burn_captions אמור לזהות את זה ולזרוק, לא להמשיך ל-ffmpeg.
    def fake_transcribe(video_path, srt_path, translate_to_english=False):
        open(srt_path, "w", encoding="utf-8").close()

    monkeypatch.setattr(captions, "_transcribe_to_srt", fake_transcribe)
    video_path = str(tmp_path / "clip.mp4")

    with pytest.raises(RuntimeError, match="לא זוהה דיבור"):
        burn_captions(video_path)


def test_burn_captions_raises_when_ffmpeg_fails(monkeypatch, tmp_path):
    def fake_transcribe(video_path, srt_path, translate_to_english=False):
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\nHello\n\n")

    monkeypatch.setattr(captions, "_transcribe_to_srt", fake_transcribe)
    fake_subprocess_run(monkeypatch, captions, lambda *a, **kw: SimpleNamespace(returncode=1, stderr="ffmpeg exploded"))
    video_path = str(tmp_path / "clip.mp4")

    with pytest.raises(RuntimeError, match="שריפת הכתוביות נכשלה"):
        burn_captions(video_path)


def _fake_ffmpeg_run_that_creates_its_output(cmd, **kw):
    # cmd מסתיים בנתיב הפלט (ראו burn_captions) - יוצרים קובץ לא-ריק אמיתי
    # שם, כדי ש-burn_captions's os.path.exists/getsize checks יעברו ו-os.replace
    # בסוף יצליח, בלי להריץ ffmpeg אמיתי.
    with open(cmd[-1], "w", encoding="utf-8") as f:
        f.write("fake video bytes")
    return SimpleNamespace(returncode=0, stderr="")


def test_the_fake_ffmpeg_does_not_catch_other_threads_commands(monkeypatch, tmp_path):
    # נמצא ב-2026-10-02: ה-fake הוחלף על subprocess.run הגלובלי, ודוגם החומרה של אפליקציית
    # הווב (nvidia-smi ... --format=csv,noheader,nounits) קיבל אותו מ-thread אחר וכתב קובץ
    # בשם הדגל בשורש הפרויקט. עכשיו רק burn_captions רואה את ה-fake.
    monkeypatch.chdir(tmp_path)  # אם זה דולף שוב, ה"פלט" נכתב ל-tmp_path ולא לשורש
    flag = "--format=csv,noheader,nounits"
    outputs, sampled = [], {}

    def hardware_sampler():
        sampled["result"] = subprocess.run(
            [sys.executable, "-c", "import sys; print(sys.argv[-1])", flag],
            capture_output=True, text=True, timeout=30,
        )

    def fake_transcribe(video_path, srt_path, translate_to_english=False):
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\nHello\n\n")

    def fake_run(cmd, **kw):
        outputs.append(cmd[-1])
        return _fake_ffmpeg_run_that_creates_its_output(cmd, **kw)

    monkeypatch.setattr(captions, "_transcribe_to_srt", fake_transcribe)
    fake_subprocess_run(monkeypatch, captions, fake_run)
    video_path = str(tmp_path / "clip.mp4")
    open(video_path, "w").close()

    # הדוגם רץ בזמן שה-fake מותקן, אבל לא מתוכו - כך שגם אם זה דולף שוב אין רקורסיה
    # שכותבת לשורש אחרי ש-chdir כבר חזר
    sampler = threading.Thread(target=hardware_sampler)
    sampler.start()
    sampler.join(30)
    burn_captions(video_path)

    assert sampled["result"].returncode == 0
    assert sampled["result"].stdout.strip() == flag  # רץ באמת, לא דרך ה-fake
    assert outputs == [str(tmp_path / ".clip.captioning.mp4")]
    assert not (tmp_path / flag).exists()


def test_burn_captions_passes_translate_to_english_through_to_transcribe(monkeypatch, tmp_path):
    calls = []

    def fake_transcribe(video_path, srt_path, translate_to_english=False):
        calls.append(translate_to_english)
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\nHello\n\n")

    monkeypatch.setattr(captions, "_transcribe_to_srt", fake_transcribe)
    fake_subprocess_run(monkeypatch, captions, _fake_ffmpeg_run_that_creates_its_output)
    video_path = str(tmp_path / "clip.mp4")
    open(video_path, "w").close()

    burn_captions(video_path, translate_to_english=True)

    assert calls == [True]


def test_burn_captions_defaults_translate_to_english_to_false(monkeypatch, tmp_path):
    calls = []

    def fake_transcribe(video_path, srt_path, translate_to_english=False):
        calls.append(translate_to_english)
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\nHello\n\n")

    monkeypatch.setattr(captions, "_transcribe_to_srt", fake_transcribe)
    fake_subprocess_run(monkeypatch, captions, _fake_ffmpeg_run_that_creates_its_output)
    video_path = str(tmp_path / "clip.mp4")
    open(video_path, "w").close()

    burn_captions(video_path)

    assert calls == [False]


def test_transcribe_to_srt_passes_translate_task_to_whisper_model(monkeypatch, tmp_path):
    captured = {}

    class _FakeModel:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, video_path, beam_size, task):
            captured["task"] = task
            return [], None

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=_FakeModel))
    srt_path = str(tmp_path / "out.srt")

    captions._transcribe_to_srt("video.mp4", srt_path, translate_to_english=True)
    assert captured["task"] == "translate"

    captions._transcribe_to_srt("video.mp4", srt_path, translate_to_english=False)
    assert captured["task"] == "transcribe"


# --- עיצוב כתוביות (item) ---

def test_hex_to_ass_color_white():
    assert _hex_to_ass_color("#FFFFFF") == "&H00FFFFFF"


def test_hex_to_ass_color_without_hash_prefix():
    assert _hex_to_ass_color("FFFFFF") == "&H00FFFFFF"


def test_hex_to_ass_color_reverses_byte_order():
    # ASS הוא &HAABBGGRR (BGR הפוך) - אדום טהור (#FF0000) חייב לצאת עם ה-R
    # בסוף, לא בהתחלה.
    assert _hex_to_ass_color("#FF0000") == "&H000000FF"
    assert _hex_to_ass_color("#00FF00") == "&H0000FF00"
    assert _hex_to_ass_color("#0000FF") == "&H00FF0000"


def test_hex_to_ass_color_invalid_length_raises():
    with pytest.raises(ValueError):
        _hex_to_ass_color("#FFF")


def test_hex_to_ass_color_invalid_hex_digits_raise():
    with pytest.raises(ValueError):
        _hex_to_ass_color("#GGGGGG")


def test_position_to_alignment_known_positions():
    assert _position_to_alignment("bottom") == 2
    assert _position_to_alignment("top") == 8
    assert _position_to_alignment("center") == 5


def test_position_to_alignment_unknown_raises():
    with pytest.raises(ValueError, match="מיקום כתוביות לא מוכר"):
        _position_to_alignment("middle-left")


def test_burn_captions_applies_custom_style(monkeypatch, tmp_path):
    captured_cmd = []

    def fake_transcribe(video_path, srt_path, translate_to_english=False):
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\nHello\n\n")

    def fake_run(cmd, **kw):
        captured_cmd.append(cmd)
        return _fake_ffmpeg_run_that_creates_its_output(cmd, **kw)

    monkeypatch.setattr(captions, "_transcribe_to_srt", fake_transcribe)
    fake_subprocess_run(monkeypatch, captions, fake_run)
    video_path = str(tmp_path / "clip.mp4")
    open(video_path, "w").close()

    burn_captions(video_path, font_name="Rubik", font_size=28, font_color="#FF00AA", position="top")

    vf_arg = captured_cmd[0][captured_cmd[0].index("-vf") + 1]
    assert "FontName=Rubik" in vf_arg
    assert "FontSize=28" in vf_arg
    assert "PrimaryColour=&H00AA00FF" in vf_arg  # #FF00AA -> BGR הפוך
    assert "Alignment=8" in vf_arg  # top


def test_burn_captions_passes_through_video_codec_and_hdr_args(monkeypatch, tmp_path):
    # item: שימור הגדרות HDR - תיקון. בלי video_codec_args/hdr_output_args,
    # שריפת כתוביות הייתה דורסת בשקט קודק hevc_nvenc/av1_nvenc ומטא-דאטת HDR
    # שכבר נבחרו לרינדור המקורי (ffmpeg בורר ברירת מחדל, בד"כ libx264/SDR).
    captured_cmd = []

    def fake_transcribe(video_path, srt_path, translate_to_english=False):
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\nHello\n\n")

    def fake_run(cmd, **kw):
        captured_cmd.append(cmd)
        return _fake_ffmpeg_run_that_creates_its_output(cmd, **kw)

    monkeypatch.setattr(captions, "_transcribe_to_srt", fake_transcribe)
    fake_subprocess_run(monkeypatch, captions, fake_run)
    video_path = str(tmp_path / "clip.mp4")
    open(video_path, "w").close()

    burn_captions(
        video_path,
        video_codec_args=["-c:v", "hevc_nvenc", "-preset", "p5", "-cq", "19"],
        hdr_output_args=["-pix_fmt", "p010le", "-color_trc", "smpte2084"],
    )

    cmd = captured_cmd[0]
    assert "-c:v" in cmd and cmd[cmd.index("-c:v") + 1] == "hevc_nvenc"
    assert "-pix_fmt" in cmd and cmd[cmd.index("-pix_fmt") + 1] == "p010le"
    assert "-c:a" in cmd and cmd[cmd.index("-c:a") + 1] == "copy"


def test_burn_captions_without_codec_args_keeps_old_behavior(monkeypatch, tmp_path):
    # None (ברירת מחדל) - שום -c:v מפורש בכלל, בדיוק כמו לפני התיקון (קוראים
    # קיימים שלא מעבירים את הפרמטרים החדשים לא מושפעים).
    captured_cmd = []

    def fake_transcribe(video_path, srt_path, translate_to_english=False):
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\nHello\n\n")

    def fake_run(cmd, **kw):
        captured_cmd.append(cmd)
        return _fake_ffmpeg_run_that_creates_its_output(cmd, **kw)

    monkeypatch.setattr(captions, "_transcribe_to_srt", fake_transcribe)
    fake_subprocess_run(monkeypatch, captions, fake_run)
    video_path = str(tmp_path / "clip.mp4")
    open(video_path, "w").close()

    burn_captions(video_path)

    assert "-c:v" not in captured_cmd[0]


# --- שבירת שורות בכתוביות (max_chars) ---

def test_wrap_caption_text_breaks_at_the_last_space_before_the_limit():
    text = "the quick brown fox jumps over the lazy dog"
    assert captions.wrap_caption_text(text, 15) == "the quick brown\nfox jumps over\nthe lazy dog"
    assert captions.wrap_caption_text("hello world", 11) == "hello world"   # בדיוק על הגבול - לא נשבר
    assert captions.wrap_caption_text("hello world", 10) == "hello\nworld"


def test_wrap_caption_text_is_off_by_default_and_for_zero():
    text = "the quick brown fox jumps over the lazy dog"
    assert captions.wrap_caption_text(text, 0) == text
    assert captions.wrap_caption_text(text, None) == text
    assert captions.wrap_caption_text(text, "abc") == text
    assert captions.wrap_caption_text(text, -5) == text


def test_wrap_caption_text_never_breaks_inside_a_word():
    assert captions.wrap_caption_text("a extraordinarily b", 5) == "a\nextraordinarily\nb"
    assert captions.wrap_caption_text("supercalifragilistic", 5) == "supercalifragilistic"


def test_wrap_caption_text_hebrew_and_english():
    assert captions.wrap_caption_text("זה משפט ארוך בעברית שצריך להישבר", 12) == "זה משפט ארוך\nבעברית שצריך\nלהישבר"
    assert captions.wrap_caption_text("שלום world מה שלומך today", 11) == "שלום world\nמה שלומך\ntoday"


def test_wrap_caption_text_ignores_hebrew_niqqud_when_measuring():
    shalom, olam = "שָׁלוֹם", "עוֹלָם"  # שָׁלוֹם עוֹלָם: 4 אותיות כל אחת
    assert len(f"{shalom} {olam}") > 9
    assert captions.wrap_caption_text(f"{shalom} {olam}", 9) == f"{shalom} {olam}"
    assert captions.wrap_caption_text(f"{shalom} {olam}", 8) == f"{shalom}\n{olam}"


def test_wrap_caption_text_wraps_each_existing_line_separately_and_keeps_short_lines_as_they_are():
    assert captions.wrap_caption_text("ab cd\nef gh ij", 5) == "ab cd\nef gh\nij"
    assert captions.wrap_caption_text("a  b", 10) == "a  b"   # שורה שנכנסת - בלי נגיעה ברווחים


def test_wrap_srt_file_keeps_timing_and_wraps_every_cue(tmp_path):
    src, dst = tmp_path / "in.srt", tmp_path / "out.srt"
    src.write_text("1\n00:00:00,000 --> 00:00:02,500\nthe quick brown fox\n\n2\n00:00:03,000 --> 00:01:04,000\nshort\n\n", encoding="utf-8")
    captions.wrap_srt_file(str(src), str(dst), 10)
    cues = captions.parse_srt(dst.read_text(encoding="utf-8"))
    assert [(cue["start"], cue["end"], cue["text"]) for cue in cues] == [(0.0, 2.5, "the quick\nbrown fox"), (3.0, 64.0, "short")]


def test_karaoke_ass_breaks_the_line_with_an_ass_newline_before_the_word_that_overflows(tmp_path):
    words = [{"start": 0, "end": 0.4, "word": "hi"}, {"start": 0.4, "end": 1, "word": " there"}, {"start": 1, "end": 1.5, "word": "friend"}]
    segment = {"start": 0, "end": 1.5, "text": "hi there friend", "words": words}
    wrapped, plain, fallback = tmp_path / "w.ass", tmp_path / "p.ass", tmp_path / "f.ass"
    captions.write_karaoke_ass([segment], str(wrapped), max_chars=8)
    captions.write_karaoke_ass([segment], str(plain))
    captions.write_karaoke_ass([{"start": 0, "end": 1, "text": "aaa bbb ccc"}], str(fallback), max_chars=7)  # בלי חותמות-זמן למילים
    assert "{\\kf40}hi {\\kf60}there\\N{\\kf50}friend" in wrapped.read_text(encoding="utf-8")
    plain_body = plain.read_text(encoding="utf-8")
    assert "{\\kf40}hi {\\kf60}there {\\kf50}friend" in plain_body and "\\N" not in plain_body
    assert ",aaa bbb\\Nccc" in fallback.read_text(encoding="utf-8")


def _burn_and_capture_burned_srt(monkeypatch, tmp_path, **burn_kwargs):
    seen = {}

    def fake_transcribe(video_path, srt_path, translate_to_english=False):
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:02,000\nthe quick brown fox jumps over\n\n")

    def fake_run(cmd, **kw):
        vf = cmd[cmd.index("-vf") + 1]
        subtitle_path = re.search(r"subtitles='(.*?)':force_style", vf).group(1).replace("\\:", ":")
        with open(subtitle_path, encoding="utf-8") as f:
            seen["burned"] = f.read()
        return _fake_ffmpeg_run_that_creates_its_output(cmd, **kw)

    monkeypatch.setattr(captions, "_transcribe_to_srt", fake_transcribe)
    fake_subprocess_run(monkeypatch, captions, fake_run)
    video_path = str(tmp_path / "clip.mp4")
    open(video_path, "w").close()
    burn_captions(video_path, **burn_kwargs)
    return seen["burned"]


def test_burn_captions_wraps_the_burned_captions_but_not_the_exported_srt(monkeypatch, tmp_path):
    burned = _burn_and_capture_burned_srt(monkeypatch, tmp_path, max_chars=15, export_formats="srt")
    assert "the quick brown\nfox jumps over" in burned
    assert "the quick brown fox jumps over" in (tmp_path / "clip.srt").read_text(encoding="utf-8")  # הייצוא נשאר שלם


def test_burn_captions_without_max_chars_burns_the_text_as_a_single_line(monkeypatch, tmp_path):
    assert "the quick brown fox jumps over" in _burn_and_capture_burned_srt(monkeypatch, tmp_path)
