# tests/studio/test_web_app_editor_wave3.py
#
# גל 3 של 102-ההצעות - שדות וקלט (items 19-28): בוררי-קבצים 📂, אימות נתיב חי,
# עורך טווחים ויזואלי, בורר צבע, בורר גופנים מהמערכת, קלט mm:ss, סליידר חיתוך
# לפי הקובץ הראשון, ℹ️ בלחיצה, היסטוריה לכל שדות-הטקסט, ושדה-מספר לסליידרים.
# חלק ראשון: endpoints/פרסור בצד השרת (TestClient); חלק שני: דפדפן אמיתי.
import os
import subprocess


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.video.video_editor import parse_time_seconds, sanitize_batch_overrides

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


# --- 24: קלט mm:ss ---

@pytest.mark.parametrize("raw,expected", [
    (90, 90.0), ("90", 90.0), ("12.5", 12.5), ("1:30", 90.0), ("01:30", 90.0), ("1:30.5", 90.5),
    ("1:02:03", 3723.0), (" 2:00 ", 120.0), (0, 0.0),
])
def test_parse_time_seconds_accepts_numbers_and_clock_text(raw, expected):
    assert parse_time_seconds(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "abc", "-5", -3, "1:xx", True, "1::2"])
def test_parse_time_seconds_rejects_invalid(raw):
    assert parse_time_seconds(raw) is None


def test_build_extra_args_accepts_clock_text_for_time_fields():
    args = web_app._build_extra_args("video_editor.py", {
        "trim_start": "1:30", "trim_duration": "0:45", "target_seconds": "1:00",
        "fade_in_seconds": "0:02", "fade_out_seconds": 1.5,
    })
    assert args[args.index("--trim-start") + 1] == "90.0"
    assert args[args.index("--trim-duration") + 1] == "45.0"
    assert args[args.index("--target-seconds") + 1] == "60"
    assert args[args.index("--fade-in-seconds") + 1] == "2.0"
    assert args[args.index("--fade-out-seconds") + 1] == "1.5"


def test_invalid_time_text_is_dropped_not_crashing():
    args = web_app._build_extra_args("video_editor.py", {"trim_start": "abc", "trim_duration": "x", "fade_in_seconds": "?"})
    assert args == ["--codec", "h264"]


def test_batch_override_trim_accepts_clock_text():
    assert sanitize_batch_overrides({"a.mp4": {"trim_start": "0:05", "trim_duration": "1:00"}}) == {"a.mp4": {"trim_start": 5.0, "trim_duration": 60.0}}


# --- 20: אימות נתיב חי ---

def test_path_info_reports_missing_file_dir_and_existing(tmp_path):
    f = tmp_path / "logo.png"
    f.write_bytes(b"12345")
    missing = client.get("/api/path_info", params={"path": str(tmp_path / "nope.png")}).json()
    assert missing["exists"] is False
    directory = client.get("/api/path_info", params={"path": str(tmp_path)}).json()
    assert directory["is_dir"] is True and directory["is_file"] is False
    existing = client.get("/api/path_info", params={"path": f'"{f}"'}).json()  # גרשיים מהעתקת-נתיב נחתכים
    assert existing == {"exists": True, "is_file": True, "is_dir": False, "size": 5, "ext": ".png"}
    assert client.get("/api/path_info", params={"path": "  "}).json()["exists"] is False


# --- 23: בורר גופנים ---

def test_list_system_font_families_reads_real_family_names(tmp_path):
    windows_fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    arial = os.path.join(windows_fonts, "arial.ttf")
    if not os.path.exists(arial):
        pytest.skip("arial.ttf לא קיים בסביבה הזו")
    import shutil
    shutil.copy(arial, tmp_path / "some_renamed_file.ttf")
    (tmp_path / "not_a_font.ttf").write_bytes(b"garbage")
    (tmp_path / "readme.txt").write_text("x")
    assert web_app.list_system_font_families([str(tmp_path), str(tmp_path / "missing")]) == ["Arial"]


