# tests/bot/test_youtube_uploader.py
import json
from types import SimpleNamespace


import utils.bot.youtube_uploader as youtube_uploader
from utils.bot.youtube_uploader import _is_retryable_upload_error, is_configured


def test_is_configured_false_when_client_secrets_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_uploader, "CLIENT_SECRETS_FILE", str(tmp_path / "client_secret.json"))
    assert is_configured() is False


def test_is_configured_true_when_client_secrets_present(monkeypatch, tmp_path):
    secrets_path = tmp_path / "client_secret.json"
    secrets_path.write_text("{}")
    monkeypatch.setattr(youtube_uploader, "CLIENT_SECRETS_FILE", str(secrets_path))
    assert is_configured() is True


def test_retryable_on_5xx_http_status():
    exc = Exception("server error")
    exc.resp = SimpleNamespace(status=503)
    assert _is_retryable_upload_error(exc) is True


def test_not_retryable_on_4xx_http_status():
    exc = Exception("bad request")
    exc.resp = SimpleNamespace(status=400)
    assert _is_retryable_upload_error(exc) is False


def test_retryable_on_network_errors():
    assert _is_retryable_upload_error(ConnectionError("connection reset")) is True
    assert _is_retryable_upload_error(TimeoutError("timed out")) is True
    assert _is_retryable_upload_error(OSError("socket error")) is True


def test_not_retryable_on_generic_exception_without_http_status():
    assert _is_retryable_upload_error(ValueError("bad input")) is False


# --- _get_credentials scope-checking / re-consent (item: YouTube Analytics feedback loop) ---

class _FakeCreds:
    def __init__(self, valid, expired, refresh_token, scopes):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.scopes = scopes
        self.refreshed = False

    def refresh(self, request):
        self.refreshed = True
        self.valid = True

    def to_json(self):
        return json.dumps({"scopes": self.scopes})


def _patch_google_auth(monkeypatch, cached_creds, flow_creds):
    import google.auth.transport.requests
    import google.oauth2.credentials
    import google_auth_oauthlib.flow

    monkeypatch.setattr(google.oauth2.credentials.Credentials, "from_authorized_user_file", staticmethod(lambda path, scopes: cached_creds))
    monkeypatch.setattr(google.auth.transport.requests, "Request", lambda: None)

    flow = SimpleNamespace(run_local_server=lambda port: flow_creds)
    monkeypatch.setattr(google_auth_oauthlib.flow.InstalledAppFlow, "from_client_secrets_file", staticmethod(lambda path, scopes: flow))
    return flow


def test_get_credentials_returns_cached_token_when_valid_with_all_scopes(tmp_path, monkeypatch):
    token_path = tmp_path / "youtube_token.json"
    token_path.write_text("{}")
    monkeypatch.setattr(youtube_uploader, "TOKEN_FILE", str(token_path))
    cached = _FakeCreds(valid=True, expired=False, refresh_token="rt", scopes=youtube_uploader.SCOPES)
    flow_creds = _FakeCreds(valid=True, expired=False, refresh_token="rt", scopes=youtube_uploader.SCOPES)
    _patch_google_auth(monkeypatch, cached, flow_creds)

    result = youtube_uploader._get_credentials()

    assert result is cached
    assert cached.refreshed is False


def test_get_credentials_refreshes_expired_token_that_already_has_all_scopes(tmp_path, monkeypatch):
    token_path = tmp_path / "youtube_token.json"
    token_path.write_text("{}")
    monkeypatch.setattr(youtube_uploader, "TOKEN_FILE", str(token_path))
    cached = _FakeCreds(valid=False, expired=True, refresh_token="rt", scopes=youtube_uploader.SCOPES)
    flow_creds = _FakeCreds(valid=True, expired=False, refresh_token="rt", scopes=youtube_uploader.SCOPES)
    _patch_google_auth(monkeypatch, cached, flow_creds)

    result = youtube_uploader._get_credentials()

    assert result is cached
    assert cached.refreshed is True


def test_get_credentials_triggers_reauth_when_cached_token_missing_readonly_scope(tmp_path, monkeypatch):
    """טוקן ישן שאושר לפני שנוסף READONLY_SCOPE - עדיין 'valid' טכנית, אבל
    בלי הרשאה שנדרשת עכשיו. חייב לעבור הסכמה מחדש, לא רק refresh."""
    token_path = tmp_path / "youtube_token.json"
    token_path.write_text("{}")
    monkeypatch.setattr(youtube_uploader, "TOKEN_FILE", str(token_path))
    cached = _FakeCreds(valid=True, expired=False, refresh_token="rt", scopes=[youtube_uploader.UPLOAD_SCOPE])
    flow_creds = _FakeCreds(valid=True, expired=False, refresh_token="rt", scopes=youtube_uploader.SCOPES)
    _patch_google_auth(monkeypatch, cached, flow_creds)

    result = youtube_uploader._get_credentials()

    assert result is flow_creds
    assert cached.refreshed is False


def test_get_credentials_triggers_reauth_when_no_token_file_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_uploader, "TOKEN_FILE", str(tmp_path / "nonexistent_token.json"))
    flow_creds = _FakeCreds(valid=True, expired=False, refresh_token="rt", scopes=youtube_uploader.SCOPES)
    _patch_google_auth(monkeypatch, None, flow_creds)

    result = youtube_uploader._get_credentials()

    assert result is flow_creds


def test_get_credentials_writes_token_file_after_reauth(tmp_path, monkeypatch):
    token_path = tmp_path / "youtube_token.json"
    monkeypatch.setattr(youtube_uploader, "TOKEN_FILE", str(token_path))
    flow_creds = _FakeCreds(valid=True, expired=False, refresh_token="rt", scopes=youtube_uploader.SCOPES)
    _patch_google_auth(monkeypatch, None, flow_creds)

    youtube_uploader._get_credentials()

    assert token_path.exists()
    assert json.loads(token_path.read_text())["scopes"] == youtube_uploader.SCOPES
