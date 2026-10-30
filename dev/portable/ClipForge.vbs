' ClipForge (portable package) - dev/portable/ClipForge.vbs, copied to the package root by dev/build_portable.py.
' Opens ClipForge in the browser: launcher.pyw starts the app the first time, or reuses the one already running.
' pythonw.exe and window style 0: no console window at all.
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = root
shell.Run """" & root & "\python\pythonw.exe"" """ & root & "\launcher.pyw""", 0, False
