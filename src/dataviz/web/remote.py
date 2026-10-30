# dataviz/web/remote.py (עד 19.10.2026: utils/dataviz_remote.py)
#
# גל 52: מקורות נתונים מכתובת (קובץ CSV / JSON / Excel ברשת, או Google Sheets משותף) לפרק בעורך הגרפים.
# ההורדה קורית רק כשהמשתמש לוחץ "רענן נתונים", או במשימה מתוזמנת שהוא יצר (dataviz_maker.py --refresh-data) -
# אף פעם לא לבד. העותק נשמר תחת data/dataviz_cache/<פרק>/ (קובץ של האפליקציה, לא בתיקיית הפרק), ולצידו מצב
# (טביעת הקובץ וזמן) - כך ש"השתנה מאז הפעם הקודמת" ידוע, וריצה מתוזמנת יכולה לדלג כשאין חדש.
# הוספת מקור מכתובת כותבת רק לקובץ השינויים של הפרק (data/dataviz_overrides) - config.yaml לא משתנה.

import copy
import hashlib
import json
import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Mapping, Optional

from dataviz.web import episodes as de
from utils.shared import data_paths

CACHE_DIRNAME = data_paths.DATAVIZ_CACHE
STATE_NAME = "state.json"
REMOTE_MAX_BYTES = 20 * 1024 * 1024
_SHEET_RE = re.compile(r"^https://docs\.google\.com/spreadsheets/d/([\w-]+)")
_GID_RE = re.compile(r"[#&?]gid=(\d+)")


def cache_dir(data_dir: str, episode: str) -> str:
    return os.path.join(data_dir, CACHE_DIRNAME, episode)


def download_url(url: str) -> str:
    """הכתובת שממנה מורידים: קישור לגיליון Google Sheets הופך לייצוא CSV של אותה לשונית; אחר - כמו שהוא."""
    match = _SHEET_RE.match(url)
    if not match:
        return url
    gid = _GID_RE.search(url)
    return f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv" + (f"&gid={gid.group(1)}" if gid else "")


def _check_url(url: str) -> str:
    url = str(url or "").strip()
    if not url.startswith(("https://", "http://")) or len(url) > 2000 or any(c.isspace() for c in url):
        raise de.EpisodeError("כתובת לא תקינה - צריכה להתחיל ב-https:// (או http://).")
    return url


def _state_path(data_dir: str, episode: str) -> str:
    return os.path.join(cache_dir(data_dir, episode), STATE_NAME)


