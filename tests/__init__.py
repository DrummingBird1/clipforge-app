# tests/ - חבילה: pytest (import mode prepend) מכניס את שורש הפרויקט ל-sys.path לפי החבילה העליונה, ו-conftest.py
# מוסיף את src/ - כך שקובץ טסט בכל עומק (tests/<אזור>/test_x.py) לא מוסיף נתיבים בעצמו. נתיבים לקבצים בריפו:
# PROJECT_ROOT (שורש הפרויקט) ו-TESTS_DIR (התיקייה הזו - data/, golden/, visual_baselines/), לא dirname(__file__).
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
