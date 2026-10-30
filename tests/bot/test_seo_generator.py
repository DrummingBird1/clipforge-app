# tests/bot/test_seo_generator.py
import os

import pytest


import utils.bot.seo_generator as seo_generator
from utils.bot.seo_generator import (
    GAME_TAGS,
    detect_game_title,
    generate_seo_metadata,
    get_confetti_particles,
    get_encoder_args,
    sort_clip_to_smart_library,
)

_REAL_AI_ENABLED = seo_generator.ai_enabled


def test_detect_game_title_rocket_league():
    assert detect_game_title("C:/clips/RL_epic_save.mp4") == "Rocket League"


def test_detect_game_title_minecraft():
    assert detect_game_title("my_minecraft_base_tour.mp4") == "Minecraft"


def test_detect_game_title_fivem_or_gta():
    assert detect_game_title("gta_rp_heist.mp4") == "FiveM"
    assert detect_game_title("fivem_session_3.mp4") == "FiveM"


def test_detect_game_title_falls_back_to_gameplay():
    assert detect_game_title("random_clip_42.mp4") == "Gameplay"


def test_get_encoder_args_matches_by_substring_not_exact_text():
    # ה-dropdown בפועל שולח "AV1 (NVIDIA RTX Next-Gen)"/"HEVC (H.265 Ultra)",
    # לא "AV1"/"HEVC" גולמי - match מדויק מעולם לא היה תופס את אלה.
    assert get_encoder_args("AV1 (NVIDIA RTX Next-Gen)")[1] == "av1_nvenc"
    assert get_encoder_args("HEVC (H.265 Ultra)")[1] == "hevc_nvenc"
    assert get_encoder_args("Unknown Codec")[1] == "libx264"


def test_get_confetti_particles_returns_nonempty_list():
    particles = get_confetti_particles()
    assert len(particles) > 0
    assert all(isinstance(p, str) for p in particles)


def test_generate_seo_metadata_writes_files(tmp_path, monkeypatch):
    monkeypatch.setattr(seo_generator, "HISTORY_LOG_FILE", str(tmp_path / "history.txt"))
    clip_path = tmp_path / "RL_clip.mp4"
    clip_path.write_text("fake video bytes")

    result = generate_seo_metadata(str(clip_path))

    assert "Rocket League" in result
    assert GAME_TAGS["Rocket League"] in result
    meta_path = tmp_path / "RL_clip_metadata_seo.txt"
    assert meta_path.exists()
    assert meta_path.read_text(encoding="utf-8") == result
    assert (tmp_path / "history.txt").exists()


def test_history_log_lives_in_data_logs_not_the_project_root():
    # 19.10.2026: מהשורש ל-data/logs/ (נקרא מהקוד עצמו - ה-conftest מחליף את הקבועים בכל טסט)
    import importlib.util
    spec = importlib.util.find_spec("utils.bot.seo_generator")
    source = open(spec.origin, encoding="utf-8").read()
    assert "HISTORY_LOG_FILE = data_paths.path(data_paths.SEO_HISTORY_LOG)" in source   # 23.10.2026: השם מ-data_paths
    from utils.shared import data_paths
    assert data_paths.SEO_HISTORY_LOG == "logs/seo_history_log.txt" and data_paths.SEO_HISTORY_LOG.startswith(data_paths.LOGS + "/")


def test_new_history_log_starts_from_a_copy_of_the_old_root_one(tmp_path, monkeypatch):
    legacy = tmp_path / "seo_history_log.txt"
    legacy.write_text("old sheet\n\n", encoding="utf-8")
    new_log = tmp_path / "data" / "logs" / "seo_history_log.txt"
    monkeypatch.setattr(seo_generator, "LEGACY_HISTORY_LOG_FILE", str(legacy))
    monkeypatch.setattr(seo_generator, "HISTORY_LOG_FILE", str(new_log))
    clip_path = tmp_path / "RL_clip.mp4"
    clip_path.write_text("fake video bytes")

    generate_seo_metadata(str(clip_path))
    generate_seo_metadata(str(clip_path))

    text = new_log.read_text(encoding="utf-8")
    assert text.startswith("old sheet\n\n") and text.count("Rocket League") >= 2
    assert text.count("old sheet") == 1  # הועתק פעם אחת, רק כשהחדש עוד לא היה
    assert legacy.read_text(encoding="utf-8") == "old sheet\n\n"  # הישן לא השתנה


