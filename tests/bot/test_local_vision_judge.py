# tests/bot/test_local_vision_judge.py
import json


import utils.media.local_vision_judge as local_vision_judge
from utils.media.local_vision_judge import _parse_judge_response, _sanitize_game_name, judge_clip_locally


def test_sanitize_game_name_strips_invalid_filesystem_chars():
    assert _sanitize_game_name('Counter-Strike: Global Offensive?') == "Counter-Strike Global Offensive"


def test_sanitize_game_name_strips_whitespace():
    assert _sanitize_game_name("  Portal 2  ") == "Portal 2"


def test_parse_judge_response_plain_json():
    raw = json.dumps({"game_name": "Portal 2", "interesting": True, "reason": "active puzzle solving"})
    interesting, game, reason = _parse_judge_response(raw, fallback_game="General Gameplay")
    assert interesting is True
    assert game == "Portal 2"
    assert reason == "active puzzle solving"


def test_parse_judge_response_strips_markdown_fences():
    raw = "```json\n" + json.dumps({"game_name": "Minecraft", "interesting": False, "reason": "loading screen"}) + "\n```"
    interesting, game, reason = _parse_judge_response(raw, fallback_game="General Gameplay")
    assert interesting is False
    assert game == "Minecraft"


def test_parse_judge_response_falls_back_to_fallback_game_when_missing():
    raw = json.dumps({"interesting": True, "reason": "no game field"})
    _, game, _ = _parse_judge_response(raw, fallback_game="General Gameplay")
    assert game == "General Gameplay"


def test_judge_clip_locally_returns_safe_default_when_no_readable_frames():
    interesting, game, reason = judge_clip_locally(["/nonexistent/frame.jpg"], fallback_game="Portal 2")
    assert interesting is True
    assert game == "Portal 2"
    assert "לא ניתן" in reason


def test_judge_clip_locally_returns_safe_default_when_ollama_unreachable(tmp_path, monkeypatch):
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")

    # מצביע לפורט שאין עליו שירות בכלל - מדמה Ollama לא זמין בלי תלות במצב האמיתי של המכונה
    monkeypatch.setattr(local_vision_judge, "OLLAMA_URL", "http://127.0.0.1:1")

    interesting, game, reason = judge_clip_locally([str(frame)], fallback_game="Portal 2", model="llava:7b")

    assert interesting is True
    assert game == "Portal 2"
    assert "נכשל" in reason
