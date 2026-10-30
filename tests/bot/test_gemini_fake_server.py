# tests/bot/test_gemini_fake_server.py
#
# הנתיבים האמיתיים מול שרת Gemini מזויף (tests/fake_gemini.py, HTTP אמיתי דרך GOOGLE_GEMINI_BASE_URL):
#  - story_cutter.py בתהליך נפרד, כמה קריאות Gemini: אזהרה מוקדמת ב-80% מהתקרה, ואז 429 אמיתי -> אזהרת
#    "המכסה נגמרה", קליפים שמאושרים בלי שיפוט (אין Ollama) מסומנים בקול, וסיכום בסוף.
#  - dataviz_maker.py עם publish.seo_ai: תשובה תקינה -> כותרת מ-Gemini; 429 -> נפילה להגדרות, והכשל נרשם.
# story_cutter כותב ל-workspace/ ול-temp_analysis/ יחסית למיקום הקובץ שלו, אז רץ כעותק בתיקייה זמנית.
import os
from tests import PROJECT_ROOT
import shutil
import subprocess
import sys

import pytest
import requests

from tests.dataviz_helpers import write_episode
from tests.fake_gemini import FakeGemini
from tests.media_support import needs_ffmpeg
from utils import dataviz_publish as dp
from utils.shared.ffmpeg_locator import get_ffmpeg_exe

BASE_DIR = PROJECT_ROOT
CUTTER = os.path.join(BASE_DIR, "my_scripts", "video", "story_cutter.py")
MAKER = os.path.join(BASE_DIR, "my_scripts", "video", "dataviz_maker.py")
JUDGE_OK = '{"game_name": "Fake Game", "interesting": true, "reason": "fake judge says yes"}'
TITLE_OK = '{"title": "כותרת מהשרת המזויף", "description": "תיאור מהשרת", "hashtags": ["FakeTag", "AI"]}'


def _child_env(extra):
    env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
    env.update({"PYTHONUTF8": "1", "PYTHONPATH": os.path.join(BASE_DIR, "src")})
    env.update(extra)
    return env


def _ollama_running():
    try:
        requests.get("http://localhost:11434/api/version", timeout=1)
        return True
    except requests.RequestException:
        return False


