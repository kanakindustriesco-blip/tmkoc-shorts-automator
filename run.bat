@echo off
title TMKOC Shorts Automator (16:9 to 9:16) & 5-Min Scheduler
cd /d "%~dp0"

echo =====================================================================
echo           TMKOC SHORTS AUTOMATOR & 5-MINUTE AUTO SCHEDULER
echo =====================================================================
echo Starting backend server on http://localhost:8000 ...
echo Opening web dashboard in default browser...

start "" "http://localhost:8000"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
pause
