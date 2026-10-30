# tests/infra/test_update_checker.py
#
# בודק utils/shared/update_checker.py - כל הבדיקה מול GitHub Releases API עצמה
# ממוקת (monkeypatch על requests.get) כדי שהטסטים לא יהיו תלויים ברשת/בקצב
# API אמיתי של GitHub.


import utils.shared.update_checker as update_checker


class _FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


def test_check_for_update_returns_tag_when_newer_version_available(monkeypatch):
    monkeypatch.setattr(
        update_checker.requests, "get",
        lambda *a, **k: _FakeResponse(200, {"tag_name": "v1.2.0"}),
    )
    assert update_checker.check_for_update("1.0.0") == "v1.2.0"


def test_check_for_update_returns_none_when_up_to_date(monkeypatch):
    monkeypatch.setattr(
        update_checker.requests, "get",
        lambda *a, **k: _FakeResponse(200, {"tag_name": "v1.0.0"}),
    )
    assert update_checker.check_for_update("1.0.0") is None


def test_check_for_update_returns_none_when_installed_is_newer(monkeypatch):
    # מקרה קצה: מפתח שרץ על גרסה עתידית שעדיין לא פורסמה כ-release רשמי
    monkeypatch.setattr(
        update_checker.requests, "get",
        lambda *a, **k: _FakeResponse(200, {"tag_name": "v1.0.0"}),
    )
    assert update_checker.check_for_update("1.5.0") is None


def test_check_for_update_returns_none_when_no_releases_published_yet(monkeypatch):
    # 404 - פרויקט חדש שעוד לא פרסם אף release, בדיוק המצב האמיתי של הריפו
    # הזה כרגע. לא אמור לזרוק/לקרוס.
    monkeypatch.setattr(update_checker.requests, "get", lambda *a, **k: _FakeResponse(404))
    assert update_checker.check_for_update("1.0.0") is None


def test_check_for_update_returns_none_on_network_error(monkeypatch):
    def _raise(*a, **k):
        raise ConnectionError("no network")
    monkeypatch.setattr(update_checker.requests, "get", _raise)
    assert update_checker.check_for_update("1.0.0") is None


def test_version_tuple_handles_v_prefix_and_numeric_ordering():
    # "1.9.0" < "1.10.0" מספרית, למרות ש-"1.9.0" > "1.10.0" מחרוזתית
    assert update_checker._version_tuple("v1.9.0") < update_checker._version_tuple("v1.10.0")
    assert update_checker._version_tuple("1.2.0") == (1, 2, 0)


def test_check_for_update_handles_missing_tag_name(monkeypatch):
    monkeypatch.setattr(update_checker.requests, "get", lambda *a, **k: _FakeResponse(200, {}))
    assert update_checker.check_for_update("1.0.0") is None


# --- apply_update (item: true auto-update) ---

class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_apply_update_refuses_when_working_tree_is_dirty(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["git", "status"]:
            return _FakeCompletedProcess(0, stdout=" M some_file.py\n")
        raise AssertionError(f"should not reach: {cmd}")

    monkeypatch.setattr(update_checker.subprocess, "run", fake_run)
    ok, message = update_checker.apply_update("C:\\fake\\repo")

    assert ok is False
    assert "שינויים מקומיים" in message
    assert len(calls) == 1  # git pull/uv sync never attempted


def test_apply_update_succeeds_on_clean_tree(monkeypatch):
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return _FakeCompletedProcess(0, stdout="")
        if cmd[:2] == ["git", "pull"]:
            assert "--ff-only" in cmd
            return _FakeCompletedProcess(0, stdout="Already up to date... actually updated")
        if cmd[:2] == ["uv", "sync"]:
            return _FakeCompletedProcess(0)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(update_checker.subprocess, "run", fake_run)
    ok, message = update_checker.apply_update("C:\\fake\\repo")

    assert ok is True
    assert "בהצלחה" in message


def test_apply_update_reports_git_pull_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return _FakeCompletedProcess(0, stdout="")
        if cmd[:2] == ["git", "pull"]:
            return _FakeCompletedProcess(1, stderr="fatal: not possible to fast-forward")
        raise AssertionError(f"uv sync should not run after a failed pull: {cmd}")

    monkeypatch.setattr(update_checker.subprocess, "run", fake_run)
    ok, message = update_checker.apply_update("C:\\fake\\repo")

    assert ok is False
    assert "git pull נכשל" in message
    assert "fast-forward" in message


def test_apply_update_reports_uv_sync_failure_after_successful_pull(monkeypatch):
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return _FakeCompletedProcess(0, stdout="")
        if cmd[:2] == ["git", "pull"]:
            return _FakeCompletedProcess(0, stdout="Updated")
        if cmd[:2] == ["uv", "sync"]:
            return _FakeCompletedProcess(1, stderr="dependency resolution failed")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(update_checker.subprocess, "run", fake_run)
    ok, message = update_checker.apply_update("C:\\fake\\repo")

    assert ok is False
    assert "uv sync נכשל" in message
    assert "dependency resolution failed" in message


def test_apply_update_never_uses_force_or_merge_flags(monkeypatch):
    seen_cmds = []

    def fake_run(cmd, **kwargs):
        seen_cmds.append(cmd)
        if cmd[:2] == ["git", "status"]:
            return _FakeCompletedProcess(0, stdout="")
        if cmd[:2] == ["git", "pull"]:
            return _FakeCompletedProcess(0)
        return _FakeCompletedProcess(0)

    monkeypatch.setattr(update_checker.subprocess, "run", fake_run)
    update_checker.apply_update("C:\\fake\\repo")

    for cmd in seen_cmds:
        assert "--force" not in cmd
        assert "-f" not in cmd
        assert "reset" not in cmd


def test_apply_update_handles_git_status_exception_gracefully(monkeypatch):
    def _raise(cmd, **kwargs):
        raise OSError("git not found")
    monkeypatch.setattr(update_checker.subprocess, "run", _raise)

    ok, message = update_checker.apply_update("C:\\fake\\repo")

    assert ok is False
    assert "git" in message.lower()
