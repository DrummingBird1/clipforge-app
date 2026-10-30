# tests/bot/test_tesseract_locator.py


from utils.media import tesseract_locator


def test_returns_first_existing_common_install_path(monkeypatch):
    found = tesseract_locator._COMMON_INSTALL_PATHS[1]
    monkeypatch.setattr(tesseract_locator.os.path, "exists", lambda path: path == found)

    assert tesseract_locator.get_tesseract_exe() == found


def test_prefers_earlier_path_when_both_exist(monkeypatch):
    monkeypatch.setattr(tesseract_locator.os.path, "exists", lambda path: True)

    assert tesseract_locator.get_tesseract_exe() == tesseract_locator._COMMON_INSTALL_PATHS[0]


def test_falls_back_to_bare_command_when_nothing_installed(monkeypatch):
    monkeypatch.setattr(tesseract_locator.os.path, "exists", lambda path: False)

    assert tesseract_locator.get_tesseract_exe() == "tesseract"


def test_is_available_true_for_an_absolute_path_without_checking_path(monkeypatch):
    monkeypatch.setattr(tesseract_locator, "get_tesseract_exe", lambda: tesseract_locator._COMMON_INSTALL_PATHS[0])
    monkeypatch.setattr(tesseract_locator.shutil, "which", lambda name: (_ for _ in ()).throw(AssertionError("shouldn't check PATH for an absolute path")))

    assert tesseract_locator.is_tesseract_available() is True


def test_is_available_true_when_bare_command_resolves_on_path(monkeypatch):
    monkeypatch.setattr(tesseract_locator, "get_tesseract_exe", lambda: "tesseract")
    monkeypatch.setattr(tesseract_locator.shutil, "which", lambda name: "/usr/bin/tesseract" if name == "tesseract" else None)

    assert tesseract_locator.is_tesseract_available() is True


def test_is_available_false_when_bare_command_not_on_path(monkeypatch):
    monkeypatch.setattr(tesseract_locator, "get_tesseract_exe", lambda: "tesseract")
    monkeypatch.setattr(tesseract_locator.shutil, "which", lambda name: None)

    assert tesseract_locator.is_tesseract_available() is False
