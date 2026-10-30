# tests/bot/test_bot_main_entrypoint.py
#
# src/entrypoints/main.py (בוט הדיסקורד) כתת-תהליך אמיתי - בלי רשת ובלי Discord: עטיפה קטנה מחליפה את
# get_secret ואת load_dotenv (שום טוקן אמיתי מ-Credential Manager או מ-.env), ו-login/connect של
# discord.py זורקים במקום להתחבר. בתת-תהליך ולא ב-import, כי main.py עוטף את sys.stdout בזמן הייבוא.
import ast
from tests import PROJECT_ROOT
import json
import os
import subprocess
import sys

BASE_DIR = PROJECT_ROOT
MAIN_PY = os.path.join(BASE_DIR, "src", "entrypoints", "main.py")
COGS_DIR = os.path.join(BASE_DIR, "src", "cogs")


def _config_error_exit_code():
    """CONFIG_ERROR_EXIT_CODE מתוך main.py עצמו (ast - בלי לייבא אותו: הייבוא עוטף את sys.stdout)."""
    with open(MAIN_PY, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "CONFIG_ERROR_EXIT_CODE" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("CONFIG_ERROR_EXIT_CODE לא מוגדר ב-main.py")

_BOOTSTRAP = r"""
import asyncio, json, runpy, sys
sys.path.insert(0, SRC_DIR)
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
import utils.shared.secrets_vault as vault
vault.get_secret = lambda key, default="": TOKEN if key == "DISCORD_TOKEN" else default
import discord
from discord.ext import commands

async def _login(self, token):
    if MODE == "bad_token":
        raise discord.LoginFailure("Improper token has been passed.")
    if MODE != "no_intents":
        raise AssertionError("ניסיון התחברות ל-Discord בטסט")

async def _connect(self, *a, **k):
    if MODE == "no_intents":
        raise discord.PrivilegedIntentsRequired(None)
    raise AssertionError("ניסיון התחברות ל-Discord בטסט")

discord.Client.login = _login
discord.Client.connect = _connect

if MODE == "cogs":
    loaded = []
    async def _load_extension(self, name, **k):
        loaded.append(name)
    commands.Bot.load_extension = _load_extension
    module = runpy.run_path(MAIN_PY, run_name="clipforge_bot_main")
    asyncio.run(module["bot"].load_all_cogs())
    print("LOADED=" + json.dumps(loaded))
else:
    runpy.run_path(MAIN_PY, run_name="__main__")
"""


def _run_main(tmp_path, mode, token=""):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8", "DISCORD_TOKEN")}
    env["CLIPFORGE_DATA_DIR"] = str(tmp_path / "data")
    env["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
    prelude = f"SRC_DIR = {os.path.join(BASE_DIR, 'src')!r}\nMAIN_PY = {MAIN_PY!r}\nMODE = {mode!r}\nTOKEN = {token!r}\n"
    proc = subprocess.run([sys.executable, "-c", prelude + _BOOTSTRAP], cwd=BASE_DIR, env=env, capture_output=True, timeout=120)
    # כמו שרת הדפדפן (_run_bot_process_loop): הפלט נקרא ב-utf-8 קפדני - בייטים של cp1255 נכשלים כאן
    return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")


def test_config_error_exit_code_is_2_not_the_crash_code():
    # שרת הדפדפן מפעיל מחדש את הבוט אחרי קריסה (קוד 1) - על שגיאת הגדרה הוא אמור לעצור
    assert _config_error_exit_code() == 2


def test_without_token_exits_with_the_config_error_code_and_a_clear_message(tmp_path):
    code, out, err = _run_main(tmp_path, "no_token")
    assert code == _config_error_exit_code()
    assert "לא נמצא DISCORD_TOKEN" in out
    assert "Traceback" not in out + err


def test_rejected_token_exits_with_the_config_error_code_without_traceback(tmp_path):
    code, out, err = _run_main(tmp_path, "bad_token", token="not-a-real-token")
    assert code == _config_error_exit_code()
    assert "Discord דחה את ה-DISCORD_TOKEN" in out
    assert "Traceback" not in out + err


def test_missing_message_content_intent_exits_with_the_config_error_code_without_traceback(tmp_path):
    code, out, err = _run_main(tmp_path, "no_intents", token="not-a-real-token")
    assert code == _config_error_exit_code()
    assert "Message Content Intent" in out
    assert "Traceback" not in out + err


def test_bot_loads_every_cog_in_src_cogs(tmp_path):
    """מ-6.9.2026 (המעבר ל-src/) main.py חיפש את <שורש>/cogs, שלא קיים - והבוט עלה בלי אף cog."""
    code, out, err = _run_main(tmp_path, "cogs", token="not-a-real-token")
    assert code == 0, err
    loaded = json.loads(out.split("LOADED=", 1)[1].strip())
    expected = sorted(f"cogs.{name[:-3]}" for name in os.listdir(COGS_DIR) if name.endswith(".py") and not name.startswith("__"))
    assert len(expected) >= 9
    assert loaded == expected
