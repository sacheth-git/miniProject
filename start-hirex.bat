@echo off
rem Starts HireX locally: API on port 8000, website on port 5173. Close the two windows to stop.
start "HireX API" /d "%~dp0backend" cmd /k "set ENABLE_SCHEDULER=false&& .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "HireX Web" /d "%~dp0frontend" cmd /k "npm run dev -- --host 127.0.0.1"
echo Waiting for HireX to start...
timeout /t 12 /nobreak >nul
start "" http://127.0.0.1:5173
