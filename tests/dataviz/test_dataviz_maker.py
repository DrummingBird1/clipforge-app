# tests/dataviz/test_dataviz_maker.py
#
# my_scripts/video/dataviz_maker.py - העטיפה של מנוע src/dataviz: מציאת פרקים (פרק בודד או
# תיקייה של פרקים), נתיבי הפלט לפי כיוון התמונה, ושורות PROGRESS:/RESULT: שה-GUI קורא -
# גם בהרצה ישירה וגם דרך utils/worker.py. רק במצב stills (פריימים בודדים), בלי וידאו מלא.
import importlib.util
from tests import PROJECT_ROOT
import json
import os
import subprocess
import sys
import threading

import pytest

from tests.dataviz_helpers import write_episode

BASE_DIR = PROJECT_ROOT
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "dataviz_maker.py")


@pytest.fixture(scope="module")
def maker():
    spec = importlib.util.spec_from_file_location("dataviz_maker_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300, cwd=BASE_DIR)


def _result(stdout):
    lines = [line for line in stdout.splitlines() if line.startswith("RESULT:")]
    return json.loads(lines[-1][len("RESULT:"):])


def test_find_episodes_single_folder_or_folder_of_episodes(maker, tmp_path):
    first = write_episode(tmp_path, name="a")
    second = write_episode(tmp_path, name="b")
    (tmp_path / "not_an_episode").mkdir()

    assert maker.find_episodes(first, "", str(tmp_path)) == [first]
    assert maker.find_episodes(str(tmp_path), "", "unused") == [first, second]
    assert maker.find_episodes("", "b", str(tmp_path)) == [second]          # --episode גובר
    assert maker.find_episodes("", "", str(tmp_path)) == [first, second]    # ברירת מחדל: תיקיית הפרקים
    assert maker.find_episodes(str(tmp_path / "missing"), "", "x") == []


def test_output_paths_follow_the_workspace_orientation_folders(maker):
    config = {"name": "ep", "video": {"width": 1440, "height": 888, "output_name": "race"}}
    assert maker.output_paths(config, "full", "W") == (os.path.join("W", "dataviz", "outputs", "horizontal"),
                                                       os.path.join("W", "dataviz", "outputs", "horizontal", "race.mp4"))
    assert maker.output_paths(config, "test", "W")[1].endswith("race_test.mp4")
    assert maker.output_paths(config, "stills", "W")[1].endswith("race_stills")
    vertical = {"name": "ep", "video": {"width": 1080, "height": 1920, "output_name": ""}}
    assert maker.output_paths(vertical, "full", "W")[1] == os.path.join("W", "dataviz", "outputs", "vertical", "ep.mp4")


def test_progress_is_split_between_episodes_and_printed_once_per_percent(maker, capsys):
    progress = maker.Progress(2)
    progress(1, 4)
    progress(1, 4)
    progress.index = 1
    progress(4, 4)
    assert capsys.readouterr().out.split() == ["PROGRESS:12", "PROGRESS:100"]


def test_stills_run_reports_progress_and_result(tmp_path):
    folder = write_episode(tmp_path)
    out = tmp_path / "out"

    proc = _run("--input_dir", folder, "--mode", "stills", "--output_dir", str(out))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    pcts = [int(line.split(":")[1]) for line in proc.stdout.splitlines() if line.startswith("PROGRESS:")]
    assert pcts == sorted(pcts) and pcts[-1] == 100
    assert _result(proc.stdout) == {"episodes": 1, "files_created": 10, "errors": 0}
    stills = out / "dataviz" / "outputs" / "horizontal" / "tiny_stills"
    assert len(list(stills.glob("still_*.png"))) == 10


def test_invalid_episode_prints_every_error_and_fails(tmp_path):
    folder = write_episode(tmp_path, {"chart": "rocket_race", "ranking": {"top_n": 0}})

    proc = _run("--input_dir", folder, "--mode", "stills", "--output_dir", str(tmp_path / "out"))

    assert proc.returncode == 1
    assert "rocket_race" in proc.stdout and "ranking.top_n" in proc.stdout
    assert _result(proc.stdout) == {"episodes": 1, "files_created": 0, "errors": 1}


def test_runs_through_the_worker_like_the_gui(tmp_path):
    from utils.script_metadata import get_script_metadata
    from utils.worker import TaskWorker

    meta = get_script_metadata(SCRIPT)
    assert meta["concurrency"] == "heavy" and meta["safety"] == "read-only"
    worker = TaskWorker()
    done = threading.Event()
    outcome = {}
    worker.add_script_task(SCRIPT, write_episode(tmp_path), lambda o: (outcome.update(o), done.set()),
                           concurrency=meta["concurrency"], extra_args=["--mode", "stills", "--output_dir", str(tmp_path / "out")])
    assert done.wait(300)
    pcts = []
    while not worker.progress_queue.empty():
        pcts.append(worker.progress_queue.get()["pct"])
    assert outcome["returncode"] == 0
    assert outcome["result"] == {"episodes": 1, "files_created": 10, "errors": 0}
    assert 100 in pcts and len(set(pcts)) >= 5
