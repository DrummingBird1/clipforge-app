# utils/video/video_editor_post.py
#
# גל 7ב של 102-ההצעות: שלבי עיבוד-אחרי על הפלט הגמור של video_editor.py (אחרי
# שריפת הכתוביות) - intro/outro bumper (81), loop/boomerang (89), פרקים ומטא-דאטה
# (89), וייצוא נוסף ל-GIF/WebP/אודיו-בלבד (89). כל פונקציה כאן בונה פקודת ffmpeg
# (רשימה) או תוכן-קובץ - טהורה ובדיקה בלי ffmpeg; ההרצה עצמה בסקריפט.

import re
from typing import Dict, List, Optional, Sequence, Tuple

EXTRA_VIDEO_EXPORTS: Tuple[str, ...] = ("gif", "webp", "both")
AUDIO_EXPORTS: Dict[str, List[str]] = {
    "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
    "wav": ["-c:a", "pcm_s16le"],
}
BOOMERANG_MAX_SECONDS = 60.0  # reverse מחזיק את כל הקליפ בזיכרון - רק לקליפים קצרים
MAX_LOOP_COUNT = 10


def post_temp_path(output_path: str, step: str) -> str:
    """נתיב זמני *באותה תיקייה* (os.replace בין כוננים נכשל - WinError 17) ובאותה
    סיומת (אותו muxer)."""
    import os
    directory, name = os.path.split(os.path.abspath(output_path))
    stem, ext = os.path.splitext(name)
    return os.path.join(directory, f".{stem}.{step}{ext or '.mp4'}")


def build_bumper_concat_command(
    ffmpeg_exe: str, clips: Sequence[Tuple[str, float, bool]], width: int, height: int, fps: str,
    include_audio: bool, codec_args: Sequence[str], output_path: str,
) -> List[str]:
    """intro + פלט + outro לקובץ אחד. clips: [(path, duration, has_audio)] לפי הסדר.
    כל קטע מותאם לאותן מידות/fps (letterbox, לא מתיחה); קטע בלי שמע מקבל שקט
    באורך שלו כשהפלט עם שמע, כדי ש-concat יקבל זוג v/a מכל קטע."""
    cmd = [ffmpeg_exe, "-y"]
    for path, _duration, _has_audio in clips:
        cmd += ["-i", path]
    parts, labels = [], []
    for i, (_path, duration, has_audio) in enumerate(clips):
        parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[v{i}]"
        )
        labels.append(f"[v{i}]")
        if include_audio:
            if has_audio:
                parts.append(f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
            else:
                parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration:.3f},aformat=sample_fmts=fltp[a{i}]")
            labels.append(f"[a{i}]")
    audio_flag = 1 if include_audio else 0
    parts.append(f"{''.join(labels)}concat=n={len(clips)}:v=1:a={audio_flag}[v]" + ("[a]" if include_audio else ""))
    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]"]
    if include_audio:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    cmd += list(codec_args) + ["-movflags", "+faststart", output_path]
    return cmd


def build_boomerang_command(ffmpeg_exe: str, source: str, has_audio: bool, codec_args: Sequence[str], output_path: str) -> List[str]:
    """קדימה ואז אחורה (boomerang) - כולל השמע (areverse) אם יש."""
    graph = "[0:v]split=2[__f][__r0];[__r0]reverse[__r];[__f][__r]concat=n=2:v=1:a=0[v]"
    maps = ["-map", "[v]"]
    if has_audio:
        graph += ";[0:a]asplit=2[__fa][__ra0];[__ra0]areverse[__ra];[__fa][__ra]concat=n=2:v=0:a=1[a]"
        maps += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    return [ffmpeg_exe, "-y", "-i", source, "-filter_complex", graph, *maps, *codec_args, "-movflags", "+faststart", output_path]


def build_loop_command(ffmpeg_exe: str, source: str, count: int, output_path: str) -> List[str]:
    """חוזר על הפלט count פעמים ברצף - העתקת זרמים בלי קידוד מחדש."""
    count = max(1, min(MAX_LOOP_COUNT, int(count)))
    return [ffmpeg_exe, "-y", "-stream_loop", str(count - 1), "-i", source, "-map", "0", "-c", "copy", "-movflags", "+faststart", output_path]


_CHAPTER_LINE_RE = re.compile(r"^\s*((?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d+)?)\s*[-–—:]?\s*(.+?)\s*$")