def test_system_fonts_endpoint_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(web_app, "_system_fonts_cache", None)
    monkeypatch.setattr(web_app, "list_system_font_families", lambda font_dirs=None: calls.append(1) or ["Arial", "Segoe UI"])
    assert client.get("/api/system_fonts").json() == {"fonts": ["Arial", "Segoe UI"]}
    assert client.get("/api/system_fonts").json() == {"fonts": ["Arial", "Segoe UI"]}
    assert calls == [1]


# --- 25: probe לקובץ הראשון (סליידר החיתוך) ---

def _ffmpeg_available():
    import shutil
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    exe = get_ffmpeg_exe()
    return (os.path.isabs(exe) and os.path.exists(exe)) or bool(shutil.which(exe))


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg לא זמין")
def test_probe_endpoint_returns_duration_and_dimensions(tmp_path):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    clip = tmp_path / "clip.mp4"
    subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=160x120:rate=10", "-pix_fmt", "yuv420p", str(clip)],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)
    info = client.get("/api/video_editor/probe", params={"path": str(clip)}).json()
    assert abs(info["duration"] - 3.0) < 0.2
    assert (info["width"], info["height"]) == (160, 120)
    assert info["hdr"] is False and info["has_audio"] is False


def test_probe_endpoint_rejects_missing_and_data_dir(tmp_path):
    assert client.get("/api/video_editor/probe", params={"path": str(tmp_path / "x.mp4")}).status_code == 400
    token_file = os.path.join(web_app.DATA_DIR, "web_app_token.txt")
    if os.path.exists(token_file):
        assert client.get("/api/video_editor/probe", params={"path": token_file}).status_code == 403


# --- דפדפן אמיתי ---

def _set_value(page, element_id, value):
    page.evaluate("([id, v]) => _veSetFieldValue(document.getElementById(id), v)", [element_id, value])


def test_browser_path_fields_get_browse_button_and_live_validation(editor_page, tmp_path):
    for field_id in ("veWatermarkPath", "vePipPath", "veLutPath", "veReplaceAudioPath"):
        assert editor_page.evaluate(f"() => !!document.querySelector('#{field_id} ~ .ve-browse-btn')"), field_id
    _set_value(editor_page, "veWatermarkPath", str(tmp_path / "missing.png"))
    editor_page.wait_for_function("() => document.querySelector('.ve-field-msg[data-for=veWatermarkPath]').textContent.includes('לא נמצא')")
    assert editor_page.evaluate("() => document.getElementById('veWatermarkPath').classList.contains('ve-invalid')")
    real = tmp_path / "logo.png"
    real.write_bytes(b"x" * 10)
    _set_value(editor_page, "veWatermarkPath", str(real))
    editor_page.wait_for_function("() => document.querySelector('.ve-field-msg[data-for=veWatermarkPath]').textContent.startsWith('✓')")
    wrong_type = tmp_path / "logo.txt"
    wrong_type.write_text("x")
    _set_value(editor_page, "veWatermarkPath", str(wrong_type))
    editor_page.wait_for_function("() => document.querySelector('.ve-field-msg[data-for=veWatermarkPath]').textContent.includes('סוג לא צפוי')")


def test_browser_file_picker_filters_by_type_and_fills_field(editor_page, tmp_path):
    for name in ("look.cube", "clip.mp4", "notes.txt"):
        (tmp_path / name).write_text("x")
    _set_value(editor_page, "veLutPath", str(tmp_path / "placeholder.cube"))
    editor_page.evaluate("() => openVeFieldFileBrowser('veLutPath')")
    editor_page.wait_for_selector("#modalBg.show")
    listed = editor_page.evaluate("() => Array.from(document.querySelectorAll('#modalList div')).map(d => d.textContent)")
    assert any("look.cube" in row for row in listed)
    assert not any("clip.mp4" in row or "notes.txt" in row for row in listed)
    editor_page.click("#modalList div:has-text('look.cube')")
    assert editor_page.evaluate("() => document.getElementById('veLutPath').value").endswith("look.cube")
    assert editor_page.evaluate("() => state.browseExtensions") is None


