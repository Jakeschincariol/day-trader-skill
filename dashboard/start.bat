@echo off
cd /d "%~dp0"
echo Starting TraderDash... open http://127.0.0.1:8212 in your browser
start "" http://127.0.0.1:8212
python server.py || py server.py
pause
