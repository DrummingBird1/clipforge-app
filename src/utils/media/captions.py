# utils/media/captions.py
#
# מתמלל את פס הקול עם faster-whisper ושורף כתוביות לתוך הווידאו (ffmpeg + libass),
# כי רוב הצפייה ב-Shorts/TikTok היא בלי קול. משנה את הקובץ במקום (render לקובץ
# זמני ואז החלפה אטומית), כך שהקורא לא צריך לטפל בנתיב חדש.

import hashlib
import os
import re
import shutil
import subprocess
import tempfile

WHISPER_MODEL_SIZE = "small"
# item 71/72 (102-ההצעות, גל 7): סגנונות כתוביות - classic (הקיים), bold (סגנון
# טיקטוק: מודגש עם קו-מתאר עבה), outline (קו-מתאר בלבד בלי צל), box (רקע כהה
# חצי-שקוף מאחורי הטקסט), karaoke (מילה-מילה, לפי חותמות-זמן של כל מילה).
CAPTION_STYLES = ("classic", "bold", "outline", "box", "karaoke")
WHISPER_MODEL_SIZES = ("tiny", "base", "small", "medium", "large-v3")

SRT_HEADER_INVALID_CHARS = ["\\", "'"]

# item: עיצוב כתוביות - מיקום נבחר מדבר עם ASS Alignment (מספרי הנומפאד,
# ראו תיעוד libass) - רק שלושת המיקומים הכי שימושיים לכתוביות (לא כל 9
# האפשרויות של ASS, שרובן לא הגיוניות לכתוביות רגילות).
_POSITION_TO_ALIGNMENT = {"bottom": 2, "top": 8, "center": 5}


def _hex_to_ass_color(hex_color):
    """ממיר צבע hex רגיל (RGB, עם/בלי '#', למשל "#FFFF00") לפורמט צבע ASS
    (&HAABBGGRR - סדר בתים הפוך, alpha=00 קבוע = אטום) - כדי לחשוף צבע
    כתוביות כ-hex רגיל/מוכר ב-CLI, במקום לדרוש מהמשתמש להקליד את הפורמט
    ההפוך-בתים הלא-אינטואיטיבי של ASS ידנית. ValueError על קלט לא תקין."""
    text = hex_color.strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"צבע hex לא תקין (צריך בדיוק 6 ספרות): {hex_color!r}")
    r, g, b = text[0:2], text[2:4], text[4:6]
    try:
        int(r, 16), int(g, 16), int(b, 16)
    except ValueError:
        raise ValueError(f"צבע hex לא תקין: {hex_color!r}")
    return f"&H00{b}{g}{r}".upper()


def _position_to_alignment(position):
    """ValueError עם רשימת האפשרויות התקינות על מיקום לא מוכר - עדיף כישלון
    מיידי וברור מאשר ffmpeg שנכשל מאוחר יותר עם שגיאת force_style עמומה."""
    try:
        return _POSITION_TO_ALIGNMENT[position]
    except KeyError:
        raise ValueError(f"מיקום כתוביות לא מוכר: {position!r} (אפשרויות: {', '.join(_POSITION_TO_ALIGNMENT)})")


def build_caption_force_style(font_name="Arial", font_size=16, font_color="#FFFFFF", position="bottom", style="classic"):
    """מחרוזת force_style של libass לכתוביות - מקור-אמת יחיד לשריפה האמיתית
    (burn_captions) ולכתובית-לדוגמה בתצוגה המקדימה של עורך-העל (item 40, גל 4
    של 102-ההצעות) - כדי שהתצוגה המקדימה תראה בדיוק את אותו עיצוב. style (גל 7)
    מוסיף וריאציות; "classic" זהה בדיוק למחרוזת המקורית."""
    alignment = _position_to_alignment(position)
    ass_color = _hex_to_ass_color(font_color)
    if style not in CAPTION_STYLES:
        raise ValueError(f"סגנון כתוביות לא מוכר: {style!r} (אפשרויות: {', '.join(CAPTION_STYLES)})")
    head = f"FontName={font_name},FontSize={font_size},PrimaryColour={ass_color}"
    tail = f"Alignment={alignment},MarginV=60"
    if style == "bold":
        return f"{head},Bold=1,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,{tail}"
    if style == "outline":
        return f"{head},OutlineColour=&H00000000,BorderStyle=1,Outline=4,Shadow=0,{tail}"
    if style == "box":
        return f"{head},OutlineColour=&H80000000,BackColour=&H80000000,BorderStyle=3,Outline=6,Shadow=0,{tail}"
    if style == "karaoke":
        # \kf ממלא מ-SecondaryColour (לבן) ל-PrimaryColour (צבע ההדגשה) מילה-מילה.
        return f"{head},SecondaryColour=&H00FFFFFF,Bold=1,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,{tail}"
    return f"{head},OutlineColour=&H00000000,BorderStyle=1,Outline=2,{tail}"


