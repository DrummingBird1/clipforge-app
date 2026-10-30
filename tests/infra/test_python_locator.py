# tests/infra/test_python_locator.py
import sys


from utils.shared import python_locator


def test_not_frozen_returns_sys_executable(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert python_locator.get_python_executable() == sys.executable


def test_frozen_prefers_bundled_venv(monkeypatch, tmp_path):
    # מדמה dist/Launcher/{Launcher.exe, venv/Scripts/python.exe} -
    # ראו build_exe.py (מעתיק את .venv המקומי לשם) ו-utils/shared/python_locator.py.
    exe_dir = tmp_path / "Launcher"
    bundled_python = exe_dir / "venv" / "Scripts" / "python.exe"
    bundled_python.parent.mkdir(parents=True)
    bundled_python.write_text("")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "Launcher.exe"))

    assert python_locator.get_python_executable() == str(bundled_python)


def test_frozen_without_bundled_venv_falls_back_to_global(monkeypatch, tmp_path):
    exe_dir = tmp_path / "Launcher"
    exe_dir.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "Launcher.exe"))
    monkeypatch.setattr(python_locator.shutil, "which", lambda name: f"C:/global/{name}.exe" if name == "python" else None)

    assert python_locator.get_python_executable() == "C:/global/python.exe"


def test_frozen_with_nothing_found_returns_none(monkeypatch, tmp_path):
    exe_dir = tmp_path / "Launcher"
    exe_dir.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "Launcher.exe"))
    monkeypatch.setattr(python_locator.shutil, "which", lambda name: None)

    assert python_locator.get_python_executable() is None
