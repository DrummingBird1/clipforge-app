# dataviz/web/library.py (עד 19.10.2026: utils/dataviz_library.py)
#
# גל 45: שני דברים שעורך הגרפים שומר בשביל הפרקים, מחוץ לתיקיות הפרקים עצמן:
# - ספריית מפות (data/dataviz_maps/): קובץ GeoJSON שהועלה פעם אחת ומשמש כל פרק. קובץ חדש בלבד - שם קיים לא נדרס.
# - הקלטות קריינות לאירועים (data/dataviz_overrides/<פרק>/narration/<תאריך>_<שעה>.<סיומת>): כל הקלטה היא קובץ
#   חדש (האחרונה גוברת), והפרק מפנה לתיקייה דרך narration.folder בקובץ השינויים שלו. config.yaml לא משתנה.

import base64
import io
import json
import os
import re
import time
from typing import Any, Dict, List, Tuple

from dataviz.web import episodes as de
from utils.shared import data_paths

MAPS_DIRNAME = data_paths.DATAVIZ_MAPS
MAP_MAX_BYTES = 20 * 1024 * 1024
MAP_NAME_RE = re.compile(r"^[\w\- א-ת]{1,60}$")
RECORDING_MAX_BYTES = 10 * 1024 * 1024
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------- ספריית המפות ----------
def maps_dir(data_dir: str) -> str:
    return os.path.join(data_dir, MAPS_DIRNAME)


def map_path(data_dir: str, name: str) -> str:
    """נתיב של מפה בספרייה, רק לשם תקין של קובץ קיים - אחרת EpisodeError."""
    stem = str(name or "")[: -len(".geojson")] if str(name or "").endswith(".geojson") else str(name or "")
    if not MAP_NAME_RE.match(stem):
        raise de.EpisodeError("שם מפה לא תקין.")
    path = os.path.join(maps_dir(data_dir), stem + ".geojson")
    if not os.path.isfile(path):
        raise de.EpisodeError("המפה לא נמצאה בספרייה.", status=404)
    return path


def list_maps(data_dir: str) -> List[Dict[str, Any]]:
    from dataviz.geo import geojson_keys
    folder = maps_dir(data_dir)
    result = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not name.endswith(".geojson"):
            continue
        path = os.path.join(folder, name)
        try:
            keys = geojson_keys(path)
        except (OSError, ValueError):
            keys = {}
        result.append({"name": name[: -len(".geojson")], "path": path, "keys": keys, "size": os.path.getsize(path)})
    return result


def save_map(data_dir: str, filename: str, text: str) -> Dict[str, Any]:
    """שומר GeoJSON חדש בספרייה (שם מהקובץ). שם קיים = שגיאה 409, לא דורסים."""
    from dataviz.geo import _polygons
    stem = os.path.splitext(os.path.basename(str(filename or "")))[0].strip()
    stem = re.sub(r"[^\w\- א-ת]+", "_", stem)[:60].strip("_") or "map"
    if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > MAP_MAX_BYTES:
        raise de.EpisodeError("קובץ מפה ריק או גדול מ-20MB.")
    try:
        data = json.loads(text)
    except ValueError:
        raise de.EpisodeError("הקובץ אינו JSON תקין.") from None
    features = data.get("features") if isinstance(data, dict) and data.get("type") == "FeatureCollection" else [data]
    if not any(isinstance(f, dict) and _polygons(f.get("geometry") or {}) for f in features or []):
        raise de.EpisodeError("אין בקובץ אזורים (Polygon / MultiPolygon) - צריך GeoJSON של שטחים.")
    folder = maps_dir(data_dir)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, stem + ".geojson")
    try:
        with open(path, "x", encoding="utf-8") as f:   # "x" - נכשל אם הקובץ קיים
            f.write(text)
    except FileExistsError:
        raise de.EpisodeError(f"כבר יש בספרייה מפה בשם '{stem}'.", status=409) from None
    return {"name": stem, "path": path}


def map_match(data_dir: str, episode: str, name: str, key: str, projection: str = "mercator") -> Dict[str, Any]:
    """אילו ישויות של הפרק נמצאו במפה (לפי המאפיין key) ואילו לא."""
    from dataviz.geo import load_geojson, match_report
    from dataviz.web.data import _episode
    folder = de.episode_folder(data_dir, episode)
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    try:
        geo = load_geojson(map_path(data_dir, name), str(key or "name"), projection)
    except ValueError as e:
        raise de.EpisodeError(str(e)) from None
    # הישויות אחרי שמות חלופיים והחרגות - כמו שהן יופיעו בסרטון
    return match_report(geo, list(_episode(folder, de.load_overrides_for_path(folder)).entities))