def edited_captions_path(captions_dir, source_video_path):
    """item 70 (עורך תמלול): נתיב התמלול הערוך לקובץ-מקור - לפי sha1 של הנתיב
    המלא (לא שם-הקובץ בלבד - שני קבצים באותו שם בתיקיות שונות לא יתנגשו).
    אותה פונקציה בדיוק בשרת הווב (שכותב) ובסקריפט (שקורא)."""
    key = hashlib.sha1(os.path.normcase(os.path.abspath(source_video_path)).encode("utf-8")).hexdigest()
    return os.path.join(captions_dir, key + ".srt")


def write_srt(segments, srt_path):
    """segments: [{start, end, text}] -> קובץ SRT (שורות ריקות מדולגות)."""
    with open(srt_path, "w", encoding="utf-8") as f:
        index = 1
        for seg in segments:
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            f.write(f"{index}\n{_format_srt_timestamp(float(seg['start']))} --> {_format_srt_timestamp(float(seg['end']))}\n{text}\n\n")
            index += 1


_SRT_TIME_RE = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")


def _parse_srt_time(text):
    match = _SRT_TIME_RE.search(text)
    if not match:
        raise ValueError(f"זמן SRT לא תקין: {text!r}")
    h, m, s_, ms = match.groups()
    return int(h) * 3600 + int(m) * 60 + int(s_) + int(ms.ljust(3, "0")) / 1000


