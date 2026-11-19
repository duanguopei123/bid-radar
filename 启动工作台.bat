@echo off
cd /d "C:\Users\ZJ\WorkBuddy\2026-11-19-14-31-48\bid-radar"
echo === Bid Radar: running daily pipeline (all projects view) ===
"C:\Users\ZJ\AppData\Local\Programs\Python\Python313\python.exe" run_once.py --all
echo.
echo === Opening latest brief in browser... ===
set "LATEST="
for /f "delims=" %%i in ('dir /b /o-d out\brief_*.html 2^>nul') do if not defined LATEST set "LATEST=%%i"
if defined LATEST (start "" "out\%LATEST%") else (echo No brief found in out folder.)
echo.
pause
