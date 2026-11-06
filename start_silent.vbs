Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)

WshShell.CurrentDirectory = strPath

pyExe = "C:\Users\SJC\AppData\Local\Python\bin\python.exe"
If Not fso.FileExists(pyExe) Then
    pyExe = "python.exe"
End If

cmdLine = "%comspec% /c """"" & pyExe & """ -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> """ & strPath & "\server.log"" 2>&1"""
WshShell.Run cmdLine, 0, False
