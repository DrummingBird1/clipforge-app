# tests/studio/test_video_editor_e2e.py
#
# טסט end-to-end אמיתי: מריץ my_scripts/video/video_editor.py כתת-תהליך אמיתי
# (בדיוק כמו שהמשתמש היה מריץ אותו) על קובץ וידאו זעיר-אך-אמיתי (נוצר עם ffmpeg
# lavfi testsrc - בלי לדרוש נכס בינארי שמור בריפו), ומוודא שהפלט בפועל תקין
# (ffprobe מאשר רזולוציה אנכית) - לא רק שהקוד מתקמפל/שקוד עזר בודד מחזיר ערך נכון,
# אלא שכל ה-pipeline האמיתי (ffmpeg -filter_complex וכו') עובד מקצה לקצה.
# מדולג אוטומטית אם ffmpeg לא זמין בסביבה (למשל ב-CI, שם ffmpeg/bin/ מוחרג
# מה-git כי הוא נכס בינארי גדול, ראו utils/shared/ffmpeg_locator.py).
import os
from tests import PROJECT_ROOT
import shutil
import subprocess
import sys


import pytest

from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.video.video_editor import resolve_sig_path

from tests.conftest import remove_video_editor_output

BASE_DIR = PROJECT_ROOT
from utils.shared.workspace_dir import WORKSPACE_DIR  # הזמני של הריצה (tests/conftest.py) - לא workspace/ של המשתמש
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "video_editor.py")
HORIZONTAL_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "studio", "horizontal")
VERTICAL_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "studio", "vertical")
OUTPUT_DIR = HORIZONTAL_OUTPUT_DIR  # ברירת מחדל - רוב הטסטים כאן לא מעבירים --vertical


def _is_runnable(exe_path):
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


pytestmark = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()) or not _is_runnable(get_ffprobe_exe()),
    reason="ffmpeg/ffprobe לא זמינים בסביבה הזו - טסט ה-E2E מדולג (ראו utils/shared/ffmpeg_locator.py)",
)


