# dataviz/narration.py
#
# גל 42: קריינות לסרטון נתונים - כל אירוע (ואם רוצים גם כל "שיא חדש") מוקרא בקול של Windows (SAPI,
# System.Speech דרך PowerShell - בלי חבילות נוספות) בדיוק כשהכרטיס שלו עולה. כל משפט נשמר כ-WAV
# בתיקייה זמנית, ו-ffmpeg מערבב את כולם מעל הסרטון שכבר נוצר (המוזיקה בעוצמה שלה, הקריינות מעליה;
# הווידאו מועתק בלי קידוד מחדש). בלי narration.enabled - שום דבר מזה לא רץ.

import os
import subprocess
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SpeakFn = Callable[[str, str], None]
# גל 45: קריינות מוקלטת - קובץ שמע לאירוע בתיקייה narration.folder, בשם התאריך שלו (2023-10-07.mp3,
# או 2023-10-07_<משהו>.webm - האחרון שנשמר גובר) או בשם האירוע עצמו. בלי הקלטה - קול של Windows (narration.tts).
RECORDING_EXT = (".wav", ".mp3", ".m4a", ".ogg", ".opus", ".webm", ".flac", ".aac")
MAX_LINES = 60
MAX_TEXT = 300

# הטקסט, הקול והקובץ עוברים במשתני סביבה - אף פעם לא כחלק מהפקודה (בלי בעיות של מרכאות ובלי הזרקה)
_SPEAK_PS = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "if ($env:CF_TTS_VOICE) { $s.SelectVoice($env:CF_TTS_VOICE) }; "
    "$s.Rate = [int]$env:CF_TTS_RATE; "
    "$s.SetOutputToWaveFile($env:CF_TTS_OUT); "
    "$s.Speak($env:CF_TTS_TEXT); "
    "$s.Dispose()"
)
_VOICES_PS = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "foreach ($v in $s.GetInstalledVoices()) { if ($v.Enabled) { $v.VoiceInfo.Name + '|' + $v.VoiceInfo.Culture.Name + '|' + $v.VoiceInfo.Gender } }; "
    "$s.Dispose()"
)


def _powershell(script: str, env: Optional[Mapping[str, str]] = None, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                          timeout=timeout, env={**os.environ, **(env or {})}, creationflags=_NO_WINDOW,
                          encoding="utf-8", errors="replace")


