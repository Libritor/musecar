@echo off
rem Double-click to test the car with made-up headband data: after a mock calibration it drives forward for 10 s and stops for 10 s, in turn. See README.md.
cd /d "%~dp0"
python tools\muse_drive.py --simulate %*
echo.
pause
