@echo off
rem Double-click to drive the car with the Muse connected straight to this PC over Bluetooth (no phone app). The headband must not be connected to the phone. See README.md.
cd /d "%~dp0"
python tools\muse_drive.py --muse %*
echo.
pause
