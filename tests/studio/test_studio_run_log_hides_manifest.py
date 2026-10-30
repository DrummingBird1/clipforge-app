# tests/studio/test_studio_run_log_hides_manifest.py
#
# 24.10.2026, סיור השימושיות בסטודיו (ממצא 8): אחרי כל ריצה של עורך-העל, השורה האחרונה בלוג שבמסך הייתה נתיב טכני -
# "RUN_MANIFEST: C:\...\run_manifests\....json". הממשק מקבל את הנתיב ב-RESULT (manifest_path), אז השורה נשארת רק בקובץ.
import logging

import utils.shared.worker as worker_module


def test_the_manifest_line_stays_out_of_the_on_screen_log(caplog):
    w = worker_module.TaskWorker()
    with caplog.at_level(logging.INFO):
        w._handle_output_line("RUN_MANIFEST: C:\\ws\\.cache\\run_manifests\\x.json", "video_editor.py")
    assert w.log_queue.empty()                                                  # קודם: בלוג שבמסך
    assert any("RUN_MANIFEST" in record.getMessage() for record in caplog.records)   # בקובץ הלוג - כמו קודם
    w._handle_output_line("✅ נוצר: clip_1_edited.mp4", "video_editor.py")
    assert "clip_1_edited" in w.log_queue.get_nowait()[0]                       # שורות רגילות - כמו קודם