def load_state(data_dir: str, episode: str) -> Dict[str, Any]:
    try:
        with open(_state_path(data_dir, episode), "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def _write_atomic(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)   # safe: עותק של מקור מכתובת / קובץ המצב שלו, תחת data/dataviz_cache - קבצים של האפליקציה


def _config(data_dir: str, episode: str) -> Dict[str, Any]:
    from dataviz.config import ConfigError, load_config
    folder = de.episode_folder(data_dir, episode)
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    try:
        # בלי בדיקת הקבצים: מקור מכתובת שעוד לא הורד הוא בדיוק מה שבא להוריד
        return load_config(os.path.join(folder, "config.yaml"), de.load_overrides_for_path(folder))
    except ConfigError:
        import yaml

        from dataviz.config import DEFAULTS, merge
        with open(os.path.join(folder, "config.yaml"), "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        config = merge(DEFAULTS, merge(raw, de.load_overrides_for_path(folder)))
        config["base_dir"] = folder
        return config


def _ensure_cache_dir(data_dir: str, episode: str, config: Mapping[str, Any]) -> str:
    """הפרק מפנה לתיקיית העותקים שלו (data.cache_dir) - ההורדה לעולם לא כותבת לתיקיית הפרק."""
    folder = os.path.abspath(cache_dir(data_dir, episode))
    if (config.get("data") or {}).get("cache_dir") != folder:
        overrides = de.load_overrides_for_path(de.episode_folder(data_dir, episode) or "")
        de._set_path(overrides, "data.cache_dir", folder)
        de._write_overrides(data_dir, episode, de.episode_folder(data_dir, episode) or "", overrides, check=False)
    return folder


def refresh_sources(data_dir: str, episode: str, opener: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    """מוריד מחדש כל מקור מכתובת של הפרק. {"sources": [{url, changed, bytes, at, error?}], "changed": האם משהו השתנה}."""
    from dataviz.sources import url_cache_path
    config = _config(data_dir, episode)
    remote = [spec for spec in config.get("sources") or [] if spec.get("url") and not spec.get("path")]
    if not remote:
        return {"sources": [], "changed": False}
    folder = _ensure_cache_dir(data_dir, episode, config)
    config = dict(config, data=dict(config.get("data") or {}, cache_dir=folder))
    if opener is None:
        import urllib.request

        def opener(url: str) -> Any:
            request = urllib.request.Request(url, headers={"User-Agent": "ClipForge dataviz"})
            return urllib.request.urlopen(request, timeout=30)
    state = load_state(data_dir, episode)
    results: List[Dict[str, Any]] = []
    for spec in remote:
        url = _check_url(spec["url"])
        entry: Dict[str, Any] = {"url": url}
        try:
            with opener(download_url(url)) as response:
                raw = response.read(REMOTE_MAX_BYTES + 1)
            if len(raw) > REMOTE_MAX_BYTES:
                raise ValueError("הקובץ גדול מ-20MB")
            if not raw.strip():
                raise ValueError("הקובץ ריק")
        except (OSError, ValueError) as e:
            entry.update({"changed": False, "error": str(e)[:200]})
            results.append(entry)
            continue
        digest = hashlib.sha256(raw).hexdigest()
        previous = (state.get(url) or {}).get("sha256")
        _write_atomic(url_cache_path(spec, config), raw)
        at = datetime.now().isoformat(timespec="seconds")
        state[url] = {"sha256": digest, "bytes": len(raw), "at": at, "changed_at": at if digest != previous else (state.get(url) or {}).get("changed_at", at)}
        entry.update({"changed": digest != previous, "bytes": len(raw), "at": at})
        results.append(entry)
    _write_atomic(_state_path(data_dir, episode), json.dumps(state, ensure_ascii=False, indent=1).encode("utf-8"))
    return {"sources": results, "changed": any(r.get("changed") for r in results)}


def add_url_source(data_dir: str, episode: str, form: Mapping[str, Any], opener: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    """מקור חדש מכתובת: מוריד אותו פעם אחת (בלחיצה של המשתמש), בודק שהפרק נטען איתו, ורק אז שומר אותו בקובץ השינויים."""
    from dataviz.config import ConfigError, load_config
    from dataviz.episode import build_episode
    folder = de.episode_folder(data_dir, episode)
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    url = _check_url(form.get("url", ""))
    text = lambda key: str(form.get(key) or "").strip()[:120]  # noqa: E731
    if not text("time_column"):
        raise de.EpisodeError("בחר את עמודת התאריך.")
    period = text("period") or "day"
    if period not in de.PERIODS:
        raise de.EpisodeError("תקופת הזמן צריכה להיות יום, חודש או שנה.")
    spec: Dict[str, Any] = {"url": url, "time": {"column": text("time_column"), **({"period": period} if period != "day" else {})},
                            "value": {"column": text("value_column")} if text("value_column") else "count",
                            "entity": {"column": text("entity_column")} if text("entity_column") else {"from_time": "year"}}
    if text("legend"):
        spec["legend"] = text("legend")
    config = _config(data_dir, episode)
    overrides = de.load_overrides_for_path(folder)
    original = copy.deepcopy(overrides)   # 23.10.2026: בכישלון חוזרים בדיוק לזה (לא למקורות של config.yaml)
    sources = [dict(s) for s in config.get("sources") or []]
    if any(s.get("url") == url for s in sources):
        raise de.EpisodeError("המקור הזה כבר בפרק.", status=409)
    de._set_path(overrides, "sources", sources + [spec])
    de._set_path(overrides, "data.cache_dir", os.path.abspath(cache_dir(data_dir, episode)))
    de._write_overrides(data_dir, episode, folder, overrides, check=False)
    refreshed = refresh_sources(data_dir, episode, opener=opener)
    failed = next((r["error"] for r in refreshed["sources"] if r["url"] == url and r.get("error")), "")
    try:
        if failed:
            raise ValueError("ההורדה נכשלה: " + failed)
        build_episode(load_config(os.path.join(folder, "config.yaml"), de.load_overrides_for_path(folder)))
    except (ConfigError, KeyError, ValueError, OSError) as e:
        # המקור לא נטען - קובץ השינויים חוזר להיות בדיוק מה שהיה. קודם נכתבו לתוכו המקורות של config.yaml ו-cache_dir,
        # ושינויים עתידיים במקורות של config.yaml נבלעו בשקט
        de._write_overrides(data_dir, episode, folder, original, check=False)
        message = "; ".join(e.errors[:2]) if isinstance(e, ConfigError) else str(e)[:200]
        raise de.EpisodeError(f"המקור מהכתובת לא נוסף: {message}") from e
    return {"ok": True, "source": spec, "refresh": refreshed}


def remote_overview(data_dir: str, episode: str) -> Dict[str, Any]:
    """המקורות מכתובת של הפרק, מתי הורדו ומתי השתנו לאחרונה, והמשימות המתוזמנות שלו."""
    config = _config(data_dir, episode)
    state = load_state(data_dir, episode)
    remote = [{"url": s["url"], **{k: v for k, v in (state.get(s["url"]) or {}).items() if k in ("bytes", "at", "changed_at")}}
              for s in config.get("sources") or [] if s.get("url") and not s.get("path")]
    return {"sources": remote, "schedules": schedules_for(episode)}


# ---------- תזמון: רינדור בלילה ורענון נתונים ----------
SCHEDULE_MODES = ("full", "test", "share")


def schedule_args(episode: str, mode: str, refresh: bool, only_if_changed: bool) -> List[str]:
    if mode not in SCHEDULE_MODES or not de.NAME_RE.match(episode):
        raise de.EpisodeError("מצב או פרק לא תקינים לתזמון.")
    args = ["--episode", episode, "--mode", mode]
    if refresh:
        args.append("--refresh-data")
        if only_if_changed:
            args.append("--only-if-changed")
    return args


def schedules_for(episode: str) -> List[Dict[str, Any]]:
    from utils import scheduler_store
    result = []
    for task in scheduler_store.load_tasks():
        args = task.get("extra_args") or []
        if "--episode" in args and args[args.index("--episode") + 1:args.index("--episode") + 2] == [episode]:
            result.append({k: task.get(k) for k in ("id", "schedule_type", "time", "weekday", "interval_hours", "enabled", "last_run_at", "label", "extra_args")})
    return result