def list_voices() -> List[Dict[str, str]]:
    """הקולות המותקנים ב-Windows: [{name, culture, gender}]. מחוץ ל-Windows / בלי SAPI - רשימה ריקה."""
    if os.name != "nt":
        return []
    try:
        result = _powershell("[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + _VOICES_PS, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    voices = []
    for line in (result.stdout or "").splitlines():
        parts = line.strip().split("|")
        if len(parts) == 3 and parts[0]:
            voices.append({"name": parts[0], "culture": parts[1], "gender": parts[2]})
    return voices


def make_sapi_speaker(voice: str = "", rate: int = 0) -> SpeakFn:
    """פונקציה (טקסט, נתיב WAV) שמקריאה בקול של Windows. RuntimeError כשההקראה נכשלה."""
    def speak(text: str, wav_path: str) -> None:
        env = {"CF_TTS_TEXT": text, "CF_TTS_OUT": wav_path, "CF_TTS_VOICE": voice or "", "CF_TTS_RATE": str(int(rate))}
        result = _powershell(_SPEAK_PS, env=env)
        if result.returncode != 0 or not os.path.isfile(wav_path):
            raise RuntimeError("ההקראה נכשלה: " + (result.stderr or "").strip()[:200])
    return speak


def narration_lines(spans: Sequence[Mapping[str, Any]], *, events: bool = True, records: bool = False) -> List[Tuple[float, str]]:
    """(זמן בשניות, מה להקריא) - לאירועים: התווית בלבד (תאריך בהקראה נשמע מסורבל)."""
    kinds = ({"event"} if events else set()) | {"script"}   # 20.10.2026: תסריט קריינות - תמיד מוקרא
    if records:
        kinds.add("record")
    lines = [(float(s["start"]), str(s.get("label") or s["text"]).strip()[:MAX_TEXT]) for s in spans if s.get("kind") in kinds]
    return [(start, text) for start, text in lines if text][:MAX_LINES]


def _safe_stem(text: str) -> str:
    return "".join(c for c in str(text) if c not in '\\/:*?"<>|').strip()[:80]


def find_recording(folder: str, label: str, date: str = "") -> str:
    """ההקלטה של אירוע בתיקייה (לפי התאריך או השם), החדשה ביותר אם יש כמה. ריק = אין."""
    if not folder or not os.path.isdir(folder):
        return ""
    keys = [k for k in (str(date or ""), _safe_stem(label)) if k]
    found = []
    for name in os.listdir(folder):
        stem, ext = os.path.splitext(name)
        if ext.lower() in RECORDING_EXT and any(stem == k or stem.startswith(k + "_") for k in keys):
            path = os.path.join(folder, name)
            found.append((os.path.getmtime(path), path))
    return max(found)[1] if found else ""


def synthesize(lines: Sequence[Tuple[float, str]], out_dir: str, speak: SpeakFn) -> List[Tuple[float, str]]:
    """WAV לכל שורה בתיקייה out_dir: [(זמן, נתיב)]."""
    os.makedirs(out_dir, exist_ok=True)
    clips = []
    for index, (start, text) in enumerate(lines):
        path = os.path.join(out_dir, f"line_{index:03d}.wav")
        speak(text, path)
        clips.append((start, path))
    return clips


def mix_command(ffmpeg: str, video_path: str, clips: Sequence[Tuple[float, str]], out_path: str, *, has_audio: bool,
                volume: float = 1.0, duration: float = 0.0, bitrate: str = "192k") -> List[str]:
    """פקודת ffmpeg שמוסיפה את הקריינות לסרטון: כל קטע מוזז לזמן שלו (adelay) ומעורבב עם המוזיקה בלי
    להנמיך אותה (normalize=0). בלי מוזיקה - הקריינות לבדה, עם שקט עד סוף הסרטון."""
    cmd = [ffmpeg, "-loglevel", "error", "-y", "-i", video_path]
    for _start, path in clips:
        cmd += ["-i", path]
    parts = []
    labels = []
    for k, (start, _path) in enumerate(clips, start=1):
        ms = int(round(max(0.0, start) * 1000))
        parts.append(f"[{k}:a]adelay={ms}|{ms},volume={volume:g}[n{k}]")
        labels.append(f"[n{k}]")
    if has_audio:
        parts.append(f"[0:a]{''.join(labels)}amix=inputs={len(clips) + 1}:duration=first:dropout_transition=0:normalize=0[aout]")
    else:
        parts.append(f"{''.join(labels)}amix=inputs={len(clips)}:duration=longest:dropout_transition=0:normalize=0,apad[aout]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", bitrate]
    if duration > 0:
        cmd += ["-t", f"{duration:.3f}"]
    cmd.append(out_path)
    return cmd


def add_narration(video_path: str, clips: Sequence[Tuple[float, str]], *, ffmpeg: str, has_audio: bool, volume: float = 1.0,
                  duration: float = 0.0, bitrate: str = "192k") -> str:
    """מחליף את הסרטון בגרסה עם קריינות (דרך קובץ זמני - אם ffmpeg נכשל הסרטון המקורי נשאר)."""
    if not clips:
        return video_path
    tmp = os.path.splitext(video_path)[0] + ".narration.tmp.mp4"
    cmd = mix_command(ffmpeg, video_path, clips, tmp, has_audio=has_audio, volume=volume, duration=duration, bitrate=bitrate)
    result = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW)
    if result.returncode != 0 or not os.path.isfile(tmp):
        if os.path.isfile(tmp):
            os.remove(tmp)
        raise RuntimeError("הוספת הקריינות נכשלה: " + result.stderr.decode("utf-8", "replace").strip()[-300:])
    os.replace(tmp, video_path)
    return video_path


