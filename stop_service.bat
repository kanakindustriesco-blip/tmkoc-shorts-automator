@echo off
title Stop TMKOC Shorts Automator Service
cd /d "%~dp0"

echo Stopping TMKOC Shorts Automator background processes...
powershell -Command "Get-Process -Name 'python' -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'uvicorn' -or $_.Path -match 'tmkoc' } | Stop-Process -Force"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo Background service stopped.
pause
