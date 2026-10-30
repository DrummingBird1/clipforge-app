# tests/infra/test_install_profile.py
#
# 30.10.2026 (לפני ההפצה הציבורית): הגדרות ב-config.json עם ברירות מחדל ניטרליות - אותן בכל התקנה - ושפה שנקבעת פעם
# אחת (חדשה = אנגלית, קיימת = עברית), נכתבות לקובץ פעם אחת (utils/shared/install_profile). ערך שהמשתמש קבע נשאר. וגם:
# התחזוקה היומית והסיכום היומי רצים בשעון המקומי, לא ב-UTC.
import datetime
import json

from utils.shared import install_profile

NEW = install_profile.DEFAULTS


def _ensure(tmp_path):
    return install_profile.ensure(str(tmp_path / "config.json"), str(tmp_path / "config.json.lock"))


def _saved(tmp_path):
    return json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))


def test_a_new_install_gets_neutral_values_written_once(tmp_path):
    assert install_profile.read(str(tmp_path / "config.json"))["steam_country"] == "us"
    settings = _ensure(tmp_path)
    assert (settings["rss_keywords"], settings["steam_country"], settings["steam_language"], settings["docker_container"]) == (
        [], "us", "english", "")
    assert _saved(tmp_path) == {**NEW, "language": "en"}


def test_an_existing_install_keeps_hebrew_and_gets_the_same_neutral_defaults(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"theme": "Pink"}), encoding="utf-8")
    settings = _ensure(tmp_path)
    assert (settings["language"], settings["steam_country"], settings["docker_container"], settings["rss_keywords"]) == (
        "he", "us", "", [])
    assert _saved(tmp_path) == {**NEW, "theme": "Pink", "language": "he"}
    before = (tmp_path / "config.json").read_bytes()
    _ensure(tmp_path)
    assert (tmp_path / "config.json").read_bytes() == before   # פעם אחת


def test_an_english_install_without_the_keys_is_a_new_one_and_own_values_are_kept(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"language": "en", "steam_country": "de"}), encoding="utf-8")
    settings = _ensure(tmp_path)
    assert (settings["steam_country"], settings["steam_language"], settings["docker_container"]) == ("de", "english", "")


def test_a_broken_config_is_not_overwritten(tmp_path):
    (tmp_path / "config.json").write_text("{not json", encoding="utf-8")
    assert _ensure(tmp_path)["docker_container"] == ""
    assert (tmp_path / "config.json").read_text(encoding="utf-8") == "{not json"


def test_the_desktop_keeps_the_keys_it_does_not_own_when_it_saves(tmp_path, monkeypatch):
    from utils.shared import state as state_module
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"language": "he", "rss_keywords": ["mine"], "steam_country": "fr"}), encoding="utf-8")
    monkeypatch.setattr(state_module, "CONFIG_FILE", str(config))
    monkeypatch.setattr(state_module, "CONFIG_LOCK_FILE", str(config) + ".lock")
    app_state = state_module.state
    for _key, (attr, _type, _default) in state_module.CONFIG_SCHEMA.items():   # load_config משנה את ה-singleton - מחזירים אחרי
        monkeypatch.setattr(app_state, attr, getattr(app_state, attr))
    monkeypatch.setattr(app_state, "ui_settings", dict(app_state.ui_settings))
    app_state.load_config()
    assert app_state.docker_container == ""   # קובץ בלי המפתח - בלי Docker
    app_state.save_config()
    saved = json.loads(config.read_text(encoding="utf-8"))
    assert (saved["rss_keywords"], saved["steam_country"], saved["docker_container"]) == (["mine"], "fr", "")


def test_the_daily_jobs_run_on_local_time():
    from cogs import approval_cog, scheduler_cog
    local = datetime.datetime.now().astimezone().utcoffset()
    for at, hour in ((scheduler_cog.DAILY_RUN_TIME, 4), (approval_cog.DAILY_DIGEST_TIME, 20)):
        assert at.hour == hour and at.tzinfo is not None
        assert at.tzinfo.utcoffset(None) == local


def test_steam_asks_for_the_configured_store(monkeypatch):
    import asyncio
    from cogs import steam_monitor

    seen = []

    class _Response:
        status = 404

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _Session:
        def get(self, url):
            seen.append(url)
            return _Response()

    asyncio.run(steam_monitor._fetch_appdetails(_Session(), "111", "de", "german"))
    assert seen == ["https://store.steampowered.com/api/appdetails?appids=111&cc=de&l=german"]
