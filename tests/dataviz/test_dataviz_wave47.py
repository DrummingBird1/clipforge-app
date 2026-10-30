# tests/dataviz/test_dataviz_wave47.py - גל 47: shapefile דחוס (zip) -> מפה בספרייה - הצורות (כולל חור) והטבלה
# (עברית ב-cp1255 בלי .cpg), קואורדינטות במטרים שמצוירות כמו שהן, הגנות (zip בלי .dbf, תוכן גדול מדי, שם קיים)
# והנתיב במסך. הקבצים נבנים כאן בזיכרון - בלי הורדות.
import base64
import io
import json
import os
import struct
import zipfile


import pytest
from fastapi.testclient import TestClient

from dataviz.geo import load_geojson, read_dbf, read_shp, shapefile_to_geojson
from entrypoints import web_app
from entrypoints.web_app import app
from dataviz.web import episodes as de
from dataviz.web import library as lib

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _square(x, y, size, clockwise):
    ring = [(x, y), (x, y + size), (x + size, y + size), (x + size, y), (x, y)]   # עם כיוון השעון
    return ring if clockwise else ring[::-1]


def make_shp(shapes):
    """shapes: רשימת צורות, כל צורה = רשימת טבעות (בסדר של הקובץ)."""
    records = b""
    for n, rings in enumerate(shapes, start=1):
        points = [p for ring in rings for p in ring]
        parts, start = [], 0
        for ring in rings:
            parts.append(start)
            start += len(ring)
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        content = struct.pack("<i4d2i", 5, min(xs), min(ys), max(xs), max(ys), len(rings), len(points))
        content += struct.pack(f"<{len(parts)}i", *parts) + b"".join(struct.pack("<2d", *p) for p in points)
        records += struct.pack(">2i", n, len(content) // 2) + content
    header = struct.pack(">7i", 9994, 0, 0, 0, 0, 0, (100 + len(records)) // 2) + struct.pack("<2i8d", 1000, 5, *([0.0] * 8))
    return header + records


def make_dbf(rows, encoding="cp1255"):
    fields = [("NAME", "C", 30), ("POP", "N", 10)]
    header_len = 32 + 32 * len(fields) + 1
    record_len = 1 + sum(size for _n, _t, size in fields)
    header = struct.pack("<B3BIHH20x", 3, 126, 10, 16, len(rows), header_len, record_len)
    for name, kind, size in fields:
        header += name.encode("ascii").ljust(11, b"\x00") + kind.encode("ascii") + b"\x00" * 4 + bytes([size, 0]) + b"\x00" * 14
    header += b"\x0d"
    body = b"".join(b" " + row[0].encode(encoding).ljust(30, b" ") + str(row[1]).rjust(10).encode("ascii") for row in rows)
    return header + body + b"\x1a"


# שתי ערים ברשת ישראל (מטרים); לשנייה חור באמצע
SHAPES = [[_square(170000, 650000, 1000, True)],
          [_square(180000, 660000, 3000, True), _square(181000, 661000, 1000, False)]]
ROWS = [("ירושלים", 950000), ("תל אביב - יפו", 470000)]


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    return str(data)


def test_shapes_and_hebrew_rows_are_read(tmp_path):
    shapes = read_shp(make_shp(SHAPES))
    assert len(shapes) == 2 and len(shapes[0]) == 1 and len(shapes[1]) == 1 and len(shapes[1][0]) == 2   # חיצונית + חור
    assert read_dbf(make_dbf(ROWS)) == [{"NAME": "ירושלים", "POP": 950000}, {"NAME": "תל אביב - יפו", "POP": 470000}]
    assert read_dbf(make_dbf(ROWS, "utf-8"), "UTF-8")[0]["NAME"] == "ירושלים"
    geo = shapefile_to_geojson(make_shp(SHAPES), make_dbf(ROWS))
    assert [f["properties"]["NAME"] for f in geo["features"]] == ["ירושלים", "תל אביב - יפו"]
    path = tmp_path / "cities.geojson"
    path.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
    loaded = load_geojson(str(path), "NAME")
    tlv = loaded["features"][1]
    assert len(tlv["polygons"][0]) == 2 and loaded["bounds"] == (170000, 650000, 183000, 663000)   # מטרים - כמו שהם
    with pytest.raises(ValueError):
        read_shp(b"not a shapefile")


def test_a_zipped_shapefile_becomes_a_new_map_in_the_library(data_dir):
    zipped = _zip({"layer/Cities.shp": make_shp(SHAPES), "layer/Cities.dbf": make_dbf(ROWS), "layer/Cities.prj": b"ITM"})
    assert lib.save_shapefile_zip(data_dir, "גבולות שיפוט.zip", zipped)["name"] == "גבולות שיפוט"
    listed = lib.list_maps(data_dir)
    assert listed[0]["keys"]["NAME"][:2] == ["ירושלים", "תל אביב - יפו"]
    with pytest.raises(de.EpisodeError) as e:
        lib.save_shapefile_zip(data_dir, "גבולות שיפוט.zip", zipped)
    assert e.value.status == 409
    with pytest.raises(de.EpisodeError):
        lib.save_shapefile_zip(data_dir, "x.zip", _zip({"a.shp": make_shp(SHAPES)}))   # בלי .dbf
    with pytest.raises(de.EpisodeError):
        lib.save_shapefile_zip(data_dir, "x.zip", base64.b64encode(b"not a zip").decode())


def test_a_zip_that_unpacks_too_big_is_refused(data_dir, monkeypatch):
    monkeypatch.setattr(lib, "SHAPEFILE_MAX_UNZIPPED", 100)
    with pytest.raises(de.EpisodeError):
        lib.save_shapefile_zip(data_dir, "big.zip", _zip({"a.shp": make_shp(SHAPES), "a.dbf": make_dbf(ROWS)}))
    assert not os.path.isdir(lib.maps_dir(data_dir)) or not os.listdir(lib.maps_dir(data_dir))


def test_the_shapefile_route(data_dir):
    zipped = _zip({"Cities.shp": make_shp(SHAPES), "Cities.dbf": make_dbf(ROWS)})
    resp = client.post("/api/dataviz/maps/upload_shapefile", json={"filename": "ערים.zip", "data_base64": zipped})
    assert resp.status_code == 200 and resp.json()["name"] == "ערים"
    assert client.post("/api/dataviz/maps/upload_shapefile", json={"filename": "ערים.zip", "data_base64": zipped}).status_code == 409


# ---------- אנגלית לטקסטים שהשרת שולח (סכימה ומדריך) ----------
def _hebrew(text):
    return any("֐" <= ch <= "׿" for ch in str(text))


def test_every_setting_and_guide_text_has_english():
    from dataviz import schema
    from dataviz.help import help_sections
    from dataviz.i18n_en import EN
    missing = []
    for _key, title, about in schema.GROUPS:
        missing += [s for s in (title, about) if s not in EN]
    for field in schema.FIELDS:
        missing += [s for s in (field["label"], field.get("help") or "", *(field.get("choice_labels") or {}).values()) if s and s not in EN]
    assert missing == [], missing
    english = help_sections("en")
    # ערך ברירת המחדל הוא תוכן הסרטון עצמו (למשל שמות המקומות בעברית) - הוא נשאר כמו שהוא
    bad = [(s["id"], i["title"], i["text"]) for s in english for i in s["items"]
           if _hebrew(i["title"]) or _hebrew(i["text"].split(" Default: ")[0])]
    bad += [(s["id"], s["title"]) for s in english if _hebrew(s["title"]) or _hebrew(s.get("about", ""))]
    assert bad == [], bad[:5]
    assert any("Range: 0.005 to 1." in i["text"] for s in english for i in s["items"])
    assert help_sections("he")[0]["title"].endswith("סוגי תרשימים")


def test_the_editor_and_guide_routes_answer_in_english(tmp_path, monkeypatch):
    from tests.dataviz_helpers import write_episode
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    write_episode(data / "dataviz_episodes", name="tiny")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    groups = client.get("/api/dataviz/episodes/editor", params={"episode": "tiny", "lang": "en"}).json()["groups"]
    assert groups[0]["title"] == "⭐ Basics" and groups[0]["fields"][0]["label"] == "Title"   # גל 59
    assert groups[1]["title"] == "📝 Texts" and groups[1]["fields"][0]["label"] == "Intro: title"
    assert not any(_hebrew(f["label"]) or _hebrew(f["help"]) for g in groups for f in g["fields"])
    assert client.get("/api/dataviz/episodes/editor", params={"episode": "tiny"}).json()["groups"][1]["title"] == "📝 טקסטים"
    assert client.get("/api/dataviz/help", params={"lang": "en"}).json()["sections"][1]["title"] == "▶️ What to produce"
