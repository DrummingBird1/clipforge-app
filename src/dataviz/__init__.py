# dataviz/__init__.py
#
# מנוע סרטוני ויזואליזציית נתונים בסגנון "Data is Beautiful" (bar chart race ועוד).
# חבילה מבודדת: לא מייבאת שום קוד של ClipForge (utils/ וכו') - נתיב ffmpeg, תיקיית
# הפלט ודיווח ההתקדמות מגיעים מבחוץ (my_scripts/video/dataviz_maker.py), כך שאפשר
# להוציא אותה לפרויקט נפרד כמו שהיא.
#
# הזרימה: episode (הגדרות + נתונים -> מטריצה יומית) -> plan (מצב כל פריים, בלי ציור)
# -> charts (ציור פריים אחד, פונקציה טהורה של הפריים בתכנית) -> render (מקבילי + ffmpeg).

from dataviz.config import ConfigError, load_config
from dataviz.episode import Episode, load_episode
from dataviz.plan import build_plan
from dataviz.render import render_stills, render_video, still_indices

__all__ = [
    "ConfigError",
    "Episode",
    "build_plan",
    "load_config",
    "load_episode",
    "render_stills",
    "render_video",
    "still_indices",
]