def test_browser_visual_range_editor_writes_json(editor_page):
    editor_page.click("#veRangesEditor > button")
    editor_page.click("#veRangesEditor > button")
    rows = editor_page.locator("#veRangesEditor .ve-range-row")
    assert rows.count() == 2
    rows.nth(1).locator("input").nth(0).fill("1:10")
    rows.nth(1).locator("input").nth(0).dispatch_event("change")
    rows = editor_page.locator("#veRangesEditor .ve-range-row")
    rows.nth(1).locator("input").nth(1).fill("1:20.5")
    rows.nth(1).locator("input").nth(1).dispatch_event("change")
    assert editor_page.evaluate("() => JSON.parse(document.getElementById('veRemoveRanges').value)") == [[5, 10], [70, 80.5]]
    # שורה לא-תקינה מסומנת ולא נשלחת
    rows = editor_page.locator("#veRangesEditor .ve-range-row")
    rows.nth(0).locator("input").nth(1).fill("0:01")
    rows.nth(0).locator("input").nth(1).dispatch_event("change")
    assert editor_page.evaluate("() => document.querySelectorAll('#veRangesEditor .ve-range-row.bad').length") == 1
    assert editor_page.evaluate("() => JSON.parse(document.getElementById('veRemoveRanges').value)") == [[70, 80.5]]


def test_browser_range_editor_follows_profile_load_and_json_toggle(editor_page):
    editor_page.evaluate("() => _applyVideoEditorFields({remove_ranges: '[[1,2],[65,70]]'})")
    values = editor_page.evaluate("() => Array.from(document.querySelectorAll('#veRangesEditor .ve-range-row input')).map(i => i.value)")
    assert values == ["0:01", "0:02", "1:05", "1:10"]
    editor_page.click("#veRemoveRangesJsonToggle")
    assert editor_page.evaluate("() => document.getElementById('veRemoveRanges').hidden") is False
    assert editor_page.evaluate("() => document.getElementById('veRangesEditor').hidden") is True


def test_browser_color_swatch_syncs_both_ways(editor_page):
    _set_value(editor_page, "veChromakeyColor", "0x112233")
    assert editor_page.evaluate("() => document.querySelector('.ve-color-swatch[data-for=veChromakeyColor]').value") == "#112233"
    editor_page.evaluate("() => { const s = document.querySelector('.ve-color-swatch[data-for=veCaptionColor]'); s.value = '#abcdef'; s.dispatchEvent(new Event('input', {bubbles: true})); }")
    assert editor_page.evaluate("() => document.getElementById('veCaptionColor').value") == "#ABCDEF"
    editor_page.evaluate("() => { const s = document.querySelector('.ve-color-swatch[data-for=veChromakeyBgColor]'); s.value = '#00ff00'; s.dispatchEvent(new Event('input', {bubbles: true})); }")
    assert editor_page.evaluate("() => document.getElementById('veChromakeyBgColor').value") == "0x00FF00"


def test_browser_font_inputs_use_system_font_list(editor_page):
    assert editor_page.evaluate("() => document.getElementById('veCaptionFont').getAttribute('list')") == "veSystemFontsList"
    # גל 10: הטקסט הקבוע הפך לשכבת טקסט - בודקים את גופן הכתוביות (שורת העיצוב
    # מוצגת רק כשכתוביות פעילות - חשיפה מדורגת)
    _set_value(editor_page, "veCaptions", True)
    editor_page.evaluate("() => document.querySelector('[data-subcat=captions]').closest('details').open = true")
    editor_page.focus("#veCaptionFont")
    editor_page.wait_for_function("() => document.querySelectorAll('#veSystemFontsList option').length > 0", timeout=20000)
    _set_value(editor_page, "veCaptionFont", "Consolas")
    assert "Consolas" in editor_page.evaluate("() => document.querySelector('.ve-font-preview[data-for=veCaptionFont]').style.fontFamily")


