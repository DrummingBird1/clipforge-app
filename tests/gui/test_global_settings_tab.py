# tests/gui/test_global_settings_tab.py
#
# בודק את כפתורי הגיבוי המוצפן שנוספו ל-GlobalSettingsTabComponent (item:
# encrypted local backup bundle) - בלי לגעת ב-data/ האמיתי של הפרויקט בכלל:
# utils/encrypted_backup.create_backup_bundle/restore_backup_bundle עצמם
# ממוקים כאן לחלוטין (כבר מכוסים ישירות ב-tests/infra/test_encrypted_backup.py),
# והדיאלוג (ui.widgets.PassphraseDialog) מוחלף בגרסה מזויפת שמגדירה .result.
# ההרס מתוזמן דרך after() ולא קורה מיד בתוך __init__ - self.wait_window(dialog)
# עושה tkwait על window._w בפועל, אז אם החלון כבר נהרס לפני שהגענו לשם, ה-path
# הזה כבר לא קיים ב-Tcl בכלל (TclError: bad window path name) - צריך שהחלון
# עדיין "יהיה שם" ברגע הקריאה, וייהרס רק תוך כדי לולאת האירועים ש-wait_window
# עצמו מפעיל, אותו עיקרון שנקבע כבר לגבי אימות ויזואלי של gui_manager.pyw:
# widget-construction אמיתי + לוגיקה ממוקת, בלי צילום מסך על שולחן העבודה האמיתי.


import customtkinter as ctk
import pytest

import ui.global_settings_tab as global_settings_tab
from ui.global_settings_tab import GlobalSettingsTabComponent


class _FakeApp:
    pass


class _FakePassphraseDialog(ctk.CTkToplevel):
    result_to_return = "correct-horse-battery-staple"

    def __init__(self, parent, title, prompt):
        super().__init__(parent)
        self.result = type(self).result_to_return
        self.after(10, self.destroy)


@pytest.fixture
def comp(shared_tk_root):
    component = GlobalSettingsTabComponent(shared_tk_root, _FakeApp())
    yield component
    component.destroy()


def test_encrypted_backup_buttons_are_constructed(comp):
    # t() מפעיל fix_hebrew_word_order (הופך את סדר המילים) על כל טקסט עברי
    # ללא ספרות/לטינית - אז בודקים מילים בודדות, לא צירוף רב-מילים בסדר קבוע.
    texts = [w.cget("text") for w in comp.card_left.winfo_children() if isinstance(w, ctk.CTkButton)]
    assert any("גיבוי" in t and "מוצפן" in t for t in texts)
    assert any("שחזר" in t for t in texts)


def test_create_encrypted_backup_calls_util_with_dialog_passphrase_and_chosen_path(comp, tmp_path, monkeypatch):
    monkeypatch.setattr(global_settings_tab, "PassphraseDialog", _FakePassphraseDialog)
    output_path = str(tmp_path / "chosen_backup.ibkp")
    monkeypatch.setattr(global_settings_tab.filedialog, "asksaveasfilename", lambda **kw: output_path)
    calls = []
    monkeypatch.setattr(
        global_settings_tab.encrypted_backup, "create_backup_bundle",
        lambda passphrase, path: calls.append((passphrase, path)) or {"included_files": ["config.json"], "size_bytes": 123},
    )
    info_calls = []
    monkeypatch.setattr(global_settings_tab.messagebox, "showinfo", lambda *a, **kw: info_calls.append((a, kw)))

    comp.create_encrypted_backup()

    assert len(calls) == 1
    assert calls[0] == ("correct-horse-battery-staple", output_path)
    assert len(info_calls) == 1


def test_create_encrypted_backup_does_nothing_when_passphrase_dialog_cancelled(comp, monkeypatch):
    class _CancelledDialog(_FakePassphraseDialog):
        result_to_return = None

    monkeypatch.setattr(global_settings_tab, "PassphraseDialog", _CancelledDialog)
    save_calls = []
    monkeypatch.setattr(global_settings_tab.filedialog, "asksaveasfilename", lambda **kw: save_calls.append(1) or "")

    comp.create_encrypted_backup()

    assert save_calls == []  # לא בכלל מגיע לפתיחת דיאלוג שמירת-קובץ


