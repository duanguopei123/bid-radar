@echo off
cd /d "%~dp0"
set "PYW=.venv\Scripts\pythonw.exe"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] .venv not found.
    echo Re-create the virtual environment before running this launcher.
    pause
    exit /b 1
)
if exist "%PYW%" (
    start "" "%PYW%" settings_gui.py
) else (
    start "" "%PY%" settings_gui.py
)
exit /b 0
