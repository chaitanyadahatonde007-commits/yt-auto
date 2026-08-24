@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo.
  echo Python is not on PATH.
  echo Install Python 3.11 or newer from https://www.python.org/downloads/
  echo Tick "Add python.exe to PATH", then open a new Command Prompt here.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Failed to create .venv
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo pip install failed
  pause
  exit /b 1
)

if not exist "vendor\espeak-ng\espeak-ng.wasm" (
  where npm >nul 2>&1
  if errorlevel 1 (
    echo.
    echo Node.js / npm is not on PATH. The local voice engine needs it.
    echo Install LTS from https://nodejs.org/ then open a new Command Prompt.
    echo.
    pause
    exit /b 1
  )
  echo Installing local voice runtime...
  if not exist "vendor\espeak-ng" mkdir "vendor\espeak-ng"
  if not exist "%TEMP%\channelforge-espeak" mkdir "%TEMP%\channelforge-espeak"
  npm pack espeak-ng --pack-destination "%TEMP%\channelforge-espeak"
  for %%F in ("%TEMP%\channelforge-espeak\espeak-ng-*.tgz") do (
    tar -xzf "%%F" -C "%TEMP%\channelforge-espeak"
  )
  copy /Y "%TEMP%\channelforge-espeak\package\dist\espeak-ng.js" "vendor\espeak-ng\" >nul
  copy /Y "%TEMP%\channelforge-espeak\package\dist\espeak-ng.wasm" "vendor\espeak-ng\" >nul
)

if "%YT_AUTO_HOST%"=="" set "YT_AUTO_HOST=127.0.0.1"
if "%YT_AUTO_PORT%"=="" set "YT_AUTO_PORT=8000"
set PYTHONUNBUFFERED=1

echo.
echo ChannelForge is starting.
echo Open http://localhost:%YT_AUTO_PORT%
echo Leave this window open. Press Ctrl+C to stop.
echo.

python -m uvicorn app.main:app --host %YT_AUTO_HOST% --port %YT_AUTO_PORT%
if errorlevel 1 pause
