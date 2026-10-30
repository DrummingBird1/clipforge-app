# tests/infra/test_logging_setup.py
#
# בודק utils/shared/logging_setup.py - הן את ה-tee הקיים (stdout/stderr -> קובץ
# מתגלגל) והן את התוספת (item: לוגים מובנים) - קובץ JSON-lines מקביל, אותה
# רשומה בדיוק בשני פורמטים.
import io
import json
import logging
import os
import sys


import pytest

from utils.shared import logging_setup


@pytest.fixture(autouse=True)
def _isolate_logs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(logging_setup, "LOGS_DIR", str(tmp_path))


def _reset_logger(log_name):
    """מנקה handlers שהתווספו בקריאה קודמת - setup_persistent_logging() בודק
    `if not logger.handlers` כדי לא להכפיל handlers על אותו logger, אבל זה
    אומר שקריאה שנייה בטסט אחר על אותו log_name לא הייתה מוסיפה handlers
    חדשים המצביעים ל-tmp_path המבודד של הטסט הזה."""
    logger = logging.getLogger(f"persistent.{log_name}")
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


# --- _infer_level ---

@pytest.mark.parametrize("message,expected_level", [
    ("[ERROR] משהו נכשל", "error"),
    ("[WARNING] שים לב", "warning"),
    ("[SUCCESS] הסתיים", "success"),
    ("[APPROVED] נוצר קובץ", "success"),
    ("[SKIP] כבר קיים", "skip"),
    ("[INFO] מידע כללי", "info"),
    ("שורה בלי שום קידומת מוכרת", "info"),
])
def test_infer_level_from_message_prefix(message, expected_level):
    assert logging_setup._infer_level(message) == expected_level


# --- _JsonLinesFormatter ---

def test_json_lines_formatter_produces_valid_json_with_expected_fields():
    formatter = logging_setup._JsonLinesFormatter()
    record = logging.LogRecord("persistent.test", logging.INFO, __file__, 1, "[ERROR] נכשל", None, None)

    line = formatter.format(record)
    parsed = json.loads(line)

    assert parsed["level"] == "error"
    assert parsed["message"] == "[ERROR] נכשל"
    assert parsed["logger"] == "persistent.test"
    assert "timestamp" in parsed


# --- setup_persistent_logging end-to-end ---

def test_setup_persistent_logging_creates_both_log_and_jsonl_files(tmp_path):
    _reset_logger("test_both_files")
    try:
        logging_setup.setup_persistent_logging("test_both_files")
        print("[INFO] שורת בדיקה")
        sys.stdout.flush()

        assert os.path.exists(os.path.join(str(tmp_path), "test_both_files.log"))
        assert os.path.exists(os.path.join(str(tmp_path), "test_both_files.jsonl"))
    finally:
        _reset_logger("test_both_files")
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__


def test_jsonl_file_contains_one_valid_json_object_per_line(tmp_path):
    _reset_logger("test_jsonl_content")
    try:
        logging_setup.setup_persistent_logging("test_jsonl_content")
        print("[WARNING] אזהרת בדיקה")
        print("[SUCCESS] הצלחה")
        sys.stdout.flush()

        jsonl_path = os.path.join(str(tmp_path), "test_jsonl_content.jsonl")
        with open(jsonl_path, "r", encoding="utf-8") as f:
            lines = [line for line in f.read().splitlines() if line.strip()]

        parsed = [json.loads(line) for line in lines]
        levels = [p["level"] for p in parsed]
        assert "warning" in levels
        assert "success" in levels
    finally:
        _reset_logger("test_jsonl_content")
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__


# --- _TeeStream re-entrancy guard (item: RecursionError שהפיל ריצת רינדור) ---

class _AlwaysFailingHandler(logging.Handler):
    """מדמה handler אמיתי שנכשל בפועל (למשל RotatingFileHandler.doRollover
    שנתקל בקובץ נעול ע"י תהליך אחר, שכיח ב-Windows) - emit שזורק תמיד גורם
    ל-logging.Handler.handleError() המובנה להיכנס לפעולה, שכותב ל-sys.stderr
    כברירת מחדל בדיוק כמו בתרחיש האמיתי שקרה בייצור."""

    def emit(self, record):
        # כמו RotatingFileHandler/StreamHandler האמיתיים - תופס את הכשל *בתוך*
        # emit ומעביר ל-handleError() בעצמו (base Handler.handle() לא עושה
        # את זה אוטומטית - זו אחריות כל handler בנפרד), כדי שהתרחיש ישחזר
        # באמת את handleError()'s שכותב ל-sys.stderr, לא רק חריגה שמתפשטת.
        try:
            raise OSError("simulated handler failure (e.g. Windows file lock during rollover)")
        except Exception:
            self.handleError(record)


def test_tee_stream_write_does_not_recurse_forever_when_its_own_handler_fails(monkeypatch):
    # שחזור מדויק של הרקורסיה שקרתה בפועל: handler שנכשל -> handleError()
    # כותב ל-sys.stderr -> אם זה ה-_TeeStream הזה עצמו, כתיבה חדשה ל-logger
    # -> אותו handler נכשל שוב -> ... בלי ההגנה, זה היה תופס RecursionError.
    logger = logging.getLogger("persistent.test_tee_recursion_guard")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.addHandler(_AlwaysFailingHandler())

    original = io.StringIO()
    tee = logging_setup._TeeStream(original, logger)
    monkeypatch.setattr(sys, "stderr", tee)
    monkeypatch.setattr(logging, "raiseExceptions", True)

    tee.write("[INFO] שורת בדיקה שגורמת לכשל ב-handler\n")  # לא אמור להעלות RecursionError

    assert "שורת בדיקה" in original.getvalue()


def test_tee_stream_write_still_logs_normally_after_a_recursive_failure(monkeypatch):
    # ההגנה משתמשת ב-threading.local per-write, לא flag קבוע - אחרי שכתיבה
    # אחת "נתקלה" בכשל-רקורסיבי וטופלה, כתיבה *הבאה* (סתם רגילה, בלי כשל)
    # עדיין אמורה לעבוד כרגיל, לא להישאר "נעולה" עקב ה-guard.
    logger = logging.getLogger("persistent.test_tee_recursion_guard_2")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    calls = []
    ok_handler = logging.Handler()
    ok_handler.emit = lambda record: calls.append(record.getMessage())
    logger.addHandler(ok_handler)

    original = io.StringIO()
    tee = logging_setup._TeeStream(original, logger)

    tee.write("[INFO] שורה ראשונה\n")
    tee.write("[INFO] שורה שנייה\n")

    assert calls == ["[INFO] שורה ראשונה", "[INFO] שורה שנייה"]


def test_setup_persistent_logging_is_idempotent_and_does_not_duplicate_handlers(tmp_path):
    _reset_logger("test_idempotent")
    try:
        logging_setup.setup_persistent_logging("test_idempotent")
        handler_count_after_first_call = len(logging.getLogger("persistent.test_idempotent").handlers)
        logging_setup.setup_persistent_logging("test_idempotent")
        handler_count_after_second_call = len(logging.getLogger("persistent.test_idempotent").handlers)

        assert handler_count_after_first_call == handler_count_after_second_call == 2
    finally:
        _reset_logger("test_idempotent")
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
