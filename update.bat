@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat and build_installer.bat first on the HOST computer.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" build_release.py
if errorlevel 1 (
    echo Update publication failed. The previous published release remains available.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m deployment.host_control start
if errorlevel 1 (
    echo Release published, but the OTA host could not start. See the error above.
    pause
    exit /b 1
)
echo Update published and OTA host ready. Clients check when they next open IDFrame.
pause
