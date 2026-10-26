@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat and build_installer.bat first on the HOST computer.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m deployment.host_control start
pause