def parse_srt(text):
    """תוכן SRT -> [{start, end, text}] (לעורך התמלול בווב)."""
    segments = []
    for block in re.split(r"\r?\n\s*\r?\n", text.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        timing_index = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if timing_index is None:
            continue
        start_text, end_text = lines[timing_index].split("-->", 1)
        segments.append({"start": _parse_srt_time(start_text), "end": _parse_srt_time(end_text), "text": "\n".join(lines[timing_index + 1:])})
    return segments


def srt_to_vtt(srt_text):
    """SRT -> WebVTT (item 69): כותרת WEBVTT, נקודה במקום פסיק בחותמות-הזמן, בלי מספרי-קיו."""
    out = ["WEBVTT", ""]
    for seg in parse_srt(srt_text):
        out.append(f"{_format_srt_timestamp(seg['start']).replace(',', '.')} --> {_format_srt_timestamp(seg['end']).replace(',', '.')}")
        out.append(seg["text"])
        out.append("")
    return "\n".join(out)


def _format_ass_timestamp(seconds):
    cs = int(round(max(0.0, seconds) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s_, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s_:02d}.{cs:02d}"


def write_karaoke_ass(segments, ass_path):
    """item 71 (karaoke): קובץ ASS שבו כל מילה מקבלת תג \\kf באורך המילה שלה
    (מחותמות-הזמן לכל מילה של Whisper), כך שהמילה "נצבעת" בדיוק כשהיא נאמרת.
    הסגנון עצמו (גופן/צבע/מיקום) מגיע מ-force_style בזמן השריפה."""
    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 384", "PlayResY: 288", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Arial,16,&H0000FFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,3,1,2,10,10,60,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for seg in segments:
        words = seg.get("words") or []
        if words:
            parts = []
            for word in words:
                duration_cs = max(1, int(round((float(word["end"]) - float(word["start"])) * 100)))
                parts.append(f"{{\\kf{duration_cs}}}{str(word['word']).strip()} ")
            text = "".join(parts).strip()
        else:
            text = str(seg.get("text", "")).strip()
        if text:
            lines.append(f"Dialogue: 0,{_format_ass_timestamp(float(seg['start']))},{_format_ass_timestamp(float(seg['end']))},Default,,0,0,0,,{text}")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def escape_subtitles_path(path):
    """ffmpeg's subtitles filter דורש escaping לנתיב Windows (":" ו-"\\")."""
    return path.replace("\\", "/").replace(":", "\\:")


def write_sample_srt(srt_path, text, duration_seconds):
    """קובץ SRT עם כתובית אחת לאורך כל duration_seconds - לתצוגה מקדימה בלבד
    (תמלול Whisper אמיתי איטי מדי בשביל פריים בודד)."""
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(f"1\n{_format_srt_timestamp(0)} --> {_format_srt_timestamp(max(1.0, duration_seconds))}\n{text}\n\n")


def _format_srt_timestamp(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def transcribe_segments(video_path, translate_to_english=False, language=None, model_size=None, word_timestamps=False):
    """תמלול Whisper -> [{start, end, text, words:[{start, end, word}]}]. משמש
    את השריפה וגם את עורך התמלול בווב (item 70). language=None = זיהוי אוטומטי;
    word_timestamps (karaoke) מבקש חותמת-זמן לכל מילה."""
    from faster_whisper import WhisperModel

    # "cpu" בכוונה, לא "auto"/"cuda": NVENC (רינדור) וה-cuBLAS/cuDNN הדרושים ל-CTranslate2
    # הם ערימות ריצה שונות של NVIDIA - מחשב עם NVENC תקין יכול עדיין לא להחזיק את
    # ה-DLLs הדרושים ל-GPU inference, וזה נכשל בצורה לא ברורה. CPU עם מודל "small"
    # מהיר מספיק לקליפים קצרים ותמיד עובד.
    model = WhisperModel(model_size or WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    # task="translate" הוא היכולת המובנית של Whisper עצמו - מתרגם מכל שפת-מקור
    # שזוהתה ל**אנגלית בלבד** (לא כל שפת-יעד; זו המגבלה של Whisper, לא שלנו) -
    # item: כתוביות באנגלית להרחבת קהל, בלי תלות בשירות תרגום חיצוני נוסף.
    kwargs = {"beam_size": 5, "task": "translate" if translate_to_english else "transcribe"}
    if language:
        kwargs["language"] = language
    if word_timestamps:
        kwargs["word_timestamps"] = True
    segments, _info = model.transcribe(video_path, **kwargs)
    result = []
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        words = [{"start": w.start, "end": w.end, "word": w.word} for w in (getattr(seg, "words", None) or [])]
        result.append({"start": seg.start, "end": seg.end, "text": text, "words": words})
    return result


def _transcribe_to_srt(video_path, srt_path, translate_to_english=False, language=None, model_size=None):
    write_srt(transcribe_segments(video_path, translate_to_english=translate_to_english, language=language, model_size=model_size), srt_path)


def burn_captions(
    video_path, ffmpeg_exe="ffmpeg", translate_to_english=False,
    font_name="Arial", font_size=16, font_color="#FFFFFF", position="bottom",
    video_codec_args=None, hdr_output_args=None,
    style="classic", language=None, model_size=None, export_formats="", burn=True, srt_override_path=None,
):
    """
    style/language/model_size (גל 7, items 71-72): סגנון/שפה/גודל-מודל. export_formats
    ("srt"/"vtt"/"both", item 69) שומר קובץ כתוביות לצד הווידאו; burn=False = רק ייצוא.
    srt_override_path (item 70, עורך תמלול): תמלול ערוך שמחליף את התמלול האוטומטי
    (בלי Whisper בכלל). karaoke עם תמלול ערוך נופל ל-bold (אין חותמות-זמן למילים).

    מתמלל את video_path ושורף כתוביות ישירות לתוכו (משנה במקום). מחזיר את אותו
    נתיב אם הצליח. זורק חריגה אם נכשל - הקורא אמור להתייחס לזה כתכונה אופציונלית.
    translate_to_english=True מתרגם את הכתוביות לאנגלית (task="translate" של
    Whisper עצמו) במקום לתמלל בשפת-המקור כמו שהיא.

    font_name/font_size/font_color/position (item: עיצוב כתוביות) - מותאמים
    אישית במקום סגנון קבוע יחיד. font_color מתקבל כ-hex רגיל (למשל "#FFFF00")
    ומומר ל-ASS פנימית (ראו _hex_to_ass_color). position: "bottom"/"top"/"center".

    video_codec_args/hdr_output_args (item: שימור הגדרות HDR - תיקון) - בלי
    אלה, שריפת הכתוביות (שהיא re-encode נפרד) מקודדת מחדש עם ברירת המחדל
    הגלובלית של ffmpeg (בד"כ libx264/8-bit/SDR) - זה היה דורס בשקט קודק
    hevc_nvenc/av1_nvenc שנבחר לרינדור המקורי, וגם מוחק לגמרי מטא-דאטת HDR
    אם video_path כבר עבר HDR pass-through (נמצא תוך כדי הוספת עיצוב
    הכתוביות - video_editor.py השתמש בפונקציה הזו כבר, בלי לדעת שהיא לא
    שומרת קודק/HDR בכלל). None (ברירת מחדל) משאיר את ההתנהגות הישנה - קוראים
    קיימים שלא מעבירים את זה (rocket_shorts_publisher.py, תמיד h264) לא מושפעים.
    """
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

    with tempfile.TemporaryDirectory() as tmp_dir:
        srt_path = os.path.join(tmp_dir, "captions.srt")
        subtitle_path = srt_path
        effective_style = style
        if srt_override_path:
            shutil.copyfile(srt_override_path, srt_path)
            if style == "karaoke":
                effective_style = "bold"
        elif style == "karaoke":
            segments = transcribe_segments(video_path, translate_to_english=translate_to_english, language=language, model_size=model_size, word_timestamps=True)
            write_srt(segments, srt_path)
            subtitle_path = os.path.join(tmp_dir, "captions.ass")
            write_karaoke_ass(segments, subtitle_path)
        else:
            # kwargs נוספים רק כשבאמת שונים מברירת המחדל - שומר תאימות לקוראים/fakes קיימים
            extra = {}
            if language:
                extra["language"] = language
            if model_size and model_size != WHISPER_MODEL_SIZE:
                extra["model_size"] = model_size
            _transcribe_to_srt(video_path, srt_path, translate_to_english=translate_to_english, **extra)

        if not os.path.exists(srt_path) or os.path.getsize(srt_path) == 0:
            raise RuntimeError("לא זוהה דיבור/טקסט לתמלול בסרטון")

        stem = os.path.splitext(video_path)[0]
        if export_formats in ("srt", "both"):
            shutil.copyfile(srt_path, stem + ".srt")
        if export_formats in ("vtt", "both"):
            with open(srt_path, encoding="utf-8") as src, open(stem + ".vtt", "w", encoding="utf-8") as dst:
                dst.write(srt_to_vtt(src.read()))
        if not burn:
            return video_path

        escaped_srt = escape_subtitles_path(subtitle_path)
        # הפלט הזמני נכתב *ליד* הווידאו, לא ב-tmp_dir: os.replace לא יכול להעביר בין
        # כוננים (%TEMP% ב-C: ו-workspace ב-E: -> WinError 17, והכתוביות לא נשרפו
        # בכלל). אותה סיומת כמו המקור, כדי ש-ffmpeg יבחר את אותו muxer (mkv נשאר mkv).
        video_dir, video_name = os.path.split(os.path.abspath(video_path))
        stem_name, ext = os.path.splitext(video_name)
        temp_output = os.path.join(video_dir, f".{stem_name}.captioning{ext or '.mp4'}")

        style = build_caption_force_style(font_name, font_size, font_color, position, effective_style)
        cmd = [ffmpeg_exe, "-y", "-i", video_path, "-vf", f"subtitles='{escaped_srt}':force_style='{style}'"]
        cmd += list(video_codec_args) if video_codec_args else []
        cmd += ["-c:a", "copy"]
        cmd += list(hdr_output_args) if hdr_output_args else []
        cmd += [temp_output]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NO_WINDOW_FLAGS)

        if result.returncode != 0 or not os.path.exists(temp_output) or os.path.getsize(temp_output) == 0:
            if os.path.exists(temp_output):
                os.remove(temp_output)
            raise RuntimeError(f"שריפת הכתוביות נכשלה: {result.stderr[-500:]}")

        os.replace(temp_output, video_path)

    return video_path
