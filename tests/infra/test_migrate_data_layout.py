# tests/infra/test_migrate_data_layout.py
#
# dev/migrate_data_layout.py: העברת data/ לתיקיות לפי נושא (פריט 19, שלבים ב'-ג'). יבש כברירת מחדל, מגבה לפני שמזיז, לא
# דורס, משכתב נתיבים מוחלטים שנשמרו ב-JSON, כותב את הסימן רק בסוף, ומחזיר הכל אחורה כשהעברה נכשלת באמצע. הכל על data
# זמני - לא על data/ האמיתי.
import importlib.util
import json
import os
import subprocess
import sys
import zipfile

from tests import PROJECT_ROOT

_spec = importlib.util.spec_from_file_location("migrate_data_layout", os.path.join(PROJECT_ROOT, "dev", "migrate_data_layout.py"))
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)


def _file(path, content="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _flat_data(data, stored_root=None):
    root = str(stored_root or data)
    _file(data / "config.json", "{}")
    _file(data / "config.json.bak", "{}")
    _file(data / "config.example.json", "{}")
    _file(data / "clipforge_data.db", "db")
    _file(data / "web_app_token.txt", "token")
    _file(data / "counter.txt", "7")
    _file(data / "rocket_settings.json", json.dumps({"counter_file_path": os.path.join(root, "counter.txt"), "title": "x"}))
    _file(data / "video_editor_profiles.json", "{}")
    _file(data / "editor_projects" / "p1.json", "{}")
    _file(data / "dataviz_episodes" / "ep1" / "data.csv", "a,b")
    _file(data / "dataviz_overrides" / "ep1.json", json.dumps({
        "sources": [{"path": os.path.join(root, "dataviz_episodes", "ep1", "data.csv")}, {"path": "relative.csv"}],
        "map": {"geojson": os.path.join(root, "dataviz_maps", "il.geojson")},
        "elsewhere": "C:\\Videos\\clip.mp4"}))
    _file(data / "ffprobe_cache.json", "{}")
    _file(data / "logs" / "web.log", "log")
    _file(data / "backups" / "old.zip", "zip")
    _file(data / "mystery.txt", "?")


def _snapshot(data):
    return sorted(str(p.relative_to(data)) for p in data.rglob("*"))


def test_dry_run_lists_every_move_and_touches_nothing(tmp_path, capsys):
    data = tmp_path / "data"
    _flat_data(data)
    before = _snapshot(data)
    assert mig.main(["--data-dir", str(data)]) == 0
    assert _snapshot(data) == before
    out = capsys.readouterr().out
    assert f"config.json  ->  {os.path.join('settings', 'config.json')}" in out
    assert f"config.json.bak  ->  {os.path.join('settings', 'config.json.bak')}" in out    # הגיבוי עובר עם המקור
    assert f"clipforge_data.db  ->  {os.path.join('bot', 'clipforge_data.db')}" in out
    assert f"dataviz_episodes  ->  {os.path.join('dataviz', 'dataviz_episodes')}   (תיקייה)" in out
    assert "mystery.txt" in out.split("== נשאר במקום - לא שייך")[1]


def test_layout_covers_every_flat_name_in_data_paths():
    # שם חדש ב-data_paths בלי תיקייה כאן היה נשאר בשורש בלי שאף אחד ישים לב
    names = {v for k, v in vars(mig.data_paths).items()
             if k.isupper() and isinstance(v, str) and "/" not in v and not os.path.isabs(v)}
    assert len(names) > 30
    assert names - set(mig.data_paths.FOLDERS) - mig.STAY - {mig.data_paths.DATAVIZ_FOLDER} == set()


def test_the_code_switches_to_the_new_layout_only_after_apply(tmp_path):
    data = tmp_path / "data"
    _flat_data(data)
    dp = mig.data_paths
    assert not dp.migrated(str(data)) and dp.path(dp.CONFIG, str(data)) == str(data / "config.json")
    assert mig.main(["--data-dir", str(data)]) == 0           # יבש - שום סימן
    assert not dp.migrated(str(data))
    assert mig.main(["--data-dir", str(data), "--apply"]) == 0
    assert dp.migrated(str(data))
    for name in (dp.CONFIG, dp.WEB_TOKEN, dp.BOT_DB, dp.ROCKET_COUNTER, dp.EDITOR_PROFILES, dp.FFPROBE_CACHE):
        assert os.path.isfile(dp.path(name, str(data))), name
    assert dp.path(dp.WEB_TOKEN, str(data)) == str(data / "security" / "web_app_token.txt")
    assert open(dp.path(dp.WEB_TOKEN, str(data)), encoding="utf-8").read() == "token"
    assert os.path.isdir(os.path.join(dp.dataviz_root(str(data)), dp.DATAVIZ_EPISODES, "ep1"))
    assert mig.main(["--data-dir", str(data), "--apply"]) == 0   # הרצה חוזרת: אין מה להזיז, ושום דבר לא נשבר
    assert dp.path(dp.CONFIG, str(data)) == str(data / "settings" / "config.json")


def test_a_move_that_fails_midway_puts_everything_back(tmp_path, monkeypatch):
    data = tmp_path / "data"
    _flat_data(data)
    before = {p: (data / p).read_bytes() for p in _snapshot(data) if (data / p).is_file()}
    real_replace, calls = os.replace, []

    def flaky(src, dst):
        calls.append(src)
        if len(calls) == 5:
            raise OSError("הקובץ פתוח בתוכנה אחרת")
        return real_replace(src, dst)

    monkeypatch.setattr(mig.os, "replace", flaky)
    assert mig.main(["--data-dir", str(data), "--apply"]) == 1
    monkeypatch.setattr(mig.os, "replace", real_replace)
    after = {p: (data / p).read_bytes() for p in _snapshot(data) if (data / p).is_file() and not p.startswith("backups")}
    assert after == {p: b for p, b in before.items() if not p.startswith("backups")}   # כל קובץ במקומו, עם אותו תוכן
    assert not mig.data_paths.migrated(str(data))
    assert not any((data / folder).exists() and any((data / folder).iterdir()) for folder in set(mig.data_paths.FOLDERS.values()))


def test_apply_backs_up_moves_and_rewrites_stored_paths(tmp_path):
    data = tmp_path / "data"
    _flat_data(data)
    assert mig.main(["--data-dir", str(data), "--apply"]) == 0

    for rel in ("settings/config.json", "settings/config.json.bak", "security/web_app_token.txt", "bot/clipforge_data.db",
                "bot/counter.txt", "studio/video_editor_profiles.json", "studio/editor_projects/p1.json",
                "dataviz/dataviz_episodes/ep1/data.csv", "cache/ffprobe_cache.json", "logs/web.log", "backups/old.zip",
                "config.example.json", "mystery.txt"):
        assert (data / rel).is_file(), rel
    assert not (data / "config.json").exists()

    rocket = json.loads((data / "settings" / "rocket_settings.json").read_text(encoding="utf-8"))
    assert rocket == {"counter_file_path": os.path.join(str(data), "bot", "counter.txt"), "title": "x"}
    overrides = json.loads((data / "dataviz" / "dataviz_overrides" / "ep1.json").read_text(encoding="utf-8"))
    assert overrides["sources"][0]["path"] == os.path.join(str(data), "dataviz", "dataviz_episodes", "ep1", "data.csv")
    assert overrides["sources"][1]["path"] == "relative.csv"
    assert overrides["map"]["geojson"] == os.path.join(str(data), "dataviz", "dataviz_maps", "il.geojson")
    assert overrides["elsewhere"] == "C:\\Videos\\clip.mp4"

    backups = [p for p in (data / "backups").iterdir() if p.name.startswith("pre-data-layout-")]
    assert len(backups) == 1
    with zipfile.ZipFile(backups[0]) as zf:
        names = set(zf.namelist())
    assert "config.json" in names and "rocket_settings.json" in names and "dataviz_episodes/ep1/data.csv" in names
    assert not any(n.startswith(("logs/", "backups/")) for n in names)


def test_dry_run_on_a_copy_reports_rewrites_against_the_original_folder(tmp_path, capsys):
    original = tmp_path / "real" / "data"
    copy = tmp_path / "copy" / "data"
    _flat_data(copy, stored_root=original)
    assert mig.main(["--data-dir", str(copy), "--stored-root", str(original)]) == 0
    out = capsys.readouterr().out
    assert os.path.join(str(original), "bot", "counter.txt") in out
    assert os.path.join(str(original), "dataviz", "dataviz_episodes", "ep1", "data.csv") in out


def test_existing_target_means_nothing_moves(tmp_path):
    data = tmp_path / "data"
    _flat_data(data)
    _file(data / "settings" / "config.json", '{"newer": true}')
    before = _snapshot(data)
    assert mig.main(["--data-dir", str(data), "--apply"]) == 1
    assert [p for p in _snapshot(data) if not p.startswith("backups")] == [p for p in before if not p.startswith("backups")]
    assert json.loads((data / "settings" / "config.json").read_text(encoding="utf-8")) == {"newer": True}


def test_render_lock_refuses_the_move(tmp_path):
    data = tmp_path / "data"
    _flat_data(data)
    _file(data / "render.lock", "")
    before = _snapshot(data)
    assert mig.main(["--data-dir", str(data), "--apply"]) == 2
    assert _snapshot(data) == before


_STARTUP_PROBE = r"""
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "src"))
from fastapi.testclient import TestClient
from entrypoints import web_app as W
from utils.shared import job_history, state
from utils.video import video_editor_profiles
client = TestClient(W.app)
resp = client.get("/api/rocket_settings", headers={"Authorization": "Bearer " + W.ACCESS_TOKEN})
print(json.dumps({"token": W.TOKEN_PATH, "config": state.CONFIG_FILE, "profiles": video_editor_profiles.PROFILES_PATH,
                  "runs": W._editor_runs_path(), "db": job_history.DB_PATH, "status": resp.status_code, "body": resp.text}))
"""


def test_the_app_starts_from_a_migrated_data_dir(tmp_path):
    # כמו אחרי --apply אמיתי: האפליקציה עולה מתיקייה שהועברה (CLIPFORGE_DATA_DIR) ולוקחת הכל מהתיקיות החדשות
    data = tmp_path / "data"
    _flat_data(data)
    assert mig.main(["--data-dir", str(data), "--apply"]) == 0
    env = {**os.environ, "CLIPFORGE_DATA_DIR": str(data), "CLIPFORGE_WORKSPACE_DIR": str(tmp_path / "workspace"),
           "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, "-c", _STARTUP_PROBE, PROJECT_ROOT], capture_output=True, text=True,
                            encoding="utf-8", env=env, timeout=180)
    assert result.returncode == 0, result.stderr[-3000:]
    seen = json.loads(result.stdout.strip().splitlines()[-1])
    assert seen["token"] == str(data / "security" / "web_app_token.txt")
    assert seen["config"] == str(data / "settings" / "config.json")
    assert seen["profiles"] == str(data / "studio" / "video_editor_profiles.json")
    assert seen["runs"] == str(data / "studio" / "video_editor_runs.json")
    assert seen["db"] == str(data / "bot" / "clipforge_data.db")
    assert seen["status"] == 200
    assert json.loads(seen["body"])["counter"] == 7   # counter.txt ("7") נקרא מ-bot/, דרך rocket_settings.json שב-settings/