def use_map(data_dir: str, episode: str, name: str, key: str) -> Dict[str, Any]:
    path = map_path(data_dir, name)
    key = str(key or "").strip()
    if not key or len(key) > 60:
        raise de.EpisodeError("בחר את המאפיין עם שם האזור.")
    return de.update_override_fields(data_dir, episode, {"map.geojson": os.path.abspath(path), "map.key": key}, [])


# ---------- הקלטות קריינות ----------
def recordings_dir(data_dir: str, episode: str) -> str:
    return os.path.join(data_dir, de.OVERRIDES_DIRNAME, episode, "narration")


def list_recordings(data_dir: str, episode: str) -> Dict[str, str]:
    """תאריך -> שם קובץ של ההקלטה האחרונה."""
    from dataviz.narration import RECORDING_EXT
    if de.episode_folder(data_dir, episode) is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    folder = recordings_dir(data_dir, episode)
    newest: Dict[str, Any] = {}
    for name in os.listdir(folder) if os.path.isdir(folder) else []:
        stem, ext = os.path.splitext(name)
        date = stem.split("_", 1)[0]
        if ext.lower() in RECORDING_EXT and DATE_RE.match(date):
            mtime = os.path.getmtime(os.path.join(folder, name))
            if date not in newest or mtime > newest[date][0]:
                newest[date] = (mtime, name)
    return {date: name for date, (_m, name) in sorted(newest.items())}


def save_recording(data_dir: str, episode: str, date: str, ext: str, data_base64: str) -> Dict[str, Any]:
    """הקלטה חדשה לאירוע (קובץ חדש תמיד), והפרק מפנה לתיקיית ההקלטות."""
    from dataviz.narration import RECORDING_EXT
    folder_ep = de.episode_folder(data_dir, episode)
    if folder_ep is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    ext = "." + str(ext or "").lower().lstrip(".")
    if not DATE_RE.match(str(date or "")) or ext not in RECORDING_EXT:
        raise de.EpisodeError("הקלטה לא תקינה (תאריך YYYY-MM-DD וקובץ שמע).")
    try:
        raw = base64.b64decode(str(data_base64 or ""), validate=True)
    except ValueError:
        raise de.EpisodeError("ההקלטה לא הגיעה תקינה.") from None
    if not raw or len(raw) > RECORDING_MAX_BYTES:
        raise de.EpisodeError("ההקלטה ריקה או גדולה מ-10MB.")
    folder = recordings_dir(data_dir, episode)
    os.makedirs(folder, exist_ok=True)
    name = _write_new(folder, f"{date}_{time.strftime('%Y%m%d%H%M%S')}", ext, raw)
    if (de.load_overrides_for_path(folder_ep).get("narration") or {}).get("folder") != os.path.abspath(folder):
        de.update_override_fields(data_dir, episode, {"narration.folder": os.path.abspath(folder)}, [])
    return {"name": name, "date": date}


def _write_new(folder: str, stem: str, ext: str, raw: bytes) -> str:
    """23.10.2026: קובץ חדש תמיד - שתי העלאות באותה שנייה (תמונה ל-"Haifa" ול-"haifa", שתי הקלטות לאותו תאריך) נפלו
    על FileExistsError (500). השנייה מקבלת _2, _3... (אחרי השם עם הזמן - הסדר לפי שם וזמן נשמר)."""
    for i in range(1, 1000):
        name = stem + (f"_{i}" if i > 1 else "") + ext
        try:
            with open(os.path.join(folder, name), "xb") as f:
                f.write(raw)
            return name
        except FileExistsError:
            continue
    raise de.EpisodeError("לא נמצא שם פנוי לקובץ - נסה שוב.", status=500)


def _episode_or_404(data_dir: str, episode: str) -> None:
    """23.10.2026: הנתיבים של התמונות וההקלטות נבנו משם הפרק כמו שנשלח - נתיב מוחלט או "..\\.." הגיעו לקבצים מחוץ
    ל-data/ (וה-/trash שלחו אותם לסל המיחזור). עכשיו רק פרק שקיים, בשם המדויק שלו."""
    if de.episode_folder(data_dir, str(episode or "")) is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)


