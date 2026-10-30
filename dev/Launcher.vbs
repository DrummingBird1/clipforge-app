' dev/Launcher.vbs - ה-GUI השולחני (קפוא). נקודת הכניסה הראשית היא WebLauncher.vbs בשורש.
'
' נקודת הכניסה בפועל - זה מה שאמור להיות מכופל-קליק. שם הבת' עצמו שונה בכוונה
' ל-_launcher_impl.bat (לא "Launcher.bat") - כששני קבצים נקראים "Launcher"
' (רק סיומת שונה) קל מדי לכפול-קליק בטעות על הבת' במקום ה-vbs ולקבל בכל זאת
' חלון CMD. מריץ את _launcher_impl.bat לגמרי מוסתר (בלי חלון CMD בכלל, ראה
' WindowStyle=0 למטה) וממתין לסיום (bWaitOnReturn=True) כדי לתפוס את קוד
' היציאה שלו. הוא עצמו כותב את כל הפלט שלו ל-data\logs\launcher.log (לא
' לקונסולה, שממילא מוסתרת) - אם הוא נכשל, מוצגת כאן הודעת שגיאה אחת פשוטה במקום.
Dim fso, shell, scriptDir, batPath, exitCode

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\_launcher_impl.bat"

exitCode = shell.Run(Chr(34) & batPath & Chr(34), 0, True)

If exitCode <> 0 Then
    MsgBox "ההפעלה נכשלה (קוד " & exitCode & "). פרטים בקובץ data\logs\launcher.log.", vbCritical, "Launcher"
End If
