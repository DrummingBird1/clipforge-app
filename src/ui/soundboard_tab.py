# ui/soundboard_tab.py
import customtkinter as ctk
from utils.shared.sound import play_board_sound
from utils.shared.state import state  # שורת הזהב שהייתה חסרה!
from utils.shared.i18n import t

class SoundboardTabComponent(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._build_tab()

    def _build_tab(self):
        self.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(self, text=t("🔊 פאנל אפקטים קוליים לסטרימינג"), font=("Segoe UI", 13, "bold"), text_color=state.current_theme["accent"]).grid(row=0, column=0, columnspan=3, pady=20)
        
        ctk.CTkButton(self, text="🚨 Airhorn", command=lambda: play_board_sound(880, 400)).grid(row=1, column=0, padx=15, pady=15, sticky="ew")
        ctk.CTkButton(self, text="💥 Boom", command=lambda: play_board_sound(150, 600)).grid(row=1, column=1, padx=15, pady=15, sticky="ew")
        ctk.CTkButton(self, text="🎮 Game Over", command=lambda: play_board_sound(293, 500)).grid(row=1, column=2, padx=15, pady=15, sticky="ew")