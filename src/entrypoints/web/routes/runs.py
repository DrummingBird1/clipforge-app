# entrypoints/web/routes/runs.py
#
# הרצת סקריפטים: run/stop/pause, היסטוריה, undo, מנעול הרינדור וה-WebSocket של הלוג.
# גל 11: הועבר כמו שהוא מ-web_app.py - המצב המשותף (נתיבים, helpers, מנעולים) נשאר
# שם ונגיש כ-W.<שם>, כך ש-monkeypatch.setattr(web_app, ...) חל גם על ה-endpoints כאן.

import json
import os
import queue
import time

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from utils.shared import move_undo_log
from utils.shared.health_status import format_duration

from entrypoints import web_app as W

router = APIRouter()


@router.post("/api/run")
@W.limiter.limit("10/minute")
async def api_run(payload: dict, request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)

    script_id = str(payload.get("script", ""))
    folder = str(payload.get("folder", ""))

    # הגנה מפני Path Traversal - זהה בעיקרון ל-cogs/remote_execution.py:
    # מוודאים שהנתיב הסופי נשאר בתוך my_scripts/ אחרי הצירוף.
    script_path = os.path.abspath(os.path.join(W.SCRIPTS_DIR, script_id.replace("/", os.sep)))
    if not script_path.startswith(W.SCRIPTS_DIR + os.sep) or not os.path.isfile(script_path):
        return JSONResponse({"error": "סקריפט לא נמצא."}, status_code=400)
    if not folder or not os.path.isdir(folder):
        return JSONResponse({"error": "תיקייה לא תקינה."}, status_code=400)

    if W.worker.is_running:
        return JSONResponse({"error": "כבר יש ריצה פעילה - המתן לסיומה או עצור אותה."}, status_code=409)
    return W._start_script_run(script_path, folder, payload, request.client.host if request.client else None)


