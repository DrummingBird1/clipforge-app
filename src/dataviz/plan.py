# dataviz/plan.py
#
# תכנון כל הפריימים מראש, בלי ציור: קצב הזמן (כמה פריימים לכל יום), דירוג מוחלק,
# ציר X מוחלק, כרטיסי אירוע, התראות "שיא חדש", אינטרו ואאוטרו. התוצאה היא רשימת
# dicts פשוטים (נשלחים לתהליכי הרינדור), והציור הוא פונקציה טהורה של פריים אחד.
#
# כלל הקצב (למדנו אותו מהקפיצות בגרסאות הראשונות): לכל יום מוקצים מספיק פריימים כך
# שאף עמודה לא תתקדם ביותר מ-step (0.5% מהציר) בפריים אחד - יום כמו 7.10.2023 מתפרש
# על פני כמה שניות במקום לקפוץ. סביב אירועים יש האטה, ושני מעברי החלקה (מקסימום ואז
# ממוצע) נותנים כניסה ויציאה הדרגתיות מההאטה בלי לשטח את השיא.
#
# strict (ברירת מחדל): הפריימים שבין יום d ל-d+1 מנפישים את התוספת של יום d+1, ומעבר
# הממוצע מוריד את המשקל של היום שלפני תחילת קפיצה - בגרסה המקורית זה נתן עד ~23% מעל
# step ב-2% מהפריימים (למשל 11/11/2018). strict מבטיח ליום d לפחות את מה שהתוספת של d+1
# דורשת. strict_step: false משחזר בדיוק את הסרטון הראשון.

from typing import Any, Dict, List, Literal, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd

Frame = Dict[str, Any]


def pacing_weights(daily: np.ndarray, cum: np.ndarray, event_days: Sequence[int], *, step: float, base: float,
                   axis_min: float, before: int, after: int, extra: float, window: int, strict: bool = True,
                   rolling: bool = False) -> np.ndarray:
    """פריימים לכל יום. daily/cum = [יום, ישות]. rolling (גל 49): הערכים הם חלון מתגלגל - הקפיצה היא השינוי
    בערך המוצג (עולה או יורד), והציר הוא המוביל של אותו יום (הוא גם מצטמצם)."""
    if rolling:
        inc = np.abs(np.diff(cum, axis=0, prepend=np.zeros((1, cum.shape[1])))).max(axis=1)
        axis = np.maximum(cum.max(axis=1), axis_min)
    else:
        inc = np.abs(daily).max(axis=1)                        # הקפיצה היומית הגדולה ביותר - גם ירידה (23.10.2026: רמה שצונחת)
        axis = np.maximum(np.maximum.accumulate(cum.max(axis=1)), axis_min)
    need = inc / axis / step
    w = np.maximum(base, need)
    for di in event_days:                                      # האטה סביב אירועים
        w[max(di - before, 0):di + after] += extra
    w = (pd.Series(w).rolling(window, center=True, min_periods=1).max()
         .rolling(window, center=True, min_periods=1).mean().to_numpy(copy=True))
    if strict and len(w) > 1:
        w[:-1] = np.maximum(w[:-1], need[1:])
    return w


def _pacing_daily(episode: Any) -> np.ndarray:
    """18.10.2026: ביום הראשון של ישות ממקור רמות (kind: level) התוספת היא הרמה כולה - זו כניסה, לא קפיצה, אז כלל
    ה-STEP לא מאט עליה (אחרת הקו "נבנה" מ-0 במשך כמה שניות). בלי רמות - daily כמו שהוא."""
    levels = getattr(episode, "levels", None) or []
    if not levels:
        return episode.daily
    daily = np.array(episode.daily, dtype=float, copy=True)
    for e in levels:
        c = episode.entities.index(e)
        if episode.start_idx[c] < len(daily):
            daily[episode.start_idx[c], c] = 0.0
    return daily


