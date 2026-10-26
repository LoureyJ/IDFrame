@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" download_model.py
if errorlevel 1 goto :failed
echo Ready! Double-click launch.bat to open IDFrame.
pause
exit /b 0
:failed
echo Setup failed. Check your internet connection and Python 3.12 installation, then retry.
pause
exit /b 1
