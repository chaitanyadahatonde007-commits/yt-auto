@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where py >nul 2>&1 (
  py -3 run.py
  if errorlevel 1 pause
  exit /b %errorlevel%
)

where python >nul 2>&1 (
  python run.py
  if errorlevel 1 pause
  exit /b %errorlevel%
)

echo.
echo Python is not on PATH.
echo Install Python 3.11+ from https://www.python.org/downloads/
echo Tick "Add python.exe to PATH", then open a new Command Prompt here.
echo.
pause
exit /b 1