def frame_days(weights: np.ndarray, n_frames: int) -> np.ndarray:
    """היום (שבור) שכל פריים מציג - פריים לכל weights[d] של זמן, כך שיום כבד מקבל יותר פריימים."""
    n_days = len(weights)
    cum_w = np.concatenate([[0.0], np.cumsum(weights)])[:n_days]
    return np.interp(np.linspace(0, cum_w[-1], n_frames), cum_w, np.arange(n_days))


def event_schedule(day_f: np.ndarray, events: Sequence[Tuple[str, str, int]], cards: Mapping[str, Any]) -> List[Tuple[int, str, str, int]]:
    """(פריים התחלה, תווית, תאריך, משך) לכל אירוע. משך = עד האירוע הבא פחות מרווח, בין מינימום למקסימום."""
    starts = [(int(np.searchsorted(day_f, di)), label, date) for date, label, di in events]
    result = []
    for k, (f, label, date) in enumerate(starts):
        gap = (starts[k + 1][0] - f - cards["gap_frames"]) if k + 1 < len(starts) else cards["max_frames"]
        result.append((f, label, date, max(cards["min_frames"], min(cards["max_frames"], gap))))
    return result


def main_frame_count(weights: np.ndarray, fixed: int) -> Tuple[int, np.ndarray]:
    """אורך הקטע הראשי: לפי הקצב (fixed=0), או קבוע (מצב test) עם משקלות מנורמלים."""
    if fixed:
        return fixed, weights * (fixed / weights.sum())
    return int(round(weights.sum())), weights


def build_plan(episode: Any, mode: str = "full") -> List[Frame]:
    """תכנית מלאה לפרק: intro + main + outro (פריים = dict)."""
    from dataviz.config import mode_timing

    cfg = episode.config
    timing, ranking = cfg["timing"], cfg["ranking"]
    slow = timing["event_slowdown"]
    lengths = mode_timing(cfg, mode)
    weights = pacing_weights(_pacing_daily(episode), episode.cum, [di for _, _, di in episode.events], step=timing["step"],
                             base=timing["base_frames_per_day"], axis_min=ranking["axis_min"], before=slow["before_days"],
                             after=slow["after_days"], extra=slow["extra"], window=timing["smooth_window"],
                             strict=bool(timing.get("strict_step", True)),
                             rolling=(cfg.get("values") or {}).get("mode") == "rolling")
    story = cfg.get("story") or {}
    weights = apply_speed(weights, episode.dates, story.get("speed") or [])
    n_main, weights = main_frame_count(weights, lengths["main"])
    day_f = frame_days(weights, n_main)
    main = plan_main(episode, day_f)
    fps = int(cfg["video"]["fps"])
    main = insert_holds(main, day_f, episode, fps)
    teaser = cfg.get("teaser") or {}
    opening = plan_teaser(episode, main, int(float(teaser.get("seconds") or 3) * fps), str(teaser.get("label") or "")) if teaser.get("enabled") else []
    return opening + plan_intro(lengths["intro"]) + main + plan_outro(episode, lengths["outro"])


def day_index(dates: Any, date: Any, side: Literal["left", "right"] = "left") -> int:
    """האינדקס של התאריך בימי הפרק (תאריך לפני ההתחלה = 0, אחרי הסוף = מספר הימים)."""
    return int(np.searchsorted(np.asarray(dates.values), np.datetime64(pd.Timestamp(str(date)).normalize()), side=side))


def apply_speed(weights: np.ndarray, dates: Any, segments: Sequence[Mapping[str, Any]]) -> np.ndarray:
    """גל 50: קטעי מהירות - בכל טווח תאריכים הפריימים לכל יום מחולקים ב-speed (2 = פי שניים מהר יותר,
    0.5 = לאט פי שניים). מעל כלל ה-STEP: המשתמש בחר לרוץ מהר יותר גם על חשבון קפיצות."""
    if not segments:
        return weights
    result = weights.copy()
    for segment in segments:
        a, b = day_index(dates, segment["start"]), day_index(dates, segment["end"], "right")
        result[a:b] = result[a:b] / float(segment["speed"])
    return result


