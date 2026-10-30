# tests/dataviz/test_dataviz_variants.py
#
# 20.10.2026: גרסאות של פרק - שכבה עם שם (set) מעל קובץ השינויים, עם יעד ושפה משלה ושם קובץ פלט משלה; הבסיס ו-config.yaml
# לא משתנים. רינדור של גרסה עובר בתור: קובץ הבקרה אומר ל-dataviz_maker איזו גרסה, והוא טוען את השכבה שלה.
import hashlib
import importlib.util
import json
import os

import pytest
from fastapi.testclient import TestClient

from dataviz.web import episodes as de
from dataviz.web import variants
from entrypoints import web_app
from entrypoints.web.script_args import _args_dataviz
from entrypoints.web_app import app
from tests import PROJECT_ROOT
from tests.dataviz_helpers import write_episode

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    folder = write_episode(data / "dataviz_episodes", name="tiny")
    de.update_override_fields(str(data), "tiny", {"subtitle": "בסיס"}, [])
    return {"data": str(data), "folder": folder}


def _save(**body):
    return client.post("/api/dataviz/variants/save", json={"episode": "tiny", **body})


def test_a_variant_is_a_layer_over_the_base_and_the_base_does_not_change(env):
    config = hashlib.md5(open(os.path.join(env["folder"], "config.yaml"), "rb").read()).digest()
    assert _save(name="short", label="קצרה", target="shorts", set={"title": "גרסה קצרה", "ranking.top_n": 4}).status_code == 200
    rows = client.get("/api/dataviz/variants", params={"episode": "tiny"}).json()["variants"]
    assert [(r["name"], r["label"], r["target"]) for r in rows] == [("short", "קצרה", "shorts")]
    merged = variants.effective_overrides(env["data"], "tiny", "short")
    assert merged["subtitle"] == "בסיס" and merged["title"] == "גרסה קצרה" and merged["ranking"]["top_n"] == 4
    assert merged["video"]["output_name"] == "tiny_short"                                   # לא דורס את הבסיס
    assert de.load_overrides_for_path(env["folder"]) == {"subtitle": "בסיס"}
    assert hashlib.md5(open(os.path.join(env["folder"], "config.yaml"), "rb").read()).digest() == config


def test_bad_variants_are_refused(env):
    assert _save(name="no spaces", set={"title": "x"}).status_code == 400
    assert _save(name="ok", target="fax", set={}).status_code == 400
    assert _save(name="ok", set={"ranking.top_n": "many"}).status_code == 400
    assert _save(name="english", lang="en", set={}).status_code == 400                      # אין translations.en
    assert _save(name="en", set={}).status_code == 409                                      # 23.10.2026: <פרק>_en הוא הגרסה באנגלית של הפרק
    assert client.get("/api/dataviz/variants", params={"episode": "nope"}).status_code == 404
    assert client.post("/api/dataviz/variants/zap", json={"episode": "tiny"}).status_code == 404


def test_remove_moves_the_variant_aside(env):
    _save(name="short", set={"title": "x"})
    assert client.post("/api/dataviz/variants/remove", json={"episode": "tiny", "name": "short"}).status_code == 200
    assert variants.names(env["data"], "tiny") == []
    removed = os.path.join(variants.variants_dir(env["data"], "tiny"), ".removed")
    assert len(os.listdir(removed)) == 1                                                    # לא נמחק
    assert client.post("/api/dataviz/variants/remove", json={"episode": "tiny", "name": "short"}).status_code == 404


def test_rendering_a_variant_goes_through_the_queue_with_its_target(env, monkeypatch):
    _save(name="short", target="shorts", set={"title": "גרסה קצרה"})
    calls = []
    monkeypatch.setattr(web_app, "_start_script_run", lambda script, folder, payload, host: calls.append(payload) or {"ok": True})
    assert client.post("/api/dataviz/run", json={"episode": "tiny", "mode": "stills", "variant": "nope"}).status_code == 404
    assert client.post("/api/dataviz/run", json={"episode": "tiny", "mode": "stills", "variant": "short"}).status_code == 200
    payload = calls[0]
    args = _args_dataviz(payload)
    assert args[args.index("--target") + 1] == "shorts" and args[args.index("--episodes") + 1] == "tiny"
    control = payload["dv_queue_file"][: -len(".json")] + ".control.json"
    assert json.load(open(control, encoding="utf-8")) == {"skip": [], "variants": {"tiny": "short"}}
    assert client.post("/api/dataviz/run", json={"episodes": ["tiny"], "mode": "stills", "variant": "short"}).status_code == 400


def test_the_maker_loads_the_variant_named_in_the_control_file(env, tmp_path):
    _save(name="short", set={"title": "גרסה קצרה"})
    spec = importlib.util.spec_from_file_location("dataviz_maker_variants", os.path.join(PROJECT_ROOT, "my_scripts", "video", "dataviz_maker.py"))
    maker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maker)
    queue_file = str(tmp_path / "dataviz_queue.json")
    with open(queue_file[: -len(".json")] + ".control.json", "w", encoding="utf-8") as f:
        json.dump({"skip": [], "variants": {"tiny": "short"}}, f)
    queue = maker.QueueTracker(queue_file, ["tiny"])
    assert queue.variants == {"tiny": "short"}
    seen = []
    import dataviz

    def fake_load(path, overrides):
        seen.append(overrides)
        raise OSError("stop here")
    original = dataviz.load_episode
    dataviz.load_episode = fake_load
    try:
        results = {"errors": 0, "files_created": 0}
        maker.render_episode(env["folder"], "stills", None, lambda done, total: None, results, queue=queue)
        maker.render_episode(env["folder"], "stills", None, lambda done, total: None, results, queue=None)
    finally:
        dataviz.load_episode = original
    assert seen[0]["title"] == "גרסה קצרה" and seen[0]["video"]["output_name"] == "tiny_short"
    assert seen[1] == {"subtitle": "בסיס"}                                                  # בלי גרסה - הבסיס
