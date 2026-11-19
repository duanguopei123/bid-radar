@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=C:\Users\ZJ\AppData\Local\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=python"

echo.
echo [Bid Radar] running daily pipeline...
echo.
"%PY%" run_once.py --all

if errorlevel 1 echo [ERROR] run failed. check .venv or the log above.

echo.
echo [Bid Radar] opening latest brief...
set "LATEST="
for /f "delims=" %%i in ('dir /b /o-d out\brief_*.html 2^>nul') do if not defined LATEST set "LATEST=%%i"
if defined LATEST start "" "out\%LATEST%"
if not defined LATEST echo [WARN] no brief found in out folder.
echo.
pause
