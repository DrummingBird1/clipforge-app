# tests/web/test_web_app_recording_browser.py
#
# 16.11.2026 (2.0): מסך "🔴 הקלטה" בדפדפן. הנתונים מזויפים בדף (fetch עטוף - page.route לא תופס בקשות שה-service worker
# מטפל בהן), וכל POST נרשם במקום לרוץ: שום הקלטה אמיתית, שום התקן.
import pytest

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning")]

FAKE = """() => {
  window.__posts = [];
  let replay = false;
  const settings = {engine: 'ffmpeg', source: 'device', screen_index: 0, fps: 60, console: 'ps5', device_video: 'HD60 X',
                    device_audio: 'HD60 X Audio', game_audio: true, mic: '', facecam: '', codec: 'hevc', quality: 22,
                    replay_seconds: 60, replay_max_gb: 8, hotkey_save_replay: 'ctrl+alt+s', hotkey_toggle_record: 'ctrl+alt+r'};
  const consoles = [{id: 'ps5', label: 'PlayStation 5', note: 'כבה HDCP'}, {id: 'switch', label: 'Nintendo Switch', note: 'בעגינה'}];
  const devices = {video: [{name: 'HD60 X', alternative: '@a'}, {name: 'Webcam', alternative: '@c'}],
                   audio: [{name: 'HD60 X Audio', alternative: '@b'}, {name: 'Mic', alternative: '@d'}]};
  const status = () => ({engine: 'ffmpeg', recording: false, replay, replay_buffered_seconds: replay ? 24 : 0, error: null,
                         last_saved: null, hotkeys: replay});
  const realFetch = window.fetch;
  const json = (body, code = 200) => Promise.resolve(new Response(JSON.stringify(body), {status: code, headers: {'Content-Type': 'application/json'}}));
  window.fetch = (url, options = {}) => {
    const u = String(url);
    if ((options.method || 'GET') === 'POST' && u.startsWith('/api/recording/')) {
      const body = JSON.parse(options.body || '{}');
      window.__posts.push([u, body]);
      if (u.endsWith('/replay/start')) replay = true;
      if (u.endsWith('/settings')) return json({settings: Object.assign(settings, body)});
      return json(status());
    }
    if (u === '/api/recording/settings') return json({settings, loopback: true, consoles});
    if (u === '/api/recording/devices') return json(devices);
    if (u === '/api/recording/status') return json(status());
    return realFetch(url, options);
  };
}"""


def _open(page):
    page.evaluate("() => closeVeEditor()")
    page.evaluate(FAKE)
    page.evaluate("() => switchTab('recording')")
    page.wait_for_function("() => document.querySelectorAll('#recDeviceVideo option').length === 3")


def test_a_console_capture_card_setup_is_shown_and_replay_runs(editor_page):
    page = editor_page
    _open(page)
    assert page.is_visible("#recDeviceFields") and page.is_hidden("#recScreenFields")
    assert page.input_value("#recConsole") == "ps5" and page.inner_text("#recConsoleNote") == "כבה HDCP"
    assert page.input_value("#recDeviceVideo") == "HD60 X" and page.input_value("#recDeviceAudio") == "HD60 X Audio"
    assert page.is_disabled("#recReplaySave")
    page.click("#recReplayStart")
    page.wait_for_function("() => !document.getElementById('recReplaySave').disabled")
    assert "24" in page.inner_text("#recStatus")
    page.click("#recReplaySave")
    page.wait_for_function("() => window.__posts.length === 2")
    assert [p[0] for p in page.evaluate("() => window.__posts")] == ["/api/recording/replay/start", "/api/recording/replay/save"]


def test_settings_are_saved_from_the_form(editor_page):
    page = editor_page
    _open(page)
    page.select_option("#recSource", "screen")
    assert page.is_visible("#recScreenFields") and page.is_hidden("#recDeviceFields")
    page.fill("#recFps", "30")
    page.evaluate("() => saveRecSettings()")
    page.wait_for_function("() => window.__posts.some((p) => p[0] === '/api/recording/settings')")
    sent = next(p[1] for p in page.evaluate("() => window.__posts") if p[0] == "/api/recording/settings")
    assert sent["source"] == "screen" and sent["fps"] == 30 and sent["console"] == "ps5"


def test_obs_engine_shows_the_scenes_section(editor_page):
    page = editor_page
    _open(page)
    page.select_option("#recEngine", "obs")
    assert page.is_visible("#recObsSection") and page.is_hidden("#recFfmpegFields")
