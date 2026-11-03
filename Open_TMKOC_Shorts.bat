@echo off
cd /d "C:\Users\SJC\.gemini\antigravity\scratch\tmkoc_shorts_automator"

netstat -ano | findstr :8000 >nul 2>&1
if %errorlevel% neq 0 (
    wscript.exe start_silent.vbs
    timeout /t 2 /nobreak >nul
)

start "" "http://localhost:8000"