def insert_holds(main: List[Frame], day_f: np.ndarray, episode: Any, fps: int) -> List[Frame]:
    """גל 50: פרקים ועצירות - הפריים של היום הזה קופא לכמה שניות, עם כרטיס כותרת (פרק) או הסבר (עצירה).
    הפריימים הקפואים הם עותקים של אותו פריים עם "hold" (סוג, טקסט ו-t מ-0 ל-1 בשביל כניסה ויציאה)."""
    story = episode.config.get("story") or {}
    dates = episode.dates
    holds = []
    for item in story.get("chapters") or []:
        seconds = float(item.get("seconds") or story.get("chapter_seconds") or 2.5)
        holds.append((item["date"], 0, {"kind": "chapter", "title": str(item["title"]), "subtitle": str(item.get("subtitle") or "")}, seconds))
    for item in story.get("pauses") or []:
        seconds = float(item.get("seconds") or story.get("pause_seconds") or 3.0)
        holds.append((item["date"], 1, {"kind": "pause", "text": str(item["text"])}, seconds))
    if not holds or not main:
        return main
    result = list(main)
    placed = []
    for date, order, hold, seconds in holds:
        di = day_index(dates, date)
        if di >= len(dates) or pd.Timestamp(str(date)) < dates[0]:
            continue    # מחוץ לטווח הפרק
        placed.append((int(np.searchsorted(day_f, di)), order, hold, max(1, int(round(seconds * fps)))))
    for f, _order, hold, n in sorted(placed, key=lambda h: (h[0], h[1]), reverse=True):
        f = min(f, len(main) - 1)
        frozen = {k: v for k, v in main[f].items() if k != "say"}
        copies = [{**frozen, "hold": {**hold, "t": j / max(n - 1, 1)}} for j in range(n)]
        head = result[f]   # ג6: משפט מהתסריט נאמר פעם אחת - בפריים הראשון של העצירה, ולא בכל פריים קפוא
        if head.get("say"):
            copies[0]["say"] = head["say"]
            result[f] = {k: v for k, v in head.items() if k != "say"}
        result[f:f] = copies
    return result