def test_create_encrypted_backup_does_nothing_when_save_dialog_cancelled(comp, monkeypatch):
    monkeypatch.setattr(global_settings_tab, "PassphraseDialog", _FakePassphraseDialog)
    monkeypatch.setattr(global_settings_tab.filedialog, "asksaveasfilename", lambda **kw: "")
    calls = []
    monkeypatch.setattr(global_settings_tab.encrypted_backup, "create_backup_bundle", lambda *a, **kw: calls.append(1))

    comp.create_encrypted_backup()

    assert calls == []


def test_create_encrypted_backup_shows_error_on_backup_error(comp, tmp_path, monkeypatch):
    monkeypatch.setattr(global_settings_tab, "PassphraseDialog", _FakePassphraseDialog)
    monkeypatch.setattr(global_settings_tab.filedialog, "asksaveasfilename", lambda **kw: str(tmp_path / "out.ibkp"))

    def _raise(*a, **kw):
        raise global_settings_tab.encrypted_backup.BackupError("סיסמה שגויה או שקובץ הגיבוי פגום.")

    monkeypatch.setattr(global_settings_tab.encrypted_backup, "create_backup_bundle", _raise)
    error_calls = []
    monkeypatch.setattr(global_settings_tab.messagebox, "showerror", lambda *a, **kw: error_calls.append((a, kw)))

    comp.create_encrypted_backup()

    assert len(error_calls) == 1


def test_restore_encrypted_backup_calls_util_after_confirmation(comp, tmp_path, monkeypatch):
    input_path = str(tmp_path / "existing_backup.ibkp")
    monkeypatch.setattr(global_settings_tab.filedialog, "askopenfilename", lambda **kw: input_path)
    monkeypatch.setattr(global_settings_tab.messagebox, "askyesno", lambda *a, **kw: True)
    monkeypatch.setattr(global_settings_tab, "PassphraseDialog", _FakePassphraseDialog)
    calls = []
    monkeypatch.setattr(
        global_settings_tab.encrypted_backup, "restore_backup_bundle",
        lambda passphrase, path: calls.append((passphrase, path)) or {"restored_files": ["config.json", "clipforge_data.db"]},
    )
    info_calls = []
    monkeypatch.setattr(global_settings_tab.messagebox, "showinfo", lambda *a, **kw: info_calls.append((a, kw)))

    comp.restore_encrypted_backup()

    assert calls == [("correct-horse-battery-staple", input_path)]
    assert len(info_calls) == 1


def test_restore_encrypted_backup_does_nothing_when_confirmation_declined(comp, tmp_path, monkeypatch):
    monkeypatch.setattr(global_settings_tab.filedialog, "askopenfilename", lambda **kw: str(tmp_path / "x.ibkp"))
    monkeypatch.setattr(global_settings_tab.messagebox, "askyesno", lambda *a, **kw: False)
    calls = []
    monkeypatch.setattr(global_settings_tab.encrypted_backup, "restore_backup_bundle", lambda *a, **kw: calls.append(1))

    comp.restore_encrypted_backup()

    assert calls == []


def test_restore_encrypted_backup_shows_error_on_wrong_passphrase(comp, tmp_path, monkeypatch):
    monkeypatch.setattr(global_settings_tab.filedialog, "askopenfilename", lambda **kw: str(tmp_path / "x.ibkp"))
    monkeypatch.setattr(global_settings_tab.messagebox, "askyesno", lambda *a, **kw: True)
    monkeypatch.setattr(global_settings_tab, "PassphraseDialog", _FakePassphraseDialog)

    def _raise(*a, **kw):
        raise global_settings_tab.encrypted_backup.BackupError("סיסמה שגויה או שקובץ הגיבוי פגום.")

    monkeypatch.setattr(global_settings_tab.encrypted_backup, "restore_backup_bundle", _raise)
    error_calls = []
    monkeypatch.setattr(global_settings_tab.messagebox, "showerror", lambda *a, **kw: error_calls.append((a, kw)))

    comp.restore_encrypted_backup()

    assert len(error_calls) == 1
