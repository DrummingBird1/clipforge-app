# utils/shared/backup_sync.py
import os
import shutil


def mirror_folder(source_dir, dest_dir):
    """
    מעתיק לתיקיית היעד רק קבצים חדשים/שהשתנו (השוואה לפי גודל+זמן שינוי),
    כדי לא להעתיק מחדש כל פעם את כל תיקיית ה-exports. מחזיר (copied_count, error).
    """
    if not source_dir or not os.path.exists(source_dir):
        return 0, f"תיקיית המקור לא קיימת: {source_dir}"
    if not dest_dir:
        return 0, "לא הוגדרה תיקיית גיבוי."

    try:
        os.makedirs(dest_dir, exist_ok=True)
    except Exception as e:
        return 0, f"לא ניתן ליצור את תיקיית היעד: {e}"

    copied = 0
    try:
        for root, _dirs, files in os.walk(source_dir):
            rel_root = os.path.relpath(root, source_dir)
            target_root = os.path.join(dest_dir, rel_root) if rel_root != "." else dest_dir
            os.makedirs(target_root, exist_ok=True)

            for filename in files:
                src_path = os.path.join(root, filename)
                dst_path = os.path.join(target_root, filename)

                needs_copy = True
                if os.path.exists(dst_path):
                    src_stat = os.stat(src_path)
                    dst_stat = os.stat(dst_path)
                    if src_stat.st_size == dst_stat.st_size and src_stat.st_mtime <= dst_stat.st_mtime:
                        needs_copy = False

                if needs_copy:
                    shutil.copy2(src_path, dst_path)
                    copied += 1

        return copied, None
    except Exception as e:
        return copied, str(e)
