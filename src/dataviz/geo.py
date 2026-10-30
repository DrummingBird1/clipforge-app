# dataviz/geo.py
#
# גל 42: קריאת GeoJSON לתרשים המפה (map_race) - בלי ספריות גיאוגרפיות. כל Feature עם Polygon או
# MultiPolygon הופך לרשימת מצולעים - טבעת חיצונית וחורים (גל 45: חורים נשמרים ומצוירים) - בהטלת מרקטור
# (כמו מפות ברשת) או בהטלה פשוטה (קו האורך מוכפל בקוסינוס של קו הרוחב האמצעי). השם של כל אזור = המאפיין
# map.key, והוא מותאם לשם הישות כטקסט.

import json
import math
from typing import Any, Dict, List, Mapping, Sequence, Tuple

Ring = List[Tuple[float, float]]
Polygon = List[Ring]          # [טבעת חיצונית, חור, חור...]
MAX_POINTS_PER_RING = 2000
PROJECTIONS = ("mercator", "equirect")


def _polygons(geometry: Mapping[str, Any]) -> List[Sequence[Sequence[Sequence[float]]]]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        return [coords] if coords else []
    if kind == "MultiPolygon":
        return [polygon for polygon in coords if polygon]
    if kind == "GeometryCollection":
        return [p for g in geometry.get("geometries") or [] for p in _polygons(g)]
    return []


def _thin(ring: Sequence[Sequence[float]]) -> Ring:
    """טבעת עם יותר מדי נקודות מדוללת (אחת מכל k) - המפה קטנה בפריים, והציור נשאר מהיר."""
    step = max(1, math.ceil(len(ring) / MAX_POINTS_PER_RING))
    return [(float(p[0]), float(p[1])) for p in ring[::step] if len(p) >= 2]


def _mercator_y(lat: float) -> float:
    lat = max(-85.0, min(85.0, lat))
    return math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def load_geojson(path: str, key: str, projection: str = "mercator") -> Dict[str, Any]:
    """{"features": [{"name", "polygons", "rings"}], "bounds": (x0, y0, x1, y1)} אחרי ההטלה. rings = הטבעות
    החיצוניות בלבד (לתאימות). ValueError על קובץ לא תקין."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, Mapping):
        raise ValueError("GeoJSON לא תקין: צריך אובייקט ברמה העליונה.")
    raw = data.get("features") if data.get("type") == "FeatureCollection" else [data]
    regions: List[Tuple[str, List[Polygon]]] = []
    for feature in raw or []:
        if not isinstance(feature, Mapping):
            continue
        name = (feature.get("properties") or {}).get(key)
        polygons: List[Polygon] = []
        for polygon in _polygons(feature.get("geometry") or {}):
            rings = [ring for ring in (_thin(r) for r in polygon) if len(ring) >= 3]
            if rings:
                polygons.append(rings)
        if name is not None and polygons:
            regions.append((str(name), polygons))
    if not regions:
        raise ValueError(f"אין בקובץ המפה אזורים (Polygon/MultiPolygon) עם המאפיין '{key}'.")
    # גל 47: קואורדינטות במטרים (רשת ישראל וכו', למשל מ-shapefile) כבר מוטלות - מצוירות כמו שהן
    planar = any(abs(x) > 180 or abs(y) > 90 for _name, polys in regions for poly in polys for ring in poly for x, y in ring[:1])
    if planar:
        def project(x: float, y: float) -> Tuple[float, float]:
            return x, y
    elif projection == "mercator":
        def project(x: float, y: float) -> Tuple[float, float]:
            return x, _mercator_y(y)
    else:
        lats = [y for _name, polys in regions for poly in polys for ring in poly for _x, y in ring]
        factor = math.cos(math.radians((min(lats) + max(lats)) / 2))

        def project(x: float, y: float) -> Tuple[float, float]:
            return x * factor, y
    projected = [(name, [[[project(x, y) for x, y in ring] for ring in poly] for poly in polys]) for name, polys in regions]
    xs = [x for _name, polys in projected for poly in polys for ring in poly for x, _y in ring]
    ys = [y for _name, polys in projected for poly in polys for ring in poly for _x, y in ring]
    return {"features": [{"name": name, "polygons": polys, "rings": [poly[0] for poly in polys]} for name, polys in projected],
            "bounds": (min(xs), min(ys), max(xs), max(ys))}


def geojson_keys(path: str, limit: int = 3) -> Dict[str, List[str]]:
    """המאפיינים של האזורים בקובץ, עם כמה ערכים לדוגמה - לבחירת map.key במסך."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    features = data.get("features") if isinstance(data, Mapping) and data.get("type") == "FeatureCollection" else [data]
    keys: Dict[str, List[str]] = {}
    for feature in features or []:
        for k, v in ((feature or {}).get("properties") or {}).items() if isinstance(feature, Mapping) else []:
            samples = keys.setdefault(str(k), [])
            if v is not None and len(samples) < limit and str(v) not in samples:
                samples.append(str(v))
    return keys


def match_report(geo: Mapping[str, Any], entities: Sequence[Any]) -> Dict[str, List[str]]:
    """אילו ישויות נמצאו במפה ואילו לא (לבדיקה במסך ובטסטים)."""
    names = {feature["name"] for feature in geo["features"]}
    found = [str(e) for e in entities if str(e) in names]
    missing = [str(e) for e in entities if str(e) not in names]
    return {"found": found, "missing": missing, "unused": sorted(names - set(found))}


