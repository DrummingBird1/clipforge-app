# tests/infra/test_docs_layout.py
#
# 23.10.2026 (סדר התיקיות, 21): דוח של תאריך מסוים (סיור שימושיות, מפת דרכים קפואה...) יושב ב-docs/history/ - בשורש docs/
# נשארים המדריכים החיים. יומן המסירה ב-docs/handoff/.
import os
import re

from tests import PROJECT_ROOT

DOCS = os.path.join(PROJECT_ROOT, "docs")
DATED = re.compile(r"\d{4}-\d{2}-\d{2}")


def test_dated_reports_live_in_docs_history():
    strays = sorted(name for name in os.listdir(DOCS) if name.endswith(".md") and DATED.search(name))
    assert strays == [], f"דוחות עם תאריך בשורש docs/ - להעביר ל-docs/history/: {strays}"


def test_links_to_moved_reports_point_into_history():
    stale = []
    skip = {".git", ".venv", "node_modules", ".claude", os.path.join("docs", "handoff")}
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        # 25.10.2026: לפי שם תיקייה מהשורש ולא "חלק מהנתיב" - .claude/worktrees (worktrees של sessions אחרים, עם עותקים ישנים
        # של docs) הכשיל את הטסט מקומית, ו-".git" בתוך הנתיב דילג בטעות גם על .github
        rel_dir = os.path.relpath(dirpath, PROJECT_ROOT)
        dirnames[:] = [d for d in dirnames if os.path.normpath(os.path.join(rel_dir, d)) not in skip]
        for name in filenames:
            if name.endswith((".md", ".py")):
                with open(os.path.join(dirpath, name), encoding="utf-8", errors="replace") as f:
                    if re.search(r"docs/dataviz_usability_\d{4}", f.read()):
                        stale.append(os.path.relpath(os.path.join(dirpath, name), PROJECT_ROOT))
    assert stale == [], f"קישור לנתיב הישן: {stale}"
