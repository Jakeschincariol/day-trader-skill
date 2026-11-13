@echo off
rem Builds TradingDesk.exe (one file, no console) with PyInstaller.
rem Usage: .claude\desk\app\build_exe.bat [output folder]   (default: %USERPROFILE%\Desktop)
setlocal
cd /d "%~dp0\..\..\.."
set OUT=%~1
if "%OUT%"=="" set OUT=%USERPROFILE%\Desktop
set WORK=%TEMP%\tradingdesk-build
python -m PyInstaller --noconfirm --clean --onefile --noconsole --name TradingDesk ^
  --distpath "%OUT%" --workpath "%WORK%" --specpath "%WORK%" ^
  --paths trader-scanner --paths .claude\desk\app ^
  --hidden-import scan --hidden-import live --collect-data tzdata ^
  --add-data "%CD%\.claude\desk\app\index.html;." ^
  .claude\desk\app\server.py
echo Built: %OUT%\TradingDesk.exe