def narrate_video(video_path: str, config: Mapping[str, Any], spans: Sequence[Mapping[str, Any]], *, ffmpeg: str,
                  duration: float, speak: Optional[SpeakFn] = None, work_dir: Optional[str] = None,
                  event_dates: Optional[Mapping[str, str]] = None) -> int:
    """כל התהליך לפי narration.* בהגדרות: שורות -> WAV -> ערבוב. מחזיר כמה שורות הוקראו."""
    import shutil
    import tempfile

    settings = config.get("narration") or {}
    lines = narration_lines(spans, events=bool(settings.get("events", True)), records=bool(settings.get("records", False)))
    if not lines:
        return 0
    recordings = os.path.join(str(config.get("base_dir", "")), str(settings["folder"])) if settings.get("folder") else ""
    use_tts = bool(settings.get("tts", True))
    folder = work_dir or tempfile.mkdtemp(prefix="dataviz_narration_")
    try:
        clips, to_speak = [], []
        for start, text in lines:   # גל 45: הקלטה קודמת לקול של Windows
            recorded = find_recording(recordings, text, (event_dates or {}).get(text, ""))
            if recorded:
                clips.append((start, recorded))
            elif use_tts:
                to_speak.append((start, text))
        if to_speak:
            speak = speak or make_sapi_speaker(str(settings.get("voice") or ""), int(settings.get("rate") or 0))
            clips += synthesize(to_speak, folder, speak)
        clips.sort()
        if not clips:
            return 0
        audio = config.get("audio") or {}
        add_narration(video_path, clips, ffmpeg=ffmpeg, has_audio=bool(audio.get("path")), volume=float(settings.get("volume", 1.0)),
                      duration=duration, bitrate=str(audio.get("bitrate", "192k")))
    finally:
        if work_dir is None:
            shutil.rmtree(folder, ignore_errors=True)
    return len(clips)


def track_path(config: Mapping[str, Any]) -> str:
    """27.10.2026: הקלטה רציפה (narration.track) - הנתיב המלא בתיקיית ההקלטות, או "" כשאין / הקובץ חסר."""
    settings = config.get("narration") or {}
    name = str(settings.get("track") or "")
    if not name or not settings.get("folder"):
        return ""
    path = os.path.join(str(config.get("base_dir", "")), str(settings["folder"]), name)
    return path if os.path.isfile(path) else ""


def has_audio_stream(ffmpeg: str, video_path: str) -> bool:
    """האם בקובץ יש פס קול (מה ש-ffmpeg -i מדפיס על הקלטים, בלי לקודד כלום)."""
    result = subprocess.run([ffmpeg, "-hide_banner", "-i", video_path], capture_output=True, creationflags=_NO_WINDOW)
    return b"Audio:" in result.stderr


def narrate_track(video_path: str, config: Mapping[str, Any], *, ffmpeg: str, duration: float, has_audio: Optional[bool] = None) -> bool:
    """27.10.2026: מערבב את ההקלטה הרציפה לסרטון מהשנייה track_start (מעל המוזיקה והקריינות לאירועים, בלי להנמיך אותן).
    False כשאין הקלטה. has_audio - האם בסרטון כבר יש פס קול (None = בודקים בקובץ)."""
    path = track_path(config)
    if not path:
        return False
    if has_audio is None:
        has_audio = has_audio_stream(ffmpeg, video_path)
    settings = config.get("narration") or {}
    audio = config.get("audio") or {}
    add_narration(video_path, [(float(settings.get("track_start") or 0.0), path)], ffmpeg=ffmpeg, has_audio=has_audio,
                  volume=float(settings.get("volume", 1.0)), duration=duration, bitrate=str(audio.get("bitrate", "192k")))
    return True
