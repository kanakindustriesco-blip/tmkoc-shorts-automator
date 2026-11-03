Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)

' Run uvicorn completely in background (0 = hidden window)
WshShell.CurrentDirectory = strPath
WshShell.Run "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000", 0, False
