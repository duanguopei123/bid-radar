@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo [Bid Radar] running tests with project venv...
echo.
".venv\Scripts\python.exe" -m pytest tests/ -q
echo.
pause
