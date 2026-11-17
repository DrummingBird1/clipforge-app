# utils/media/shorts_layout.py
#
# 16.11.2026 (ClipForge 2.0): פקודת ffmpeg ל-Short אנכי (1080x1920) מקטע של הקלטה ארוכה:
#   - center: המשחק חתוך למרכז ב-9:16.
#   - facecam: המצלמה למעלה (stream וידאו שני בקובץ - כמו שמסך ההקלטה שומר Facecam) והמשחק למטה. בלי stream מצלמה - center.
#   - punch-in: זום של 25% על המשחק סביב השיא (שנייה לפני ועד שנייה וחצי אחריו), בלי לשנות את גודל הפלט.
#   - שמע: ערוץ המשחק, ואם יש - המיקרופון מעורבב מעליו (כמו --mic-track בסטודיו).
# טהור - רק בונה את הפקודה; my_scripts/video/long_to_shorts.py מריץ.
from typing import List, Optional

W, H = 1080, 1920
CAM_H = 608           # בערך שליש עליון (16:9 ברוחב מלא)
GAME_H = H - CAM_H
PUNCH_ZOOM = 0.25


def _punch(width: int, height: int, peak: Optional[float]) -> str:
    if peak is None:
        return ""
    on = f"between(t\\,{max(0.0, peak - 1.0):.2f}\\,{peak + 1.5:.2f})"
    return (f",scale=w='trunc({width}*(1+{PUNCH_ZOOM}*{on})/2)*2':h='trunc({height}*(1+{PUNCH_ZOOM}*{on})/2)*2':eval=frame"
            f",crop={width}:{height}:(iw-ow)/2:(ih-oh)/2")


def build_command(ffmpeg_exe: str, source: str, start: float, duration: float, output: str, layout: str = "center",
                  has_cam: bool = False, punch_at: Optional[float] = None, mic_track: Optional[int] = None,
                  video_args: Optional[List[str]] = None) -> List[str]:
    """punch_at - שניות מתחילת הקטע (Moment.peak_in_clip), או None."""
    facecam = layout == "facecam" and has_cam
    if facecam:
        graph = [f"[0:v:1]scale={W}:{CAM_H}:force_original_aspect_ratio=increase,crop={W}:{CAM_H}[cam]",
                 f"[0:v:0]scale=-2:{GAME_H},crop={W}:{GAME_H}{_punch(W, GAME_H, punch_at)}[game]",
                 "[cam][game]vstack,format=yuv420p[v]"]
    else:
        graph = [f"[0:v:0]scale=-2:{H},crop={W}:{H}{_punch(W, H, punch_at)},format=yuv420p[v]"]
    maps = ["-map", "[v]"]
    if mic_track is not None:
        graph.append(f"[0:a:0][0:a:{mic_track}]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
        maps += ["-map", "[a]"]
    else:
        maps += ["-map", "0:a:0?"]
    return ([ffmpeg_exe, "-hide_banner", "-y", "-ss", f"{start:.2f}", "-t", f"{duration:.2f}", "-i", source,
             "-filter_complex", ";".join(graph)] + maps
            + list(video_args or ["-c:v", "libx264", "-preset", "medium", "-crf", "20"])
            + ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", output])
