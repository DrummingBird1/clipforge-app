# tests/bot/test_title_generator.py


import pytest

from utils.bot.title_generator import parse_gemini_json_response


def test_parses_plain_json_with_no_fences():
    text = '{"title": "Epic Save!", "description": "clutch moment", "hashtags": ["#rl", "#clip"]}'
    result = parse_gemini_json_response(text)
    assert result == {"title": "Epic Save!", "description": "clutch moment", "hashtags": ["#rl", "#clip"]}


def test_strips_json_code_fence():
    text = '```json\n{"title": "Wow", "description": "desc", "hashtags": ["#a"]}\n```'
    result = parse_gemini_json_response(text)
    assert result["title"] == "Wow"


def test_strips_plain_code_fence_without_json_marker():
    text = '```\n{"title": "Wow", "description": "desc", "hashtags": ["#a"]}\n```'
    result = parse_gemini_json_response(text)
    assert result["title"] == "Wow"


def test_missing_fields_default_to_empty():
    text = '{"title": "Only title"}'
    result = parse_gemini_json_response(text)
    assert result == {"title": "Only title", "description": "", "hashtags": []}


def test_strips_whitespace_from_title_and_description():
    text = '{"title": "  Spacey Title  ", "description": "  spacey desc  ", "hashtags": []}'
    result = parse_gemini_json_response(text)
    assert result["title"] == "Spacey Title"
    assert result["description"] == "spacey desc"


def test_invalid_json_raises():
    with pytest.raises(Exception):
        parse_gemini_json_response("not valid json at all")
