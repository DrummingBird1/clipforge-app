# tests/studio/test_editor_run_labels.py - גל 36: שם ותגיות לריצה בהיסטוריה (utils/editor_runs.set_run_label + route)
from utils.video import editor_runs

from tests.web_app_support import client, web_app  # noqa: F401


def _runs_file(tmp_path):
    path = str(tmp_path / "runs.json")
    run_id = editor_runs.record_start(path, str(tmp_path), {"codec": "hevc"})
    return path, run_id


def test_label_sets_name_and_clean_tags(tmp_path):
    path, run_id = _runs_file(tmp_path)
    run = editor_runs.set_run_label(path, run_id, "  גרסה   לשורטס ", ["#shorts", "shorts", " טיוטה ", "", "#"])
    assert run["name"] == "גרסה לשורטס"
    assert run["tags"] == ["shorts", "טיוטה"]
    assert editor_runs.get_run(path, run_id)["tags"] == ["shorts", "טיוטה"]   # נשמר בקובץ


def test_empty_label_removes_name_and_tags(tmp_path):
    path, run_id = _runs_file(tmp_path)
    editor_runs.set_run_label(path, run_id, "x", ["a"])
    run = editor_runs.set_run_label(path, run_id, "", [])
    assert "name" not in run and "tags" not in run
    assert run["settings"] == {"codec": "hevc"}   # שאר הריצה לא נוגע


def test_label_limits_and_unknown_run(tmp_path):
    path, run_id = _runs_file(tmp_path)
    run = editor_runs.set_run_label(path, run_id, "א" * 200, [f"t{i}" for i in range(20)])
    assert len(run["name"]) == editor_runs.MAX_RUN_NAME and len(run["tags"]) == editor_runs.MAX_RUN_TAGS
    assert editor_runs.set_run_label(path, "nope", "x", []) is None


def test_label_route(tmp_path, monkeypatch):
    path, run_id = _runs_file(tmp_path)
    monkeypatch.setattr(web_app, "_editor_runs_path", lambda: path)
    resp = client.post(f"/api/video_editor/runs/{run_id}/label", json={"name": "ניסיון", "tags": ["אדום"]})
    assert resp.status_code == 200 and resp.json() == {"ok": True, "name": "ניסיון", "tags": ["אדום"]}
    assert client.post("/api/video_editor/runs/nope/label", json={"name": "x"}).status_code == 404
