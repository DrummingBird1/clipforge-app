# dataviz/web/batch.py
#
# 20.10.2026: תמונות של כל הפרקים בתיקייה בבת אחת, עם דף דוח. מקור: תיקיית הטיוטה (workspace/dataviz/staging), תיקייה
# אחרת עם תתי-תיקיות של פרקים, או הפרקים של האפליקציה (אפשר לפי תיקייה בתגיות). לכל פרק כמה פריימים בגודל קטן (אותו מנוע
# של התצוגה החיה) - בלי רינדור וידאו. תיקיות המקור רק נקראות; הפלט בתיקייה חדשה workspace/dataviz/batch/<זמן>/ (PNG,
# report.json ו-index.html). רינדור מלא - רק בבחירה מפורשת, דרך התור הקיים (routes/dataviz.py), ורק לפרקים של האפליקציה.
import html
import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Mapping, Optional

POSITIONS = (0.15, 0.6, 1.0)   # התחלה, אמצע, הסוף (תיבת הסיום)
SCALE = 0.35
MAX_EPISODES = 60

_state_lock = threading.Lock()
_state: Dict[str, Any] = {"running": False}


def batch_root(workspace_dir: str) -> str:
    from utils.shared.workspace_dir import DATAVIZ, tool_output_dir
    return tool_output_dir(DATAVIZ, "batch", base=workspace_dir)


def find_episodes(data_dir: str, workspace_dir: str, source: str, path: str = "", folder: str = "") -> List[Dict[str, str]]:
    """[{name, path, app}] - source: staging / folder (נתיב) / app (folder = תיקייה בתגיות, ריק = כולם)."""
    from dataviz.web import episodes as de
    if source == "app":
        tags = de.load_tags(data_dir)
        root = de.episodes_root(data_dir)
        names = sorted(n for n in os.listdir(root) if os.path.isfile(os.path.join(root, n, "config.yaml"))) if os.path.isdir(root) else []
        if folder:
            names = [n for n in names if (tags.get(n) or {}).get("folder") == folder]
        return [{"name": n, "path": os.path.join(root, n), "app": "1"} for n in names][:MAX_EPISODES]
    if source == "staging":
        base = de.staging_folder(workspace_dir)
    elif source == "folder":
        base = os.path.abspath(str(path or "").strip().strip('"'))
    else:
        raise de.EpisodeError("מקור לא מוכר.")
    if not base or not os.path.isdir(base):
        raise de.EpisodeError("התיקייה לא נמצאה.", status=404)
    if os.path.isfile(os.path.join(base, "config.yaml")):
        found = [base]
    else:
        found = [os.path.join(base, n) for n in sorted(os.listdir(base)) if os.path.isfile(os.path.join(base, n, "config.yaml"))]
    return [{"name": os.path.basename(p), "path": p, "app": ""} for p in found][:MAX_EPISODES]


def _new_out_dir(workspace_dir: str) -> str:
    root = batch_root(workspace_dir)
    os.makedirs(root, exist_ok=True)
    base = time.strftime("%Y%m%d_%H%M%S")
    for i in range(1, 1000):
        path = os.path.join(root, base + (f"_{i}" if i > 1 else ""))
        try:
            os.mkdir(path)   # בלעדי - שתי ריצות באותה שנייה לא חולקות תיקייה
            return path
        except FileExistsError:
            continue
    raise RuntimeError("no free batch folder name")


def run(data_dir: str, workspace_dir: str, episodes: List[Dict[str, str]], out_dir: str,
        progress: Optional[Callable[[int, int], None]] = None) -> Dict[str, Any]:
    """מצייר את הפריימים לכל פרק לתוך out_dir ומחזיר את הדוח (גם נכתב ל-report.json ול-index.html). כשל בפרק = שורה עם
    השגיאה, ממשיכים לבא."""
    import shutil

    from dataviz.web import episodes as de
    from dataviz.web.preview import preview_frame
    cache = os.path.join(out_dir, ".cache")
    rows = []
    for index, item in enumerate(episodes):
        row: Dict[str, Any] = {"name": item["name"], "path": item["path"], "app": bool(item.get("app")), "images": [], "error": ""}
        started = time.monotonic()
        try:
            overrides = de.load_overrides_for_path(item["path"]) if item.get("app") else {}
            row["title"] = _title(item["path"])
            for k, position in enumerate(POSITIONS):
                frame = preview_frame(item["path"], overrides, cache, position, scale=SCALE)
                image = f"{_safe(item['name'])}_{k + 1}.png"
                shutil.copyfile(frame["path"], os.path.join(out_dir, image))
                row["images"].append({"file": image, "date": frame.get("date", ""), "kind": frame.get("kind", "")})
                row["frames"] = frame.get("frames", 0)
        except Exception as e:   # פרק שבור לא עוצר את השאר - השגיאה בדוח
            row["error"] = str(e)[:300]
        row["seconds"] = round(time.monotonic() - started, 1)
        rows.append(row)
        if progress:
            progress(index + 1, len(episodes))
    shutil.rmtree(cache, ignore_errors=True)   # safe: מטמון הפריימים שיצרנו כאן בתוך תיקיית הפלט החדשה
    report = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "folder": out_dir, "episodes": rows,
              "ok": sum(1 for r in rows if not r["error"]), "failed": sum(1 for r in rows if r["error"])}
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(report_html(report))
    return report


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:60] or "episode"


