# entrypoints/web/routes/bot.py
#
# בוט הדיסקורד: הפעלה/עצירה, לוג חי, RSS ו-Steam.
# גל 11: הועבר כמו שהוא מ-web_app.py - המצב המשותף (נתיבים, helpers, מנעולים) נשאר
# שם ונגיש כ-W.<שם>, כך ש-monkeypatch.setattr(web_app, ...) חל גם על ה-endpoints כאן.

import queue
import threading
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from entrypoints import web_app as W

router = APIRouter()


@router.get("/api/bot/status")
def api_bot_status():
    with W._bot_state_lock:
        return {"running": W._bot_state["is_running"], "gave_up": W._bot_state["gave_up"], "config_error": W._bot_state["config_error"]}


@router.post("/api/bot/start")
def api_bot_start(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    with W._bot_state_lock:
        if W._bot_state["is_running"]:
            return JSONResponse({"error": "הבוט כבר רץ."}, status_code=409)
        W._bot_state["is_running"] = True
        W._bot_state["gave_up"] = False
        W._bot_state["config_error"] = False
        W._bot_state["crash_timestamps"] = []
    threading.Thread(target=W._run_bot_process_loop, daemon=True).start()
    W.audit_log.record_action("web", "start_bot", username=request.client.host if request.client else None)
    return {"ok": True}


@router.post("/api/bot/stop")
def api_bot_stop(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    with W._bot_state_lock:
        W._bot_state["is_running"] = False
        proc = W._bot_state["process"]
        W._bot_state["process"] = None
    if proc:
        proc.terminate()
    W._bot_write_to_log("\n--- הבוט כובה על ידי המשתמש ---\n")
    W.audit_log.record_action("web", "stop_bot", username=request.client.host if request.client else None)
    return {"ok": True}


@router.websocket("/ws/bot")
async def ws_bot_endpoint(websocket: WebSocket):
    """סטרימינג לוג הבוט - אותו עיקרון בדיוק כמו /ws (סקריפטים), רק על
    _bot_log_queue/_bot_log_buffer במקום worker.log_queue."""
    import asyncio
    if not W._authorize_websocket(websocket):
        await websocket.close(code=4401)
        return
    await websocket.accept()

    if W._bot_log_buffer:
        await websocket.send_json({"type": "log_batch", "lines": [{"line": line} for line in list(W._bot_log_buffer)]})

    disconnected, watcher = W._watch_ws_disconnect(websocket)
    try:
        while not disconnected.is_set():
            sent_anything = False
            batch = []
            try:
                while len(batch) < W._LOG_BATCH_SIZE:
                    batch.append({"line": W._bot_log_queue.get_nowait()})
            except queue.Empty:
                pass
            if batch:
                await websocket.send_json({"type": "log_batch", "lines": batch})
                sent_anything = True
            await asyncio.sleep(0.05 if sent_anything else 0.2)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        watcher.cancel()


@router.get("/api/bot/rss")
def api_bot_rss_list():
    W._ensure_bot_tables()
    with W.db.connect(W.BOT_DB_PATH) as conn:
        rows = conn.execute("SELECT id, name, url, channel_id FROM rss_feeds").fetchall()
    return [{"id": r[0], "name": r[1], "url": r[2], "channel_id": r[3]} for r in rows]


@router.post("/api/bot/rss")
async def api_bot_rss_add(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    name = str(payload.get("name", "")).strip()
    url = str(payload.get("url", "")).strip()
    try:
        channel_id = int(payload.get("channel_id"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "מזהה ערוץ (channel_id) חייב להיות מספר."}, status_code=400)
    if not name or not url:
        return JSONResponse({"error": "שם וכתובת RSS הם שדות חובה."}, status_code=400)

    W._ensure_bot_tables()
    with W.db.connect(W.BOT_DB_PATH) as conn:
        conn.execute("INSERT INTO rss_feeds (name, url, channel_id) VALUES (?, ?, ?)", (name, url, channel_id))
    W.audit_log.record_action("web", "rss_feed_add", details=name, username=request.client.host if request.client else None)
    return {"ok": True}


@router.delete("/api/bot/rss/{feed_id}")
def api_bot_rss_delete(feed_id: int, request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    W._ensure_bot_tables()
    with W.db.connect(W.BOT_DB_PATH) as conn:
        conn.execute("DELETE FROM rss_feeds WHERE id = ?", (feed_id,))
    W.audit_log.record_action("web", "rss_feed_delete", details=str(feed_id), username=request.client.host if request.client else None)
    return {"ok": True}


@router.get("/api/bot/steam")
def api_bot_steam_list():
    W._ensure_bot_tables()
    with W.db.connect(W.BOT_DB_PATH) as conn:
        rows = conn.execute("SELECT id, name, app_id, channel_id FROM steam_games").fetchall()
    return [{"id": r[0], "name": r[1], "app_id": r[2], "channel_id": r[3]} for r in rows]


@router.post("/api/bot/steam")
async def api_bot_steam_add(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    name = str(payload.get("name", "")).strip()
    app_id = str(payload.get("app_id", "")).strip()
    try:
        channel_id = int(payload.get("channel_id"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "מזהה ערוץ (channel_id) חייב להיות מספר."}, status_code=400)
    if not name or not app_id:
        return JSONResponse({"error": "שם משחק ו-App ID הם שדות חובה."}, status_code=400)

    W._ensure_bot_tables()
    with W.db.connect(W.BOT_DB_PATH) as conn:
        conn.execute("INSERT INTO steam_games (name, app_id, channel_id) VALUES (?, ?, ?)", (name, app_id, channel_id))
    W.audit_log.record_action("web", "steam_game_add", details=name, username=request.client.host if request.client else None)
    return {"ok": True}


@router.delete("/api/bot/steam/{game_id}")
def api_bot_steam_delete(game_id: int, request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    W._ensure_bot_tables()
    with W.db.connect(W.BOT_DB_PATH) as conn:
        conn.execute("DELETE FROM steam_games WHERE id = ?", (game_id,))
    W.audit_log.record_action("web", "steam_game_delete", details=str(game_id), username=request.client.host if request.client else None)
    return {"ok": True}
