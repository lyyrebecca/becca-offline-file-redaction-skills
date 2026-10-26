@echo off
setlocal
set "PYTHONUTF8=1"
if defined LPC_PYTHON (set "LPC_RUNTIME=%LPC_PYTHON%") else (set "LPC_RUNTIME=%LOCALAPPDATA%\legal-privacy-cloak\venv\Scripts\python.exe")
if not exist "%LPC_RUNTIME%" (
  echo Local runtime missing. Please follow docs/INSTALL.md for Windows setup.
  exit /b 1
)
"%LPC_RUNTIME%" "%~dp0lpc.py" %*