def _title(path: str) -> str:
    import yaml
    try:
        with open(os.path.join(path, "config.yaml"), encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return str(raw.get("title") or "") if isinstance(raw, Mapping) else ""
    except (OSError, yaml.YAMLError):
        return ""


def report_html(report: Mapping[str, Any]) -> str:
    """דף דוח עצמאי (נפתח גם ישירות מהתיקייה): כרטיס לכל פרק עם הפריימים, או השגיאה."""
    cards = []
    for row in report["episodes"]:
        body = (f'<p class="err">❌ {html.escape(row["error"])}</p>' if row["error"] else
                "".join(f'<figure><img src="{html.escape(i["file"])}" alt="{html.escape(row["name"])} {k + 1}" loading="lazy">'
                        f'<figcaption>{html.escape(i.get("date") or i.get("kind") or "")}</figcaption></figure>'
                        for k, i in enumerate(row["images"])))
        cards.append(f'<section class="{"bad" if row["error"] else "good"}"><h2>{html.escape(row.get("title") or row["name"])}'
                     f' <small>{html.escape(row["name"])} · {row["seconds"]}s</small></h2><div class="frames">{body}</div></section>')
    return f"""<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>דוח תמונות - {html.escape(report["created"])}</title>
<style>
body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 16px; background: #fbfaf6; color: #1f2933; }}
section {{ border: 1px solid #e7e4da; border-radius: 8px; padding: 8px 12px; margin-block: 12px; background: white; }}
section.bad {{ border-color: #d1495b; }}
.frames {{ display: flex; flex-wrap: wrap; gap: 8px; }}
figure {{ margin: 0; }} img {{ max-width: 320px; width: 100%; border: 1px solid #e7e4da; }}
figcaption, small {{ color: #6b7280; font-size: 0.85em; }} .err {{ color: #d1495b; }}
</style></head><body>
<h1>דוח תמונות ({report["ok"]} תקינים, {report["failed"]} נכשלו)</h1>
<p>{html.escape(report["created"])} · {html.escape(report["folder"])}</p>
{"".join(cards)}
</body></html>
"""


# ---------- ריצה ברקע (ריצה אחת בכל פעם) ----------
def start(data_dir: str, workspace_dir: str, source: str, path: str = "", folder: str = "") -> Dict[str, Any]:
    from dataviz.web import episodes as de
    episodes = find_episodes(data_dir, workspace_dir, source, path, folder)
    if not episodes:
        raise de.EpisodeError("אין פרקים (תיקיות עם config.yaml) במקור הזה.")
    with _state_lock:
        if _state.get("running"):
            raise de.EpisodeError("כבר רץ דוח תמונות - המתן לסיומו.", status=409)
        out_dir = _new_out_dir(workspace_dir)
        _state.clear()
        _state.update({"running": True, "done": 0, "total": len(episodes), "id": os.path.basename(out_dir), "error": "",
                       "source": source, "names": [e["name"] for e in episodes if e.get("app")]})

    def progress(done: int, total: int) -> None:
        with _state_lock:
            _state["done"] = done

    def work() -> None:
        try:
            report = run(data_dir, workspace_dir, episodes, out_dir, progress)
            result = {"ok": report["ok"], "failed": report["failed"]}
        except Exception as e:
            result = {"error": str(e)[:300]}
        with _state_lock:
            _state.update(result)
            _state["running"] = False

    threading.Thread(target=work, name="dataviz-batch", daemon=True).start()
    return status()


def status() -> Dict[str, Any]:
    with _state_lock:
        return dict(_state)


def report_file(workspace_dir: str, batch_id: str, name: str) -> Optional[str]:
    """נתיב לקובץ בדוח (index.html, report.json או PNG) - רק בתוך תיקיית הדוח, בלי נתיבים יחסיים."""
    if not batch_id or not name or any(sep in batch_id + name for sep in ("/", "\\", "..")):
        return None
    if not name.endswith((".png", ".html", ".json")):
        return None
    path = os.path.join(batch_root(workspace_dir), batch_id, name)
    return path if os.path.isfile(path) else None
