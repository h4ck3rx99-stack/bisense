@echo off
rem BISense one-click start for Windows. Double-click this file.
rem First run: installs everything (incl. the offline speech model, ~460 MB), downloads the official BIS
rem data and builds the index (15-30 minutes, needs internet).
rem Later runs: starts straight away. Close this window (or press Ctrl+C) to stop BISense.
rem
rem Online or local is chosen automatically at every start (scripts\choose-mode.ps1):
rem   ONLINE  Groq reachable with the key in .env -> Groq answers and speech; Ollama (if installed) is the backup,
rem           used by itself when Groq fails or its free daily allowance runs out.
rem   LOCAL   no internet / no key -> Ollama answers (if installed), Whisper on this computer for speech;
rem           without Ollama, answers show the official sources verbatim.
rem Force a mode:  start-bisense.bat online   or   start-bisense.bat local
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
rem New BISense versions may need new parts (e.g. the offline speech model): rerun setup once when
rem scripts\setup-version.txt differs from what the last setup recorded.
if not exist "data\.setup-version" goto :setup
fc /b "scripts\setup-version.txt" "data\.setup-version" >nul 2>nul
if errorlevel 1 goto :setup
goto :data

:setup
echo  [1/3] Setup: installing dependencies, search models and the offline speech model...
call npm run setup
if errorlevel 1 (
  echo  [!] Setup failed. Check your internet connection and the messages above.
  goto :fail
)

rem --- 3. Official BIS data (downloaded once; resumes if a previous download was interrupted) ---------
:data
if exist "data\public\COMPLETE" goto :index
echo  [2/3] Downloading official BIS pages and documents (needs internet; resumes where it stopped)...
call npm run fetch-public
rem New files arrived: refresh the index (only changed files are re-read).
set REBUILD=1
if exist "data\public\COMPLETE" goto :index
if exist "data\public\fetch_log.yaml" (
  echo.
  echo  [!] Some official files could not be downloaded right now. BISense starts with the ones it has;
  echo      run this file again later to fetch the rest.
  echo.
  goto :index
)
set REBUILD=
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
if defined REBUILD goto :ingest
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
echo  Choosing online or local mode...
set "BISENSE_MODE=%~1"
if not defined BISENSE_MODE set "BISENSE_MODE=auto"
if /i not "%BISENSE_MODE%"=="online" if /i not "%BISENSE_MODE%"=="local" set "BISENSE_MODE=auto"
set "MODE_FILE=%TEMP%\bisense-mode-%RANDOM%.cmd"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\choose-mode.ps1" -Out "%MODE_FILE%" -Mode %BISENSE_MODE%
if exist "%MODE_FILE%" (
  call "%MODE_FILE%"
  del /q "%MODE_FILE%" >nul 2>nul
)
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
