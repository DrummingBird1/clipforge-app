# tests/dataviz/test_dataviz_catalog.py
#
# 20.10.2026: קטלוג מקורות הנתונים - רשימה קבועה (למ"ס, הבנק העולמי, OECD) עם חיפוש; הורדה רק בבקשה מפורשת, רק מהכתובת
# הקבועה שבקטלוג, עד 5MB - לפרק חדש (עם SOURCES.md) או כמקור לפרק קיים. הכל מול שרת HTTP מזויף על localhost - אף בקשה
# לא יוצאת לרשת.
# 22.10.2026: השרת המזויף מתנהג כמו האמיתיים בהורדה האמיתית (באישור המשתמש): OECD מחזיר 403 ל-User-Agent של
# Python-urllib, ובלי תוויות (format=csv) רק קודי מדינות; מדד המחירים של הלמ"ס מ-API המדדים - 100 קריאות לעמוד עם
# paging.next_url, וכל קריאה בבסיס שהיה בתוקף בזמנה. הקובץ עם התוויות של OECD כאן לפי התיעוד - לא נבדק מול השרת.
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import yaml
from fastapi.testclient import TestClient

from dataviz.web import catalog
from dataviz.web import episodes as de
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

WB = json.dumps([{"page": 1}, [
    {"date": "2021", "value": 9364000, "country": {"value": "Israel"}, "countryiso3code": "ISR"},
    {"date": "2022", "value": 9550000, "country": {"value": "Israel"}, "countryiso3code": "ISR"},
    {"date": "2021", "value": 331900000, "country": {"value": "United States"}, "countryiso3code": "USA"},
    {"date": "2022", "value": None, "country": {"value": "United States"}, "countryiso3code": "USA"},
]]).encode()
OECD_CODES = b"DATAFLOW,REF_AREA,FREQ,TIME_PERIOD,OBS_VALUE\nX,ISR,M,2023-01,3.4\nX,ISR,M,2023-02,3.6\nX,USA,M,2023-01,3.5\n"
OECD_LABELS = (b"STRUCTURE,STRUCTURE_ID,REF_AREA,Reference area,TIME_PERIOD,Time period,OBS_VALUE,Observation value\n"
               b"DATAFLOW,X,ISR,Israel,2023-01,,3.4,\nDATAFLOW,X,ISR,Israel,2023-02,,3.6,\nDATAFLOW,X,USA,United States,2023-01,,3.5,\n")
CPI = "מדד המחירים לצרכן - כללי"
# (שנה, חודש, ערך, בסיס, שינוי חודשי %) מהחדש לישן, כמו ב-API: ינואר 2025 עלה ב-1% מדצמבר 2024, שפורסם בבסיס הקודם
CBS_NEW = [(2025, 2, 101.5, "2024 ממוצע", 0.5), (2025, 1, 101.0, "2024 ממוצע", 1.0)]
CBS_OLD = [(2024, 12, 110.0, "2022 ממוצע", 0.3), (2024, 11, 99.0, "2022 ממוצע", 0.1)]


def _cbs_page(items, next_url):
    return json.dumps({"month": [{"code": 120010, "name": CPI, "date": [
        {"year": y, "month": m, "monthDesc": "", "percent": p, "percentYear": None, "currBase": {"baseDesc": b, "value": v}, "prevBase": None}
        for y, m, v, b, p in items]}], "quarter": None,
        "paging": {"total_items": 4, "page_size": 2, "next_url": next_url}}, ensure_ascii=False).encode()


@pytest.fixture
def fake(monkeypatch):
    seen, agents = [], []
    state = {"next": "auto"}   # הכתובת של העמוד השני אצל הלמ"ס: "auto" = בשרת המזויף, אחרת מה שהטסט שם
    replies = {"/wb": WB, "/big": b"x" * (catalog.MAX_BYTES + 10)}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            agents.append(self.headers.get("User-Agent", ""))
            base = f"http://127.0.0.1:{self.server.server_address[1]}"
            if self.path.startswith("/oecd"):
                if agents[-1].startswith("Python-urllib"):
                    return self._reply(403, b"")
                return self._reply(200, OECD_LABELS if "format=csvfilewithlabels" in self.path else OECD_CODES)
            if self.path.startswith("/cbs/price"):
                if "Page=2" in self.path:
                    return self._reply(200, _cbs_page(CBS_OLD, None))
                return self._reply(200, _cbs_page(CBS_NEW, f"{base}/cbs/price?Page=2&PageSize=2&id=120010" if state["next"] == "auto" else state["next"]))
            body = next((v for k, v in replies.items() if self.path.startswith(k)), b"")
            self._reply(200 if body else 404, body)

        def _reply(self, status, body):
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setattr(catalog, "BASES", {"worldbank": base + "/wb", "oecd": base + "/oecd", "cbs": base + "/cbs"})
    yield {"seen": seen, "agents": agents, "base": base, "state": state}
    server.shutdown()


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    return data


