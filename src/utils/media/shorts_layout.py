# utils/media/shorts_layout.py
#
# 16.11.2026 (ClipForge 2.0): פקודת ffmpeg ל-Short אנכי (1080x1920) מקטע של הקלטה ארוכה:
#   - center: המשחק חתוך למרכז ב-9:16.
#   - facecam: המצלמה למעלה (stream וידאו שני בקובץ - כמו שמסך ההקלטה שומר Facecam) והמשחק למטה. בלי stream מצלמה - center.
#   - punch-in: זום של 25% על המשחק סביב השיא (שנייה לפני ועד שנייה וחצי אחריו), בלי לשנות את גודל הפלט.
#   - שמע: ערוץ המשחק, ואם יש - המיקרופון מעורבב מעליו (כמו --mic-track בסטודיו).
# 17.11.2026 (2.0.1):
#   - cam_track: מסגרת המצלמה עוקבת אחרי הפנים (utils/media/face_track.py) במקום חיתוך למרכז.
#   - slowmo_at: הילוך איטי (חצי מהירות) על השיא - מ-0.3 שניות לפניו ועד 0.7 אחריו, בווידאו ובשמע (atempo שומר על גובה
#     הצליל). ה-Short מתארך בשנייה. הזום על השיא מחושב על הזמן המקורי, ולכן שניהם יושבים על אותו רגע.
# טהור - רק בונה את הפקודה; my_scripts/video/long_to_shorts.py מריץ.
from typing import List, Optional, Tuple

from utils.media import face_track

W, H = 1080, 1920
CAM_H = 608           # בערך שליש עליון (16:9 ברוחב מלא)
GAME_H = H - CAM_H
PUNCH_ZOOM = 0.25
SLOWMO_SPEED = 0.5
SLOWMO_BEFORE, SLOWMO_AFTER = 0.3, 0.7
SLOWMO_MIN = 0.2      # חלון קצר מזה (שיא בקצה הקטע) - בלי הילוך איטי


def _punch(width: int, height: int, peak: Optional[float]) -> str:
    if peak is None:
        return ""
    on = f"between(t\\,{max(0.0, peak - 1.0):.2f}\\,{peak + 1.5:.2f})"
    return (f",scale=w='trunc({width}*(1+{PUNCH_ZOOM}*{on})/2)*2':h='trunc({height}*(1+{PUNCH_ZOOM}*{on})/2)*2':eval=frame"
            f",crop={width}:{height}:(iw-ow)/2:(ih-oh)/2")


def slowmo_window(duration: float, peak: Optional[float]) -> Optional[Tuple[float, float]]:
    """(התחלה, סוף) של ההילוך האיטי בשניות מתחילת הקטע, או None."""
    if peak is None:
        return None
    begin, end = max(0.0, peak - SLOWMO_BEFORE), min(duration, peak + SLOWMO_AFTER)
    return (round(begin, 2), round(end, 2)) if end - begin >= SLOWMO_MIN else None


def _slowmo(source: str, out: str, window: Tuple[float, float], duration: float, audio: bool) -> List[str]:
    """חותך את source לשלושה חלקים (לפני, איטי, אחרי), מאט את האמצעי ומחבר ל-out. חלק ריק בקצה לא נוצר."""
    begin, end = window
    trim, pts, split, kind = ("atrim", "asetpts", "asplit", "v=0:a=1") if audio else ("trim", "setpts", "split", "v=1:a=0")
    slow = f"atempo={SLOWMO_SPEED:g}" if audio else f"setpts=PTS/{SLOWMO_SPEED:g}"
    parts = []
    if begin > 0.05:
        parts.append(f"{trim}=end={begin:.2f},{pts}=PTS-STARTPTS")
    parts.append(f"{trim}=start={begin:.2f}:end={end:.2f},{pts}=PTS-STARTPTS,{slow}")
    if end < duration - 0.05:
        parts.append(f"{trim}=start={end:.2f},{pts}=PTS-STARTPTS")
    tag = "sa" if audio else "sv"
    if len(parts) == 1:
        return [f"{source}{parts[0]}{out}"]
    ins = [f"[{tag}{i}]" for i in range(len(parts))]
    outs = [f"[{tag}{i}o]" for i in range(len(parts))]
    return ([f"{source}{split}={len(parts)}{''.join(ins)}"] + [f"{ins[i]}{part}{outs[i]}" for i, part in enumerate(parts)]
            + [f"{''.join(outs)}concat=n={len(parts)}:{kind}{out}"])


def build_command(ffmpeg_exe: str, source: str, start: float, duration: float, output: str, layout: str = "center",
                  has_cam: bool = False, punch_at: Optional[float] = None, mic_track: Optional[int] = None,
                  video_args: Optional[List[str]] = None, cam_track: Optional[face_track.Track] = None,
                  slowmo_at: Optional[float] = None, fps: Optional[float] = None, has_audio: bool = True) -> List[str]:
    """punch_at / slowmo_at - שניות מתחילת הקטע (Moment.peak_in_clip), או None. fps - קצב הפריימים של המקור, כדי שהפלט
    יישאר בקצב קבוע אחרי ההילוך האיטי. has_audio=False - מקור בלי שמע (אז ההילוך האיטי על הווידאו בלבד)."""
    facecam = layout == "facecam" and has_cam
    window = slowmo_window(duration, slowmo_at)
    video_out = "[vl]" if window else "[v]"
    if facecam:
        cam = (face_track.crop_filter(cam_track, W, CAM_H) if cam_track
               else f"scale={W}:{CAM_H}:force_original_aspect_ratio=increase,crop={W}:{CAM_H}")
        graph = [f"[0:v:1]{cam}[cam]",
                 f"[0:v:0]scale=-2:{GAME_H},crop={W}:{GAME_H}{_punch(W, GAME_H, punch_at)}[game]",
                 f"[cam][game]vstack,format=yuv420p{video_out}"]
    else:
        graph = [f"[0:v:0]scale=-2:{H},crop={W}:{H}{_punch(W, H, punch_at)},format=yuv420p{video_out}"]
    if window:
        graph += _slowmo("[vl]", "[vs]" if fps else "[v]", window, duration, audio=False)
        if fps:
            graph.append(f"[vs]fps={fps:g}[v]")
    maps = ["-map", "[v]"]
    if mic_track is not None:
        mixed = "[am]" if window else "[a]"
        graph.append(f"[0:a:0][0:a:{mic_track}]amix=inputs=2:duration=first:dropout_transition=0:normalize=0{mixed}")
        if window:
            graph += _slowmo("[am]", "[a]", window, duration, audio=True)
        maps += ["-map", "[a]"]
    elif window and has_audio:
        graph += _slowmo("[0:a:0]", "[a]", window, duration, audio=True)
        maps += ["-map", "[a]"]
    elif has_audio:
        maps += ["-map", "0:a:0?"]
    return ([ffmpeg_exe, "-hide_banner", "-y", "-ss", f"{start:.2f}", "-t", f"{duration:.2f}", "-i", source,
             "-filter_complex", ";".join(graph)] + maps
            + list(video_args or ["-c:v", "libx264", "-preset", "medium", "-crf", "20"])
            + ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", output])
