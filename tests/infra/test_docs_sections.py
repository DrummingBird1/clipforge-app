# tests/infra/test_docs_sections.py - גל 33: "📖 בתיעוד" ליד הגדרה בעורך-העל (utils/shared/docs_sections.py + /api/docs/section)
from utils.shared import docs_sections

from tests.web_app_support import client  # noqa: F401

SAMPLE = """# Video Editor

Intro paragraph about the editor.

## Options

- **Picture in picture** (`--pip <file>`, `--pip-position tl|tr`) - overlays a second video.
- **PiP position** (`--pip-position`) - where the small window sits.
- **Export codec** (`--codec h264|hevc|av1`) - `--nvenc-cq <n>` overrides quality.

A plain paragraph
that spans two lines and mentions loudness.
"""


def _write_doc(tmp_path, name="video_editor", text=SAMPLE):
    (tmp_path / f"{name}.md").write_text(text, encoding="utf-8")
    return str(tmp_path)


def test_split_blocks_one_block_per_bullet_and_paragraph():
    blocks = docs_sections.split_blocks(SAMPLE)
    texts = [t for _, t in blocks]
    assert texts[0] == "Intro paragraph about the editor."
    assert sum(t.startswith("- **") for t in texts) == 3
    assert blocks[-1] == ("Options", "A plain paragraph\nthat spans two lines and mentions loudness.")


def test_flag_matches_whole_flag_only(tmp_path):
    docs_dir = _write_doc(tmp_path)
    found = docs_sections.find_section("video_editor", ["--pip-position"], docs_dir=docs_dir)
    assert found["title"] == "Picture in picture"   # הסעיף הראשון שמזכיר את הדגל המלא
    found = docs_sections.find_section("video_editor", ["--pip"], docs_dir=docs_dir)
    assert found["title"] == "Picture in picture"
    assert docs_sections.find_section("video_editor", ["--pi"], docs_dir=docs_dir) is None


def test_terms_are_tried_in_priority_order(tmp_path):
    docs_dir = _write_doc(tmp_path)
    found = docs_sections.find_section("video_editor", ["--nothing", "--nvenc-cq", "loudness"], docs_dir=docs_dir)
    assert found["title"] == "Export codec"
    assert found["text"].startswith("**Export codec**")
    found = docs_sections.find_section("video_editor", ["--nothing", "LOUDNESS"], docs_dir=docs_dir)
    assert found["title"] == "Options"   # פסקה בלי הדגשה - הכותרת האחרונה


def test_unknown_doc_and_path_tricks_are_refused(tmp_path):
    docs_dir = _write_doc(tmp_path)
    assert docs_sections.find_section("../README", ["--pip"], docs_dir=docs_dir) is None
    assert docs_sections.find_section("secrets", ["--pip"], docs_dir=docs_dir) is None
    assert docs_sections.find_section("video_editor", ["", "x"], docs_dir=docs_dir) is None


def test_long_blocks_are_truncated(tmp_path):
    docs_dir = _write_doc(tmp_path, text="- **Long** (`--long`) " + "word " * 2000)
    found = docs_sections.find_section("video_editor", ["--long"], docs_dir=docs_dir)
    assert len(found["text"]) <= docs_sections.MAX_TEXT + 2
    assert found["text"].endswith("…")


def test_real_video_editor_doc_has_nvenc_section():
    found = docs_sections.find_section("video_editor", ["--nvenc-cq"])
    assert found and "--nvenc-cq" in found["text"]


def test_api_docs_section_route():
    resp = client.get("/api/docs/section", params={"doc": "video_editor", "q": "--no-such-flag|--nvenc-cq"})
    assert resp.status_code == 200
    assert "--nvenc-cq" in resp.json()["text"]
    assert client.get("/api/docs/section", params={"doc": "../x", "q": "--pip"}).status_code == 404
    assert client.get("/api/docs/section", params={"doc": "video_editor", "q": "--no-such-flag"}).status_code == 404
