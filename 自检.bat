@echo off
setlocal
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [ERROR] .venv not found: %PY%
    echo Please recreate the virtual environment, see README.
    pause
    exit /b 1
)

if not exist "selfcheck.py" (
    echo [ERROR] selfcheck.py not found in %CD%
    pause
    exit /b 1
)

"%PY%" selfcheck.py
echo.
pause
