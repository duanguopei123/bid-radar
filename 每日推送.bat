@echo off
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" exit /b 1
if not exist logs mkdir logs
"%PY%" run_once.py --all >> logs\daily.log 2>&1
exit /b %errorlevel%
