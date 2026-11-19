@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo.
echo [Bid Radar] running tests...
echo.
"%PY%" -m pytest tests/ -q --tb=short > test_output.txt 2>&1
type test_output.txt
echo.
echo ------------------------------------------------------------
echo Full output saved to: %CD%\test_output.txt
echo Send this file to the reviewer.
echo ------------------------------------------------------------
pause
