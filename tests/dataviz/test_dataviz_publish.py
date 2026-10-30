# tests/dataviz/test_dataviz_publish.py
#
# שלבי הפרסום של סרטוני נתונים (utils/dataviz_publish.py + הצינור ב-dataviz_maker.py) ומצב ה-preview:
# כותרת/SEO מההגדרות, Gemini אופציונלי, תמונה ממוזערת, קובץ אישור, וכשלים שלא מפילים את הרינדור.
# הרצה אמיתית של סרטון (ffmpeg אמיתי) בטסט האחרון - קטן מאוד כדי להישאר מהיר.
import importlib.util
from tests import PROJECT_ROOT
import json
import os
import subprocess
import sys

import pytest

from dataviz.config import load_config, mode_timing, preview_config, validate
from tests.dataviz_helpers import write_episode
from tests.media_support import needs_ffmpeg
from dataviz.web import publish as dp

BASE_DIR = PROJECT_ROOT
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "dataviz_maker.py")
TINY_VIDEO = {"width": 320, "height": 180, "dpi": 40, "fps": 10}
TINY_TIMING = {"intro_seconds": 1, "outro_seconds": 1, "base_frames_per_day": 0.02, "step": 0.05, "strict_step": False}


def _config(tmp_path, **overrides):
    folder = write_episode(tmp_path, overrides=overrides)
    return load_config(os.path.join(folder, "config.yaml"))


def _fake_thumb(video, out, **kwargs):
    with open(out, "wb") as f:
        f.write(b"jpg")
    _fake_thumb.calls.append((video, kwargs["title_text"]))


_fake_thumb.calls = []


def test_publish_defaults_are_off_and_validated(tmp_path):
    config = _config(tmp_path)
    assert config["publish"]["enabled"] is False and config["publish"]["approval"] is True
    assert validate({**config, "publish": {**config["publish"], "enabled": "yes", "hashtags": "x"}}) == [
        "publish.enabled צריך להיות true או false.", "publish.hashtags צריך להיות רשימת טקסטים."]


def test_metadata_comes_from_config_with_publish_overrides(tmp_path):
    config = _config(tmp_path, publish={"title": "כותרת ליוטיוב " + "ש" * 120, "hashtags": ["#טסט", "טסט", "a b!"]})

    meta = dp.build_metadata(config)

    assert meta["source"] == "config"
    assert len(meta["youtube_title"]) == dp.YOUTUBE_TITLE_MAX
    assert meta["description"] == "תת-כותרת"                      # subtitle של הפרק
    assert meta["hashtags"] == ["#טסט", "#ab", "#dataviz", "#DataIsBeautiful"]
    assert meta["tiktok_caption"].endswith("#טסט #ab #dataviz #DataIsBeautiful")


def test_ai_metadata_is_used_only_when_requested_and_failure_falls_back(tmp_path):
    video = str(tmp_path / "ep.mp4")
    calls = []

    def ai(path):
        calls.append(path)
        return {"title": "כותרת מ-AI", "description": "תיאור", "hashtags": ["AI"]}

    off = dp.prepare_publish(video, _config(tmp_path), ai_metadata=ai, make_thumbnail=_fake_thumb)
    assert calls == [] and off["metadata"]["title"] == "פרק בדיקה"

    on = dp.prepare_publish(video, _config(tmp_path, publish={"seo_ai": True}), ai_metadata=ai, make_thumbnail=_fake_thumb)
    assert calls == [video] and on["metadata"]["title"] == "כותרת מ-AI" and on["metadata"]["source"] == "ai"
    assert on["metadata"]["hashtags"][0] == "#AI"

    def broken(path):
        raise RuntimeError("quota")

    failed = dp.prepare_publish(video, _config(tmp_path, publish={"seo_ai": True}), ai_metadata=broken, make_thumbnail=_fake_thumb)
    assert failed["steps"]["ai"] == "failed: quota" and failed["metadata"]["title"] == "פרק בדיקה"


def test_prepare_writes_thumbnail_sheet_and_pending_sidecar(tmp_path):
    video = str(tmp_path / "ep.mp4")
    _fake_thumb.calls.clear()

    package = dp.prepare_publish(video, _config(tmp_path), make_thumbnail=_fake_thumb)

    assert package["status"] == dp.PENDING and package["steps"] == {"seo": "ok", "thumbnail": "ok"}
    assert _fake_thumb.calls == [(video, "פרק בדיקה")]            # הכותרת על התמונה
    assert os.path.isfile(tmp_path / "ep_thumb.jpg") and os.path.isfile(tmp_path / "ep_metadata_seo.txt")
    sheet = (tmp_path / "ep_metadata_seo.txt").read_text(encoding="utf-8")
    assert "[YOUTUBE TITLE]:\nפרק בדיקה" in sheet and "#dataviz" in sheet
    assert dp.load_package(video) == dp.load_package(dp.sidecar_path(video))
    assert json.loads((tmp_path / "ep.publish.json").read_text(encoding="utf-8"))["video"] == "ep.mp4"


