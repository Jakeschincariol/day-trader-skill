@echo off
rem Trading Desk launcher: starts the local server and opens the app window.
cd /d "%~dp0\..\..\.."
where python >nul 2>nul && (set PY=python) || (set PY=py -3)
start "Trading Desk server" /min %PY% ".claude\desk\app\server.py"
