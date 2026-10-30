# tests/infra/test_data_paths.py
#
# 23.10.2026 (פריט 19, שלב א'): כל השמות ב-data/ במקום אחד - utils/shared/data_paths.py. כאן: שאף אחד לא חוזר להדביק
# שם בעצמו על DATA_DIR, ושלושת המקומות שסורקים את data/ כולה (שני הגיבויים והאבחון) וה-.gitignore ימשיכו לעבוד כשהקבצים
# יעברו לתיקיות לפי נושא (שלב ב'). שום טסט כאן לא נוגע ב-data/ האמיתית - DATA_DIR זמני לכל טסט.
import json
import os
import re
import sqlite3
import subprocess
import zipfile

import pytest

from utils.shared import data_paths, diagnostics, encrypted_backup, job_history, notification_log, state
from utils.shared.data_dir import PROJECT_ROOT

CODE_DIRS = ("src", "my_scripts", "dev")
JOIN_LITERAL = re.compile(r"""os\.path\.join\((DATA_DIR|W\.DATA_DIR|web_app\.DATA_DIR|data_dir), ["'](?!\*)""")   # לא glob ("*.json")
DATAVIZ_LITERAL = re.compile(r"""^[A-Z_]+ = ["']dataviz_(episodes|overrides|history|smart|trash|variants|cache|maps)""", re.M)
OWN = {os.path.join("src", "utils", "shared", "data_paths.py"), os.path.join("src", "utils", "shared", "data_dir.py")}


def _code_files():
    for top in CODE_DIRS:
        for root, _dirs, files in os.walk(os.path.join(PROJECT_ROOT, top)):
            for name in files:
                if name.endswith(".py"):
                    path = os.path.join(root, name)
                    rel = os.path.relpath(path, PROJECT_ROOT)
                    if rel not in OWN:
                        yield rel, path


def _names():
    return {key: value for key, value in vars(data_paths).items() if key.isupper() and isinstance(value, str) and key != "DATA_DIR"}


def test_no_one_glues_a_name_onto_data_dir_by_hand():
    offenders = []
    for rel, path in _code_files():
        with open(path, encoding="utf-8") as f:
            text = f.read()
        offenders += [f"{rel}: {m.group(0)}" for m in JOIN_LITERAL.finditer(text)]
        offenders += [f"{rel}: {m.group(0)}" for m in DATAVIZ_LITERAL.finditer(text)]
    assert offenders == [], "שם קובץ ב-data/ - להוסיף ל-utils/shared/data_paths.py ולהשתמש בו:\n" + "\n".join(offenders)


def test_every_name_is_unique_and_stays_under_data():
    names = _names()
    assert len(set(names.values())) == len(names), "שני קבועים לאותו שם"
    for key, name in names.items():
        assert not os.path.isabs(name) and ".." not in name.split("/"), key
        assert data_paths.relative(data_paths.path(name)) == name, key


def test_modules_take_their_paths_from_here():
    assert job_history.DB_PATH == notification_log.DB_PATH == data_paths.path(data_paths.BOT_DB)
    assert state.CONFIG_FILE == data_paths.path(data_paths.CONFIG)
    assert encrypted_backup.BACKUPS_DIR == data_paths.path(data_paths.BACKUPS)


@pytest.mark.parametrize("path, ignored", [
    ("data/web_app_token.txt", True), ("data/security/web_app_token.txt", True), ("data/security/web_app_tls_key.pem", True),
    ("data/settings/paired_devices.json", True), ("data/bot/logs/bot.log", True), ("data/dataviz/dataviz_overrides/x.json", True),
    ("data/config.example.json", False), ("data/rocket_settings.example.json", False),
    # 30.10.2026: data/ כולה מחוץ לגיט, גם הפרקים והפרויקטים - רק קובצי הדוגמה בשורש נשארים
    ("data/dataviz/dataviz_episodes/alarms/config.yaml", True), ("data/dataviz_episodes/alarms/config.yaml", True),
    ("data/studio/editor_projects/p.json", True), ("data/settings/config.json", True), ("data/bot/clipforge_data.db", True),
    ("data/settings/config.example.json", True), ("temp_analysis/report.txt", True), ("workspace/vertical/a.mp4", True),
])
def test_user_data_stays_out_of_git_in_any_subfolder(path, ignored):
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=PROJECT_ROOT, capture_output=True)
    assert (result.returncode == 0) is ignored, path


