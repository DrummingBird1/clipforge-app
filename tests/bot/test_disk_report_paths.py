# tests/bot/test_disk_report_paths.py
#
# דוח סריקת הדיסק עבר מ-data/ (נתוני המשתמש) ל-workspace/reports/disk/ (תוצרים, 19.10.2026).
# disk_scanner.py כותב לשם בלי --output; duplicate_cleaner.py ו-report_to_excel.py קוראים משם,
# וכשאין דוח חדש - את data/report.json הישן, בלי לכתוב ל-data/ ובלי להזיז אותו.
import json
from tests import PROJECT_ROOT
import os
import subprocess
import sys

BASE_DIR = PROJECT_ROOT
TOOLS_DIR = os.path.join(BASE_DIR, "my_scripts", "tools")


def _dirs(tmp_path):
    data_dir = tmp_path / "data"
    workspace_dir = tmp_path / "workspace"
    data_dir.mkdir()
    workspace_dir.mkdir()
    return data_dir, workspace_dir


def _run(script, data_dir, workspace_dir, *args):
    env = dict(os.environ, CLIPFORGE_DATA_DIR=str(data_dir), CLIPFORGE_WORKSPACE_DIR=str(workspace_dir))
    result = subprocess.run(
        [sys.executable, os.path.join(TOOLS_DIR, script), *args],
        cwd=BASE_DIR, env=env, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    return result


def _result(stdout):
    line = [line for line in stdout.splitlines() if line.startswith("RESULT:")][-1]
    return json.loads(line[len("RESULT:"):])


def _write_report(path, files):
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {"total_files_scanned": len(files), "duplicates": [{"hash": "fake", "size_bytes": 5, "count": len(files), "files": files}]}
    path.write_text(json.dumps(report), encoding="utf-8")


def test_disk_scanner_writes_to_workspace_reports_disk_by_default(tmp_path):
    data_dir, workspace_dir = _dirs(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    (target / "a.txt").write_text("hello")

    result = _run("disk_scanner.py", data_dir, workspace_dir, "--target_dir", str(target))

    assert result.returncode == 0, result.stdout + result.stderr
    reports = workspace_dir / "reports" / "disk"
    assert (reports / "report.json").exists()
    assert (reports / "report.xlsx").exists() and (reports / "report.html").exists()
    assert list(data_dir.iterdir()) == []


def test_duplicate_cleaner_falls_back_to_the_old_data_report(tmp_path):
    data_dir, workspace_dir = _dirs(tmp_path)
    legacy = data_dir / "report.json"
    _write_report(legacy, [str(tmp_path / "x.txt"), str(tmp_path / "y.txt")])
    (tmp_path / "x.txt").write_text("dupe")
    (tmp_path / "y.txt").write_text("dupe")
    before = legacy.read_bytes()

    result = _run("duplicate_cleaner.py", data_dir, workspace_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _result(result.stdout)["groups_processed"] == 1
    assert (tmp_path / "x.txt").exists() and (tmp_path / "y.txt").exists()  # תצוגה מקדימה בלבד
    assert legacy.read_bytes() == before


def test_duplicate_cleaner_prefers_the_new_report(tmp_path):
    data_dir, workspace_dir = _dirs(tmp_path)
    (data_dir / "report.json").write_text(json.dumps({"duplicates": []}), encoding="utf-8")  # ישן ושונה - לא אמור להיקרא
    _write_report(workspace_dir / "reports" / "disk" / "report.json", [str(tmp_path / "gone_a"), str(tmp_path / "gone_b")])

    result = _run("duplicate_cleaner.py", data_dir, workspace_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _result(result.stdout)["groups_processed"] == 1


def test_report_to_excel_reads_the_old_report_but_writes_to_workspace(tmp_path):
    data_dir, workspace_dir = _dirs(tmp_path)
    _write_report(data_dir / "report.json", [str(tmp_path / "x.txt")])

    result = _run("report_to_excel.py", data_dir, workspace_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (workspace_dir / "reports" / "disk" / "report.xlsx").exists()
    assert sorted(p.name for p in data_dir.iterdir()) == ["report.json"]


def test_report_to_excel_without_any_report_points_at_the_new_location(tmp_path):
    data_dir, workspace_dir = _dirs(tmp_path)

    result = _run("report_to_excel.py", data_dir, workspace_dir)

    assert result.returncode == 1
    assert os.path.join("reports", "disk", "report.json") in result.stdout


def test_duplicate_scene_report_defaults_to_workspace_reports_disk():
    from utils.shared import disk_report_paths
    from utils.shared.workspace_dir import WORKSPACE_DIR

    assert disk_report_paths.DUPLICATE_SCENES_REPORT_JSON == os.path.join(WORKSPACE_DIR, "reports", "disk", "duplicate_scenes_report.json")
    source = open(os.path.join(BASE_DIR, "my_scripts", "video", "duplicate_scene_detector.py"), encoding="utf-8").read()
    assert "OUTPUT_PATH = args.output or DUPLICATE_SCENES_REPORT_JSON" in source and "DATA_DIR" not in source
