@echo off
rem Double-click to drive the car from the Muse headband. See README.md.
cd /d "%~dp0"
python tools\muse_drive.py %*
echo.
pause