def test_the_catalog_lists_fixed_series_and_searches_without_downloading(env, fake):
    items = client.get("/api/dataviz/catalog").json()["items"]
    assert {i["provider"] for i in items} == {"worldbank", "oecd", "cbs"} and len(items) == len(catalog.CATALOG)
    assert all(i["url"].startswith(fake["base"]) and i["units"] and i["license"] for i in items)
    hits = client.get("/api/dataviz/catalog", params={"q": "תוחלת"}).json()["items"]
    assert [i["id"] for i in hits] == ["wb_life_expectancy"]
    assert client.get("/api/dataviz/catalog", params={"q": "למ\"ס"}).json()["items"][0]["provider"] == "cbs"
    assert fake["seen"] == []                                                   # רק רשימה - שום בקשה


def test_each_provider_format_becomes_one_csv(env, fake):
    wb = catalog.fetch_csv("wb_population")
    assert wb["csv"].splitlines() == ["date,entity,value", "2021,Israel,9364000", "2021,United States,331900000", "2022,Israel,9550000"]
    oecd = catalog.fetch_csv("oecd_unemployment_monthly")
    assert oecd["entities"] == ["Israel", "United States"] and oecd["range"] == ["2023-01", "2023-02"]
    cbs = catalog.fetch_csv("cbs_cpi")
    assert cbs["entities"] == [CPI] and cbs["range"] == ["2024-11", "2025-02"]
    assert [p.split("?")[0] for p in fake["seen"]] == ["/wb" + catalog._BY_ID["wb_population"]["path"].split("?")[0],
                                                       "/oecd" + catalog._BY_ID["oecd_unemployment_monthly"]["path"].split("?")[0],
                                                       "/cbs/price", "/cbs/price"]


def test_oecd_gets_our_user_agent_and_country_names(env, fake):
    oecd = catalog.fetch_csv("oecd_cpi_annual")                                  # היום: 403 ל-Python-urllib
    assert oecd["entities"] == ["Israel", "United States"]                       # ולא ISR / USA
    assert "format=csvfilewithlabels" in fake["seen"][0] and fake["agents"] == [catalog.USER_AGENT]


def test_the_cbs_price_index_follows_its_pages_and_is_chained_to_the_latest_base(env, fake):
    cbs = catalog.fetch_csv("cbs_cpi")
    # דצמבר 2024 בבסיס הקודם (110) = ינואר 2025 (101) פחות 1% = 100; נובמבר בהתאם (99 * 100/110 = 90)
    assert cbs["csv"].splitlines()[1:] == [f"2024-11,{CPI},90", f"2024-12,{CPI},100", f"2025-01,{CPI},101", f"2025-02,{CPI},101.5"]
    assert cbs["note"] == "משורשר לבסיס האחרון (2024 ממוצע = 100)"
    assert fake["seen"][1].startswith("/cbs/price?Page=2") and len(fake["seen"]) == 2


def test_cbs_paging_stays_on_the_same_site_and_has_a_page_cap(env, fake, monkeypatch):
    fake["state"]["next"] = "http://evil.example/cbs/price?Page=2"
    with pytest.raises(de.EpisodeError, match="אותו אתר"):
        catalog.fetch_csv("cbs_cpi")
    assert len(fake["seen"]) == 1                                                # לא פנה לאתר האחר
    fake["state"]["next"] = "auto"
    monkeypatch.setattr(catalog, "MAX_PAGES", 1)
    with pytest.raises(de.EpisodeError, match="עמודים"):
        catalog.fetch_csv("cbs_cpi")


def test_a_base_switch_without_a_monthly_change_stops_the_series_there():
    page = json.loads(_cbs_page(CBS_NEW[:1] + [(2025, 1, 101.0, "2024 ממוצע", None)] + CBS_OLD, None))
    rows, _note = catalog._rows_cbs([page])
    assert [r[0] for r in rows] == ["2025-02", "2025-01"]                        # לא מערבבים את הבסיס הקודם בלי קישור


