# tests/infra/test_migrate_workspace_layout.py
#
# dev/migrate_workspace_layout.py: העברת התוצרים הקיימים מ-workspace/<כיוון>/<כלי> ל-workspace/<כלי>/<כיוון>.
# יבש כברירת מחדל, לא דורס, לא מוחק קבצים, מסיר רק תיקיות שהתרוקנו לגמרי, ומשכתב נתיבים ב-run manifests. הכל על
# workspace זמני - לא על workspace/ האמיתי.
import importlib.util
import json
import os

from tests import PROJECT_ROOT

_spec = importlib.util.spec_from_file_location("migrate_workspace_layout", os.path.join(PROJECT_ROOT, "dev", "migrate_workspace_layout.py"))
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)


def _file(path, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _old_workspace(ws):
    _file(ws / "horizontal" / "edited_videos" / "a_edited_horizontal.mp4", b"studio")
    _file(ws / "horizontal" / "edited_videos" / "_sig" / "a_edited_horizontal.mp4.sig.json", b"{}")
    _file(ws / "vertical" / "edited_videos" / "tiktok" / "b.mp4", b"target")
    _file(ws / "vertical" / "timelapses" / "t_vertical.mp4", b"tl")
    _file(ws / "horizontal" / "dataviz" / "ep.mp4", b"dv")
    _file(ws / "horizontal" / "dataviz" / "ep.publish.json", b'{"video": "ep.mp4"}')
    _file(ws / "horizontal" / "YouTube" / "r1.mp4", b"yt")
    _file(ws / "square" / "r1_square.mp4", b"sq")          # Rocket כתב ישר ל-square/
    (ws / "square" / "edited_videos" / "_sig").mkdir(parents=True)
    (ws / "vertical" / "TikTok").mkdir(parents=True)        # ריקה
    _file(ws / "dataviz_israel_staging" / "ep1" / "config.yaml", b"title: x")
    _file(ws / "horizontal" / "my_notes" / "keep.txt", b"user")   # לא שייך לאף מיפוי
    _file(ws / "clips" / "c.mp4", b"clip")


def _snapshot(root):
    return sorted(os.path.relpath(os.path.join(r, f), root) for r, _d, fs in os.walk(root) for f in fs)


def test_dry_run_lists_everything_and_touches_nothing(tmp_path, capsys):
    ws = tmp_path / "ws"
    _old_workspace(ws)
    before = _snapshot(ws)

    assert mig.main(["--workspace", str(ws)]) == 0

    out = capsys.readouterr().out
    assert _snapshot(ws) == before and not (ws / "studio").exists()
    assert os.path.join("studio", "horizontal", "a_edited_horizontal.mp4") in out
    assert os.path.join("dataviz", "staging", "ep1", "config.yaml") in out
    assert os.path.join("rocket_shorts", "square", "r1_square.mp4") in out
    assert "my_notes" in out and "--apply" in out


def test_apply_moves_to_tool_first_layout_and_removes_only_emptied_folders(tmp_path):
    ws = tmp_path / "ws"
    _old_workspace(ws)
    plan = mig.build_plan(str(ws), bases=[str(ws)])
    moved, failed, _removed = mig.apply_plan(plan)

    assert failed == [] and moved == 9
    assert (ws / "studio" / "horizontal" / "a_edited_horizontal.mp4").read_bytes() == b"studio"
    assert (ws / "studio" / "horizontal" / "_sig" / "a_edited_horizontal.mp4.sig.json").exists()
    assert (ws / "studio" / "vertical" / "tiktok" / "b.mp4").read_bytes() == b"target"
    assert (ws / "timelapses" / "vertical" / "t_vertical.mp4").exists()
    assert (ws / "dataviz" / "outputs" / "horizontal" / "ep.publish.json").exists()   # החבילה עוברת עם הסרטון
    assert (ws / "rocket_shorts" / "YouTube" / "r1.mp4").exists()
    assert (ws / "rocket_shorts" / "square" / "r1_square.mp4").read_bytes() == b"sq"
    assert (ws / "dataviz" / "staging" / "ep1" / "config.yaml").exists()
    # מה שלא שייך לאף מיפוי נשאר, וגם ההורה שלו; תיקיות שהתרוקנו (גם הריקות מלכתחילה) הוסרו
    assert (ws / "horizontal" / "my_notes" / "keep.txt").read_bytes() == b"user"
    assert not (ws / "vertical").exists() and not (ws / "square").exists() and not (ws / "dataviz_israel_staging").exists()
    assert not (ws / "horizontal" / "edited_videos").exists()
    assert (ws / "clips" / "c.mp4").exists()


def test_never_overwrites_an_existing_target(tmp_path):
    ws = tmp_path / "ws"
    _file(ws / "horizontal" / "edited_videos" / "same.mp4", b"old")
    _file(ws / "studio" / "horizontal" / "same.mp4", b"new")
    plan = mig.build_plan(str(ws), bases=[str(ws)])
    assert plan.moves == [] and len(plan.conflicts) == 1

    mig.apply_plan(plan)

    assert (ws / "studio" / "horizontal" / "same.mp4").read_bytes() == b"new"
    assert (ws / "horizontal" / "edited_videos" / "same.mp4").read_bytes() == b"old"   # נשאר, וגם התיקייה שלו
    assert str(ws / "horizontal" / "edited_videos") not in plan.empty_dirs


def test_run_manifest_output_paths_are_rewritten(tmp_path):
    ws = tmp_path / "ws"
    out = _file(ws / "horizontal" / "edited_videos" / "a.mp4")
    manifests = ws / ".cache" / "run_manifests"
    manifests.mkdir(parents=True)
    (manifests / "m.json").write_text(json.dumps({"output_dir": str(out.parent), "files": [{"output": str(out), "source": "D:\\in\\a.mp4"}]}),
                                      encoding="utf-8")
    plan = mig.build_plan(str(ws), bases=[str(ws)])
    assert len(plan.rewrites) == 2

    mig.apply_plan(plan)

    data = json.loads((manifests / "m.json").read_text(encoding="utf-8"))
    assert data["output_dir"] == str(ws / "studio" / "horizontal")
    assert data["files"][0]["output"] == str(ws / "studio" / "horizontal" / "a.mp4")
    assert data["files"][0]["source"] == "D:\\in\\a.mp4"
