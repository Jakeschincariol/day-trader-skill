@echo off
rem Builds Saladi.exe (one file, no console, with its icon) with PyInstaller.
rem Usage: .claude\desk\app\build_exe.bat [output folder]   (default: %USERPROFILE%\Desktop)
setlocal
cd /d "%~dp0\..\..\.."
set OUT=%~1
if "%OUT%"=="" set OUT=%USERPROFILE%\Desktop
set WORK=%TEMP%\saladi-build
set APP=%CD%\.claude\desk\app
python -m PyInstaller --noconfirm --clean --onefile --noconsole --name Saladi --icon "%APP%\saladi.ico" ^
  --distpath "%OUT%" --workpath "%WORK%" --specpath "%WORK%" ^
  --paths trader-scanner --paths .claude\desk\app ^
  --hidden-import scan --hidden-import live --collect-data tzdata ^
  --add-data "%APP%\index.html;." --add-data "%APP%\saladi.ico;." --add-data "%APP%\saladi.png;." ^
  .claude\desk\app\server.py
echo Built: %OUT%\Saladi.exe