# ---------- גל 47: shapefile (SHP + DBF) -> GeoJSON, בלי ספריות ----------
# גבולות שיפוט של רשויות בישראל מגיעים ממשרד הפנים כ-shapefile דחוס (zip) ברשת ישראל החדשה (מטרים).
# כאן נקראים המצולעים (סוג 5 / 15 / 25 - רק X,Y) והטבלה שלהם, והחורים משויכים לטבעת החיצונית שמכילה
# אותם. קואורדינטות שאינן קו אורך / רוחב (מטרים) מצוירות כמו שהן - ראו "planar" ב-load_geojson.
SHP_POLYGON_TYPES = (5, 15, 25)


def _ring_area(ring: Sequence[Sequence[float]]) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, list(ring[1:]) + [ring[0]])) / 2


def _inside(point: Sequence[float], ring: Sequence[Sequence[float]]) -> bool:
    x, y = point
    inside = False
    for (x0, y0), (x1, y1) in zip(ring, list(ring[1:]) + [ring[0]]):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / ((y1 - y0) or 1e-12) + x0:
            inside = not inside
    return inside


def read_shp(data: bytes) -> List[Any]:
    """רשימת צורות; כל צורה = רשימת מצולעים [טבעת חיצונית, חורים...] (רשימת נקודות [x, y]). צורה ריקה = []."""
    import struct
    if len(data) < 100 or struct.unpack(">i", data[0:4])[0] != 9994:
        raise ValueError("קובץ ה-SHP לא תקין.")
    shapes: List[Any] = []
    pos = 100
    while pos + 8 <= len(data):
        _num, length = struct.unpack(">ii", data[pos:pos + 8])
        content = data[pos + 8:pos + 8 + length * 2]
        pos += 8 + length * 2
        if len(content) < 4:
            break
        shape_type = struct.unpack("<i", content[:4])[0]
        if shape_type not in SHP_POLYGON_TYPES:
            shapes.append([])
            continue
        num_parts, num_points = struct.unpack("<ii", content[36:44])
        parts = list(struct.unpack(f"<{num_parts}i", content[44:44 + 4 * num_parts]))
        start = 44 + 4 * num_parts
        coords = struct.unpack(f"<{num_points * 2}d", content[start:start + 16 * num_points])
        points = [[coords[i], coords[i + 1]] for i in range(0, len(coords), 2)]
        rings = [points[a:b] for a, b in zip(parts, parts[1:] + [num_points]) if b - a >= 3]
        outers = [r for r in rings if _ring_area(r) < 0] or rings[:1]   # ב-shapefile: חיצונית עם כיוון השעון
        polygons = [[r] for r in outers]
        for ring in rings:
            if any(ring is o for o in outers):
                continue
            owner = next((p for p in polygons if _inside(ring[0], p[0])), polygons[-1] if polygons else None)
            if owner is not None:
                owner.append(ring)
        shapes.append(polygons)
    return shapes


def read_dbf(data: bytes, encoding: str = "") -> List[Dict[str, Any]]:
    """השורות של טבלת ה-DBF (שם שדה -> ערך). קידוד: מה-.cpg, אחרת utf-8 ואם נכשל cp1255 (עברית)."""
    import struct
    if len(data) < 32:
        raise ValueError("קובץ ה-DBF לא תקין.")
    count, header_len, record_len = struct.unpack("<IHH", data[4:12])
    fields = []
    pos = 32
    while pos + 32 <= header_len and data[pos] != 0x0D:
        name = data[pos:pos + 11].split(b"\x00", 1)[0].decode("ascii", "replace").strip()
        fields.append((name, chr(data[pos + 11]), data[pos + 16]))
        pos += 32

    def text(raw: bytes) -> str:
        for codec in [c for c in (encoding, "utf-8", "cp1255") if c]:
            try:
                return raw.decode(codec).strip()
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("latin-1").strip()

    rows: List[Dict[str, Any]] = []
    for i in range(count):
        start = header_len + i * record_len
        record = data[start:start + record_len]
        if not record or record[:1] == b"*":
            rows.append({})
            continue
        offset, row = 1, {}
        for name, kind, size in fields:
            raw = record[offset:offset + size]
            offset += size
            value: Any = text(raw)
            if kind in ("N", "F") and value:
                try:
                    number = float(value)
                    value = int(number) if number.is_integer() and "." not in value else number
                except ValueError:
                    pass
            row[name] = value
        rows.append(row)
    return rows


def shapefile_to_geojson(shp: bytes, dbf: bytes, encoding: str = "") -> Dict[str, Any]:
    """FeatureCollection - מצולע לכל שורה, עם כל השדות של הטבלה כמאפיינים."""
    shapes, rows = read_shp(shp), read_dbf(dbf, encoding)
    features = []
    for polygons, props in zip(shapes, rows):
        if not polygons:
            continue
        geometry = {"type": "Polygon", "coordinates": polygons[0]} if len(polygons) == 1 else {"type": "MultiPolygon", "coordinates": polygons}
        features.append({"type": "Feature", "properties": props, "geometry": geometry})
    if not features:
        raise ValueError("אין בקובץ מצולעים (צריך shapefile של שטחים).")
    return {"type": "FeatureCollection", "features": features}