@router.post("/api/stop")
@W.limiter.limit("10/minute")
def api_stop(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    W._current_run["stop_requested"] = True   # מרכז ההתראות: "נעצר", לא "נכשל"
    W.worker.terminate_current()
    W.audit_log.record_action("web", "stop_script", username=request.client.host if request.client else None)
    return {"ok": True}


@router.post("/api/pause")
@W.limiter.limit("10/minute")
def api_pause(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    W.worker.pause_current()
    W.audit_log.record_action("web", "pause_script", username=request.client.host if request.client else None)
    return {"ok": True}


@router.post("/api/resume")
@W.limiter.limit("10/minute")
def api_resume(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    W.worker.resume_current()
    W.audit_log.record_action("web", "resume_script", username=request.client.host if request.client else None)
    return {"ok": True}


@router.post("/api/cancel_shutdown")
def api_cancel_shutdown(request: Request):
    """מבטל כיבוי מתוזמן שהופעל ע"י מצב לילה (ראו _run_completion_side_effects) -
    מקביל ל-"🛑 בטל כיבוי" בדיאלוג של ui/dashboard.py, רק שכאן זה כפתור בדף
    ה-web (ראו ה-JS handler ל-type:"finished" עם shutdown_seconds) ולא חלון
    Tkinter נפרד - אין כאן שום דיאלוג נראה לעין חוץ מהעמוד עצמו."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    W._night_shutdown_waiting = False   # גם כיבוי שעוד מחכה לסוף התור (W._finish_waiting_night_shutdown)
    os.system("shutdown /a")
    return {"ok": True}


@router.get("/api/lock_status")
def api_lock_status():
    """מצב מנעול הרינדור החוצה-תהליכים (utils/shared/render_lock.py) - אם תפוס ע"י
    תהליך אחר (GUI/בוט), זה בדיוק למה "הרץ" כאן ייתקע/ימתין."""
    status = W.get_render_lock_status()
    if status is None:
        return {"locked": False}
    return {
        "locked": True,
        "pid": status["pid"],
        "age": format_duration(status["age_seconds"]) if status["age_seconds"] is not None else None,
        "age_seconds": status["age_seconds"],  # הממשק מעצב בעצמו - "age" בעברית נשאר עברית גם בממשק האנגלי
        "is_stale": status["is_stale"],
        "queue_length": status.get("queue_length", 0),
    }


@router.get("/api/queue_status")
def api_queue_status():
    """כמה משימות ממתינות בתור מאחורי הריצה הנוכחית (מפורק heavy/light) -
    אותו worker.pending_counts_by_lane() בדיוק כמו ui/dashboard.py השולחני.
    רלוונטי בעיקר כשה-GUI השולחני או הבוט דחפו כבר משימות לתור המשותף -
    "הרץ" מכאן עדיין נדחה עם 409 כשיש ריצה פעילה (ראו /api/run), אבל בלי
    זה אין שום דרך לדעת שיש עוד N ממתינות מאחורי מה שכן רץ."""
    counts = W.worker.pending_counts_by_lane()
    return {"pending": counts["heavy"] + counts["light"], "heavy": counts["heavy"], "light": counts["light"]}


def _result_dict(result_json):
    """גל 17: התוצאה המובנית (dict) לצד שורת ה-summary - פיד הפעילות בדף מציג ממנה
    סיכום אנושי ("24 נוצרו · 4:05") במקום key: value גולמי."""
    try:
        value = json.loads(result_json) if isinstance(result_json, str) else result_json
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


@router.get("/api/history")
def api_history():
    rows = W.job_history.get_recent_jobs(limit=20)
    return [
        {
            "script": script_name, "status": status, "started_at": started_at,
            "duration": duration_seconds, "summary": W.job_history.format_result_summary(result_json),
            "result": _result_dict(result_json),
        }
        for script_name, status, started_at, duration_seconds, result_json in rows
    ]


@router.get("/api/history/search")
def api_history_search(q: str = ""):
    """חיפוש בהיסטוריית הריצות (item: global search) - לא רק שם סקריפט, גם
    תוכן ה-RESULT: (למשל שם קובץ שעובד). q ריק מחזיר [] (לא את כל ההיסטוריה) -
    הלקוח (loadHistory()) כבר מטפל בתצוגה הרגילה, זה רק למצב 'יש טקסט חיפוש'."""
    if not q.strip():
        return []
    rows = W.job_history.search_jobs(q.strip(), limit=50)
    return [
        {
            "script": script_name, "status": status, "started_at": started_at,
            "duration": duration_seconds, "summary": W.job_history.format_result_summary(result_json),
            "result": _result_dict(result_json),
        }
        for script_name, status, started_at, duration_seconds, result_json in rows
    ]


@router.get("/api/undo/status")
def api_undo_status():
    """יש/אין batch ממתין לביטול (item: undo last file-move operation) - רק
    cleanup_published_sources.py כותב ל-move_undo_log כרגע, ראו שם. הלקוח
    (loadHistory()) מציג/מסתיר את כפתור "↩️ בטל" לפי זה."""
    batch = move_undo_log.get_last_move_batch()
    if batch is None:
        return {"pending": False}
    return {"pending": True, "script_name": batch["script_name"], "file_count": len(batch["moves"])}


@router.post("/api/undo/last_move_batch")
@W.limiter.limit("10/minute")
async def api_undo_last_move_batch(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    result = move_undo_log.undo_last_move_batch()
    if "error" in result:
        return JSONResponse({"error": result["error"]}, status_code=400)
    W.audit_log.record_action("web", "undo_last_move_batch", details=f"restored={len(result['restored'])}", username=request.client.host if request.client else None)
    return {"restored": len(result["restored"]), "skipped": len(result["skipped"])}


def _new_progress_state() -> dict:
    return {"overall_seen": False, "overall_pct": 0, "done": 0, "total": None, "files": {}}


def _main_progress(state: dict, items: list) -> tuple:
    """(אחוז הפס הראשי, שניות שנותרו או None) מכל מה שהגיע מה-worker בסבב הזה; state נשמר בין סבבים עד סוף הריצה.

    סבב ייצוב: הפס הראשי והזמן שנותר באים מאותו מקור. קודם הפס היה הכולל (קבצים שהסתיימו - 0% עד הסוף בריצה של
    קובץ אחד) והזמן מהפס של הקובץ, אז הזמן רץ והפס עמד, והסטודיו עצר ריצה שהייתה ב-77%. כשהסקריפט מדווח כמה
    מתוך כמה ("PROGRESS: k/N"), הפס = הקבצים שהסתיימו + החלק שנעשה בקבצים שבעבודה. None = הזמן יוערך מהאחוז."""
    overall = None
    for item in items:
        if item.get("label"):
            state["files"][item["label"]] = item
        else:
            overall = item
            state["overall_seen"], state["overall_pct"] = True, item["pct"]
            if item.get("total"):
                state["done"], state["total"] = item["done"], item["total"]
    total = state["total"]
    if total:
        fractions = [f["pct"] / 100 for f in state["files"].values()]
        # קובץ שהגיע ל-100% עוד לפני שהכולל עודכן נספר פעם אחת - ולא נעלם (הפס לא חוזר אחורה)
        units = max(state["done"] + sum(x for x in fractions if x < 1), sum(fractions))
        active = [f for f in state["files"].values() if f["pct"] < 100]
        eta = active[0]["eta_seconds"] if total == 1 and state["done"] == 0 and len(active) == 1 else None
        return min(100, int(units * 100 / total)), eta
    if overall is not None:
        return overall["pct"], overall["eta_seconds"]
    if state["overall_seen"]:
        return state["overall_pct"], None
    latest = items[-1]
    return latest["pct"], latest["eta_seconds"]


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    import asyncio
    # ה-middleware של HTTP (_require_access_token) לא חל על WebSocket (פרוטוקול
    # שדרוג נפרד) - בדיקה זהה נדרשת כאן בנפרד. cookies נשלחים גם ב-handshake
    # של WS (אותו מקור), כי הדפדפן כבר טען את העמוד עם העוגייה קודם. query
    # param נבדק קודם - אותה סיבה כמו ב-_require_access_token. מכשיר מצומד - בעוגייה שלו (22.10.2026).
    if not W._authorize_websocket(websocket):
        await websocket.close(code=4401)
        return
    await websocket.accept()

    # משחזר את שורות הלוג מהריצה הנוכחית לחיבור חדש - בלי זה, חיבור שהתנתק
    # (רשת לא יציבה, טאב נרדם) והתחבר מחדש היה מפספס לצמיתות כל מה שקרה
    # בינתיים (queue.Queue.get_nowait() הרסני - רק מי שקורא ראשון "מקבל" שורה).
    # הודעה אחת (item: log spam) גם כשיש עד 500 שורות להשלים, לא 500 הודעות.
    if W._LOG_REPLAY_BUFFER:
        await websocket.send_json({
            "type": "log_batch",
            "lines": [{"line": line, "tag": tag} for line, tag in list(W._LOG_REPLAY_BUFFER)],
        })

    progress_state = _new_progress_state()
    disconnected, watcher = W._watch_ws_disconnect(websocket)
    try:
        while not disconnected.is_set():
            sent_anything = False

            batch = []
            try:
                while len(batch) < W._LOG_BATCH_SIZE:
                    line, tag = W.worker.log_queue.get_nowait()
                    W._LOG_REPLAY_BUFFER.append((line, tag))
                    batch.append({"line": line, "tag": tag})
            except queue.Empty:
                pass
            if batch:
                await websocket.send_json({"type": "log_batch", "lines": batch})
                sent_anything = True

            # item: התקדמות פר-קובץ - progress עם label (פס tqdm של קובץ ספציפי)
            # נאסף למפה {קובץ: אחוז}; progress בלי label (PROGRESS: הכולל/0/100
            # של ה-worker) הוא ההתקדמות הכוללת. כך הפס הראשי לא "קופץ" יותר בין
            # אחוז-קובץ לאחוז-כולל, וכל קובץ פעיל מוצג בנפרד.
            items = []
            try:
                while True:
                    items.append(W.worker.progress_queue.get_nowait())
                    sent_anything = True
            except queue.Empty:
                pass
            if items:
                pct, eta_seconds = _main_progress(progress_state, items)
                file_progress = {item["label"]: item["pct"] for item in items if item.get("label")}
                if eta_seconds is None and pct < 100 and W._current_run["script_name"] and W._current_run["started_at"]:
                    # סקריפט שמדווח רק PROGRESS:N בלי ETA משלו (למשל dataviz): ETA מההתקדמות + היסטוריית הריצות (job_history)
                    script = W._current_run["script_name"]
                    if progress_state.get("typical_for") != script:
                        progress_state["typical_for"] = script
                        progress_state["typical"] = W.job_history.get_typical_duration(script)
                    eta_seconds = W.job_history.estimate_remaining_seconds(
                        time.time() - W._current_run["started_at"], pct, progress_state.get("typical"))
                await websocket.send_json({
                    "type": "progress", "pct": pct,
                    "eta": format_duration(eta_seconds) if eta_seconds is not None else None,
                    "files": file_progress,
                })

            try:
                outcome = W._finished_queue.get_nowait()
                sent_anything = True
                success = outcome.get("returncode") == 0
                # 23.10.2026: ההיסטוריה, ה-webhook, הגיבוי ומצב לילה כבר קרו בסוף הריצה עצמה (W._record_run_end) - גם
                # כשאין טאב מחובר. כאן רק מודיעים לדפדפן, כולל הספירה לאחור של הכיבוי (shutdown_seconds) עם ביטול
                W._current_run["script_name"] = None
                W._current_run["started_at"] = None
                progress_state.clear()
                progress_state.update(_new_progress_state())
                await websocket.send_json({
                    "type": "finished", "success": success, "result": outcome.get("result"),
                    "shutdown_seconds": outcome.get("shutdown_seconds"),
                    # גל 8: פעולות סוף-ריצה של עורך-העל (שינה/פרסום/צליל) - לדפדפן להציג/לבטל
                    "sleep_seconds": outcome.get("sleep_seconds"), "publish_started": outcome.get("publish_started"),
                    "finish_sound": outcome.get("finish_sound"), "editor_run_id": outcome.get("editor_run_id"),
                })
            except queue.Empty:
                pass

            await asyncio.sleep(0.05 if sent_anything else 0.2)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        watcher.cancel()
