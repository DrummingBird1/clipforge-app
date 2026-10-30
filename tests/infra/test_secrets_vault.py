# tests/infra/test_secrets_vault.py
#
# utils/shared/secrets_vault.py - שכבת Windows Credential Manager (keyring) עם fallback
# ל-.env. keyring עצמו ממופתח לגמרי (לא נוגע ב-Credential Manager האמיתי של
# המחשב בטסטים). מכסה גם את הקישור ל-item: מעקב "גיל מפתח" - set_secret
# אמור לרשום סבב בכל קריאה מוצלחת.


import pytest

from utils.shared import secrets_vault


class _FakeKeyring:
    def __init__(self):
        self.store = {}

    def get_password(self, service, key):
        return self.store.get((service, key))

    def set_password(self, service, key, value):
        self.store[(service, key)] = value

    def delete_password(self, service, key):
        del self.store[(service, key)]


@pytest.fixture(autouse=True)
def _isolate_rotation_path(tmp_path, monkeypatch):
    from utils.shared import credential_rotation as cr
    monkeypatch.setattr(cr, "ROTATION_LOG_PATH", str(tmp_path / "credential_rotation.json"))


def test_get_secret_prefers_keyring_over_env(monkeypatch):
    fake = _FakeKeyring()
    fake.store[(secrets_vault.SERVICE_NAME, "GEMINI_API_KEY")] = "from-vault"
    monkeypatch.setattr(secrets_vault, "keyring", fake)
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert secrets_vault.get_secret("GEMINI_API_KEY") == "from-vault"


def test_get_secret_falls_back_to_env_when_not_in_vault(monkeypatch):
    monkeypatch.setattr(secrets_vault, "keyring", _FakeKeyring())
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert secrets_vault.get_secret("GEMINI_API_KEY") == "from-env"


def test_get_secret_falls_back_to_env_when_keyring_unavailable(monkeypatch):
    monkeypatch.setattr(secrets_vault, "keyring", None)
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert secrets_vault.get_secret("GEMINI_API_KEY") == "from-env"


def test_get_secret_returns_default_when_nowhere_found(monkeypatch):
    monkeypatch.setattr(secrets_vault, "keyring", _FakeKeyring())
    monkeypatch.delenv("SOME_UNSET_KEY", raising=False)
    assert secrets_vault.get_secret("SOME_UNSET_KEY", default="fallback") == "fallback"


def test_set_secret_writes_to_keyring(monkeypatch):
    fake = _FakeKeyring()
    monkeypatch.setattr(secrets_vault, "keyring", fake)
    secrets_vault.set_secret("GEMINI_API_KEY", "new-value")
    assert fake.store[(secrets_vault.SERVICE_NAME, "GEMINI_API_KEY")] == "new-value"


def test_set_secret_raises_when_keyring_unavailable(monkeypatch):
    monkeypatch.setattr(secrets_vault, "keyring", None)
    with pytest.raises(RuntimeError):
        secrets_vault.set_secret("GEMINI_API_KEY", "new-value")


def test_set_secret_records_rotation_timestamp(monkeypatch):
    from utils.shared import credential_rotation as cr
    monkeypatch.setattr(secrets_vault, "keyring", _FakeKeyring())
    assert cr.get_rotation_date("GEMINI_API_KEY") is None
    secrets_vault.set_secret("GEMINI_API_KEY", "new-value")
    assert cr.get_rotation_date("GEMINI_API_KEY") is not None
    assert cr.get_age_days("GEMINI_API_KEY") == 0


def test_delete_secret_removes_from_keyring(monkeypatch):
    fake = _FakeKeyring()
    fake.store[(secrets_vault.SERVICE_NAME, "GEMINI_API_KEY")] = "value"
    monkeypatch.setattr(secrets_vault, "keyring", fake)
    secrets_vault.delete_secret("GEMINI_API_KEY")
    assert (secrets_vault.SERVICE_NAME, "GEMINI_API_KEY") not in fake.store


def test_delete_secret_is_a_no_op_without_keyring(monkeypatch):
    monkeypatch.setattr(secrets_vault, "keyring", None)
    secrets_vault.delete_secret("GEMINI_API_KEY")  # לא אמור לזרוק


def test_delete_secret_swallows_missing_key_error(monkeypatch):
    monkeypatch.setattr(secrets_vault, "keyring", _FakeKeyring())
    secrets_vault.delete_secret("NEVER_SET_KEY")  # לא אמור לזרוק KeyError


def test_is_vault_available_reflects_keyring_presence(monkeypatch):
    monkeypatch.setattr(secrets_vault, "keyring", _FakeKeyring())
    assert secrets_vault.is_vault_available() is True
    monkeypatch.setattr(secrets_vault, "keyring", None)
    assert secrets_vault.is_vault_available() is False
