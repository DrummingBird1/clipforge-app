# dataviz/captions.py
#
# גל 42: כתוביות לסרטון נתונים - מחושבות מהתכנית (plan.py) בלי לצייר כלום: כל כרטיס אירוע וכל
# התראת "שיא חדש" הם קטע עם זמן התחלה וסוף, בדיוק בפריימים שבהם הם על המסך. מכאן נכתב קובץ SRT
# ליד הסרטון, ומכאן גם הקריינות (narration.py) יודעת מתי להקריא כל אירוע.

import os
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

Span = Dict[str, Any]   # {"kind": event/record/intro, "start": שניות, "end": שניות, "text": ..., "label": ...}


def _runs(plan: Sequence[Mapping[str, Any]], key: str) -> List[Dict[str, Any]]:
    """רצפים של פריימים עם אותו כרטיס / אותה התראה: (התחלה, סוף, הערך)."""
    runs: List[Dict[str, Any]] = []
    for index, frame in enumerate(plan):
        value = frame.get(key)
        if key == "hold":   # פריים קפוא: אותו פרק / אותה עצירה (בלי t, שמשתנה בכל פריים)
            ident = (value.get("kind"), value.get("title") or value.get("text")) if value else None
        else:
            ident = (value[0], value[1]) if key == "card" and value else (value[0] if value else None)
        if ident is None:
            continue
        if runs and runs[-1]["id"] == ident and runs[-1]["end"] == index:
            runs[-1]["end"] = index + 1
        else:
            runs.append({"id": ident, "start": index, "end": index + 1, "value": value})
    return runs


def caption_spans(plan: Sequence[Mapping[str, Any]], fps: float, *, events: bool = True, records: bool = True,
                  intro: bool = False, intro_text: str = "", chapters: bool = True) -> List[Span]:
    """הקטעים של הכתוביות, לפי הזמן בסרטון. chapters (גל 50): כרטיס הכותרת של כל פרק בתוך הסרטון."""
    fps = float(fps) or 1.0
    spans: List[Span] = []
    if intro and intro_text:
        intro_frames = [i for i, f in enumerate(plan) if f.get("k") == "intro"]
        if intro_frames:   # גל 50: הפתיח לא תמיד בהתחלה (טיזר לפניו)
            spans.append({"kind": "intro", "start": intro_frames[0] / fps, "end": (intro_frames[-1] + 1) / fps,
                          "text": intro_text, "label": intro_text})
    if chapters:
        for run in _runs(plan, "hold"):
            hold = run["value"]
            if hold.get("kind") == "chapter":
                text = " - ".join(t for t in (hold.get("title"), hold.get("subtitle")) if t)
                spans.append({"kind": "chapter", "start": run["start"] / fps, "end": run["end"] / fps, "text": text,
                              "label": str(hold.get("title") or "")})
    if events:
        for run in _runs(plan, "card"):
            label, date = run["value"][0], run["value"][1]
            spans.append({"kind": "event", "start": run["start"] / fps, "end": run["end"] / fps,
                          "text": f"{label} ({date})", "label": str(label)})
    for index, frame in enumerate(plan):   # 20.10.2026: תסריט קריינות (story.script)
        for text in frame.get("say") or []:
            spans.append({"kind": "script", "start": index / fps, "end": index / fps + 3.0, "text": text, "label": text})
    if records:
        for run in _runs(plan, "toast"):
            text = str(run["value"][0])
            spans.append({"kind": "record", "start": run["start"] / fps, "end": run["end"] / fps, "text": text, "label": text})
    spans.sort(key=lambda s: (s["start"], s["kind"]))
    return spans


def episode_spans(config: Mapping[str, Any], plan: Sequence[Mapping[str, Any]], *, settings: Optional[Mapping[str, Any]] = None) -> List[Span]:
    """הקטעים לפי ההגדרות של הפרק (captions.*), או לפי settings (למשל של הקריינות)."""
    options = dict(settings if settings is not None else config.get("captions") or {})
    intro = config.get("intro") or {}
    intro_text = " - ".join(t for t in (intro.get("title") or config.get("title", ""), intro.get("question", "")) if t)
    return caption_spans(plan, float(config["video"]["fps"]), events=bool(options.get("events", True)),
                         records=bool(options.get("records", True)), intro=bool(options.get("intro", False)), intro_text=intro_text)


def _timestamp(seconds: float) -> str:
    millis = int(round(max(0.0, seconds) * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def to_srt(spans: Sequence[Span]) -> str:
    """טקסט SRT (UTF-8). קטעים חופפים (כרטיס ושיא באותו זמן) נשארים חופפים - נגנים מציגים את שניהם."""
    blocks = []
    for number, span in enumerate(spans, start=1):
        text = " ".join(str(span["text"]).split())
        blocks.append(f"{number}\n{_timestamp(span['start'])} --> {_timestamp(span['end'])}\n{text}\n")
    return "\n".join(blocks)


def srt_path(video_path: str) -> str:
    return os.path.splitext(video_path)[0] + ".srt"


def write_srt(video_path: str, spans: Sequence[Span]) -> str:
    """כותב <שם>.srt ליד הסרטון (BOM של UTF-8 - נגנים ב-Windows מזהים עברית)."""
    path = srt_path(video_path)
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(to_srt(spans))
    return path


# ---------- גל 55: פרקים ביוטיוב ----------
# יוטיוב מציג פרקים כשבתיאור יש לפחות 3 חותמות זמן, הראשונה 0:00, וכל פרק לפחות 10 שניות. הפרקים נגזרים מהתכנית:
# הפתיח, כל פרק של הסיפור וכל כרטיס אירוע - פרק שמתחיל פחות מ-10 שניות אחרי הקודם מתאחד איתו.
YOUTUBE_MIN_CHAPTER = 10.0


def youtube_chapters(config: Mapping[str, Any], plan: Sequence[Mapping[str, Any]], offset: float = 0.0) -> List[Tuple[float, str]]:
    """[(שנייה, שם)] לתיאור ביוטיוב, או [] כשיוצאים פחות מ-3 פרקים. offset = אינטרו מקליפ שנוסף לפני הסרטון."""
    fps = float(config["video"]["fps"]) or 1.0
    intro = config.get("intro") or {}
    candidates: List[Tuple[float, str]] = [(0.0, str(intro.get("title") or config.get("title") or ""))]
    for span in caption_spans(plan, fps, events=True, records=False, chapters=True):
        if span["kind"] in ("chapter", "event"):
            candidates.append((span["start"] + offset, str(span["label"])))
    kept: List[Tuple[float, str]] = []
    for start, label in sorted(candidates, key=lambda c: c[0]):
        if not kept or start - kept[-1][0] >= YOUTUBE_MIN_CHAPTER:
            kept.append((start, label))
    end = len(plan) / fps + offset
    while len(kept) > 1 and end - kept[-1][0] < YOUTUBE_MIN_CHAPTER:
        kept.pop()
    return kept if len(kept) >= 3 else []


def chapter_stamp(seconds: float) -> str:
    whole = int(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def chapters_path(video_path: str) -> str:
    return os.path.splitext(video_path)[0] + ".chapters.txt"


def write_chapters(video_path: str, chapters: Sequence[Tuple[float, str]]) -> str:
    """<שם>.chapters.txt ליד הסרטון - שורה לכל פרק ("1:23 תיאור"), בדיוק כמו שנכנס לתיאור ביוטיוב."""
    path = chapters_path(video_path)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(f"{chapter_stamp(start)} {label}" for start, label in chapters) + "\n")
    return path
