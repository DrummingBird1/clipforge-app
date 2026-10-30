# tests/bot/test_story_cutter_game_guess.py
#
# 30.10.2026: המשחק ש-story_cutter מנחש משם הקובץ (כשה-AI לא מזהה) - מילים שלמות, כמו seo_generator. קודם "rl" ו-"mc" כתת-מחרוזת
# הפכו כל "world_record" או "girl" ל-Rocket League. הסקריפט מפעיל argparse כבר בייבוא, אז רק הפונקציה עצמה מהודרת כאן.
import ast
import os

from tests import PROJECT_ROOT


def _detect():
    path = os.path.join(PROJECT_ROOT, "my_scripts", "video", "story_cutter.py")
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    func = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "detect_game_from_filename")
    namespace = {}
    exec(compile(ast.Module(body=[func], type_ignores=[]), path, "exec"), namespace)
    return namespace["detect_game_from_filename"]


def test_the_game_guess_matches_whole_words_only():
    detect = _detect()
    assert detect("world_record_girl.mp4") == "General Gameplay"
    assert detect("rl_clip_3.mp4") == "Rocket League"
    assert detect("minecraft_build.mp4") == "Minecraft"
