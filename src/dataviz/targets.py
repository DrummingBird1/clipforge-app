# dataviz/targets.py
#
# גל 41: יעדי פרסום לסרטון נתונים. YouTube = הגדרות הפרק כמו שהן (לרוחב); Shorts ו-TikTok = פריים לאורך
# 1080x1920 (הפריסה האנכית ב-charts/base.py), עם שם קובץ משלו כדי לא לדרוס את הגרסה לרוחב.

import copy
from typing import Any, Dict, Mapping

TARGETS: Dict[str, Dict[str, Any]] = {
    "youtube": {"label": "YouTube (16:9)", "vertical": False},
    "shorts": {"label": "YouTube Shorts (9:16)", "vertical": True},
    "tiktok": {"label": "TikTok (9:16)", "vertical": True},
}
VERTICAL_SIZE = (1080, 1920)


def apply_target(config: Mapping[str, Any], target: str) -> Dict[str, Any]:
    """עותק של ההגדרות ליעד. יעד לא מוכר -> ValueError; youtube לא משנה כלום."""
    if target not in TARGETS:
        raise ValueError(f"יעד לא מוכר: {target!r} (קיימים: {', '.join(TARGETS)}).")
    result = copy.deepcopy(dict(config))
    if not TARGETS[target]["vertical"]:
        return result
    video = result["video"]
    width, height = VERTICAL_SIZE
    # אותו גודל טקסט ביחס לרוחב הפריים: רוחב אינצ'ים קטן יותר -> DPI קצת גבוה יותר
    video["dpi"] = max(40, int(round(video["dpi"] * width / max(video["width"], 1) * 1.25)))
    video["width"], video["height"] = width, height
    video["output_name"] = f"{video.get('output_name') or result.get('name', 'episode')}_{target}"
    return result