def test_thumbnail_failure_and_skip_are_recorded_not_raised(tmp_path):
    video = str(tmp_path / "ep.mp4")

    def boom(*args, **kwargs):
        raise RuntimeError("ffmpeg נפל")

    failed = dp.prepare_publish(video, _config(tmp_path), make_thumbnail=boom)
    assert failed["steps"]["thumbnail"] == "failed: ffmpeg נפל" and failed["thumbnail"] == ""

    skipped = dp.prepare_publish(video, _config(tmp_path, publish={"thumbnail": False}), make_thumbnail=boom)
    assert skipped["steps"]["thumbnail"] == "skipped"

    no_approval = dp.prepare_publish(video, _config(tmp_path, publish={"approval": False}), make_thumbnail=_fake_thumb)
    assert no_approval["status"] == dp.APPROVED


def test_decision_changes_status_once_and_never_silently_overwrites(tmp_path):
    video = str(tmp_path / "ep.mp4")
    dp.prepare_publish(video, _config(tmp_path), make_thumbnail=_fake_thumb)
    assert [p["video"] for p in dp.list_packages(str(tmp_path), dp.PENDING)] == ["ep.mp4"]

    decided = dp.set_decision(video, dp.REJECTED)

    assert decided["status"] == dp.REJECTED and decided["decided_at"]
    assert dp.list_packages(str(tmp_path), dp.PENDING) == []
    with pytest.raises(ValueError, match="כבר התקבלה החלטה"):
        dp.set_decision(video, dp.APPROVED)
    with pytest.raises(ValueError, match="החלטה לא מוכרת"):
        dp.set_decision(video, "maybe")
    (tmp_path / "bad.publish.json").write_text("{}", encoding="utf-8")
    assert len(dp.list_packages(str(tmp_path))) == 1               # קובץ לא תקין מדולג


def test_preview_keeps_the_layout_but_shrinks_the_pixels(tmp_path):
    config = _config(tmp_path)
    small = preview_config(config)

    assert (small["video"]["width"], small["video"]["height"], small["video"]["dpi"]) == (720, 444, 60)
    assert config["video"]["width"] == 1440                          # המקור לא השתנה
    assert small["video"]["width"] / small["video"]["dpi"] == config["video"]["width"] / config["video"]["dpi"]
    assert mode_timing(config, "preview") == {"intro": 30, "outro": 30, "main": 300}
    with pytest.raises(ValueError):
        preview_config(config, 1.5)


@pytest.fixture(scope="module")
def maker():
    spec = importlib.util.spec_from_file_location("dataviz_maker_publish_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preview_output_name_and_publish_step_without_gemini(maker, tmp_path, monkeypatch):
    config = {"name": "ep", "video": {"width": 100, "height": 50, "output_name": ""}}
    assert maker.output_paths(config, "preview", "W")[1].endswith("ep_preview.mp4")

    results = {}
    video = str(tmp_path / "ep.mp4")
    full = _config(tmp_path, publish={"enabled": True, "thumbnail": False})
    maker.run_publish(video, full, results)
    assert results["published_packages"] == 1 and dp.load_package(video)["status"] == dp.PENDING


@needs_ffmpeg
def test_real_render_publishes_a_package_and_decide_updates_it(tmp_path):
    folder = write_episode(tmp_path, overrides={"video": TINY_VIDEO, "timing": TINY_TIMING, "publish": {"enabled": True}},
                           name="real")
    out = tmp_path / "out"
    env = {**os.environ, "PYTHONUTF8": "1"}

    run = subprocess.run([sys.executable, SCRIPT, "--input_dir", folder, "--output_dir", str(out)], capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=300, cwd=BASE_DIR, env=env)

    assert run.returncode == 0, run.stdout + run.stderr
    target = out / "dataviz" / "outputs" / "horizontal"
    assert sorted(p.name for p in target.iterdir()) == ["real.chapters.txt", "real.mp4", "real.publish.json",   # גל 55: פרקים ביוטיוב
                                                        "real_metadata_seo.txt", "real_thumb.jpg"]
    assert (target / "real_thumb.jpg").stat().st_size > 1000          # JPEG אמיתי מ-ffmpeg
    assert dp.load_package(str(target / "real.mp4"))["status"] == dp.PENDING

    decide = subprocess.run([sys.executable, SCRIPT, "--decide", "approved", "--package", str(target / "real.mp4")],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, cwd=BASE_DIR, env=env)
    assert decide.returncode == 0, decide.stdout + decide.stderr
    assert dp.load_package(str(target / "real.mp4"))["status"] == dp.APPROVED