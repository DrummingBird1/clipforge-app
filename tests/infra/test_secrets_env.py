# tests/infra/test_secrets_env.py
#
# load_project_env: מפתח שנמצא רק ב-.env (לא ב-Credential Manager) חייב להיראות מוגדר גם בתהליך השרת,
# כמו שהוא נראה בסקריפטים - אחרת בדיקת התקינות בהפעלה מתריעה "חסר" שלא לצורך.
import os
from tests import PROJECT_ROOT

from utils.shared import diagnostics as diagnostics_module
from utils.shared import secrets_vault


def test_env_file_value_becomes_visible_without_overriding_existing_variables(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("FAKE_ONLY_IN_ENV_FILE=from-file\nFAKE_ALREADY_SET=from-file\n", encoding="utf-8")
    monkeypatch.delenv("FAKE_ONLY_IN_ENV_FILE", raising=False)
    monkeypatch.setenv("FAKE_ALREADY_SET", "from-real-env")
    monkeypatch.setattr(secrets_vault, "keyring", None)

    assert secrets_vault.get_secret("FAKE_ONLY_IN_ENV_FILE") == ""
    assert secrets_vault.load_project_env(str(env_file)) is True
    assert secrets_vault.get_secret("FAKE_ONLY_IN_ENV_FILE") == "from-file"
    assert os.environ["FAKE_ALREADY_SET"] == "from-real-env"
    monkeypatch.delenv("FAKE_ONLY_IN_ENV_FILE", raising=False)


def test_missing_env_file_is_not_an_error(tmp_path):
    assert secrets_vault.load_project_env(str(tmp_path / "nope.env")) is False


def test_startup_health_sees_a_gemini_key_that_only_lives_in_the_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=fake-key-for-tests\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(secrets_vault, "keyring", None)
    assert diagnostics_module._check_gemini_key()[1] is False

    secrets_vault.load_project_env(str(env_file))

    assert diagnostics_module._check_gemini_key()[1] is True
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_web_server_loads_the_env_file_before_the_startup_health_check():
    source = open(os.path.join(PROJECT_ROOT, "src", "entrypoints", "web_app.py"),
                  encoding="utf-8").read()
    assert source.index("load_project_env()") < source.index("print_startup_health()")