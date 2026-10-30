# tests/web/test_web_dashboard.py
#
# בודק את התוספת ל-web_dashboard.py (item: "מרכז שליטה" כללי לכל הבוטים/
# שרתים המקומיים) - discover_sibling_projects()/_is_project_folder_active()
# הן קריאה-בלבד לגמרי, בלי תלות בתהליכים אמיתיים (psutil ממופתח).


from entrypoints import web_dashboard


# --- discover_sibling_projects ---

def test_discover_sibling_projects_finds_folders_under_known_categories(tmp_path, monkeypatch):
    (tmp_path / "Bots" / "SomeBot").mkdir(parents=True)
    (tmp_path / "Apps" / "SomeApp").mkdir(parents=True)
    monkeypatch.setattr(web_dashboard, "_is_project_folder_active", lambda path: False)

    results = web_dashboard.discover_sibling_projects(projects_root=str(tmp_path))

    names = {name for name, _rel, _active in results}
    assert names == {"SomeBot", "SomeApp"}


def test_discover_sibling_projects_excludes_this_projects_own_folder(tmp_path, monkeypatch):
    own_dir = tmp_path / "Bots" / "Python"
    own_dir.mkdir(parents=True)
    (tmp_path / "Bots" / "OtherBot").mkdir(parents=True)
    monkeypatch.setattr(web_dashboard, "BASE_DIR", str(own_dir))
    monkeypatch.setattr(web_dashboard, "_is_project_folder_active", lambda path: False)

    results = web_dashboard.discover_sibling_projects(projects_root=str(tmp_path))

    names = {name for name, _rel, _active in results}
    assert "Python" not in names
    assert "OtherBot" in names


def test_discover_sibling_projects_ignores_files_not_directories(tmp_path, monkeypatch):
    bots_dir = tmp_path / "Bots"
    bots_dir.mkdir()
    (bots_dir / "not_a_project.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(web_dashboard, "_is_project_folder_active", lambda path: False)

    results = web_dashboard.discover_sibling_projects(projects_root=str(tmp_path))

    assert results == []


def test_discover_sibling_projects_returns_empty_list_when_root_missing():
    assert web_dashboard.discover_sibling_projects(projects_root="Z:\\does_not_exist_at_all") == []


def test_discover_sibling_projects_ignores_unrecognized_top_level_folders(tmp_path, monkeypatch):
    (tmp_path / "SomeRandomFolder" / "Project").mkdir(parents=True)
    monkeypatch.setattr(web_dashboard, "_is_project_folder_active", lambda path: False)

    results = web_dashboard.discover_sibling_projects(projects_root=str(tmp_path))

    assert results == []


def test_discover_sibling_projects_reports_relative_path_with_category(tmp_path, monkeypatch):
    (tmp_path / "Tools" / "MyTool").mkdir(parents=True)
    monkeypatch.setattr(web_dashboard, "_is_project_folder_active", lambda path: False)

    results = web_dashboard.discover_sibling_projects(projects_root=str(tmp_path))

    assert results == [("MyTool", "Tools/MyTool", False)]


def test_discover_sibling_projects_sorted_alphabetically_case_insensitive(tmp_path, monkeypatch):
    (tmp_path / "Apps" / "zeta").mkdir(parents=True)
    (tmp_path / "Apps" / "Alpha").mkdir(parents=True)
    monkeypatch.setattr(web_dashboard, "_is_project_folder_active", lambda path: False)

    results = web_dashboard.discover_sibling_projects(projects_root=str(tmp_path))

    assert [name for name, _rel, _active in results] == ["Alpha", "zeta"]


# --- _is_project_folder_active ---

def test_is_project_folder_active_returns_none_without_psutil(monkeypatch):
    monkeypatch.setattr(web_dashboard, "psutil", None)
    assert web_dashboard._is_project_folder_active("C:\\some\\folder") is None


def test_is_project_folder_active_true_when_process_cwd_matches(tmp_path, monkeypatch):
    class _FakeProc:
        def __init__(self, info):
            self.info = info

    fake_psutil = type("FakePsutil", (), {
        "process_iter": staticmethod(lambda attrs: [_FakeProc({"cwd": str(tmp_path), "cmdline": []})]),
    })()
    monkeypatch.setattr(web_dashboard, "psutil", fake_psutil)

    assert web_dashboard._is_project_folder_active(str(tmp_path)) is True


def test_is_project_folder_active_true_when_cmdline_mentions_folder(tmp_path, monkeypatch):
    class _FakeProc:
        def __init__(self, info):
            self.info = info

    fake_psutil = type("FakePsutil", (), {
        "process_iter": staticmethod(lambda attrs: [_FakeProc({"cwd": None, "cmdline": ["python", str(tmp_path / "main.py")]})]),
    })()
    monkeypatch.setattr(web_dashboard, "psutil", fake_psutil)

    assert web_dashboard._is_project_folder_active(str(tmp_path)) is True


def test_is_project_folder_active_false_when_nothing_matches(tmp_path, monkeypatch):
    class _FakeProc:
        def __init__(self, info):
            self.info = info

    fake_psutil = type("FakePsutil", (), {
        "process_iter": staticmethod(lambda attrs: [_FakeProc({"cwd": "C:\\unrelated", "cmdline": ["notepad.exe"]})]),
    })()
    monkeypatch.setattr(web_dashboard, "psutil", fake_psutil)

    assert web_dashboard._is_project_folder_active(str(tmp_path)) is False


def test_is_project_folder_active_survives_process_access_errors(tmp_path, monkeypatch):
    class _FakeProc:
        @property
        def info(self):
            raise Exception("access denied")

    fake_psutil = type("FakePsutil", (), {
        "process_iter": staticmethod(lambda attrs: [_FakeProc()]),
    })()
    monkeypatch.setattr(web_dashboard, "psutil", fake_psutil)

    assert web_dashboard._is_project_folder_active(str(tmp_path)) is False


# --- /api/sibling_projects ---

def test_api_sibling_projects_endpoint(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    (tmp_path / "Tools" / "MyTool").mkdir(parents=True)
    monkeypatch.setattr(web_dashboard, "PROJECTS_ROOT", str(tmp_path))
    monkeypatch.setattr(web_dashboard, "_is_project_folder_active", lambda path: True)

    client = TestClient(web_dashboard.app)
    resp = client.get("/api/sibling_projects")

    assert resp.status_code == 200
    data = resp.json()
    assert data["root"] == str(tmp_path)
    assert data["projects"] == [{"name": "MyTool", "path": "Tools/MyTool", "active": True}]
