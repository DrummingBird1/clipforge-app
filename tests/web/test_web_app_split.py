# tests/web/test_web_app_split.py
#
# 24.10.2026: פיצול web_app.py לקבוצות (src/entrypoints/web/<קבוצה>.py), בלי שינוי התנהגות. טסטים מחליפים את
# web_app.<שם> (monkeypatch) - קוד שזז רואה את ההחלפה רק אם הוא ניגש לשם דרך W. ולא דרך שם מקומי. כאן:
# (1) כל מה שזז נשאר נגיש כ-web_app.<שם>, ואותו אובייקט; (2) בקבצים שזזו אין גישה לשם שקיים גם ב-web_app בלי W. - גם
# בתוך אותה קבוצה (פונקציה שזזה יחד עם הפונקציה שהיא קוראת לה). מודולי ספרייה (import os) לא נחשבים - מחליפים את
# המאפיינים שלהם, לא אותם.
import ast
import importlib
import os

import pytest

from entrypoints import web_app
from utils.shared.data_dir import PROJECT_ROOT

SRC = os.path.join(PROJECT_ROOT, "src")
SPLIT_MODULES = ["entrypoints.web.server_startup", "entrypoints.web.path_checks", "entrypoints.web.config_files", "entrypoints.web.auth",
                 "entrypoints.web.bot_process",
                 "entrypoints.web.run_lifecycle"]


def _path(module):
    return os.path.join(SRC, *module.split(".")) + ".py"


def _web_app_names():
    """השמות ברמת המודול של web_app.py: השמות, הפונקציות והמחלקות שהוגדרו בו, ומה שיובא אליו ב-from X import Y."""
    tree = ast.parse(open(_path("entrypoints.web_app"), encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node in tree.body:
            names.add(node.name)
        elif isinstance(node, ast.ImportFrom) and node.col_offset == 0:
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.col_offset == 0:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(t.id for target in targets for t in ast.walk(target) if isinstance(t, ast.Name))
    return names - {"W"}


def _bound_in(func):
    """שמות שהפונקציה עצמה קושרת (פרמטרים, השמות, לולאות, with/except, import, פונקציות פנימיות)."""
    bound = {a.arg for a in ast.walk(func.args) if isinstance(a, ast.arg)}
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not func:
            bound.add(node.name)
            bound.update(a.arg for a in ast.walk(node.args) if isinstance(a, ast.arg))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update((alias.asname or alias.name).split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
    return bound


@pytest.mark.parametrize("module", SPLIT_MODULES)
def test_what_moved_is_still_web_app_attribute_and_the_same_object(module):
    moved = importlib.import_module(module)
    tree = ast.parse(open(_path(module), encoding="utf-8").read())
    top = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    top += [t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)]
    assert top, module
    for name in top:
        assert getattr(web_app, name) is getattr(moved, name), f"{module}.{name} לא זהה ל-web_app.{name}"


@pytest.mark.parametrize("module", SPLIT_MODULES)
def test_moved_code_reaches_web_app_names_only_through_w(module):
    names = _web_app_names()
    tree = ast.parse(open(_path(module), encoding="utf-8").read())
    offenders = []
    for func in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        bound = _bound_in(func)
        for node in ast.walk(func):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in names and node.id not in bound:
                offenders.append(f"{module}:{node.lineno} {node.id} -> W.{node.id}")
    assert sorted(set(offenders)) == [], "שם מ-web_app בלי W. - monkeypatch על web_app לא יחול עליו:\n" + "\n".join(sorted(set(offenders)))
