@echo off
rem Double-click launcher for Windows. Keep ASCII only: cmd.exe reads batch files with the
rem OEM code page. All Chinese UI text is printed by the Python layer as UTF-8.
setlocal
chcp 65001 >nul 2>nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "HERE=%~dp0"
if not exist "%HERE%scripts\run.cmd" (
  echo This file must stay inside the skill folder, next to the scripts directory.
  pause
  exit /b 2
)
call "%HERE%scripts\run.cmd" desktop
set "CODE=%errorlevel%"
if not "%CODE%"=="0" (
  echo.
  echo Startup failed with code %CODE%. Read the messages above.
  echo If Python or the local engine is missing, run: python scripts\bootstrap.py
  pause
)
exit /b %CODE%
