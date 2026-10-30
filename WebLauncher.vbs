' WebLauncher.vbs
'
' מקביל בדיוק ל-Launcher.vbs, אבל לגרסת הדפדפן (src/entrypoints/web_app.py)
' במקום ה-GUI השולחני. מריץ את dev\_web_launcher_impl.bat לגמרי
' מוסתר (בלי חלון CMD), ממתין שהשרת יעלה בפועל ואז פותח את הדפדפן עם הטוקן
' הנכון - לא צריך לקרוא לוג כדי למצוא URL. פרטי כשל נכתבים ל-
' data\logs\web_launcher.log (לא לקונסולה, שממילא מוסתרת).
Dim fso, shell, scriptDir, batPath, exitCode

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\dev\_web_launcher_impl.bat"

exitCode = shell.Run(Chr(34) & batPath & Chr(34), 0, True)

If exitCode <> 0 Then
    MsgBox "ההפעלה נכשלה (קוד " & exitCode & "). פרטים בקובץ data\logs\web_launcher.log.", vbCritical, "WebLauncher"
End If
