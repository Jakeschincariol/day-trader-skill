@echo off
cd /d "%~dp0"
echo Starting TraderDash with iPhone access...
echo On this PC open http://127.0.0.1:8212 and click "Use on iPhone" at the bottom.
start "" http://127.0.0.1:8212
python server.py --phone || py server.py --phone
pause