def _make_db(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE t (x)")
        conn.execute("INSERT INTO t VALUES (1)")
    conn.close()


def test_the_encrypted_backup_finds_the_database_wherever_it_moves(tmp_path, monkeypatch):
    monkeypatch.setattr(data_paths, "BOT_DB", "bot/clipforge_data.db")
    _make_db(str(tmp_path / "bot" / "clipforge_data.db"))
    (tmp_path / "settings").mkdir()
    (tmp_path / "settings" / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "bot" / "logs").mkdir()
    (tmp_path / "bot" / "logs" / "bot.log").write_text("x", encoding="utf-8")
    payload, included = encrypted_backup._build_zip_bytes(str(tmp_path))
    names = zipfile.ZipFile(__import__("io").BytesIO(payload)).namelist()
    assert names.count("bot/clipforge_data.db") == 1                      # snapshot אחד, לא גם הקובץ החי
    assert os.path.join("settings", "config.json") in included and not any("bot.log" in n for n in names)


def test_diagnostics_check_known_files_in_a_subfolder(tmp_path, monkeypatch):
    monkeypatch.setattr(data_paths, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(diagnostics, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(data_paths, "CONFIG", "settings/config.json")
    monkeypatch.setattr(data_paths, "CHECKED_JSON", (data_paths.CONFIG,))
    (tmp_path / "settings").mkdir()
    (tmp_path / "settings" / "config.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "top.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    _name, ok, detail = diagnostics._check_data_json_files()
    assert ok is False and "config.json" in detail
    (tmp_path / "settings" / "config.json").write_text("{}", encoding="utf-8")
    _name, ok, detail = diagnostics._check_data_json_files()
    assert ok is True and "2" in detail


def test_the_daily_backup_skips_by_name_from_here():
    from cogs import scheduler_cog
    assert scheduler_cog._DATA_BACKUP_EXCLUDE_DIRNAMES == data_paths.BACKUP_SKIP_DIRS == {"backups", "logs"}
    assert scheduler_cog._DATA_BACKUP_EXCLUDE_FILENAMES == data_paths.BACKUP_SKIP_FILES == {"clipforge_data.db", "render.lock"}


# --- 24.10.2026 (שלב ג'): המבנה לפי נושא, רק אחרי ש-dev/migrate_data_layout.py --apply כתב את הסימן ---

def _migrated_dir(tmp_path):
    (tmp_path / data_paths.LAYOUT_MARKER).write_text("2\n", encoding="utf-8")
    return str(tmp_path)


def test_without_the_marker_everything_stays_flat_even_if_folders_exist(tmp_path):
    (tmp_path / "settings").mkdir()
    (tmp_path / "settings" / "config.json").write_text("{}", encoding="utf-8")
    assert not data_paths.migrated(str(tmp_path))
    assert data_paths.path(data_paths.CONFIG, str(tmp_path)) == os.path.join(str(tmp_path), "config.json")
    assert data_paths.dataviz_root(str(tmp_path)) == str(tmp_path)


def test_after_the_move_names_resolve_to_their_topic_folder(tmp_path):
    data = _migrated_dir(tmp_path)
    expected = {data_paths.CONFIG: "settings", data_paths.WEB_TOKEN: "security", data_paths.BOT_DB: "bot",
                data_paths.EDITOR_PROFILES: "studio", data_paths.DATAVIZ_EPISODES: "dataviz", data_paths.FFPROBE_CACHE: "cache"}
    for name, folder in expected.items():
        assert data_paths.path(name, data) == os.path.join(data, folder, name), name   # גם כשעוד לא קיים - כתיבה חדשה הולכת לשם
    assert data_paths.path(data_paths.LOGS, data) == os.path.join(data, "logs")
    assert data_paths.path(data_paths.SEO_HISTORY_LOG, data) == os.path.join(data, "logs", "seo_history_log.txt")
    assert data_paths.dataviz_root(data) == os.path.join(data, "dataviz")


def test_after_the_move_a_name_that_exists_only_flat_is_read_from_there(tmp_path):
    data = _migrated_dir(tmp_path)
    (tmp_path / "config.json").write_text('{"restored": 1}', encoding="utf-8")
    assert data_paths.path(data_paths.CONFIG, data) == os.path.join(data, "config.json")
    (tmp_path / "settings").mkdir()
    (tmp_path / "settings" / "config.json").write_text("{}", encoding="utf-8")
    assert data_paths.path(data_paths.CONFIG, data) == os.path.join(data, "settings", "config.json")   # שניהם קיימים - החדש


def test_the_graph_editor_two_levels_above_an_episode_is_its_root_in_both_layouts(tmp_path):
    from dataviz.web import episodes as de
    for data, migrated in ((tmp_path / "flat", False), (tmp_path / "moved", True)):
        data.mkdir()
        if migrated:
            _migrated_dir(data)
        root = data_paths.dataviz_root(str(data))
        os.makedirs(os.path.join(root, de.OVERRIDES_DIRNAME))
        with open(de.overrides_path(root, "ep1"), "w", encoding="utf-8") as f:
            json.dump({"title": "x"}, f)
        episode = os.path.join(data_paths.path(data_paths.DATAVIZ_EPISODES, str(data)), "ep1")
        assert os.path.dirname(os.path.dirname(episode)) == root
        assert de.load_overrides_for_path(episode) == {"title": "x"}, data


def test_localize_maps_backup_names_to_the_current_layout(tmp_path):
    flat, moved = str(tmp_path / "flat"), _migrated_dir(tmp_path)
    assert data_paths.localize("config.json", moved) == "settings/config.json"
    assert data_paths.localize("config.json.bak", moved) == "settings/config.json.bak"
    assert data_paths.localize(r"dataviz_episodes\ep1\config.yaml", moved) == "dataviz/dataviz_episodes/ep1/config.yaml"
    assert data_paths.localize("settings/config.json", moved) == "settings/config.json"
    assert data_paths.localize("settings/config.json", flat) == "config.json"
    assert data_paths.localize("bot/clipforge_data.db", flat) == "clipforge_data.db"
    assert data_paths.localize("logs/web.log", moved) == "logs/web.log"
    assert data_paths.localize("mystery/thing.txt", moved) == "mystery/thing.txt"


def _backup_of(tmp_path, data, passphrase="pw"):
    out = str(tmp_path / f"b_{os.path.basename(data)}.cfbak")
    encrypted_backup.create_backup_bundle(passphrase, out, data_dir=data)
    return out


@pytest.mark.parametrize("source_moved, target_moved", [(False, True), (True, False), (True, True)])
def test_an_encrypted_backup_restores_into_either_layout(tmp_path, source_moved, target_moved):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    if source_moved:
        _migrated_dir(source)
    if target_moved:
        _migrated_dir(target)
    _make_db(data_paths.path(data_paths.BOT_DB, str(source)))
    for name, content in ((data_paths.CONFIG, '{"a": 1}'), (data_paths.WEB_TOKEN, "tok")):
        path = data_paths.path(name, str(source))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    encrypted_backup.restore_backup_bundle("pw", _backup_of(tmp_path, str(source)), data_dir=str(target))
    with open(data_paths.path(data_paths.CONFIG, str(target)), encoding="utf-8") as f:
        assert json.load(f) == {"a": 1}
    with open(data_paths.path(data_paths.WEB_TOKEN, str(target)), encoding="utf-8") as f:
        assert f.read() == "tok"
    with sqlite3.connect(data_paths.path(data_paths.BOT_DB, str(target))) as conn:
        assert conn.execute("SELECT x FROM t").fetchall() == [(1,)]
    conn.close()
    assert data_paths.migrated(str(target)) is target_moved   # הסימן לא משוחזר מהגיבוי - המבנה של היעד קובע
    leftovers = {p.name for p in target.iterdir()} - {data_paths.LAYOUT_MARKER}
    assert leftovers == ({"settings", "security", "bot"} if target_moved else {"config.json", "web_app_token.txt", "clipforge_data.db"})


def test_a_new_install_starts_in_the_topic_folders(tmp_path):
    """30.10.2026: data/ חדשה (ריקה, או רק עם הדוגמאות של git) מקבלת את הסימן מיד - אין מה להעביר."""
    fresh = tmp_path / "fresh"
    assert data_paths.adopt_layout_if_new(str(fresh)) is True
    assert data_paths.migrated(str(fresh))
    assert data_paths.path(data_paths.CONFIG, str(fresh)) == str(fresh / "settings" / "config.json")
    assert data_paths.adopt_layout_if_new(str(fresh)) is False   # פעם אחת

    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "config.example.json").write_text("{}", encoding="utf-8")
    (clone / "logs").mkdir()
    assert data_paths.adopt_layout_if_new(str(clone)) is True


def test_an_existing_flat_data_folder_is_not_marked_without_moving_it(tmp_path):
    for leftover in ("config.json", "config.json.bak", "editor_projects"):
        data = tmp_path / leftover.replace(".", "_")
        data.mkdir()
        if leftover == "editor_projects":
            (data / leftover).mkdir()
        else:
            (data / leftover).write_text("{}", encoding="utf-8")
        assert data_paths.adopt_layout_if_new(str(data)) is False, leftover
        assert not data_paths.migrated(str(data))


_FIRST_RUN = r'''
import os, sqlite3, sys
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
from utils.shared import data_dir
data_dir.DATA_DIR = sys.argv[1]   # לפני data_paths - הייבוא שלו מאמץ את המבנה, כמו בהפעלה הראשונה של החבילה
from utils.shared import data_paths
from utils.shared.atomic_write import atomic_write_json
with open(data_paths.path(data_paths.WEB_TOKEN), "w", encoding="utf-8") as f:   # web_app._persist_token
    f.write("token")
sqlite3.connect(data_paths.path(data_paths.BOT_DB)).execute("CREATE TABLE IF NOT EXISTS t (x)")
atomic_write_json(data_paths.path(data_paths.CONFIG), {"language": "en"})
with open(data_paths.path(data_paths.FFPROBE_CACHE), "w", encoding="utf-8") as f:
    f.write("{}")
print("ok")
'''


def test_the_first_run_of_a_new_install_can_write_into_every_topic_folder(tmp_path):
    """30.10.2026: החבילה הניידת קרסה בהפעלה הראשונה - adopt_layout_if_new כתב את הסימן בלי ליצור את התיקיות, ו-web_app
    לא הצליח לכתוב את data/security/web_app_token.txt. כאן בלי CLIPFORGE_DATA_DIR, כמו אצל משתמש, על תיקייה ריקה."""
    import subprocess
    import sys
    data = tmp_path / "data"
    env = {k: v for k, v in os.environ.items() if k != "CLIPFORGE_DATA_DIR"}
    result = subprocess.run([sys.executable, "-c", _FIRST_RUN, str(data)], cwd=PROJECT_ROOT, env=env, capture_output=True,
                            text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0 and "ok" in result.stdout, result.stderr[-2000:]
    assert data_paths.migrated(str(data))
    for folder in set(data_paths.FOLDERS.values()):
        assert (data / folder).is_dir(), folder
    assert (data / "security" / "web_app_token.txt").read_text(encoding="utf-8") == "token"
    assert (data / "bot" / data_paths.BOT_DB).is_file() and (data / "settings" / "config.json").is_file()


def test_adopting_the_layout_creates_the_topic_folders(tmp_path):
    fresh = tmp_path / "fresh"
    assert data_paths.adopt_layout_if_new(str(fresh)) is True
    assert {p.name for p in fresh.iterdir() if p.is_dir()} == set(data_paths.FOLDERS.values())
    (fresh / "studio").rmdir()   # תיקייה שנמחקה אחרי ההעברה חוזרת בהפעלה הבאה
    data_paths.ensure_folders(str(fresh))
    assert (fresh / "studio").is_dir()
