@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "OUT=review_diff.txt"

echo [Bid Radar] exporting working-tree diff...
echo.

> "%OUT%" echo ===== git status =====
>> "%OUT%" git status --short
>> "%OUT%" echo.
>> "%OUT%" echo ===== diff --stat =====
>> "%OUT%" git diff --stat
>> "%OUT%" echo.
>> "%OUT%" echo ===== full diff =====
>> "%OUT%" git diff
>> "%OUT%" echo.
>> "%OUT%" echo ===== untracked files =====
>> "%OUT%" git ls-files --others --exclude-standard
>> "%OUT%" echo.
>> "%OUT%" echo ===== test result =====
>> "%OUT%" ".venv\Scripts\python.exe" -m pytest tests/ -q 2>&1

echo.
echo Done. File: %CD%\%OUT%
echo.
echo Send this file to the reviewer.
echo.
pause