def test_a_download_makes_a_new_episode_with_its_sources_file(env, fake):
    resp = client.post("/api/dataviz/catalog/fetch", json={"id": "wb_population", "target": "new", "name": "population", "url": "http://evil.example/x"})
    assert resp.status_code == 200, resp.text
    folder = env / "dataviz_episodes" / "population"
    config = yaml.safe_load((folder / "config.yaml").read_text(encoding="utf-8"))
    assert config["chart"] == "line_race" and config["sources"][0]["path"] == "wb_population.csv" and config["sources"][0]["kind"] == "level"
    sources = (folder / "SOURCES.md").read_text(encoding="utf-8")
    assert "הבנק העולמי" in sources and "SP.POP.TOTL" in sources and "אנשים" in sources and fake["base"] in sources
    assert "evil.example" not in sources and all("evil" not in p for p in fake["seen"])   # הכתובת מהקטלוג, לא מהבקשה
    again = client.post("/api/dataviz/catalog/fetch", json={"id": "wb_population", "target": "new", "name": "population"})
    assert again.status_code == 409


def test_a_download_can_be_a_source_of_an_existing_episode(env, fake):
    folder = write_episode(env / "dataviz_episodes", name="tiny")
    config = open(os.path.join(folder, "config.yaml"), "rb").read()
    resp = client.post("/api/dataviz/catalog/fetch", json={"id": "cbs_cpi", "target": "source", "episode": "tiny"})
    assert resp.status_code == 200, resp.text
    sources = de.load_overrides_for_path(folder)["sources"]
    assert len(sources) == 3 and sources[2]["kind"] == "level" and sources[2]["time"] == {"column": "date", "period": "month"}
    notes = (env / "dataviz_overrides" / "tiny" / "SOURCES.md").read_text(encoding="utf-8")
    assert "הלמ\"ס" in notes and "120010" in notes and "משורשר לבסיס האחרון" in notes
    assert open(os.path.join(folder, "config.yaml"), "rb").read() == config


def test_bad_downloads_write_nothing(env, fake, monkeypatch):
    assert client.post("/api/dataviz/catalog/fetch", json={"id": "nope", "name": "x"}).status_code == 404
    monkeypatch.setitem(catalog.BASES, "worldbank", fake["base"] + "/big")
    big = client.post("/api/dataviz/catalog/fetch", json={"id": "wb_population", "name": "big"})
    assert big.status_code == 400 and "5MB" in big.json()["error"]
    monkeypatch.setitem(catalog.BASES, "worldbank", fake["base"] + "/missing")
    assert client.post("/api/dataviz/catalog/fetch", json={"id": "wb_population", "name": "gone"}).status_code == 400
    assert os.listdir(env / "dataviz_episodes") == []


# 30.10.2026 (לפני ההפצה): בממשק באנגלית המקורות העולמיים קודם, המדינות של העולם לפני ישראל, והלמ"ס בשפת הממשק - בעברית
# כמו קודם. המקורות הישראליים נשארים בשתי השפות.
def test_in_english_world_sources_come_first_and_cbs_answers_in_english(env, fake):
    english = client.get("/api/dataviz/catalog", params={"lang": "en"}).json()["items"]
    providers = [i["provider"] for i in english]
    assert providers == sorted(providers, key=catalog.WORLD_FIRST.get) and "cbs" in providers
    assert "/country/USA;GBR;DEU;FRA;JPN;ISR/" in english[0]["url"]                       # קודם: ISR ראשונה
    assert "lang=en" in next(i for i in english if i["provider"] == "cbs")["url"]
    hebrew = client.get("/api/dataviz/catalog").json()["items"]
    assert [i["id"] for i in hebrew] == [i["id"] for i in catalog.CATALOG]
    assert "lang=he" in next(i for i in hebrew if i["provider"] == "cbs")["url"]
    resp = client.post("/api/dataviz/catalog/fetch", json={"id": "cbs_cpi", "target": "new", "name": "cpi_en", "lang": "en"})
    assert resp.status_code == 200, resp.text
    assert any(p.startswith("/cbs/price") and "lang=en" in p for p in fake["seen"])
    assert "lang=en" in (env / "dataviz_episodes" / "cpi_en" / "SOURCES.md").read_text(encoding="utf-8")


def test_the_catalog_texts_have_english():
    with open(os.path.join(os.path.dirname(web_app.__file__), "web", "i18n", "en.json"), encoding="utf-8") as f:
        exact = json.load(f)["exact"]
    texts = {t for item in catalog.CATALOG for t in (item["title"], item["units"])} | {p[k] for p in catalog.PROVIDERS.values() for k in ("name", "license")}
    hebrew = {t for t in texts if any("֐" <= ch <= "׿" for ch in t)}
    assert sorted(t for t in hebrew if t not in exact) == []                              # קודם: כולם בעברית בממשק האנגלי
