# tests/studio/test_media_pool.py
#
# גל 24: מאגר העבודה המוגבל לקריאות ffmpeg/ffprobe מה-routes (utils/video/media_pool.py) -
# תקרה לכל נתיב, נתיבים לא חוסמים זה את זה, single_flight מריץ פעם אחת לכל פלט.
import os
import subprocess
import sys
import threading
import time

import pytest

from tests.scoped_subprocess import fake_subprocess_run, flag_named_files_in_project_root
from utils.video import media_pool


@pytest.fixture(autouse=True, scope="module")
def _no_flag_named_files_left_in_the_project_root():
    yield
    assert flag_named_files_in_project_root() == []


def _hammer(lane, count, hold=0.05):
    active = {"now": 0, "peak": 0}
    lock = threading.Lock()

    def work():
        with media_pool.slot(lane):
            with lock:
                active["now"] += 1
                active["peak"] = max(active["peak"], active["now"])
            time.sleep(hold)
            with lock:
                active["now"] -= 1

    threads = [threading.Thread(target=work) for _ in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    return active["peak"]


def test_each_lane_never_runs_more_than_its_limit():
    for lane, limit in media_pool.LANE_LIMITS.items():
        assert _hammer(lane, limit * 4) == limit


def test_a_flood_of_thumbnails_does_not_block_the_interactive_lane():
    release = threading.Event()

    def thumb():
        with media_pool.slot("thumbs"):
            release.wait(5)

    blockers = [threading.Thread(target=thumb) for _ in range(media_pool.LANE_LIMITS["thumbs"] + 3)]
    for t in blockers:
        t.start()
    try:
        started = time.monotonic()
        with media_pool.slot("interactive"):
            waited = time.monotonic() - started
        assert waited < 1.0
    finally:
        release.set()
        for t in blockers:
            t.join(5)


def test_run_passes_through_to_subprocess_inside_a_slot(monkeypatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append((cmd, kwargs, media_pool.stats()["analysis"]["running"]))
        return "done"

    fake_subprocess_run(monkeypatch, media_pool, fake_run)
    assert media_pool.run(["ffmpeg", "-version"], lane="analysis", timeout=5) == "done"
    assert seen == [(["ffmpeg", "-version"], {"timeout": 5}, 1)]
    assert media_pool.stats()["analysis"]["running"] == 0


def test_the_slot_is_released_when_the_command_fails(monkeypatch):
    def boom(cmd, **kwargs):
        raise OSError("no ffmpeg")

    fake_subprocess_run(monkeypatch, media_pool, boom)
    for _ in range(media_pool.LANE_LIMITS["thumbs"] + 2):
        try:
            media_pool.run(["ffmpeg"], lane="thumbs")
        except OSError:
            pass
    assert media_pool.stats()["thumbs"]["running"] == 0
    assert _hammer("thumbs", 2) >= 1  # לא ננעל


def test_single_flight_runs_the_work_once_per_key(tmp_path):
    out = tmp_path / "thumb.jpg"
    calls = []

    def request():
        with media_pool.single_flight(str(out)):
            if not out.exists():
                calls.append(1)
                time.sleep(0.05)
                out.write_bytes(b"jpg")

    threads = [threading.Thread(target=request) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert calls == [1]
    assert media_pool._flights == {}  # אין דליפה אחרי שכולם סיימו


def test_single_flight_does_not_serialize_different_keys():
    barrier = threading.Barrier(2, timeout=2)
    results = []

    def request(key):
        with media_pool.single_flight(key):
            try:
                barrier.wait()  # שני המפתחות חייבים להיות בפנים באותו זמן
                results.append(key)
            except threading.BrokenBarrierError:
                results.append("blocked")

    threads = [threading.Thread(target=request, args=(k,)) for k in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert sorted(results) == ["a", "b"]


# --- ה-routes עצמם: תמונות ממוזערות מתור של הרבה קבצים ---

def _fake_ffmpeg(monkeypatch, hold=0.03):
    """subprocess.run מזויף - רק בתוך media_pool - שכותב את קובץ הפלט (הארגומנט האחרון)
    ומודד כמה רצים במקביל."""
    lock = threading.Lock()
    state = {"now": 0, "peak": 0, "calls": []}

    def fake_run(cmd, **kwargs):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
            state["calls"].append(cmd[-1])
        time.sleep(hold)
        with open(cmd[-1], "wb") as f:
            f.write(b"\xff\xd8jpg")
        with lock:
            state["now"] -= 1
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    fake_subprocess_run(monkeypatch, media_pool, fake_run)
    return state


def _thumbnail_route(monkeypatch, tmp_path):
    from entrypoints import web_app
    from entrypoints.web.routes import editor as editor_routes
    monkeypatch.setattr(web_app, "PREVIEWS_DIR", str(tmp_path / "previews"))
    monkeypatch.setattr(web_app, "get_ffmpeg_exe", lambda: "ffmpeg")
    return editor_routes.api_video_editor_file_thumbnail


def _thumbnails_written(tmp_path):
    """הפלטים היחידים שה-fake אמור היה לקבל: src_*.jpg בתיקיית ה-previews של הטסט."""
    previews = tmp_path / "previews"
    names = sorted(os.listdir(previews))
    assert all(name.startswith("src_") and name.endswith(".jpg") for name in names), names
    return [os.path.join(str(previews), name) for name in names]


def _in_threads(fn, args_list):
    results = [None] * len(args_list)

    def call(i, args):
        results[i] = fn(*args)

    threads = [threading.Thread(target=call, args=(i, a)) for i, a in enumerate(args_list)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    return results


def test_a_folder_of_thumbnails_never_runs_more_ffmpeg_than_the_lane_allows(monkeypatch, tmp_path):
    route = _thumbnail_route(monkeypatch, tmp_path)
    state = _fake_ffmpeg(monkeypatch)
    videos = []
    for i in range(24):
        video = tmp_path / f"clip_{i}.mp4"
        video.write_bytes(b"x" * (i + 1))
        videos.append((str(video),))
    responses = _in_threads(route, videos)
    assert all(getattr(r, "status_code", 200) == 200 for r in responses)
    assert len(state["calls"]) == 24
    assert sorted(state["calls"]) == _thumbnails_written(tmp_path)
    assert state["peak"] <= media_pool.LANE_LIMITS["thumbs"]


def test_the_same_thumbnail_requested_together_runs_ffmpeg_once(monkeypatch, tmp_path):
    route = _thumbnail_route(monkeypatch, tmp_path)
    state = _fake_ffmpeg(monkeypatch, hold=0.1)
    video = tmp_path / "same.mp4"
    video.write_bytes(b"video")
    responses = _in_threads(route, [(str(video),)] * 6)
    assert all(getattr(r, "status_code", 200) == 200 for r in responses)
    assert len(state["calls"]) == 1
    assert state["calls"] == _thumbnails_written(tmp_path)


def test_the_fake_ffmpeg_does_not_catch_other_threads_commands(monkeypatch, tmp_path):
    """נמצא ב-2026-10-02 (-n 6): ה-fake הוחלף על subprocess.run הגלובלי, ודוגם החומרה
    (nvidia-smi ... --format=csv,noheader,nounits) קיבל אותו מ-thread אחר - נוצר קובץ בשם
    הדגל בשורש הפרויקט, ו-24 הקריאות הצפויות נהיו 25."""
    monkeypatch.chdir(tmp_path)  # אם זה דולף שוב, ה"פלט" נכתב ל-tmp_path ולא לשורש
    route = _thumbnail_route(monkeypatch, tmp_path)
    state = _fake_ffmpeg(monkeypatch, hold=0.2)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    flag = "--format=csv,noheader,nounits"
    sampled = {}

    def hardware_sampler():
        sampled["result"] = subprocess.run(
            [sys.executable, "-c", "import sys; print(sys.argv[-1])", flag],
            capture_output=True, text=True, timeout=30,
        )

    sampler = threading.Thread(target=hardware_sampler)
    thumbnail = threading.Thread(target=route, args=(str(video),))
    thumbnail.start()
    deadline = time.monotonic() + 10
    while not state["calls"] and time.monotonic() < deadline:  # הדוגם מתחיל כש-ה-fake כבר בתוך run() (hold=0.2)
        time.sleep(0.005)
    sampler.start()
    for t in (thumbnail, sampler):
        t.join(30)

    assert sampled["result"].returncode == 0
    assert sampled["result"].stdout.strip() == flag  # רץ באמת, לא דרך ה-fake
    assert state["calls"] == _thumbnails_written(tmp_path)
    assert not (tmp_path / flag).exists()


def test_analysis_routes_answer_cleanly_without_ffmpeg(monkeypatch, tmp_path):
    """נמצא ב-CI (בלי ffmpeg): זיהוי סצנות/עוצמה החזירו 500 עם traceback - עכשיו 503 מסודר."""
    from entrypoints import web_app
    from entrypoints.web.routes import pro
    from utils.shared import ffmpeg_locator
    monkeypatch.setattr(web_app, "PREVIEWS_DIR", str(tmp_path / "previews"))
    monkeypatch.setattr(ffmpeg_locator, "get_ffmpeg_exe", lambda: str(tmp_path / "no-ffmpeg.exe"))
    (tmp_path / "clip.mp4").write_bytes(b"video")
    for route in (pro.api_video_editor_scene_cuts, pro.api_video_editor_loudness):
        response = route(folder=str(tmp_path), file="clip.mp4")
        assert response.status_code == 503