def parse_chapters(text: str) -> List[Tuple[float, str]]:
    """"0:00 פתיחה" / "1:02:30 - בוס" (שורה לכל פרק, או מופרדים ב-|) -> [(שניות, כותרת)],
    ממוינים, בלי כפילויות-זמן. שורות לא תקינות מדולגות."""
    chapters: Dict[float, str] = {}
    for line in re.split(r"[\n|]", text or ""):
        match = _CHAPTER_LINE_RE.match(line)
        if not match:
            continue
        seconds = 0.0
        for piece in match.group(1).split(":"):
            seconds = seconds * 60 + float(piece)
        chapters.setdefault(round(seconds, 3), match.group(2)[:120])
    return sorted(chapters.items())


def _escape_ffmetadata(value: str) -> str:
    return re.sub(r"([=;#\\\n])", r"\\\1", value)


def build_ffmetadata(title: str, comment: str, chapters: Sequence[Tuple[float, str]], total_duration: float, offset: float = 0.0) -> str:
    """קובץ FFMETADATA1: כותרת/הערה + פרקים (סוף כל פרק = תחילת הבא / סוף הסרטון).
    offset מזיז את כל הפרקים (למשל אורך ה-intro, שנוסף לפני התוכן)."""
    lines = [";FFMETADATA1"]
    if title.strip():
        lines.append(f"title={_escape_ffmetadata(title.strip())}")
    if comment.strip():
        lines.append(f"comment={_escape_ffmetadata(comment.strip())}")
    shifted = [(start + offset, name) for start, name in chapters if start + offset < total_duration]
    for i, (start, name) in enumerate(shifted):
        end = shifted[i + 1][0] if i + 1 < len(shifted) else total_duration
        if end <= start:
            continue
        lines += ["", "[CHAPTER]", "TIMEBASE=1/1000", f"START={int(start * 1000)}", f"END={int(end * 1000)}", f"title={_escape_ffmetadata(name)}"]
    return "\n".join(lines) + "\n"


def build_metadata_command(ffmpeg_exe: str, source: str, metadata_path: str, output_path: str) -> List[str]:
    return [ffmpeg_exe, "-y", "-i", source, "-i", metadata_path, "-map", "0", "-map_metadata", "1", "-map_chapters", "1",
            "-c", "copy", "-movflags", "+faststart", output_path]


def build_gif_command(ffmpeg_exe: str, source: str, output_path: str, width: int = 480, fps: int = 12) -> List[str]:
    """GIF באיכות טובה: palettegen+paletteuse באותו מעבר (פלטה מותאמת לקליפ)."""
    graph = (f"fps={int(fps)},scale={int(width)}:-2:flags=lanczos,split[__a][__b];"
             "[__a]palettegen=stats_mode=diff[__p];[__b][__p]paletteuse=dither=bayer:bayer_scale=5")
    return [ffmpeg_exe, "-y", "-i", source, "-filter_complex", graph, "-loop", "0", output_path]


def build_webp_command(ffmpeg_exe: str, source: str, output_path: str, width: int = 480, fps: int = 12) -> List[str]:
    return [ffmpeg_exe, "-y", "-i", source, "-vf", f"fps={int(fps)},scale={int(width)}:-2:flags=lanczos",
            "-an", "-c:v", "libwebp", "-lossless", "0", "-q:v", "70", "-loop", "0", output_path]


def build_audio_export_command(ffmpeg_exe: str, source: str, output_path: str, audio_format: str) -> List[str]:
    if audio_format not in AUDIO_EXPORTS:
        raise ValueError(f"פורמט שמע לא מוכר: {audio_format!r} (אפשרויות: {', '.join(AUDIO_EXPORTS)})")
    return [ffmpeg_exe, "-y", "-i", source, "-vn", *AUDIO_EXPORTS[audio_format], output_path]


def extra_export_paths(output_path: str, video_exports: Optional[str], audio_format: Optional[str]) -> Dict[str, str]:
    """{סוג: נתיב} לכל ייצוא נוסף - לצד הפלט, באותו שם."""
    import os
    stem = os.path.splitext(output_path)[0]
    paths: Dict[str, str] = {}
    if video_exports in ("gif", "both"):
        paths["gif"] = stem + ".gif"
    if video_exports in ("webp", "both"):
        paths["webp"] = stem + ".webp"
    if audio_format in AUDIO_EXPORTS:
        paths[audio_format] = f"{stem}.{audio_format}"
    return paths
