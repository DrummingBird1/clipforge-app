# dev/portable/clipforge_exe.py -> ClipForge.exe בחבילה הניידת (PyInstaller, ב-release.yml)
#
# 16.11.2026 (ClipForge 2.0): winget מתקין חבילת zip רק כשיש בה exe. זה כל ה-exe: מריץ את launcher.pyw בפייתון של החבילה
# (pythonw - בלי חלון), בדיוק כמו ClipForge.vbs. כל ההיגיון - ב-launcher.pyw.
import os
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000


def root_dir():
    return os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))


def command(root):
    return [os.path.join(root, "python", "pythonw.exe"), os.path.join(root, "launcher.pyw")]


def main():
    root = root_dir()
    subprocess.Popen(command(root), cwd=root, creationflags=CREATE_NO_WINDOW)
    return 0


if __name__ == "__main__":
    sys.exit(main())
