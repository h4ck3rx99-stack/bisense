@echo off
rem BISense one-click start for Windows. Double-click this file.
rem First run: installs everything, downloads the official BIS data and builds the index (10-20 minutes).
rem Later runs: starts straight away. Close this window (or press Ctrl+C) to stop BISense.
setlocal
cd /d "%~dp0"
title BISense

echo.
echo  ==============================================
echo    BISense - starting up
echo  ==============================================
echo.

rem --- 1. Check the tools BISense needs -------------------------------------------------------------
where node >nul 2>nul
if errorlevel 1 (
  echo  [!] Node.js is not installed.
  echo      Install the LTS version from https://nodejs.org , then double-click this file again.
  goto :fail
)
where uv >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo  [!] Python is not installed.
    echo      Install uv from https://docs.astral.sh/uv/  ^(recommended^)
    echo      or Python 3.12 from https://www.python.org/downloads/ , then double-click this file again.
    goto :fail
  )
)

rem --- 2. First-time setup (dependencies, .env, search models) --------------------------------------
if not exist "web\node_modules" goto :setup
if not exist ".env" goto :setup
goto :data

:setup
echo  [1/3] First-time setup: installing dependencies and search models...
call npm run setup
if errorlevel 1 (
  echo  [!] Setup failed. Check your internet connection and the messages above.
  goto :fail
)

rem --- 3. Official BIS data (downloaded once) ------------------------------------------------------
:data
if exist "data\public\fetch_log.yaml" goto :index
echo  [2/3] Downloading official BIS pages and documents (once; needs internet)...
call npm run fetch-public
if exist "data\public\fetch_log.yaml" goto :index
echo.
echo  [!] The official BIS data could not be downloaded (no internet?).
echo      Starting in SAMPLE MODE: sample documents only, labelled "Sample data, not official".
echo      Run this file again with internet to switch to the official data.
echo.
set DATASET=sample
if exist "data\index\sample-mode.flag" if exist "data\index\bisense.db" goto :run
if exist "data\index\bisense.db" del /q "data\index\bisense.db" >nul 2>nul
if not exist "data\index" mkdir "data\index"
echo sample> "data\index\sample-mode.flag"
goto :ingest

rem --- 4. Build the search index (only when missing) -----------------------------------------------
:index
rem An index built earlier in sample mode is rebuilt now that the official data is here.
if exist "data\index\sample-mode.flag" (
  del /q "data\index\sample-mode.flag" >nul 2>nul
  if exist "data\index\bisense.db" del /q "data\index\bisense.db" >nul 2>nul
)
if exist "data\index\bisense.db" goto :run
:ingest
echo  [3/3] Building the search index...
call npm run ingest
if errorlevel 1 (
  echo  [!] Building the index failed. See the messages above.
  goto :fail
)

rem --- 5. Start BISense and open the browser ------------------------------------------------------
:run
echo.
echo  BISense will open in your browser at http://127.0.0.1:8000
echo  Keep this window open while you use it. Close it to stop BISense.
echo.
rem Opens the browser as soon as the server answers (up to 6 minutes on the first run).
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -Command "for($i=0;$i -lt 180;$i++){try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/api/health | Out-Null; Start-Process 'http://127.0.0.1:8000'; break}catch{Start-Sleep -Seconds 2}}"
call npm run demo
if errorlevel 1 (
  echo  [!] BISense stopped with an error. See the messages above.
  goto :fail
)
goto :end

:fail
echo.
pause
exit /b 1

:end
endlocal