def plan_teaser(episode: Any, main: Sequence[Frame], n: int, label: str) -> List[Frame]:
    """גל 50: פתיח "טיזר" - n פריימים מהרגע החזק (היום עם התוספת הגדולה ביותר, כמו במצב share), לפני הפתיח."""
    if n <= 0 or not main:
        return []
    totals = episode.daily.sum(axis=1)
    day = int(totals.argmax()) if len(totals) else 0
    # ב12: רק פריימים שזזים (בלי העצירות), ובלי מה שיוצג שוב בהמשך - כרטיס אירוע, שיא, משפט מהתסריט (כתוביות וקריינות)
    moving = [f for f in main if "hold" not in f]
    center = next((i for i, f in enumerate(moving) if f["x"] >= day), len(moving) - 1)
    start = max(0, min(center - n * 2 // 3, len(moving) - n))
    return [{**{k: v for k, v in f.items() if k not in ("hold", "say", "card", "toast")}, "teaser": label} for f in moving[start:start + n]]


def rank_matrix(cum: Any, start_idx: Sequence[int], smooth: int = 1) -> Any:
    """[ימים x ישויות] דירוג (1 = הגבוה ביותר) בין הישויות שכבר התחילו; NaN לפני ההתחלה. smooth > 1 = ממוצע נע."""
    cum = np.asarray(cum, dtype=float)
    n_days, n_ent = cum.shape
    active = np.arange(n_days)[:, None] >= np.asarray(start_idx)[None, :]
    order = np.argsort(-np.where(active, cum, -np.inf), axis=1, kind="stable")
    ranks = np.empty((n_days, n_ent))
    np.put_along_axis(ranks, order, np.broadcast_to(np.arange(1, n_ent + 1, dtype=float), (n_days, n_ent)), axis=1)
    ranks[~active] = np.nan
    if smooth > 1:
        ranks = pd.DataFrame(ranks).rolling(smooth, min_periods=1).mean().to_numpy().copy()
        ranks[~active] = np.nan
    return ranks


def rank_moves(ranks: np.ndarray, day: int, window: int, shown: Sequence[Any], col: Mapping[Any, int]) -> Dict[Any, int]:
    """גל 49: כמה מקומות כל ישות שבתמונה עלתה (+) או ירדה (-) לעומת window ימים אחורה."""
    before = max(day - window, 0)
    moves: Dict[Any, int] = {}
    for entity in shown:
        now, then = ranks[day, col[entity]], ranks[before, col[entity]]
        if not (np.isnan(now) or np.isnan(then)) and int(then - now):
            moves[entity] = int(then - now)
    return moves


def plan_intro(n: int) -> List[Frame]:
    return [{"k": "intro", "t": j / max(n - 1, 1)} for j in range(n)]


def plan_main(episode: Any, day_f: np.ndarray) -> List[Frame]:
    cfg = episode.config
    ranking, records, cards = cfg["ranking"], cfg["records"], cfg["cards"]
    top_n = int(ranking["top_n"])
    smoothing = float(ranking["smoothing"])
    date_format = cfg["labels"]["date_format"]
    record_text = cfg["labels"]["record"]
    entities = episode.entities
    col = {e: i for i, e in enumerate(entities)}
    cum, n_days = episode.cum, episode.n_days
    years = np.asarray(episode.dates.year)
    schedule = event_schedule(day_f, episode.events, cards)
    labels = cfg["labels"]
    callouts = plan_callouts(episode)
    annotations = plan_annotations(episode)
    focus_steps, focus_dim = plan_focus(episode)
    script = sorted((day_index(episode.dates, item["date"]), str(item["text"]))
                    for item in (cfg.get("story") or {}).get("script") or [])
    # גל 49: חיצי דירוג ו-"+N" - רק כשהופעלו (הפריימים של סרטון בלי הן נשארים בדיוק כמו קודם)
    ranks = rank_matrix(cum, episode.start_idx) if labels.get("rank_arrows") else None
    rank_window = int(labels.get("rank_window_days") or 7)
    gains_min = float(labels.get("gains_min") or 0.0)

    pos: Dict[Any, float] = {}
    xmax = float(ranking["axis_min"])
    prev_leader, last_toast, toast_from = None, -9999, -9999
    toast_text = ""
    frames: List[Frame] = []
    for fi in range(len(day_f)):
        x = day_f[fi]
        i0 = int(np.floor(x))
        i1 = min(i0 + 1, n_days - 1)
        a = x - i0
        vals = cum[i0] * (1 - a) + cum[i1] * a
        cur_idx = int(episode.current[i0])
        cur = entities[cur_idx] if cur_idx >= 0 else None
        active = [e for e in entities if episode.start_idx[col[e]] <= i0]

        def val(e: Any, vals: Any = vals) -> Any:   # קשירה מפורשת של הערכים של האיטרציה הזו (B023)
            return vals[col[e]]

        shown = sorted(active, key=lambda e: -val(e))[:top_n]
        if cur is not None and cur in active and cur not in shown:
            shown = sorted(shown[:-1] + [cur], key=lambda e: -val(e))
        target = {e: float(r) for r, e in enumerate(shown)}
        for e in active:
            t = target.get(e, top_n + 1.0)
            if e not in pos:
                pos[e] = t if fi == 0 else float(top_n)
            pos[e] += (t - pos[e]) * smoothing

        leader = shown[0] if shown else None
        if leader != prev_leader:
            takes_lead = leader == cur if records["when"] == "current_takes_lead" else True
            if (records["enabled"] and prev_leader is not None and leader is not None and takes_lead
                    and val(leader) > records["min_value"] and fi - last_toast > records["cooldown_frames"]):
                toast_from, last_toast, toast_text = fi, fi, record_text.format(entity=leader)
            prev_leader = leader

        top_val = max(val(e) for e in shown) if shown else 0.0
        tgt_x = max(top_val * ranking["axis_headroom"], ranking["axis_min"])
        xmax += (tgt_x - xmax) * (ranking["axis_rise"] if tgt_x > xmax else ranking["axis_fall"])
        xmax = max(xmax, top_val * ranking["axis_min_headroom"])

        card = None
        for f, label, date, dur in schedule:
            if f <= fi < f + dur:
                card = (label, pd.Timestamp(date).strftime(date_format),
                        min(1.0, (fi - f) / cards["fade_in_frames"], (f + dur - fi) / cards["fade_out_frames"]))
        toast = None
        dur_toast = records["duration_frames"]
        if toast_from <= fi < toast_from + dur_toast:
            toast = (toast_text, min(1.0, (fi - toast_from) / records["fade_in_frames"],
                                     (toast_from + dur_toast - fi) / records["fade_out_frames"]))

        bars = [(e, float(val(e)), round(pos[e], 3)) for e in active if pos[e] < top_n + 0.01]
        frame = {"k": "main", "date": episode.dates[i0].strftime(date_format), "bars": bars,
                 "xmax": float(xmax), "year": int(years[i0]), "current": cur, "leader": leader, "card": card,
                 "toast": toast, "frac": float(x / (n_days - 1)) if n_days > 1 else 1.0,
                 "total": float(vals.sum()), "x": float(x)}
        if ranks is not None:
            frame["moves"] = rank_moves(ranks, i0, rank_window, shown, col)
        if labels.get("gains") and i1 > i0:
            jumps = {e: float(cum[i1, col[e]] - cum[i0, col[e]]) for e in shown}
            frame["gains"] = {e: g for e, g in jumps.items() if g > 0 and g >= gains_min * xmax}
        while script and script[0][0] <= x:   # 20.10.2026: תסריט קריינות - בפריים הראשון שמגיע לתאריך
            frame.setdefault("say", []).append(script.pop(0)[1])
        if focus_steps:   # 20.10.2026: הישויות בפוקוס ברגע הזה (האחרונה שהתחילה)
            frame["focus"] = next(names for d0, names in reversed(focus_steps) if d0 <= x)
            frame["focus_dim"] = focus_dim
        if annotations:   # 20.10.2026: (יום, ערך, טקסט, dx, dy, סגנון, שקיפות)
            on = [(d0, value, text, dx, dy, style, min(1.0, (x - d0) / fade, (d0 + days - x) / fade))
                  for d0, days, fade, value, text, dx, dy, style in annotations if d0 <= x < d0 + days]
            if on:
                frame["annotations"] = on
        if callouts:
            # 27.10.2026: גם מספר ההערה ברשימה ו-dx/dy (גרירה בתצוגה) - הציור מתחיל בשלושת הראשונים, כמו קודם
            active_now = [(entity, text, min(1.0, (x - d0) / fade, (d0 + days - x) / fade), index, dx, dy)
                          for d0, days, fade, entity, text, index, dx, dy in callouts if d0 <= x < d0 + days and entity in shown]
            if active_now:
                frame["callouts"] = active_now
        frames.append(frame)
    return frames


def plan_callouts(episode: Any) -> List[Tuple[int, int, float, Any, str, int, Any, Any]]:
    """גל 50: הערות לישות - (יום ההתחלה, כמה ימים, ימי כניסה/יציאה, הישות, הטקסט, המספר ברשימה, dx, dy). הישות לפי
    השם כטקסט (2020 ו-"2020" זה אותו דבר); הערה על ישות שלא בפרק או מחוץ לטווח - לא מוצגת. dx/dy (27.10.2026): None
    כשההערה לא נגררה בתצוגה."""
    story = episode.config.get("story") or {}
    by_name = {str(e): e for e in episode.entities}
    result = []
    for index, item in enumerate(story.get("callouts") or []):
        entity = by_name.get(str(item.get("entity")))
        d0 = day_index(episode.dates, item["date"])
        if entity is None or d0 >= episode.n_days:
            continue
        days = int(item.get("days") or story.get("callout_days") or 30)
        moved = "dx" in item and "dy" in item
        result.append((d0, days, max(days * 0.15, 0.5), entity, str(item["text"]), index,
                       int(item["dx"]) if moved else None, int(item["dy"]) if moved else None))
    return result


def clip_range(plan: List[Frame], episode: Any, start: Any, end: Any) -> List[Frame]:
    """27.10.2026: רק הקטע הראשי בין שני תאריכים (YYYY-MM-DD, כולל) - "רינדור טווח" לבדיקה של קטע אחד, בלי פתיח, טיזר
    וסיום. טווח בלי אף פריים - ValueError."""
    lo, hi = sorted((day_index(episode.dates, str(start)), day_index(episode.dates, str(end))))
    kept = [f for f in plan if f.get("k") == "main" and not f.get("teaser") and lo <= float(f.get("x", -1)) <= hi + 0.999]
    if not kept:
        raise ValueError(f"אין פריימים בטווח {start} - {end}.")
    return kept


def plan_focus(episode: Any) -> Tuple[List[Tuple[int, Tuple[str, ...]]], float]:
    """20.10.2026: מצב פוקוס - [(יום, שמות הישויות בפוקוס)] מההתחלה ובכל החלפה (story.focus), והעמעום. בלי פוקוס - []."""
    cfg = episode.config
    focus = cfg.get("focus") or {}
    switches = sorted(((day_index(episode.dates, item["date"]), tuple(str(n) for n in item["entities"]))
                       for item in (cfg.get("story") or {}).get("focus") or []), key=lambda s: s[0])
    base = tuple(str(n) for n in focus.get("entities") or [])
    if not base and not switches:
        return [], 1.0
    return [(-1, base)] + switches, float(focus.get("dim", 0.25))


def plan_annotations(episode: Any) -> List[Tuple[int, int, float, float, str, int, int, str]]:
    """20.10.2026: הערות על הגרף - (יום, כמה ימים, ימי כניסה/יציאה, ערך, טקסט, dx, dy, סגנון). בלי days - עד הסוף."""
    result = []
    for item in (episode.config.get("story") or {}).get("annotations") or []:
        d0 = day_index(episode.dates, item["date"])
        if d0 >= episode.n_days:
            continue
        days = int(item.get("days") or episode.n_days - d0 + 1)
        result.append((d0, days, max(min(days * 0.1, 10.0), 0.5), float(item["value"]), str(item["text"]),
                       int(item.get("dx", -60)), int(item.get("dy", 40)), str(item.get("style") or "default")))
    return result


def plan_outro(episode: Any, n: int) -> List[Frame]:
    """סיום: הדירוג הסופי של כל הסדרה, קבוע, עם תיבת "המקומות הראשונים"."""
    cfg = episode.config
    top_n = int(cfg["ranking"]["top_n"])
    places = len(cfg["outro"]["places"])
    col = {e: i for i, e in enumerate(episode.entities)}
    final_vals = episode.cum[-1]
    top = sorted(episode.entities, key=lambda e: -final_vals[col[e]])[:top_n]
    final_bars = [(e, float(final_vals[col[e]]), float(r)) for r, e in enumerate(top)]
    # 23.10.2026: לא מתחת ל-axis_min (כמו בקטע הראשי) - כל הערכים 0 או שליליים נתנו ציר 0 / שלילי (חלוקה ב-0 בפיזור)
    xmax = max(float(final_bars[0][1] * cfg["ranking"]["axis_headroom"]) if final_bars else 0.0, float(cfg["ranking"]["axis_min"]))
    frames = [{"k": "outro", "t": j / max(n - 1, 1), "bars": final_bars, "xmax": xmax,
               "top": [(e, v) for e, v, _ in final_bars[:places]], "frac": 1.0, "total": float(final_vals.sum()),
               "x": float(episode.n_days - 1)} for j in range(n)]
    end_screen = cfg.get("end_screen") or {}
    if end_screen.get("enabled"):   # גל 50: השניות האחרונות - מסך סיום עם מקום פנוי לאלמנטים של יוטיוב
        last = min(n, int(float(end_screen.get("seconds") or 20) * int(cfg["video"]["fps"])))
        for j, frame in enumerate(frames[n - last:]):
            frame["end_screen"] = j / max(last - 1, 1)
    return frames
