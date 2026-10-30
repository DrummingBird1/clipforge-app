# ui/approvals_tab.py
#
# גרסת-דסקטופ ל"אישור קליפים" (item: mobile-friendly clip-approval view) -
# אותה טבלת pending_approvals ש-cogs/approval_cog.py מזין דרך הבוט (ומאפשר
# לאשר/לדחות דרך כפתורים בדיסקורד), נקרא/נכתב כאן דרך utils/bot/approval_store.py
# (סינכרוני, בלי תלות בזה שהבוט רץ - זהה לדפוס הקיים כבר ב-web_app.py's
# הטאב המקביל). המוקד המקורי של הפיצ'ר הוא "מהטלפון" (ראו web_app.py), אבל
# לפי כלל-הזהב של הפרויקט הזה ("כל שינוי חייב להתקיים גם בדסקטופ וגם בווב")
# הטאב הזה קיים גם כאן, לשימוש מקומי בלי לפתוח דפדפן בכלל.
import os

import customtkinter as ctk
from PIL import Image

from utils.shared.workspace_dir import WORKSPACE_DIR  # CLIPFORGE_WORKSPACE_DIR (טסטים, שרת בדיקה) - ברירת המחדל workspace/ כמו קודם
from utils.bot import approval_store
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.i18n import t
from utils.shared.state import PALETTE
from utils.media.thumbnail_generator import extract_frame_at_timestamp, get_video_duration_via_ffprobe

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# אותה THUMBNAIL_CACHE_DIR בדיוק כמו web_app.py - קליפ שכבר קיבל תמונה
# ממוזערת בגלריית הווב לא צריך לחלץ פריים שוב כאן.
THUMBNAIL_CACHE_DIR = os.path.join(WORKSPACE_DIR, ".cache", "thumbnail_cache")  # = web_app
THUMBNAIL_DISPLAY_SIZE = (320, 180)


class ApprovalsTabComponent(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        # CTkImage/PIL.Image חייבים רפרנס חי כל עוד הם מוצגים - אחרת האספן
        # (GC) של פייתון עלול לפנות אותם והתמונה נעלמת מה-widget בלי שגיאה.
        self._image_refs = []
        self._build_tab()
        self.refresh_approvals()

    def _build_tab(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(header, text=t("✅ אישור קליפים"), font=("Segoe UI", 13, "bold")).pack(side="right")
        ctk.CTkButton(header, text="🔄", width=28, height=24, fg_color=PALETTE["border"], command=self.refresh_approvals).pack(side="left")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=10, pady=10)

    def refresh_approvals(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        self._image_refs.clear()

        # שורות שהקובץ שלהן כבר לא קיים בדיסק (אושר/נדחה במקביל מהדיסקורד וכו')
        # מסוננות כאן - זהה ל-web_app.py's /api/approvals.
        rows = [
            (pending_id, video_path, created_at)
            for pending_id, video_path, created_at in approval_store.get_pending_approvals()
            if os.path.isfile(video_path)
        ]
        if not rows:
            ctk.CTkLabel(self.scroll, text=t("אין קליפים שממתינים לאישור כרגע."), text_color=PALETTE["text_muted"]).pack(pady=10)
            return

        for pending_id, video_path, created_at in rows:
            self._build_card(pending_id, video_path, created_at)

    def _build_card(self, pending_id, video_path, created_at):
        card = ctk.CTkFrame(self.scroll, fg_color=PALETTE["surface_alt"])
        card.pack(fill="x", pady=6)

        thumb = self._load_thumbnail(video_path)
        if thumb:
            self._image_refs.append(thumb)
            ctk.CTkLabel(card, image=thumb, text="").pack(pady=(8, 4))

        game_name = os.path.basename(os.path.dirname(video_path))
        ctk.CTkLabel(card, text=os.path.basename(video_path), font=("Segoe UI", 12, "bold")).pack()
        ctk.CTkLabel(
            card, text=t("🎮 {game} · {created_at}", game=game_name, created_at=created_at),
            font=("Segoe UI", 10), text_color=PALETTE["text_muted"],
        ).pack(pady=(0, 8))

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(
            actions, text=t("✅ אשר לרינדור"), fg_color=PALETTE["success_btn"], hover_color=PALETTE["success_btn_hover"],
            command=lambda: self._decide(pending_id, video_path, True),
        ).pack(side="right", expand=True, fill="x", padx=(4, 0))
        ctk.CTkButton(
            actions, text=t("❌ דחה"), fg_color=PALETTE["danger"], hover_color=PALETTE["danger_hover"],
            command=lambda: self._decide(pending_id, video_path, False),
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

    def _load_thumbnail(self, video_path):
        try:
            os.makedirs(THUMBNAIL_CACHE_DIR, exist_ok=True)
            cache_path = os.path.join(
                THUMBNAIL_CACHE_DIR, f"{os.path.basename(video_path)}.{int(os.path.getmtime(video_path))}.jpg",
            )
            if not os.path.exists(cache_path):
                duration = get_video_duration_via_ffprobe(video_path, get_ffprobe_exe())
                extract_frame_at_timestamp(video_path, max(0.1, duration * 0.2), cache_path, get_ffmpeg_exe())
            if not os.path.exists(cache_path):
                return None
            image = Image.open(cache_path)
            image.thumbnail(THUMBNAIL_DISPLAY_SIZE)
            return ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
        except Exception:
            return None

    def _decide(self, pending_id, video_path, approved):
        approval_store.resolve_pending(pending_id, video_path, approved)
        self.refresh_approvals()