def _make_synthetic_video(path, duration=1, width=320, height=240):
    """יוצר קובץ mp4 זעיר-אך-אמיתי דרך ffmpeg lavfi testsrc - בלי צורך בקובץ מדיה שמור בריפו."""
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=10",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _probe_dimensions(path):
    cmd = [
        get_ffprobe_exe(), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    return result.stdout.strip()


def test_video_editor_e2e_produces_a_real_vertical_h264_output(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "e2e_pytest_probe_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(VERTICAL_OUTPUT_DIR, "e2e_pytest_probe_clip_edited_vertical.mp4")
    remove_video_editor_output(output_path)  # שאריות מריצה קודמת שנכשלה ולא ניקתה אחריה

    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--vertical", "--codec", "h264"],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert "RESULT:" in result.stdout
        assert '"files_created": 1' in result.stdout
        assert os.path.exists(output_path), f"קובץ הפלט לא נוצר בפועל: {output_path}\n{result.stdout}"
        assert _probe_dimensions(output_path) == "1080x1920"
    finally:
        remove_video_editor_output(output_path)


def test_video_editor_e2e_skips_rerender_of_identical_output_then_force_overrides(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "skip_test_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(OUTPUT_DIR, "skip_test_clip_edited_horizontal.mp4")
    sig_path = resolve_sig_path(output_path)
    for path in (output_path, sig_path):
        if os.path.exists(path):
            os.remove(path)  # שאריות מריצה קודמת שנכשלה ולא ניקתה אחריה

    try:
        base_cmd = [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--codec", "h264"]

        first = subprocess.run(base_cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS)
        assert first.returncode == 0, first.stdout + first.stderr
        assert '"files_created": 1' in first.stdout
        assert os.path.exists(output_path)
        assert os.path.exists(sig_path)
        first_mtime = os.path.getmtime(output_path)

        # ריצה שנייה, אותם פרמטרים בדיוק, בלי --force - אמורה לדלג לגמרי (לא
        # לגעת בקובץ הפלט הקיים).
        second = subprocess.run(base_cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS)
        assert second.returncode == 0, second.stdout + second.stderr
        assert '"skipped": 1' in second.stdout
        assert '"files_created": 0' in second.stdout
        assert os.path.getmtime(output_path) == first_mtime, "הריצה השנייה נגעה בקובץ הפלט למרות שהייתה אמורה לדלג"

        # --force דורס את הדילוג ומרנדר מחדש בפועל.
        third = subprocess.run(base_cmd + ["--force"], cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS)
        assert third.returncode == 0, third.stdout + third.stderr
        assert '"files_created": 1' in third.stdout
        assert '"skipped": 0' in third.stdout
    finally:
        for path in (output_path, sig_path):
            if os.path.exists(path):
                os.remove(path)


def test_video_editor_e2e_skip_ignores_changed_settings_between_runs(tmp_path):
    # item: smart re-encode skip נגד רינדור-מחדש שגוי - שינוי הגדרות הריצה
    # (כאן: codec) בין ריצה לריצה על אותו קובץ מקור (בלי שינוי בתוכן שלו) לא
    # אמור לשבור את הדילוג יותר - רק תוכן קובץ המקור עצמו קובע (--force
    # תמיד עוקף, נבדק בטסט הקודם).
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "skip_settings_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(OUTPUT_DIR, "skip_settings_clip_edited_horizontal.mp4")
    sig_path = resolve_sig_path(output_path)
    for path in (output_path, sig_path):
        if os.path.exists(path):
            os.remove(path)

    try:
        first = subprocess.run(
            [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--codec", "h264"],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
        )
        assert first.returncode == 0, first.stdout + first.stderr
        assert '"files_created": 1' in first.stdout
        assert os.path.exists(output_path)
        first_mtime = os.path.getmtime(output_path)

        # ריצה שנייה עם --denoise/--sharpen חדשים (הגדרות שונות לגמרי מהריצה
        # הראשונה, בלי --force) - עדיין אמורה לדלג, כי קובץ המקור עצמו לא השתנה.
        second = subprocess.run(
            [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--codec", "h264", "--denoise", "--sharpen"],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
        )
        assert second.returncode == 0, second.stdout + second.stderr
        assert '"skipped": 1' in second.stdout
        assert '"files_created": 0' in second.stdout
        assert os.path.getmtime(output_path) == first_mtime, "שינוי הגדרות בלבד לא אמור לגרום לרינדור-מחדש"
    finally:
        for path in (output_path, sig_path):
            if os.path.exists(path):
                os.remove(path)


def test_video_editor_e2e_skip_still_breaks_when_source_content_actually_changes(tmp_path):
    # item: smart re-encode skip - הגנה שנשארת בכוונה: אם קובץ המקור *עצמו*
    # הוחלף בפועל (אותו שם, mtime/גודל שונים - למשל הוקלט מחדש), הדילוג לא
    # אמור להגיש תוצר מיושן בשקט, גם בלי --force.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "changed_source_clip.mp4"
    _make_synthetic_video(str(src_path), duration=1)

    output_path = os.path.join(OUTPUT_DIR, "changed_source_clip_edited_horizontal.mp4")
    sig_path = resolve_sig_path(output_path)
    for path in (output_path, sig_path):
        if os.path.exists(path):
            os.remove(path)

    try:
        base_cmd = [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--codec", "h264"]

        first = subprocess.run(base_cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS)
        assert first.returncode == 0, first.stdout + first.stderr
        assert '"files_created": 1' in first.stdout

        # "מקליטים מחדש" את אותו שם קובץ עם תוכן שונה (משך שונה -> גודל/mtime שונים).
        _make_synthetic_video(str(src_path), duration=2)

        second = subprocess.run(base_cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS)
        assert second.returncode == 0, second.stdout + second.stderr
        assert '"files_created": 1' in second.stdout, "תוכן קובץ המקור השתנה - היה אמור לרנדר מחדש, לא לדלג"
        assert '"skipped": 0' in second.stdout
    finally:
        for path in (output_path, sig_path):
            if os.path.exists(path):
                os.remove(path)


def test_video_editor_e2e_logs_the_specific_reason_it_did_not_skip(tmp_path):
    # item: "why didn't it skip" diagnostics - כל אחת מהסיבות שגורמות לרינדור-מלא
    # במקום דילוג אמורה להדפיס [INFO] עם הסיבה המדויקת, כדי שחקירת מקרה עתידי
    # (כמו זה שדרש חפירה ידנית ארוכה בקבצים על הדיסק) תהיה מיידית מתוך לוג הריצה.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "why_no_skip_clip.mp4"
    _make_synthetic_video(str(src_path), duration=1)

    output_path = os.path.join(OUTPUT_DIR, "why_no_skip_clip_edited_horizontal.mp4")
    sig_path = resolve_sig_path(output_path)
    base_cmd = [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--codec", "h264"]
    for path in (output_path, sig_path):
        if os.path.exists(path):
            os.remove(path)

    try:
        # 1) אין פלט קודם בכלל.
        first = subprocess.run(base_cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS)
        assert first.returncode == 0, first.stdout + first.stderr
        assert "אין פלט קודם" in first.stdout

        # 2) יש פלט, אבל ה-.sig.json נמחק/חסר.
        os.remove(sig_path)
        second = subprocess.run(base_cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS)
        assert second.returncode == 0, second.stdout + second.stderr
        assert "בלי קובץ .sig.json" in second.stdout

        # 3) יש פלט+sig תקינים, אבל תוכן קובץ המקור עצמו השתנה.
        _make_synthetic_video(str(src_path), duration=2)
        third = subprocess.run(base_cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS)
        assert third.returncode == 0, third.stdout + third.stderr
        assert "קובץ המקור השתנה" in third.stdout
    finally:
        for path in (output_path, sig_path):
            if os.path.exists(path):
                os.remove(path)


def test_video_editor_e2e_target_size_mb_h264_two_pass_lands_near_target(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "twopass_test_clip.mp4"
    _make_synthetic_video(str(src_path), duration=5, width=640, height=360)

    output_path = os.path.join(OUTPUT_DIR, "twopass_test_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    target_mb = 0.5

    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--codec", "h264", "--target-size-mb", str(target_mb)],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert '"files_created": 1' in result.stdout
        assert "pass 1/2" in result.stdout and "pass 2/2" in result.stdout
        assert os.path.exists(output_path), f"קובץ הפלט לא נוצר בפועל: {output_path}\n{result.stdout}"

        actual_mb = os.path.getsize(output_path) / (1024 * 1024)
        # two-pass VBR הוא הערכה, לא ערבות מתמטית מדויקת - מרווח סבלנות רחב (50%)
        # מספיק כדי לתפוס רגרסיה אמיתית (למשל אם היעד יורד/עולה מהחישוב) בלי
        # להיות שביר מול תנודתיות טבעית של הקידוד עצמו.
        assert actual_mb < target_mb * 1.5, f"הפלט ({actual_mb:.2f}MB) חורג משמעותית מהיעד ({target_mb}MB)"

        # קבצי ה-passlog הזמניים לא אמורים להישאר אחרי סיום הריצה.
        assert not os.path.exists(os.path.join(OUTPUT_DIR, "twopass_test_clip_2pass-0.log"))
    finally:
        remove_video_editor_output(output_path)
        for leftover in ("twopass_test_clip_2pass-0.log", "twopass_test_clip_2pass-0.log.mbtree"):
            leftover_path = os.path.join(OUTPUT_DIR, leftover)
            if os.path.exists(leftover_path):
                os.remove(leftover_path)


def test_video_editor_e2e_preview_only_generates_contact_sheet_without_rendering(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for i in range(3):
        _make_synthetic_video(str(input_dir / f"preview_clip_{i}.mp4"))

    output_path = os.path.join(OUTPUT_DIR, "preview_clip_0_edited_horizontal.mp4")
    preview_path = os.path.join(OUTPUT_DIR, "_preview_contact_sheet.png")
    remove_video_editor_output(output_path)
    if os.path.exists(preview_path):
        os.remove(preview_path)

    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--codec", "h264", "--preview-only"],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=60, creationflags=NO_WINDOW_FLAGS,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert '"videos_found": 3' in result.stdout
        assert os.path.exists(preview_path), f"contact-sheet לא נוצר: {result.stdout}"
        assert not os.path.exists(output_path), "--preview-only לא אמור לרנדר בפועל"
    finally:
        remove_video_editor_output(output_path)
        if os.path.exists(preview_path):
            os.remove(preview_path)


def test_video_editor_e2e_recurses_into_subfolders_and_mirrors_them_in_the_output(tmp_path):
    input_dir = tmp_path / "input"
    (input_dir / "Session1").mkdir(parents=True)
    (input_dir / "Session2" / "Nested").mkdir(parents=True)
    _make_synthetic_video(str(input_dir / "Session1" / "clip.mp4"))
    _make_synthetic_video(str(input_dir / "Session2" / "Nested" / "clip.mp4"))

    output_paths = [
        os.path.join(OUTPUT_DIR, "Session1", "clip_edited_horizontal.mp4"),
        os.path.join(OUTPUT_DIR, "Session2", "Nested", "clip_edited_horizontal.mp4"),
    ]
    for output_path in output_paths:
        remove_video_editor_output(output_path)  # שאריות מריצה קודמת שנכשלה ולא ניקתה אחריה

    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--codec", "h264"],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert "RESULT:" in result.stdout
        assert '"files_created": 2' in result.stdout
        for output_path in output_paths:
            assert os.path.exists(output_path), f"קובץ הפלט לא נוצר בפועל: {output_path}\n{result.stdout}"
    finally:
        for output_path in output_paths:
            remove_video_editor_output(output_path)
        for empty_dir in (os.path.join(OUTPUT_DIR, "Session2", "Nested"), os.path.join(OUTPUT_DIR, "Session2"), os.path.join(OUTPUT_DIR, "Session1")):
            if os.path.isdir(empty_dir) and not os.listdir(empty_dir):
                os.rmdir(empty_dir)