def recording_path(data_dir: str, episode: str, name: str) -> str:
    _episode_or_404(data_dir, episode)
    folder = os.path.realpath(recordings_dir(data_dir, episode))
    path = os.path.realpath(os.path.join(folder, os.path.basename(str(name or ""))))
    if os.path.dirname(path) != folder or not os.path.isfile(path):
        raise de.EpisodeError("ההקלטה לא נמצאה.", status=404)
    return path


# ---------- גל 51: תמונה לכל ישות ----------
# קובץ חדש תמיד תחת data/dataviz_overrides/<פרק>/images/ בשם "<ישות>@<זמן>.<סיומת>" (המנוע לוקח את החדש ביותר לכל
# ישות), והפרק מפנה לתיקייה (images.folder). מחיקה = סל המיחזור, והישות חוזרת לתמונה הקודמת או לבלי תמונה.
IMAGE_UPLOAD_EXT = (".png", ".jpg", ".jpeg", ".webp")
IMAGE_MAX_BYTES = 5 * 1024 * 1024


def images_dir(data_dir: str, episode: str) -> str:
    return os.path.join(data_dir, de.OVERRIDES_DIRNAME, episode, "images")


def list_images(data_dir: str, episode: str) -> Dict[str, str]:
    """שם הישות (כמו בשם הקובץ) -> שם הקובץ של התמונה החדשה ביותר שהועלתה מהמסך."""
    if de.episode_folder(data_dir, episode) is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    folder = images_dir(data_dir, episode)
    newest: Dict[str, Any] = {}
    for name in os.listdir(folder) if os.path.isdir(folder) else []:
        stem, ext = os.path.splitext(name)
        if ext.lower() in IMAGE_UPLOAD_EXT:
            key = stem.rsplit("@", 1)[0]
            mtime = os.path.getmtime(os.path.join(folder, name))
            if key not in newest or mtime > newest[key][0]:
                newest[key] = (mtime, name)
    return {key: name for key, (_m, name) in sorted(newest.items())}


def save_image(data_dir: str, episode: str, entity: str, ext: str, data_base64: str) -> Dict[str, Any]:
    from dataviz.charts.base import image_name
    folder_ep = de.episode_folder(data_dir, episode)
    if folder_ep is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    key = image_name(entity)
    ext = "." + str(ext or "").lower().lstrip(".")
    if not key or len(key) > 80 or ext not in IMAGE_UPLOAD_EXT:
        raise de.EpisodeError("תמונה לא תקינה (ישות ותמונה png / jpg / webp).")
    try:
        raw = base64.b64decode(str(data_base64 or ""), validate=True)
    except ValueError:
        raise de.EpisodeError("התמונה לא הגיעה תקינה.") from None
    if not raw or len(raw) > IMAGE_MAX_BYTES:
        raise de.EpisodeError("התמונה ריקה או גדולה מ-5MB.")
    try:
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
    except Exception:
        raise de.EpisodeError("הקובץ הוא לא תמונה תקינה.") from None
    folder = images_dir(data_dir, episode)
    os.makedirs(folder, exist_ok=True)
    name = _write_new(folder, f"{key}@{time.strftime('%Y%m%d%H%M%S')}", ext, raw)
    if (de.load_overrides_for_path(folder_ep).get("images") or {}).get("folder") != os.path.abspath(folder):
        de.update_override_fields(data_dir, episode, {"images.folder": os.path.abspath(folder)}, [])
    return {"name": name, "entity": key}


def image_path(data_dir: str, episode: str, name: str) -> str:
    _episode_or_404(data_dir, episode)
    folder = os.path.realpath(images_dir(data_dir, episode))
    path = os.path.realpath(os.path.join(folder, os.path.basename(str(name or ""))))
    if os.path.dirname(path) != folder or not os.path.isfile(path):
        raise de.EpisodeError("התמונה לא נמצאה.", status=404)
    return path


# ---------- גל 46: מפות מוכנות - קטלוג קבוע, הורדה רק בלחיצה במסך ----------
# כתובות קבועות בלבד (לא מהדפדפן), גודל מוגבל, והקובץ נבדק כ-GeoJSON לפני שהוא נכנס לספרייה (בשם חדש בלבד).
READY_MAPS: Tuple[Dict[str, Any], ...] = (
    {"id": "israel-districts", "title": "ישראל - 6 המחוזות", "key": "shapeName", "size": 44192, "license": "Public Domain (geoBoundaries)",
     "url": "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/ISR/ADM1/geoBoundaries-ISR-ADM1_simplified.geojson"},
    {"id": "israel-subdistricts", "title": "ישראל - 15 הנפות", "key": "shapeName", "size": 122084, "license": "CC0 (geoBoundaries)",
     "url": "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/ISR/ADM2/geoBoundaries-ISR-ADM2_simplified.geojson"},
    {"id": "world-countries", "title": "מדינות העולם", "key": "NAME", "size": 838726, "license": "Public Domain (Natural Earth)",
     "url": "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson"},
)
READY_MAX_BYTES = 5 * 1024 * 1024


