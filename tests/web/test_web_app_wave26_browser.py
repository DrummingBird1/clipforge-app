# tests/web/test_web_app_wave26_browser.py
#
# גל 26 בדפדפן אמיתי: שכבת B-roll בעורך השכבות (כל השדות נכתבים ל-JSON של השכבות),
# תווית בציר-הזמן, ידית גרירה רק לחלון (PiP), והנגן החי יוצר וידאו מסונכרן לשכבה.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _add_broll(page, clip_path):
    page.evaluate("() => { const d = document.querySelector('details[data-cat=layers]'); d.open = true; }")
    page.click("button[onclick=\"addVeLayer('video')\"]")
    row = "#veLayersRows .ve-layer-row[data-type=video]"
    page.wait_for_selector(row)
    page.fill(f"{row} input[data-field=path]", clip_path)
    page.dispatch_event(f"{row} input[data-field=path]", "input")
    return row


def test_a_broll_layer_row_writes_every_field(editor_page, tmp_path):
    page = editor_page
    clip = tmp_path / "broll.mp4"
    clip.write_bytes(b"x")
    row = _add_broll(page, str(clip))
    for field, value in (("start", "0:02"), ("end", "5"), ("source_in", "1:30")):
        page.fill(f"{row} input[data-field={field}]", value)
        page.dispatch_event(f"{row} input[data-field={field}]", "input")
    page.select_option(f"{row} select[data-field=fit]", "pip")
    page.select_option(f"{row} select[data-field=audio]", "replace")
    page.fill(f"{row} input[data-field=scale]", "40")
    page.dispatch_event(f"{row} input[data-field=scale]", "input")
    layer = page.evaluate("() => _veLayersValue()[0]")
    assert layer["type"] == "video" and layer["path"] == str(clip)
    assert (layer["start"], layer["end"], layer["source_in"]) == (2, 5, 90)
    assert (layer["fit"], layer["audio"], layer["scale"]) == ("pip", "replace", 0.4)
    # נשלח לריצה כמו כל שכבה
    assert page.evaluate("() => _collectRunOptions().layers[0].type") == "video"
    # ידית גרירה רק כשהוא חלון; במסך מלא אין מה לגרור
    targets = "() => _veDragTargets().filter(t => t.kind === 'layer').length"
    assert page.evaluate(targets) == 1
    page.select_option(f"{row} select[data-field=fit]", "fill")
    assert page.evaluate(targets) == 0


def test_the_live_player_builds_a_synced_video_for_the_broll(editor_page, tmp_path):
    page = editor_page
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    page.evaluate("""(path) => _applyVideoEditorFields({layers: [{type: 'video', path, start: 1, end: 3, source_in: 2, fit: 'fill', audio: 'mix'}]})""",
                  str(clip))
    box = page.evaluate("""() => {
        const box = document.getElementById('veLiveOverlays');
        const opts = _collectRunOptions();
        opts._layers = opts.layers;
        if (!_veLive) _veLive = {};  // בלי מצב נגן חי פעיל - רק בונים את השכבות
        _veLiveBuildOverlays(opts, {w: 1920, h: 1080}, {w: 640, h: 360}, 1 / 3);
        const video = box.querySelector('video.ve-live-layer');
        return video && {src: video.getAttribute('src'), full: video.classList.contains('ve-live-broll-full'), muted: video.muted, fit: video.style.objectFit};
    }""")
    assert box and "source_stream" in box["src"] and "clip.mp4" in box["src"]
    assert box["full"] and box["muted"] and box["fit"] == "cover"


def test_a_missing_broll_clip_is_reported_next_to_the_layers_field(editor_page, tmp_path):
    page = editor_page
    missing = str(tmp_path / "gone.mp4")
    result = page.evaluate("""async (path) => {
        const response = await fetch('/api/video_editor/validate', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({folder: '', static_only: true, layers: [{type: 'video', path}]})});
        return response.json();
    }""", missing)
    errors = result.get("field_errors") or result.get("errors") or {}
    assert "layers" in errors and "gone.mp4" in errors["layers"]