def test_generate_seo_metadata_handles_errors_gracefully(monkeypatch):
    # נתיב לא תקין (תו null) גורם ל-open() לזרוק - הפונקציה תופסת ומחזירה
    # הודעת שגיאה כמחרוזת במקום להפיל את כל הפייפליין.
    result = generate_seo_metadata("Z:/\x00invalid/path.mp4")
    assert "Failed" in result


def test_sort_clip_to_smart_library_local_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(seo_generator, "EXPORTS_DIR", str(tmp_path / "workspace" / "exports"))
    clip_path = tmp_path / "source" / "gta_clip.mp4"
    clip_path.parent.mkdir()
    clip_path.write_text("fake video bytes")

    result = sort_clip_to_smart_library(str(clip_path), base_backup_dir=None)

    assert os.path.exists(result)
    assert "FiveM" in result
    assert "workspace" in result and "exports" in result


def test_sort_clip_to_smart_library_uses_external_backup_dir_when_available(tmp_path):
    external_dir = tmp_path / "external_drive"
    external_dir.mkdir()
    clip_path = tmp_path / "minecraft_clip.mp4"
    clip_path.write_text("fake video bytes")

    result = sort_clip_to_smart_library(str(clip_path), base_backup_dir=str(external_dir))

    assert str(external_dir) in result
    assert "Minecraft" in result


def test_sort_clip_to_smart_library_returns_original_path_on_failure(tmp_path, monkeypatch):
    # בלי monkeypatch על EXPORTS_DIR, os.makedirs(target_folder) (שרץ *לפני*
    # shutil.copy2 הכושל) היה יוצר בפועל workspace/exports/... תחת הפרויקט
    # האמיתי - רגרסיה אמיתית שנתפסה כשזה בדיוק מה שקרה (ראו item: reorganize
    # workspace by orientation, שמחק את workspace/exports/ הישן וזה חזר לבד).
    monkeypatch.setattr(seo_generator, "EXPORTS_DIR", str(tmp_path / "workspace" / "exports"))
    missing_clip = "Z:/does/not/exist/clip.mp4"
    result = sort_clip_to_smart_library(missing_clip, base_backup_dir=None)
    assert result == missing_clip


# --- גל 32: Gemini במקום התאמת מילת-מפתח, וזיהוי משחק לפי מילה שלמה ---

def test_detect_game_title_matches_abbreviations_only_as_whole_words():
    # "rl" בתוך world/girl ו-"mc" בתוך שם אחר זיהו בעבר משחק לא נכון
    assert detect_game_title("world_tour_girl.mp4") == "Gameplay"
    assert detect_game_title("emcee_battle.mp4") == "Gameplay"
    assert detect_game_title("mc-clip.mp4") == "Minecraft"
    assert detect_game_title("gta5_heist.mp4") == "FiveM"
    assert detect_game_title("RLShorts #12.mp4") == "Rocket League"


def test_detect_game_title_prefers_the_file_name_over_the_folder():
    assert detect_game_title("E:/Rocket League/minecraft_build.mp4") == "Minecraft"
    assert detect_game_title("E:/Rocket League/clip_3.mp4") == "Rocket League"


