@echo off
cd /d "%~dp0"
echo Starting the TraderDash DEMO (example portfolio, your accounts are not used)... open http://127.0.0.1:8214
start "" http://127.0.0.1:8214
python server.py --demo --port 8214 || py server.py --demo --port 8214
pause
