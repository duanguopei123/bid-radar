@echo off
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" goto :missing_venv

echo.
echo [Bid Radar] running daily pipeline...
echo.
"%PY%" run_once.py --all
if errorlevel 1 goto :run_failed

echo.
echo [Bid Radar] opening latest brief...
set "LATEST="
for /f "delims=" %%i in ('dir /b /o-d out\brief_*.html 2^>nul') do if not defined LATEST set "LATEST=%%i"
if defined LATEST start "" "out\%LATEST%"
if not defined LATEST echo [WARN] no brief found in out folder.
echo.
pause
exit /b 0

:missing_venv
echo [ERROR] .venv not found.
echo Re-create the virtual environment before running this launcher.
echo.
pause
exit /b 1

:run_failed
echo [ERROR] Pipeline failed. See the error above.
echo The latest brief was not opened.
echo.
pause
exit /b 1
