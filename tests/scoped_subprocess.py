# tests/scoped_subprocess.py
#
# monkeypatch.setattr(subprocess, "run", fake) - וגם setattr(module.subprocess, "run", fake),
# שזה אותו אובייקט מודול - מחליף את subprocess.run לכל התהליך. כל thread אחר שמריץ פקודה
# באותו זמן מקבל את ה-fake: דוגם החומרה של אפליקציית הווב (nvidia-smi ...
# --format=csv,noheader,nounits, utils/shared/hardware.py) קיבל fake-ffmpeg שכותב ל-cmd[-1], ונוצר
# קובץ בשם הדגל בשורש הפרויקט (2026-10-02). כאן מחליפים רק את ההפניה ל-subprocess בתוך
# המודול הנבדק - כל שאר הקוד ממשיך לראות את subprocess האמיתי.
import os
import subprocess

from tests import PROJECT_ROOT


class _SubprocessWithFakeRun:
    """subprocess כמו שמודול אחד רואה אותו: רק run() מוחלף, כל השאר (PIPE,
    CompletedProcess, TimeoutExpired...) הוא המודול האמיתי."""

    def __init__(self, run):
        self.run = run

    def __getattr__(self, name):
        return getattr(subprocess, name)


def fake_subprocess_run(monkeypatch, module, run):
    """subprocess.run מזויף רק בשביל `module` (שעושה import subprocess ברמת המודול)."""
    monkeypatch.setattr(module, "subprocess", _SubprocessWithFakeRun(run))


def flag_named_files_in_project_root():
    """קבצים ששמם נראה כמו דגל CLI - סימן ש-fake שכותב ל-cmd[-1] תפס פקודה של מישהו אחר."""
    return sorted(name for name in os.listdir(PROJECT_ROOT) if name.startswith("-"))