def _make_game_video(path, seconds=100):
    # תנועה חזותית (testsrc2) + שמע שקט עם פרץ רעש חזק כל 20 שניות -> כמה נקודות שיא
    subprocess.run([get_ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=320x180:d={seconds}:r=10",
                    "-f", "lavfi", "-i", f"anoisesrc=d={seconds}:a=0.9:r=44100,volume='if(between(mod(t,20),10,12),1,0.01)':eval=frame",
                    "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True, timeout=120)


@needs_ffmpeg
@pytest.mark.skipif(_ollama_running(), reason="Ollama רץ על המחשב - הבדיקה מניחה שאין שיפוט מקומי")
def test_story_cutter_warns_early_then_on_real_429_and_flags_unjudged_clips(tmp_path):
    mirror = tmp_path / "a" / "b"
    mirror.mkdir(parents=True)
    script = mirror / "story_cutter.py"
    shutil.copy(CUTTER, script)
    (tmp_path / "in").mkdir()
    _make_game_video(tmp_path / "in" / "game1.mp4")
    for number in (2, 3, 4):                                    # 4 הקלטות x 2 נקודות שיא = 8 החלטות, מספיק כדי לעבור את 4 הקריאות
        shutil.copy(tmp_path / "in" / "game1.mp4", tmp_path / "in" / f"game{number}.mp4")
    # 3 תשובות תקינות ואז מכסה שנגמרה (429) לכל השאר
    with FakeGemini([("ok", JUDGE_OK)] * 3 + [("429", None)]) as fake:
        run = subprocess.run([sys.executable, str(script), "--input_dir", str(tmp_path / "in"), "--gemini-daily-limit", "4"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, cwd=str(tmp_path),
                             env=_child_env({**fake.env(), "CLIPFORGE_WORKSPACE_DIR": str(tmp_path / "workspace")}))
        requests_seen = len(fake.requests)
    out = run.stdout

    assert run.returncode == 0, out + run.stderr
    assert requests_seen >= 5                                   # שלוש תשובות תקינות + לפחות ניסיון 429 אחד אמיתי
    assert requests_seen <= 7                                   # מפסק: 3 כשלי מכסה רצופים ואז מפסיקים (בלי המפסק היו 18 בקשות)
    assert out.count("מדלגים עליו זמנית") == 1
    assert out.count("[WARNING] נשלחו 4 בקשות") == 1 and "80%" in out
    assert out.index("נשלחו 4 בקשות") < out.index("מכסת Gemini כנראה נגמרה")
    assert out.count("מכסת Gemini כנראה נגמרה") == 1 and "Ollama לא זמין" in out and "בלי שיפוט" in out
    assert "429" in out and "RESOURCE_EXHAUSTED" in out
    assert "(fake judge says yes)" in out or "fake judge says yes" in out
    assert out.count("קליפ אושר בלי שיפוט AI אמיתי") >= 1
    assert "[WARNING] סיכום מכסה:" in out and "שגיאות מכסה" in out
    judged = out.count("[APPROVED]") - out.count("מאשר כברירת מחדל")
    assert judged == 3                                          # בדיוק השלושה ש-Gemini שפט
    assert (tmp_path / "workspace" / "clips" / "Fake Game").is_dir()


@pytest.fixture(scope="module")
def tiny_episode(tmp_path_factory):
    return write_episode(tmp_path_factory.mktemp("seo_ai_eps"), overrides={
        "video": {"width": 320, "height": 180, "dpi": 40, "fps": 10},
        "timing": {"intro_seconds": 1, "outro_seconds": 1, "base_frames_per_day": 0.02, "step": 0.05, "strict_step": False},
        "publish": {"enabled": True, "seo_ai": True}}, name="seo_ep")


def _render(folder, out, extra_env):
    return subprocess.run([sys.executable, MAKER, "--input_dir", folder, "--output_dir", str(out)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300, cwd=BASE_DIR, env=_child_env(extra_env))


@needs_ffmpeg
def test_seo_ai_uses_gemini_title_from_a_real_http_reply(tiny_episode, tmp_path):
    with FakeGemini([("ok", TITLE_OK)]) as fake:
        run = _render(tiny_episode, tmp_path, fake.env())
        calls = len(fake.requests)

    assert run.returncode == 0, run.stdout + run.stderr
    package = dp.load_package(str(tmp_path / "dataviz" / "outputs" / "horizontal" / "seo_ep.mp4"))
    assert calls == 1 and package["steps"]["ai"] == "ok"
    assert package["metadata"]["source"] == "ai" and package["metadata"]["title"] == "כותרת מהשרת המזויף"
    assert package["metadata"]["hashtags"][:2] == ["#FakeTag", "#AI"]
    assert package["status"] == dp.PENDING


@needs_ffmpeg
def test_seo_ai_falls_back_to_the_config_title_on_a_real_429(tiny_episode, tmp_path):
    with FakeGemini([("429", None)]) as fake:
        run = _render(tiny_episode, tmp_path, fake.env())
        calls = len(fake.requests)

    assert run.returncode == 0, run.stdout + run.stderr                  # הרינדור לא נופל
    package = dp.load_package(str(tmp_path / "dataviz" / "outputs" / "horizontal" / "seo_ep.mp4"))
    assert calls == 1 and package["steps"]["ai"].startswith("failed") and "429" in package["steps"]["ai"]
    assert package["metadata"]["source"] == "config" and package["metadata"]["title"] == "פרק בדיקה"
    assert package["steps"]["seo"] == "ok" and package["steps"]["thumbnail"] == "ok"