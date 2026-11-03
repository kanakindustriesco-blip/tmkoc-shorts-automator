@echo off
title Setup 24x7 Silent Background Service
cd /d "%~dp0"

echo =========================================================================
echo          TMKOC SHORTS AUTOMATOR - 24x7 BACKGROUND SERVICE SETUP
echo =========================================================================
echo.

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS_SCRIPT=%~dp0start_silent.vbs"

echo [1/3] Adding Silent Background Launcher to Windows Startup folder...
echo Set oWS = WScript.CreateObject("WScript.Shell") > "%TEMP%\CreateShortcut.vbs"
echo sLinkFile = "%STARTUP_FOLDER%\TMKOC_Shorts_Automator.lnk" >> "%TEMP%\CreateShortcut.vbs"
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%TEMP%\CreateShortcut.vbs"
echo oLink.TargetPath = "wscript.exe" >> "%TEMP%\CreateShortcut.vbs"
echo oLink.Arguments = """%VBS_SCRIPT%""" >> "%TEMP%\CreateShortcut.vbs"
echo oLink.WorkingDirectory = "%~dp0" >> "%TEMP%\CreateShortcut.vbs"
echo oLink.Description = "TMKOC Shorts Automator 24x7 Service" >> "%TEMP%\CreateShortcut.vbs"
echo oLink.Save >> "%TEMP%\CreateShortcut.vbs"
cscript //nologo "%TEMP%\CreateShortcut.vbs"
del "%TEMP%\CreateShortcut.vbs" >nul 2>&1

echo [2/3] Registering Windows Scheduled Task for Auto-Start on Login...
schtasks /create /tn "TMKOC_Shorts_Automator" /tr "wscript.exe \"%VBS_SCRIPT%\"" /sc onlogon /f >nul 2>&1

echo [3/3] Starting the 24x7 Background Service now...
wscript.exe "%VBS_SCRIPT%"

echo.
echo =========================================================================
echo SUCCESS! 24x7 Background Service successfully activated!
echo.
echo - System will now run 24x7 in the background silently.
echo - When Windows restarts or boots, it will start automatically.
echo - Access dashboard anytime at: http://localhost:8000
echo - To stop the service anytime, double-click "stop_service.bat".
echo =========================================================================
echo.
pause
