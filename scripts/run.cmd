@echo off
rem ASCII-only on purpose: cmd.exe parses batch files with the OEM code page, so Chinese
rem text here would be mangled on a cp936/cp437 console. The Python layer prints UTF-8.
setlocal
chcp 65001 >nul 2>nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "HERE=%~dp0"
set "PY="

if not "%LPC_BOOTSTRAP_PYTHON%"=="" call :try %LPC_BOOTSTRAP_PYTHON%
if not defined PY call :try py -3.12
if not defined PY call :try py -3.11
if not defined PY call :try python
if not defined PY goto missing

%PY% "%HERE%run.py" %*
exit /b %errorlevel%

:try
rem Accept only Python 3.11/3.12 so a stray 3.8 python.exe cannot fail with a syntax error.
%* "%HERE%pyversion.py" >nul 2>nul
if not errorlevel 1 set "PY=%*"
exit /b 0

:missing
echo Python 3.11 or 3.12 was not found.
echo Install Python 3.12 from https://www.python.org/downloads/windows/ and tick
echo "Add python.exe to PATH", or set LPC_BOOTSTRAP_PYTHON to its full path.
exit /b 2