def ready_maps(data_dir: str) -> List[Dict[str, Any]]:
    """הקטלוג, עם סימון של מה שכבר בספרייה."""
    folder = maps_dir(data_dir)
    return [{**{k: m[k] for k in ("id", "title", "key", "size", "license")},
             "installed": os.path.isfile(os.path.join(folder, m["id"] + ".geojson"))} for m in READY_MAPS]


def fetch_ready_map(data_dir: str, map_id: str, opener: Any = None) -> Dict[str, Any]:
    """מוריד מפה מהקטלוג לספרייה (data/dataviz_maps/<id>.geojson). קיימת כבר = 409, לא דורסים."""
    entry = next((m for m in READY_MAPS if m["id"] == map_id), None)
    if entry is None:
        raise de.EpisodeError("מפה לא מוכרת בקטלוג.", status=404)
    if os.path.isfile(os.path.join(maps_dir(data_dir), entry["id"] + ".geojson")):
        raise de.EpisodeError("המפה כבר בספרייה.", status=409)
    if opener is None:
        import urllib.request
        opener = lambda url: urllib.request.urlopen(url, timeout=30)  # noqa: E731
    try:
        with opener(entry["url"]) as response:
            raw = response.read(READY_MAX_BYTES + 1)
    except OSError as e:
        raise de.EpisodeError(f"ההורדה נכשלה: {e}") from None
    if len(raw) > READY_MAX_BYTES:
        raise de.EpisodeError("הקובץ גדול מהצפוי - לא נשמר.")
    return save_map(data_dir, entry["id"] + ".geojson", raw.decode("utf-8", "replace"))


# ---------- גל 47: shapefile דחוס (zip) -> מפה בספרייה ----------
SHAPEFILE_MAX_BYTES = 30 * 1024 * 1024        # הקובץ הדחוס
SHAPEFILE_MAX_UNZIPPED = 120 * 1024 * 1024    # מה שבתוכו - הגנה מקובץ דחוס "מתפוצץ"


def save_shapefile_zip(data_dir: str, filename: str, data_base64: str) -> Dict[str, Any]:
    """zip עם .shp + .dbf (ו-.cpg אם יש) -> GeoJSON חדש בספרייה, בשם הקובץ הדחוס. שם קיים = 409."""
    import io
    import zipfile
    from dataviz.geo import shapefile_to_geojson
    try:
        raw = base64.b64decode(str(data_base64 or ""), validate=True)
    except ValueError:
        raise de.EpisodeError("הקובץ לא הגיע תקין.") from None
    if not raw or len(raw) > SHAPEFILE_MAX_BYTES:
        raise de.EpisodeError("קובץ ריק או גדול מ-30MB.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise de.EpisodeError("הקובץ אינו zip תקין.") from None
    with archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
        if sum(i.file_size for i in infos) > SHAPEFILE_MAX_UNZIPPED:
            raise de.EpisodeError("התוכן של הקובץ הדחוס גדול מדי.")
        by_ext: Dict[str, Any] = {}
        for info in infos:
            ext = os.path.splitext(info.filename)[1].lower()
            by_ext.setdefault(ext, info)   # רק לפי הסיומת - נתיבים בתוך ה-zip לא משמשים לכתיבה
        if ".shp" not in by_ext or ".dbf" not in by_ext:
            raise de.EpisodeError("ב-zip צריכים להיות קובץ .shp וקובץ .dbf של אותה שכבה.")
        encoding = archive.read(by_ext[".cpg"]).decode("ascii", "ignore").strip() if ".cpg" in by_ext else ""
        try:
            geo = shapefile_to_geojson(archive.read(by_ext[".shp"]), archive.read(by_ext[".dbf"]), encoding)
        except (ValueError, KeyError) as e:
            raise de.EpisodeError(f"לא הצלחתי לקרוא את ה-shapefile: {e}") from None
    return save_map(data_dir, os.path.splitext(os.path.basename(str(filename or "")))[0] + ".geojson", json.dumps(geo, ensure_ascii=False))

