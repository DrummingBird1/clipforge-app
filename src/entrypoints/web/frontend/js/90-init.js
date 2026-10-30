// item: התקנת PWA - שירות-עובד רשום (בנוסף ל-manifest.json שכבר היה קיים)
// הוא מה שמאפשר בפועל להתקין את הדף כאפליקציה (beforeinstallprompt) ברוב
// הדפדפנים, לא רק סימניה. serviceWorker לא קיים בכלל ב-http:// שאינו
// localhost (secure context) - אין צורך לבדוק את זה במפורש, הדפדפן פשוט
// לא יחשוף את ה-API במקרה כזה.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

updateNotifyBtn();
loadScripts();
// item: בחירת פרופיל אחרונה נשמרת בין ריענונים - חייב לרוץ אחרי שה-<select>
// מלא באפשרויות (loadVideoEditorPresets/loadVideoEditorProfiles), לא לפניו.
loadVideoEditorPresets().then(_restoreVeLastProfileSelection).then(_veHandleImportProfileLink);
loadHistory();
checkUndoStatus();
loadLockStatus();
pollWhenVisible(loadLockStatus, 5000);
loadQueueStatus();
pollWhenVisible(loadQueueStatus, 5000);
refreshNotificationBadge();
pollWhenVisible(refreshNotificationBadge, 30000);
loadHardwareStats();
pollWhenVisible(loadHardwareStats, 2000);
connectWs();
checkForUpdate();
// 23.10.2026: קישור ישיר למסך (/?screen=phone - אחרי צימוד טלפון)
const _uiStartScreen = new URLSearchParams(location.search).get("screen");
if (_uiStartScreen && document.querySelector(`.nav-rail .tab-btn[data-tab="${CSS.escape(_uiStartScreen)}"]`)) switchTab(_uiStartScreen);
_captureVeFieldDefaults();
_setupPerFieldResetButtons();
_setupGlossaryKeyboardNav();
_veEnhanceInputs();
_setupVeFieldHistory();
_veRefreshRangeLabels();
updateVeCodecDependentRows();
syncAutoFavorites();
_veInitOrganization();
_veInitPreviewFeedback();
_veApplyAria();
_veApplyDialogRoles();
_veApplySheetMode();
for (const details of _veCategoryEls()) _veRunLazyInit(details);
_veInitWave10();
_veInitWave12();
_veInitWave13();
_veInitWave14();
// גל 25: גלגלי הצבע ועורך העקומות
_veSetupGrade();
// גל 27: שבב התיקייה, פס הסטטוס, איפוס בקליק ימני, פריים אוטומטי וחיפוש בתור
_veInitWave27();
// גל 28: תתי-אזורים מתקפלים, שדות תלויים מהסכמה, שדות זמן ולשוניות בסטודיו
_veInitWave28();
// גל 29: ציר-הזמן והנגן כמשטח העריכה - פסים נגררים, רשימת שכבות, גרירת קבצים
_veInitWave29();
_veInitWave30();
_veInitWave31();
_veInitWave33();
_veInitWave34();
_veInitWave35();
_veInitWave36();
_uiInitShell();
if (_veLoadPref("veEnglish", false)) setVeEnglish(true);
// מונחי המקראה משמשים גם את החיפוש הגלובלי (item) - נטענים ברקע פעם אחת.
fetch("/api/video_editor/field_help").then(r => r.json()).then(data => { if (!_fieldHelpCache) _fieldHelpCache = data; }).catch(() => {});
// גל 18: הסטודיו (מפרידים, גרירה על תוויות, מסלול שכבות) - אחרי שכל האזורים אותחלו
_uiInitStudio();
// גלים 19-20: מסכים (עבודות/תוצאות/גלריה/אישור/טפסים/סטטיסטיקות/דיאלוגים) וליטוש
_uiInitScreens();
_uiInitPolish();
// גל 21: שפת הממשק (עברית/English) - אחרון, אחרי שכל הטקסט הדינמי הראשוני נבנה
_uiInitPrefs();
