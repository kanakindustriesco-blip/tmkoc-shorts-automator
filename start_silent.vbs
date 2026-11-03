Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)

' Set working directory to project root
WshShell.CurrentDirectory = strPath

' Try full python path first, fallback to standard python command
pyExe = "C:\Users\SJC\AppData\Local\Python\bin\python.exe"
If Not fso.FileExists(pyExe) Then
    pyExe = "python.exe"
End If

WshShell.Run """" & pyExe & """ -m uvicorn app.main:app --host 0.0.0.0 --port 8000", 0, False