def test_generate_seo_uses_gemini_and_merges_game_tags(tmp_path, monkeypatch):
    calls = []

    def fake_generate_metadata(path, game):
        calls.append(game)
        return {"title": "  Insane   ceiling shot 🚀 ", "description": "From the replay buffer",
                "hashtags": ["#RocketLeague", "rl", "#ceiling shot", "#gaming", "#flip"]}

    import utils.bot.title_generator as title_generator
    monkeypatch.setattr(title_generator, "generate_metadata", fake_generate_metadata)
    monkeypatch.setattr(seo_generator, "ai_enabled", lambda: True)
    clip = tmp_path / "RL_replay.mp4"
    clip.write_bytes(b"x")

    seo = seo_generator.generate_seo_with_sheet(str(clip))

    assert calls == ["Rocket League"]
    assert seo["source"] == "ai" and seo["title"] == "Insane ceiling shot 🚀"
    # כפילויות (באותיות שונות) יורדות, רווחים וסימנים נמחקים, עד MAX_HASHTAGS
    assert seo["hashtags"][:3] == ["#RocketLeague", "#rl", "#ceilingshot"]
    assert len(seo["hashtags"]) == seo_generator.MAX_HASHTAGS
    assert len({tag.lower() for tag in seo["hashtags"]}) == len(seo["hashtags"])
    assert seo["tiktok_caption"].startswith("Insane ceiling shot 🚀 #RocketLeague")
    assert seo["youtube_tags"][0] == "RocketLeague"
    assert "🤖 Gemini" in seo["sheet"] and "From the replay buffer" in seo["sheet"]
    assert (tmp_path / "RL_replay_metadata_seo.txt").read_text(encoding="utf-8") == seo["sheet"]


def test_generate_seo_falls_back_to_the_template_when_gemini_fails(tmp_path, monkeypatch):
    import utils.bot.title_generator as title_generator

    def broken(*_args):
        raise RuntimeError("GEMINI_API_KEY לא מוגדר")

    monkeypatch.setattr(title_generator, "generate_metadata", broken)
    monkeypatch.setattr(seo_generator, "ai_enabled", lambda: True)
    clip = tmp_path / "minecraft_base.mp4"
    clip.write_bytes(b"x")

    monkeypatch.setattr(seo_generator.ui_language, "current", lambda: "he")   # 30.10.2026: הכותרת בשפת ההתקנה
    seo = seo_generator.generate_seo(str(clip))

    assert seo["source"] == "template"
    assert seo["tiktok_caption"] == f"הקליפ הכי מטורף שלי ב-Minecraft! 🔥 {GAME_TAGS['Minecraft']}"
    monkeypatch.setattr(seo_generator.ui_language, "current", lambda: "en")
    assert seo_generator.generate_seo(str(clip))["title"] == "My craziest Minecraft clip! 🔥"   # התקנה באנגלית


def test_generate_seo_skips_gemini_when_the_setting_is_off(tmp_path, monkeypatch):
    import utils.bot.title_generator as title_generator
    monkeypatch.setattr(title_generator, "generate_metadata", lambda *_a: pytest.fail("Gemini נקרא למרות seo_ai כבוי"))
    monkeypatch.setattr(seo_generator, "ai_enabled", _REAL_AI_ENABLED)  # conftest מכבה אותו לכל הטסטים
    settings = tmp_path / "rocket_settings.json"
    monkeypatch.setattr(seo_generator, "ROCKET_SETTINGS_PATH", str(settings))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")

    assert seo_generator.ai_enabled() is True  # אין קובץ הגדרות - ברירת מחדל פעיל
    settings.write_text('{"seo_ai": false}', encoding="utf-8")
    assert seo_generator.ai_enabled() is False
    assert seo_generator.generate_seo(str(clip))["source"] == "template"


def test_generate_seo_reuses_the_rocket_shorts_ai_file_without_calling_gemini(tmp_path, monkeypatch):
    import utils.bot.title_generator as title_generator
    monkeypatch.setattr(title_generator, "generate_metadata", lambda *_a: pytest.fail("Gemini נקרא פעמיים"))
    clip = tmp_path / "Shorts #9.mp4"
    clip.write_bytes(b"x")
    (tmp_path / "Shorts #9_ai_metadata.txt").write_text(
        "Title: Flip reset: the sequel\nDescription: one: line\nHashtags: #rl #flipreset\n", encoding="utf-8")

    seo = seo_generator.generate_seo(str(clip))

    assert seo["source"] == "ai" and seo["title"] == "Flip reset: the sequel" and seo["description"] == "one: line"
    assert seo["hashtags"][:2] == ["#rl", "#flipreset"]