def test_browser_time_fields_accept_mm_ss(editor_page):
    editor_page.fill("#veTrimStart", "1:30")
    editor_page.dispatch_event("#veTrimStart", "input")
    editor_page.fill("#veFadeOutSeconds", "0:02.5")
    editor_page.dispatch_event("#veFadeOutSeconds", "input")
    opts = editor_page.evaluate("() => _collectRunOptions()")
    assert opts["trim_start"] == 90 and opts["fade_out_seconds"] == 2.5
    assert "90" in editor_page.inner_text(".ve-time-hint[data-for=veTrimStart]")
    editor_page.fill("#veTrimStart", "abc")
    editor_page.dispatch_event("#veTrimStart", "input")
    assert editor_page.evaluate("() => document.getElementById('veTrimStart').classList.contains('ve-invalid')")
    assert editor_page.evaluate("() => _collectRunOptions().trim_start") == 0


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg לא זמין")
def test_browser_trim_slider_follows_first_file(editor_page, tmp_path):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc=duration=20:size=160x120:rate=5", "-pix_fmt", "yuv420p", str(tmp_path / "a.mp4")],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)
    editor_page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(tmp_path))
    editor_page.wait_for_function("() => !document.getElementById('veTrimSliderBox').hidden", timeout=15000)
    assert "a.mp4" in editor_page.inner_text("#veTrimSliderBox")
    editor_page.evaluate("""() => { const [start, end] = document.querySelectorAll('#veTrimSliderBox input[type=range]');
        start.value = '4'; start.dispatchEvent(new Event('input', {bubbles: true}));
        end.value = '10'; end.dispatchEvent(new Event('input', {bubbles: true})); }""")
    opts = editor_page.evaluate("() => _collectRunOptions()")
    assert opts["trim_start"] == 4 and opts["trim_duration"] == 6
    editor_page.evaluate("""() => { const end = document.querySelectorAll('#veTrimSliderBox input[type=range]')[1];
        end.value = end.max; end.dispatchEvent(new Event('input', {bubbles: true})); }""")
    assert editor_page.evaluate("() => _collectRunOptions().trim_duration") is None


def test_browser_info_button_toggles_inline_help(editor_page):
    btn = editor_page.locator("#veLoudnorm").locator("xpath=ancestor::div[contains(@class,'ve-row')]").locator(".ve-info-btn")
    btn.click()
    assert "LUFS" in editor_page.inner_text(".ve-info-box")
    btn.click()
    assert editor_page.locator(".ve-info-box").count() == 0


def test_browser_every_text_field_gets_history(editor_page):
    ids = editor_page.evaluate("() => _veHistoryFieldIds()")
    for expected in ("veNumberPrefix", "veFps", "veWatermarkPath", "veOutputTemplate"):
        assert expected in ids
    # גל 10: שדות ישנים מוסתרים (#veLegacyFields) לא מקבלים היסטוריה - אין להם UI
    for excluded in ("veTrimStart", "veCaptionFont", "veProfileName", "veRemoveRanges", "veText"):
        assert excluded not in ids
    assert editor_page.evaluate("() => document.getElementById('veOutputTemplate').getAttribute('list')") == "veOutputTemplateHistory"


def test_browser_slider_number_inputs_sync_both_ways(editor_page):
    _set_value(editor_page, "veWatermarkPath", r"C:\logo.png")  # שורות גודל/שקיפות מוצגות רק כשיש watermark
    editor_page.wait_for_function("() => !document.querySelector('[data-card=logo]').hidden")  # כרטיס הלוגו נחשף
    editor_page.fill(".ve-range-number[data-for=veWatermarkScale]", "30")
    editor_page.dispatch_event(".ve-range-number[data-for=veWatermarkScale]", "change")
    assert editor_page.evaluate("() => document.getElementById('veWatermarkScale').value") == "30"
    # סליידר באחוזים (0-1 בשדה, 0-100 במספר)
    editor_page.evaluate("() => { const r = document.getElementById('veLutIntensity'); r.value = '0.35'; r.dispatchEvent(new Event('input', {bubbles: true})); }")
    assert editor_page.evaluate("() => document.querySelector('.ve-range-number[data-for=veLutIntensity]').value") == "35"
    assert editor_page.evaluate("() => getComputedStyle(document.getElementById('veWatermarkOpacityValue')).display") == "none"
