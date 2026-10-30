# tests/web/test_web_settings_lazy.py
#
# 23.10.2026: ההגדרות הכלליות (31-global-settings.js) נטענות רק כשפותחים את המסך (LAZY_JS["settings"]) - כך הדף הראשי
# ירד מ-292,050 ל-289,143 בייט דחוסים. _applyAccentLive נשאר בראשי: 69-ui-prefs.js עוטף אותו כשהדף נטען.
from entrypoints.web import frontend_assembly as fa


def test_the_general_settings_code_is_not_in_the_main_bundle():
    main = fa.bundle("js")
    lazy = fa.lazy_bundle("settings")
    for name in ("loadGlobalSettings", "saveExportDir", "startDevicePairing", "loadRemoteAccess", "saveStyleSettings"):
        assert f"function {name}(" in lazy and f"function {name}(" not in main, name
    assert "function _applyAccentLive(" in main and "function _infoLine(" in main
    assert 'uiLoadLazy("settings")' in main
