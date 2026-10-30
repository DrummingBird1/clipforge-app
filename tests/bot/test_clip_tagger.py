# tests/bot/test_clip_tagger.py
#
# בודק utils/media/clip_tagger.py (item: content-based auto-tagging). לא קורא ל-Gemini
# / Ollama אמיתיים - _parse_tags_response נבדק ישירות (טהור), ו-generate_tags_locally/
# generate_tags_with_gemini/generate_clip_tags נבדקים עם OLLAMA_URL מפנה לפורט
# שאין עליו שירות (מדמה "לא זמין" בלי תלות במצב האמיתי של המכונה - אותו דפוס
# בדיוק כמו test_local_vision_judge.py) ו-get_secret ממופתח.
import json
import os


import utils.media.clip_tagger as clip_tagger
from utils.media.clip_tagger import (
    _parse_tags_response,
    generate_clip_tags,
    generate_tags_locally,
    generate_tags_with_gemini,
    list_all_cached_tags,
    read_cached_tags,
    tags_cache_path,
)


def test_parse_tags_response_plain_json():
    raw = json.dumps({"tags": ["Goal", "Victory Screen"]})
    assert _parse_tags_response(raw) == ["Goal", "Victory Screen"]


def test_parse_tags_response_strips_markdown_fences():
    raw = "```json\n" + json.dumps({"tags": ["Save"]}) + "\n```"
    assert _parse_tags_response(raw) == ["Save"]


def test_parse_tags_response_caps_at_max_tags():
    raw = json.dumps({"tags": [f"tag{i}" for i in range(10)]})
    assert len(_parse_tags_response(raw)) == clip_tagger.MAX_TAGS


def test_parse_tags_response_drops_empty_and_whitespace_only_tags():
    raw = json.dumps({"tags": ["Goal", "", "   ", "Save"]})
    assert _parse_tags_response(raw) == ["Goal", "Save"]


def test_parse_tags_response_invalid_json_returns_empty_list():
    assert _parse_tags_response("not valid json{{{") == []


def test_parse_tags_response_missing_tags_key_returns_empty_list():
    assert _parse_tags_response(json.dumps({"something_else": 1})) == []


def test_parse_tags_response_tags_not_a_list_returns_empty_list():
    assert _parse_tags_response(json.dumps({"tags": "Goal"})) == []


def test_generate_tags_locally_returns_empty_when_no_readable_frames():
    assert generate_tags_locally(["/nonexistent/frame.jpg"]) == []


def test_generate_tags_locally_returns_empty_when_ollama_unreachable(tmp_path, monkeypatch):
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
    monkeypatch.setattr(clip_tagger, "OLLAMA_URL", "http://127.0.0.1:1")

    assert generate_tags_locally([str(frame)], model="llava:7b") == []


def test_generate_tags_with_gemini_returns_empty_without_api_key(tmp_path, monkeypatch):
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
    monkeypatch.setattr(clip_tagger, "get_secret", lambda key, default="": "")

    assert generate_tags_with_gemini([str(frame)]) == []


def test_generate_clip_tags_local_provider_skips_gemini_entirely(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(clip_tagger, "generate_tags_with_gemini", lambda *a, **kw: calls.append("gemini") or [])
    monkeypatch.setattr(clip_tagger, "generate_tags_locally", lambda *a, **kw: calls.append("local") or ["Goal"])

    result = generate_clip_tags(["frame.jpg"], provider="local")

    assert result == ["Goal"]
    assert calls == ["local"]


def test_generate_clip_tags_gemini_provider_returns_gemini_tags_when_available(monkeypatch):
    monkeypatch.setattr(clip_tagger, "generate_tags_with_gemini", lambda *a, **kw: ["Save"])
    monkeypatch.setattr(clip_tagger, "generate_tags_locally", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not be called")))

    assert generate_clip_tags(["frame.jpg"], provider="gemini") == ["Save"]


def test_generate_clip_tags_falls_back_to_local_when_gemini_empty_and_ollama_available(monkeypatch):
    monkeypatch.setattr(clip_tagger, "generate_tags_with_gemini", lambda *a, **kw: [])
    monkeypatch.setattr(clip_tagger, "is_ollama_available", lambda: True)
    monkeypatch.setattr(clip_tagger, "generate_tags_locally", lambda *a, **kw: ["Explosion"])

    assert generate_clip_tags(["frame.jpg"], provider="gemini") == ["Explosion"]


def test_generate_clip_tags_returns_empty_when_gemini_empty_and_ollama_unavailable(monkeypatch):
    monkeypatch.setattr(clip_tagger, "generate_tags_with_gemini", lambda *a, **kw: [])
    monkeypatch.setattr(clip_tagger, "is_ollama_available", lambda: False)

    assert generate_clip_tags(["frame.jpg"], provider="gemini") == []


# --- מטמון תגיות (item: clip gallery search/filter by tag) - משותף בין
# web_app.py לדסקטופ (ui/stats_tab.py). ---

def _write_cache(cache_dir, clip_path, tags):
    os.makedirs(cache_dir, exist_ok=True)
    with open(tags_cache_path(clip_path, cache_dir), "w", encoding="utf-8") as f:
        json.dump({"tags": tags}, f)


def test_tags_cache_path_includes_basename_and_mtime(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    cache_dir = str(tmp_path / ".tags_cache")

    path = tags_cache_path(str(clip), cache_dir)

    assert path == os.path.join(cache_dir, f"clip.mp4.{int(os.path.getmtime(str(clip)))}.json")


def test_read_cached_tags_returns_none_when_never_tagged(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")

    assert read_cached_tags(str(clip), str(tmp_path / ".tags_cache")) is None


def test_read_cached_tags_returns_saved_tags(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    cache_dir = str(tmp_path / ".tags_cache")
    _write_cache(cache_dir, str(clip), ["Goal", "Save"])

    assert read_cached_tags(str(clip), cache_dir) == ["Goal", "Save"]


def test_read_cached_tags_returns_empty_list_for_corrupt_cache_file(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    cache_dir = str(tmp_path / ".tags_cache")
    os.makedirs(cache_dir, exist_ok=True)
    with open(tags_cache_path(str(clip), cache_dir), "w", encoding="utf-8") as f:
        f.write("not valid json{{{")

    assert read_cached_tags(str(clip), cache_dir) == []


def test_list_all_cached_tags_returns_empty_list_when_cache_dir_missing(tmp_path):
    assert list_all_cached_tags(str(tmp_path / "nonexistent")) == []


def test_list_all_cached_tags_dedups_and_sorts_across_clips(tmp_path):
    cache_dir = str(tmp_path / ".tags_cache")
    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    clip_a.write_bytes(b"fake-a")
    clip_b.write_bytes(b"fake-b")
    _write_cache(cache_dir, str(clip_a), ["Goal", "Save"])
    _write_cache(cache_dir, str(clip_b), ["Save", "Explosion"])

    assert list_all_cached_tags(cache_dir) == ["Explosion", "Goal", "Save"]


def test_list_all_cached_tags_ignores_corrupt_cache_files(tmp_path):
    cache_dir = str(tmp_path / ".tags_cache")
    os.makedirs(cache_dir, exist_ok=True)
    with open(os.path.join(cache_dir, "broken.json"), "w", encoding="utf-8") as f:
        f.write("not valid json{{{")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    _write_cache(cache_dir, str(clip), ["Goal"])

    assert list_all_cached_tags(cache_dir) == ["Goal"]
